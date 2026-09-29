# Setup guide

How this project's setup was built, in the order to repeat it: to rebuild this project, or to give a new project the same setup. Each step says who does it and how to check that it worked.

- **You:** the owner. Steps that need your sign-in, your money or your decision.
- **Agent:** Claude Code in your terminal, working in the repository. It follows [security-setup-prompt.md](security-setup-prompt.md), which holds the exact commands; the phase numbers below point into it.

This project's values (names, IDs, region) and the status of the stack's own setup steps are in `.claude/security-stack.json`; on a new project the agent starts that file fresh. What protects each stop a change passes through, and what's still open, is in [security.md](security.md).

**It starts locked down.** Every check is installed at its strictest setting, and nothing is lowered during setup, even to get past a failure. Lowering a protection later is your decision, and it's recorded as described in [checks-inventory.md](checks-inventory.md#lowering-a-protection).

**It isn't a compliance certificate.** The setup gives strong technical controls, but it's set up for one owner, and standards such as SOC 2 and ISO/IEC 27001 expect every change to production to be reviewed by someone other than its author. Read the [caveats](enterprise-level-gaps.md#caveats-for-anyone-adopting-this-baseline) before you rely on it for a business.

## The rule

**Agents never skip or change enforcement without your approval.** Enforcement means the files listed in `.github/CODEOWNERS` (the hooks, the agent guard, the gates and what they read), Claude Code's and VS Code's settings files, and the repository's rules and settings on GitHub. Every other change merges when the checks pass. [security.md](security.md#the-one-rule) says how you approve, in your terminal and on GitHub.

## Before you start

| You need | Why |
| --- | --- |
| A GitHub account on GitHub Pro, or a Team organization | Rulesets on private repositories are enforced only on these plans |
| An Azure subscription where you are Owner | The agent sets up the Azure foundation under your sign-in |
| On your computer: `git`, `gh`, Python 3.12 (as `python`), `uv`, `pre-commit`, `zizmor` (for the local tests), `jq`, `bash` (Git Bash on Windows), `az`, Claude Code | The agent checks these in step 3 and helps install what's missing. Without `python`, the guard refuses every tool call |
| An editor and agents the guard covers | The baseline is tested in VS Code on Windows, with Claude Code and GitHub Copilot Chat. The guard runs in both; for any other agent, see [coding-agents.md](coding-agents.md) |
| Three decisions: the Azure region, the repository name, and the names that must never appear in the repository | All three are hard to change later |

## Steps

### 1. Create the repository (you)

Create an empty repository on GitHub and clone it on your computer. Start it private, and read [before the repository goes public](enterprise-level-gaps.md#7-before-the-repository-goes-public) before you open it to others.

**Check:** the clone works, and GitHub shows the repository as private.

### 2. Set up your terminal (you)

1. Sign in to GitHub: `gh auth login`, then `gh auth status`.
2. Open Claude Code in the clone.
3. Choose the permission mode. In bypass-permissions mode nothing asks before a command runs; the guard still blocks hook skips, and refuses enforcement changes. It asks you only in the default and plan modes, and refuses in every other mode, accept edits included.
4. List the MCP servers the session loads: `claude mcp list`. Remove or disable any the project doesn't need, above all ones that can write.
5. If you use GitHub Copilot Chat in VS Code: trust the workspace, and keep `chat.useHooks` on and `chat.useClaudeHooks` off (both are the defaults). VS Code runs a workspace's hooks only when it's trusted. Its auto-approve settings decide what Copilot runs without asking; the guard refuses enforcement changes there whatever they say.

**Check:** you know which permission mode the session runs in, and every MCP server listed is one the project needs.

### 3. Install the stack and prove it locally (agent: Phases 0 to 2)

For a new project, first copy `docs/security-setup-prompt.md` and this guide from this repository (each links to the other). Then tell the agent:

> Read docs/security-setup-prompt.md and follow it with me, starting at Phase 0. Show me your plan before each phase and wait for my go-ahead. Stop and ask me wherever the prompt says the owner decides.

[prompts/set-up-a-new-repository.md](prompts/set-up-a-new-repository.md) is a fuller version, which also asks which agents you use and whether your app is Python.

The agent checks your tools and your terminal setup, asks for the blocked names, copies the stack files, pins the actions, hook revisions and CI tools to current versions, and runs the tests and hooks.

**Check:** every test passes; `pre-commit run --all-files` and `uv run bash scripts/check_python.sh` pass; a commit containing a fake secret is refused. In a new Claude Code session, `git commit --no-verify` is refused, and an edit to `.claude/settings.json` asks you (in bypass-permissions mode, it's refused). If you use Copilot Chat in VS Code: **Chat: Configure Hooks** lists `.github/hooks/agent-guard.json`, and its agent is refused both `git commit --no-verify -m test` and adding a line to `.github/CODEOWNERS`.

### 4. First pull request (agent: Phase 3)

The agent opens a PR with the stack. On a first install, the required checks can't run on that PR yet: they run from `main`'s copy of the trusted workflow, which doesn't exist until this PR merges. So the agent first proves the new workflow on a throwaway staging PR, works through Copilot's review of the stack PR (asking for a fresh review after each round of fixes), then merges.

**Check:** on the throwaway PR, every `-staging` job passed on the clean change, and a must-fail commit (a suppression comment plus a workflow job named like a required check) made the staging gate fail for both reasons. Then the stack PR is merged. From then on, every PR runs every required check (step 9 proves it).

### 5. GitHub protections (agent, after your go-ahead: Phase 4)

The ruleset on `main`, which:
- requires a PR, squash merges only;
- requires the security checks from the start, and the app's language check, such as `python`, once it has passed on a real PR, all on an up-to-date branch;
- holds enforcement PRs by other authors for your review, dismissing stale approvals;
- requires every review thread to be resolved before merging;
- has no bypass.

Also read-only workflow tokens, SHA-pinned actions, and Dependabot. The agent also lists the deployment environments and asks whether you use GitHub's coding agent, so you can remove what you didn't set up. To set these yourself in GitHub's settings pages, follow [GitHub settings by hand](#github-settings-by-hand).

**Check:** the agent reads each setting back and shows it to you. `python scripts/github_settings.py` reports nothing short except the deploy environment, which step 8 creates.

### 6. Azure sign-in (you sign in, the agent verifies: Phase 5)

**Check:** you confirm the user, tenant and subscription the agent reads back to you.

### 7. Azure foundation (agent, after you approve its plan: Phase 6)

Two resource groups (one for the app, one for the deploy identity), the region lock, the deploy identity with Contributor on the app resource group only, its federated credential, and the monthly budget.

**Check:** the deploy identity has exactly one role assignment; both region policies are assigned; the budget exists; every name and ID is recorded in `.claude/security-stack.json`.

### 8. Keyless CI sign-in (agent: Phase 7)

A GitHub environment that deploys from `main` only, with four variables and no secrets.

**Check:** the `azure-login-check` workflow runs and prints the app resource group, and `python scripts/github_settings.py` says every setting is at the baseline or stricter.

### 9. Prove the gate on GitHub (agent: Phase 8)

A throwaway draft PR: a clean change passes, and each deliberate weakening is blocked.

**Check:** each result matches the Phase 8 table, and the PR is closed without merging.

### 10. Your own steps (you: Phase 9)

1. In the Azure portal, confirm Entra ID security defaults are on.
2. Create an emergency admin account. Its password never passes through the agent.
3. Decide the enforcement anchor (the prompt's "Remaining risk" section).
4. Review what reaches the project from the cloud:
   - GitHub → Settings → Applications → Installed GitHub Apps: limit each app to the repositories it needs.
   - Your other connectors (file storage, documents and the like): each is a way for code or data to leave GitHub. Keep only what the project needs.
   - Cloud agent environments: their variables are visible to anyone who uses the environment, their setup script runs as root, and their network allowlist decides what code can reach. Keep secrets out of the variables.
   - GitHub's coding agent: if you don't use it, turn it off and delete the `copilot` environment.
5. Record your terminal choices from step 2.

**Check:** each item is recorded as done or still open, in `.claude/security-stack.json` and in the checklist at the end of [security.md](security.md#whats-left-for-you).

## Day to day

- Before any Azure command, `az account show` must show the tenant and subscription recorded in `.claude/security-stack.json`.
- Merge only when every required check passes on the PR's latest commit and every review thread, Copilot's included, has an answer and is resolved; the ruleset won't merge until it is. Never bypass a check.
- Branch names aren't checked for blocked names; commits are, by the git hooks and again on the PR.
- **Approving an enforcement change.** When the agent wants to change an enforcement file, or merge or approve a PR that does, the guard asks you in default or plan mode; in any other mode, such as bypass permissions, it refuses, so switch to default mode (Shift+Tab) to approve, or merge the PR yourself in the browser. Dependabot's PRs that touch enforcement files (a workflow's action pins, or `pyproject.toml`) wait on GitHub for your normal review, unless you let its bumps merge on green (`github.dependabot_merges_on_green` in `.claude/security-stack.json`, a lowering recorded as in [checks-inventory.md](checks-inventory.md#lowering-a-protection)). Then the agent approves and merges them once the checks pass.

## GitHub settings by hand

Step 5 in GitHub's own settings pages, for when you'd rather click than have the agent run Phase 4's commands. The labels are GitHub's. [security-setup-prompt.md](security-setup-prompt.md#phase-4-github-settings) holds the same settings as API calls.

There's nothing to click for CI itself: the workflows in `.github/workflows/` are the pipeline. The required checks run from `main`'s copy of `security-gate.yml`, so they report only after the stack's first PR has merged (step 4).

**Settings → Rules → Rulesets → New branch ruleset:**
1. Name `main`. Enforcement status **Active**. Leave the **Bypass list** empty: not even you.
2. Target branches: **Add target → Include default branch**.
3. Tick **Restrict deletions** and **Block force pushes**.
4. Tick **Require a pull request before merging**, then under it:
   - **Required approvals:** 0.
   - Tick **Dismiss stale pull request approvals when new commits are pushed**, **Require review from Code Owners**, and **Require conversation resolution before merging**.
   - If the page offers an extra approval for commits whose author isn't linked to a GitHub account, tick that too.
   - **Allowed merge methods:** Squash only.
5. Tick **Require status checks to pass**, then **Require branches to be up to date before merging**. Leave **Do not require status checks on creation** unticked. Under **Add checks**, add `secret-scan`, `precommit`, `selftest` and `security-critical-gate`, each with **GitHub Actions** as its source. Add `python` once it has passed on a real PR.

**Settings → Actions → General:**
6. Actions permissions: tick **Require actions to be pinned to a full-length commit SHA**.
7. Workflow permissions: **Read repository contents and packages permissions**, and untick **Allow GitHub Actions to create and approve pull requests**.

**Settings → Advanced Security** (on some plans, **Code security**):
8. Enable **Dependabot alerts** and **Dependabot security updates**.

**Settings → Environments** (step 8 does this):
9. New environment `dev`. Deployment branches and tags: **Selected branches and tags**, with a rule for `main` only.

Four things that catch people out:
- **Conversation resolution is a checkbox under the pull request rule,** not a status check. Typing its name under **Add checks** creates a required check that never reports, and it blocks every PR.
- **GitHub offers a check under Add checks only after it has run once.** A required check that can't run blocks every PR.
- **A check's source matters.** With **GitHub Actions** as the source, another app can't report the same name and satisfy it.
- **Don't add yourself to the bypass list** "just for emergencies". A rule with a standing bypass is a suggestion ([checks-inventory.md](checks-inventory.md#52-no-one-bypasses-the-ruleset)).

To check your work, run `python scripts/github_settings.py`. It reports anything below the baseline.

## Final check

| What | How | Expected |
| --- | --- | --- |
| Tests | `python -m unittest discover -s tests/gate -t .` and the same with `tests/hooks` | all pass |
| Hooks | `pre-commit run --all-files` | all pass |
| Python checks | `uv run bash scripts/check_python.sh` | all pass |
| Guard | in a new Claude Code session: `git commit --no-verify`, then an edit to `.claude/settings.json`, then `gh pr merge` on a PR that changes an enforcement file | the first is refused; the others ask you (refused in bypass-permissions mode) |
| Ruleset | `gh api repos/<owner>/<repo>/rulesets`, then the ruleset by its ID | every check in `required_checks` required, squash only, code-owner review on, review threads resolved before merging, no bypass |
| Actions | `gh api repos/<owner>/<repo>/actions/permissions/workflow` | read-only token; Actions can't approve PRs |
| GitHub settings | `python scripts/github_settings.py` | every setting at the baseline or stricter |
| CI sign-in | `gh workflow run azure-login-check.yml`, then `gh run watch` | the run succeeds, and its log shows the app resource group |
| Deploy identity | `az role assignment list --assignee <principal ID> --all` | exactly one: Contributor on the app resource group |

## What's left

Your decisions and the known limits are in [security.md](security.md), each at the stop it belongs to, with a checklist at the end: [What's left for you](security.md#whats-left-for-you).
