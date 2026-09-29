# Checks inventory

Every gate, hook, security check and code-quality check in this repository and in its GitHub and Azure setup: what each one does, what it stops, and how a new repository adopts it. Every fact here comes from the source files and the live settings. Rebuild it with [How to recount](#how-to-recount).

**Locked down by default.** Every check here starts on, and every check that can stop a change is set to block. A few only warn by design: their row says so, and none can be made to block. Lowering a protection is the owner's decision, never a way to get a change through: see [Lowering a protection](#lowering-a-protection) and the repository's [AGENTS.md](../AGENTS.md).

The columns:
- **Where it runs:** a Claude Code hook, a Claude Code setting, a Copilot Chat hook (VS Code), a git commit, CI on a pull request, scheduled CI, CI run by hand, by hand in the terminal, a GitHub setting, or an Azure setting.
- **If it breaks:** fails closed (a broken check stops the change), fails open (a broken check lets it through), or platform-enforced.
- **Type:** our code; our code running a third-party tool; a third-party tool we install and configure; or a platform setting.
- **To adopt:** copy as is; copy and set values; install and pin; turn on; or write your own.
- **Enforcement file:** whether changing the check needs the owner's approval under the repository's one rule.

## The checks

| # | Check | Where it runs | When it fires | What it stops | Blocks or warns | If it breaks | Type | To adopt | Enforcement file | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Hook skips refused | Claude Code hook | Before each shell command and file edit | `--no-verify`, `-n`, `SKIP=` and similar variables, `core.hooksPath`, hook-skipping aliases, `pre-commit uninstall`, writes inside `.git/` | Blocks | Fails closed | Our code | Copy as is | Yes | `.claude/hooks/block_hook_bypass.py`; `.claude/settings.json` (PreToolUse) |
| 2 | Git hooks installed before an agent's commit | Claude Code hook | Before each `git commit` | A commit in a clone whose pre-commit or commit-msg hook isn't installed | Blocks | Fails closed | Our code | Copy as is | Yes | `block_hook_bypass.py` (`missing_hooks`) |
| 3 | Enforcement changes ask the owner | Claude Code hook | Before each shell command and file edit | Edits, writes, deletes, moves, copies, links, inline-code writes, `git rm/mv/restore/checkout` and patches that touch an enforcement file | Blocks (asks the owner) | Fails closed | Our code | Copy as is | Yes | `block_hook_bypass.py` (`check_file_edit`, `check_writes`, `check_git`) |
| 4 | GitHub rule and setting changes ask the owner | Claude Code hook | Before each `gh` command | Repository, workflow, secret and variable changes; `gh api` writes other than issues, pull requests, labels, branches and workflow runs; unlisted GraphQL mutations | Blocks (asks the owner) | Fails closed | Our code | Copy as is | Yes | `block_hook_bypass.py` (`check_gh`) |
| 5 | Merging or approving an enforcement PR asks the owner | Claude Code hook | Before each merge or approval, by `gh`, REST, GraphQL or a connector | Merging or approving a PR that changes an enforcement file (renaming one away counts), or whose files can't be listed. | Blocks (asks the owner) | Fails closed | Our code | Copy as is | Yes | `block_hook_bypass.py` (`check_gh_pr`, `check_pr_change`, `dependabot_bump`); `.claude/security-stack.json` |
| 6 | Connector tools that touch enforcement ask the owner | Claude Code hook | Before each connector (MCP) tool call | Connector writes to enforcement files, and write-named operations on repository settings | Blocks (asks the owner) | Fails closed | Our code | Copy as is | Yes | `block_hook_bypass.py` (`check_mcp`); `.claude/settings.json` (matcher `mcp__.*`) |
| 7 | Azure commands stay in the project's tenant | Claude Code hook | Before each `az` command | `az` against another tenant, or when the sign-in can't be confirmed; a sign-in followed by another `az` command in one call | Blocks | Fails closed; skipped until a tenant is recorded | Our code | Copy as is | Yes | `block_hook_bypass.py` (`check_az`, `check_az_tenant`, `project_tenant`); `.claude/security-stack.json` |
| 8 | Azure changes ask the owner | Claude Code hook | Before each `az` command that isn't a read, and inline code that runs `az` | Creating, changing or deleting Azure resources and settings from the terminal; downloads; `az rest` writes | Blocks (asks the owner) | Fails closed | Our code | Copy as is | Yes | `block_hook_bypass.py` (`check_az`, `check_az_in_code`) |
| 9 | Python 3.9 or later for the guard | Claude Code hook | Before each guarded tool call | Guarded tool calls when Python is missing or too old for the guard to run | Blocks | Fails closed | Our code | Copy as is | Yes | `.claude/settings.json` (PreToolUse, third and fifth entries) |
| 10 | Git hooks installed at session start | Claude Code hook | When a session starts | A session working in a clone without the git hooks | Warns (a message; check 2 blocks the commit) | Fails open (a message only) | Our code, running pre-commit | Copy as is | Yes | `.claude/settings.json` (SessionStart) |
| 11 | Secrets | git commit | Each commit | Secrets in staged files that aren't in `.secrets.baseline` | Blocks | Fails closed | Third-party tool: detect-secrets (pinned in `.pre-commit-config.yaml`) | Install and pin (its `rev`) | Yes | `.pre-commit-config.yaml` (detect-secrets); `.secrets.baseline` |
| 12 | Large files | git commit | Each commit | Staged files over 500 KB | Blocks | Fails closed | Third-party tool: pre-commit-hooks (pinned in `.pre-commit-config.yaml`) | Install and pin (its `rev`) | Yes | `.pre-commit-config.yaml` (check-added-large-files) |
| 13 | Private keys | git commit | Each commit | Private keys in staged files | Blocks | Fails closed | Third-party tool: pre-commit-hooks (pinned in `.pre-commit-config.yaml`) | Install and pin (its `rev`) | Yes | `.pre-commit-config.yaml` (detect-private-key) |
| 14 | Merge-conflict markers | git commit | Each commit | Unresolved merge-conflict markers | Blocks | Fails closed | Third-party tool: pre-commit-hooks (pinned in `.pre-commit-config.yaml`) | Install and pin (its `rev`) | Yes | `.pre-commit-config.yaml` (check-merge-conflict) |
| 15 | Broken YAML | git commit | Each commit | YAML files that don't parse | Blocks | Fails closed | Third-party tool: pre-commit-hooks (pinned in `.pre-commit-config.yaml`) | Install and pin (its `rev`) | Yes | `.pre-commit-config.yaml` (check-yaml) |
| 16 | Blocked names in files and paths | git commit | Each commit | Listed names in staged files and their paths | Blocks | Fails closed | Our code | Copy and set values (the project's names, added as hashes) | Yes | `scripts/check_blocked_terms.py`; `.github/blocked-terms.txt`; `.pre-commit-config.yaml` (blocked-names) |
| 17 | Blocked names in the commit message | git commit | Each commit message | Listed names in the message | Blocks | Fails closed | Our code | Copy and set values (the project's names, added as hashes) | Yes | `scripts/check_blocked_terms.py --message`; `.pre-commit-config.yaml` (blocked-names-message) |
| 18 | App files under 500 lines | git commit | Each commit that stages a `src/` Python file | A `src/` Python file over 500 lines | Blocks | Fails closed | Our code | Copy as is | Yes | `scripts/check_file_length.py`; `.pre-commit-config.yaml` (file-length) |
| 19 | Lint at commit | git commit | Each commit that stages a Python file | Lint findings in app code, with noqa comments ignored | Blocks | Fails closed | Third-party tool: ruff (pinned in `.pre-commit-config.yaml`) | Install and pin (its `rev`, the same version as `uv.lock`) | Yes | `.pre-commit-config.yaml` (ruff-check); `pyproject.toml` |
| 20 | Format at commit | git commit | Each commit that stages a Python file | Unformatted Python; the hook formats it and stops the commit | Blocks | Fails closed | Third-party tool: ruff (pinned in `.pre-commit-config.yaml`) | Install and pin (its `rev`, the same version as `uv.lock`) | Yes | `.pre-commit-config.yaml` (ruff-format) |
| 21 | Secret scan of the PR | CI on PR | Each PR update | A secret in any file the PR adds or changes (the default branch's full scan is check 44) | Blocks | Fails closed | Our code, running detect-secrets | Copy as is | Yes | `.github/workflows/security-gate.yml` (secret-scan) |
| 22 | Commit checks replayed | CI on PR | Each PR update | A hook skipped locally, or one the PR's config drops (the default branch's config runs too) | Blocks | Fails closed | Our code, running pre-commit | Copy as is | Yes | `security-gate.yml` (precommit) |
| 23 | Tests of the gate and the guard | CI on PR | Each PR update | A PR that breaks or weakens the gate or the guard, including by changing a tested behaviour and its test together | Blocks | Fails closed | Our code, running unittest | Copy as is | Yes | `security-gate.yml` (selftest); `tests/gate/`; `tests/hooks/` |
| 24 | Gate: no new suppressions | CI on PR | Each PR update | New zizmor ignores, secret-scan allowlist comments, noqa and type-ignore comments, type-checker directives, coverage exclusions and test skips, in any file | Blocks | Fails closed | Our code | Copy as is | Yes | `scripts/security_gate.sh` (section 1) |
| 25 | Gate: no blocked names | CI on PR | Each PR update | Listed names in changed files, file paths, the PR title and description, and every commit message | Blocks | Fails closed | Our code | Copy and set values (the project's names, added as hashes) | Yes | `security_gate.sh` (section 2); `scripts/check_blocked_terms.py` |
| 26 | Gate: risky workflow settings | CI on PR | Each PR that changes a workflow | What zizmor finds in the changed workflows | Blocks | Fails closed | Our code, running zizmor | Copy as is | Yes | `security_gate.sh` (section 3) |
| 27 | Gate: workflows can't weaken the required checks | CI on PR | Each PR that changes a workflow | Changes to the trusted workflow that could let a required check pass without running; any other job that could report a required name | Blocks | Fails closed | Our code | Copy and set values (the required check names) | Yes | `security_gate.sh` (section 3); `scripts/workflow_checks.py` |
| 28 | Gate: protected lists only grow | CI on PR | Each PR that changes one of the lists | An entry removed from any of eleven protected lists | Blocks | Fails closed | Our code | Copy as is | Yes | `security_gate.sh` (section 4); `scripts/precommit_hooks.py` |
| 29 | Gate: pinned tool lists are frozen | CI on PR | Each PR that changes `.github/requirements/` | A package added, removed or swapped, or a list added, renamed or deleted | Blocks | Fails closed | Our code | Copy as is | Yes | `security_gate.sh` (section 4) |
| 30 | Gate: secret scanning only gets stricter | CI on PR | Each PR that changes `.secrets.baseline` | A detector removed or loosened, a new filter or filter pattern, a new allowlisted finding | Blocks | Fails closed | Our code | Copy as is | Yes | `security_gate.sh` (section 5); `scripts/baseline_checks.py` |
| 31 | Gate: security-critical paths reported | CI on PR | Each PR update | Nothing: it lists changed security-critical paths, and those without a dedicated check yet | Warns | Fails closed (an error stops the gate) | Our code | Copy and set values (the path patterns) | Yes | `security_gate.sh` (section 6); `.github/security-critical-paths.txt` |
| 32 | Lint | CI on PR | Each PR update | Lint findings in app code, including size limits and imports of `unittest.mock`; noqa comments ignored | Blocks | Fails closed | Our code, running ruff | Install and pin (in `pyproject.toml` and `uv.lock`) | Yes | `scripts/check_python.sh`; `pyproject.toml` (`[tool.ruff]`) |
| 33 | Format | CI on PR | Each PR update | Unformatted Python | Blocks | Fails closed | Our code, running ruff | Install and pin (in `pyproject.toml` and `uv.lock`) | Yes | `scripts/check_python.sh` |
| 34 | Types | CI on PR | Each PR update | Type errors: strict for `src/`, standard for tests; type-ignore comments do nothing | Blocks | Fails closed | Our code, running basedpyright | Install and pin (in `pyproject.toml` and `uv.lock`) | Yes | `scripts/check_python.sh`; `pyproject.toml` (`[tool.pyright]`) |
| 35 | Tests | CI on PR | Each PR update | A failing test, a warning, an unknown marker, or no tests at all | Blocks | Fails closed | Our code, running pytest | Install and pin (in `pyproject.toml` and `uv.lock`) | Yes | `scripts/check_python.sh`; `pyproject.toml` (`[tool.pytest.ini_options]`) |
| 36 | Skipped tests fail the run | CI on PR | Each test run | A skipped or expected-to-fail test | Blocks | Fails closed | Our code | Copy as is | Yes | `tests/conftest.py` |
| 37 | Changed-line coverage | CI on PR | Each PR update | Less than 80% of the changed lines covered | Blocks | Fails closed | Our code, running diff-cover | Install and pin (in `pyproject.toml` and `uv.lock`) | Yes | `scripts/check_python.sh`; `pyproject.toml` (`[tool.coverage]`) |
| 38 | Dependencies | CI on PR | Each PR update | A package that `src/` uses but doesn't declare, or declares but doesn't use | Blocks | Fails closed | Our code, running deptry | Install and pin (in `pyproject.toml` and `uv.lock`) | Yes | `scripts/check_python.sh`; `pyproject.toml` (`[tool.deptry]`) |
| 39 | Dead code | CI on PR | Each PR update | Code in `src/` that nothing calls | Blocks | Fails closed | Our code, running vulture | Install and pin (in `pyproject.toml` and `uv.lock`) | Yes | `scripts/check_python.sh`; `pyproject.toml` (`[tool.vulture]`) |
| 40 | Known vulnerabilities | CI on PR | Each PR update | A locked package with a known vulnerability | Blocks | Fails closed | Our code, running pip-audit | Install and pin (in `pyproject.toml` and `uv.lock`) | Yes | `scripts/check_python.sh` |
| 41 | Hash-checked installs for the Python checks | CI on PR | Each PR update | A package whose hash doesn't match `uv.lock`; a `uv.lock` out of date with `pyproject.toml`; a PR dependency replacing a tool; a checkout that isn't the PR's commit | Blocks | Fails closed | Our code, running uv | Install and pin (the uv version in the workflow) | Yes | `security-gate.yml` (python) |
| 42 | Hash-pinned tools for the security jobs | CI on PR | Each job that installs its tools | A tool file whose hash isn't in its list | Blocks | Fails closed | Our code, running pip | Install and pin (fresh versions and hashes) | Yes | `.github/requirements/*.txt` |
| 43 | Seven-day cooldown on package versions | CI on PR | Each time `uv.lock` is resolved; CI checks the lock is current | Package versions uploaded in the last seven days | Blocks | Fails closed | Third-party tool: uv (pinned in `security-gate.yml`) | Install and pin (`exclude-newer` in `pyproject.toml`) | Yes | `pyproject.toml` (`[tool.uv]`); `uv.lock` |
| 44 | Secret scan of main | CI scheduled | After each merge to main, and daily | A secret on main, including one only newer patterns detect | Warns (a failed run blocks nothing) | Fails visibly | Our code, running detect-secrets | Copy as is | Yes | `.github/workflows/security.yml` (secret-scan-main) |
| 45 | Vulnerability audit of main | CI scheduled | After each merge to main, and daily | A vulnerability disclosed after a package was merged | Warns (a failed run blocks nothing) | Fails visibly | Our code, running pip-audit | Copy as is | Yes | `security.yml` (dependency-audit-main) |
| 46 | Keyless Azure sign-in proof | CI, run by hand | When run | A broken sign-in, found before a deploy needs it | Warns (a failed run) | Fails visibly | Our code, running the azure/login action | Copy and set values (the environment name) | Yes | `.github/workflows/azure-login-check.yml` |
| 47 | Required status checks | GitHub setting | Each PR into the default branch | Merging unless every required check passes on an up-to-date branch | Blocks | Platform-enforced | Platform setting: GitHub | Turn on (the required check names) | Yes | Ruleset on the default branch (`required_status_checks`) |
| 48 | Pull request required, squash only | GitHub setting | Each change to the default branch | Direct pushes; merge commits and rebase merges | Blocks | Platform-enforced | Platform setting: GitHub | Turn on | Yes | Ruleset (`pull_request`) |
| 49 | Code-owner review for other authors | GitHub setting | Each PR that changes a file in CODEOWNERS | Merging such a PR by an author who isn't a code owner until the owner approves; approvals are dismissed by a new push | Blocks | Platform-enforced | Platform setting: GitHub | Turn on | Yes | Ruleset (`pull_request`) |
| 50 | Extra approval for unattributed changes | GitHub setting | Each PR | A commit whose author isn't linked to a GitHub account, without one more approval | Blocks | Platform-enforced | Platform setting: GitHub | Turn on | Yes | Ruleset (`pull_request`) |
| 51 | No deletion or force push | GitHub setting | Always | Deleting the default branch, or rewriting its history | Blocks | Platform-enforced | Platform setting: GitHub | Turn on | Yes | Ruleset (`deletion`, `non_fast_forward`) |
| 52 | No one bypasses the ruleset | GitHub setting | Always | Anyone, admins and the owner included, skipping the rules | Blocks | Platform-enforced | Platform setting: GitHub | Turn on | Yes | Ruleset (enforcement active, bypass list empty) |
| 53 | Enforcement files listed | GitHub setting | Read by checks 3, 5, 49 and 68 | Changes to enforcement files without the owner | Blocks (through those checks) | Fails closed (the guard treats every file as enforcement if it can't read the list) | Platform setting: GitHub | Copy and set values (the owner's handle) | Yes | `.github/CODEOWNERS` |
| 54 | Read-only workflow token; Actions can't approve PRs | GitHub setting | Each workflow run | A workflow writing to the repository without asking for write permission; a workflow approving a PR | Blocks | Platform-enforced | Platform setting: GitHub | Turn on | Yes | Actions permissions (workflow) |
| 55 | Actions pinned to a full commit SHA | GitHub setting | Each workflow run | A workflow using an action by tag or branch | Blocks | Platform-enforced | Platform setting: GitHub | Turn on | Yes | Actions permissions |
| 56 | Dependabot alerts | GitHub setting | When an advisory affects a dependency | Vulnerable dependencies going unnoticed | Warns | Platform-enforced | Platform setting: GitHub | Turn on | Yes | Repository settings (vulnerability alerts) |
| 57 | Dependabot security updates | GitHub setting | When an alert has a fix | Vulnerable dependencies staying unpatched; it opens a fix PR | Warns | Platform-enforced | Platform setting: GitHub | Turn on | Yes | Repository settings (automated security fixes) |
| 58 | Dependabot version updates | GitHub setting | Weekly | Stale action pins and Python packages; it opens update PRs for versions at least seven days old | Warns | Platform-enforced | Platform setting: GitHub | Copy as is | Yes | `.github/dependabot.yml` |
| 59 | Deploy environment limited to the default branch | GitHub setting | Each job that uses the environment | A job on any other branch using the deploy environment and its sign-in | Blocks | Platform-enforced | Platform setting: GitHub | Turn on (the environment and its branch policy) | Yes | The deploy environment's branch policy |
| 60 | Allowed locations | Azure setting | Each resource created | A resource outside the project's region | Blocks | Platform-enforced | Platform setting: Azure | Turn on (the project's region) | No | Policy assignment `allowed-locations` |
| 61 | Allowed locations for resource groups | Azure setting | Each resource group created | A resource group outside the project's region | Blocks | Platform-enforced | Platform setting: Azure | Turn on (the project's region) | No | Policy assignment `allowed-rg-locations` |
| 62 | Cloud security benchmark audit | Azure setting | Continuously | Nothing: it reports resources that fall short of the benchmark | Warns | Platform-enforced | Platform setting: Azure | Turn on (with Defender for Cloud) | No | Policy assignment `SecurityCenterBuiltIn` |
| 63 | Monthly budget alerts | Azure setting | As costs accrue | Spending going unnoticed | Warns | Platform-enforced | Platform setting: Azure | Turn on (the monthly amount) | No | The budget named in `.claude/security-stack.json` |
| 64 | Deploy identity limited to the app resource group | Azure setting | Each deploy | The deploy identity acting outside the app resource group, or on its own permissions | Blocks | Platform-enforced | Platform setting: Azure | Turn on | No | Role assignment on the deploy identity |
| 65 | Sign-in only from the deploy environment, with no secret | Azure setting | Each CI sign-in | Any other workflow signing in as the deploy identity; stored credentials | Blocks | Platform-enforced | Platform setting: Azure | Turn on (the repository and environment in the subject) | No | Federated credential on the deploy identity |
| 66 | GitHub settings at the baseline | By hand | When run | GitHub settings that fall short of the baseline going unnoticed: the ruleset, Actions, Dependabot and the deploy environment | Warns | Fails closed (a setting it can't read ends the run with exit 2) | Our code | Copy as is | Yes | `scripts/github_settings.py` |
| 67 | Review threads resolved before merging | GitHub setting | Each PR into the default branch | Merging while a review thread, a bot's included, is unresolved | Blocks | Platform-enforced | Platform setting: GitHub | Turn on | Yes | Ruleset (`pull_request`, conversation resolution) |
| 68 | The guard in Copilot Chat | Copilot Chat hook (VS Code) | Before each tool call by Copilot Chat's agent in VS Code | What checks 1 to 8, 71 and 72 stop, from Copilot Chat's terminal, file edits, patches, file reads, web fetches, tasks and connectors; editor commands, extension installs and tool calls the guard can't read. It refuses where Claude Code would ask | Blocks | Fails closed (the registration turns a guard that can't start into a block, passes the block through Windows PowerShell's exit code, and runs from an enforcement folder; a planted program the hooks run needs the owner; the guard blocks on its own after 45 seconds) | Our code | Copy as is | Yes | `.github/hooks/agent-guard.json`; `block_hook_bypass.py` (`check_copilot`) |
| 69 | Gate: hook pins are full commit hashes | CI on PR | Each PR that changes `.pre-commit-config.yaml` | A hook repository pinned by a tag, a branch, a short hash or nothing | Blocks | Fails closed | Our code | Copy as is | Yes | `security_gate.sh` (section 4); `scripts/precommit_hooks.py` (`--pins`) |
| 70 | Sign-in files denied to Claude Code | Claude Code setting | Before each file read, and each shell read Claude Code recognizes | Claude Code reading `~/.azure`, `~/.ssh`, `~/.config/gh`, `~/.aws`, `~/.docker/config.json` and `.env` files other than `.env.example` | Blocks | Platform-enforced (in every permission mode, bypass included) | Third-party tool: Claude Code (permission rules) | Copy as is | Yes | `.claude/settings.json` (`permissions.deny`) |
| 71 | Sign-in reads and token printing refused | Claude Code hook | Before each shell command and file edit | Commands that read or copy those sign-ins or `.env` files, in bash or PowerShell, inline code that names them, edits to them, and commands that print a token (`gh auth token`, `gh auth status --show-token`, `az account get-access-token`, `aws configure export-credentials`) | Blocks | Fails closed | Our code | Copy as is | Yes | `block_hook_bypass.py` (`check_credentials`, `is_credential_path`) |
| 72 | Outbound data asks the owner | Claude Code hook | Before each shell command and web fetch | Requests that send a body, upload a file or use a method other than GET; requests to a host that isn't on the allowlist or can't be read; `az rest` outside Azure and the allowlist; `gh gist create`; `git push` to a remote other than `origin`; remote URL changes; `scp`, `sftp`, `ssh`, `nc` and `rsync` to another computer; inline code that opens network connections | Blocks (asks the owner) | Fails closed | Our code | Copy and set values (the allowlist) | Yes | `block_hook_bypass.py` (`check_outbound`, `check_web_request`, `check_host`); `.claude/security-stack.json` (`network.allowed_hosts`); `.claude/settings.json` (matcher `WebFetch`) |

## Each check

### 1. Hook skips refused
- **What it does:** parses each shell command before it runs, including nested shells, heredocs and inline code, and refuses any way of skipping the git hooks.
- **What it stops:** `git commit --no-verify` or `-n`; `SKIP=`, `HUSKY=`, `PRE_COMMIT_ALLOW_NO_CONFIG=` and `GIT_CONFIG_*`, in bash and PowerShell; `core.hooksPath`; aliases that hide a skip; `pre-commit uninstall`; any non-read-only command on a path inside `.git/`.
- **Why it exists:** the commit checks only help if an agent can't switch them off.
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`Blocks`, `Allows`).
- **How to adopt:** copy `.claude/hooks/block_hook_bypass.py` and `.claude/settings.json` (setup prompt Phase 1, step 1).
- **Lowering it:** change the guard, which asks the owner. The guard's tests assert this behaviour, so the change also fails `selftest` and needs the owner's temporary ruleset bypass. The project gives up refusing hook skips in Claude Code; CI still replays the hooks (check 22).

### 2. Git hooks installed before an agent's commit
- **What it does:** before `git commit`, checks that the clone has the pre-commit and commit-msg hooks the config expects.
- **What it stops:** a commit that would skip its checks because the hooks were never installed.
- **Why it exists:** a clone without hooks skips them silently.
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`HooksInstalled`).
- **How to adopt:** comes with the guard (Phase 1, step 1).
- **Lowering it:** change the guard; it fails `selftest`, so it needs the owner's temporary bypass. The project gives up the commit-time catch; CI still replays the hooks.

### 3. Enforcement changes ask the owner
- **What it does:** before a file edit or shell command, works out which paths it changes, and asks the owner when one is an enforcement file (CODEOWNERS, plus Claude Code's and VS Code's settings files).
- **What it stops:** an agent changing its own checks without the owner.
- **Why it exists:** the repository's one rule: agents never skip or change enforcement without the owner's approval.
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`OwnerApproval`).
- **How to adopt:** comes with the guard (Phase 1, step 1).
- **Lowering it:** change the guard; it fails `selftest`, so it needs the owner's temporary bypass. The project gives up the owner's say over enforcement changes made in the terminal.

