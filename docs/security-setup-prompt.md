# Security setup prompt

A generic, reusable security stack for a GitHub repository that deploys to Azure, and the procedure for an agent (Claude Code or similar) to set it up with the repository owner. Give this file to the agent. Nothing in it is specific to one project: project values live in `.claude/security-stack.json` (decision 10 names the two exceptions). The owner's short, plain-English version of the same setup, with who does each step, is [setup-guide.md](setup-guide.md); the project's security status, stop by stop, is [security.md](security.md).

---

## What the stack is

| Part | Files | What it guarantees |
| --- | --- | --- |
| Required checks, from a workflow the PR can't edit | `.github/workflows/security-gate.yml` | `security-critical-gate`, `secret-scan`, `precommit` and `selftest`, plus the app's language check (here `python`), run as the default branch defines them (`pull_request_target`), so a PR can't rewrite the jobs that judge it |
| Pinned tools | `.github/requirements/*.txt`; `uv.lock` for `python` | Every tool the four security jobs install (zizmor, PyYAML, detect-secrets, pre-commit and all their dependencies) is pinned by file hash, read from the default branch, and installed before any PR file is on disk. The `python` job's tools come from the default branch's `uv.lock`, also pinned by hash, and go in over the PR's own app dependencies (decision 4). One exception: when `precommit` runs, pre-commit installs each hook's own dependencies from PyPI without hashes (the hook repositories themselves are pinned to commit SHAs) |
| Security gate | job `security-critical-gate`: `scripts/security_gate.sh` with `workflow_checks.py`, `baseline_checks.py`, `precommit_hooks.py`, `check_blocked_terms.py` | Automated checks on every PR (below) |
| Secret scan | job `secret-scan`; `.github/workflows/security.yml` for `main` | The files each PR adds or changes; every tracked file on `main` after every merge and daily |
| CI replay of the pre-commit chain | job `precommit`, `.pre-commit-config.yaml` | The whole chain re-runs on every PR, with both the base branch's and the PR's config, so a hook skipped locally can't get a change onto `main`. Hook repositories are pinned to commit SHAs |
| Tests of the gate and the guard | `tests/gate/` (the gate, against a fake GitHub API), `tests/hooks/` (the guard), job `selftest` | The default branch's tests and then the PR's tests run against the PR's code, so the gate or the guard can't be weakened together with their tests. `selftest` runs only these two folders; the app's own tests change with its behaviour, so they run in the app's own job. |
| GitHub settings check | `scripts/github_settings.py` | Compares the ruleset, the Actions permissions, Dependabot and the deploy environment with Phase 4's baseline, using the project values; a stricter setting passes. `--apply` raises what falls short and never lowers a stricter setting (Phase 4) |
| Staging copy | `scripts/staging_workflow.py` | A throwaway `pull_request` copy of the trusted workflow, to test a change to it on GitHub before it merges (Phase 3) |
| Agent guard | `.claude/settings.json`, `.claude/hooks/block_hook_bypass.py`, `.github/hooks/agent-guard.json` | In any Claude Code session that loads this repository's settings, local or cloud, agents can't skip git hooks, and every change to enforcement asks the owner first. In GitHub Copilot Chat's agent in VS Code, the same guard refuses those changes instead of asking. Not in the Copilot CLI or the Copilot cloud agent. It fails closed ([The agent guard](#the-agent-guard)). Commits made through a connector or the web editor run no hooks and no guard; the CI replay covers them |
| Owner approval | `.github/CODEOWNERS`, the ruleset's code-owner review | The enforcement files are listed once, in CODEOWNERS. The guard reads the list; on GitHub, a PR that touches one waits for the owner's review when its author isn't a code owner (Dependabot, or an agent with its own account) |
| Blocked names | `.github/blocked-terms.txt` | Listed company or other names never reach the default branch. The git hooks check each commit's files, paths and message as it's made; the gate checks every PR's file contents, paths, PR text and commits. Branch names aren't checked. Stored as hashes, so the list never contains the names |
| Security-critical paths | `.github/security-critical-paths.txt` | Which paths are reported as security-critical; areas without their own test yet are listed in the gate's summary |
| Keyless Azure sign-in | `.github/workflows/azure-login-check.yml` | CI signs in to Azure with OIDC; no stored credential exists |
| Repository basics | `.gitignore`, `.gitattributes`, `.env.example`, `.secrets.baseline`, `.github/SECURITY.md`, `.github/dependabot.yml` | Secret files ignored, LF line endings, the scan baseline, reporting policy, action pins and the Python packages in `uv.lock` kept current (weekly, with a seven-day cooldown) |
| Python toolchain | `pyproject.toml`, `uv.lock`, `.python-version`, `scripts/check_python.sh`, `scripts/check_file_length.py`, `tests/conftest.py`, and the app skeleton the checks run on (`src/app/`, `tests/fakes/`, `tests/behaviour/test_composition.py`); job `python`; job `dependency-audit-main` in `.github/workflows/security.yml` | The app's lint (ruff, with `noqa` comments ignored), format, strict types (basedpyright, with type-ignore comments switched off), tests (a skipped or expected-to-fail test fails the run), 80% coverage of changed lines, unused or undeclared packages, dead code and known vulnerabilities. The `python` job runs the default branch's copy of `scripts/check_python.sh` against the PR's code; the same script runs locally. uv resolves no package version uploaded in the last seven days. At commit, ruff lint and format run too, and app files stay under 500 lines. `main`'s packages are audited daily |
| Agent rules | `AGENTS.md`, `CLAUDE.md` | The rules every coding agent reads: the one rule, scope and untrusted content, what to do when stopped, locked down by default, the working rules and the inventory rule. `CLAUDE.md` holds only `@AGENTS.md`, so Claude Code loads the same file. Both are enforcement files |
| Checks inventory | `docs/checks-inventory.md` | Every check, what it stops, how to adopt it and how to lower it. Recount it for the new repository with its "How to recount" commands, and keep it current (the inventory rule in `AGENTS.md`) |
| Project values | `.claude/security-stack.json` | Repository, required check names, Azure IDs, region, resource names, the network allowlist, setup status |
| Agent skill | `.claude/skills/security-setup/SKILL.md` | Loads this procedure and the project values when security work comes up |

