# Prompt: port the agent guard to another coding agent

The agent guard runs in Claude Code and in GitHub Copilot Chat in VS Code. To bring it to another agent or editor, paste the prompt below into that agent, in a clone of your repository, and fill in the brackets. It follows the steps in [coding-agents.md](../coding-agents.md#porting-the-guard).

The guard, its registrations, the gate and CODEOWNERS are enforcement files, so the agent needs your approval to change them. If the agent you're porting to has no guard yet, review its pull request before you merge it.

```text
Port this repository's agent guard to [the agent, and where it runs: an IDE extension, a CLI or a cloud agent]. Its hook documentation: [link].

Read first:
- AGENTS.md: the one rule and the working rules.
- docs/coding-agents.md: what the guard does, where it runs, and what a port needs.
- .claude/hooks/block_hook_bypass.py: the guard. What counts as enforcement and how a command is parsed are shared; only the input and the answer belong to an agent.
- .github/hooks/agent-guard.json and check_copilot in the guard: a worked port, for Copilot Chat.

Then, one step at a time:
1. From the agent's documentation, list, with a link for each: the hook that runs before a tool call; its input fields; its tool names for the shell, file edits, patches and connectors, and where each names its command or files; how a hook denies, asks and allows; what a crash, a timeout and a failing exit do; and where a repository registers hooks. Show me the list before writing code.
2. Map the agent's tools onto the guard's checks, as check_copilot does. Where the agent can't be relied on to put a question in front of me, deny instead of asking.
3. Make it fail closed: a guard that can't start, crashes or times out must block. If the agent lets a failing hook through, wrap the command so it exits with the agent's blocking code.
4. Register it in the repository, and add the registration to the gate's protected lists, as .github/hooks/agent-guard.json is.
5. Add tests to tests/hooks/. The existing tests must still pass. The new ones must fail against the current guard, and one must run the registration's own command.
6. In the same pull request, update docs/checks-inventory.md (a new check), docs/coding-agents.md and AGENTS.md section 8.
7. Tell me the live test to run in the agent: ask it to run git commit --no-verify -m test, and to add a line to .github/CODEOWNERS. Both must be refused.

Never weaken a check, a test or a protected list to make the port pass.
```
