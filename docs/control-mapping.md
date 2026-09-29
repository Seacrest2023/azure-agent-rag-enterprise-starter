# Control mapping

This page maps each check in the [checks inventory](checks-inventory.md) to the audit questions it answers, in the auditor's own numbering, and says which questions no repository can answer. A repository supplies evidence for controls; only an organisation is certified, so this page is the evidence pre-mapped, not the audit. The AI-specific risks, in the FINOS AI Governance Framework's numbering, are in [ai-risk-mapping.md](ai-risk-mapping.md).

As of 28 September 2026. SOC 2 is the 2017 Trust Services Criteria with the 2022 points of focus; ISO is ISO/IEC 27001:2022 Annex A; NIST is CSF 2.0 by function (GV govern, ID identify, PR protect, DE detect, RS respond, RC recover).

## How to read this

| Status | Meaning |
| --- | --- |
| **Full** | The check alone is sufficient evidence that the control operates for the repository's scope. |
| **Partial** | The check contributes evidence, but the control also needs something outside the repository: a person, a policy or a setting elsewhere. |
| **Not covered** | The control is out of the repository's reach; the row says where it lives. |

A check that warns cannot be Full; one that ends in the owner's answer is Partial. Where a whole SOC 2 series applies, such as the control environment or monitoring, the page names the series (CC1.x to CC5.x) rather than listing each criterion in it. A recorded lowering is shown where it applies; the baseline starts with none. Check numbers and names are the inventory's.

## Coverage at a glance

44, 45 and 51 count in two areas; all 72 checks appear.

| Control area | SOC 2 | ISO 27001:2022 Annex A | NIST CSF 2.0 |
| --- | --- | --- | --- |
| Change control: the checks cannot be skipped or rewritten | Full (14): CC8.1 | Full (14): 8.9, 8.32 | Full (14): PR |
| Independent review and separation of duties | Partial (9): CC8.1 | Partial (9): 5.3, 8.32 | Partial (9): GV, PR |
| Secure coding and testing | Full (15): CC8.1 | Full (15): 8.28, 8.29 | Full (15): PR |
| Secrets and data leakage | Full (8): CC6.1 | Full (8): 5.17, 8.12 | Full (8): PR, DE |
| The agent's reach: the owner's sign-ins and data leaving | Partial (3): CC6.1, CC6.7 | Partial (3): 5.14, 5.17, 8.12 | Partial (3): PR |
| Supply chain and software integrity | Full (8): CC6.8, CC9.2 | Full (8): 5.19 to 5.22, 8.19 | Full (8): PR |
| Vulnerability management | Partial (4): CC7.1 | Partial (4): 8.8 | Partial (4): ID, PR, DE |
| Least privilege for CI and deploy identities | Full (6): CC6.1, CC6.2, CC6.3 | Full (6): 5.18, 8.2, 8.3, 8.5, 8.31 | Full (6): PR |
| Cloud configuration and data residency | Full (2): CC5.x | Full (2): 5.23, 5.31, 8.9 | Full (2): GV, PR |
| Monitoring of main, settings and cloud | Partial (5): CC4.x, CC7.1, CC7.2 | Partial (5): 8.16 | Partial (5): DE |
| Logging and immutable history | Partial (1): CC8.1 | Partial (1): 8.15 | Partial (1): DE |
| User access management: people, MFA, reviews | Not covered: CC6.2, CC6.3 | Not covered: 5.15, 5.16, 5.18 | Not covered: PR |
| Incident management, backup and recovery | Not covered: CC7.3, CC7.4, CC7.5 | Not covered: 5.24 to 5.28, 5.30, 8.13 | Not covered: RS, RC |
| Governance, risk, policy and training | Not covered: CC1.x, CC2.x, CC3.x, CC9.1 | Not covered: 5.8, 5.35, 6.3, 6.8 | Not covered: GV |