### 4. GitHub rule and setting changes ask the owner
- **What it does:** asks the owner before `gh` commands and `gh api` writes that change the repository's rules or settings. Everyday work on issues, pull requests, labels, branches and workflow runs passes.
- **What it stops:** an agent loosening a ruleset or setting from the terminal.
- **Why it exists:** GitHub rules and settings are enforcement, and the agent works through an admin account.
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`OwnerApproval`).
- **How to adopt:** comes with the guard (Phase 1, step 1).
- **Lowering it:** change the guard; it fails `selftest`, so it needs the owner's temporary bypass. The project gives up the owner's say over setting changes made in the terminal.

### 5. Merging or approving an enforcement PR asks the owner
- **What it does:** lists the files of the PR being merged or approved, with a renamed file's old name too, and asks the owner if any is an enforcement file. It covers `gh pr merge`, `gh pr review --approve`, the REST and GraphQL forms, and connector tools. A PR whose files can't be listed counts as one.
- **What it stops:** an agent merging its own enforcement change.
- **Why it exists:** GitHub doesn't hold a code owner's own PR (check 49), and the agent uses the owner's account.
- **Dependabot's bumps:** with `github.dependabot_merges_on_green` set to `true` in `.claude/security-stack.json`, it doesn't ask before merging or approving, by `gh`, REST or a connector, a PR that meets three conditions. Dependabot opened it, in this repository. Only Dependabot has pushed to its branch, by GitHub's record of the branch's pushes, from the branch's creation to the PR's head. And every change to an enforcement file moves an action's pin in a workflow, or a dependency's version in `pyproject.toml`, to another pin or version of the same action or dependency. Anything else, or anything it can't confirm, asks. The setting is off in the baseline.
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`PullRequestChanges`, `PullRequestRenames`, `DependabotBumps`).
- **How to adopt:** comes with the guard (Phase 1, step 1).
- **Lowering it:** change the guard; it fails `selftest`, so it needs the owner's temporary bypass. The project gives up the owner's say over enforcement merges made in the terminal. Letting Dependabot's bumps through is the setting above; the guard asks before `.claude/security-stack.json` changes. The project gives up the owner's say over those bumps, and relies on the required checks and Dependabot's seven-day cooldown on version updates (check 58). Security updates (check 57) skip the cooldown by design, so a fix for a known vulnerability merges without waiting.

