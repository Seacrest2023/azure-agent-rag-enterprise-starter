# Agent-over-RAG baseline for Azure

A baseline for building an AI agent over an organisation's own data on Microsoft Azure, with the security and governance in place before any data is loaded.

Project was built for complex scenarios where operational data is messy: each location or team runs its own systems, names for the same thing don't match, and documents arrive as PDFs and photos. The baseline takes data in any format, turns it into clean, consistent records through an enforcement layer, and lets an AI agent answer questions within each person's permissions. Every answer is grounded in the data it came from.

## Locked down by default

The baseline starts at its strictest: every check is on, and every check that can stop a change blocks. If your agent tries to change enforcement in Claude Code, it asks you first. It asks only in the default and plan permission modes; in any other mode, such as bypass permissions, it refuses until you switch to default mode and approve. In GitHub Copilot Chat in VS Code, it refuses. Other agents meet the checks at the pull request, and everyday changes merge when the checks pass. You can lower a protection later, as your own recorded decision: see [Lowering a protection](docs/checks-inventory.md#lowering-a-protection).

## Start here

To adopt the baseline in your own repository:

1. Read [AGENTS.md](AGENTS.md), the rules every coding agent follows here, and [docs/checks-inventory.md](docs/checks-inventory.md), every check in the box and how to adopt it.
2. Point your agent at [docs/security-setup-prompt.md](docs/security-setup-prompt.md) and set up the stack with it, phase by phase. To do it by hand, follow [docs/setup-guide.md](docs/setup-guide.md), which uses the same phase numbers.
3. Add your use case: copy [docs/use-cases/_template.md](docs/use-cases/_template.md) and answer its questions first. The [restaurant use case](docs/use-cases/restaurant.md) is a worked example.
4. Before you rely on the baseline for a business, read [the caveats](docs/enterprise-level-gaps.md#caveats-for-anyone-adopting-this-baseline). It isn't certified, and meeting SOC 2 or ISO/IEC 27001 needs independent review of every change.

**Tested with VS Code on Windows,** with Claude Code and GitHub Copilot Chat. The runtime guard runs in both. The git hooks and the pull request checks hold for every agent, and most of the stack doesn't depend on the agent or the editor. [docs/coding-agents.md](docs/coding-agents.md) says what's supported where, and has prompt templates to port the guard to another agent or adapt the checks to another language or CI.

What changes between versions is in [CHANGELOG.md](CHANGELOG.md).

## Principles

What the design commits to. The product itself isn't built yet: see [Status](#status).

- **Enforcement first.** The rules that govern how data enters the database are built before any data is loaded. Agents write only through that enforcement layer.
- **Governed access.** People and agents alike see only what their role allows, enforced by the database through Entra ID groups, row-level security, and data masking. The agent answers within the asker's permissions.
- **Evidence, not guesses.** The agent reads clean, validated data and cites its sources.
- **Built for scale.** Designed for hundreds of locations and millions of transactions, even when running on a small dataset.

## Use cases

The baseline is domain-neutral. A use case adds its own tables, enforcement rules, agent tools and seed data on top of it ([architecture.md](docs/architecture.md#2-use-cases)).

- [Multi-site restaurant groups](docs/use-cases/restaurant.md): the worked example, with the domain research, a 25-table data model, and a supplier invoice followed through the pipeline.

To add one, copy [the template](docs/use-cases/_template.md).

## Azure stack (target)

The services the product will run on. None of them is deployed yet, apart from Defender for Cloud's free foundational plans; what exists in Azure today is the foundation listed under [Status](#status).

| Role | Service |
| --- | --- |
| Agent | Azure AI Foundry Agent Service + Microsoft Agent Framework |
| Models | Azure OpenAI |
| Document reading (OCR) | Azure AI Document Intelligence |
| Raw file storage | Azure Blob Storage |
| Operational database | Azure SQL Database |
| Document search (RAG) | Azure AI Search |
| App code (Python) | Azure Functions |
| Secrets and identity | Azure Key Vault + Microsoft Entra ID |
| Prompt-injection defense | Azure AI Content Safety (prompt shields) |
| Per-user rate limits | Azure API Management |
| Threat protection | Microsoft Defender for Cloud, with Defender for Storage scanning uploads for malware |
| Logs and auditing | Log Analytics (Azure SQL auditing, Key Vault logs) |
| Network isolation | Private endpoints for Azure SQL, Blob Storage, AI Search, Azure OpenAI and Key Vault; public access off |

The last five rows come from the security plan in [docs/architecture.md](docs/architecture.md#10-security). What each part does, and exactly what the Python code does: [docs/stack.md](docs/stack.md).

## Architecture

| Layer | Holds |
| --- | --- |
| **Bronze (raw)** | every file and feed exactly as received |
| **Staging** | what the agent extracted, with confidence scores, awaiting validation |
| **Silver (clean)** | accepted records in the shared dimensions and the use case's own dimension and fact tables |
| **Gold (business-ready)** | calculated views for people and the agent, such as margin by site and month |
| **Control** | an append-only audit ledger of every agent write and every approval |

```
source files → Blob Storage → malware scan → raw intake → Document Intelligence → screening
  → agent extraction → staging → enforcement → clean tables → views → agent (read-only)
```

Intake starts only when a file scans clean, and checks it before it's read. The text read from it is screened for hidden instructions, and a document that fails is held for a person. A document goes into the search index only after enforcement has accepted all of its records.

Full design, shared tables, and decision log: [docs/architecture.md](docs/architecture.md)

## Status

- [x] Architecture defined (layers and shared tables)
- [x] Roles and access model defined
- [x] A worked use case designed ([docs/use-cases/](docs/use-cases/))
- [x] Repository security stack (required checks, secret scanning, agent guard, owner approval for enforcement changes)
- [x] Python toolchain and code-quality checks (lint, format, strict types, tests, changed-line coverage, dependencies, dead code, known vulnerabilities)
- [x] Checks inventory, agent rules (`AGENTS.md`), and the enterprise-level gaps list
- [x] Azure foundation (resource groups, region lock, budget, keyless CI sign-in)
- [ ] Enforcement layer
- [ ] Azure app resources (database, storage, search, models, Key Vault) as infrastructure code
- [ ] Deploy job that applies code, infrastructure and agent definitions from `main`
- [ ] Ingestion and seeding
- [ ] Agent and RAG, with each agent's definition kept in the repository

## Development setup

In every new clone:

```bash
pip install pre-commit
pre-commit install -t pre-commit -t commit-msg  # secrets, file checks, blocked names, lint and format on every commit
uv sync                                         # Python 3.12 and the app's tools, pinned by hash in uv.lock
uv run pytest --ignore=tests/integration --ignore=tests/access  # the fast tests, before each commit
uv run bash scripts/check_python.sh             # the app's checks: lint, format, types, tests, coverage, audits
python -m unittest discover -s tests/gate -t .  # tests for the security tooling
python -m unittest discover -s tests/hooks -t .
```

Install uv first (`winget install astral-sh.uv` on Windows). A Claude Code session runs the `pre-commit install` step itself when it starts, and loads the agent guard. Pull requests run five required checks (`secret-scan`, `precommit`, `selftest`, `security-critical-gate`, `python`) and merge when they pass; a PR that changes an enforcement file also needs the owner's approval.

Which tests a change needs, and how to write them, is in [.claude/skills/testing/SKILL.md](.claude/skills/testing/SKILL.md). Claude Code uses it whenever it writes code here.

## Security

One rule governs agents here: they never skip or change enforcement without the owner's approval.

- [docs/security.md](docs/security.md): what protects each stop a change passes through, its status, and what's still open.
- [docs/setup-guide.md](docs/setup-guide.md): how to set all of this up again, in this project or a new one.
- [docs/security-setup-prompt.md](docs/security-setup-prompt.md): the generic procedure an agent follows to set it up; this project's values are in `.claude/security-stack.json`.
- [docs/coding-agents.md](docs/coding-agents.md): runtime enforcement, and which protections reach which coding agent. The runtime guard runs in Claude Code and in Copilot Chat in VS Code, and the doc covers what porting it to Cursor, Codex and others would take.
- [docs/workstation-hardening.md](docs/workstation-hardening.md): the path to protect your own sign-ins from code that runs as you, and what to do if a token keeps getting stolen.
- [docs/prompts/](docs/prompts/): prompt templates to port the guard, adapt the checks, set the stack up in a new repository, or harden the workstation.
- [docs/checks-inventory.md](docs/checks-inventory.md): every check, what it stops, and how to adopt or lower it.
- [docs/enterprise-level-gaps.md](docs/enterprise-level-gaps.md): what the baseline doesn't cover on its own, measured against enterprise security standards.
- [docs/control-mapping.md](docs/control-mapping.md): each check mapped to the SOC 2, ISO/IEC 27001 and NIST CSF 2.0 controls it evidences, and what no repository covers.
- [docs/ai-risk-mapping.md](docs/ai-risk-mapping.md): the FINOS AI Governance Framework's 23 mitigations and 23 risks against what is built and what is designed, with FINOS's own ISO/IEC 42001, EU AI Act, NIST SP 800-53 and OWASP references.

**Not a compliance certificate.** The baseline isn't certified, and it doesn't make a project compliant with SOC 2, ISO/IEC 27001 or similar standards. It's set up for one owner, and those standards expect every change to production to be reviewed by someone other than its author. See [the caveats](docs/enterprise-level-gaps.md#caveats-for-anyone-adopting-this-baseline).

## License

MIT License: see [LICENSE](LICENSE).
