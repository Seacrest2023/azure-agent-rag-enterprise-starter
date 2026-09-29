# Architecture

**Status:** Architecture agreed. No tables built, no data loaded.
**Next phase:** Enforcement layer, designed table by table before anything is created.

---

## 1. Summary

This baseline is an agent-over-RAG platform on Microsoft Azure for organisations with many locations or business units. It takes in operational data in any format (CSV, PDF, image, Word doc, system feeds), turns it into clean, consistent records, and lets people and an AI agent use them within their permissions. Every answer is grounded in evidence.

**Design principle:** Enforcement comes first. The rules that govern how data enters the database are built before any data is loaded. Agents seed the database only through that enforcement layer.

**Scale:** Designed for production volume (hundreds of locations, millions of records per month), even when running on a small dataset.

**Domain-neutral:** a use case supplies the domain (Section 2). Everything else in this document applies to every use case.

---

## 2. Use cases

A use case is one vertical built on this baseline. The baseline provides the layers (Section 4), the shared tables (Section 5), roles and access (Section 6), the enforcement layer and the security plan (Section 10). The use case provides the rest:

| A use case supplies | For example |
| --- | --- |
| Its domain tables and Gold views, alongside the shared tables | the facts the business records, and the calculated views people and the agent read |
| Its enforcement rules | an invoice's lines add up to its total; a price matches the agreed price for that date |
| Its agent tools | a question the business asks each month, answered from a Gold view |
| Seed data with the mess real data has | the same item named differently by each source, documents as photos |
| Its research, domain decisions and open items | how its data model was derived, and the corrections made along the way |
| Which groups may read each document type in full, and which fields are masked | finance reads invoices; documents holding pay aren't indexed for search |

Worked example: [multi-site restaurant groups](use-cases/restaurant.md). To add a use case, copy [the template](use-cases/_template.md).

---

## 3. Key terms

| Term | Plain meaning |
| --- | --- |
| **Database** | the whole data store. One Azure SQL database holds everything. |
| **Table** | one kind of thing, at one level of detail (like a spreadsheet tab with strict rules) |
| **Schema** | the blueprint: which tables exist, their columns, and how they connect |
| **Row / record** | one entry in a table |
| **Column / field** | one attribute of every row |
| **Grain** | what one row represents ("one line on one document") |
| **Dimension table** | a list of things that rarely change: sites, items, employees |
| **Fact table** | a log of events: sales, shifts, invoice lines |
| **Star schema** | facts in the middle, pointing to the dimensions that describe them |
| **View** | a saved calculation that runs on demand; nothing stored |
| **Primary key** | the column that uniquely identifies each row |
| **Surrogate key** | an internal auto-numbered ID the database generates |
| **Natural key** | a real-world value, or combination of values, that identifies a row: an ID another system assigns (its order ID), or business fields such as supplier + invoice number |
| **Foreign key** | a column pointing to another table's row, so facts are referenced, not copied |
| **Unique key** | a rule that blocks two rows sharing the same value; this is what prevents duplicates |
| **Idempotent** | running the same import twice produces no duplicates |
| **Header / lines** | one row for the whole document, plus one row per line on it |
| **Temporal table** | a table that automatically keeps every past version of each row |
| **Medallion architecture** | Bronze (raw) → Silver (clean) → Gold (business-ready) |
| **Rowstore index** | row-by-row storage; fast single lookups (dimensions) |
| **Columnstore index** | column-by-column storage; compressed and fast for totals (large facts) |
| **Partitioning** | splitting a large table into monthly chunks so queries skip irrelevant months |
| **Service principal** | an identity for software, not a person |
| **Role-based access control (RBAC)** | permissions granted to roles, and people granted roles, never access one by one |
| **Entra ID group** | a group of people in Microsoft Entra ID; each role maps to one group |
| **Row-level security (RLS)** | an Azure SQL rule that filters which rows a person can see; a site manager's query physically returns only their site |
| **Dynamic data masking** | hides sensitive column values (e.g. employee pay) from roles that don't need them |
| **Ledger table** | append-only, cryptographically chained table; tampering is provable |
| **Azure AI Document Intelligence** | Azure's OCR service for reading invoices, PDFs, and images |
| **Microsoft Fabric** | Microsoft's large-scale analytics platform; a later step, not needed to start |

