#!/usr/bin/env python3
"""PreToolUse hook for Claude Code and GitHub Copilot Chat: the local half of the stack's one rule.

The rule: agents never skip or change enforcement without the owner.

Claude Code runs it from .claude/settings.json. GitHub Copilot Chat in VS Code
(its Local agent) runs it from .github/hooks/agent-guard.json with --copilot,
and sends the same event fields under its own tool names: the terminal, file
edits and patches are checked as the Claude Code tool that does the same, and
any other tool by the files and commands its input names. Copilot Chat's
auto-approve modes skip prompts, so there the guard refuses where it would ask,
and refuses what it can't read, such as an editor command or an extension
install. The Copilot CLI and
cloud agent read that file too, but run a command that allows everything: the
guard doesn't cover them.

Skipping hooks is blocked outright, before the command runs:
  - git commit/merge/push/... with --no-verify, and git commit -n (also inside
    short-flag clusters such as -anm)
  - SKIP=, PRE_COMMIT_ALLOW_NO_CONFIG=, HUSKY= and GIT_CONFIG_* assignments
    (bash and PowerShell), which switch hooks off or inject git config
  - git -c core.hooksPath=... and git config core.hooksPath ...
  - pre-commit uninstall
  - any shell command that touches a path inside .git/ unless it is a known
    read-only command with no redirect, and Write/Edit calls inside .git/
  - git commit in a clone whose pre-commit config expects hooks that aren't
    installed

Changing enforcement needs the owner's approval. Enforcement is the files
listed in .github/CODEOWNERS (hooks, this guard, the gates and what they read),
Claude Code's and VS Code's settings files, and the repository's rules and
settings on GitHub. The guard sees file edits; shell writes, deletes and moves;
code run inline that writes files; git rm/mv/restore/checkout and patches applied with
git apply/am; every gh write except everyday work on issues, pull requests,
labels, branches and workflow runs; connector tools not named as reads that
touch enforcement files, or that write repository settings; and merging or
approving a pull request that changes enforcement files (renaming one away
counts), however it's done, unless the owner lets Dependabot's version bumps
merge on green (see dependabot_bump). It asks the owner; in a permission mode
that can't ask (such as bypass permissions) it refuses. If CODEOWNERS can't be
read, every change in the repository counts.

Azure: every az command must run against the tenant recorded in
.claude/security-stack.json (the one named with --tenant, or else the one az is
signed in to), or it's refused. An az command that isn't a read (show, list,
get, what-if, ...) needs the owner's approval too: Azure changes go through a
pull request and the deploy job. Signing in and the CLI's own setup (az login,
az account set, az bicep, ...) need neither.

Commands are parsed, not text-matched: heredoc bodies and quoted arguments
(commit messages) don't trigger it just by mentioning a bypass or a path.
It is a brake, not a sandbox: it can't see inside script files, and switching
branches brings that branch's files. GitHub is the wall for the checks
themselves: CI re-runs the hooks on every PR and the gate refuses weakened
checks. GitHub can hold an enforcement PR for the owner's review only when its
author isn't a code owner (Dependabot, or an agent with its own account).

Exit 2 blocks the tool call. Exit 0 with a JSON "ask" decision asks the owner.
Exit 0 with no output allows it. Any error blocks: the guard fails closed.
Claude Code and Copilot Chat both read exit 2 as a block. Copilot Chat reads
any other failing exit as a warning and runs the tool, so its registration
turns a guard that can't start into exit 2.
"""

import base64
import fnmatch
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import threading
from urllib.parse import quote, unquote

BLOCKED_ENV = re.compile(r"^(SKIP|PRE_COMMIT_ALLOW_NO_CONFIG|HUSKY|GIT_CONFIG_(PARAMETERS|COUNT|KEY_\d+|VALUE_\d+|GLOBAL|SYSTEM))$")
_NAMES = r"(SKIP|PRE_COMMIT_ALLOW_NO_CONFIG|HUSKY|GIT_CONFIG_\w+)"
# Every PowerShell/cmd form that sets an environment variable: $env:X = ...,
# Set-Item/New-Item/Set-Content on Env:X, [Environment]::SetEnvironmentVariable('X', ...),
# and setx / set X= in cmd.
POWERSHELL_ENV = re.compile(
    r"\$env:" + _NAMES + r"\s*="
    r"|\b(Set-Item|New-Item|Set-Content|Add-Content|si|ni|sc|ac)\b[^;|&\n]*\bEnv:[\\/]?" + _NAMES + r"\b"
    r"|SetEnvironmentVariable\s*\(\s*['\"]" + _NAMES + r"['\"]"
    r"|\bsetx\s+" + _NAMES + r"\b"
    r"|\bset\s+\"?" + _NAMES + r"=",
    re.IGNORECASE)
# bash builtins that set a variable from their arguments.
ASSIGNING_BUILTINS = {"export", "declare", "typeset", "readonly", "local"}
# Shell keywords in front of a command: `if grep ...; then ...` runs grep.
SHELL_KEYWORDS = {"if", "then", "else", "elif", "fi", "while", "until", "do", "done", "for", "!", "{", "}"}
GIT_DIR_PATH = re.compile(r"(^|[^A-Za-z0-9_.-])\.git([/\\]|$)")
# The only commands allowed to touch paths inside .git/: they only read.
# Anything else (sed -i, tee, cp, python, ...) is refused, as is any redirect.
READ_ONLY = {
    "ls", "cat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg", "stat", "file", "wc", "du",
    "find", "tree", "get-content", "gc", "get-childitem", "gci", "dir", "get-item", "test-path",
    "select-string", "type",
}
FIND_ACTIONS = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"}
# Programs whose arguments are code: any mention of a .git/ path counts. For
# other programs an argument with spaces is prose (a PR comment, a message),
# not a path, so mentioning .git/hooks in text isn't refused.
INTERPRETERS = {"python", "python3", "py", "node", "deno", "perl", "ruby", "php", "bash", "sh", "zsh", "dash",
                "pwsh", "powershell", "cmd", "osascript"}
# An output redirect: >out, 2>>log, {fd}>out, PowerShell's *>out, or <>f, which opens f to write too.
# Group 2 is its target when that's in the same word; otherwise the target is the next word.
REDIRECT = re.compile(r"^(\d*|&|\{\w+\}|\*)(?:>>?|<>)(.*)$", re.DOTALL)
# Any redirect, input too (<in, <<<text), and bare ones (>, 2>) whose target is the next word. Group 1 is the
# target when it's in the same word. A heredoc's << isn't one: its body is stripped before commands are read.
REDIRECT_WORD = re.compile(r"^(?:\d+|\{\w+\}|\*)?(?:>>?|<<<|<>|<(?!<))(.*)$", re.DOTALL)
# A redirect with & or | in it is read as a plain one, so the & or | doesn't end the command there:
# &>out and &>>out as >out and >>out, 2>&1 as 2>1, >&2 as >2, <&0 as <0, and >|out as >out.
AMP_BEFORE_REDIRECT = re.compile(r"(?<![&|])&(?=>)")
AMP_IN_REDIRECT = re.compile(r"(?<=[<>])&")
# 2>&1, >&2, <&0 and >&- join or close a stream: no file. They're read as /dev/fd/N, a path that's never an
# enforcement file, so a relative "1" can't land in a folder the guard takes to be protected. >&file writes file.
FD_DUP = re.compile(r"(?<=[<>])&(?=(?:\d+|-)(?![\w./\\-]))")
PIPE_IN_REDIRECT = re.compile(r"(?<=>)\|")
# A < or > written against the word before it: git log>out.
ATTACHED_REDIRECT = re.compile(r"(?<=[^\s;&|()<>])[<>]")
# A line ending in a backslash joins the next line (an escaped backslash, \\, doesn't); in PowerShell, a backtick.
LINE_CONTINUATION = re.compile(r"(?<!\\)((?:\\\\)*)\\\r?\n")
POWERSHELL_CONTINUATION = re.compile(r"(?<!`)((?:``)*)`\r?\n")
# What a substitution prints stands in the command as this: a value the guard never resolves (expand_vars).
# Braced, so text after it ($(printf .github/)CODEOWNERS) can't make it another variable's name.
SUBSTITUTED_NAME = "__SUBSTITUTED__"
SUBSTITUTED = "${" + SUBSTITUTED_NAME + "}"
# A case statement: its patterns end in ), so a $( ) that holds one can't be told where it ends.
CASE_STATEMENT = re.compile(r"(^|[\s;&|(])case\s+\S+\s+in(\s|$)")
# Commands that run another command given as a string: bash -c '...',
# pwsh -Command ..., cmd /c ..., eval ... The string is checked like a command.
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
POWERSHELLS = {"pwsh", "powershell"}
CODE_INTERPRETERS = INTERPRETERS - SHELLS - POWERSHELLS - {"cmd", "osascript"}
BYPASS_TEXT = re.compile(
    r"--no-verify|hookspath|\bSKIP\s*=|\bHUSKY\s*=|GIT_CONFIG_(PARAMETERS|COUNT|KEY)|pre-commit\s+uninstall"
    r"|\.git[/\\]+(hooks|config)|['\"]-n['\"]"
    # the same variables set for a child process: env={'SKIP': ...}, os.environ['SKIP'], process.env.SKIP, $ENV{SKIP}
    r"|['\"]" + _NAMES + r"['\"]|\benv\." + _NAMES + r"\b|\bENV\{['\"]?" + _NAMES, re.IGNORECASE)
MAX_NESTING = 5
# Groups: 3 = the rest of the line after the marker, 4 = the body.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1([^\n]*)\n(.*?)^\s*\2\s*$", re.DOTALL | re.MULTILINE)
SEPARATORS = {";", "&&", "||", "|", "&", "\n", "(", ")", "{", "}"}
WRAPPERS = {"env", "command", "exec", "time", "nohup", "sudo", "xargs"}
# A wrapper's options that take the next word as their value: in sudo -u root git push, root isn't the program.
WRAPPER_VALUE_OPTIONS = {
    "sudo": {"-u", "--user", "-g", "--group", "-C", "--close-from", "-D", "--chdir", "-h", "--host", "-p",
             "--prompt", "-R", "--chroot", "-r", "--role", "-t", "--type", "-T", "--command-timeout", "-U",
             "--other-user"},
    "env": {"-u", "--unset", "-C", "--chdir"},
    "time": {"-f", "--format", "-o", "--output"},
    "xargs": {"-a", "--arg-file", "-d", "--delimiter", "-E", "-I", "-L", "--max-lines", "-n", "--max-args", "-P",
              "--max-procs", "-s", "--max-chars"},
    "exec": {"-a"},
}
GIT_GLOBAL_WITH_VALUE = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
# An alias body that skips hooks, or a shell alias ("!...") that could run anything.
ALIAS_BYPASS = re.compile(r"^!|--no-verify|\bcommit\b.*(^|\s)-[A-Za-z]*n")
VERIFY_SUBCOMMANDS = {"commit", "merge", "push", "am", "rebase", "cherry-pick", "revert", "pull", "switch", "checkout"}
# git commit short options that take a value; in a cluster, the rest of the token is that value.
COMMIT_SHORT_WITH_VALUE = set("mFCctS") | {"u"}
COMMIT_LONG_WITH_VALUE = {
    "--message", "--file", "--author", "--date", "--template", "--reuse-message", "--reedit-message",
    "--fixup", "--squash", "--trailer", "--pathspec-from-file", "--cleanup", "--gpg-sign", "--untracked-files",
}

# --- What changes files ---
# Deleting or moving a folder that holds enforcement files changes them too.
DELETE_PROGRAMS = {"rm", "rmdir", "unlink", "shred", "remove-item", "ri", "del", "erase", "rd"}
MOVE_PROGRAMS = {"mv", "move-item", "mi", "move", "rename-item", "rni", "ren"}  # sources move away, to a destination
COPY_PROGRAMS = {"cp", "install", "ln", "copy-item", "cpi", "copy"}  # only the destination changes
DESTINATION_FLAGS = {"-t", "--target-directory", "-destination", "-dest"}
# Programs that change every path in their arguments (sed and perl only with -i).
WRITE_PROGRAMS = {"tee", "truncate", "touch", "dd", "chmod", "chown", "patch", "set-content", "sc", "add-content",
                  "ac", "out-file", "new-item", "ni", "clear-content", "clc"}
GIT_WRITE_SUBCOMMANDS = {"rm", "mv", "restore", "checkout"}
GIT_PATCH_SUBCOMMANDS = {"apply", "am"}
GIT_PATCH_CONTROL = {"--continue", "--abort", "--skip", "--quit", "--show-current-patch"}
PATCH_PATH = re.compile(r"^(?:diff --git a/(\S+) b/(\S+)|(?:\+\+\+|---) (?:[ab]/)?(\S+))", re.MULTILINE)
CHANGE_DIRECTORY = {"cd", "pushd", "chdir", "set-location", "sl", "push-location", "popd", "pop-location"}
# The option letters that give each interpreter code inline (python -c, node -e, ...).
INLINE_CODE_FLAGS = {"python": "c", "python3": "c", "py": "c", "node": "ep", "perl": "e", "ruby": "e", "php": "r"}
# .NET file calls in PowerShell: [IO.File]::WriteAllText(...), (Get-Item x).Delete()
# SetEnvironmentVariable writes no file (the variables that switch hooks off are blocked by POWERSHELL_ENV).
DOTNET_WRITE = re.compile(r"(::|\.)\s*(?!SetEnvironmentVariable\b)(Write|Append|Delete|Move|Copy|Replace|Create|Open|Set)"
                          r"\w*\s*\(", re.IGNORECASE)