### 6. Connector tools that touch enforcement ask the owner
- **What it does:** for each connector (MCP) tool call that isn't named as a read, checks the paths it names and whether it targets repository settings.
- **What it stops:** enforcement changes made through a connector from this session.
- **Why it exists:** connectors write through the same account as the terminal.
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`OwnerApproval`, `PullRequestChanges`).
- **How to adopt:** comes with the guard, registered for `mcp__.*` in `.claude/settings.json` (Phase 1, step 1).
- **Lowering it:** remove the registration or change the guard. The gate refuses a removed hook registration, and `selftest` fails on a changed behaviour, so it needs the owner's temporary bypass. The project gives up the owner's say over connector changes.

### 7. Azure commands stay in the project's tenant
- **What it does:** before each `az` command, confirms the tenant is the one recorded in `.claude/security-stack.json`: the tenant named with `--tenant`, or else the signed-in one (for `--subscription`, that subscription's). Signing in and the CLI's own setup are exempt.
- **What it stops:** Azure commands against another organisation's tenant, or with an unconfirmed sign-in, or after a sign-in in the same call.
- **Why it exists:** the project must only ever touch its own Azure tenant.
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`AzureCommands`).
- **How to adopt:** comes with the guard; the tenant is recorded in setup Phase 5, step 4. Until then, only check 8 applies.
- **Lowering it:** change the guard; it fails `selftest`, so it needs the owner's temporary bypass. The project gives up the protection against working in the wrong tenant.

### 8. Azure changes ask the owner
- **What it does:** asks the owner before any `az` command that isn't a read (show, list, get, what-if, ...), before downloads, `az rest` writes, and inline code that runs `az`. It refuses in modes that can't ask.
- **What it stops:** Azure changes made from the terminal, which would skip the pull request and the deploy job.
- **Why it exists:** Azure changes go through the checkpoint (architecture Section 10, item 24).
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`AzureCommands`).
- **How to adopt:** comes with the guard (Phase 1, step 1).
- **Lowering it:** change the guard; it fails `selftest`, so it needs the owner's temporary bypass. The project gives up the owner's say over terminal changes to Azure.

### 9. Python 3.9 or later for the guard
- **What it does:** a second hook, run before every guarded tool call, that blocks when `python` is missing or older than 3.9.
- **What it stops:** tool calls going through unchecked because the guard can't start.
- **Why it exists:** a guard that can't run must not let commands through.
- **Tested by:** untested.
- **How to adopt:** comes with `.claude/settings.json` (Phase 1, step 1).
- **Lowering it:** remove the registration. The gate refuses a removed hook registration, so it needs the owner's temporary bypass. The project gives up failing closed when Python is missing.

### 10. Git hooks installed at session start
- **What it does:** runs `pre-commit install -t pre-commit -t commit-msg` when a Claude Code session starts, and prints a message if pre-commit is missing or the install fails.
- **What it stops:** sessions working without the git hooks. The block itself is check 2.
- **Why it exists:** hooks aren't cloned with the repository.
- **Tested by:** untested. Its removal is refused by the gate (`tests/gate/test_security_gate.py`, `test_session_start_hook_removed_fails`).
- **How to adopt:** comes with `.claude/settings.json` (Phase 1, step 1).
- **Lowering it:** remove the registration; the gate refuses that, so it needs the owner's temporary bypass. The project gives up automatic installation; check 2 still blocks commits.