**The one rule: agents never skip or change enforcement without the owner's approval.** Enforcement is the files listed in `.github/CODEOWNERS` (the hooks, the guard, the gates and what they read), Claude Code's and VS Code's settings files, and the repository's rules and settings on GitHub. The guard holds the rule wherever an agent works through Claude Code, or through Copilot Chat in VS Code, merges included: merging or approving a PR that changes an enforcement file asks the owner in Claude Code, and is refused in Copilot Chat, where a prompt can't be relied on to reach the owner. On GitHub, the ruleset holds it for PRs whose author isn't a code owner ([The owner's approval](#the-owners-approval)). Everything else merges when the checks pass.

### The agent guard

`.claude/hooks/block_hook_bypass.py`, registered in `.claude/settings.json`, runs before every tool call in a Claude Code session that loads this repository's settings. Registered in `.github/hooks/agent-guard.json`, it also runs before every tool call by GitHub Copilot Chat's agent in VS Code.

- **Blocks hook skips outright:** `--no-verify`, `-n`, every bash and PowerShell way of setting `SKIP`/`HUSKY`/`GIT_CONFIG_*` (also for a child process started by inline code), `core.hooksPath`, aliases that hide a bypass, `pre-commit uninstall`, any non-read-only command on a path inside `.git/`, and an agent's commit while the clone's git hooks aren't installed. A session-start hook installs them.
- **Asks the owner before any change to enforcement:** file edits; shell writes, deletes, moves, copies and links, following variables, loops, directory changes and subshells; inline code that writes files; patches (`git apply`, `git am`, `patch`); every `gh` write except everyday work on issues, PRs, labels, branches and workflow runs; connector tools that touch enforcement files or repository settings; and merging or approving a PR that changes an enforcement file (renaming one away counts), however it's done (the owner can let Dependabot's bumps through: [The owner's approval](#the-owners-approval)). It asks only in the default and plan permission modes, and refuses in every other mode, bypass permissions and accept edits included.
- **Keeps Azure commands in the project's tenant:** every `az` command must run in the tenant recorded in `.claude/security-stack.json` (the one named with `--tenant`, or else the signed-in one), or it's refused. An `az` command that isn't a read (show, list, what-if, ...) asks the owner, because Azure changes go through the checkpoint. So do downloads, which write local files, and `az` run from inline code, whose tenant can't be checked. A sign-in followed by another `az` command in the same call is refused. Signing in and the CLI's own setup (`az login`, `az account set`, `az bicep`) need neither. Until a tenant is recorded (Phase 5), only the approval applies; a recorded tenant that can't be read fails closed.
- **Keeps the owner's sign-ins out of reach:** it refuses a command that reads or copies `~/.azure`, `~/.ssh`, `~/.config/gh`, `~/.aws`, `~/.docker/config.json` or a `.env` file other than an example, in bash or PowerShell and in any letter case; inline code that names one; an edit to one; a Copilot Chat search that could reach one; and a command that prints a token (`gh auth token`, `gh auth status --show-token`, `az account get-access-token`, `aws configure export-credentials`). Deny rules in `.claude/settings.json` stop Claude Code's own reads of the same files in every permission mode. Those logins are what an attacker would most want from the agent.
- **Asks before data leaves:** a web request that sends data, uploads a file, reads a header or cookie from a file, or uses a method other than GET, whatever the host; a request or web fetch to a host that isn't in `network.allowed_hosts` in `.claude/security-stack.json`, or can't be read; `az rest` outside Azure and the allowlist; `gh gist create`; `git push` to a remote other than `origin`, and settings that change where a remote points or a push goes; `scp`, `sftp`, `ssh`, `nc` or `rsync` to another computer; and inline code that opens network connections. Text the agent reads can be written to look like instructions, so the guard, not the agent, decides where data may go.
- **Says what to do next:** every stop tells the agent to say what it needs and recommend a way forward, rather than ask an open question, and tells the owner how to approve (default mode, Shift+Tab) or to do it themselves.
- **Fails closed:** unreadable input, any error, or running out of time (45 seconds, before a runner's own timeout) blocks the tool call, writing a program the hooks run (`python`, `cmd`, a shell) anywhere needs the owner, a second hook blocks when `python` is missing or older than 3.9, and a write target it can't resolve counts as an enforcement path.
- **In Copilot Chat (VS Code):** it checks Copilot's terminal, file edits, patches, file reads, web fetches, tasks and connectors as the Claude Code tools that do the same, and judges any other tool by the files and commands it names. Copilot's auto-approve modes skip prompts, so where the guard would ask it refuses, and it refuses what it can't read, such as an editor command or an extension install. The registration's commands turn a guard that can't start into a block. The Copilot CLI and the Copilot cloud agent read the same file but run its `exit 0` command, so the guard doesn't cover them, nor VS Code's Copilot session target, which uses the CLI's hooks.
- **Its limits:** it can't see inside a script file the agent writes and then runs, or an Azure change made through an SDK or the portal; checking out or merging a branch brings that branch's files; and it's cautious rather than exact, so it sometimes refuses a harmless command (Pitfalls).

**What the security gate refuses.** A PR fails `security-critical-gate` if it:
- **Suppresses a check:** adds a zizmor ignore comment or a detect-secrets allowlist pragma in any file. Only markers written as comments count, so prose about them doesn't; occurrences are counted, so a second marker on an existing line is new.
- **Contains a blocked name** anywhere: the full content of every changed file, file paths, the PR title and description, every commit message. Path-only names are checked in file and folder names only.
- **Weakens the required checks through a workflow:** zizmor findings in any changed workflow; any other workflow with a job that could report a required check name (including through an expression); or, in the trusted workflow, a trigger other than `pull_request_target` with all of `opened, synchronize, reopened, edited`, a required name produced by more or fewer than one job, `if:`, `needs:` or `continue-on-error` on a required job or its steps, write permissions, a PR checkout with persisted credentials, or, in a job that runs PR code, any expression outside a short safe list (so no secret or token in any syntax). Renaming or deleting the trusted workflow also fails.
- **Removes coverage** from a protected list, or renames or deletes one: security-critical path patterns, blocked-name entries, pre-commit hook definitions and the global settings that narrow what runs (adding hooks and bumping `rev` are fine), agent hook registrations and `disableAllHooks` (in `.claude/settings.json` and `.github/hooks/agent-guard.json`), Claude Code's permission deny rules, the required check names in `.claude/security-stack.json`, and test case names.
- **Pins a hook by name:** a hook repository in `.pre-commit-config.yaml`, other than `local` and `meta`, whose `rev` isn't a full commit hash. A tag, branch or short hash is looked up by name, so it can be moved to other code.
- **Changes what the trusted jobs install:** a package added to, removed from or swapped in a pinned tool list, or a list added, renamed or deleted. Only versions and hashes may change.
- **Loosens secret scanning** in `.secrets.baseline`: a detector removed or changed, a custom filter added or widened (detect-secrets' own setting-free heuristics may be added, since new releases add them), or an allowlisted finding added (compared by file, type and hash, not by count).

It fails closed: it refuses to pass on an invalid path regex, a partial file or commit list (the API stops at 3000 files and 250 commits), a file it can't fetch or parse, a helper that can't run, or any unexpected error.

### Two surfaces

| Surface | What it is | What acts there |
| --- | --- | --- |
| Local | Anything started from the owner's terminal: the agent session, its shell and file edits, the connectors it uses from there, the owner's CLI logins | The guard, the git hooks, `.gitignore`. The session's permission mode and MCP servers are the owner's settings (Phase 0, step 5) |
| Cloud | Cloud to cloud: cloud agent sessions and connectors, GitHub's coding agent, GitHub Actions and the ruleset, Azure | The required checks, pinned tools, read-only tokens, SHA-pinned actions, Dependabot, the daily scan, and the ruleset with its code-owner review. In Azure: keyless sign-in, the region lock, the budget, the deploy identity's single role. A cloud Claude Code session also loads the guard and the hooks, if its environment has `python` and pre-commit |

The enforcement sits in the cloud: whatever reaches the default branch has passed the checks, from either surface. A push to any other branch is checked by nothing.

---

## Decisions (settled; don't reopen them)

1. **No manual steps, apart from the one rule.** No review labels, approvals or sign-offs; the owner may work solo. When every required check passes, the owner or the agent merges. A manual step for a solo owner becomes a rubber stamp; an automated check that fails closed doesn't. (A label-based review gate was tried and removed for this reason.) The exception is a change to enforcement: an agent that can change its own checks isn't checked, so that change is the owner's call.
2. **Every required check comes from the default branch's workflow** (`pull_request_target`, which GitHub always runs, and checks out, from the default branch, whatever the PR's base: a PR aimed at a branch carrying an old or weakened copy is still judged by the default branch's). A check defined in a `pull_request` workflow is controlled by the PR it judges: the PR keeps the job name and replaces the steps. `security-critical-gate` never runs PR code; `secret-scan` only reads it; `precommit`, `selftest` and the app's language check (here `python`) must run it, so they check the PR out without credentials, with a read-only token that never reaches PR code, in a repository with no secrets. That is acceptable for a private repository, where only collaborators open PRs. For a public repository, run those three on `pull_request` and accept that a PR controls their steps.
3. **Same-named checks can't outvote a failure.** Verified on GitHub: when a required check fails, the PR stays `BLOCKED` even if a PR-supplied job with the same name passes later. The gate still refuses workflows that could report a required name, so a lookalike can't be merged into the default branch.
4. **Tools come from the default branch, pinned by hash, before PR code lands.** Each trusted job checks out the default branch's `.github/requirements/*.txt`, installs with `--no-deps --require-hashes`, and only then checks out the PR. The app's language check (here `python`) also has to install the PR's own dependencies. So it installs those first, then installs the default branch's tools over them, hash-pinned by its lockfile. Nothing from the PR runs during either install, and the default branch's tools win any name clash.
5. **A tested behaviour can be extended, not silently changed.** `selftest` runs the default branch's tests against the PR's code, so a PR that changes what the gate or the guard does must keep the old tests passing. Change a behaviour in one PR and its test in the next, or keep the old contract.
6. **Checks protect their own inputs.** Protected lists can grow but never shrink, move or disappear, and the baseline can only get stricter.
7. **False positives are restructured, never allowlisted.** A PR can't add a suppression, a secret-scan allowlist entry or a scan filter. (The network allowlist is different: a host is added on purpose, and the guard asks the owner.) Build test values at run time, keep hash-pinned requirement lines in `.txt` files, and otherwise take it to the owner. The only baseline filters are the two added at install time (Phase 1, step 6): one for frozen `rev:` SHAs, as narrow as possible, and the baseline's exclusion of itself.
8. **Local hooks are early warnings; CI is enforcement.** Humans may skip hooks locally; the `precommit` job re-runs them anyway. Agents in Claude Code may not skip them at all, and the guard enforces that. Commits made through a connector or the web editor run no hooks, which is why the CI replay, not the local hooks, is the enforcement.
9. **Keyless Azure.** CI signs in through an OIDC federated credential. The deploy identity lives in its own resource group and can only reach the app resource group, so a deploy can't change its own permissions.
10. **Generic stack, one project file.** No company names anywhere (enforced by the blocked-names check), and no project name in file or folder names (a path-only blocked name). Project values live in `.claude/security-stack.json`, apart from two that the files themselves must carry: the owner's handle in `.github/CODEOWNERS`, and the environment name in `.github/workflows/azure-login-check.yml`.
11. **Commit trailers can't carry evidence.** Squash merges rewrite commit messages, so "this commit ran the hooks" markers don't survive to `main`. The CI replay is what makes skipping hooks pointless.
12. **Start locked down.** Install every check at its baseline setting, and lower nothing during setup, even to get past a failure: fix the cause. Lowering is the owner's decision after setup, done as in [checks-inventory.md](checks-inventory.md#lowering-a-protection). It fits decision 6: the gate refuses a shrinking protected list, so lowering one needs the owner's temporary ruleset bypass (The owner's approval, below).
13. **Pins are checked, not trusted.** Everything fetched by a pin is pinned by a full commit hash or a content hash, and what arrives is checked before it runs, because a pin looked up by name can be moved after it was reviewed. Today that means PR checkouts compare HEAD with the PR's commit, tools install with `--require-hashes`, actions need full commit hashes, and pre-commit hook pins must be full commit hashes.

### The owner's approval

The guard asks the owner, who approves the prompt. That covers changing an enforcement file, changing the repository's rules or settings, and merging or approving a PR that changes an enforcement file. The guard asks only in the default and plan permission modes; in every other mode, bypass permissions and accept edits included, it refuses, and the owner switches to default mode (Shift+Tab) and approves, or does it themselves (merging in the browser, for instance).

On GitHub, the ruleset's code-owner review holds an enforcement PR until the owner approves it, but only when the PR's author isn't a code owner: with zero required approvals, a code owner's own PR merges without review (verified on this repository). So Dependabot's PRs that touch enforcement files (a workflow's action pins, or `pyproject.toml`) wait for the owner's normal review, while PRs opened through the owner's account, the agent's included, rely on the guard. An account of its own for the agent brings its PRs under the review too (Remaining risk, below).

An owner who merges ordinary pull requests on green, without reviewing them, can also let Dependabot's bumps merge on green by setting `github.dependabot_merges_on_green` to `true` in `.claude/security-stack.json`. The guard then lets the agent approve and merge, without asking, a PR in this repository that Dependabot opened and only Dependabot has pushed to, where every change to an enforcement file moves an action's pin in a workflow, or a dependency's version in `pyproject.toml`, to another pin or version of the same action or dependency. It reads the pushes from GitHub's record of the branch's activity. Anything else, or anything the guard can't confirm, still asks. It's off in the baseline, and turning it on is a lowering (decision 12). Keep Dependabot's seven-day cooldown on every ecosystem it updates. It holds back version updates; security updates skip it by design, so a fix for a known vulnerability merges without waiting. Refresh a bump with `@dependabot rebase`, not GitHub's update-branch button: that button's push is the owner's, so the bump would ask again.

A PR the gate refuses by design (a new scan filter or allowlist entry, a package added to a pinned tool list, a protected entry removed, or a tested behaviour and its test changed together) is exactly what a weakening would look like, so restructure it first (decision 7). If it truly must land, the owner adds the repository admin role to the ruleset's bypass list, merges, removes it again, and records why in the PR. The agent changes the ruleset only when the owner approves it in the terminal.

### Remaining risk: GitHub can't tell the agent from the owner

The agent works through the owner's GitHub account, which is an admin and a code owner. So GitHub doesn't hold the agent's enforcement PRs for review, and what stops the agent merging one, or lifting a rule, is the guard. The guard is a brake, not a wall: it can't see inside a script file the agent writes and then runs, and an agent working only through a connector (a Claude chat with the GitHub connector) runs no guard at all. The checks themselves also live in the repository they protect. Closing this needs an anchor the agent can't reach, which is the owner's decision. Record it as `enforcement_anchor` in `.claude/security-stack.json`:

| Option | What it anchors | Cost |
| --- | --- | --- |
| Accept the risk | The guard's prompts, and the owner's reading of each enforcement PR | None |
| A separate GitHub account for the agent | GitHub tells the agent from the owner. With the ruleset as it is, the agent's enforcement PRs wait for the owner's normal review, and its account gets write access, not admin, so it can't change a rule | A second account and its token, used by the agent and its connectors |
| Keep the checks outside the repository | Organization rulesets and required workflows that the project's admins can't edit | A GitHub organization (Team or Enterprise) |

### Standards and compliance

The stack gives a project strong technical controls, but it isn't certified, and it doesn't make the project compliant with SOC 2, ISO/IEC 27001 or similar standards. Those standards audit an organisation, and they expect every change to production to be reviewed by someone other than its author. Out of the box, the stack is set up for one owner (decision 1), so it doesn't separate duties. Before an adopter relies on it for a business, go through the [caveats](enterprise-level-gaps.md#caveats-for-anyone-adopting-this-baseline) with the owner.

---

## Rules for the agent

1. **Check the Azure account before every Azure command.** Read `azure.tenant_id` from `.claude/security-stack.json` (or ask the owner, on a new project). Start every Azure script with:
   ```bash
   export MSYS_NO_PATHCONV=1   # Git Bash on Windows; harmless elsewhere
   [ "$(az account show --query tenantId -o tsv)" = "<tenant-id>" ] || { echo "WRONG TENANT, stopping"; exit 1; }
   ```
   If the CLI holds another login, say so and help the owner sign in again (Phase 5). Never deploy into a tenant the owner didn't name.
2. **Merge on green, and leave enforcement to the owner.** Never use an admin bypass, `--no-verify`, `SKIP=` or any other way past a check, and never weaken a check, a list, the baseline or a suppression to get a PR through. Fix the cause. Change enforcement only with the owner's approval: when the guard asks, the owner answers; when it refuses, stop, tell the owner what you need, why, and what you recommend, say if they need to switch to default mode (Shift+Tab) to approve, and don't look for another way. If a check blocks something the owner wants anyway, stop and tell them, with a recommendation rather than an open question.
3. **Read automated review comments before merging.** Copilot reviews a PR once when it opens and doesn't re-review new commits on its own. After fixing its findings, request a new review (the `request_copilot_review` tool of the GitHub MCP server, or the Reviewers menu), wait for its run to finish, and repeat until nothing valid remains. Reply to every thread and resolve it, fixed or not: the ruleset won't merge a PR with an unresolved thread. Security code usually takes several rounds. For the agent guard, a finding that is one more indirect route to a file (a variable, a loop, a link) falls under its documented limit: fix the cheap, general ones, say so in the thread, and stop rather than grow the guard without end.
4. **Show the plan before creating anything in Azure or changing GitHub settings**, then wait for the go-ahead. Region and repository owner are the owner's decisions.
5. **No stored credentials.** No client secrets, access keys or connection strings in code, CI secrets or chat. GitHub environment values that are identifiers (client, tenant and subscription IDs) are variables, not secrets.
6. **Verify, don't assume.** A hook installed isn't a hook that fires; a role assigned isn't a role confirmed; a check run isn't a check run on the latest commit; a test that passes on Windows hasn't run on the Linux runner. Each phase says how to verify.
7. **Never write a blocked name.** Add names only with `python scripts/check_blocked_terms.py --add "<name>"` (or `--add --paths` for path-only), so the name itself is never written into the repository. The git hooks check each commit's files, paths and message before it's made. Branch names aren't checked, and whatever is pushed is on GitHub before the PR checks run, so choose branch names with care.
8. **Test changes to the trusted workflow before they reach `main`** (Phase 3, step 3). A broken required check blocks every PR, including the one that would fix it.
9. **Report failures plainly**, with the error and cause, then fix and re-verify.

---

## Phase 0: Discover

1. Read `README.md`, any architecture document, and `.claude/security-stack.json` if it exists.
2. Check tools: `git`, `gh` (signed in, `gh auth status`), `python`, `uv`, `pre-commit`, `jq`, `bash`, `az`, and `zizmor` for running the tests locally. Install what's missing with the owner's consent.
3. Check the repository: default branch, private or public, the owner's GitHub plan (rulesets on a private repo need GitHub Pro or a Team organization), existing `.github/` and hooks. Work on a branch.
4. Ask the owner which names must never appear (company names, other codebases, other tenants), and which may appear in content but not in file names.
5. Report the terminal's setup to the owner, and change nothing in it without their go-ahead:
   - Claude Code's permission mode and rules, in `.claude/settings.json`, `.claude/settings.local.json` and the user's `~/.claude/settings.json`. In bypass-permissions mode nothing asks before a command runs; the deny rules still hold, and the guard still blocks hook skips and refuses what it would ask about, as it does in every mode but default and plan.
   - The MCP servers the session loads (`claude mcp list`, and `.mcp.json` if present): for each, whether it can write and whether its package is pinned. Servers unrelated to the project are candidates for removal or for disabling in this project.
   - The logins the agent can act with: `az account show` (tenant, subscription, and the owner's role there) and `gh auth status` (token scopes).

## Phase 1: Install the stack

1. Copy every file in the table above from the reference repository. Don't copy `.claude/security-stack.json` values or `.github/blocked-terms.txt` entries; start both fresh.
2. Fill in `.claude/security-stack.json`: repository, branch, environment name, `required_checks` (the four security job names, plus the app's language check once its toolchain exists, here `python`), `required_checks_in_ruleset_now` (the ones the ruleset requires so far), and `merge_methods` (`["squash"]`). `scripts/github_settings.py` stops without these. Leave `dependabot_merges_on_green` out, or `false`: the baseline starts locked down. Set `network.allowed_hosts`, the sites an agent may reach without asking the owner: start from the reference repository's list (GitHub, the Claude Code and Microsoft docs, PyPI) and add only what the project needs. Azure values come in Phase 6.
3. Set the owner's GitHub handle in `.github/CODEOWNERS`, which lists the enforcement files. These are:
   - Claude Code's two project settings files and its hooks;
   - `.claude/security-stack.json`, the project values the gate and the guard read (the required checks, the Azure tenant);
   - the pre-commit config and the baseline;
   - `.github/` (the guard's Copilot Chat registration included) and `scripts/`;
   - VS Code's workspace settings and tasks (`.vscode/`, and `*.code-workspace` files anywhere in the repository), which can switch Copilot Chat's hooks off or run commands the guard doesn't see;
   - the gate's and the guard's tests (`tests/gate/`, `tests/hooks/`);
   - the files that decide how tests run: `tests/__init__.py`, `conftest.py`, `tests/conftest.py`, `pyproject.toml`, `pytest.ini` and `.pytest.ini`;
   - the agent rules files: `AGENTS.md`, and `CLAUDE.md`, which imports it.

   Add any test folder the project treats as enforcement, such as its access tests. Leave the app's other tests out, so everyday work needs no approval. Keep `.claude/settings.local.json` in `.gitignore` too: it's personal, and a shared copy could switch hooks off for everyone. Set the environment name in `.github/workflows/azure-login-check.yml` if the project's isn't `dev`.
4. Create the blocked-names list: keep the header comment, then `python scripts/check_blocked_terms.py --add "<name>"` for each name, and `--add --paths "<name>"` for path-only names.
5. Pin everything to current versions rather than copying old pins:
   - Actions: `tag=$(gh api repos/actions/checkout/releases/latest --jq .tag_name); gh api repos/actions/checkout/commits/$tag --jq .sha`, for each action.
   - pre-commit hook repositories: `pre-commit autoupdate --freeze` (commit SHAs, with the tag in a `# frozen:` comment).
   - Tool lists in `.github/requirements/`: download the exact Linux files and hash each one, dependencies included:
     ```bash
     pip download <tool>==<version> -d wheels --only-binary=:all: --platform manylinux2014_x86_64 \
       --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 --platform any \
       --python-version 3.12 --implementation cp --abi cp312 --abi abi3 --abi none
     sha256sum wheels/*   # one "name==version --hash=sha256:..." line per file
     ```
     Check each package's PyPI JSON: for compiled packages, confirm there is only one Linux x86-64 build for Python 3.12, or list the hash of every such build.
   - The Python toolchain: `uv lock --upgrade`, which keeps the seven-day cooldown set in `pyproject.toml`. Then keep the ruff hook's `rev` in `.pre-commit-config.yaml` at the same ruff version as `uv.lock`.
6. Generate the secrets baseline, with the one narrow filter for frozen hook SHAs:
   ```bash
   detect-secrets scan --exclude-files '^\.secrets\.baseline$' \
     --exclude-lines '^rev: "[0-9a-f]{40}"\s+# frozen: v[0-9][0-9.]*$' > .secrets.baseline
   ```
   Review every finding with the owner; remove real secrets rather than accepting them.
7. Scan the repository for blocked names before committing: `git ls-files -z | xargs -0 python scripts/check_blocked_terms.py` (NUL-separated, so paths with spaces are checked correctly).

## Phase 2: Prove it locally

1. `python -m unittest discover -s tests/gate -t .` and `python -m unittest discover -s tests/hooks -t .`: every test passes.
2. `pre-commit install -t pre-commit -t commit-msg` (a Claude Code session does this itself when it starts), then `pre-commit run --all-files`: every hook passes.
3. `zizmor --offline .github/workflows/*.yml` and `python scripts/workflow_checks.py --root . --trusted .github/workflows/security-gate.yml --required <each name> .github/workflows/*.yml`: no findings except any transitional duplicate you're about to remove.
4. Prove the hook blocks a real secret. Write a throwaway file with a fake key, stage it, try to commit; the commit must fail and `git log` must be unchanged. Then unstage and delete it:
   ```bash
   fake=$(python -c "import os,base64;print(base64.b64encode(os.urandom(64)).decode())")
   printf 'CONN="DefaultEndpointsProtocol=https;AccountName=test;AccountKey=%s;EndpointSuffix=core.windows.net"\n' "$fake" > leak_test.py
   ```
5. The agent guard loads when a Claude Code session starts. In a new session, `git commit --no-verify` must be refused, and an edit to `.claude/settings.json` must ask the owner (in bypass-permissions mode, be refused). If the owner uses Copilot Chat in VS Code: trust the workspace, check that **Chat: Configure Hooks** lists `.github/hooks/agent-guard.json`, then ask Copilot Chat's agent to run `git commit --no-verify -m test`, and to add a line to `.github/CODEOWNERS`. Both must be refused, with the guard's "Blocked:" message. Repeat this after VS Code updates.
6. The Python checks: `uv sync`, then `uv run bash scripts/check_python.sh`. Lint, format, types, tests, changed-line coverage, dependencies, dead code and known vulnerabilities must all pass.

## Phase 3: Pull request and merge

1. Commit (hooks on) and push. Open the PR.
2. The trusted workflow always runs from the default branch, so the PR that adds or changes it is judged by the old version, or by nothing on a first install.
3. **Prove the new trusted workflow before merging.** GitHub runs `pull_request_target` from the default branch whatever the PR's base, so a new version can't be tried through that trigger. Run a `pull_request` copy of it instead, on a throwaway PR whose base is a staging copy of the change (so the gate sees only the test commits):
   ```bash
   git push origin <branch>:stage/<name>                      # the change, as a base branch
   git switch -c test/<name> <branch>
   python scripts/staging_workflow.py                         # writes .github/workflows/staging-check.yml
   # ...also commit a clean change to a security-critical path, push...
   gh pr create --draft --base stage/<name> --head test/<name> --title "test: staging check (do not merge)"
   ```
   Every `-staging` job must pass, with the tool installs, both pre-commit runs and every test visible in the logs. Then push one commit that must fail (a suppression comment plus a workflow with a job named like a required check) and confirm the staging gate fails for both reasons. Close the PR and delete both branches. Never test with a real blocked name: pushed commits and closed PRs keep it in the repository's history.
4. Watch the real PR's checks until they finish on its latest commit (`gh pr checks <n> --watch`, and compare the run's head SHA with the PR's). A failure is a problem to fix, not to wait out.
5. Work through Copilot's review (rule 3), then squash-merge.

## Phase 4: GitHub settings

With admin access, do these through the API and read each back; otherwise walk the owner through the same settings in the browser, one at a time.

1. **Ruleset on the default branch**, after the Phase 3 merge (a ruleset requiring checks that can't yet run blocks every PR):
   ```bash
   cat > ruleset.json <<'EOF'
   {"name": "main", "target": "branch", "enforcement": "active", "bypass_actors": [],
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [
      {"type": "deletion"}, {"type": "non_fast_forward"},
      {"type": "pull_request", "parameters": {"required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true, "require_code_owner_review": true,
        "require_last_push_approval": false, "required_review_thread_resolution": true,
        "require_extra_approval_for_unattributed_changes": true, "allowed_merge_methods": ["squash"]}},
      {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "secret-scan", "integration_id": 15368}, {"context": "precommit", "integration_id": 15368},
          {"context": "selftest", "integration_id": 15368}, {"context": "security-critical-gate", "integration_id": 15368}]}}]}
   EOF
   gh api -X POST repos/<owner>/<repo>/rulesets --input ruleset.json
   ```
   Once the app has a language check (here `python`), add it to `required_status_checks` as well, and to `required_checks_in_ruleset_now`. Do this only after it has passed on a real PR: a required check that can't run blocks every PR. `15368` is the GitHub Actions app. Zero approvals, so ordinary PRs merge on green; Code Owner review on, so an enforcement PR by an author who isn't a code owner waits for the owner (a code owner's own PR needs no review; [The owner's approval](#the-owners-approval)); stale approvals dismissed, so an approval covers only the code the owner read; every review thread resolved before merging, so a review finding can't be passed over unanswered; one more approval for a commit whose author isn't linked to a GitHub account. An empty bypass list means the rules bind admins and agents too. Allow rebase merges as well if the owner stacks PRs.
2. **Actions:** read-only workflow token, Actions may not approve PRs, SHA pinning required:
   ```bash
   gh api -X PUT repos/<owner>/<repo>/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false
   gh api -X PUT repos/<owner>/<repo>/actions/permissions -F enabled=true -f allowed_actions=all -F sha_pinning_required=true
   ```
3. **Dependabot:** `gh api -X PUT repos/<owner>/<repo>/vulnerability-alerts` and `gh api -X PUT repos/<owner>/<repo>/automated-security-fixes`. Turn on secret scanning and push protection too if the plan offers them for private repositories.
4. Verify: `gh api repos/<owner>/<repo>/rulesets/<id>`, `.../actions/permissions`, `.../actions/permissions/workflow`, `.../automated-security-fixes`. `python scripts/github_settings.py` checks all of this and the deploy environment in one read-only run, and exits 0 only when every setting is at the baseline or stricter. Phase 7 creates the environment, so until then the script reports it as missing and exits 1; everything else it reports must be fixed now. With `--apply`, it sets what falls short from `.claude/security-stack.json`, including the ruleset of steps 1 to 3, and never lowers a stricter setting. It requires only the checks in `required_checks_in_ruleset_now`, so a check that hasn't run yet can't block every PR.
5. List the deployment environments (`gh api repos/<owner>/<repo>/environments --jq '.environments[].name'`) and report any the owner didn't create. GitHub's coding agent (Copilot) creates one named `copilot` with no protection rules, and works on the repository from the cloud. Ask the owner whether they use it; if not, they turn it off in the repository's Copilot settings, and the `copilot` environment is deleted with their go-ahead.

## Phase 5: Azure sign-in (support the owner)

The owner signs in; the agent prepares and verifies.

1. Show what the CLI holds: `az account show`. If it's a login the owner doesn't recognise or no longer uses, ask, then `az logout && az account clear`.
2. If the owner also uses another Azure account on this machine, offer a separate CLI profile: `export AZURE_CONFIG_DIR="$HOME/.azure-<project>"`.
3. Start the sign-in in the background and tell the owner a browser tab is opening:
   ```bash
   AZURE_CORE_LOGIN_EXPERIENCE_V2=off az login --only-show-errors \
     --query "[].{subscription:name, tenant:tenantId, user:user.name}" -o table
   ```
   No tab? Use `--use-device-code` and relay the code. A guest in several tenants? `az login --tenant <id>`.
4. Read back the user, tenant and subscription and have the owner confirm them. Record the tenant ID in `.claude/security-stack.json`.
5. Survey without changing anything: offer type (free trial or pay-as-you-go) and spending limit, the owner's role, resource groups, resources, registered providers.
6. Ask the owner for the region (it must offer every service the project uses and is hard to change later) and confirm the repository owner/name (the CI sign-in is tied to it exactly).

## Phase 6: Azure setup

Show the plan, get the go-ahead, then run each step with the tenant check.

1. Register providers: `Microsoft.CognitiveServices`, `Microsoft.Search`, `Microsoft.Sql`, `Microsoft.Storage`, `Microsoft.KeyVault`, `Microsoft.ManagedIdentity`, `Microsoft.Security`, `Microsoft.OperationalInsights`, `Microsoft.PolicyInsights` (`az provider register -n <ns> --wait`).
2. Create two resource groups, `rg-<project>-dev` (app) and `rg-<project>-ci` (deploy identity only), tagged `project=<project>`.
3. Region lock at subscription scope: **Allowed locations** (`e56962a6-4747-49cd-b67b-bf8b01975c4c`) and **Allowed locations for resource groups** (`e765b5de-1225-4ba3-bd56-1ac6695af988`), each with `listOfAllowedLocations` set to the region.
4. Create the user-assigned identity `id-<project>-gh-deploy` in the CI resource group.
5. Federated credential: issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`, and the subject exactly as GitHub presents it. GitHub now includes the owner's and repository's numeric IDs, `repo:<owner>@<owner_id>/<repo>@<repo_id>:environment:<env>`, so a renamed or recreated repository with the same name can't inherit the login. Get the IDs with `gh api repos/<owner>/<repo> --jq '.owner.id, .id'`. If the Phase 7 check fails with `AADSTS700213`, the error message quotes the subject GitHub presented; set the credential to exactly that.
6. **Contributor** on the app resource group only (`--assignee-object-id <principalId> --assignee-principal-type ServicePrincipal`), retrying every 15 seconds while the new identity propagates.
7. Budget that notifies the subscription's Owner role (no email address to store):
   ```bash
   az rest --method put --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.Consumption/budgets/monthly-guardrail?api-version=2023-05-01" --body @budget.json
   ```
   with a monthly amount and notifications at 50%, 80% and 100% actual and 100% forecast, each `"contactRoles": ["Owner"]`.
8. Defender for Cloud's free plan assigns its cloud security benchmark initiative (`SecurityCenterBuiltIn`) to the subscription once Defender for Cloud is on. Confirm it: `az policy assignment list --query "[?name=='SecurityCenterBuiltIn'].displayName" -o tsv`. If it's missing, the owner opens Defender for Cloud for the subscription in the portal once. It audits and warns; it blocks nothing.
9. Verify: exactly one role assignment on the identity, the two region policies and the benchmark initiative assigned, resource groups in the region, budget present. Record every name and ID in `.claude/security-stack.json`.

Don't create app resources (SQL, Search, OpenAI, Storage, Key Vault) by hand. They belong in infrastructure code, where the gate and an infrastructure scanner cover them.

## Phase 7: CI sign-in to Azure

1. Create the GitHub environment, deployable from the default branch only:
   ```bash
   echo '{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}' \
     | gh api -X PUT repos/<owner>/<repo>/environments/<env> --input -
   gh api -X POST repos/<owner>/<repo>/environments/<env>/deployment-branch-policies -f name=main -f type=branch
   ```
2. Environment variables (not secrets): `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP` (`gh variable set <NAME> --env <env> --body <value>`).
3. Run `gh workflow run azure-login-check.yml`, wait for it, and confirm it printed the resource group. That proves the keyless sign-in end to end.
4. Run `python scripts/github_settings.py`: with the environment in place, it must exit 0.

## Phase 8: Prove the gate on the default branch

On a throwaway branch and draft PR, one commit per scenario, waiting for the checks on each new head SHA. Close the PR without merging.

| Scenario | Expected |
| --- | --- |
| A clean change to a security-critical path outside CODEOWNERS (such as the architecture document) | all checks pass; merge state `CLEAN` (after `gh pr ready`) |
| A clean change to an enforcement file, from the owner's account | all checks pass; `CLEAN`, since the author is a code owner. In a session, the agent's `gh pr merge` must ask the owner (in bypass-permissions mode, be refused) |
| An added detect-secrets allowlist pragma comment | gate fails ("new check suppressions"); `BLOCKED` |
| A removed line in the path list | gate fails ("patterns removed"); `BLOCKED` |
| A new workflow with a job named like a required check | gate fails ("could report a required check name"); `BLOCKED` |

Blocked names aren't tested here: a real one pushed to a branch stays in the repository's history (Phase 3, step 3). `selftest` covers that rule, like every other gate rule, against a fake API on each PR; this phase proves the wiring on GitHub itself. If you combine several weakenings in one commit, expect `selftest` to fail as well: the default branch's tests run against the PR's weakened files. That's a second layer catching the same change, not noise.

## Phase 9: Owner-only steps and handoff

Walk the owner through what needs their identity, one at a time:
1. Entra ID → Overview → Properties → **Manage security defaults**: confirm **Enabled** (MFA for everyone). The CLI's token can't read this setting.
2. An emergency Global Administrator (`breakglass@<tenant>.onmicrosoft.com`) with a long random password kept offline and, ideally, a FIDO2 key. The owner creates it; its password must never pass through the agent.
3. The enforcement-anchor decision (Remaining risk, above).
4. Cloud access. The agent's CLI token can't read these, so the owner reviews them:
   - GitHub → Settings → Applications → Installed GitHub Apps: each app an agent reaches GitHub through, limited to the repositories and permissions the project needs. A connector's tools may include merging, deleting branches and deleting repositories; only the default branch's ruleset limits them.
   - The owner's other connectors (file storage, documents, mail and the like): each is a way for code or data to leave GitHub. Keep only what the project needs.
   - Cloud agent environments: their variables are visible to anyone who uses the environment, their setup script runs as root, and their network allowlist decides what code can reach. No secrets in the variables; the setup script installs `python` and pre-commit, so the guard and the hooks can run.
   - GitHub's coding agent (Phase 4, step 5).
5. The terminal choices from Phase 0, step 5: the permission mode, any deny rules, and which MCP servers stay. Optionally, a managed settings file that also registers the guard: it needs administrator rights to change, and `disableAllHooks` can't switch it off, but it applies to every project on the computer.

Finish with the status in `.claude/security-stack.json` (done and verified, done by the owner, still open), and write the project's security document (`docs/security.md` in the reference repository): each stop a change passes through, what protects it, its status, and a checklist of what's left for the owner. Add the next security items for the project's upcoming phase.

---

## Pitfalls

| Pitfall | Fix |
| --- | --- |
| **Azure CLI** | |
| Git Bash rewrites arguments starting with `/` or containing `rev:path`, so `--scope /subscriptions/...` fails with `MissingSubscription` and `git show origin/main:file` fails | `export MSYS_NO_PATHCONV=1` |
| `az login` in a non-interactive shell hangs on the subscription picker | Run it in the background with `AZURE_CORE_LOGIN_EXPERIENCE_V2=off` |
| An old login's refresh token expired (`AADSTS700082`) | `az logout && az account clear`, sign in again |
| The CLI can't read Entra policies (`AccessDenied`) | The owner checks in the portal |
| A new identity's role assignment fails for a minute; the output shows the role as `None` | Retry every 15 s; confirm with `az role assignment list --assignee <principalId> --all` |
| CI sign-in fails with `AADSTS700213: No matching federated identity record` | GitHub's OIDC subject includes numeric owner and repository IDs (`repo:<owner>@<id>/<repo>@<id>:environment:<env>`); set the credential's subject to the one quoted in the error (Phase 6, step 5) |
| **Rulesets and required checks** | |
| A ruleset created before the trusted workflow is on the default branch blocks every PR | Merge the stack first, then create the ruleset |
| A required check never starts (GitHub occasionally drops an event); the PR sits `BLOCKED` | Push any commit to trigger the checks again |
| A **skipped** required check counts as passed | No `if:`, `needs:` or `continue-on-error` on required jobs or their steps (the gate enforces this) |
| A required check defined in a `pull_request` workflow can be faked by the PR | Define every required check in the `pull_request_target` workflow (decision 2) |
| Moving a required check to another workflow leaves the PR that moves it with no producer for that check | Two steps: add the new job under the same name while the old one still runs, prove it (Phase 3, step 3), remove the old one in the next PR. Never loosen the ruleset to get through |
| Two jobs reporting the same required name | Verified: a failure blocks even if the other passes later. Keep one producer per name anyway; the gate refuses others |
| `pull_request_target` always runs the default branch's workflow file and checks out the default branch, whatever the PR's base, so neither the PR that changes the trusted workflow nor a staging base branch can try the new version | A `pull_request` copy (`scripts/staging_workflow.py`) on a throwaway PR (Phase 3, step 3) |
| Rulesets on a private repo on the free plan save but aren't enforced | GitHub Pro or a Team organization; check for the warning banner |
| **The GitHub API** | |
| The API returns the previous head's files right after a push | Wait until the run's head SHA equals the PR's head SHA |
| The files API stops at 3000 files and the commits API at 250 commits | Compare with the event's `changed_files` and `commits`; refuse on a mismatch |
| A contents URL with a space, `#`, `%` or `?` in the file name fetches the wrong file | URL-encode each path segment |
| A fork PR's head commit may not fetch by SHA from the base repository | Check out `refs/pull/<number>/head`, then confirm `git rev-parse HEAD` equals the event's head SHA |
| Copilot doesn't re-review new commits | Request a review again (rule 3) |
| **Supply chain** | |
| A tool installed by version only runs whatever PyPI serves, dependencies included | Hash-pinned lists with `--no-deps --require-hashes`, every dependency listed (Phase 1, step 5) |
| A pin looked up by name (a tag, a branch, a short hash) can be moved to other code after it was reviewed | Pin by a full commit hash or a content hash, and check what arrives before it runs (decision 13) |
| pre-commit hook repositories pinned by tag can be moved upstream | `pre-commit autoupdate --freeze`, which writes full commit hashes; the gate refuses any other pin |
| Frozen `rev:` SHAs are flagged as high-entropy secrets | The one narrow baseline filter (Phase 1, step 6); it still flags a `rev:` without the `# frozen:` comment |
| Hash-pinned requirement lines inside a YAML block are flagged as a secret keyword (`detect-secrets==...`) | Keep requirement lines in `.txt` files, where they aren't flagged |
| Running the PR's code before the default branch's tests lets it tamper with them | Run the default branch's tests first |
| **The gate and the guard** | |
| zizmor always flags `pull_request_target` | The trusted workflow's trigger carries the one accepted zizmor ignore comment, with its reason; any other new suppression fails the gate |
| A doc that quotes a suppression marker fails the gate | Markers count only as comments; describe them in prose |
| Test fixtures containing a literal suppression comment trip the gate on every PR that touches them | Assemble markers from parts (`"# pragma: " + "allowlist secret"`) |
| A second suppression on a line that already has one | Count occurrences, not lines |
| Names in unchanged lines, or split across a line break | Scan the full content of every changed file, normalised as one string |
| Binary files crash a text scan | Read bytes and decode leniently |
| `\|\| true` after a check hides a crash as "nothing found" | Helpers exit 0 clean, 1 found, 2 couldn't run; the gate stops on 2 |
| A bash `ERR` trap doesn't fire inside functions, or loses its message when stdout is redirected | `set -E`, and print the message to stderr |
| An unquoted YAML value containing `: ` (such as `--only-binary :all: --require-hashes`) is invalid | Use a block scalar (`run: \|`); the structure check refuses to pass on invalid YAML |
| A guard that pattern-matches raw command text blocks harmless commands and misses real ones | Parse the command; allow a read-only list for `.git/` paths and refuse everything else, including redirects |
| An inline git alias hides a bypass (`git -c alias.x='commit --no-verify' x`) | The guard refuses inline aliases, and persistent ones that skip hooks or run a shell |
| A bypass nested in another command (`bash -c '...'`, `pwsh -EncodedCommand ...`, `cat <<EOF \| sh`) | The guard parses the nested command, decoding encoded PowerShell, and checks code for interpreters conservatively. A script file it can't see (`bash script.sh`) is the CI replay's job |
| Matching credential expressions by pattern misses other syntaxes (`github['token']`, `toJSON(github)`) | In jobs that run PR code, allow only a short list of safe expressions and refuse everything else |
| Automated reviewers may describe `pull_request_target` as running from the PR's base branch | Verified on GitHub (see decision 2): it runs, and checks out, the default branch |
| The agent guard only loads when a Claude Code session starts | Start a new session after installing it |
| A guard whose error or missing interpreter counts as "allow" lets everything through | Fail closed: the guard blocks on bad input or any error, and a second hook blocks when `python` is missing or older than 3.9 |
| The guard asks the owner only in the default and plan permission modes | In every other mode, bypass permissions and accept edits included, it refuses instead. The owner switches to default mode (Shift+Tab) and approves, or makes the change |
| A request to a site the project needs, such as a new documentation site or package index, stops at the guard | Add the host to `network.allowed_hosts` in `.claude/security-stack.json` (an enforcement file, so the guard asks the owner), or approve the one request in default mode |
| The guard refuses a harmless command: it's cautious with inline code that runs other commands or writes files and names an enforcement folder | Don't work around a refusal, not even an apparent false positive: stop and tell the owner. Plan routine work so it doesn't trip the guard, with plain commands rather than inline scripts that name `.claude`, `.github`, `scripts` or `tests` |
| Code-owner review with zero required approvals doesn't hold a code owner's own PR (verified here), and the agent uses the owner's account | The guard gates the agent's merges and approvals of enforcement PRs; an account of its own for the agent brings its PRs under the review ([The owner's approval](#the-owners-approval)) |
| A commit made through a connector or the web editor runs no hooks and no guard | Expected: the CI replay covers PRs into the default branch. Never push a blocked name to any branch (rule 7) |
| **Agent shells and local testing** | |
| Heredocs with nested quotes or embedded scripts fail to parse in some agent shells, and the guard parses heredocs too | Write files with the editor tool |
| Chains of `sleep` are refused by some agent shells | Poll with `until <condition>; do sleep 5; done` or `gh pr checks --watch` |
| `jq` on Windows writes CRLF; `python3` may not exist; Windows can't create file names containing `?` | CI runs on Linux; the tests shim `jq` on Windows and pass `PYTHON` |
| A test probe with a duplicated YAML key silently drops the first value | Give each probe value its own mapping |
| Temporary "wip" commits pushed to test something | Test locally with `tests/`, or on a staging branch; push only real commits |
