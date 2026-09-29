# Workstation hardening

The baseline checks what a coding agent asks to do, and everything that reaches the default branch. It can't check code that runs as you on your own computer. A poisoned package's install script, or anything else running under your account, can read your sign-ins directly and send them out. This page is the path to close that gap. The baseline documents it rather than building it; [a prompt template](prompts/harden-the-workstation.md) has an agent build it for you.

## The risk

Code that runs as you can read everything you can:
- the cloud CLI's sign-in cache (`~/.azure`), which can mint new access tokens for weeks;
- SSH keys, the GitHub CLI's token, other tools' credentials, and `.env` files;
- secrets exported in your shell's environment, which every program the agent starts inherits.

If that code stays in the repository or on the machine, rotating a token doesn't help: it steals each new one.

## What the baseline already covers

- **Getting in.** Packages wait seven days before use and install from hash-pinned lists; actions and hooks are pinned by commit hash; `main` changes only through a pull request that passes the required checks.
- **Hiding places.** Workflows, hook configuration, and the editor's tasks and settings are enforcement files: changing them needs the owner, and the gate sees it.
- **A tricked agent.** The guard stops an agent reading credential files, printing tokens, or sending data to sites that aren't on the allowlist ([checks-inventory.md](checks-inventory.md)).

What's left is code that runs as you, outside the agent.

## The fix: a sealed workspace for the agent

1. **Run the agent in a dev container.** Commands run inside the container, not on your computer; your edits still appear in the repository. Anthropic's [dev container guide](https://code.claude.com/docs/en/devcontainer) and [reference container](https://github.com/anthropics/claude-code/tree/main/.devcontainer) are the starting point; VS Code opens it with the Dev Containers extension.
2. **Don't bring your sign-ins.** Never mount `~/.azure`, `~/.ssh` or the GitHub CLI's config into the container. Give it its own credentials instead: a fine-grained GitHub token limited to this repository, with an expiry date, and an Azure identity with only the access the work needs. Your Owner login stays outside, for your own steps.
3. **Limit where it can connect.** A firewall in the container that blocks everything except an allowlist; reuse the allowed hosts in `.claude/security-stack.json`, plus the domains Claude Code itself needs.
4. **Put policy where the agent can't change it.** Managed settings in the container (the credential deny rules, the guard, bypass-permissions mode turned off) take precedence over the project's settings. Anthropic's server-managed settings go further, for policy that repository edits can't touch.
5. **Keep secrets out of the environment.** No long-lived API keys exported in shell profiles; short-lived, scoped tokens where a tool needs one.

What stays open: the container can't protect the rest of your computer (the browser, other apps), and a token inside it can still reach the allowed sites, which is why those tokens are scoped and short-lived.

## If a token keeps getting stolen

Clean first, rotate last.
1. **Contain.** Sign out everywhere, and disable the leaked tokens.
2. **Find what's stealing them.**
   - In the repository: every branch, the workflows, hook configuration, editor tasks and settings, and config files with content pushed out of view.
   - In your GitHub account: SSH keys, tokens, OAuth apps and deploy keys you didn't add.
   - On the computer: startup items, shell profiles, and recently installed packages and extensions.
3. **Remove it.** If in doubt, rebuild from a commit you know is good.
4. **Rotate every credential that computer held**, only now.
5. **Watch** for new sign-ins, new keys and unexpected pushes.