# Code that writes, deletes or moves files, or runs commands, in the languages the guard sees inline.
CODE_WRITES = re.compile(
    r"open\s*\([^,)]*,\s*(mode\s*=\s*)?['\"][rbt]*[wax+>]"
    r"|\b(write|write_text|write_bytes|writeFile|writeFileSync|appendFile|appendFileSync|remove|removedirs|unlink"
    r"|unlinkSync|rename|renameSync|rmdir|rmdirSync|rm|rmSync|rmtree|move|copy2?|copyfile|copytree|copyFile"
    r"|copyFileSync|cp|cpSync|truncate|chmod|symlink|symlink_to|touch|system|popen|exec|execSync|spawn|spawnSync)\s*\("
    r"|\bos\.replace\b|\bsubprocess\b|\bchild_process\b|\bunlink\b|\bFile(Utils)?\.\w+|WriteAll\w*"
    r"|\b(Set-Content|Add-Content|Out-File|Remove-Item|Move-Item|Copy-Item|Rename-Item|New-Item)\b", re.IGNORECASE)
GLOB = re.compile(r"[*?\[]")
# Claude Code's and VS Code's settings files can switch hooks off, so they count as enforcement files too.
# (The workspace's .vscode/ is in CODEOWNERS; VS Code's user settings and workspace files can set chat.useHooks.)
LOCAL_SETTINGS = "/.claude/settings.local.json"
VSCODE_USER = [f"{home}/{app}/User" for home in ("$APPDATA", "~/Library/Application Support", "~/.config")
               for app in ("Code", "Code - Insiders")]
USER_SETTINGS = ("~/.claude/settings.json", "~/.claude/settings.local.json",
                 *(f"{user}/{profile}settings.json" for user in VSCODE_USER for profile in ("", "profiles/*/")))

# --- The repository's rules and settings on GitHub ---
# gh api writes that are everyday work, not settings: issues, pull requests and
# their reviews, labels, branches, and re-running or starting workflow runs.
# Any other write (settings, security features, environments, rulesets, ...) needs the owner.
GH_EVERYDAY_WRITES = re.compile(
    r"^/?repos/[^/]+/[^/]+/(issues|pulls|labels|git/refs"
    r"|actions/(runs|jobs)/\d+/(rerun|rerun-failed-jobs|cancel|force-cancel)|actions/workflows/[^/]+/dispatches)(/|$)")
GRAPHQL_EVERYDAY = {  # merging isn't here: it goes through the pull request check
    "addComment", "addPullRequestReview", "addPullRequestReviewThreadReply", "submitPullRequestReview",
    "resolveReviewThread", "unresolveReviewThread", "requestReviews", "markPullRequestReadyForReview",
    "convertPullRequestToDraft", "closePullRequest", "reopenPullRequest", "updatePullRequest",
    "updatePullRequestBranch", "disablePullRequestAutoMerge", "createIssue",
    "updateIssue", "closeIssue", "reopenIssue", "addLabelsToLabelable", "removeLabelsFromLabelable",
}
# gh pr merge / gh pr review options that take a value.
GH_PR_VALUE_FLAGS = {"-b", "--body", "-F", "--body-file", "-t", "--subject", "-A", "--author-email",
                     "--match-head-commit", "-R", "--repo"}
GH_SETTINGS_COMMANDS = {
    "repo": {"edit", "delete", "archive", "rename"}, "workflow": {"disable", "enable"},
    "secret": {"set", "delete", "remove"}, "variable": {"set", "delete"},
}
GH_BODY_FLAGS = {"-f", "-F", "--field", "--raw-field", "--input"}
GH_VALUE_FLAGS = {"-H", "--header", "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p", "--preview"}
# Connector tools: any operation not named as a read that targets an enforcement file,
# and any write-named operation on a repository's settings.
MCP_WRITE_VERB = re.compile(
    r"(^|_)(create|update|write|push|delete|remove|edit|patch|put|upload|move|rename|apply|set|add|enable|disable)(_|$)")
MCP_READ_VERB = re.compile(r"(^|_)(get|read|list|search|view|show|find|fetch|query|download|describe|diff|log|status)(_|$)")
MCP_SETTINGS = re.compile(r"repositor|ruleset|protection|environment|secret|variable|collaborator|webhook|permission",
                          re.IGNORECASE)
MCP_PATH_KEY = re.compile(r"^(path|file_?path|dir_?path|file_?name|target|destination|source|src|from|to"
                          r"|old_?path|new_?path)$", re.IGNORECASE)
# Dependabot's bumps, which the owner can let merge on green (dependabot_bump). The only change one
# may make to an enforcement file: an action's pin in a workflow, or a dependency's version in
# pyproject.toml, each removed line paired with an added line that moves the same action to another
# commit, or the same dependency to another version with the same operator.
DEPENDABOT = "dependabot[bot]"
WORKFLOW = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$")
PINNED_ACTION_LINE = re.compile(
    r"^[-+]\s*(-\s+)?uses:\s+(?P<name>[\w.-]+/[\w./-]+)@(?P<pin>[0-9a-f]{40})(\s+#\s*[\w.+-]+)?\s*$")
DEPENDENCY_LINE = re.compile(  # pin: the version itself; rest: other specifiers and markers, which must not change
    r'^[-+]\s*"(?P<name>[A-Za-z0-9][\w.-]*(\[[\w,.-]+\])?)\s*(?P<op>===|==|~=|!=|>=|<=|>|<)\s*'
    r'(?P<pin>[^\s",;]+)(?P<rest>[^"]*)",?\s*$')

# --- GitHub Copilot Chat in VS Code ---
# Its agent sends the same event fields as Claude Code, under its own tool names. Each is checked as the
# Claude Code tool that does the same; reads pass; any other tool is judged by what its input names.
# The names and their inputs are the ones Copilot Chat's open-source code declares
# (microsoft/vscode-copilot-chat: src/extension/tools/common/toolNames.ts, and package.json).
COPILOT_TERMINAL = {"run_in_terminal"}
COPILOT_EDITS = {"create_file", "edit_notebook_file", "replace_string_in_file", "multi_replace_string_in_file",
                 "insert_edit_into_file", "create_directory"}
COPILOT_PATCH = {"apply_patch"}
COPILOT_READS = {"read_file", "file_search", "grep_search", "list_dir", "semantic_search", "get_errors",
                 "get_changed_files", "get_terminal_output", "test_search", "fetch_webpage"}
# Run code the guard can't see: an editor command, which can do anything the editor can (type into a
# terminal, say), and an extension, which runs inside the editor from then on.
COPILOT_UNSEEN_CODE = {"run_vscode_command", "install_extension"}
# Adds a task to .vscode/tasks.json and runs it.
COPILOT_NEW_TASK = {"create_and_run_task"}
# The programs the hook registrations run. One planted where it's found first (a folder early on PATH, or the
# folder a hook runs in) would run instead of the guard, so writing one anywhere needs the owner.
HOOK_PROGRAMS = re.compile(r"(python3?|py|cmd|powershell|pwsh|bash|sh)(\.(exe|com|bat|cmd|ps1))?", re.IGNORECASE)
# A runner that kills a slow hook may let the tool call through (Copilot Chat reads the killed process as a
# warning), so the guard blocks on its own first, well inside the runners' 60-second budget.
WATCHDOG_SECONDS = 45
# --- Credentials and outbound data ---
# Where the owner's sign-ins live. An agent that reads them, or prints a token, could send them anywhere.
CREDENTIAL_DIRS = ("~/.azure", "~/.ssh", "~/.config/gh", "~/.aws")
CREDENTIAL_FILES = ("~/.docker/config.json",)
ENV_FILE = re.compile(r"\.env(\.[\w.-]+)?")  # .env and .env.local, but not the examples below
ENV_EXAMPLE = re.compile(r"\.env\.(example|sample|template)")
CREDENTIAL_TEXT = re.compile(r"\.(azure|ssh|aws)[/\\]|\.config[/\\]gh\b|\.docker[/\\]config\.json"
                             r"|(^|[\s'\"/\\=(,@])\.env(?![\w.-]*\.(example|sample|template)\b)(\.[\w-]+)*\b",
                             re.IGNORECASE)  # Windows paths ignore case: ~/.SSH is ~/.ssh
TOKEN_COMMANDS = {("gh", "auth", "token"), ("az", "account", "get-access-token")}
# Programs that send requests, and their options that send data or pick another method.
WEB_PROGRAMS = {"curl", "wget", "invoke-webrequest", "iwr", "invoke-restmethod", "irm"}
POWERSHELL_WEB = {"invoke-webrequest", "iwr", "invoke-restmethod", "irm"}
# Options (case-sensitive) that send data, read the request from a file, or send it somewhere other than the URL.
CURL_SENDS = re.compile(r"--(data(-\w+)?|form(-string)?|upload-file|json|config|resolve|connect-to|proxy|preproxy"
                        r"|socks\w*)")
CURL_SENDS_SHORT = set("dFTKx")
CURL_VALUE = {"-o", "-H", "-u", "-A", "-e", "-b", "-c", "-w", "-m", "-r", "-E", "-Y", "-y", "-z", "-U", "--output",
              "--header", "--user", "--user-agent", "--referer", "--cookie", "--cookie-jar", "--write-out",
              "--max-time", "--range", "--cert", "--connect-timeout", "--retry", "--retry-delay", "--limit-rate"}
WGET_SENDS = {"--post-data", "--post-file", "--body-data", "--body-file", "-i", "--input-file", "-e", "--execute"}
WGET_VALUE = {"-O", "-o", "-P", "-U", "-T", "-t", "--header", "--user", "--password", "--output-document",
              "--output-file", "--directory-prefix", "--user-agent", "--timeout", "--tries"}
POWERSHELL_WEB_VALUE = {"outfile", "headers", "useragent", "timeoutsec", "websession", "sessionvariable",
                        "contenttype", "credential", "maximumredirection", "certificatethumbprint", "transferencoding"}
REMOTE_PROGRAMS = {"scp", "sftp", "ssh", "nc", "ncat", "netcat", "socat", "telnet", "ftp"}
NETWORK_CODE = re.compile(r"\bimport\s+(urllib|requests|httpx|aiohttp|socket|http\.client)\b"
                          r"|\bfrom\s+(urllib|requests|httpx|aiohttp|socket|http)\b|\burlopen\s*\(|\bsocket\.\w+\s*\("
                          r"|\brequests\.(get|post|put|patch|delete|head|request|Session)\b|\bhttp\.request\s*\("
                          r"|\bNet\.(WebClient|Http|Sockets)|WebRequest\b|HttpClient\b|RestMethod\b|\bfetch\s*\("
                          r"|\b(require|import)\s*\(\s*['\"](node:)?(https?|http2|net|tls|dgram|axios|node-fetch|undici)"
                          r"['\"]|\bfrom\s+['\"](node:)?(https?|http2|net|tls|dgram|axios|node-fetch|undici)['\"]"
                          r"|\bDeno\.connect"  # Deno; then Ruby, Perl and PHP
                          r"|\brequire\s+['\"](net/https?|open-uri|socket|httparty|faraday|rest-client)['\"]"
                          r"|Net::HTTP\b|\bURI\.open\b|\b(TCP|UDP)Socket\b|LWP::|HTTP::Tiny\b|IO::Socket"  # perl -MLWP::…
                          r"|\buse\s+Socket\b|\b(curl_init|fsockopen|stream_socket_client)\s*\("
                          r"|\b(file_get_contents|fopen|readfile|file)\s*\(\s*['\"](https?|ftp)://")
# git settings that decide which server a push or fetch reaches: a remote's URL, a URL rewrite, and the
# remote a push goes to by default.
GIT_ROUTING = re.compile(r"^(remote\.[^.]+\.(push)?url|url\..+\.(push)?insteadof|remote\.pushdefault"
                         r"|branch\..+\.(push)?remote)$")
