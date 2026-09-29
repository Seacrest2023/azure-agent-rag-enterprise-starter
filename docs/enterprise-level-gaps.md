# Enterprise-level gaps

What this baseline doesn't cover on its own, measured against enterprise security standards, as a todo list. When an item is done and verified, tick it here. Then update its entry in [security.md](security.md) (the status, stop by stop) and in `.claude/security-stack.json` (the status record), or add one where neither has it yet.

The delivery pipeline and the code-quality checks already meet or exceed common enterprise practice:
- required checks a pull request can't rewrite
- the checks' own tools pinned by hash, and actions by SHA (the hook dependencies that pre-commit installs in CI are the exception; see section 5)
- secret scanning on every pull request and on `main` after every merge and daily, plus at commit wherever the git hooks run (a connector or the web editor runs none, so the pull-request scan is the enforcement)
- keyless sign-in to Azure
- strict lint, type and test checks with no way to suppress them
- an agent guard

The gaps are below, most important first. The caveats at the end apply to anyone who adopts the baseline.

Status as of 28 September 2026.

## 1. Independent review

This is the biggest gap. Enterprise standards expect every change to production to be approved by someone other than its author. Today, ordinary pull requests need no approval. A pull request that changes an enforcement file waits for the owner's review, but only when its author isn't a code owner. The agent works through the owner's GitHub account, so GitHub can't tell the agent from the owner, and the agent's pull requests wait for no one on GitHub. In Claude Code, the guard asks the owner before the agent merges an enforcement change, and in Copilot Chat in VS Code it refuses; other agents have no guard. Where the owner has let Dependabot's bumps merge on green, the agent approves those through the owner's account, so even Dependabot's enforcement PRs get no independent review.

- [ ] Give the agent its own GitHub account, with write access and not admin. GitHub then holds the agent's enforcement pull requests for the owner's review, and the agent can't change a rule.
- [ ] Require one approval on every pull request into `main`, and turn on "Require approval of the most recent reviewable push", so whoever pushed last can't be the approver. Stale approvals are already dismissed on a new push.
- [ ] Decide how the owner's own pull requests merge. GitHub doesn't let authors approve their own pull requests, so pick one:
  - All changes come from the agent's account, and the owner reviews them.
  - A second person reviews the owner's pull requests.
  - The owner is a bypass actor for pull requests only, and every bypass is logged. This is the weakest option; an auditor will ask about each bypass.
- [ ] Revisit decision 1 in [security-setup-prompt.md](security-setup-prompt.md) ("No manual steps"). It trades review for speed, which suits a solo owner but not an enterprise. Present required review as the enterprise setting.

## 2. Anchor the checks outside the repository

The checks live in the repository they protect, and that repository's admin is the account the agent uses today.

- [ ] Decide where the repository lives: a personal account or a GitHub organisation. Organisation rulesets are available on GitHub Team and above. A personal account has only repository rulesets, which the repository's admin can change.
- [ ] In an organisation, move the branch rules and the required workflows into organisation rulesets. Only organisation owners, and anyone given a custom role that manages organisation rulesets, can edit them. Keep the agent's account out of both, or the anchor holds nothing.
- [ ] Record the decision as `enforcement_anchor` in `.claude/security-stack.json`. It's `undecided` today.

## 3. GitHub's built-in scanning

- [ ] Code scanning (CodeQL) on every pull request, as a required check.
- [ ] GitHub's secret scanning and push protection, alongside the repository's own secret scan.

Both are free for public repositories. A private repository needs an organisation on GitHub Team or above, with GitHub Code Security and GitHub Secret Protection, which are paid. A private repository in a personal account can't have them.

## 4. Identity and access