### 11. Secrets
- **What it does:** scans staged files for secrets, comparing against `.secrets.baseline`.
- **What it stops:** keys, tokens and passwords being committed.
- **Why it exists:** a pushed secret is exposed even if deleted later.
- **Tested by:** untested here. Setup Phase 2, step 4 proves it with a fake key.
- **How to adopt:** comes with `.pre-commit-config.yaml` (Phase 1); pin its `rev` (Phase 1, step 5) and generate the baseline (Phase 1, step 6).
- **Lowering it:** remove or narrow the hook. The gate refuses a removed or changed hook, so it needs the owner's temporary bypass. The project gives up the commit-time catch; check 21 still scans each PR.

### 12. Large files
- **What it does:** refuses staged files over 500 KB.
- **What it stops:** large binaries and data dumps in the history.
- **Why it exists:** they bloat every clone and can hide data.
- **Tested by:** untested.
- **How to adopt:** comes with `.pre-commit-config.yaml` (Phase 1); pin its `rev` (Phase 1, step 5).
- **Lowering it:** raise the limit or remove the hook; the gate refuses either, so it needs the owner's temporary bypass. The project gives up the size limit.

### 13. Private keys
- **What it does:** refuses staged files that contain a private key.
- **What it stops:** private keys being committed.
- **Why it exists:** a key in the history is compromised.
- **Tested by:** untested.
- **How to adopt:** comes with `.pre-commit-config.yaml` (Phase 1); pin its `rev` (Phase 1, step 5).
- **Lowering it:** remove the hook; the gate refuses that, so it needs the owner's temporary bypass. The project gives up this catch; checks 11 and 21 may still find the key.

### 14. Merge-conflict markers
- **What it does:** refuses staged files with unresolved conflict markers.
- **What it stops:** broken merges being committed.
- **Why it exists:** conflict markers break code and configuration silently.
- **Tested by:** untested.
- **How to adopt:** comes with `.pre-commit-config.yaml` (Phase 1); pin its `rev` (Phase 1, step 5).
- **Lowering it:** remove the hook; the gate refuses that, so it needs the owner's temporary bypass. The project gives up this catch.

### 15. Broken YAML
- **What it does:** refuses staged YAML files that don't parse.
- **What it stops:** broken workflows and configuration.
- **Why it exists:** a broken workflow can stop every required check.
- **Tested by:** untested.
- **How to adopt:** comes with `.pre-commit-config.yaml` (Phase 1); pin its `rev` (Phase 1, step 5).
- **Lowering it:** remove the hook; the gate refuses that, so it needs the owner's temporary bypass. The project gives up this catch.