AZURE_HOSTS = re.compile(r"(^|\.)(azure\.com|windows\.net|azure\.net|graph\.microsoft\.com)$")
URL = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
NETWORK_RULE = (
    "Requests that send data, or go to a host that isn't on the allowlist (network.allowed_hosts in "
    ".claude/security-stack.json), need the owner. Agent: say what the request is for, and recommend either an "
    "allowlisted source or adding the host to the allowlist, which the owner approves."
)
CREDENTIAL_RULE = (
    "Agents never read the owner's sign-ins or print tokens: the tools use them without showing them. Agent: say "
    "what you need, and recommend a way that doesn't expose the secret, such as the command that uses it. The "
    "owner can run it themselves."
)
# Each of those tools also has an ID it's registered under, which is checked as its name.
COPILOT_IDS = {
    "copilot_applyPatch": "apply_patch", "copilot_createFile": "create_file",
    "copilot_replaceString": "replace_string_in_file", "copilot_multiReplaceString": "multi_replace_string_in_file",
    "copilot_insertEdit": "insert_edit_into_file", "copilot_editNotebook": "edit_notebook_file",
    "copilot_createDirectory": "create_directory", "copilot_runVscodeCommand": "run_vscode_command",
    "copilot_installExtension": "install_extension",
    "copilot_createAndRunTask": "create_and_run_task", "copilot_readFile": "read_file",
    "copilot_findFiles": "file_search", "copilot_findTextInFiles": "grep_search", "copilot_listDirectory": "list_dir",
    "copilot_searchCodebase": "semantic_search", "copilot_getErrors": "get_errors",
    "copilot_getChangedFiles": "get_changed_files", "copilot_findTestFiles": "test_search",
    "copilot_fetchWebPage": "fetch_webpage",
}
# The files an apply_patch names: "*** Update File: <path>" (also Add, Delete and Move to), or a unified diff.
PATCH_FILE_HEADER = re.compile(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): *(.+?)\s*$", re.MULTILINE)
# True when Copilot Chat runs the guard (.github/hooks/agent-guard.json passes --copilot, and its tool
# names show it too). Its auto-approve modes skip prompts, so an "ask" might never reach the owner, and
# the guard refuses instead.
COPILOT = False

# --- Azure ---
# az commands that only change this computer's CLI setup or sign-in: no tenant check, no approval.
# `az login --tenant <id>` is how the owner fixes a wrong tenant.
AZ_LOCAL_GROUPS = {"login", "logout", "version", "upgrade", "extension", "bicep", "config", "cloud", "find",
                   "feedback", "survey", "init", "interactive", "help", "self-test"}
AZ_LOCAL_ACCOUNT = {"show", "list", "set", "clear", "list-locations"}
# The last word of an az command that only reads: show, list-keys, get-access-token, what-if, ...
# download isn't one: it writes a local file.
AZ_READ_VERB = re.compile(r"^(show|list|get|exists|query|check|wait|what-if|validate|export|browse|tail)(-|$)")
# Options that may come before the command path: those that take a value, and plain flags.
# Any other option there makes the command unreadable, so it needs the owner.
AZ_VALUE_OPTIONS = {"--subscription", "--output", "-o", "--query", "--tenant"}
AZ_FLAGS = {"--debug", "--verbose", "--only-show-errors", "--version", "-h", "--help"}
# Code that names the az command: os.system('az group ...'), subprocess.run(['az', ...]).
AZ_IN_CODE = re.compile(r"(^|[^\w.-])az([\s'\",\]]|$)")
# Set when a command signs in or switches az's account: a later az command in the same
# command would run under an account the guard can't check beforehand.
AZ_SIGNED_IN_HERE = False

# Permission modes in which an "ask" reaches the owner. In any other mode
# (bypass permissions, dontAsk, ...) the guard refuses instead.
ASKING_MODES = {"default", "plan"}

GUIDANCE = (
    "Hooks are how this repo's checks run; skipping them is not allowed for agents. "
    "Fix what the failing hook reports and commit again. If a hook itself is wrong, change "
    ".pre-commit-config.yaml in a PR. CI re-runs the full chain on every PR regardless."
)
OWNER_RULE = (
    "Enforcement (the files listed in .github/CODEOWNERS, Claude Code's and VS Code's settings files, and the "
    "repository's rules and settings on GitHub) changes only with the owner's approval."
)
UNREADABLE = ("Agent: redo the call with its command or files named plainly; if it's refused again, tell the "
              "owner which call it was and recommend updating the guard for it.")
AZURE_RULE = (
    "Azure changes go through a pull request and the deploy job; a change made from the terminal "
    "skips that checkpoint, so it needs the owner's approval."
)

ROOT = CWD = ""
OWNED = None  # the CODEOWNERS patterns, or None when the file can't be read
EVENT = {}
PENDING = []  # why the owner's approval is needed; empty when it isn't
# What the shell knows while the command runs, so later paths resolve as the shell would.
SHELL_VARS = {}  # simple assignments made earlier in the command: p=x; rm "$p"
LOOP_VARS = {}  # for f in a b: f takes each word (None when the words can't be known)
OLDPWD = None  # the directory before the last cd, for cd -
DIR_STACK = []  # pushd / Push-Location


def save_shell():
    return CWD, dict(SHELL_VARS), dict(LOOP_VARS), OLDPWD, list(DIR_STACK)


def restore_shell(state):
    global CWD, SHELL_VARS, LOOP_VARS, OLDPWD, DIR_STACK
    CWD, SHELL_VARS, LOOP_VARS, OLDPWD, DIR_STACK = state


def block(reason):
    print(f"Blocked: {reason}. {GUIDANCE}", file=sys.stderr)
    sys.exit(2)


def refuse(message):
    print(message, file=sys.stderr)
    sys.exit(2)


# --- Enforcement files -------------------------------------------------------------

def _fold(text):
    return text.lower() if os.name == "nt" else text


def expand_vars(text):
    """Resolve $NAME, ${NAME} and ${NAME:-default} (also :=, :+ and the forms without the colon)
    from variables assigned earlier in the command, then the environment. Anything else is left as is."""
    def value(m):
        name = m.group(1) or m.group(4)
        if name == SUBSTITUTED_NAME:
            return m.group(0)  # what a substitution prints can't be known, whatever the command set that name to
        current = SHELL_VARS.get(name, os.environ.get(name))
        op, word = m.group(2), m.group(3) or ""
        if not op:
            return current if current is not None else m.group(0)
        unset = current is None or (op.startswith(":") and current == "")
        if op.endswith("+"):
            return "" if unset else word
        return word if unset else current
    return re.sub(r"\$\{(\w+)(?:(:?[-=+])([^}]*))?\}|\$(\w+)", value, text)


def to_abs(token):
    """An absolute path with forward slashes, resolved the way the shell would."""
    path = token.strip().strip("'\"")
    path = re.sub(r"\$env:(\w+)", lambda m: os.environ.get(m.group(1), m.group(0)), path, flags=re.IGNORECASE)
    path = re.sub(r"^\$(HOME\b|\{HOME\})", "~", expand_vars(path))
    path = os.path.expanduser(os.path.expandvars(path)).replace("\\", "/")
    drive = re.match(r"^/([a-zA-Z])(/.*|$)", path)
    if os.name == "nt" and drive:  # Git Bash style /c/Users/...
        path = drive.group(1) + ":" + (drive.group(2) or "/")
    if not os.path.isabs(path) and not re.match(r"^[A-Za-z]:/", path):
        path = os.path.join(CWD, path)
    return os.path.normpath(path).replace("\\", "/")