- [ ] Confirm MFA for everyone in the Azure directory: Entra ID security defaults, or Conditional Access where the licence allows it.
- [ ] Create an emergency admin account. Its password never passes through the agent.
- [ ] Give the agent a read-only Azure login for day-to-day work. Owner rights only when needed, through just-in-time elevation (Privileged Identity Management) where the licence allows it.
- [ ] Narrow the agent's GitHub token to the repositories and scopes it needs.
- [x] Keep the owner's sign-ins out of the agent's reach: deny rules stop Claude Code reading them and `.env` files in every permission mode, and the guard refuses commands that read them or print a token ([checks 70 and 71](checks-inventory.md#70-sign-in-files-denied-to-claude-code)).
- [ ] Settle the terminal settings:
  - the permission mode (in bypass-permissions mode, only the guard and the deny rules stand between the agent and a command)
  - deny rules for destructive commands
  - only the MCP servers the project needs, each pinned to a version
- [ ] Optional: an admin-only managed settings file that registers the agent guard, so nothing in the repository can switch it off.
- [ ] Keep code that runs as the owner away from their sign-ins: a sealed workspace for the agent, with its own scoped credentials ([workstation-hardening.md](workstation-hardening.md)).
- [ ] Review cloud access: connectors, cloud agent environments, and GitHub's coding agent.

## 5. Supply chain and build integrity

- [ ] Pin the hook dependencies that pre-commit installs in CI. Give the pinned tool lists and hook versions automatic updates and a vulnerability audit.
- [ ] When the deploy job exists, make a build attestation (a signed record of how each build was made) and a software bill of materials for what's deployed.

## 6. Not built yet

The product's own controls are designed in [architecture.md](architecture.md#10-security) but not built. Each is needed before real data goes in.

- [ ] Infrastructure as code for every app resource, applied only by the deploy job, with a scan on every pull request.
- [ ] Least privilege for the deploy identity: roles that cover only what the deploy does, in place of Contributor on the whole resource group. Add an Azure policy that allows only the resource types the project uses, as a second layer that applies to everyone.
- [ ] Drift checks: a scheduled job that flags when Azure, or a live agent, stops matching the repository.
- [ ] Central logging, kept for as long as the standard you're audited against requires.
- [ ] The runtime controls:
  - row-level security
  - masking
  - private endpoints
  - Key Vault
  - the paid Defender plans, such as Defender for Storage's malware scanning (the free foundational plans are already on)
  - prompt-injection filtering
- [ ] Access tests in `tests/access`, protected by the gate, before the first real data.

## 7. Before the repository goes public

- [ ] Three required jobs run a pull request's code under `pull_request_target`: `precommit`, `selftest` and `python`. That's acceptable only for a private repository, where only collaborators open pull requests. The comment in `security-gate.yml` gives the public option for the first two: run them on `pull_request`, where a pull request controls their steps. Decide it for all three, and say which checks a pull request then can't rewrite.
- [ ] Turn on section 3's scanning, which is free once the repository is public.

## 8. Say it in the docs

- [x] Add a short compliance note that links to the caveats below to:
  - the README
  - [security.md](security.md)
  - [security-setup-prompt.md](security-setup-prompt.md)
  - [setup-guide.md](setup-guide.md)

## Caveats for anyone adopting this baseline

Read these before you use the baseline for a business, or in a company that has to meet a security standard.

1. **It isn't certified, and it doesn't make a project compliant.** SOC 2, ISO/IEC 27001 and similar standards audit an organisation: its controls, its people, and evidence over time. They don't audit a repository. The baseline gives you strong technical controls to show an auditor. It isn't the audit.
2. **Out of the box, it's set up for one person.** Ordinary pull requests need no human approval, and the agent works through the owner's account, so its pull requests, enforcement changes included, wait for no reviewer on GitHub. That suits a solo developer. It isn't separation of duties, which SOC 2's change-management criterion (CC8.1) and ISO/IEC 27001 (Annex A 5.3, segregation of duties, and 8.32, change management) expect.
3. **To meet those standards, configure independent review** (sections 1 and 2). A second person approves every change to production, the agent has its own account, and the rules sit where the repository's admins can't change them.
4. **A solo developer can't fully separate duties.** The agent's own account, with the owner reviewing its pull requests, is the closest one person can get. An auditor may still treat that as one person's control. A business needs a second reviewer.
5. **Several controls depend on the GitHub plan.** Organisation rulesets need GitHub Team or above. For a private repository, code scanning and GitHub's secret scanning are paid add-ons that need an organisation. Check the plan before you promise them.
6. **The agent guard works only in Claude Code, and in Copilot Chat in VS Code.** Other agents skip it, the Copilot CLI and the Copilot cloud agent included. For them, the brakes are the git hooks (where they're installed and the agent commits locally), the pull-request checks and, once review is required, the reviewer. [coding-agents.md](coding-agents.md) says what each agent's hooks can do, and what porting the guard would take.
7. **Record every lowering.** You may lower a protection. Record what, why and when in the pull request that lowers it, and in the checks inventory's [Lowered from the baseline](checks-inventory.md#lowered-from-the-baseline). Update [security.md](security.md) and `.claude/security-stack.json` to match. An auditor will ask.
8. **Keep the evidence.** Auditors check that controls ran over a period, using pull-request history, approvals, check results, the organisation's audit log on GitHub and Azure's activity log. GitHub and Azure keep logs for a limited time by default, so export or archive them for as long as the standard requires.
9. **Part of every standard sits outside any repository.** Access reviews, joiners and leavers, incident response, backups and restore tests, vendor and risk management, security training, and written policies. The baseline doesn't cover them.
10. **A company's own policies come first.** If an employer adopts this baseline, map each check in the [checks inventory](checks-inventory.md) to the company's control list. Replace the solo settings with its required reviewers, organisation rulesets and single sign-on.