---

## 4. Structure

| Layer | Purpose | Azure service |
| --- | --- | --- |
| **Bronze (raw)** | every file and feed exactly as received, never edited | Blob Storage (files) + Azure SQL intake table |
| **Staging** | what the agent extracted from each file, with confidence scores, awaiting enforcement checks | Azure SQL |
| **Silver (clean)** | accepted dimension and fact tables | Azure SQL |
| **Gold (business-ready)** | calculated views for managers and the agent | Azure SQL views |
| **Control** | audit of every agent write and every approval; term mappings | Azure SQL ledger table |

**Data flow:** source files → Blob Storage → Defender malware scan → raw intake, started by a clean verdict (site record, fingerprint, type and size) → Document Intelligence (OCR) → prompt-shield screening (a document flagged, or that can't be screened, is held for a person and goes no further) → agent extraction → staging → **enforcement layer** → Silver tables → Gold views → agent (read-only). A document's text, as Document Intelligence read it, goes into the AI Search index only after enforcement has accepted all of its records.

**Sites are rows, not tables.** Every table carries `site_id`. All locations share one set of tables.

---

## 5. Shared tables

Every use case has these tables. Its own dimension and fact tables sit alongside them in Silver, and its Gold views read from them. For a complete data model built this way, see [the worked example's](use-cases/restaurant.md#data-model).

### Dimensions (5): Silver, rowstore

| # | Table | Grain | Unique key (blocks duplicates) |
| --- | --- | --- | --- |
| 1 | sites | one location or business unit | location_code |
| 2 | source_systems | one source system or platform | system_name |
| 3 | master_items | one canonical item | item_sku |
| 4 | item_aliases | one source name mapped to a master item | source_system + source_item_id |
| 5 | term_mappings | one local term mapped to its standard meaning | raw_term + site + source_system + field |

### Intake and control (3)

| # | Table | Grain | Unique key |
| --- | --- | --- | --- |
| 6 | raw_document_intake | one received file or payload | file fingerprint (SHA-256 hash) |
| 7 | staging_extractions | one record the agent extracted, with confidence | intake + target_table + record_index |
| 8 | agent_action_ledger *(Azure SQL ledger table)* | one agent write action | none — append-only |

### Use-case tables and Gold views

A use case's facts go in Silver, with columnstore and monthly partitions on the large ones. Every fact has a unique key that identifies it in its source: source system plus source ID where the source assigns one, otherwise a natural key such as supplier plus invoice number. Every table that holds site data carries `site_id`. Its Gold views are the calculated views people and the agent read.

---

## 6. Roles and access

People are governed the same way the agent is: by permissions the database enforces, not by instructions. Each role is an **Entra ID group**; people are added to groups, never granted access individually.

| Role | Can see | Can do |
| --- | --- | --- |
| **Site manager** | their own site's data only | ask the agent about their site |
| **Regional / operations lead** | the sites in their region | compare sites, review agent findings |
| **Analytics** | all sites, through Gold views | build reporting; no raw or staging data |
| **Data science** | Silver tables, sensitive fields masked | build models |
| **Data governance** | everything, including the ledger | approve term mappings, item aliases, and enforcement rule changes |
| **Finance** | finance views and financial source documents, such as invoices | sign off on financial figures |
| **Agent** | Gold views only, read-only | write only to staging, through enforcement |

**How it's enforced**

| Mechanism | What it guarantees |
| --- | --- |
| Entra ID groups mapped to database roles | access follows role membership; removing someone from a group removes their access everywhere |
| Row-level security on every table carrying `site_id` | site and regional scoping is applied by the database to every query, including queries the agent runs on a user's behalf |
| Dynamic data masking | sensitive columns (employee pay, personal details) are hidden from roles without a need to see them |
| Per-role views | each role reads through its own window; no role queries base tables it doesn't own |
| Approvals recorded in the ledger | every approved mapping, alias, or rule change records who approved it and when |
| No role holds table-creation or delete rights | schema changes happen only through reviewed, recorded changes, never ad hoc |

**The agent inherits the asker's scope.** When a site manager asks the agent a question, the answer is limited to what that manager is allowed to see. The agent never widens anyone's access.

---

## 7. Volume practices (built in from day one)

| Practice | Why |
| --- | --- |
| BIGINT surrogate primary keys | fast inserts, effectively unlimited IDs |
| A unique key on every fact: source system + source ID, or a natural key where the source assigns no ID | re-running an import never duplicates |
| Columnstore + monthly partitions on large facts | fast totals; old months archive cleanly |
| Rowstore indexes on dimensions | fast single lookups |
| Temporal tables (such as prices) with a retention period | point-in-time values without unbounded growth |
| Agent reads Gold views only, through fixed read-only queries run as the person asking (Section 8) | agent cannot damage tables or widen anyone's access |
| Agent writes only to staging; every write recorded in the ledger | nothing reaches Silver without passing enforcement |

---

## 8. Decisions and corrections log

| Decision | Reason |
| --- | --- |
| Facts placed in Silver, not Gold | Gold is views only, so stored records belong in Silver |
| Where the source assigns an ID, the unique key is source system + that ID; otherwise it's a natural key, such as supplier + invoice number | two source systems can issue the same ID, and some sources assign none |
| term_mappings keyed on term + site + source system + field | the same word means different things in different contexts |
| Extracted records wait in staging_extractions | it is where enforcement checks happen |
| Azure SQL chosen over Fabric to start | operational database with fast inserts; Fabric is a later analytics step |
| Role-based access for people, not just the agent | multi-team, multi-region organizations need governed access to shared data; enforced through Entra ID groups, row-level security, and masking |
| Agent answers are scoped to the asker's permissions | an AI assistant must never become a way around access rules |
| Python for all app code; SQL for the database | the app is data work, which is Python's strength; the security tooling is already Python. What the code does is in [stack.md](stack.md) |
| Bicep for infrastructure as code | the project is Azure-only; Bicep has no state file to store and protect, and `what-if` compares the files with live Azure for the drift check |
| Domain-neutral baseline; each vertical is a use case | the machinery is the same for every vertical; only the domain tables, rules, tools and seed data change ([restaurant example](use-cases/restaurant.md)) |
| The agent's tools query Azure SQL as the person asking, through Entra's on-behalf-of flow | row-level security and masking then apply to that person, the database's audit names them, and no code path can hand the agent a wider scope. Setting the scope in `SESSION_CONTEXT` instead would rest on our code setting it right every time, and the audit would show only the agent |
| Search honours roles through groups on each document: an indexed document carries its `site_id` and the Entra groups allowed to read that document type in full (the use case lists them), and every search is filtered on both against the asker's groups. Document types with masked fields, such as pay, are never indexed | a site filter alone would let a role read in search what the database hides from it; redacting text before indexing would be a second masking system to keep in step with the database |
| Azure Functions runs the Python | small pieces of code on triggers (a file passing its malware scan, a request arriving), billed per run, one service to secure |

---

## 9. Open items

- **Enforcement layer:** next phase. Go table by table and field by field: identify the load-bearing fields and define how data must be curated before it reaches the database.

---

## 10. Security

Ordered by the phase in which each item must be in place; items 24–26 name their phase. Items 1–6 are the repository's generic security stack: how it works and how to set it up in any repository is in [security-setup-prompt.md](security-setup-prompt.md), and this project's values and setup status are in `.claude/security-stack.json`. Of the later phases, three parts exist so far: the CI deploy identity (a managed identity, item 11), Defender for Cloud's free foundational plans (item 14), and the dependency audit (item 22). Everything else in the later phases is design. The step-by-step way to set it all up again is [setup-guide.md](setup-guide.md).

One rule governs agents: they never skip or change enforcement without the owner's approval. What protects each stop a change passes through, today's status and what's still open are in [security.md](security.md). This section is the plan: which measure has to be in place by which phase.

### Now (repository and Azure foundation)

| # | Measure | Where |
| --- | --- | --- |
| 1 | Pre-commit chain (secret scanning, file checks, and blocked names in each commit's files and message, and lint, format and a 500-line limit for the app's Python) on every commit, installed by Claude Code when a session starts, and re-run in CI on every PR with both the base branch's and the PR's config, so a hook skipped locally can't reach `main`. In Claude Code sessions that load this repository's settings, the agent guard blocks every way of skipping hooks (`--no-verify`, `SKIP=`, `core.hooksPath` changes, edits under `.git/`), and asks the owner before any change to enforcement: it asks in the default and plan permission modes, and refuses in every other mode, bypass permissions included. It fails closed. Commits made through a connector or the GitHub web editor run no hooks at all, and the guard can't see inside script files; for those, the CI replay is the guarantee. Secret scan of the files each PR adds or changes, and of every tracked file on pushes to `main` and daily. | `.pre-commit-config.yaml`, `.github/workflows/security-gate.yml` (`precommit`, `secret-scan`), `.github/workflows/security.yml` (daily scan of `main`), `.claude/settings.json`, `.claude/hooks/` |
| 2 | Secret files ignored; `.env.example` committed instead | `.gitignore`, `.env.example` |
| 3 | Workflows default to read-only tokens; actions pinned to commit SHAs (required by repository setting); Dependabot keeps the action pins and the Python packages in `uv.lock` current, weekly, each new version after seven days; every job runs on a pinned runner image (`ubuntu-24.04`); every tool the required checks install is pinned by file hash, read from `main`, and installed before any PR file is on disk; pre-commit hook repositories pinned to commit SHAs (the hooks' own dependencies, which pre-commit installs from PyPI, are not pinned by hash) | `.github/workflows/`, `.github/requirements/`, `.github/dependabot.yml`, `.pre-commit-config.yaml` |
| 4 | CI signs in to Azure with OIDC federated credentials, never stored keys; the deploy identity lives in its own resource group and can reach only the app resource group. Azure guardrails at subscription level: resources and resource groups allowed only in the project's region (two Azure Policy assignments), and a monthly budget that alerts the subscription's owners as spending approaches it | GitHub environment `dev`, `.github/workflows/azure-login-check.yml`, Azure subscription (names and IDs in `.claude/security-stack.json`) |
| 5 | `CODEOWNERS` listing the enforcement files, `SECURITY.md`, and a ruleset on `main`. It requires a PR and squash merges. It requires the four security checks and the app's language check (here `python`: lint, format, strict types, tests, changed-line coverage, dependencies, dead code and known vulnerabilities) on an up-to-date branch. It has no bypass and allows no deletion or force push. It holds enforcement PRs by authors who aren't code owners for the owner's review, with stale approvals dismissed, and asks one more approval for a commit whose author isn't linked to a GitHub account. Every review thread must be resolved before merging, and other PRs need no approval. The agent works through the owner's account, so the agent guard asks the owner before the agent merges an enforcement PR, apart from Dependabot bumps the owner has let merge on green | `.github/`, `scripts/check_python.sh`, `pyproject.toml`, repository settings |
| 6 | Security gate, fully automated. It and every other required check run from `main`'s workflow definition, so a PR can't weaken the checks that judge it. It fails on new check suppressions; blocked names (company names anywhere, the project name in file paths); any loosening of secret scanning (allowlist entries, filters, detectors); removal of coverage from a protected list (paths, names, pre-commit hooks, agent hook registrations, required check names, test cases); any change to which packages the trusted jobs install; risky workflows (zizmor); and workflow changes that could weaken a required check (a lookalike job name, or `if:`, `needs:`, `continue-on-error`, a changed trigger or an unsafe expression in a job that runs PR code, in the trusted workflow). Fails closed on anything it can't check. Its logic is tested against known-good and known-bad PRs on every PR (`selftest`), with `main`'s tests and the PR's. Later phases add their areas' tests here (items 9, 10 and 13). When all required checks pass, the owner or the agent merges; a PR that touches an enforcement file also needs the owner's approval, apart from the Dependabot bumps in item 5. | `scripts/`, `.github/workflows/security-gate.yml`, `.github/security-critical-paths.txt`, `.github/blocked-terms.txt`, `tests/gate/`, `tests/hooks/` |

### Enforcement layer

| # | Measure |
| --- | --- |
| 7 | The agent answers within the asker's scope, enforced by the database: its tools query Azure SQL as the asker, through Entra's on-behalf-of flow, so row-level security and masking apply to that person (Section 8). |
| 8 | Enforcement never trusts the agent: every staged value is validated on its own merits, whatever the confidence score or explanation. Only validated records move to Silver. |
| 9 | Automated access tests per role (visible rows, masked columns), including that a site manager cannot read another site's data directly or through the agent. Run in CI. They live in `tests/access`, where every change needs the owner's approval. |
| 10 | No role holds delete or schema-change rights, checked by a test. |

### Azure infrastructure

| # | Measure |
| --- | --- |
| 11 | Managed identities everywhere; the few remaining secrets in Key Vault. No connection strings or keys in app settings. (Exists so far: the CI deploy identity.) |
| 12 | Private endpoints for Azure SQL, Blob Storage, AI Search, Azure OpenAI and Key Vault; public access off. |
| 13 | Infrastructure code scanned in CI (Checkov or the Bicep linter). |
| 14 | Defender for Cloud on; Azure SQL auditing and Key Vault logs sent to Log Analytics. (Exists so far: Defender for Cloud's free foundational plans.) |

### Ingestion and seeding

| # | Measure |
| --- | --- |
| 15 | File type and size checked before OCR; Defender for Storage malware scanning, and intake starts only on a clean verdict; uploads use short-lived SAS tokens that can create one new file, at one server-generated path in the upload folder, and can't overwrite it; Bronze is read-only once a file lands. Intake reads only the exact version Defender scanned (the ETag in its scan result), takes each file's site from the record for that exact path, never from the uploader, and stops any file without a record. Only enforcement writes to the checked folder that AI Search indexes: the text Document Intelligence read, and only for a document whose records were all accepted. Each text is written with the document's `site_id` and allowed groups, and document types with masked fields are never written there (Section 8). |
| 16 | SHA-256 file fingerprints and each fact's unique key block replayed or altered files from creating duplicates. |

### Agent and search

| # | Measure |
| --- | --- |
| 17 | Every Azure AI Search query filtered on `site_id` and on the document's allowed groups, against the asker's groups. Document types with masked fields are never indexed (Section 8). |
| 18 | Prompt-injection defenses. Document text, OCR included, and every field extracted from it or typed by a person, is data whoever wrote it, the asker included: every tool result that carries it is marked as untrusted before the model sees it, and passed as quoted data, never instructions. Azure AI Content Safety's prompt shields screen it for attacks hidden in documents, long text in overlapping chunks that must each pass, and fail closed: shields detect rather than clean, so a document they flag, or that can't be screened, never reaches the model. Intake holds it for a person, and it's never indexed. Agent tools are read-only, and outbound calls go only to the project's Azure endpoints. Answers never display external links or images; the front end shows only citations to the project's own records, so a hidden image link can't carry data out. Two eval sets show a weakened defense before release: documents carrying injected instructions must be caught by screening, with separate cases for intake (held) and retrieval (left out), so each screen is exercised on its own, and in every case the attacked text never reaches the model; and attacks deliberately run past screening, in a document or in a field extracted from one, each paired with a clean copy, must give the same answer, make the same tool calls, and keep the same scope and citations. |
| 19 | Answers must cite records the asker can see. If a citation falls outside their scope, the answer is blocked and logged. |
| 20 | Per-user rate limits and quotas through Azure API Management. |
| 21 | Logs and telemetry redact connection strings, SAS tokens, keys and masked fields. |

### Ongoing

| # | Measure |
| --- | --- |
| 22 | Dependency audit (`pip-audit`) on every PR and daily. A package that doesn't exist fails to resolve, no version uploaded in the last seven days is used, and a new dependency needs the owner's approval (`pyproject.toml` is an enforcement file). |
| 23 | Regular review of `agent_action_ledger` and approvals, with ledger digest verification. |

### Infrastructure and agents as code

Azure resources and agents change the way code does: declared in the repository, through the pull request checkpoint, applied by the deploy job. A change made in the portal or the CLI skips the checkpoint. The route and today's status are in [security.md](security.md#three-kinds-of-change).

| # | Measure | Phase |
| --- | --- | --- |
| 24 | The app's Azure resources written as infrastructure code (scanned in CI, item 13) and applied only by the deploy job from `main`. No portal or CLI changes to them. | Azure infrastructure |
| 25 | Each agent's definition kept in the repository: its instructions, the tools it may call, its model, the identity it runs as and what that identity may reach, its data connections and its content filters. Applied only by the deploy job. Edit rights on agents in Foundry for the deploy identity alone; people get view rights. | Agent and search |
| 26 | Scheduled drift checks that compare Azure's resources and each live agent with their definitions in the repository, and fail loudly when they differ. | Ongoing, once 24 and 25 exist |