def load_codeowners():
    try:
        with open(os.path.join(ROOT, ".github", "CODEOWNERS"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except (OSError, ValueError):
        return None
    patterns = [line.split("#", 1)[0].split() for line in lines]
    return [p[0] for p in patterns if p] or None


def codeowners_match(pattern, rel):
    pattern, rel = _fold(pattern), _fold(rel)
    body = pattern.lstrip("/")
    parts = rel.split("/")
    anchored = pattern.startswith("/") or "/" in body.rstrip("/")
    candidates = [rel] if anchored else ["/".join(parts[i:]) for i in range(len(parts))]
    if body.endswith("/"):
        directory = body.rstrip("/")
        return any(c == directory or c.startswith(directory + "/") for c in candidates)
    return any(fnmatch.fnmatchcase(c, body) or c.startswith(body + "/") for c in candidates)


def is_enforcement_rel(rel, folders=False):
    """rel: a path relative to the repository root. It may be a glob; with
    folders=True, a folder that holds enforcement files counts too."""
    rel = posixpath.normpath("/" + _fold(rel.replace("\\", "/"))).lstrip("/")
    if OWNED is None:
        return True  # CODEOWNERS unreadable: can't tell, so every change needs the owner
    for pattern in OWNED + [LOCAL_SETTINGS]:
        base = _fold(pattern).strip("/")
        if codeowners_match(pattern, rel):
            return True
        if GLOB.search(rel) and fnmatch.fnmatchcase(base, rel):
            return True  # a glob that matches an enforcement file or folder
        if folders and (not rel or base.startswith(rel + "/")):
            return True
    return False


def is_enforcement_path(token, folders=False):
    """token: a path as the agent wrote it."""
    if not isinstance(token, str) or not token.strip():
        return False
    loop = next((v for v in re.findall(r"\$\{?(\w+)\}?", token) if v in LOOP_VARS), None)
    if loop:  # for f in a b; do rm "$f": check each word the variable takes
        pattern = r"\$\{?" + re.escape(loop) + r"\}?"
        return any(is_enforcement_path(re.sub(pattern, lambda m: word, token), folders)
                   for word in LOOP_VARS[loop] or ["$(unknown)"])
    expanded = expand_vars(token)
    unresolved = re.search(r"\$[\w({]", expanded)
    if unresolved:
        # A variable or command the guard can't resolve: judge where it could point,
        # by the part before it (".claude/$x" could be an enforcement file; "/tmp/$x" can't).
        return is_enforcement_path(expanded[:unresolved.start()] + "*", folders)
    path = _fold(to_abs(token))
    real = _fold(os.path.realpath(path).replace("\\", "/"))
    if real != path and is_enforcement_path(real, folders):
        return True  # a link to an enforcement file
    for settings in USER_SETTINGS:
        target = _fold(to_abs(settings))  # VS Code profiles' settings are a pattern: profiles/*/settings.json
        if fnmatch.fnmatchcase(path, target) or (folders and (target.startswith(path.rstrip("/") + "/")
                                                            or fnmatch.fnmatchcase(path, posixpath.dirname(target)))):
            return True
    if path.endswith(".code-workspace"):
        return True  # a VS Code workspace file, wherever it is: its settings apply to the workspace it opens
    root = _fold(to_abs(ROOT))
    if path == root or root.startswith(path.rstrip("/") + "/"):
        return folders  # the repository itself, or a folder above it
    if not path.startswith(root + "/"):
        return False
    return is_enforcement_rel(path[len(root) + 1:], folders)


def in_repository(path):
    here, root = _fold(to_abs(path)), _fold(to_abs(ROOT))
    return here == root or here.startswith(root + "/")


def shown(token):
    path, root = to_abs(token), to_abs(ROOT)
    return path[len(root) + 1:] if _fold(path).startswith(_fold(root) + "/") else path


def mentions_enforcement(text):
    """The first path-like word in code that names an enforcement file, or None."""
    return next((w for w in re.findall(r"[\w.$~/\\:-]+", text) if is_enforcement_path(w)), None)


def code_touches_enforcement(code):
    """For code that writes files or runs commands: the enforcement path it names, also when
    the code builds it at run time ('.claude/' + 'settings.json', os.path.join('tests', 'gate')).
    Only the owned parts of a folder count: tests/gate does, tests/unit doesn't. None if it names none."""
    hit = mentions_enforcement(code)
    if hit:
        return shown(hit)
    folded = _fold(code)
    for pattern in (OWNED or []) + [LOCAL_SETTINGS]:
        parts = [re.escape(p) for p in _fold(pattern).strip("/").split("/") if p]
        # The path's parts in order, joined by up to 8 non-word characters: / \ ' " + , and spaces.
        if parts and re.search(r"(^|[^\w.-])" + r"\W{1,8}".join(parts) + r"([^\w-]|$)", folded):
            return pattern.strip("/")
    return None


def owner_needed(reason, rule=OWNER_RULE):
    PENDING.append((reason, rule))


# --- Credentials and outbound data ---------------------------------------------------

def is_credential_path(token):
    """Whether a path is one of the owner's sign-ins: under ~/.azure, ~/.ssh, ~/.config/gh or ~/.aws,
    ~/.docker/config.json, or a .env file that isn't an example."""
    if not isinstance(token, str) or not token.strip():
        return False
    if not re.search(r"\s", token.strip()) and CREDENTIAL_TEXT.search(token.strip("'\"")):
        return True  # a path-like word naming one, also inside code: ReadAllText("$HOME/.ssh/id_rsa")
    path = _fold(to_abs(token))
    if any(path == root or path.startswith(root + "/") for root in (_fold(to_abs(d)) for d in CREDENTIAL_DIRS)):
        return True
    if any(path == _fold(to_abs(f)) for f in CREDENTIAL_FILES):
        return True
    name = posixpath.basename(path)
    return bool(ENV_FILE.fullmatch(name)) and not ENV_EXAMPLE.fullmatch(name)


def could_match_env(pattern):
    """Whether a search glob (or no glob: every file) could take in a .env file."""
    if not isinstance(pattern, str) or not pattern.strip():
        return True
    glob = pattern.strip().replace("\\", "/").lstrip("/")
    return any(fnmatch.fnmatch(sample, glob) or fnmatch.fnmatch(sample, "*/" + glob)
               for sample in (".env", "app/.env", ".env.local", "app/.env.production"))


def refuse_credentials(reason):
    refuse(f"Blocked: {reason}. {CREDENTIAL_RULE}")


def check_credentials(program, tokens, name):
    """The owner's sign-ins are never read or copied, and tokens are never printed. Writing a .env file is
    allowed (cp .env.example .env): it doesn't expose one."""
    args = [t.lower() for t in tokens[1:]]
    if name == "gh" and "auth" in args:
        after = args[args.index("auth") + 1:]
        if after[:1] == ["token"] or (after[:1] == ["status"] and ("--show-token" in after or "-t" in after)):
            refuse_credentials("gh would print a GitHub token")
    if name == "az" and az_path(tokens[1:])[0][:2] == ["account", "get-access-token"]:
        refuse_credentials("az account get-access-token prints an Azure access token")
    if name == "aws" and (("configure" in args and ("export-credentials" in args or ("get" in args and any(
            key in a for a in args for key in ("aws_access_key_id", "aws_secret_access_key", "aws_session_token")))))
            or ("sts" in args and "get-session-token" in args)):
        refuse_credentials("aws would print AWS credentials")
    # A move's sources go too, so only a real write, not a move, may name a .env file (cp .env.example .env).
    writes = {t for t, _ in written_paths(name, tokens)} if name not in MOVE_PROGRAMS else set()
    for tok in tokens[1:]:
        value = tok[1:] if tok.startswith("<") and not tok.startswith("<<") else tok
        value = value.split("=", 1)[1] if value.startswith("-") and "=" in value else value
        at = re.match(r"^(?:-[A-Za-z]|[^@=\s]*=)?@(.+)$", value)  # a file read into the request: curl -H @f, -d@f
        value = at.group(1) if at else value
        if not value or value.startswith("-") or not is_credential_path(value):
            continue
        base = posixpath.basename(value.replace("\\", "/"))
        if value in writes and ENV_FILE.fullmatch(base) and not CREDENTIAL_TEXT.search(value.replace(base, "")):
            continue
        refuse_credentials(f"{program} would read or copy {value}, one of the owner's sign-ins")


def allowed_hosts():
    hosts = stack_setting("network", "allowed_hosts")
    return {str(h).lower().rstrip(".") for h in hosts} if isinstance(hosts, list) else set()


def url_host(url):
    """The host a URL names, or None when it has none the guard can read."""
    found = re.match(r"^[a-z][a-z0-9+.-]*://([^/?#]*)", expand_vars(url.strip("'\"")), re.IGNORECASE)
    if not found or "$" in found.group(1):
        return None
    host = re.sub(r":\d+$", "", found.group(1).rsplit("@", 1)[-1]).strip("[]").lower().rstrip(".")
    return host or None


def check_host(what, host):
    """A request to a host that isn't on the allowlist, or that the guard can't read, needs the owner."""
    if host not in allowed_hosts():
        where = f"{host}, which isn't on the allowlist" if host else "an address the guard can't read"
        owner_needed(f"{what} to {where}", NETWORK_RULE)


def web_request_parts(tokens, name):
    """(sends, method, urls) of a curl, wget or PowerShell web request: whether it sends data, reads its request
    from a file or sends it elsewhere than its URL (the option, or None), the method it names, and its URLs."""
    args, urls, method, i = tokens[1:], [], None, 0

    def value(inline):
        """An option's value: given inline (--x=v, -X:v), or the next argument, which is then consumed."""
        nonlocal i
        if inline is not None:
            return inline
        i += 1
        return args[i - 1] if i - 1 < len(args) else ""

    while i < len(args):
        tok, i = args[i], i + 1
        if not tok.startswith("-") or tok == "-":
            # 2>/dev/null, >out.json and > out.json say where output goes, not where the request goes. A quoted '>'
            # never reaches here as a word of its own (detach_redirects makes it ' >'), so it can't hide a URL.
            redirect = REDIRECT_WORD.match(tok)
            if not redirect:
                urls.append(tok)
            elif not redirect.group(1):
                i += 1  # a bare > takes the next word as its target
            continue
        if name in POWERSHELL_WEB:  # parameters: case-insensitive, may be shortened, -Name:value or -Name value
            found = re.match(r"^-(\w+)(?:[:=](.*))?$", tok)
            param, inline = (found.group(1).lower(), found.group(2)) if found else ("", None)
            if param and any(p.startswith(param) for p in ("body", "infile", "form")):
                return tok, method, urls
            if param in ("uri", "ur"):
                urls.append(value(inline))
            elif len(param) >= 2 and "method".startswith(param):
                method = value(inline)
            elif param in POWERSHELL_WEB_VALUE:
                value(inline)
            continue
        flag, eq, inline = tok.partition("=")
        inline = inline if eq else None
        if name == "curl":
            if flag.startswith("-X") and len(flag) > 2:
                method = flag[2:]
            elif flag in ("-X", "--request"):
                method = value(inline)
            elif CURL_SENDS.fullmatch(flag) or (not flag.startswith("--") and CURL_SENDS_SHORT & set(flag[1:])):
                return tok, method, urls
            elif re.match(r"^-[A-Za-z]@", flag):
                return tok, method, urls  # -H@file: reads a file into the request
            elif flag in CURL_VALUE:
                given = value(inline)
                if given.startswith("@") or (flag in ("-b", "--cookie") and given and "=" not in given):
                    return tok, method, urls  # @file, or a cookie file: reads a file into the request
            elif flag == "--url":
                urls.append(value(inline))
        elif flag in WGET_SENDS:
            return tok, method, urls
        elif flag == "--method":
            method = value(inline)
        elif flag in WGET_VALUE:
            value(inline)
    return None, method, urls


def check_web_request(program, tokens, name):
    """curl, wget, Invoke-WebRequest and Invoke-RestMethod: sending data, another method than GET, or a request
    sent elsewhere than its URL needs the owner whatever the host; any request to a host off the allowlist, or
    one the guard can't read, needs the owner too."""
    sends, method, urls = web_request_parts(tokens, name)
    if sends:
        owner_needed(f"{program} {sends.split('=', 1)[0]} sends data, reads its request from a file, or sends it "
                     "somewhere other than its URL", NETWORK_RULE)
        return
    if method is not None and expand_vars(method).strip("'\"").upper() not in ("GET", "HEAD"):
        owner_needed(f"{program} sends a {expand_vars(method).strip(chr(39) + chr(34)).upper() or 'non-GET'} "
                     "request", NETWORK_RULE)
        return
    if not urls:
        owner_needed(f"a {program} request to an address the guard can't read", NETWORK_RULE)
    for url in urls:
        text = expand_vars(url).strip("'\"")
        bare = re.fullmatch(r"([\w-]+\.)+[a-z]{2,}(:\d+)?(/\S*)?", text, re.IGNORECASE)
        check_host(f"a {program} request",
                   url_host(url) or (re.sub(r"[:/].*", "", text).lower() if bare else None))


def check_outbound(program, tokens, name, tool):
    """Other ways to send data out of this computer."""
    if name in WEB_PROGRAMS:
        check_web_request(program, tokens, name)
    elif name in REMOTE_PROGRAMS:
        owner_needed(f"{program} connects to another computer", NETWORK_RULE)
    elif name == "rsync" and any(re.match(r"^(\[[^\]]+\]:|[^/\\:\s]+:|rsync://)", t)  # host:path, [v6]:path
                                 for t in tokens[1:] if not t.startswith("-")):
        owner_needed("rsync to another computer", NETWORK_RULE)
    elif name == "gh":
        words = [t for t in tokens[1:] if not t.startswith("-")]
        if words[:1] == ["gist"] and words[1:2] in (["create"], ["edit"]):
            owner_needed(f"gh gist {words[1]} publishes content outside this repository", NETWORK_RULE)
    code = " ".join(tokens[1:])
    if NETWORK_CODE.search(code) and (name in CODE_INTERPRETERS or tool == "PowerShell"):
        owner_needed(f"{program} code that opens network connections", NETWORK_RULE)


def decide_owner():
    """Ask the owner about the first change that needs them, or refuse when the session can't ask."""
    if not PENDING:
        return
    reason, rule = PENDING[0]
    stop = ("Agent: stop, tell the owner what you need and why, and recommend a way forward; don't look for "
            "another way.")
    if COPILOT:
        refuse(f"Blocked: {reason}. {rule} Copilot Chat's auto-approve modes skip prompts, so there the guard "
               f"refuses instead of asking. {stop} Owner: do it in Claude Code (default mode), or yourself.")
    mode = EVENT.get("permission_mode")
    if mode and mode not in ASKING_MODES:
        refuse(f"Blocked: {reason}. {rule} This session's permission mode ({mode}) can't ask the owner, "
               f"so it's refused. {stop} Owner: switch to default mode (Shift+Tab) and approve the prompt, "
               "or do it yourself.")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": f"Owner approval needed: {reason}. {rule}",
    }}))
    sys.exit(0)


def copy_destination(tokens):
    """(destination, sources) of a copy or move: -t DIR, --target-directory=DIR,
    PowerShell's -Destination, or else the last argument."""
    destination, skip, plain = None, False, []
    for i, tok in enumerate(tokens[1:], start=1):
        if skip:
            skip = False
            continue
        flag, _, value = tok.partition("=")
        flag = flag.lower()
        if flag in ("-t", "--target-directory") or (len(flag) >= 4 and "-destination".startswith(flag)):
            destination = value or (tokens[i + 1] if i + 1 < len(tokens) else None)
            skip = not value
        elif not tok.startswith("-"):
            plain.append(tok)
    if destination is None:
        return (plain[-1] if plain else None), plain[:-1]
    return destination, plain


def landing_paths(destination, sources):
    """Where copied or moved files land: inside the destination when it is a folder."""
    if sources and (destination.endswith(("/", "\\")) or os.path.isdir(to_abs(destination))):
        return [os.path.join(destination, os.path.basename(s.rstrip("/\\"))) for s in sources]
    return [destination]


def written_paths(name, tokens):
    """(path, folders) for each path a command changes: redirect targets, and the
    arguments of programs that write, copy, move or delete files."""
    out = []
    for i, tok in enumerate(tokens):
        m = REDIRECT.match(tok)
        if m:
            target = m.group(2) or (tokens[i + 1] if i + 1 < len(tokens) else "")
            # PowerShell's $null discards output, and in bash an unset $null stops the command, so neither
            # writes a file; a $null the command set (null=path) is resolved and checked like any path.
            if target and not target.startswith("&") and expand_vars(target).lower() != "$null":
                out.append((target, False))
    plain = [t for t in tokens[1:] if not t.startswith("-")]
    in_place = name in ("sed", "perl") and any(
        t.startswith("--in-place") or re.match(r"^-[a-zA-Z]*i", t) for t in tokens[1:])
    if name in DELETE_PROGRAMS:
        out += [(t, True) for t in plain]
    elif name == "find" and FIND_ACTIONS & set(tokens):
        # -delete or -exec can change anything under the folders searched
        starts = next((tokens[1:i] for i, t in enumerate(tokens) if i and t.startswith(("-", "(", "!"))), tokens[1:])
        out += [(t, True) for t in starts or ["."]]
    elif name in MOVE_PROGRAMS or name in COPY_PROGRAMS:
        destination, sources = copy_destination(tokens)
        if name in MOVE_PROGRAMS:
            out += [(s, True) for s in sources]  # a moved folder takes its files with it
        if name == "ln":
            out += [(s, False) for s in sources]  # a link to an enforcement file is a way to write it
        if destination:
            out += [(p, False) for p in landing_paths(destination, sources)]
    elif name in WRITE_PROGRAMS or in_place:
        for tok in tokens[1:]:
            if tok.startswith("-") and "=" not in tok:
                continue
            out.append((tok, False))
            if "=" in tok:  # dd of=path, --output=path
                out.append((tok.split("=", 1)[1], False))
    return out


def has_inline_code(tokens, flags):
    """Whether an interpreter runs code given inline (python -c ...), not a script file."""
    for tok in tokens[1:]:
        if tok.split("=", 1)[0] in ("--eval", "--print"):
            return True
        if tok.startswith("--"):
            continue
        if tok.startswith("-") and len(tok) > 1:
            if any(ch in flags for ch in tok[1:]):
                return True
            continue
        return False  # a script file: running it isn't changing it
    return False


def patch_program_files(tokens):
    """The patch files `patch` reads: -i FILE, its second file argument, or a '<' redirect."""
    files, plain, skip = [], [], False
    for i, tok in enumerate(tokens[1:], start=1):
        if skip:
            skip = False
        elif tok in ("-i", "--input"):
            files += tokens[i + 1:i + 2]
            skip = True
        elif tok.startswith("--input="):
            files.append(tok.split("=", 1)[1])
        elif not tok.startswith(("-", "<")):
            plain.append(tok)
    return files + plain[1:2] + redirect_inputs(tokens)


def is_hook_program(path):
    """A file named like a program the hooks run (python, cmd, a shell), wherever it is: one found before the
    real one, early on PATH or in the folder a hook runs in, would run instead of the guard."""
    return isinstance(path, str) and bool(HOOK_PROGRAMS.fullmatch(posixpath.basename(to_abs(path))))


