# Prompt: harden the workstation

The baseline documents how to seal the agent off from your own sign-ins ([workstation-hardening.md](../workstation-hardening.md)) but doesn't build it. Paste the prompt below into your coding agent, in a clone of your repository, to build it.

The dev container's files are new enforcement files, so the agent needs your approval to add them. You'll also create the scoped credentials yourself.

```text
Build the sealed workspace in docs/workstation-hardening.md for this repository.

Read first: docs/workstation-hardening.md; Anthropic's dev container guide (https://code.claude.com/docs/en/devcontainer) and its reference container (https://github.com/anthropics/claude-code/tree/main/.devcontainer); AGENTS.md.

Then, one step at a time, showing me each before the next:
1. Add .devcontainer/ with a non-root user and this project's tools, pinned. Mount none of my sign-ins: no ~/.azure, ~/.ssh or GitHub CLI config.
2. Add a firewall that blocks outbound traffic except the allowed hosts in .claude/security-stack.json and the domains Claude Code needs. Show me the list before you write it.
3. Put managed settings in the image: the credential deny rules, the guard's registration, and bypass-permissions mode turned off.
4. Add .devcontainer/ to CODEOWNERS, and a check for it to docs/checks-inventory.md.
5. Tell me exactly how to create the container's own credentials: a fine-grained GitHub token for this repository only, with an expiry, and an Azure identity with only the access the work needs. Don't create them yourself.
6. Add a CI job that builds the container and proves an unlisted host is blocked, a listed one works, and no credential folder is mounted.

Never mount or copy my own credentials into the container, even to test it.
```