### 16. Blocked names in files and paths
- **What it does:** normalises text and file paths, then compares every window of each listed length against the hashed list. The list stores each name as its length and SHA-256 hash, never the name itself. Each entry is blocked everywhere, or in file and folder names only. The list starts empty: add the project's names in Phase 1, step 4.
- **What it stops:** listed names, such as company names or the project's name in paths, entering the repository in any case or spelling.
- **Why it exists:** the stack is generic, and some names must never appear.
- **Tested by:** `tests/gate/test_security_gate.py` (the shared script, through the gate's tests).
- **How to adopt:** start the list fresh and add names with `python scripts/check_blocked_terms.py --add "<name>"` (Phase 1, step 4). In a public repository the list is public too, and its hashes aren't salted, so a short name can be recovered by hashing every word of its length. A name that mustn't become known can go in a list outside the repository, with `BLOCKED_TERMS_FILE` pointing the git hooks at it. That's a local check the owner keeps, not enforcement: the pull request gate checks only the repository's list, and the guard doesn't protect a file outside the repository, so keep that list where agents can't write.
- **Lowering it:** remove an entry. The gate refuses a removed entry (check 28), so it needs the owner's temporary bypass. The project gives up blocking that name.

### 17. Blocked names in the commit message
- **What it does:** the same check as 16, on the commit message's text.
- **What it stops:** a listed name in a commit message, which squash merges carry onto the default branch.
- **Why it exists:** commit messages are part of the permanent history.
- **Tested by:** `tests/gate/test_security_gate.py` (`CommitMessageHook`).
- **How to adopt:** comes with `.pre-commit-config.yaml`, installed with `-t commit-msg` (Phase 2, step 2).
- **Lowering it:** remove the hook; the gate refuses that, so it needs the owner's temporary bypass. The project gives up the commit-time catch; check 25 still checks every PR's commit messages.

### 18. App files under 500 lines
- **What it does:** refuses staged Python files under `src/` longer than 500 lines. Tests are exempt.
- **What it stops:** files that keep growing instead of being split by responsibility.
- **Why it exists:** long files are where wiring problems hide.
- **Tested by:** `tests/gate/test_security_gate.py` (`FileLengthHook`).
- **How to adopt:** comes with `.pre-commit-config.yaml` and `scripts/` (Phase 1, the Python toolchain row).
- **Lowering it:** raise `LIMIT` in `scripts/check_file_length.py` (an enforcement file; no gate refusal), or remove the hook (the gate refuses that). The project gives up the size limit on files.

### 19. Lint at commit
- **What it does:** runs ruff on staged Python files, with noqa comments ignored, using `[tool.ruff]` in `pyproject.toml`.
- **What it stops:** lint findings before they're committed.
- **Why it exists:** an early warning; check 32 is the same lint in CI.
- **Tested by:** untested.
- **How to adopt:** comes with `.pre-commit-config.yaml` (Phase 1, the Python toolchain row). Keep its `rev` the same as ruff in `uv.lock` (Phase 1, step 5).
- **Lowering it:** remove the hook; the gate refuses that, so it needs the owner's temporary bypass. The project gives up the early warning; check 32 still lints each PR.

### 20. Format at commit
- **What it does:** formats staged Python files with ruff, and stops the commit if anything changed.
- **What it stops:** unformatted code before it's committed.
- **Why it exists:** an early warning; check 33 is the same check in CI.
- **Tested by:** untested.
- **How to adopt:** comes with `.pre-commit-config.yaml` (Phase 1, the Python toolchain row).
- **Lowering it:** remove the hook; the gate refuses that, so it needs the owner's temporary bypass. The project gives up the early warning; check 33 still checks each PR.

### 21. Secret scan of the PR
- **What it does:** scans the files the PR adds or changes (renamed and copied ones at their new path) against the PR's baseline, with detect-secrets installed by hash from the default branch's list. A new secret can only arrive in those files; every tracked file is scanned on the default branch by check 44, so a PR's time doesn't grow with the repository.
- **What it stops:** a secret reaching the default branch, including one committed with the hooks skipped.
- **Why it exists:** local hooks can be skipped; this can't.
- **Tested by:** `tests/gate/test_secret_scan_step.py` runs the step's own script against a throwaway repository: changed, added and renamed files reach the scanner after `--` (so a file named like an option is scanned), deleted files and the baseline don't, and it refuses to pass without the base commit or on another checkout.
- **How to adopt:** comes with `.github/workflows/security-gate.yml` (Phase 1); proved in Phase 3.
- **Lowering it:** remove the job or its required status. The gate refuses a removed required check name and a weakened required job, so it needs the owner's temporary bypass. The project gives up the PR secret scan.

### 22. Commit checks replayed
- **What it does:** runs the whole pre-commit chain on the PR's files, with both the default branch's and the PR's config.
- **What it stops:** a hook skipped locally, or dropped by the PR's own config, reaching the default branch.
- **Why it exists:** commits made through a connector or the web editor run no hooks (setup prompt, decision 8).
- **Tested by:** untested. The gate's tests check the trusted workflow's rules.
- **How to adopt:** comes with `security-gate.yml` (Phase 1); proved in Phase 3.
- **Lowering it:** remove the job or its required status; the gate refuses that, so it needs the owner's temporary bypass. The project gives up enforcing the commit checks for changes that skip them.

### 23. Tests of the gate and the guard
- **What it does:** runs `tests/gate` and `tests/hooks` with the default branch's copy first, then the PR's, against the PR's code. `tests/gate` runs the gate against a fake GitHub API with known-good and known-bad PRs, and tests the commit-message and file-length hooks. `tests/hooks` runs the guard on commands it must block, allow, ask about or refuse. `tests/access` is reserved in CODEOWNERS and has no tests yet.
- **What it stops:** a PR that weakens the gate or the guard together with the tests that would catch it.
- **Why it exists:** a tested behaviour can be extended, not silently changed (setup prompt, decision 5).
- **Tested by:** it is the tests: 113 in `tests/gate` (98 for the gate, 10 for the GitHub settings script, 5 for the secret-scan step), 175 in `tests/hooks` (commands under [How to recount](#how-to-recount)).
- **How to adopt:** comes with `security-gate.yml` and `tests/` (Phase 1); run locally in Phase 2, step 1.
- **Lowering it:** remove the job or a test. The gate refuses a removed required check name, or a removed test name in any of the four test files (check 28), so it needs the owner's temporary bypass. The project gives up the proof that the gate and the guard still work.

### 24. Gate: no new suppressions
- **What it does:** looks for added lines, or added occurrences in files without a diff, that switch a check off. That covers zizmor ignores, secret-scan allowlist comments, noqa and type-ignore comments, type-checker directives, coverage exclusion comments, and test skips in pytest or unittest form. Matching is line by line.
- **What it stops:** reaching green by silencing a check instead of fixing the finding.
- **Why it exists:** false positives are restructured, never suppressed (setup prompt, decision 7).
- **Tested by:** `tests/gate/test_security_gate.py` (`Gate`, the suppression tests).
- **How to adopt:** comes with `scripts/` (Phase 1).
- **Lowering it:** change `scripts/security_gate.sh`; the gate's tests assert this, so it fails `selftest` and needs the owner's temporary bypass. The project gives up refusing suppressions.

### 25. Gate: no blocked names
- **What it does:** runs check 16 on the full content of every changed file, every file path, the PR title and description, and every commit message.
- **What it stops:** a listed name reaching the default branch by any route, hooks skipped or not.
- **Why it exists:** local hooks can be skipped; the gate can't.
- **Tested by:** `tests/gate/test_security_gate.py` (`Gate`, the blocked-name tests).
- **How to adopt:** comes with `scripts/`; the list is set in Phase 1, step 4.
- **Lowering it:** remove an entry from the list (check 28 refuses that) or change the gate (fails `selftest`). Either needs the owner's temporary bypass. The project gives up blocking that name.

### 26. Gate: risky workflow settings
- **What it does:** runs zizmor, offline and without the token, on every workflow the PR changes. zizmor is installed by hash from the default branch's list.
- **What it stops:** workflow settings that expose the token or run untrusted code unsafely.
- **Why it exists:** workflows run with repository access.
- **Tested by:** `tests/gate/test_security_gate.py` (`Gate`, the zizmor tests).
- **How to adopt:** comes with `scripts/` and `.github/requirements/gate-tools.txt` (Phase 1, step 5 pins it).
- **Lowering it:** change the gate (fails `selftest`) or add an ignore comment (refused by check 24). Either needs the owner's temporary bypass. The project gives up the workflow scan.

### 27. Gate: workflows can't weaken the required checks
- **What it does:** checks the trusted workflow for any change that could let a required check pass without really running:
  - a trigger other than `pull_request_target` with all its event types;
  - a required name produced by more or fewer than one job;
  - `if:`, `needs:` or `continue-on-error` on a required job or its steps;
  - write permissions;
  - a PR checkout that keeps credentials;
  - in a job that runs PR code, any expression outside a short safe list.

  In any other workflow, it refuses a job that could report a required name. Renaming or deleting the trusted workflow fails too.
- **What it stops:** a PR rewriting or imitating the checks that judge it.
- **Why it exists:** the required checks must come from the default branch's workflow (setup prompt, decision 2).
- **Tested by:** `tests/gate/test_security_gate.py` (`Gate`, the workflow tests).
- **How to adopt:** comes with `scripts/`; the required names come from `.claude/security-stack.json` (Phase 1, step 2).
- **Lowering it:** change `scripts/workflow_checks.py`; it fails `selftest`, so it needs the owner's temporary bypass. The project gives up the protection of the required checks' own definitions.

### 28. Gate: protected lists only grow
- **What it does:** compares eleven lists between the base and the PR, and fails if an entry is removed, changed, moved or deleted. The eleven lists:
  - the security-critical path patterns;
  - the blocked names;
  - the pre-commit hooks and their settings;
  - the guard's hook registrations, in `.claude/settings.json`;
  - the permission deny rules, in `.claude/settings.json`;
  - the guard's Copilot Chat registration, in `.github/hooks/agent-guard.json`: every setting of each hook (its commands, folder, timeout and environment), each event's names, and the file's top-level keys;
  - the required check names;
  - the gate's test names, in `tests/gate/test_security_gate.py`;
  - the guard's test names, in `tests/hooks/test_block_hook_bypass.py`;
  - the GitHub settings check's test names, in `tests/gate/test_github_settings.py`;
  - the secret-scan step's test names, in `tests/gate/test_secret_scan_step.py`.
- **What it stops:** weakening a check by shrinking what it covers.
- **Why it exists:** checks protect their own inputs (setup prompt, decision 6).
- **Tested by:** `tests/gate/test_security_gate.py` (`Gate`, the removal tests).
- **How to adopt:** comes with `scripts/` (Phase 1).
- **Lowering it:** removing an entry is refused by design, so it needs the owner's temporary bypass. The project gives up whatever that entry protected.

### 29. Gate: pinned tool lists are frozen
- **What it does:** allows only version and hash changes in `.github/requirements/*.txt`: no package added, removed or swapped, and no list added, renamed or deleted.
- **What it stops:** new code entering the trusted jobs.
- **Why it exists:** the trusted jobs install their tools before any PR file is on disk (setup prompt, decision 4).
- **Tested by:** `tests/gate/test_security_gate.py` (`Gate`, the pinned-package tests).
- **How to adopt:** comes with `scripts/` (Phase 1).
- **Lowering it:** adding a package is refused by design, so it needs the owner's temporary bypass. The project gives up the frozen tool set.

### 30. Gate: secret scanning only gets stricter
- **What it does:** compares the PR's `.secrets.baseline` with the base's. It fails on a detector removed or changed, a new custom filter or filter pattern, or a new allowlisted finding, compared by file, detector and hash.
- **What it stops:** switching secret scanning off through its own configuration.
- **Why it exists:** the baseline can disable scanning as surely as a missing hook.
- **Tested by:** `tests/gate/test_security_gate.py` (`Gate`, the baseline tests).
- **How to adopt:** comes with `scripts/` (Phase 1); the baseline is generated in Phase 1, step 6.
- **Lowering it:** an allowlist entry is refused by design, so it needs the owner's temporary bypass. The project gives up scanning for that finding.

### 31. Gate: security-critical paths reported
- **What it does:** lists the changed files that match the patterns in `.github/security-critical-paths.txt`, and those without a dedicated automated check yet, in the job summary.
- **What it stops:** nothing; it tells the reviewer where to look.
- **Why it exists:** to show which areas still wait for their own tests.
- **Tested by:** untested.
- **How to adopt:** comes with `scripts/`; set the patterns (Phase 1).
- **Lowering it:** removing a pattern is refused by check 28, so it needs the owner's temporary bypass. The project gives up the report for that path.

### 32. Lint
- **What it does:** runs `ruff check --ignore-noqa` on the app code. The rules (`[tool.ruff]` in `pyproject.toml`) include:
  - complexity up to 10;
  - at most 5 arguments, 12 branches and 50 statements;
  - a ban on importing `unittest.mock`.

  Tests are exempt from the size limits. The security tooling (`.claude`, `scripts`, `tests/gate`, `tests/hooks`) and Markdown are excluded.
- **What it stops:** code that is hard to read, change and test, and patching in tests instead of fakes.
- **Why it exists:** Python won't enforce these limits itself.
- **Tested by:** untested. It was proved on GitHub with a staging run of the job before it merged.
- **How to adopt:** copy the Python toolchain files and lock the dev group (Phase 1, the Python toolchain row and step 5), then prove it (Phase 2, step 6).
- **Lowering it:** change the rules in `pyproject.toml` or the script. Both are enforcement files, so the guard asks, and the gate doesn't refuse either. The two take effect differently:
  - **The script** changes only after it merges, because the check runs the default branch's copy.
  - **`pyproject.toml`** changes apply in the same pull request, because the tools read the PR's own settings. That's why it's an enforcement file.

  The project gives up the limits it loosens.

### 33. Format
- **What it does:** runs `ruff format --check`.
- **What it stops:** unformatted code.
- **Why it exists:** one format means diffs show only real changes.
- **Tested by:** untested.
- **How to adopt:** as for check 32.
- **Lowering it:** remove it from `scripts/check_python.sh` (the guard asks; the gate doesn't refuse). The project gives up consistent formatting.

### 34. Types
- **What it does:** runs basedpyright with pyright's settings in `pyproject.toml`: strict for `src/`, standard for tests, with type-ignore comments disabled. Pylance in the editor reads the same settings.
- **What it stops:** type errors, and silencing them.
- **Why it exists:** Python checks types only when a tool does.
- **Tested by:** untested.
- **How to adopt:** as for check 32.
- **Lowering it:** change `[tool.pyright]` (the guard asks; the gate doesn't refuse). The project gives up the type safety it loosens.

### 35. Tests
- **What it does:** runs pytest over `tests/unit`, `tests/behaviour`, `tests/events`, `tests/integration` and `tests/access`, whichever exist. It runs in random order, with warnings as errors, strict markers and configuration, strict expected failures and branch coverage. A run with no tests fails.
- **What it stops:** a change that breaks a test, or order-dependent tests.
- **Why it exists:** tests only protect what they're run on.
- **Tested by:** untested.
- **How to adopt:** as for check 32; the folders follow `.claude/skills/testing/SKILL.md`.
- **Lowering it:** change `[tool.pytest.ini_options]` (the guard asks; the gate doesn't refuse). The project gives up what it removes, such as random order.

### 36. Skipped tests fail the run
- **What it does:** at the end of each pytest run, fails the run if any test was skipped or expected to fail, however the skip was written.
- **What it stops:** a test that doesn't run passing as green.
- **Why it exists:** check 24 matches skips line by line; this catches every form at run time.
- **Tested by:** untested. It was proved on GitHub with a staging run.
- **How to adopt:** copy `tests/conftest.py` with the Python toolchain (Phase 1).
- **Lowering it:** edit `tests/conftest.py` (the guard asks; the gate doesn't refuse). The project gives up counting skipped tests as failures.

### 37. Changed-line coverage
- **What it does:** runs diff-cover on the coverage report: at least 80% of the changed lines must be covered. Coverage counts branches, and exclusion comments count for nothing.
- **What it stops:** new code arriving without tests.
- **Why it exists:** a threshold on changed lines, not a project-wide ratchet, keeps new code tested without old code blocking it.
- **Tested by:** untested.
- **How to adopt:** as for check 32.
- **Lowering it:** change `--fail-under` in `scripts/check_python.sh` or `[tool.coverage]` (the guard asks; the gate doesn't refuse). The project gives up the coverage it no longer requires.

### 38. Dependencies
- **What it does:** runs deptry on `src/`.
- **What it stops:** undeclared imports and unused declared packages.
- **Why it exists:** declared packages should match what the code uses.
- **Tested by:** untested.
- **How to adopt:** as for check 32.
- **Lowering it:** change `[tool.deptry]` or the script (the guard asks; the gate doesn't refuse). The project gives up the dependency hygiene check.

### 39. Dead code
- **What it does:** runs vulture on `src/` at 60% confidence and above. Names called from outside `src/`, such as `build_app`, are listed in `[tool.vulture]`.
- **What it stops:** code nothing calls, including code written but never wired in.
- **Why it exists:** unwired code is where wiring problems hide.
- **Tested by:** untested. It was proved on GitHub with a staging run.
- **How to adopt:** as for check 32.
- **Lowering it:** raise `min_confidence` or add names to `[tool.vulture]` (the guard asks; the gate doesn't refuse). The project gives up finding that dead code.

### 40. Known vulnerabilities
- **What it does:** exports the PR's `uv.lock` and runs pip-audit on it, hash-checked.
- **What it stops:** merging a package with a known vulnerability.
- **Why it exists:** vulnerable dependencies are the most common way in.
- **Tested by:** untested.
- **How to adopt:** as for check 32.
- **Lowering it:** remove it from the script, or ignore an advisory (the guard asks; the gate doesn't refuse). The project gives up the per-PR audit; check 45 still audits the default branch daily.

### 41. Hash-checked installs for the Python checks
- **What it does:** in the `python` job:
  - checks that the PR checkout is the PR's commit;
  - installs the PR's app dependencies from its `uv.lock`, then the default branch's tools over them, all by hash;
  - installs uv through an action pinned to a commit SHA, which verifies uv's checksum.
- **What it stops:** tampered packages; a lockfile out of date with `pyproject.toml`; a PR dependency named like a tool replacing it; checking a different commit.
- **Why it exists:** the check must judge the PR's code with the default branch's tools (setup prompt, decision 4).
- **Tested by:** untested. It was proved on GitHub with a staging run.
- **How to adopt:** comes with `security-gate.yml`, with its inputs `pyproject.toml` and `uv.lock` (Phase 1, the pinned tools and Python toolchain rows).
- **Lowering it:** change the job (an enforcement file; the guard asks). The gate checks the job's shape but not its install steps. The project gives up the integrity of the tools that judge the code.

### 42. Hash-pinned tools for the security jobs
- **What it does:** the security jobs install their tools with `pip install --require-hashes` from `.github/requirements/*.txt`, read from the default branch before any PR file is on disk.
- **What it stops:** a tampered or substituted tool running in a trusted job.
- **Why it exists:** setup prompt, decision 4.
- **Tested by:** untested. Check 29 guards the lists.
- **How to adopt:** re-pin current versions and hashes rather than copying old pins (Phase 1, step 5).
- **Lowering it:** removing `--require-hashes` from a workflow is an enforcement change the guard asks about (no gate refusal). Changing the lists is refused by check 29. The project gives up tool integrity.

### 43. Seven-day cooldown on package versions
- **What it does:** `exclude-newer = "7 days"` under `[tool.uv]` means uv never resolves a version uploaded in the last seven days. CI's `uv export --locked` fails if `uv.lock` doesn't match `pyproject.toml`.
- **What it stops:** adopting a hijacked release before it's caught.
- **Why it exists:** malicious releases are usually found within days.
- **Tested by:** untested.
- **How to adopt:** set it in `pyproject.toml` (Phase 1, the Python toolchain row).
- **Lowering it:** shorten or remove it, or exempt one package with `exclude-newer-package` for an urgent fix (`pyproject.toml`; the guard asks; the gate doesn't refuse). The project gives up the waiting period for what it exempts.

### 44. Secret scan of main
- **What it does:** scans every tracked file on the default branch after each merge and daily, with detect-secrets installed by hash. It's the full-tree scan: pull requests scan only the files they change (check 21).
- **What it stops:** nothing directly; a failed run shows a secret that newer patterns detect.
- **Why it exists:** detectors improve, and old commits don't get re-checked otherwise.
- **Tested by:** untested.
- **How to adopt:** comes with `.github/workflows/security.yml` (Phase 1).
- **Lowering it:** remove the job (the guard asks; the gate doesn't refuse it, since it isn't a required check). The project gives up the daily scan.

### 45. Vulnerability audit of main
- **What it does:** audits every package in the default branch's `uv.lock` after each merge and daily, with pip-audit.
- **What it stops:** nothing directly; a failed run shows a newly disclosed vulnerability.
- **Why it exists:** advisories are published after packages are merged.
- **Tested by:** untested.
- **How to adopt:** comes with `security.yml`, and needs `uv.lock` (Phase 1, the Python toolchain row).
- **Lowering it:** remove the job (the guard asks; no gate refusal). The project gives up the daily audit.

### 46. Keyless Azure sign-in proof
- **What it does:** a workflow run by hand. It signs in to Azure from the deploy environment through the federated credential, and shows the app resource group.
- **What it stops:** nothing directly; a failure shows the sign-in is broken before a deploy needs it.
- **Why it exists:** keyless sign-in has several moving parts: the environment, the variables, the identity and the subject.
- **Tested by:** untested. Run it to check.
- **How to adopt:** comes with `.github/workflows/azure-login-check.yml`; set the environment name if it isn't `dev` (Phase 1, step 3), and run it in Phase 7, step 3.
- **Lowering it:** delete the workflow (the guard asks; no gate refusal). The project gives up the one-click proof.

### 47. Required status checks
- **What it does:** the ruleset requires every check named in `.claude/security-stack.json` to pass before merging into the default branch, on a branch that is up to date with it. There are 5 today.
- **What it stops:** merging a change the checks haven't passed.
- **Why it exists:** the checks only protect the default branch if they're required.
- **Tested by:** untested. Read back with `gh api` (Phase 4, step 4).
- **How to adopt:** turn on in Phase 4, step 1, after the checks have run once. A required check that can't run blocks every PR.
- **Lowering it:** remove a check from the ruleset (the guard asks). Removing it from the required check names too is refused by check 28, so it needs the owner's temporary bypass. The project gives up that check's hold on merges.

### 48. Pull request required, squash only
- **What it does:** every change to the default branch goes through a pull request, merged by squash.
- **What it stops:** direct pushes, merge commits and rebase merges.
- **Why it exists:** the pull request is the one checkpoint for every change.
- **Tested by:** untested. Read back with `gh api`.
- **How to adopt:** turn on in Phase 4, step 1.
- **Lowering it:** change the ruleset (the guard asks). The project gives up the single checkpoint.

### 49. Code-owner review for other authors
- **What it does:** a PR that changes a file listed in CODEOWNERS waits for a code owner's approval, and a new push dismisses earlier approvals. With zero required approvals, it doesn't hold a code owner's own PR (verified on this repository).
- **What it stops:** enforcement changes by other authors, such as Dependabot, merging without a code owner's approval. Here, the agent gives that approval through the owner's account for the Dependabot bumps check 5 lets through.
- **Why it exists:** GitHub's own hold on enforcement changes.
- **Tested by:** untested. Verified with a probe PR during setup.
- **How to adopt:** turn on in Phase 4, step 1.
- **Lowering it:** change the ruleset (the guard asks). The project gives up the hold on other authors' enforcement PRs.

### 50. Extra approval for unattributed changes
- **What it does:** a PR with a commit whose author isn't linked to a GitHub account needs one more approval.
- **What it stops:** changes whose author can't be traced.
- **Why it exists:** every commit should be attributable.
- **Tested by:** untested.
- **How to adopt:** turn on with the ruleset (Phase 4, step 1, whose payload sets it). The settings script (check 66) checks it, and raises it with `--apply`.
- **Lowering it:** change the ruleset (the guard asks). The project gives up the extra approval.

### 51. No deletion or force push
- **What it does:** the default branch can't be deleted or have its history rewritten.
- **What it stops:** losing or rewriting what has merged.
- **Why it exists:** history is the record of what passed the checks.
- **Tested by:** untested.
- **How to adopt:** turn on with the ruleset (Phase 4, step 1).
- **Lowering it:** change the ruleset (the guard asks). The project gives up an immutable history.

### 52. No one bypasses the ruleset
- **What it does:** the ruleset is active, and its bypass list is empty, so the rules bind everyone, admins included.
- **What it stops:** anyone merging past a failing check.
- **Why it exists:** a rule with a standing bypass is a suggestion.
- **Tested by:** untested. Read back with `gh api`.
- **How to adopt:** turn on with the ruleset (Phase 4, step 1).
- **Lowering it:** add a bypass actor (the guard asks). The owner does this only temporarily, to merge a lowering the gate refuses by design ([Lowering a protection](#lowering-a-protection)). The project gives up rules that bind everyone.

### 53. Enforcement files listed
- **What it does:** `.github/CODEOWNERS` lists the enforcement files: the hooks, the guard, the gates and what they read, their tests, the access tests, the files that decide how tests run, the agent rules files (`AGENTS.md`, and `CLAUDE.md`, which imports it), the instructions agents are handed (the Claude Code skills in `.claude/skills/`, the setup prompt and the prompt templates in `docs/prompts/`), the audit records (this inventory, the control mapping and the AI risk mapping), and VS Code's workspace settings and tasks (`.vscode/` and workspace files). The guard reads it (checks 3 and 68), and so does GitHub's code-owner review (check 49). It has 27 entries.
- **What it stops:** enforcement files changing without the owner.
- **Why it exists:** it defines what the one rule protects.
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`OwnerApproval`).
- **How to adopt:** copy it and set the owner's handle (Phase 1, step 3).
- **Lowering it:** remove an entry (the guard asks; the gate doesn't refuse it). The project gives up protecting that file.

### 54. Read-only workflow token; Actions can't approve PRs
- **What it does:** workflow tokens are read-only unless a job asks for more, and workflows can't approve pull requests.
- **What it stops:** a workflow writing to the repository or approving a PR by default.
- **Why it exists:** a compromised step should hold as little as possible.
- **Tested by:** untested. Read back with `gh api` (Phase 4, step 4).
- **How to adopt:** turn on in Phase 4, step 2.
- **Lowering it:** change the setting (the guard asks). The project gives up the least-privilege default.

### 55. Actions pinned to a full commit SHA
- **What it does:** GitHub refuses to run a workflow that uses an action by tag or branch. All 21 action references here are pinned to a commit SHA.
- **What it stops:** a moved tag swapping an action's code.
- **Why it exists:** tags can be moved; commit SHAs can't.
- **Tested by:** untested. zizmor (check 26) flags unpinned actions too.
- **How to adopt:** turn on in Phase 4, step 2; pin current SHAs (Phase 1, step 5).
- **Lowering it:** change the setting (the guard asks). The project gives up immutable actions.

### 56. Dependabot alerts
- **What it does:** GitHub alerts on dependencies with known advisories.
- **What it stops:** vulnerable dependencies going unnoticed.
- **Why it exists:** advisories keep coming after merge.
- **Tested by:** untested.
- **How to adopt:** turn on in Phase 4, step 3.
- **Lowering it:** turn it off (the guard asks). The project gives up the alerts.

### 57. Dependabot security updates
- **What it does:** GitHub opens a fix PR when an alert has a patched version.
- **What it stops:** known vulnerabilities staying unpatched.
- **Why it exists:** the fix arrives as an ordinary PR through every check.
- **Tested by:** untested.
- **How to adopt:** turn on in Phase 4, step 3.
- **Lowering it:** turn it off (the guard asks). The project gives up automatic fix PRs.

### 58. Dependabot version updates
- **What it does:** weekly update PRs for the action pins and for the Python packages in `uv.lock`. A cooldown holds each new version for seven days, like check 43.
- **What it stops:** pins going stale, and a hijacked release arriving before it's caught.
- **Why it exists:** old pins collect known issues, and malicious releases are usually found within days.
- **Tested by:** untested.
- **How to adopt:** copy `.github/dependabot.yml` (Phase 1, repository basics).
- **Lowering it:** remove an ecosystem or shorten its cooldown (the guard asks; no gate refusal). The project gives up those updates, or the wait before them.

### 59. Deploy environment limited to the default branch
- **What it does:** the deploy environment's branch policy allows only the default branch. It holds the sign-in variables, which are identifiers, not secrets.
- **What it stops:** a job on another branch signing in to Azure as the deploy identity.
- **Why it exists:** the federated credential trusts the environment (check 65).
- **Tested by:** untested.
- **How to adopt:** turn on in Phase 7, steps 1 and 2.
- **Lowering it:** change the policy (the guard asks). The project gives up keeping deploys to the default branch.

### 60. Allowed locations
- **What it does:** an Azure Policy assignment at subscription scope. Its effect is the definition's default, Deny, for any resource outside the project's region.
- **What it stops:** resources created in other regions.
- **Why it exists:** keeps data and spend in one region.
- **Tested by:** untested. Read back with `az policy assignment list`.
- **How to adopt:** turn on in Phase 6, step 3.
- **Lowering it:** change or remove the assignment. From the terminal, the guard asks (check 8); in the portal, it's the owner's action. It isn't an enforcement file under the one rule. The project gives up the region lock for resources.

### 61. Allowed locations for resource groups
- **What it does:** as check 60, for resource groups.
- **What it stops:** resource groups created in other regions.
- **Why it exists:** as check 60.
- **Tested by:** untested.
- **How to adopt:** turn on in Phase 6, step 3.
- **Lowering it:** as check 60. The project gives up the region lock for resource groups.

### 62. Cloud security benchmark audit
- **What it does:** the default policy initiative that comes with Defender for Cloud's free plan. It audits the subscription against the cloud security benchmark.
- **What it stops:** nothing; it reports findings.
- **Why it exists:** visibility of misconfigurations.
- **Tested by:** untested.
- **How to adopt:** turn on Defender for Cloud's free plan, then confirm the assignment (Phase 6, step 8).
- **Lowering it:** remove the assignment (from the terminal, the guard asks). The project gives up the audit.

### 63. Monthly budget alerts
- **What it does:** a monthly cost budget that alerts the subscription's Owner role at 50%, 80% and 100% of actual spend and at a 100% forecast. It doesn't stop spending.
- **What it stops:** spending going unnoticed.
- **Why it exists:** mistakes in the cloud cost money quickly.
- **Tested by:** untested. Read back with `az consumption budget list`.
- **How to adopt:** turn on in Phase 6, step 7.
- **Lowering it:** raise the amount or remove it (from the terminal, the guard asks). The project gives up the alerts.

### 64. Deploy identity limited to the app resource group
- **What it does:** the deploy identity holds one role assignment: Contributor on the app resource group. It lives in a separate resource group.
- **What it stops:** a deploy reaching anything else, or changing its own permissions.
- **Why it exists:** setup prompt, decision 9.
- **Tested by:** untested. Read back with `az role assignment list`.
- **How to adopt:** turn on in Phase 6, steps 4 and 6.
- **Lowering it:** widen the role or scope (from the terminal, the guard asks). The project gives up the deploy's containment.

### 65. Sign-in only from the deploy environment, with no secret
- **What it does:** one federated credential on the deploy identity trusts GitHub's token issuer for this repository's deploy environment only. No secret exists.
- **What it stops:** other workflows, branches or repositories signing in as the deploy identity; stored credentials leaking.
- **Why it exists:** setup prompt, decision 9.
- **Tested by:** check 46.
- **How to adopt:** turn on in Phase 6, step 5, with the subject exactly as GitHub presents it.
- **Lowering it:** widen the subject or add a secret (from the terminal, the guard asks). The project gives up keyless, environment-bound sign-in.

### 66. GitHub settings at the baseline
- **What it does:** `python scripts/github_settings.py` reads the ruleset on the default branch, the Actions permissions, Dependabot and the deploy environment, and compares each with the baseline (setup prompt, Phase 4), using the values in `.claude/security-stack.json`. A stricter setting passes. `--apply` raises what falls short and never lowers a stricter setting: it keeps required approvals, extra required checks, extra rules and a narrower list of allowed actions.
- **What it stops:** a setting changed in the browser, or never set, going unnoticed.
- **Why it exists:** repository settings don't pass through a pull request, so the required checks can't see them change. It isn't scheduled, because reading the ruleset needs an admin sign-in, which CI doesn't hold.
- **Tested by:** `tests/gate/test_github_settings.py`, against a fake GitHub API.
- **How to adopt:** comes with `scripts/` (Phase 1); run it in Phase 4, and whenever the settings may have changed. It needs `gh` signed in as a repository admin.
- **Lowering it:** delete the script (the guard asks; no gate refusal). The project gives up the one-command check of its GitHub settings.

### 67. Review threads resolved before merging
- **What it does:** the ruleset's pull request rule requires every review thread to be resolved before a PR merges, Copilot's included.
- **What it stops:** merging past a review finding nobody answered.
- **Why it exists:** ordinary pull requests merge on green without a person's review, so bot reviews do that job; this makes answering them part of merging.
- **Tested by:** untested. Read back with `gh api` (How to recount).
- **How to adopt:** turn on with the ruleset (Phase 4, step 1, whose payload sets it). The settings script (check 66) checks it, and raises it with `--apply`.
- **Lowering it:** turn it off (the guard asks). The project gives up the hold on unanswered review threads.

### 68. The guard in Copilot Chat
- **What it does:** GitHub Copilot Chat's agent in VS Code runs the guard before each tool call, from `.github/hooks/agent-guard.json`. The guard checks Copilot's tools as the Claude Code tools that do the same: the terminal (`run_in_terminal`, checked as bash and as PowerShell), file edits (`create_file`, `replace_string_in_file` and the rest), patches (`apply_patch`, by the files the patch names), and connectors (`mcp_…`). It knows each tool by its name and by the ID it's registered under (`copilot_createFile`), as Copilot Chat's open-source code declares them. Any other tool is judged by the files and commands its input names. A task Copilot adds (`create_and_run_task`) edits `.vscode/tasks.json`, an enforcement file. VS Code's user settings, each profile's included, and its workspace files (`*.code-workspace`), wherever they are, are enforcement files too: `chat.useHooks` there switches the hooks off.
- **What it stops:** what checks 1 to 8, 71 and 72 stop, from Copilot Chat, including its file reads (`read_file` and the other read tools) of the owner's sign-ins and its web fetches (`fetch_webpage`) to hosts off the allowlist. Copilot's auto-approve modes skip prompts, so where the guard would ask the owner it refuses; the owner makes those changes in Claude Code or by hand. It also refuses what it can't read: code the guard can't see, from an editor command (`run_vscode_command`, which can type into a terminal) or an extension install (`install_extension`), and a terminal call, edit or patch that names no command or file.
- **Why it exists:** without it, Copilot Chat in the same clone could change enforcement, or skip the git hooks, with nothing to stop it before the pull request.
- **Where it doesn't reach:** the registration's per-platform commands run the guard; its `command` field, which the Copilot CLI and the Copilot cloud agent read, runs `exit 0`. Neither is covered, nor is VS Code's Copilot session target, which uses the Copilot CLI's hooks. Like `python script.py` in Claude Code, `runTests`, `run_notebook_cell` and `run_task` run the project's own code, which the guard doesn't read: it can't see inside a script file the agent writes and then runs, and the merge check still stops an enforcement change at the pull request. A tool VS Code runs without a hook, or names differently in a later version, isn't checked: re-run the owner's two-prompt test after VS Code updates (setup prompt, Phase 2, step 5).
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`CopilotChat`, and `CopilotRegistration`, which runs the registration's command for the platform through the shell VS Code uses, and proves a guard that can't start blocks). Copilot Chat itself: the owner's two-prompt test (setup prompt, Phase 2, step 5).
- **How to adopt:** copy `.github/hooks/agent-guard.json` with the guard (Phase 1, step 1). VS Code runs it with `chat.useHooks` on, its default, in a trusted workspace. Leave `chat.useClaudeHooks` off, its default.
- **Lowering it:** remove the registration or change it. The gate refuses both (check 28), so it needs the owner's temporary bypass. The project gives up the guard in Copilot Chat.

### 69. Gate: hook pins are full commit hashes
- **What it does:** when a PR changes `.pre-commit-config.yaml`, reads the PR's copy, and fails if any hook repository other than `local` and `meta` has a `rev` that isn't a full 40-character commit hash. The message names each repository and its rev. A copy that can't be fetched or parsed stops the gate.
- **What it stops:** a hook pinned by a tag, a branch, a short hash, or not at all.
- **Why it exists:** a full hash names one commit; anything else is looked up by name, so the repository's owner could point it at other code after it was reviewed.
- **Tested by:** `tests/gate/test_security_gate.py` (`test_precommit_hook_pinned_by_name_fails`, `test_precommit_local_and_meta_hooks_without_rev_pass`, `test_precommit_new_config_invalid_yaml_fails_closed`).
- **How to adopt:** comes with `scripts/` (Phase 1). `pre-commit autoupdate --freeze` writes full hashes (Phase 1, step 5), so ordinary bumps pass.
- **Lowering it:** change the gate. `selftest` fails on the changed behaviour, so it needs the owner's temporary bypass. The project gives up refusing hook pins that can be moved.

### 70. Sign-in files denied to Claude Code
- **What it does:** deny rules in `.claude/settings.json` stop Claude Code reading `~/.azure`, `~/.ssh`, `~/.config/gh`, `~/.aws` and `~/.docker/config.json`, and `.env` files at any depth, with `.env.example` carved out. Claude Code applies them to its file-reading tools and to the shell reads it recognizes, in every permission mode.
- **What it stops:** the agent reading the owner's sign-ins, bypass-permissions mode included.
- **Why it exists:** those files let whoever reads them act as the owner, so nothing the agent reads should be able to steer it there.
- **Tested by:** fresh headless sessions (`claude -p` with only the Read tool and only the project's settings), in default and bypass-permissions modes: a probe `.env` and paths under `~/.ssh` and `~/.azure` were denied, `.env.example` was read, and a copy without the rules read the probe. The gate keeps the list from shrinking (check 28; `test_permission_deny_rule_removed_fails`).
- **How to adopt:** comes with `.claude/settings.json` (Phase 1, step 1). Add a rule for any other sign-in store the project's tools keep.
- **Lowering it:** remove a rule. The gate refuses it (check 28), so it needs the owner's temporary bypass. The project gives up keeping Claude Code's own reads away from that sign-in.

### 71. Sign-in reads and token printing refused
- **What it does:** the guard refuses a command that reads or copies one of check 70's files, in bash or PowerShell and in the forms it can resolve (`~`, `$HOME`, `%USERPROFILE%`, `$env:USERPROFILE`, a relative `.env`, any letter case, a file read in with `@`); inline code or a script on standard input that names one; an edit to one (writing a `.env` file is allowed); a Copilot Chat search scoped to one, or through ignored files that could hold one; and a command that prints a token: `gh auth token`, `gh auth status --show-token`, `az account get-access-token`, and the AWS CLI's `configure export-credentials`, its `configure get` of a key or token, and `sts get-session-token`. A move (`mv .env x`) is refused too: only a real write may name a `.env` file. It refuses in every mode, so there's nothing to approve; the message tells the agent to recommend a way that doesn't expose the secret.
- **What it stops:** a command reaching the owner's sign-ins where check 70's rules may not.
- **Why it exists:** deny rules cover Claude Code's own reads, and a command can reach the same files another way.
- **Where it doesn't reach:** a script file the agent writes and then runs, and code that runs as the owner outside the agent, such as a package's install script.
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`CredentialsAndOutbound`; `AzureCommands.test_printing_a_token_is_refused`).
- **How to adopt:** comes with the guard (Phase 1, step 1).
- **Lowering it:** change the guard. `selftest` fails on the changed behaviour, so it needs the owner's temporary bypass. The project gives up refusing commands that expose the owner's sign-ins.

### 72. Outbound data asks the owner
- **What it does:** the guard asks the owner before a `curl`, `wget`, `Invoke-WebRequest` or `Invoke-RestMethod` request that sends data, uploads a file, reads its request or a header or cookie from a file, sends it through another address, or uses a method other than GET or HEAD, whatever the host; any such request, or a Claude Code web fetch, to a host that isn't on the allowlist (`network.allowed_hosts` in `.claude/security-stack.json`) or whose host it can't read; `az rest` to a host outside Azure and the allowlist; `gh gist create` or `edit`; `git push` to a remote other than `origin`; `git remote add`, `set-url` and `rename`, and settings, saved, per command or moved by a section rename, that change where a remote points or where a push goes; `scp`, `sftp`, `ssh`, `nc` and `rsync` to another computer; and inline code that opens network connections. In modes that can't ask, it refuses. Each stop tells the agent to recommend an allowlisted source or adding the host, which the owner approves.
- **What it stops:** repository content or secrets leaving for somewhere the owner didn't choose.
- **Why it exists:** text the agent reads can be written to look like instructions, so the guard, not the agent, decides where data may go.
- **Where it doesn't reach:** a script file the agent writes and then runs, and programs other than these that connect out.
- **Tested by:** `tests/hooks/test_block_hook_bypass.py` (`CredentialsAndOutbound`; `AzureCommands.test_az_rest_to_another_host_needs_the_owner`).
- **How to adopt:** comes with the guard and `.claude/settings.json` (Phase 1, step 1); set the allowlist in the stack file (Phase 1, step 2).
- **Lowering it:** adding a host to the allowlist is an ordinary change the guard asks the owner about, not a lowering. Removing the rule means changing the guard: `selftest` fails on the changed behaviour, so it needs the owner's temporary bypass. The project gives up choosing where the agent may send data.

## Lowering a protection

Every check starts at its baseline setting. Lowering one is allowed, but only as the owner's deliberate, recorded decision. This follows the setup prompt's "Rules for the agent" (rule 2) and "The owner's approval":

- **The owner decides.** An agent never lowers a check to get a change through. When a check blocks something, the agent fixes the cause, or stops and tells the owner.
- **One pull request per lowering,** doing nothing else, with the reason in its description.
- **The guard asks the owner in the terminal,** in the default permission mode. Some changes the gate refuses by design: a protected list shrinks, an allowlist entry or a pinned tool package is added, or a tested behaviour changes together with its test. For those, the owner adds the repository admin role to the ruleset's bypass list, merges, removes it again, and records why in the pull request.
- **In the same pull request,** update the check's row and section here, and add a line to [Lowered from the baseline](#lowered-from-the-baseline).

## Lowered from the baseline

Nothing yet: the baseline starts locked down. Each lowering adds a row.

| Check | What changed | Why | PR |
| --- | --- | --- | --- |

## Summary

All checks: **72** (`grep -cE '^[|] [0-9]+ [|]' docs/checks-inventory.md`).

By where it runs (`awk -F' [|] ' '/^[|] [0-9]+ [|]/ {print $3}' docs/checks-inventory.md | sort | uniq -c`):

```text
      6 Azure setting
      1 By hand
     24 CI on PR
      2 CI scheduled
      1 CI, run by hand
     12 Claude Code hook
      1 Claude Code setting
      1 Copilot Chat hook (VS Code)
     14 GitHub setting
     10 git commit
```

By type (`awk -F' [|] ' '/^[|] [0-9]+ [|]/ {print $8}' docs/checks-inventory.md | sed -E 's/^Our code, running .*/Our code, running a tool/; s/^Third-party tool: .*/Third-party tool/' | sort | uniq -c`):

```text
     25 Our code
     18 Our code, running a tool
      6 Platform setting: Azure
     14 Platform setting: GitHub
      9 Third-party tool
```

By how it's adopted (`awk -F' [|] ' '/^[|] [0-9]+ [|]/ {print $9}' docs/checks-inventory.md | sed -E 's/ [(].*//' | sort | uniq -c`):

```text
      8 Copy and set values
     28 Copy as is
     18 Install and pin
     18 Turn on
```

None is "Write your own".

By whether it blocks (`awk -F' [|] ' '/^[|] [0-9]+ [|]/ {print $6}' docs/checks-inventory.md | sed -E 's/ [(].*//' | sort | uniq -c`):

```text
     61 Blocks
     11 Warns
```

## How to recount

Run these from the repository root. They read the source and the live settings, so a count that no longer matches means this document needs updating. `$repo` is `jq -r .github.repository .claude/security-stack.json`; the Azure names come from the same file.

Set these first:

```bash
repo=$(jq -r .github.repository .claude/security-stack.json)
env=$(jq -r .github.deploy_environment .claude/security-stack.json)
id=$(jq -r .azure.deploy_identity.name .claude/security-stack.json)
ci=$(jq -r .azure.resource_groups.ci .claude/security-stack.json)
```

In the repository:
- Claude Code hook registrations, **6**: `jq '[.hooks[][] | .hooks[]] | length' .claude/settings.json`
- Copilot Chat hook registrations, **1**: `jq '[.hooks[][]] | length' .github/hooks/agent-guard.json`
- pre-commit hooks, **10**: `grep -cE '^\s+- id:' .pre-commit-config.yaml`
- Workflow jobs, **1, 5 and 2** (azure-login-check, security-gate, security): `for f in .github/workflows/*.yml; do printf '%s ' "$f"; awk '/^jobs:/{f=1;next} f && /^  [A-Za-z0-9_-]+:$/{n++} END{print n}' "$f"; done`
- Sections of the security gate, **6**: `grep -c '^# --- [0-9]\.' scripts/security_gate.sh`
- Protected lists, **11**: `grep -c '^protect ' scripts/security_gate.sh`
- Checks in the Python script, **8**: `grep -cE '^\s*check "' scripts/check_python.sh`
- Gate tests, **98**: `grep -cE '^\s*def test_' tests/gate/test_security_gate.py`
- GitHub settings script tests, **10**: `grep -cE '^\s*def test_' tests/gate/test_github_settings.py`
- Secret-scan step tests, **5**: `grep -cE '^\s*def test_' tests/gate/test_secret_scan_step.py`
- Guard tests, **175**: `grep -cE '^\s*def test_' tests/hooks/test_block_hook_bypass.py`
- Permission deny rules, **8**: `jq '.permissions.deny | length' .claude/settings.json`
- Hosts on the network allowlist, **8**: `jq '.network.allowed_hosts | length' .claude/security-stack.json`
- CODEOWNERS entries, **27**: `grep -cvE '^\s*(#|$)' .github/CODEOWNERS`
- Blocked names, **0**, of them in paths only **0**: `grep -cvE '^\s*(#|$)' .github/blocked-terms.txt` and `grep -cE ' paths$' .github/blocked-terms.txt`
- Packages in the hash-pinned tool lists, **2, 10 and 7** (gate tools, pre-commit, secret scan): `for f in .github/requirements/*.txt; do printf '%s ' "$f"; grep -cE '^[A-Za-z0-9]' "$f"; done`
- Action references, **21**, all pinned to a commit SHA: `grep -hoE 'uses: [^ ]+' .github/workflows/*.yml | wc -l` and `grep -hoE 'uses: [^@ ]+@[0-9a-f]{40}' .github/workflows/*.yml | wc -l`
- Packages in `uv.lock`, **49**: `grep -c '^name = ' uv.lock`

On GitHub (read only):
- Required status checks, **5**: `gh api "repos/$repo/rulesets" --jq '.[].id'`, then `gh api "repos/$repo/rulesets/<id>" --jq '[.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context]'`
- Ruleset enforcement and bypass list, **active and empty**: `gh api "repos/$repo/rulesets/<id>" --jq '{enforcement, bypass_actors}'`
- Review threads resolved before merging, **on**: `gh api "repos/$repo/rulesets/<id>" --jq '.rules[] | select(.type=="pull_request") | .parameters.required_review_thread_resolution'`
- Actions permissions, **SHA pinning required, read-only token, no PR approvals**: `gh api "repos/$repo/actions/permissions"` and `gh api "repos/$repo/actions/permissions/workflow"`
- Dependabot security updates, **enabled**: `gh api "repos/$repo/automated-security-fixes"`; alerts, **on (HTTP 204)**: `gh api -i "repos/$repo/vulnerability-alerts"`
- Deploy environment branches, **main only**: `gh api "repos/$repo/environments/$env/deployment-branch-policies" --jq '.branch_policies[].name'`

In Azure (read only, signed in to the project's tenant):
- Policy assignments, **3**: `az policy assignment list --query 'length(@)'`
- Budgets, **1**: `az consumption budget list --query 'length(@)'`
- The deploy identity's role assignments, **1**: `az role assignment list --assignee "$(az identity show -n "$id" -g "$ci" --query principalId -o tsv)" --all --query 'length(@)'`
- Federated credentials, **1**: `az identity federated-credential list --identity-name "$id" -g "$ci" --query 'length(@)'`