By check: 36 Full, 36 Partial (warns, needs a person, or runs only on the owner's computer).

## The mapping

One table per group, in the inventory's order.

### Claude Code hook

The guard runs on the owner's computer, in Claude Code and Copilot Chat (check 68). It leaves no record on GitHub, depends on the terminal's settings, and six checks end in the owner's answer, so every row is Partial. The evidence is its 175 tests, run by selftest on every pull request (check 23), and the proofs in `.claude/security-stack.json`.

| Check | What it evidences | SOC 2 | ISO | NIST | Status | Where the evidence lives |
| --- | --- | --- | --- | --- | --- | --- |
| 1 Hook skips refused; 2 Git hooks installed before an agent's commit; 9 Python 3.9 or later for the guard | The commit checks cannot be switched off, nor the guard run down | CC8.1 | 8.9, 8.32 | PR | Partial | selftest logs |
| 3 Enforcement changes ask the owner; 4 GitHub rule and setting changes ask the owner; 6 Connector tools that touch enforcement ask the owner; 8 Azure changes ask the owner | No change to a check, rule, setting or Azure resource from the terminal without the owner's yes | CC6.3, CC8.1 | 5.3, 5.23, 8.9, 8.32 | GV, PR | Partial: owner's answer | selftest logs |
| 5 Merging or approving an enforcement PR asks the owner | The agent cannot merge its own enforcement change | CC8.1 | 5.3, 8.32 | GV, PR | Partial: owner's answer | selftest logs |
| 7 Azure commands stay in the project's tenant | Terminal work stays in the project's tenant | CC6.1, CC6.3 | 5.23, 8.2 | PR | Partial | selftest logs |
| 10 Git hooks installed at session start | Sessions start with the hooks installed | CC8.1 | 8.9 | PR | Partial: warns; check 2 blocks | selftest logs |
| 68 The guard in Copilot Chat | Checks 1 to 8, 71 and 72 hold in Copilot Chat; it refuses rather than asks | CC6.3, CC8.1 | 5.3, 8.9, 8.32 | PR | Partial: other agents skip the guard | selftest logs |
| 71 Sign-in reads and token printing refused | Commands can't read or copy the owner's sign-ins or `.env` files, or print a token | CC6.1 | 5.17, 8.12 | PR | Partial | selftest logs |
| 72 Outbound data asks the owner | Data leaves only for hosts on the allowlist, or with the owner's yes | CC6.1, CC6.7 | 5.14, 8.12 | PR | Partial: owner's answer | selftest logs; `network.allowed_hosts` in `.claude/security-stack.json` |

### Claude Code setting

Claude Code enforces it itself, in every permission mode, but only for Claude Code on the owner's computer.

| Check | What it evidences | SOC 2 | ISO | NIST | Status | Where the evidence lives |
| --- | --- | --- | --- | --- | --- | --- |
| 70 Sign-in files denied to Claude Code | Claude Code can't read the owner's sign-ins or `.env` files, bypass-permissions mode included | CC6.1 | 5.17, 8.12 | PR | Partial: Claude Code only | `.claude/settings.json`; the proof recorded in `.claude/security-stack.json` |

### git commit

These run on the developer's computer and leave no record; a connector or web-editor commit runs none. Check 22 replays the chain on every pull request, so each is Partial alone and Full through check 22.

| Check | What it evidences | SOC 2 | ISO | NIST | Status | Where the evidence lives |
| --- | --- | --- | --- | --- | --- | --- |
| 11 Secrets; 13 Private keys | Keys and passwords are not committed | CC6.1 | 5.17, 8.12, 8.28 | PR | Partial | precommit logs |
| 12 Large files | Binaries and data dumps stay out | CC8.1 | 8.12 | PR | Partial | precommit logs |
| 14 Merge-conflict markers; 15 Broken YAML | Broken files stay out | CC8.1 | 8.28 | PR | Partial | precommit logs |
| 16 Blocked names in files and paths; 17 Blocked names in the commit message | Listed confidential names stay out | CC8.1 | 8.12 | PR | Partial | precommit logs |
| 18 App files under 500 lines; 19 Lint at commit; 20 Format at commit | App code meets the coding standard before commit | CC8.1 | 8.28 | PR | Partial | precommit logs |

### CI on PR

The five required jobs run from main's copy of `security-gate.yml`, with tools installed from main by hash before any PR file is on disk, and must pass on an up-to-date branch. Gate means the security-critical-gate job. The evidence is the pull request's check history and Actions logs, which GitHub keeps for a limited time: export them (enterprise-level-gaps.md, caveat 8).

| Check | What it evidences | SOC 2 | ISO | NIST | Status | Where the evidence lives |
| --- | --- | --- | --- | --- | --- | --- |
| 21 Secret scan of the PR | No secret reaches main, hooks skipped or not | CC6.1 | 5.17, 8.12, 8.29 | PR | Full | secret-scan logs |
| 22 Commit checks replayed | The commit checks cannot be skipped | CC8.1 | 8.29, 8.32 | PR | Full | precommit logs |
| 23 Tests of the gate and the guard | The controls are themselves tested on every change (288 tests) | CC4.x, CC8.1 | 8.29, 8.32 | PR | Full | selftest logs |
| 24 Gate: no new suppressions | Green cannot be reached by silencing a check | CC8.1 | 8.28, 8.29 | PR | Full | gate logs |
| 25 Gate: no blocked names | Listed names cannot reach main by any route | CC8.1 | 8.12 | PR | Full | gate logs |
| 26 Gate: risky workflow settings | Changed workflows are scanned for unsafe settings | CC8.1 | 8.9, 8.27 | PR | Full | gate logs |
| 27 Gate: workflows can't weaken the required checks; 28 Gate: protected lists only grow | A pull request cannot rewrite or shrink the checks that judge it | CC8.1 | 8.9, 8.32 | PR | Full | gate logs |
| 29 Gate: pinned tool lists are frozen; 69 Gate: hook pins are full commit hashes | No new code enters the trusted jobs; each hook pins to one commit | CC6.8, CC9.2 | 5.19 to 5.22, 8.19 | PR | Full | gate logs |
| 30 Gate: secret scanning only gets stricter | Secret scanning cannot be switched off through its baseline | CC6.1, CC8.1 | 8.12, 8.32 | PR | Full | gate logs |
| 31 Gate: security-critical paths reported | The reviewer is told which security-critical paths changed | CC8.1 | 8.32 | ID | Partial: warns | the job summary |
| 32 Lint; 33 Format; 34 Types; 38 Dependencies; 39 Dead code | App code meets the coding standard, suppressions ignored; declared packages match use; nothing unwired ships | CC8.1 | 8.28 | PR | Full | python logs |
| 35 Tests; 36 Skipped tests fail the run; 37 Changed-line coverage | Changes are tested, 80% of changed lines covered, no skip is green | CC8.1 | 8.29 | PR | Full | python logs |
| 40 Known vulnerabilities | No package with a known vulnerability merges | CC7.1 | 8.8 | ID, PR | Full | python logs |
| 41 Hash-checked installs for the Python checks; 42 Hash-pinned tools for the security jobs; 43 Seven-day cooldown on package versions | The judging tools are the intended ones; no release under seven days old | CC6.8, CC9.2 | 5.19 to 5.22, 8.19 | PR | Full | python and gate logs; `.github/requirements/`; `uv.lock` |

### CI scheduled

| Check | What it evidences | SOC 2 | ISO | NIST | Status | Where the evidence lives |
| --- | --- | --- | --- | --- | --- | --- |
| 44 Secret scan of main | Main is rescanned after each merge and daily | CC7.1, CC7.2 | 8.12, 8.16 | DE | Partial: warns | security.yml logs |
| 45 Vulnerability audit of main | Vulnerabilities disclosed after merge surface daily | CC7.1 | 8.8, 8.16 | DE, ID | Partial: warns | security.yml logs |

### CI, run by hand

| Check | What it evidences | SOC 2 | ISO | NIST | Status | Where the evidence lives |
| --- | --- | --- | --- | --- | --- | --- |
| 46 Keyless Azure sign-in proof | The federated sign-in works end to end | CC6.1 | 5.23, 8.5 | PR | Partial: run by hand; warns | azure-login-check logs |

### GitHub setting

Platform-enforced. The evidence is the settings themselves, read back with the inventory's How to recount commands, and check 66's output. A repository admin can change them ([rules anchored outside the repository](#the-two-controls-a-solo-owner-cannot-fully-evidence), below).

| Check | What it evidences | SOC 2 | ISO | NIST | Status | Where the evidence lives |
| --- | --- | --- | --- | --- | --- | --- |
| 47 Required status checks; 48 Pull request required, squash only; 67 Review threads resolved before merging | Nothing reaches main except by a pull request that passed all five checks, every review thread resolved | CC8.1 | 8.32 | PR | Full | the ruleset; check 66 output |
| 49 Code-owner review for other authors | Other authors' enforcement changes wait for the owner | CC8.1 | 5.3, 8.32 | GV, PR | Partial: does not hold the owner's own PRs, which the agent's are | the ruleset; PR review history |
| 50 Extra approval for unattributed changes | Every merged commit is linked to a GitHub account | CC8.1 | 5.16, 8.32 | PR | Full | the ruleset |
| 51 No deletion or force push | Main's history is the record of what passed | CC8.1 | 8.15, 8.32 | PR | Full | the ruleset |
| 52 No one bypasses the ruleset | The rules bind everyone, admins and owner included | CC6.3, CC8.1 | 5.3, 8.2, 8.32 | GV, PR | Full: bypass list empty | the ruleset; Lowered from the baseline |
| 53 Enforcement files listed | The protected files are defined (27 entries) | CC8.1 | 8.9, 8.32 | PR | Partial: holds through checks 3, 5, 49 and 68 | `.github/CODEOWNERS` |
| 54 Read-only workflow token; Actions can't approve PRs | CI runs with least privilege and cannot approve a change | CC6.3 | 8.2, 8.3 | PR | Full | Actions permissions readback |
| 55 Actions pinned to a full commit SHA | An action's code cannot be swapped by moving a tag | CC6.8, CC9.2 | 5.19 to 5.22, 8.19 | PR | Full | Actions permissions readback; the workflows |
| 56 Dependabot alerts; 57 Dependabot security updates | Vulnerable dependencies are flagged and a fix PR opened | CC7.1 | 8.8 | ID, PR | Partial: warns | repository settings; Dependabot PR history |
| 58 Dependabot version updates | Pins and packages refresh weekly after a seven-day cooldown | CC7.1, CC9.2 | 8.8, 8.19 | ID, PR | Partial: warns | `.github/dependabot.yml`; Dependabot PR history |
| 59 Deploy environment limited to the default branch | Only main can use the deploy sign-in | CC6.1, CC6.3 | 8.2, 8.31 | PR | Full | environment branch policy readback |

### Azure setting

Platform-enforced in Azure. None is under the one rule, and a portal change skips every repository check (security.md, "Drift"). The evidence is the How to recount readbacks and the Azure activity log.

| Check | What it evidences | SOC 2 | ISO | NIST | Status | Where the evidence lives |
| --- | --- | --- | --- | --- | --- | --- |
| 60 Allowed locations; 61 Allowed locations for resource groups | Resources and resource groups stay in the project's region | CC5.x | 5.23, 5.31, 8.9 | GV, PR | Full | policy assignment readback; Azure activity log |
| 62 Cloud security benchmark audit | Misconfigurations are reported | CC4.x, CC7.1 | 5.23, 8.8, 8.16 | DE, ID | Partial: warns | Defender for Cloud |
| 63 Monthly budget alerts | Unexpected spend is noticed | CC7.2 | 8.16 | DE | Partial: warns | budget readback; alert emails |
| 64 Deploy identity limited to the app resource group | A deploy reaches only the app's resource group | CC6.3 | 5.18, 8.2, 8.3 | PR | Full | role assignment readback; Azure activity log |
| 65 Sign-in only from the deploy environment, with no secret | CI signs in with no stored credential, from one environment only | CC6.1, CC6.2 | 5.17, 5.23, 8.5 | PR | Full | federated credential readback; check 46 logs |

### By hand

| Check | What it evidences | SOC 2 | ISO | NIST | Status | Where the evidence lives |
| --- | --- | --- | --- | --- | --- | --- |
| 66 GitHub settings at the baseline | GitHub settings match the baseline when checked | CC4.x, CC7.1 | 8.9, 8.16 | DE | Partial: run by hand with an admin sign-in | the script's output, kept by whoever runs it |

## Not covered by any repository

Part of every standard sits outside a repository (enterprise-level-gaps.md, caveat 9).

| What the standards require | Where it lives in an organisation |
| --- | --- |
| Written policies (CC1.x, CC2.x; GV) | The approved policy set; this repository's docs are inputs |
| Access reviews (CC6.3; 5.18; PR) | A recorded periodic review of GitHub, Azure and Entra access |
| Joiners and leavers (CC6.2; 5.16, 5.18; PR) | HR and IT onboarding and offboarding, including GitHub and Entra |
| Incident response plan and exercises (CC7.3, CC7.4; 5.24 to 5.28, 6.8; RS) | A written plan, event reporting, exercise records |
| Backups and restore tests (CC7.5; 5.30, 8.13; RC) | Backups of Azure data, with dated restore tests |
| Vendor and risk management (CC3.x, CC9.1, CC9.2; 5.19 to 5.22; GV, ID) | A risk register and supplier reviews of GitHub, Azure and AI providers |
| Security training (6.3; GV) | Training records for everyone with access |
| Physical security | The cloud provider's audit reports and the owner's premises |

## The two controls a solo owner cannot fully evidence

**Independent review (SOC 2 CC8.1, ISO A.5.3 and A.8.32).** No pull request into main needs a human approval today, and the agent works through the owner's GitHub account, so GitHub cannot tell the two apart; the five required checks still judge every change, and the guard asks the owner before an enforcement merge. Two settings close the gap: the agent's own GitHub account, with write access and not admin, and one required approval on every pull request into main, of the most recent push. The owner approves on green; that approval is the human signature, and the checks have done the review. An auditor may still treat one owner reviewing one agent as one person's control (enterprise-level-gaps.md, caveat 4); a business adds a second reviewer.

**Rules anchored outside the repository.** The ruleset, the workflow and the guard live in the repository they protect, and its admin, the account the agent uses today, can change them; the guard asks first and check 66 shows drift when run, but neither is an anchor. What closes it: a GitHub organisation on the Team plan or above, with the branch rules and required workflows in organisation rulesets that only organisation owners and a custom role can edit, the agent's account in neither, and the choice recorded as `enforcement_anchor` in `.claude/security-stack.json` (`undecided` today).

## Keeping this page current

A pull request that adds a check, lowers one, or changes a required check updates that check's row here in the same pull request, with its inventory row and, for a lowering, the Lowered from the baseline table. A status never moves up without a change to the check it describes. The counts here derive from the inventory, so its How to recount commands govern them.
