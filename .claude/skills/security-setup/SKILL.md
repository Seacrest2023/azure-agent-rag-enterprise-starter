---
name: security-setup
description: Set up, finish, verify or audit the repository's security stack, across the repository (secret scanning, pre-commit chain and its CI replay, the security gate and its tests, the agent guard and the owner-approval rule, blocked names), GitHub (rulesets, Actions and Dependabot settings, environments, variables) and Azure (sign-in, tenant check, resource groups, region policy, the keyless deploy identity, budget). Use when the user asks about security setup, Azure login or az commands, GitHub rulesets or branch protection, CI sign-in to Azure, OIDC, blocked names, hooks, or what security work is left.
---

# Security setup

1. Read [docs/security-setup-prompt.md](../../../docs/security-setup-prompt.md): the stack, the settled decisions, the rules, the phases and the pitfalls. Follow it.
2. Read [.claude/security-stack.json](../../security-stack.json): this project's repository, Azure IDs, region, resource names, required checks and setup status. Never hard-code those values anywhere else.
3. Read [docs/security.md](../../../docs/security.md): what protects each stop a change passes through, its status, and what's left for the owner.
4. Verify before trusting the status in either file, and update both in the same PR when an item changes.

Rules that matter most, from the prompt:
- **Tenant check before every Azure command**, against `azure.tenant_id`. Any other tenant: stop and help the owner sign in again.
- **Never skip or change enforcement without the owner's approval.** Enforcement is the files in `.github/CODEOWNERS`, Claude Code's and VS Code's settings files, and the repository's rules and settings. When the guard asks, the owner answers; when it refuses, stop and tell the owner.
- **Merge on green.** When every check in `github.required_checks` passes and every review thread has an answer and is resolved (the ruleset requires it), merge. Never bypass a check, skip hooks, or weaken a check or list to get a PR through.
- **Never write a blocked name.** Add names only with `python scripts/check_blocked_terms.py --add [--paths] "<name>"`.
- **Prove trusted-workflow changes on a staging branch before merging** (prompt Phase 3, step 3). A broken required check blocks every PR, including its own fix.
- **False positives are restructured, never allowlisted.** A PR can't add a suppression, an allowlist entry or a scan filter.
- **No stored credentials, and no app resources by hand.**
