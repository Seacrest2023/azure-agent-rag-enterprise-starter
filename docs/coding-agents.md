# Coding agents and runtime enforcement

Which protections reach which coding agent: what this baseline supports and has tested, what it doesn't, and how to bring the protections to an agent or editor it doesn't cover.

## Tested with

This baseline is built and tested in **VS Code on Windows**, with **Claude Code** (its VS Code extension; its terminal CLI runs the same hooks) and **GitHub Copilot Chat**. The CI checks run on Linux (`ubuntu-24.04`). Other editors, agents and operating systems aren't tested here: the rows below say what their documentation promises, not what this baseline has proved.

## Three layers

The one rule (agents never skip or change enforcement without the owner's approval) holds at three layers:

| Layer | What enforces it | Which agents it reaches |
| --- | --- | --- |
| Runtime, before each tool call | The agent guard, `.claude/hooks/block_hook_bypass.py` | Claude Code, and GitHub Copilot Chat's agent in VS Code |
| Commit | The git hooks (`.pre-commit-config.yaml`) | Any agent that commits in a clone where the hooks are installed |
| Pull request | The required checks, the security gate, and the ruleset on the default branch | Every change that reaches the default branch, whatever made it |

The pull request layer is the wall: nothing reaches the default branch without passing it. The runtime layer is the brake: it stops an agent before it changes enforcement, and asks you instead, or refuses where asking can't be relied on. Runtime enforcement means that brake, and it's the one layer that depends on the agent.

Every agent reads `AGENTS.md`, but instructions are advice, not enforcement. The vendors say so themselves: Claude Code's docs call instructions "context, not enforced configuration", and Cursor's say AI guidance shouldn't be your only security control.

## Where the guard runs

| Agent, and where it runs | The guard | Enforcement changes | Tested here |
| --- | --- | --- | --- |
| Claude Code: its VS Code extension, or its CLI in any terminal or editor (JetBrains IDEs included) | Runs, from `.claude/settings.json` | Asks you in the default and plan permission modes; refuses in every other mode | In VS Code on Windows |
| A Claude Code cloud session on this repository | Runs, when its environment has Python | As above | No |
| GitHub Copilot Chat in VS Code (VS Code's Local session target) | Runs, from `.github/hooks/agent-guard.json` | Always refuses | By its tests; live, by you (setup prompt Phase 2, step 5) |
| VS Code's Claude session target | May run: it uses the Claude Agent SDK, which can load `.claude/settings.json` | As Claude Code | No |
| VS Code's Copilot session target, and the Copilot CLI | Doesn't run: they take the registration's `exit 0` command | Not checked | No |
| The Copilot cloud agent | Doesn't run (the same `exit 0`) | Not checked | No |
| Any other agent, in any editor: Cursor, Codex, Gemini CLI, Devin Desktop, JetBrains' own agents and others | Doesn't run, except perhaps in Devin Desktop, which reads `.claude/settings.json` | Not checked | No |

Where the guard doesn't run, the other two layers still hold: the git hooks run when the agent commits in a clone where they're installed, and nothing reaches the default branch without the required checks, the gate and the ruleset. What's lost is the brake before the pull request: such an agent can edit an enforcement file, or skip the hooks, and only the pull request catches it.

VS Code's chat can run several agents, which it calls session targets. Local is Copilot Chat's own agent, which VS Code runs itself, and it's the only one VS Code's hook settings (`chat.useHooks` and the rest) configure. The Copilot, Claude and Codex targets run in a separate process, the Agent Host, each with its own hooks; Cloud runs on the provider.

## What the guard does

- **Blocks outright** every way of skipping the git hooks: `--no-verify` or `-n`, `SKIP=` and the other variables that switch hooks off, in bash and PowerShell, `core.hooksPath`, `pre-commit uninstall`, and writes inside `.git/`. It also blocks an agent's commit while the clone's git hooks aren't installed.
- **Needs you** for any change to enforcement: the files CODEOWNERS lists, Claude Code's and VS Code's settings files, and the repository's rules and settings on GitHub. It works out which paths a file edit, a shell command, inline code, a patch or a connector call changes. It also needs you before merging or approving a pull request that changes an enforcement file, and before an Azure change from the terminal.
- **Keeps your sign-ins and data in.** It refuses commands that read your sign-ins or `.env` files, or print a token, and needs you before data leaves: a request that sends data, a site that isn't on the allowlist in `.claude/security-stack.json`, a push to a remote other than `origin`.
- **Asks or refuses.** An ask only protects you if it reaches you. Claude Code puts it in front of you in the default and plan permission modes, so the guard asks there; in the others, bypass permissions included, it refuses. Copilot Chat's auto-approve modes skip prompts, so there it always refuses. When it refuses, the agent stops, tells you what it needs and recommends a way forward, and says when you'd need to switch to default mode (Shift+Tab) to approve; or you do it yourself.
- **Fails closed.** Input it can't read, any error, a Python that's missing or too old, a write target it can't resolve, or running out of time (45 seconds): each blocks the tool call.

Code that runs as you on your own computer, such as a poisoned package, is outside the guard's reach: [workstation-hardening.md](workstation-hardening.md) is the path to close that gap.

Its limits: it's a brake, not a sandbox. It can't see inside a script file the agent writes and then runs. Checking out or merging a branch brings that branch's files. It sees only what the agent asks to run through a hook. And it's cautious rather than exact, so now and then it refuses a harmless command. The full list is in [checks-inventory.md](checks-inventory.md), checks 1 to 10, 68 and 70 to 72.

## Copilot Chat in VS Code

`.github/hooks/agent-guard.json` runs the guard with `--copilot` before each tool call by Copilot Chat's agent. Copilot sends the same event fields as Claude Code (`tool_name`, `tool_input`, `session_id`, `cwd`), under its own tool names, and the guard maps them itself:
- **The terminal.** `run_in_terminal` is checked as Claude's `Bash`, and again as `PowerShell`, since it runs your shell.
- **File edits.** `create_file`, `replace_string_in_file`, `multi_replace_string_in_file`, `insert_edit_into_file`, `edit_notebook_file` and `create_directory` name their files in `filePath` or `dirPath`. `apply_patch` names them inside the patch text.
- **Reads** such as `read_file`, `file_search`, `grep_search` and `list_dir` pass.
- **Anything else** is judged by the files and commands its input names, and a connector (`mcp_…`) as Claude Code's connectors are. `create_and_run_task` writes `.vscode/tasks.json`, an enforcement file. `run_vscode_command` and `install_extension` run code the guard can't see, which can do anything the editor can, typing into a terminal included, so they're refused.
- **Failing closed.** VS Code treats any failing exit but 2 as a warning and runs the tool anyway, so the registration's commands turn a guard that can't start into exit 2. On Windows VS Code runs the command through Windows PowerShell, which reports any failing program as 1, so the command passes the guard's exit code on itself. It runs from `.github/hooks`, an enforcement folder, and writing a program the hooks run (`python`, `cmd`, a shell) anywhere needs you, so a planted one can't stand in for the guard.

To use it:
1. Keep `chat.useHooks` on (the default), and trust the workspace: VS Code runs a workspace's hooks only when it's trusted.
2. Leave `chat.useClaudeHooks` off (the default). It makes Copilot run `.claude/settings.json` too, whose registration is written for Claude Code.
3. Check that **Chat: Configure Hooks** lists `.github/hooks/agent-guard.json`. The **GitHub Copilot Chat Hooks** output channel shows each run.
4. Prove it (setup prompt Phase 2, step 5): ask the agent to run `git commit --no-verify -m test`, and to add a line to `.github/CODEOWNERS`. Both must be refused. Do it again after VS Code updates: a tool VS Code renames, or adds without a hook, isn't checked.

`.vscode/` is an enforcement folder, and VS Code's user settings, each profile's included, and its workspace files (`*.code-workspace`) are enforcement files, so an agent can't switch the hooks off there without you. Like `python script.py` in Claude Code, `runTests`, `run_notebook_cell` and `run_task` run the project's own code, which the guard doesn't read. Copilot's own approval settings aren't a security boundary: an auto-approve rule set to `false` asks rather than blocks.

## Other agents and editors

This baseline doesn't support other agents' runtime hooks: it ships no registration for them, and hasn't tested them. The table is what each vendor documents, checked on 28 September 2026. These features change quickly, so check again before relying on a row.

| Agent | Hook before a tool call | Can block | Can ask you | Covers | Configured in the repository at |
| --- | --- | --- | --- | --- | --- |
| Claude Code (supported) | `PreToolUse` | Yes | Yes | Shell, file edits, MCP | `.claude/settings.json` |
| GitHub Copilot Chat in VS Code (supported) | `PreToolUse` | Yes | Yes, but its auto-approve modes skip prompts | Every tool call, under Copilot's own tool names | `.github/hooks/*.json`; Claude-format hooks with `chat.useClaudeHooks` |
| GitHub Copilot CLI, and VS Code's Copilot session target | `preToolUse` | Yes | Yes | Shell, file edits | `.github/hooks/*.json`, `.github/copilot/settings.json` |
| GitHub Copilot cloud agent | `preToolUse` | Yes | No: "ask" counts as deny | Shell, file edits | `.github/hooks/*.json`, on the default branch |
| Cursor | `preToolUse`, `beforeShellExecution`, `beforeMCPExecution` | Yes | Shell and MCP only | Shell, file edits (before the write), MCP | `.cursor/hooks.json` |
| OpenAI Codex, CLI and IDE extension | `PreToolUse` | Yes | No: "ask" is ignored and the tool call runs | Shell, file edits, MCP | `.codex/hooks.json`, or `[hooks]` in `.codex/config.toml` |
| Gemini CLI | `BeforeTool` | Yes | Not documented | Shell, file edits, MCP | `.gemini/settings.json` |
| Devin Desktop (formerly Windsurf) | `PreToolUse` | Yes | Not documented | Shell, file edits, MCP | `.devin/hooks.v1.json`; it also reads `.claude/settings.json` by default |

What each needs to know:
- **The Copilot CLI, and VS Code's Copilot session target** (which uses the CLI's hooks), read `.github/hooks/*.json`, but take a command from the file's `command` field, which in the guard's registration is `exit 0`. So the guard doesn't run there, and nothing breaks. A port needs the CLI's tool names (`bash`, `powershell`, `create`, `edit`, ...), and would put the guard in the `bash` and `powershell` fields. A failing hook denies the call there, but one that times out lets it through.
- **Copilot's cloud agent** reads `.github/hooks/*.json` from the default branch, and runs the same `exit 0`. It's held by the ruleset and the required checks: its workflows wait for someone to approve the run, and the person who asked for the change can't approve its pull request.
- **Cursor** lets an action through when a hook crashes or times out, unless the hook sets `failClosed: true`. It can't ask about a file edit, so a port must deny those. Its cloud agents run the project's hooks, but not `beforeMCPExecution`.
- **Codex** runs the repository's hooks only after you trust the project, and trust each hook. Its docs call hooks "a useful guardrail, not a complete enforcement boundary". For shell commands, `.codex/rules/*.rules` can ask first or forbid.
- **Devin Desktop** reads `.claude/settings.json` hooks by default, so the guard may run there as shipped. That isn't verified, and what it does with an "ask" isn't documented. Test it before relying on it.
- **Other editors, JetBrains IDEs among them,** matter less than the agent: the guard belongs to the agent's hooks, not the editor. Claude Code runs it in any editor; an editor's own agent needs a port.

## What's portable

Most of the stack doesn't depend on the agent or the editor:
- **The git hooks** (secrets, private keys, large files, merge conflicts, broken YAML, blocked names) run in any clone where they're installed, whatever makes the commit.
- **The pull request layer** (the required checks, the gate, the ruleset, CODEOWNERS and the GitHub settings check) judges every change that reaches the default branch, whatever wrote it.
- **The Azure setup** (the region lock, the budget, the keyless deploy identity) doesn't involve the agent at all.
- **The guard's judgement** is shared: what counts as enforcement, how a shell command is parsed, and what a GitHub or Azure command changes. Only its registration, its tool names and its answer format belong to an agent.

What's specific to this baseline's choices: the app checks are Python's (ruff, basedpyright, pytest, coverage, deptry, vulture, pip-audit), and the required checks run on GitHub Actions. Another language or CI needs its own equivalents, under the same rules.

You don't have to port by hand. Point your agent at these docs, and at [checks-inventory.md](checks-inventory.md), which says how a new repository adopts each check, and use the prompt templates below.

## Porting the guard

A port needs:
1. **The agent's tools, mapped.** Read the agent's hook input, and check each of its tools as the Claude Code tool that does the same: its shell, its file edits and patches, and each connector. `check_copilot` in the guard is a worked example.
2. **A decision for "ask".** Where the agent can't be relied on to put a question in front of you, deny. The agent then can't change enforcement at all, and you make those changes yourself or through Claude Code. That's the trade the guard makes in Copilot Chat, and in Claude Code's bypass-permissions mode.
3. **Failing closed.** Configure the agent so that a crash or timeout blocks the call (Cursor's `failClosed`), and wrap the command where a failing hook would let the call through, as `.github/hooks/agent-guard.json` does. Keep the guard's rule that any error blocks.
4. **Tests.** Run the guard's tests (`tests/hooks/`) for the new agent's tools, and one that runs the registration's own command, so the port proves it blocks and refuses what the guard does.
5. **The registration protected.** Add it to CODEOWNERS (`.github/` already is) and to the gate's protected lists, so it can't be removed or weakened without you.

## Prompt templates

Paste one into your coding agent, and fill in the brackets:
- [Port the guard to another agent](prompts/port-the-guard.md).
- [Adapt the checks to another language or CI](prompts/adapt-the-checks.md).
- [Set up the stack in a new repository](prompts/set-up-a-new-repository.md).
- [Harden the workstation](prompts/harden-the-workstation.md): a sealed dev container for the agent.

## Sources

- Claude Code: [hooks](https://code.claude.com/docs/en/hooks), [permission modes](https://code.claude.com/docs/en/permission-modes), [settings in cloud sessions](https://code.claude.com/docs/en/settings#settings-in-cloud-sessions), [memory and instructions](https://code.claude.com/docs/en/memory)
- GitHub Copilot in VS Code: [hooks and session targets](https://code.visualstudio.com/docs/agent-customization/hooks), [hooks reference](https://code.visualstudio.com/docs/agents/reference/hooks-reference), [approvals](https://code.visualstudio.com/docs/agents/run/approvals), [workspace trust](https://code.visualstudio.com/docs/editing/workspaces/workspace-trust)
- GitHub Copilot CLI and cloud agent: [hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference), [using hooks](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/use-hooks), [risks and mitigations](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/risks-and-mitigations)
- Cursor: [hooks](https://cursor.com/docs/hooks), [rules](https://cursor.com/docs/context/rules)
- OpenAI Codex: [hooks](https://learn.chatgpt.com/docs/hooks), [rules](https://learn.chatgpt.com/docs/agent-configuration/rules), [config reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- Gemini CLI: [hooks](https://geminicli.com/docs/hooks/)
- Devin Desktop: [hooks](https://docs.devin.ai/cli/extensibility/hooks/overview), [changelog](https://docs.devin.ai/desktop/changelog)
