# Prompt: set up the stack in a new repository

To set the security stack up in a new repository, copy [security-setup-prompt.md](../security-setup-prompt.md) and [setup-guide.md](../setup-guide.md) into it. Then paste the prompt below into your coding agent there, and fill in the brackets. The setup guide explains each phase, and says which steps are yours.

```text
Set up the security and governance stack in this repository, following docs/security-setup-prompt.md phase by phase. The starter it comes from: [the starter repository's link].

Before Phase 0, ask me for anything the prompt says the owner decides, including: the repository's owner and name, my GitHub handle for CODEOWNERS, the Azure tenant, subscription and region, the names to block, and which coding agents and editors I use.

As you go:
- Start locked down: every check on, every check that can block set to block, nothing lowered, even to get past a failure.
- Show me your plan before each phase, and wait for my go-ahead.
- Stop at each phase's verification, and show me the result.
- If I use an agent or editor the guard doesn't cover (docs/coding-agents.md), tell me what that leaves open, and offer to port the guard with docs/prompts/port-the-guard.md.
- If my app isn't Python, or my CI isn't GitHub Actions, say which checks need replacing, and offer docs/prompts/adapt-the-checks.md.
```
