# Security

How a change reaches `main` and Azure, what protects it at each stop, and what's still open. This is the one place for the project's security status. The other documents link here:

- [setup-guide.md](setup-guide.md): how to build all of this again, step by step.
- [security-setup-prompt.md](security-setup-prompt.md): the procedure an agent follows to set it up, for any project.
- [architecture.md](architecture.md#10-security): the product's security measures, phase by phase.
- [stack.md](stack.md): what the project is built with, and what its code does.

## The one rule

**Agents never skip or change enforcement without your approval.** Enforcement means the files listed in `.github/CODEOWNERS`: the hooks, the agent guard, the gates and what they read, the tests of the gate and the guard, the access tests, the files that decide how tests run, the agent rules files (`AGENTS.md`, and `CLAUDE.md`, which imports it), the instructions agents are handed (the Claude Code skills, the setup prompt and the prompt templates), the audit records (the checks inventory, the control mapping and the AI risk mapping), and VS Code's workspace settings and tasks (`.vscode/` and workspace files). It also means Claude Code's and VS Code's settings files, and the repository's rules and settings on GitHub. Every other change merges when the checks pass.

How you approve:

- **In your terminal:** the agent guard asks you before an agent changes enforcement, or merges or approves a pull request that does. It asks only in the default and plan permission modes. In every other mode, bypass permissions and accept edits included, it refuses: switch to default mode (Shift+Tab) and approve, or do it yourself.
- **On GitHub:** a pull request that changes an enforcement file waits for your review when its author isn't you (Dependabot, or the agent once it has its own account). Pull requests through your own account don't wait on GitHub; for those, the guard is what asks.
- **What to expect:** anything that sends data out, or reaches a site that isn't on the allowlist, stops too. In default mode that means more prompts; in any other mode, more refusals. Each stop says what the agent needs and what it recommends: approve in default mode (Shift+Tab), or add the site to the allowlist (`network.allowed_hosts` in `.claude/security-stack.json`), which asks you first.

## The flow

Work starts in one of two places. Both meet at one checkpoint before anything reaches `main`. That checkpoint carries three kinds of change: code, infrastructure and agent configuration.

| Term | Meaning |
| --- | --- |
| **Local** | Anything started from your terminal: Claude Code on your computer, the connectors it uses from here, your commits and pushes. |
| **Cloud to cloud** | An agent working in the cloud (a Claude chat with connectors, a cloud Claude Code session, GitHub's coding agent) that writes to GitHub from there. Nothing runs on your computer. |
| **The checkpoint** | The pull request into `main`: its five required checks, and your approval where the rule needs it. Both paths pass through it. |

```text
                  LOCAL                              CLOUD TO CLOUD
     ┌─────────────────────────────┐         ┌─────────────────────────────┐
     │        Your terminal        │         │         Cloud agent         │
     │   [x] the guard runs here   │         │      runs in the cloud      │
     │ [x] asks before enforcement │         │   [!] connector: no guard   │
     └──────────────┬──────────────┘         └──────────────┬──────────────┘
                    │ edits files              writes files │
                    ▼                                       ▼
     ┌─────────────────────────────┐         ┌─────────────────────────────┐
     │   Commit on your computer   │         │    Commit from the cloud    │
     │ [x] commit checks run here  │         │  [!] connector: no checks   │
     └──────────────┬──────────────┘         └──────────────┬──────────────┘
                    │ git push                  push or API │
                    └───────────────────┬───────────────────┘
                                        ▼
                    ┌───────────────────────────────────────┐
                    │           Branch on GitHub            │
                    │ [!] stored as-is · nothing checks it  │
                    └───────────────────┬───────────────────┘
                                        │ open a pull request
                                        ▼
       ╔═════════════════════════════════════════════════════════════════╗
       ║                     PULL REQUEST INTO MAIN                      ║
       ║               the one checkpoint both paths share               ║
       ║                                                                 ║
       ║                   carries 3 kinds of change:                    ║
       ║           code · infrastructure · agent configuration           ║
       ║                                                                 ║
       ║              [x] 5 required checks, all must pass:              ║
       ║               secret-scan · precommit · selftest                ║
       ║                 python · security-critical-gate                 ║
       ║                                                                 ║
       ║      [x] your approval, if it changes an enforcement file       ║
       ║      (asked by the guard, or by GitHub for other authors)       ║
       ║  [!] not enforced from a cloud connector, which runs no guard   ║
       ╚════════════════════════════════╤════════════════════════════════╝
                                        │ merges only when all 5 pass
                                        │ and you approve, where needed
                                        ▼
                                  ┌───────────┐
                                  │   main    │
                                  └─────┬─────┘
                                        │ deploys (not built yet)
                                        ▼
                       ┌─────────────────────────────────┐
                       │         [ ] Deploy job          │
                       │  applies all 3 kinds of change  │
                       └────────────────┬────────────────┘
                                        │
                                        ▼
                    ┌───────────────────────────────────────┐
                    │                 AZURE                 │
[!] infrastructure  │  [x] resource groups, region, budget  │  [ ] app data
 ──────────────────▶│      [ ] app resources, as code       │◀──────────────────
     (portal, CLI)  │  SQL · Search · storage · Key Vault   │  (documents, feeds)
                    ├───────────────────────────────────────┤
  [ ] agent config  │    [ ] agents in Foundry, as code     │  [ ] role holders
 ──────────────────▶│     instructions · tools · model      │◀──────────────────
  (Foundry portal)  │   identity · permissions · filters    │  (Entra groups)
                    └───────────────────────────────────────┘

         both skip                                             both happen
    the checkpoint                                             at runtime

                 [x] in place     [!] open     [ ] not built yet
```

Status as of 28 September 2026. The diagram marks each stop `[x]` in place, `[!]` open or `[ ]` not built yet. The tables below add a fourth status, **Caught by CI**, for a gap at one stop that the checkpoint covers.

| Status | Meaning |
| --- | --- |
| **In place** | Built and working. |
| **Open** | A gap, or a decision still to make. |
| **Caught by CI** | No check at this stop; the checkpoint covers it. |
| **Not built yet** | Planned for a later phase. |

## Local: starts in your terminal

### 1. The agent works in your terminal

Claude Code runs commands, edits files and uses connectors on your computer.

| Status | What |
| --- | --- |
| **In place** | The guard blocks every known way to skip the commit checks, and changes inside `.git`, in every command Claude Code runs. |
| **In place** | Changes to enforcement ask you first, and so does merging or approving a pull request that changes it. The guard asks only in the default and plan permission modes, and refuses in every other mode, bypass permissions and accept edits included. |
| **In place** | If the guard itself fails, runs out of time, or Python is missing, the command is blocked instead of let through. |
| **In place** | The agent can't read your sign-ins (`~/.azure`, `~/.ssh`, `~/.config/gh`, `~/.aws`, `~/.docker/config.json`) or `.env` files other than examples: Claude Code's deny rules stop its file reads in every permission mode, bypass included, and the guard refuses commands that read them or print a token. Your logins are what an attacker would most want from the agent. |
| **In place** | Sending data out asks you first: a request with a body, an upload or a method other than GET; a request to a site that isn't on the allowlist; a push to a remote other than `origin`; a gist; code that opens a network connection. Text the agent reads can be written to look like instructions, so the guard, not the agent, decides where data may go. |
| **Open** | The guard is a brake, not a wall. It can't see inside a script file the agent writes and then runs, and checking out or merging a branch brings that branch's files. It's cautious rather than exact, so now and then it refuses a harmless command; the agent then stops and tells you. |
| **Open** | The guard is registered in the repository's own settings, so a script could switch it off. An admin-only settings file would stop that, but it applies to every project on this computer. Your decision. |
| **Open** | The permission mode is your choice. In bypass-permissions mode, apart from the deny rules for your sign-ins, the guard is the only brake before a command runs. |
| **Open** | MCP servers configured at user level load in every project on your computer: review each one before adding it, and keep only what the project needs. Your review. |
| **In place** | Every `az` command must run in this project's Azure tenant (the one in `.claude/security-stack.json`), or the guard refuses it. An `az` command that isn't a read (show, list, what-if, ...) asks you first, because Azure changes go through a pull request and the deploy job. |
| **Open** | The agent works with your own Azure and GitHub sign-ins. The guard can't see `az` run from inside a script file, or an Azure change made another way (the portal, an SDK). Keeping your logins away from the agent, and from code that runs as you: [workstation-hardening.md](workstation-hardening.md). |
| **In place** | GitHub Copilot Chat's agent in VS Code goes through the guard too. Its auto-approve modes skip prompts, so there the guard refuses what it would ask you about: make those changes in Claude Code, or yourself. |
| **Open** | Other agents, the Copilot CLI included, don't go through the guard ([coding-agents.md](coding-agents.md)). Their commits still run the commit checks. |

### 2. Commit on your computer

Git runs the commit checks before the commit is saved.

| Status | What |
| --- | --- |
| **In place** | Checks for secrets, private keys, large files, merge conflicts and broken YAML, and for the app's Python: lint and format (ruff), and app files under 500 lines. |
| **In place** | Every commit's files, paths and message are checked for blocked names. |
| **In place** | The checks install themselves when a Claude Code session starts, and the guard blocks an agent's commit until they're installed. |

### 3. Push to GitHub

The commits leave your computer.

| Status | What |
| --- | --- |
| **In place** | A push straight to `main` is refused. |
| **Open** | A push to any other branch is stored on GitHub with no checks. The commit checks in step 2 are the catch before this point. Branch names aren't checked for blocked names. |
| **Open** | A pull request into a branch other than `main` runs the five checks, but nothing requires them to pass. |

### 4. Pull request into main

Continues at [the checkpoint](#the-checkpoint-pull-request-into-main).

## Cloud to cloud: starts with a cloud agent

### 1. The agent works in the cloud

A Claude chat or cloud session with connectors to your apps, or GitHub's coding agent.

| Status | What |
| --- | --- |
| **Caught by CI** | A Claude chat's connectors run no commit checks; the checkpoint runs them again. A cloud Claude Code session loads the guard and the commit checks when it starts, if its environment has `python` and pre-commit. |
| **Open** | A Claude chat's connectors run no guard and act with your GitHub login, so nothing asks you before one changes enforcement, and GitHub can't tell the agent from you. Fix: the agent gets its own GitHub account. Your decision. |
| **Open** | Which repositories each connector can reach, and what it may do there. Your review. |
| **Open** | The Drive and Docs connectors can create and share files, so code could be copied out of GitHub. Your review. |
| **Open** | Cloud agent environments haven't been reviewed: their variables are visible to anyone who uses the environment, their setup script runs as root, and their network allowlist decides what code can reach. Your review. |
| **Open** | GitHub's coding agent: turn it off if you don't use it, and remove any `copilot` deployment environment it created. |

### 2. Commit through the connector

Files are written to a branch through GitHub's API.

| Status | What |
| --- | --- |
| **Open** | The commit is stored on GitHub with no checks at all. |

### 3. Pull request into main

Continues at [the checkpoint](#the-checkpoint-pull-request-into-main).

## The checkpoint: pull request into main

Nothing reaches `main` without passing all five checks. They run from `main`'s own copy of the workflow, so a pull request can't rewrite the checks that judge it.

| Check | What it does |
| --- | --- |
| `secret-scan` | Scans the files the pull request adds or changes for secrets. The full scan of every file runs on `main`. |
| `precommit` | Runs the commit checks again, so skipping them locally changes nothing. |
| `selftest` | Tests the gate and the guard, using `main`'s tests first. |
| `python` | Runs `main`'s copy of `scripts/check_python.sh` on the app's Python. It checks lint, format and types, and runs the tests; a skipped test counts as a failure. It also checks coverage of the changed lines, unused or undeclared packages, code nothing calls, and known vulnerabilities. The same script runs on your computer. |
| `security-critical-gate` | Refuses blocked names, new suppressions and anything else that weakens a check. A suppression is a comment or marker that switches off the linter, the type checker, coverage or the secret scanner, or skips a test. |

| Status | What |
| --- | --- |
| **In place** | All five checks are required. Squash merges only. The ruleset has no bypass list, so the rules bind everyone, you included. |
| **In place** | A pull request that changes an enforcement file waits for your review when its author isn't you, such as Dependabot. Your own pull requests, the agent's included, don't wait on GitHub; the guard asks you before the agent merges one. |
| **In place** | Only a repository admin can change the ruleset. The agent works through your admin account, so the guard asks you before it changes a rule or setting. |
| **In place** | `python scripts/github_settings.py` checks the ruleset, Actions, Dependabot and the deploy environment against the baseline when you run it. It isn't scheduled: reading the ruleset needs an admin sign-in, which CI doesn't hold. |
| **In place** | `main` gets a full secret scan after every merge and once a day. |
| **In place** | Every review thread must be resolved before a pull request merges, so a review finding, Copilot's included, can't be passed over unanswered. |
| **In place** | GitHub's extra approval for unattributed changes is on: a pull request with a commit whose author isn't linked to a GitHub account needs one more approval. |
| **In place** | Every pre-commit hook is pinned by a full commit hash, and the gate refuses any other pin: a tag, branch or short hash is looked up by name, so it could be moved to other code. |
| **In place** | The workflows run on a pinned runner image, `ubuntu-24.04`, so GitHub moving `ubuntu-latest` to a new Ubuntu release (from 19 October 2026) doesn't change them. A newer image is its own change. |
| **Open** | The agent's own GitHub account, so that GitHub holds its enforcement pull requests for your review too, including ones from a connector that runs no guard. Your decision. |
| **Open** | The checks live in the same repository they protect. Anchoring them outside it (organization rulesets, or a separate repository) is your decision. |
| **Open** | GitHub's own secret scanning and push protection: free for public repositories; a private one needs GitHub Code Security. Turn them on where your plan offers them. |
| **Open** | The tools the checks install are pinned by hash, but the hook dependencies pre-commit installs in CI aren't. Dependabot updates the action pins and the Python packages in `uv.lock`; the pinned tool lists and hook versions get no automatic updates or vulnerability audit. |
| **Open** | Copilot's review isn't required, and a requested re-review sometimes doesn't post. |

## Three kinds of change

The target: each one is declared in the repo, passes the same checkpoint, and is applied to Azure by the deploy job. Today only code goes through, because the deploy job and the infrastructure and agent definitions aren't built yet. Code can come from either path.

### 1. Code: what the app does

files in the repo → checkpoint → deploy job

| Status | What |
| --- | --- |
| **In place** | Every change that reaches `main` today (security tooling, tests, docs) passes the checkpoint first. |
| **Not built yet** | App code: the enforcement layer, ingestion, and how incoming files are read. |
| **Not built yet** | Database tables and access rules (roles, row-level security, masking), written as migration scripts. |
| **In place** | The `python` check on every PR, including known vulnerabilities in the app's Python packages (also audited daily on `main`). No package version newer than 7 days is used. |
| **In place** | New packages. A package that doesn't exist fails to resolve. No version uploaded in the last 7 days is used. Every new dependency needs your approval, because `pyproject.toml` is an enforcement file. |
| **Open** | A lookalike package name (one letter off a popular one) is caught only by your review when you approve the dependency. A separate package check was decided against: its list of popular names would need constant upkeep. |

### 2. Infrastructure: what exists in Azure

resource definitions in the repo → checkpoint → deploy job

| Status | What |
| --- | --- |
| **In place** | The foundation (resource groups, region lock, budget, deploy identity), set up by hand once and recorded in `.claude/security-stack.json`. |
| **In place** | CI signs in to Azure without a stored password, and the deploy identity can reach only the app's resource group. |
| **Open** | The deploy identity's Contributor role can create any resource type in that resource group; no policy limits the types or requires deploys from infrastructure code. |
| **Open** | Confirm Entra ID security defaults (sign-in with MFA for everyone) are on, and create an emergency admin account. Your steps. |
| **Not built yet** | The app's resources written as code and applied by the deploy job: SQL, Search, storage, Key Vault, Azure OpenAI, Document Intelligence and Foundry, and the supporting services (Content Safety, API Management, Log Analytics, the Defender plans and private endpoints). |
| **Not built yet** | A scan of that code on every pull request. |

### 3. Agent configuration: what the agent may do

agent definitions in the repo → checkpoint → deploy job

| Status | What |
| --- | --- |
| **Not built yet** | Each agent's definition kept in the repo: instructions, the tools it may call, its model, the identity it runs as and what that identity may reach, its data connections, its content filters. |
| **Not built yet** | Edit rights on agents in Foundry for the deploy identity only. People get view rights. |
| **Not built yet** | The agent answers within the asker's permissions: its tools query Azure SQL as the person asking, through Entra's on-behalf-of flow, so row-level security and masking apply to them ([decided](architecture.md#8-decisions-and-corrections-log)). |

"Building" an agent in the cloud is configuring it. Configuring an agent is a change to what it may do, so it needs the same checkpoint as a change to code.

## What doesn't go through the checkpoint

Two kinds of drift skip it and need their own controls. Two runtime inputs never touch GitHub at all, because they aren't changes to the system.

### Drift: infrastructure changed in the portal or CLI

portal or Azure CLI → Azure resources

| Status | What |
| --- | --- |
| **Open** | Changes made in the portal, or by the terminal agent with your Owner login, skip the checkpoint. |
| **Open** | A scheduled check that flags when Azure stops matching the repo. Today the only proof is running the CI sign-in check by hand. |
| **Open** | A read-only Azure login for the terminal agent day to day. Today it holds your Owner login, so its Azure changes are drift. Your owner-level sign-in would stay for your own steps. |

### Drift: agents edited in Foundry (widest impact)

Foundry portal → live agent

| Status | What |
| --- | --- |
| **Not built yet** | A scheduled check that compares each live agent to its definition in the repo and fails loudly when they differ. |
| **Not built yet** | Edit rights in Foundry held by the deploy identity alone, so a portal edit isn't possible in the first place. |

### Runtime inputs: data and role membership

documents and data feeds · Entra groups → Azure

| Status | What |
| --- | --- |
| **Not built yet** | The enforcement layer checking app data before it's stored, and a tamper-proof ledger of every agent write. |
| **Not built yet** | Roles held through Entra group membership, an admin action that Entra logs. What each role may do is code (type 1). |

## Standards and compliance

The stack gives the project strong technical controls, but it isn't certified, and it doesn't make the project compliant with SOC 2, ISO/IEC 27001 or similar standards. It's set up for one owner: ordinary pull requests need no human approval, and the agent works through your account. Those standards expect every change to production to be reviewed by someone other than its author. What's missing, and the caveats for anyone adopting the baseline, are in [enterprise-level-gaps.md](enterprise-level-gaps.md#caveats-for-anyone-adopting-this-baseline). Which controls the checks evidence, in the auditors' own numbering, is in [control-mapping.md](control-mapping.md).

## What's left for you

Your decisions and reviews, most important first. When one is done, update its row above and `.claude/security-stack.json`.

1. **Give the agent its own GitHub account.** It's the one change that makes GitHub hold the agent's enforcement pull requests for your review, from any connector; the ruleset already works that way. The other anchors (organization rulesets, a separate repository for the checks) need a GitHub organization.
2. **Review cloud access:** which repositories and permissions each connector has (Drive and Docs included), the cloud agent environments, and GitHub's coding agent with its `copilot` environment.
3. **Confirm Entra ID security defaults are on, and create the emergency admin account.** Its password never passes through the agent.
4. **Your terminal choices:** the permission mode, which MCP servers stay, and which sites join the allowlist.
5. **Optional:** an admin-only settings file for the guard, a read-only Azure login for the agent day to day, and a sealed workspace for the agent ([workstation-hardening.md](workstation-hardening.md)).