def check_writes(program, tokens, inputs=()):
    name = program[:-4] if program.endswith(".exe") else program
    for path, folders in written_paths(name, tokens):
        if name not in DELETE_PROGRAMS and is_hook_program(path):
            owner_needed(f"{program} would write {shown(path)}, named like a program the hooks run")
            return
        if is_enforcement_path(path, folders):
            owner_needed(f"{program} would change {shown(path)}")
            return
    if name == "patch":
        targets = patch_targets([to_abs(f) for f in patch_program_files(tokens) + list(inputs)])
        hit = next((t for t in targets or [] if is_enforcement_path(t)), None)
        if targets is None or hit:
            owner_needed(f"patch would change {shown(hit)}" if hit else "patch reads a patch that can't be checked")
            return
    flags = INLINE_CODE_FLAGS.get(name)
    code = " ".join(tokens[1:])
    if flags and has_inline_code(tokens, flags) and CODE_WRITES.search(code):
        hit = code_touches_enforcement(code)
        if hit:
            owner_needed(f"{program} code that can change {hit}")


def gh_command():
    """How to run gh. Tests point GUARD_GH (a JSON list) at a stand-in."""
    return json.loads(os.environ["GUARD_GH"]) if os.environ.get("GUARD_GH") else ["gh"]


def pr_files(selector=None, repo=None, number=None):
    """The files a pull request changes, or None when they can't all be listed. With repo and number,
    a renamed file's old name counts too: renaming an enforcement file away changes it. gh pr view
    lists new names only."""
    if repo and number:
        args = ["api", f"repos/{repo}/pulls/{number}/files", "--paginate", "--jq",
                ".[] | .filename, (.previous_filename // empty)"]
    else:
        args = ["pr", "view", *([selector] if selector else []), "--json", "files", "--jq", ".files[].path",
                *(["--repo", repo] if repo else [])]
    try:  # gh writes UTF-8; the platform's default encoding (cp1252 on Windows) can't read all of it
        result = subprocess.run(gh_command() + args, capture_output=True, encoding="utf-8", errors="replace",
                                timeout=30, cwd=CWD if os.path.isdir(CWD) else None)
    except (OSError, subprocess.SubprocessError):
        return None
    files = (result.stdout or "").splitlines()
    if result.returncode != 0 or (not (repo and number) and len(files) >= 100):
        return None  # gh pr view lists at most 100 files
    return files


def gh_json(*args):
    """What a gh command prints, parsed as JSON; None if it fails or prints anything else."""
    try:  # UTF-8, as gh writes it: Dependabot's descriptions carry emoji
        result = subprocess.run(gh_command() + list(args), capture_output=True, encoding="utf-8", errors="replace",
                                timeout=30, cwd=CWD if os.path.isdir(CWD) else None)
        return json.loads(result.stdout) if result.returncode == 0 and result.stdout else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def stack_setting(section, key):
    """A value recorded in .claude/security-stack.json, or None when it isn't there or can't be read."""
    try:
        with open(os.path.join(ROOT, ".claude", "security-stack.json"), encoding="utf-8") as fh:
            return (json.load(fh).get(section) or {}).get(key)
    except (OSError, ValueError, AttributeError):
        return None


def pr_ref(selector=None, repo=None):
    """(owner/repo, number) of the pull request a gh pr command names, or None if gh can't say."""
    if repo and selector and selector.isdigit():
        return repo, selector
    view = gh_json("pr", "view", *([selector] if selector else []), "--json", "url", *(["--repo", repo] if repo else []))
    found = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)", str(view.get("url")) if isinstance(view, dict) else "")
    return (found.group(1), found.group(2)) if found else None


def bumps(rule, removed, added):
    """Whether an added line moves the removed line's action to another commit, or its dependency to
    another version with the same operator and nothing else changed."""
    before, after = rule.match(removed), rule.match(added)
    same = ("op", "rest")
    return bool(before and after) and before["name"].lower() == after["name"].lower() \
        and all(before.groupdict().get(key) == after.groupdict().get(key) for key in same) \
        and before["pin"] != after["pin"]


def dependabot_bump(ref):
    """Whether the owner lets Dependabot's bumps merge on green (github.dependabot_merges_on_green in
    .claude/security-stack.json; off in the baseline) and the pull request ref() names is one: in this
    repository (github.repository there), Dependabot opened it; only Dependabot has pushed to its branch, by
    GitHub's record of the branch's pushes from its creation to the pull request's head (commit authors can
    be written by anyone who can push; that record can't); and every change to an enforcement file moves an
    action's pin in a workflow, or a dependency's version in pyproject.toml, to another pin or version of the
    same action or dependency. Anything else, or anything that can't be confirmed, is False."""
    if stack_setting("github", "dependabot_merges_on_green") is not True:
        return False
    found, home = ref() if ref else None, str(stack_setting("github", "repository") or "")
    if not found or not home or found[0].lower() != home.lower() or not str(found[1]).isdigit():
        return False
    repo, number = found
    pr = gh_json("api", f"repos/{repo}/pulls/{number}")
    head = (pr.get("head") or {}) if isinstance(pr, dict) else {}
    if not head or (pr.get("user") or {}).get("login") != DEPENDABOT or not head.get("ref") or not head.get("sha") \
            or (head.get("repo") or {}).get("full_name") != repo:
        return False
    branch = quote(f"refs/heads/{head['ref']}", safe="/")
    pushes = gh_json("api", f"repos/{repo}/activity?ref={branch}&per_page=100")
    if not isinstance(pushes, list) or not 0 < len(pushes) < 100 \
            or any((p.get("actor") or {}).get("login") != DEPENDABOT for p in pushes) \
            or not any(p.get("activity_type") == "branch_creation" for p in pushes) \
            or not any(p.get("after") == head["sha"] for p in pushes):
        return False
    files = gh_json("api", f"repos/{repo}/pulls/{number}/files?per_page=100")
    if not isinstance(files, list) or not 0 < len(files) < 100:
        return False
    for changed in files:
        name, before = str(changed.get("filename") or ""), str(changed.get("previous_filename") or "")
        if not is_enforcement_rel(name) and not (before and is_enforcement_rel(before)):
            continue
        rule = PINNED_ACTION_LINE if WORKFLOW.match(name) else DEPENDENCY_LINE if name == "pyproject.toml" else None
        patch = str(changed.get("patch") or "").splitlines()
        removed = [line for line in patch if line.startswith("-")]
        added = [line for line in patch if line.startswith("+")]
        if changed.get("status") != "modified" or rule is None or not removed or len(removed) != len(added) \
                or not all(bumps(rule, old, new) for old, new in zip(removed, added)):
            return False
    return True


def check_pr_change(action, what, files, ref=None):
    """Merging or approving a pull request that changes enforcement files is changing them, unless it's a
    Dependabot bump the owner lets merge on green. ref: a function that names the pull request as
    (owner/repo, number); it's called only for that check."""
    hit = next((f for f in files or [] if is_enforcement_rel(f)), None)
    if files is None:
        owner_needed(f"{action} {what}, whose changed files can't be listed")
    elif hit and not dependabot_bump(ref):
        owner_needed(f"{action} {what}, which changes {hit}")


def flag_on(args, *names):
    """Whether a boolean flag is set: --approve and --approve=true count, --approve=false doesn't."""
    on = False
    for tok in args:
        flag, eq, value = tok.partition("=")
        if flag in names:
            on = not eq or value.lower() not in ("false", "0")
    return on


def check_gh_pr(sub, args, repo=None):
    """gh pr merge, and gh pr review --approve."""
    if (sub == "review" and not flag_on(args, "--approve", "-a")) or (sub == "merge" and flag_on(args, "--disable-auto")):
        return  # a comment, a change request or turning auto-merge off changes nothing
    selector, skip = None, False
    for i, tok in enumerate(args):
        if skip:
            skip = False
            continue
        flag, _, value = tok.partition("=")
        if flag in GH_PR_VALUE_FLAGS:
            if flag in ("-R", "--repo"):
                repo = value or (args[i + 1] if i + 1 < len(args) else None)
            skip = not value
        elif not tok.startswith("-") and selector is None:
            selector = tok
    ref = pr_ref(selector, repo)  # listing by number also names renamed files' old paths
    check_pr_change("merging" if sub == "merge" else "approving", f"pull request {selector or 'for this branch'}",
                    pr_files(repo=ref[0], number=ref[1]) if ref else pr_files(selector, repo), lambda: ref)


def check_gh(tokens):
    """gh commands that change the repository's rules or settings, or its enforcement files."""
    i, repo = 1, None
    while i < len(tokens) and tokens[i].startswith("-"):  # options before the subcommand: gh --repo o/r pr merge
        flag, _, value = tokens[i].partition("=")
        if flag in ("-R", "--repo", "--hostname") and not value:
            value = tokens[i + 1] if i + 1 < len(tokens) else None
            i += 1
        if flag in ("-R", "--repo"):
            repo = value
        i += 1
    words = tokens[i:]
    if len(words) > 1 and words[1] in GH_SETTINGS_COMMANDS.get(words[0], ()):
        owner_needed(f"gh {words[0]} {words[1]} changes the repository's settings")
        return
    if words[:1] == ["pr"] and words[1:2] in (["merge"], ["review"]):
        check_gh_pr(words[1], words[2:], repo)
        return
    if words[:1] != ["api"]:
        return
    args, method, endpoint, has_body, skip = words[1:], None, None, False, False
    for i, tok in enumerate(args):
        if skip:
            skip = False
            continue
        flag, _, value = tok.partition("=")
        if tok.startswith("-X") and len(tok) > 2:
            method = tok[2:].lstrip("=")
        elif flag in ("-X", "--method"):
            method = value or (args[i + 1] if i + 1 < len(args) else "")
            skip = not value
        elif flag in GH_BODY_FLAGS or re.match(r"^-[fF].", tok):
            has_body, skip = True, flag in GH_BODY_FLAGS and not value
        elif flag in GH_VALUE_FLAGS:
            skip = not value
        elif not tok.startswith("-") and endpoint is None:
            endpoint = tok
    method = expand_vars(method or ("POST" if has_body else "GET")).upper()
    if method in ("GET", "HEAD") or not endpoint:
        return
    endpoint = expand_vars(endpoint).split("?", 1)[0]
    text = expand_vars(" ".join(args))
    if "$" in endpoint:
        owner_needed("a gh api write to an endpoint the guard can't resolve")
        return
    if endpoint.strip("/") == "graphql":
        if "--input" in args or any(t.startswith("--input=") for t in args) or re.search(r"=@|query=\$", text):
            owner_needed("a GraphQL request whose body is read from a file or command")
        elif re.search(r"\bmutation\b", text):
            unknown = set(re.findall(r"\b(\w+)\s*\(\s*input\s*:", text)) - GRAPHQL_EVERYDAY
            if re.search(r"\bAPPROVE\b", text):
                owner_needed("an approval through GraphQL, which can't be matched to its pull request's files")
            elif unknown or not re.search(r"\(\s*input\s*:", text):
                owner_needed(f"a GraphQL mutation that isn't everyday work ({', '.join(sorted(unknown)) or 'unrecognised'})")
        return
    action = re.match(r"^/?repos/([^/]+/[^/]+)/pulls/(\d+)/(merge|reviews(/\d+/events)?)$", endpoint)
    body_unseen = "--input" in args or any(t.startswith("--input=") for t in args) or "=@" in text
    if action and (action.group(3) == "merge" or body_unseen or re.search(r"\bevent=APPROVE\b", text, re.IGNORECASE)):
        check_pr_change("merging" if action.group(3) == "merge" else "approving", f"pull request #{action.group(2)}",
                        pr_files(repo=action.group(1), number=action.group(2)), lambda: action.group(1, 2))
        return
    contents = re.search(r"^/?repos/[^/]+/[^/]+/contents/(.+)$", endpoint)
    if contents:
        if is_enforcement_rel(unquote(contents.group(1))):
            owner_needed(f"a GitHub API write to {unquote(contents.group(1))}")
        return
    if not GH_EVERYDAY_WRITES.search(endpoint):
        owner_needed(f"gh api {method} {endpoint} can change the repository's rules or settings")


def mcp_paths(value):
    """Path-like values in a connector tool's input: keys such as path or file_path, at any depth."""
    out, pending = [], [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if isinstance(child, str) and MCP_PATH_KEY.match(str(key)):
                    out.append(child)
                elif isinstance(child, (dict, list)):
                    pending.append(child)
        elif isinstance(item, list):
            pending.extend(item)
    return out


def tool_operation(name):
    """A tool's name in snake_case: writeFile -> write_file."""
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).replace("-", "_").lower()


def named_as_read(name):
    operation = tool_operation(name)
    return bool(MCP_READ_VERB.search(operation)) and not MCP_WRITE_VERB.search(operation)


def check_mcp(tool, tool_input):
    name = tool.rsplit("__", 1)[-1]
    operation = tool_operation(name)
    if named_as_read(name):
        return
    approving = str(tool_input.get("event", "")).upper() == "APPROVE"
    if "pull" in operation and (re.search(r"(^|_)merge(_|$)", operation) or approving):
        owner, repo = tool_input.get("owner"), tool_input.get("repo")
        number = tool_input.get("pullNumber") or tool_input.get("pull_number") or tool_input.get("number")
        files = pr_files(repo=f"{owner}/{repo}", number=number) if owner and repo and number else None
        check_pr_change("approving" if approving else "merging", f"pull request #{number}", files,
                        lambda: (f"{owner}/{repo}", str(number)))
        return
    if MCP_SETTINGS.search(operation):
        owner_needed(f"the connector tool {name} can change a repository or its settings")
        return
    for path in mcp_paths(tool_input):
        local = os.path.isabs(path) or re.match(r"^[A-Za-z]:[/\\]", path)
        if path and (is_enforcement_path(path) if local else is_enforcement_rel(path)):
            owner_needed(f"a connector write to {path}")
            return


def check_file_edit(path):
    if re.search(r"(^|[/\\])\.git([/\\]|$)", path or ""):
        block("editing files inside .git/ can disable hooks or change git config")
    if is_credential_path(path) and not ENV_FILE.fullmatch(posixpath.basename((path or "").replace("\\", "/"))):
        refuse_credentials(f"editing {path}, one of the owner's sign-ins")
    if is_enforcement_path(path) or is_hook_program(path):
        owner_needed(f"editing {shown(path)}")


# --- GitHub Copilot Chat ---------------------------------------------------------------

def strings_in(value):
    """Every string in a tool's input, at any depth."""
    if isinstance(value, str):
        return [value]
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return [text for child in children for text in strings_in(child)]


def tool_commands(value):
    """The shell commands in a tool's input: each command string, at any depth, with its args if given."""
    if isinstance(value, list):
        return [command for child in value for command in tool_commands(child)]
    if not isinstance(value, dict):
        return []
    found = [command for child in value.values() for command in tool_commands(child)]
    command, args = value.get("command"), value.get("args")
    if isinstance(command, str) and command.strip():
        words = [str(a) for a in args if isinstance(a, (str, int, float))] if isinstance(args, list) else []
        found.append(" ".join([command] + [shlex.quote(word) for word in words]))
    return found


def check_terminal_command(command):
    """A command for a terminal whose shell the guard doesn't know (Copilot Chat uses the user's): it's
    checked as bash and again as PowerShell, each from the same starting state."""
    global AZ_SIGNED_IN_HERE
    state = save_shell()
    check_command(command, "Bash")
    restore_shell(state)
    AZ_SIGNED_IN_HERE = False
    check_command(command, "PowerShell")


def check_copilot(tool, tool_input):
    """A GitHub Copilot Chat tool call, checked as the Claude Code tool that does the same. What the guard
    can't read is refused, and so is anything that would ask the owner (decide_owner)."""
    global COPILOT
    COPILOT = True
    tool = COPILOT_IDS.get(tool, tool)
    if tool == "fetch_webpage":
        urls = tool_input.get("urls")
        for url in urls if isinstance(urls, list) and urls else [None]:
            check_host("a Copilot Chat web fetch", url_host(url) if isinstance(url, str) else None)
        return
    if tool in COPILOT_READS:
        pattern = tool_input.get("includePattern")  # grep_search and file_search scope a search with a glob
        for path in mcp_paths(tool_input) + ([pattern] if isinstance(pattern, str) else []):
            if is_credential_path(path):
                refuse_credentials(f"Copilot Chat's {tool} would read {path}, one of the owner's sign-ins")
        if tool_input.get("includeIgnoredFiles") and could_match_env(pattern):
            refuse_credentials(f"Copilot Chat's {tool} would search ignored files, where .env files are, with "
                               f"{pattern or 'no include pattern'}")
        return
    if tool in COPILOT_UNSEEN_CODE:
        refuse(f"Blocked: Copilot Chat's {tool} runs code the guard can't see (an editor command or an "
               "extension), which can do anything the editor can. Agent: do it with a terminal command or a file "
               "edit the guard can check, or tell the owner what you need; don't look for another way.")
    if tool in COPILOT_TERMINAL:
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            refuse("Blocked: a Copilot Chat terminal command the guard couldn't read, so it refuses rather than "
                   "guess. " + UNREADABLE)
        check_terminal_command(command)
        return
    if tool in COPILOT_PATCH:
        text = "\n".join(strings_in(tool_input))
        paths = PATCH_FILE_HEADER.findall(text) + [p for found in PATCH_PATH.findall(text) for p in found if p]
        if not paths:
            refuse("Blocked: a Copilot Chat patch whose files the guard couldn't read, so it refuses rather than "
                   "guess. " + UNREADABLE)
        for path in paths:
            check_file_edit(path)
        return
    paths = mcp_paths(tool_input)
    if tool in COPILOT_EDITS and not paths:
        refuse(f"Blocked: Copilot Chat's {tool} names no file the guard can read, so it refuses rather than "
               "guess. " + UNREADABLE)
    if tool in COPILOT_NEW_TASK:
        folder = tool_input.get("workspaceFolder")
        check_file_edit(os.path.join(folder if isinstance(folder, str) and folder else ROOT, ".vscode", "tasks.json"))
    if tool.startswith("mcp_"):
        check_mcp(tool, tool_input)  # a connector tool, as Copilot Chat names them
    elif tool in COPILOT_EDITS or not named_as_read(tool):
        for path in paths:
            check_file_edit(path)
    for command in tool_commands(tool_input):
        check_terminal_command(command)


# --- Azure -------------------------------------------------------------------------

def az_command():
    """How to run az (az.cmd on Windows), or None if it isn't installed. Tests point GUARD_AZ (a JSON list) at a stand-in."""
    if os.environ.get("GUARD_AZ"):
        return json.loads(os.environ["GUARD_AZ"])
    import shutil
    found = shutil.which("az")
    return [found] if found else None


def project_tenant():
    """The Azure tenant recorded in .claude/security-stack.json, or None while none is recorded
    (no file yet, or no azure.tenant_id). A file that can't be read or parsed, or a recorded value
    that isn't a tenant ID, raises, so the guard fails closed."""
    try:
        with open(os.path.join(ROOT, ".claude", "security-stack.json"), encoding="utf-8") as fh:
            stack = json.load(fh)
    except FileNotFoundError:
        return None
    tenant = (stack.get("azure") or {}).get("tenant_id")
    if tenant in (None, ""):
        return None
    if not isinstance(tenant, str) or not re.fullmatch(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", tenant):
        raise ValueError("azure.tenant_id in .claude/security-stack.json isn't a tenant ID")
    return tenant


def az_value(args, *names):
    """The value of an az option given as --name value or --name=value, or None."""
    for i, tok in enumerate(args):
        flag, eq, value = tok.partition("=")
        if flag in names:
            return value if eq else (args[i + 1] if i + 1 < len(args) else "")
    return None


def check_az_tenant(args, expected):
    """Refuse unless the command runs against the project's tenant: the one named with
    --tenant, or else the one az is signed in to (for --subscription, that subscription's)."""
    fix = (f"This project's tenant is {expected} (.claude/security-stack.json). Agent: stop and tell the owner; "
           f"don't switch accounts or tenants yourself. Owner: sign in with az login --tenant {expected}.")
    tenant = az_value(args, "--tenant")
    if not tenant:
        command = az_command()
        subscription = az_value(args, "--subscription")
        query = ["account", "show", "--query", "tenantId", "-o", "tsv"] + (
            ["--subscription", subscription] if subscription else [])
        env = dict(os.environ)
        if "AZURE_CONFIG_DIR" in SHELL_VARS:  # AZURE_CONFIG_DIR=... az ...: the same sign-in the command uses
            env["AZURE_CONFIG_DIR"] = SHELL_VARS["AZURE_CONFIG_DIR"]
        try:
            result = subprocess.run(command + query, capture_output=True, text=True, timeout=60, env=env) \
                if command else None
        except (OSError, subprocess.SubprocessError):
            result = None
        tenant = result.stdout.strip() if result is not None and result.returncode == 0 else ""
        if not tenant:
            refuse(f"Blocked: az couldn't confirm which Azure tenant it's signed in to, so the command isn't run. {fix}")
    if tenant.lower() != expected.lower():
        refuse(f"Blocked: az would run against tenant {tenant}, not this project's. {fix}")


def az_path(args):
    """The command path (group, subgroups, verb), and whether an option before it is one the
    guard can't read: az --subscription X group create has the path group create."""
    path, unknown, i = [], False, 0
    while i < len(args):
        tok = args[i]
        redirect = REDIRECT_WORD.match(tok)
        if redirect:  # az group list 2>&1: where the output goes isn't part of the command
            i += 1 if redirect.group(1) else 2
            continue
        if not tok.startswith("-"):
            path.append(tok.lower())
            i += 1
            continue
        if path:
            break  # the options after the path
        flag = tok.split("=", 1)[0]
        unknown = unknown or flag not in AZ_VALUE_OPTIONS | AZ_FLAGS
        i += 2 if flag in AZ_VALUE_OPTIONS and "=" not in tok else 1
    return path, unknown


def check_az_in_code(what, code):
    """Code that can run commands and names az: the guard can't check that command's tenant
    or what it does, so it needs the owner."""
    if CODE_WRITES.search(code) and AZ_IN_CODE.search(code):
        owner_needed(f"{what} runs az, which the guard can't check", AZURE_RULE)


def check_az(tokens):
    """Every az command runs against the project's tenant, and anything but a read needs the owner."""
    global AZ_SIGNED_IN_HERE
    args = tokens[1:]
    path, unknown = az_path(args)
    if {"-h", "--help"} & set(args) or (not path and not unknown):
        return  # help, az on its own, az --version
    if path and (path[0] in AZ_LOCAL_GROUPS or (path[0] == "account" and path[1:2] and path[1] in AZ_LOCAL_ACCOUNT)):
        if path[0] in ("login", "logout") or path[:2] in (["account", "set"], ["account", "clear"]):
            AZ_SIGNED_IN_HERE = True
        return  # this computer's CLI setup or sign-in
    if AZ_SIGNED_IN_HERE:
        refuse("Blocked: this command signs in or switches az's account, then runs another az command, so the "
               "guard can't check which tenant that one uses. Agent: run the sign-in on its own first, then the rest.")
    expected = project_tenant()
    if expected:
        check_az_tenant(args, expected)
    if unknown:
        owner_needed("an az command with an option before its command that the guard can't read", AZURE_RULE)
    elif path[0] == "rest":
        method = (az_value(args, "--method", "-m") or "get").lower()
        if method not in ("get", "head", "options"):
            owner_needed(f"az rest --method {method} can change Azure", AZURE_RULE)
        url = az_value(args, "--url", "--uri", "-u") or ""
        host = url_host(url)
        azure = host and (AZURE_HOSTS.search(host) or host in allowed_hosts())
        if not url.strip("'\"").startswith("/") and not azure:  # az rest can attach the owner's Azure token
            check_host("an az rest request, which can carry the owner's Azure token,", host)
    elif not AZ_READ_VERB.match(path[-1]):
        owner_needed(f"az {' '.join(path)} can change Azure", AZURE_RULE)


# --- Hook bypasses and shell commands -----------------------------------------------

def strip_heredocs(command):
    """Heredoc bodies are data (commit messages), not commands. The rest of the
    marker's line stays: `cat <<EOF > file` still writes to file."""
    return HEREDOC.sub(lambda m: m.group(3), command)


def segments(command, tool="Bash"):
    """Split a shell command into simple commands, as token lists. Parentheses come
    through as ["("] and [")"], so a subshell's cd and variables can end with it. A new line
    starts a new command unless the line ends in a continuation. A redirect's & or | (2>&1,
    &>out, >|out) doesn't split a command: the words after it are still its words. A
    substitution is a value the guard can't read (mask_substitutions)."""
    text = LINE_CONTINUATION.sub(r"\1", mask_substitutions(strip_heredocs(command), tool))
    text = PIPE_IN_REDIRECT.sub("", AMP_IN_REDIRECT.sub("", FD_DUP.sub("/dev/fd/", AMP_BEFORE_REDIRECT.sub(" ", text))))
    lexer = shlex.shlex(detach_redirects(text), posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace_split = True
    lexer.whitespace = lexer.whitespace.replace("\n", "")  # a new line separates commands, like ;
    lexer.commenters = ""
    current = []
    for token in lexer:
        if token in SEPARATORS or set(token) <= set(";&|()\n"):
            if current:
                yield current
            current = []
            for ch in token:
                if ch in "()":
                    yield [ch]
        else:
            current.append(token)
    if current:
        yield current


def detach_redirects(text):
    """A redirect written against the word before it (git log>out, cat<in) is a word of its own, as the shell
    reads it; an fd number, {name} or PowerShell's * in front of it (2>out, {fd}>out, *>out) belongs to it."""
    def detach(m):
        word = re.search(r"[^\s;&|()<>]*$", text[:m.start()]).group(0)
        return m.group(0) if re.fullmatch(r"\d+|\{\w+\}|\*", word) else " " + m.group(0)
    return ATTACHED_REDIRECT.sub(detach, text)


def substitutions(command, tool):
    """(bodies, unsure): the commands a shell runs inside $( ) or, in bash, backticks: unquoted or within double
    quotes, not single quotes, and in a heredoc whose marker isn't quoted. Each is checked as a command of its
    own. One that never closes runs to the end of the text. Unsure: a $( ) holds a case statement, whose
    patterns end in ) (case x in a) ...), so where the $( ) ends can't be told."""
    texts = [(strip_heredocs(command), True)]
    texts += [(m.group(4), False) for m in HEREDOC.finditer(command) if not m.group(1)]  # quotes are text there
    bodies, unsure = [], False
    for text, quoting in texts:
        for start, _, body in substitution_spans(text, tool, quoting):
            bodies.append(body)
            unsure = unsure or (text[start] == "$" and bool(CASE_STATEMENT.search(body)))
    return bodies, unsure


def substitution_spans(text, tool, quoting=True):
    """(start, end, body) for each substitution in text a shell runs, end being past where it closes. With
    quoting False, as in a heredoc's body, quotes are plain characters."""
    escape = "`" if tool == "PowerShell" else "\\"  # PowerShell escapes with a backtick, and has no backtick commands
    quote, i = None, 0
    while i < len(text):
        c = text[i]
        if c == escape and quote != "'":
            i += 2  # an escaped character: \` and \$( are literal
            continue
        if quote == "'":
            quote = None if c == "'" else quote
        elif c == "'" and quote is None and quoting:
            quote = "'"
        elif c == '"' and quoting:
            quote = None if quote == '"' else '"'
        elif c == "`":
            end = i + 1
            while end < len(text) and text[end] != "`":
                end += 2 if text[end] == "\\" else 1
            yield i, end + 1, text[i + 1:end].replace("\\`", "`")  # a nested backtick is escaped
            i = end
        elif text.startswith("$(", i):
            end = substitution_end(text, i + 2, escape)
            yield i, end + 1, text[i + 2:end]
            i = end
        i += 1


def mask_substitutions(text, tool):
    """text with each substitution replaced by a value the guard can't read, since it can't know what the
    command inside prints: rm $(printf x) removes whatever that is. The command inside is checked on its own."""
    out, last = [], 0
    for start, end, _ in substitution_spans(text, tool):
        out += [text[last:start], SUBSTITUTED]
        last = end
    return "".join(out) + text[last:]


def substitution_end(text, i, escape):
    """Where the $( before i closes: the matching ), outside quotes and comments; the end of the text if none
    does."""
    depth, quote = 1, None
    while i < len(text):
        c = text[i]
        if c == escape and quote != "'":
            i += 2
            continue
        if quote:
            quote = None if c == quote else quote
        elif c in "'\"":
            quote = c
        elif c == "#" and text[i - 1] in " \t\n;&|(":  # a comment, to the end of the line: its ) isn't one
            i = text.find("\n", i)
            if i < 0:
                return len(text)
            continue
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text)


def strip_prefix(tokens):
    """Drop keywords, env assignments and wrappers in front of the real program; check the
    assignments, and remember them for paths later in the command. Redirects in front of the
    program move after it (`>/dev/null git push` runs git), so the program is still read and
    where they write still checked."""
    i, moved = 0, []
    while i < len(tokens):
        tok = tokens[i]
        name = tok.split("=", 1)[0] if "=" in tok else None
        redirect = REDIRECT_WORD.match(tok)
        if redirect:
            width = 1 if redirect.group(1) else 2  # a bare > takes the next word as its target
            moved, i = moved + tokens[i:i + width], i + width
        elif tok in SHELL_KEYWORDS:
            i += 1
        elif name and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            if BLOCKED_ENV.match(name):
                block(f"setting {name} switches hooks off or injects git config")
            SHELL_VARS[name] = expand_vars(tok.split("=", 1)[1])
            i += 1
        elif tok in ASSIGNING_BUILTINS:
            # declare -x SKIP=1, export SKIP, readonly SKIP=...: check every argument.
            for arg in tokens[i + 1:]:
                if BLOCKED_ENV.match(arg.split("=", 1)[0]):
                    block(f"setting {arg.split('=', 1)[0]} switches hooks off or injects git config")
                if re.fullmatch(r"[A-Za-z_]\w*=.*", arg, re.DOTALL):
                    SHELL_VARS[arg.split("=", 1)[0]] = expand_vars(arg.split("=", 1)[1])
            return moved + split_redirects(tokens[i + 1:])[1]  # no program runs, but its redirects still write
        elif tok.rsplit("/", 1)[-1] in WRAPPERS:
            wrapper, i, needs = tok.rsplit("/", 1)[-1], i + 1, None  # needs: what the next word is for
            while i < len(tokens):
                redirect = REDIRECT_WORD.match(tokens[i])
                if redirect:  # the shell takes redirects out first: sudo 2>x -u root git, env -u 2>x HOME git
                    width = 1 if redirect.group(1) else 2
                    moved, i = moved + tokens[i:i + width], i + width
                elif needs == "split":  # env -S 'git push x' runs git push x, and its words can be options too
                    tokens, needs = tokens[:i] + env_words(tokens[i]) + tokens[i + 1:], None
                elif needs == "value":  # sudo -u root git push: root is -u's value, not the program
                    i, needs = i + 1, None
                elif not tokens[i].startswith("-"):
                    break
                elif wrapper == "env" and tokens[i].partition("=")[0] in ("-S", "--split-string"):
                    _, eq, inline = tokens[i].partition("=")
                    words = env_words(inline) if eq else []  # --split-string=... carries it; -S takes the next word
                    tokens, needs = tokens[:i] + words + tokens[i + 1:], None if eq else "split"
                else:
                    i, needs = i + 1, "value" if tokens[i] in WRAPPER_VALUE_OPTIONS.get(wrapper, ()) else None
        else:
            break
    return tokens[i:] + moved


def env_words(text):
    """The words env -S makes of its string: \\_ separates words too. An escape, ${VAR} or a comment in it asks
    the owner: env's own grammar there isn't the shell's, and the guard doesn't read it."""
    if re.search(r"\\(?!_)|\$|(^|\s)#", text):
        owner_needed("env -S with an escape, a variable or a comment, which the guard can't read")
    return shlex.split(text.replace("\\_", " "))


def split_redirects(words):
    """(the other words, the redirects): each redirect with its target when that's the next word."""
    plain, redirects, i = [], [], 0
    while i < len(words):
        found = REDIRECT_WORD.match(words[i])
        width = 2 if found and not found.group(1) else 1
        (redirects if found else plain).extend(words[i:i + width])
        i += width
    return plain, redirects


def redirect_inputs(tokens):
    """Files fed to a command with '<'."""
    out = []
    for i, tok in enumerate(tokens):
        if tok == "<":
            out += tokens[i + 1:i + 2]
        elif tok.startswith("<") and not tok.startswith("<<"):
            out.append(tok[1:])
    return out


def patch_targets(files):
    """Paths the patch files change, as written in them, or None when a patch can't be
    read (none named means it comes from a pipe)."""
    if not files:
        return None
    targets = []
    try:
        for name in files:
            with open(name, encoding="utf-8", errors="replace") as fh:
                for m in PATCH_PATH.finditer(fh.read()):
                    targets += [p for p in m.groups() if p and p != "/dev/null"]
    except OSError:
        return None
    return targets


def missing_hooks(here):
    """The git hooks a repository's pre-commit config needs that aren't installed in the clone
    at `here`. Checked only when Claude Code runs the guard: tests and CI have no session."""
    if not os.environ.get("CLAUDE_PROJECT_DIR"):
        return []

    def git(*args):
        return subprocess.run(["git", "-C", here, *args], capture_output=True, text=True, timeout=15).stdout.strip()

    top = git("rev-parse", "--show-toplevel")
    config = os.path.join(top, ".pre-commit-config.yaml") if top else ""
    if not config or not os.path.isfile(config):
        return []
    with open(config, encoding="utf-8", errors="replace") as fh:
        needed = ["pre-commit"] + (["commit-msg"] if "commit-msg" in fh.read() else [])
    missing = []
    for hook in needed:
        path = git("rev-parse", "--git-path", f"hooks/{hook}")
        path = path if os.path.isabs(path) else os.path.join(here, path)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                installed = "File generated by pre-commit" in fh.read()
        except OSError:
            installed = False
        if not installed or (os.name != "nt" and not os.access(path, os.X_OK)):  # git skips a hook it can't run
            missing.append(hook)
    return missing


def check_git(args, inputs=()):
    """args: everything after the git executable. inputs: files fed to it with < that args no longer shows."""
    i, workdir = 0, None
    while i < len(args) and args[i].startswith("-"):
        opt = args[i]
        value = None
        if opt in GIT_GLOBAL_WITH_VALUE and i + 1 < len(args):
            value = args[i + 1]
            i += 2
        else:
            if (opt.startswith("-c") or opt.startswith("-C")) and len(opt) > 2:
                value = opt[2:]
            elif "=" in opt:
                value = opt.split("=", 1)[1]
            i += 1
        if opt.startswith("-C") and value is not None:
            workdir = os.path.join(workdir, value) if workdir else value
        if value and "hookspath" in value.lower():
            block("git -c core.hooksPath points git away from this repo's hooks")
        if value and value.lower().startswith("alias."):
            block("an inline git alias can hide a hook bypass (git -c alias.x='commit --no-verify' x)")
        if value and GIT_ROUTING.match(value.lower().split("=", 1)[0]):
            owner_needed("git -c would send this command to another server", NETWORK_RULE)
    if i >= len(args):
        return
    sub, rest = args[i], args[i + 1:]
    here = to_abs(workdir) if workdir else CWD

    reading = any(a in ("--get", "--get-all", "--get-regexp", "--list", "-l") for a in rest)
    if sub == "config" and not reading:
        if any("hookspath" in a.lower() for a in rest):
            block("changing core.hooksPath points git away from this repo's hooks")
        if any(a.lower().startswith("alias.") for a in rest) and any(ALIAS_BYPASS.search(a) for a in rest):
            block("a git alias that skips hooks or runs a shell command can hide a hook bypass")
        if any(GIT_ROUTING.match(a.lower()) for a in rest):
            owner_needed("git config would point a remote at another server", NETWORK_RULE)
    if sub == "remote" and rest[:1] and rest[0] in ("add", "set-url", "rename"):
        owner_needed(f"git remote {rest[0]} can point a remote at another server", NETWORK_RULE)
    if sub == "config" and any(a.lower().lstrip("-") == "rename-section" for a in rest) \
            and any(re.match(r"^(remote|url|branch)\.", a.lower()) for a in rest):
        owner_needed("git config would move a remote's settings, which can point it at another server", NETWORK_RULE)
    if sub == "push":
        target, skip = None, 0
        for a in rest:
            redirect = REDIRECT_WORD.match(a)
            if skip:
                skip -= 1
            elif a in ("-o", "--push-option", "--receive-pack", "--exec"):
                skip = 1
            elif redirect:  # git push 2>&1, git push >/dev/null upstream: a redirect isn't the remote
                skip = 0 if redirect.group(1) else 1
            elif a.startswith("--repo") or a.startswith(("--receive-pack=", "--exec=")):
                target = target or "another repository"
            elif not a.startswith("-") and target is None:
                target = a
        if target not in (None, "origin"):
            owner_needed(f"git push to {target}, not origin", NETWORK_RULE)

    if sub in VERIFY_SUBCOMMANDS and "--no-verify" in rest:
        block(f"git {sub} --no-verify skips the hooks")

    if sub == "commit":
        skip_next = False
        for tok in rest:
            if skip_next:
                skip_next = False
                continue
            if tok == "--":
                break
            if tok.startswith("--"):
                if tok in COMMIT_LONG_WITH_VALUE:
                    skip_next = True
                continue
            if tok.startswith("-") and len(tok) > 1:
                for pos, ch in enumerate(tok[1:], start=1):
                    if ch == "n":
                        block("git commit -n skips the hooks")
                    if ch in COMMIT_SHORT_WITH_VALUE:
                        if pos == len(tok) - 1 and ch in "mFCct":
                            skip_next = True  # value is the next token
                        break
        missing = missing_hooks(here)
        if missing:
            block(f"this clone's {' and '.join(missing)} hook isn't installed, so the commit would skip its checks. "
                  "Install it first: pre-commit install -t pre-commit -t commit-msg")

    if sub in GIT_WRITE_SUBCOMMANDS:
        paths = rest[rest.index("--") + 1:] if "--" in rest else [a for a in rest if not a.startswith("-")]
        for tok in paths:
            path = os.path.join(here, tok)
            if is_enforcement_path(path, folders=True):
                owner_needed(f"git {sub} would change {shown(path)}")
                return

    if sub in GIT_PATCH_SUBCOMMANDS and in_repository(here) and not any(
            a.split("=", 1)[0] in GIT_PATCH_CONTROL for a in rest):
        sources = [a for a in rest if not a.startswith(("-", "<"))] + redirect_inputs(rest) + list(inputs)
        targets = patch_targets([to_abs(os.path.join(here, a)) for a in dict.fromkeys(sources)])
        hit = next((t for t in targets if is_enforcement_rel(t)), None) if targets is not None else None
        if targets is None or hit:
            owner_needed(f"git {sub} would change {hit}" if hit else f"git {sub} applies a patch that can't be read")


def check_git_redirects(program, tokens):
    """git manages .git/ and the paths it's given, but where its output is redirected is the shell writing:
    git show x > .claude/settings.json, git log > .git/hooks/pre-commit."""
    if any(GIT_DIR_PATH.search(path) for path, _ in written_paths("", tokens)):
        block("writing into .git/ can disable hooks or change git config")
    check_writes(program, tokens)


def check_git_dir_access(program, tokens):
    """A command that touches a path inside .git/ may only read it."""
    name = program[:-4] if program.endswith(".exe") else program
    touches = any(
        GIT_DIR_PATH.search(t) and (name in INTERPRETERS or not re.search(r"\s", t))
        for t in tokens[1:]
    )
    if not touches:
        return
    if any(REDIRECT.match(t) for t in tokens):
        block("writing into .git/ can disable hooks or change git config")
    if name not in READ_ONLY or (name == "find" and FIND_ACTIONS & set(tokens)):
        block(f"{program} on a path inside .git/ could change hooks or git config; only read-only commands may")


def shell_payload(tokens):
    """The command string of `bash -c '...'` (also -lc, -ec, ...), or None."""
    for i, tok in enumerate(tokens[1:], start=1):
        if tok.startswith("--"):
            continue
        if tok.startswith("-"):
            if "c" in tok[1:]:
                return tokens[i + 1] if i + 1 < len(tokens) else ""
            continue
        return None  # a script file: its contents can't be seen here
    return None


def powershell_payload(tokens):
    """The command of `pwsh -Command ...` or `-EncodedCommand <base64>`, or None."""
    for i, tok in enumerate(tokens[1:], start=1):
        flag = tok.lower()
        if flag.startswith("-") and len(flag) > 1 and "-command".startswith(flag):
            return " ".join(tokens[i + 1:])
        if flag.startswith("-e") and "-encodedcommand".startswith(flag) and i + 1 < len(tokens):
            try:
                return base64.b64decode(tokens[i + 1]).decode("utf-16-le")
            except (ValueError, UnicodeDecodeError):
                block("could not decode a PowerShell -EncodedCommand")
    return None


def check_in_new_shell(command, tool, depth):
    """Check a command another shell runs: its cd and variables don't reach this one."""
    saved = save_shell()
    try:
        check_command(command, tool, depth + 1)
    finally:
        restore_shell(saved)


def change_directory(program, tokens):
    """Follow cd, pushd/popd, Set-Location and Push-/Pop-Location. A directory the guard
    can't know (cd - with no earlier cd here, popd with nothing pushed, a folder named by a
    value it can't read, such as $(...)) is taken to be a protected one, so relative paths
    after it count as enforcement paths."""
    global CWD, OLDPWD
    unknown = os.path.join(ROOT, ".github")
    if program in ("popd", "pop-location"):
        target = DIR_STACK.pop() if DIR_STACK else unknown
    else:
        args = [t for t in split_redirects(tokens[1:])[0] if t == "-" or not t.startswith("-")]  # not cd >x dir's >x
        target = args[0] if args else "~"
        if target == "-":
            target = OLDPWD or unknown
        elif re.search(r"\$[\w({]", expand_vars(target)):
            target = unknown
        else:
            target = to_abs(target)
        if program in ("pushd", "push-location"):
            DIR_STACK.append(CWD)
    OLDPWD, CWD = CWD, target


def check_nested(program, tokens, tool, depth):
    """Commands hidden inside another command's arguments."""
    name = program[:-4] if program.endswith(".exe") else program
    payload, payload_tool = None, tool
    if name in SHELLS:
        payload, payload_tool = shell_payload(tokens), "Bash"
    elif name in POWERSHELLS:
        payload, payload_tool = powershell_payload(tokens), "PowerShell"
    elif name == "cmd":
        rest = [t for t in tokens[1:] if t.lower() not in ("/c", "/k", "/s", "/q", "/d")]
        payload, payload_tool = " ".join(rest), "PowerShell"  # backslash paths, like PowerShell
    elif name == "eval":
        payload = " ".join(tokens[1:])
    elif name in CODE_INTERPRETERS:
        # Code in another language can run git or az itself; judge its text conservatively.
        code = " ".join(tokens[1:])
        if BYPASS_TEXT.search(code):
            block(f"{program} code that mentions a hook bypass")
        if CREDENTIAL_TEXT.search(code):
            refuse_credentials(f"{program} code that names one of the owner's sign-ins")
        check_az_in_code(f"{program} code", code)
    if payload:
        check_in_new_shell(payload, payload_tool, depth)


def check_heredocs(command, depth):
    """A heredoc is data (a commit message) unless a shell or interpreter on its
    line runs it: `bash <<EOF`, `cat <<EOF | sh`, `python - <<EOF`."""
    for m in HEREDOC.finditer(command):
        line_start = command.rfind("\n", 0, m.start()) + 1
        line = command[line_start:m.start()] + " " + m.group(3)
        words = {re.split(r"[/\\]", w)[-1].lower().removesuffix(".exe") for w in re.findall(r"[\w./\\-]+", line)}
        body = m.group(4)
        if words & (SHELLS | POWERSHELLS | {"eval"}):
            check_in_new_shell(body, "PowerShell" if words & POWERSHELLS else "Bash", depth)
        elif words & CODE_INTERPRETERS:
            if BYPASS_TEXT.search(body):
                block("a script given on standard input mentions a hook bypass")
            if CREDENTIAL_TEXT.search(body):
                refuse_credentials("a script given on standard input names one of the owner's sign-ins")
            if NETWORK_CODE.search(body):
                owner_needed("a script given on standard input opens network connections", NETWORK_RULE)
            hit = code_touches_enforcement(body) if CODE_WRITES.search(body) else None
            if hit:
                owner_needed(f"a script given on standard input can change {hit}")
            check_az_in_code("a script given on standard input", body)


def check_command(command, tool="Bash", depth=0):
    if depth > MAX_NESTING:
        block("commands nested this deeply can't be checked")
    check_heredocs(command, depth)
    if tool == "PowerShell":
        # Backslash is a path separator in PowerShell, not an escape; a backtick ending a line continues it.
        command = POWERSHELL_CONTINUATION.sub(r"\1", command.replace("\\", "/"))
        if DOTNET_WRITE.search(command):
            hit = code_touches_enforcement(strip_heredocs(command))
            if hit:
                owner_needed(f"a .NET file call that can change {hit}")
    if POWERSHELL_ENV.search(strip_heredocs(command)):
        block("setting that environment variable switches hooks off or injects git config")
    bodies, unsure = substitutions(command, tool)  # echo "$(git push x)": the shell runs what's inside
    if unsure:
        owner_needed("a $( ) with a case statement in it, which the guard can't tell the end of")
    try:
        parts = list(segments(command, tool))
    except ValueError:
        check_substitutions(bodies, [save_shell()], tool, depth)
        # Unparseable (e.g. unbalanced quotes): judge the raw text conservatively.
        if re.search(r"\bgit\b", command) and re.search(r"--no-verify|hookspath", command, re.IGNORECASE):
            block("could not parse the command, and it mentions a hook bypass")
        if GIT_DIR_PATH.search(command):
            block("could not parse the command, and it touches a path inside .git/")
        hit = mentions_enforcement(command)
        if hit:
            owner_needed(f"a command that could not be parsed mentions {shown(hit)}")
        return
    states, subshells = [], []
    for tokens in parts:
        states.append(save_shell())  # the directory and variables each command runs with
        if tokens == ["("]:
            subshells.append(save_shell())
            continue
        if tokens == [")"]:
            if subshells:
                restore_shell(subshells.pop())  # a subshell's cd and variables end with it
            continue
        if tokens[0] == "for" and len(tokens) > 1:
            words = [expand_vars(w) for w in tokens[3:]] if tokens[2:3] == ["in"] else None  # `for f; do`: unknown
            LOOP_VARS[tokens[1]] = None if words is None or any("$" in w for w in words) else words
            continue
        assignment = re.fullmatch(r"\$(\w+)(?:=(.*))?", tokens[0], re.DOTALL) if tool == "PowerShell" else None
        if assignment and (assignment.group(2) is not None or tokens[1:2] == ["="]):
            value = assignment.group(2) if assignment.group(2) is not None else " ".join(tokens[2:3])
            SHELL_VARS[assignment.group(1)] = expand_vars(value)  # PowerShell: $p = 'path'
            continue
        tokens = strip_prefix(tokens)
        if not tokens:
            continue
        program = re.split(r"[/\\]", tokens[0])[-1].lower()
        if SUBSTITUTED in tokens[0]:  # $(printf git) push x: the program is what the substitution prints
            owner_needed("a command whose program comes from a substitution, which the guard can't read")
        if program in CHANGE_DIRECTORY:
            change_directory(program, tokens)  # later commands resolve their paths from here
            continue
        check_program(program, tokens, tool, depth)
        plain = [tokens[0]] + split_redirects(tokens[1:])[0]
        if plain != tokens:  # again as the program gets its arguments, which the shell takes redirects out of:
            # git -c >/dev/null core.hooksPath=x reads core.hooksPath=x as -c's value. What a patch reads
            # from < still counts.
            check_program(program, plain, tool, depth, redirect_inputs(tokens[1:]))
    states.append(save_shell())
    check_substitutions(bodies, states, tool, depth)


def check_program(program, tokens, tool, depth, inputs=()):
    """The checks for one command whose program is known. inputs: files fed to it with < that tokens no
    longer shows."""
    name = re.sub(r"\.(exe|cmd)$", "", program)
    check_credentials(program, tokens, name)
    check_outbound(program, tokens, name, tool)
    if program in ("git", "git.exe"):
        check_git(tokens[1:], inputs)  # git manages .git/ itself; its bypass options are checked here
        check_git_redirects(program, tokens)
        return
    if program in ("gh", "gh.exe"):
        check_gh(tokens)
    if program in ("az", "az.cmd", "az.exe"):
        check_az(tokens)
    check_git_dir_access(program, tokens)
    check_writes(program, tokens, inputs)
    check_nested(program, tokens, tool, depth)
    if program in ("pre-commit", "pre-commit.exe") and tokens[1:2] == ["uninstall"]:
        block("pre-commit uninstall removes the installed hooks")


def check_substitutions(bodies, states, tool, depth):
    """Each command a substitution runs, checked with every directory and set of variables the command
    passes through, since it runs with one of them: in cd .github; echo "$(rm CODEOWNERS)" the rm runs
    in .github."""
    if not bodies:
        return
    after = save_shell()
    for state in {repr(s): s for s in states}.values():
        for body in bodies:
            restore_shell((state[0], dict(state[1]), dict(state[2]), state[3], list(state[4])))
            check_in_new_shell(body, tool, depth)
    restore_shell(after)


def main():
    global ROOT, CWD, OWNED, EVENT, COPILOT
    COPILOT = "--copilot" in sys.argv[1:]
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except ValueError:
        event = None
    if not isinstance(event, dict):
        refuse("Blocked: the hook guard received input it couldn't read, so it refuses rather than guess. "
               + UNREADABLE)
    here = os.path.dirname(os.path.abspath(__file__))
    ROOT = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.path.join(here, "..", ".."))
    # Copilot Chat runs the guard from .github/hooks; without a cwd in the event, the workspace is the root.
    CWD = event.get("cwd") or (ROOT if COPILOT else os.getcwd())
    OWNED = load_codeowners()
    EVENT = event
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if COPILOT and not (isinstance(tool, str) and tool and isinstance(tool_input, dict)):
        refuse("Blocked: the hook guard received a Copilot Chat tool call it couldn't read, so it refuses rather "
               "than guess. " + UNREADABLE)
    if tool in ("Bash", "PowerShell"):
        command = tool_input.get("command", "")
        if not isinstance(command, str):
            raise TypeError("the command isn't text")
        check_command(command, tool)
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        check_file_edit(tool_input.get("file_path") or tool_input.get("notebook_path", ""))
    elif tool.startswith("mcp__"):
        check_mcp(tool, tool_input)
    elif tool == "WebFetch":
        url = tool_input.get("url")
        check_host("a web fetch", url_host(url) if isinstance(url, str) else None)
    elif COPILOT or COPILOT_IDS.get(tool, tool) in (COPILOT_TERMINAL | COPILOT_EDITS | COPILOT_PATCH
                                                    | COPILOT_UNSEEN_CODE | COPILOT_NEW_TASK):
        check_copilot(tool, tool_input)
    decide_owner()


def start_watchdog():
    """Block, with exit 2, if the guard hasn't finished in time. GUARD_WATCHDOG_SECONDS can only shorten it."""
    try:
        seconds = min(float(os.environ.get("GUARD_WATCHDOG_SECONDS", WATCHDOG_SECONDS)), WATCHDOG_SECONDS)
    except ValueError:
        seconds = WATCHDOG_SECONDS

    def expire():
        try:
            print(f"Blocked: the hook guard ran out of time ({seconds:g}s), so it refuses rather than let the tool "
                  "call through unchecked.", file=sys.stderr, flush=True)
        finally:
            os._exit(2)

    timer = threading.Timer(seconds, expire)
    timer.daemon = True
    timer.start()


if __name__ == "__main__":
    try:
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="replace")
        start_watchdog()
        main()
    except SystemExit:
        raise
    except BaseException as exc:  # fail closed: a guard that breaks must not let the command through
        try:
            print(f"Blocked: the hook guard hit an unexpected error ({type(exc).__name__}: {exc}), "
                  "so it refuses the command rather than let it through unchecked.", file=sys.stderr)
        finally:
            sys.exit(2)
