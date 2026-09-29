# Stack

What this project is built with, how the pieces work alone and together, and which parts are code and which are config. It's written to be reused: to start another project on the same stack, see [Reusing this stack](#reusing-this-stack).

Status as of 28 September 2026. Most of the stack is designed but not built yet, and every table below says which parts exist.

## In one minute

- **The product runs on Azure.** Azure provides the services: file storage, document reading, the database, search, the models and the agent host.
- **Azure services don't talk to each other on their own.** Each one waits for a request, does its one job, answers, and stops. A few are wired together natively by config. Everything else is Python making the calls and deciding what happens next.
- **We write Python and SQL.** Python is the logic and the glue. It calls the services in order, decides what gets into the database, and passes each person's identity to the database. SQL defines the database and its access rules, and the database decides what each person may see.
- **Everything else is config.** Files in the repository declare which Azure resources exist, how they're wired together, how each agent is set up, and how changes are deployed. Apart from the one-time foundation ([setup-guide.md](setup-guide.md)), nothing is set up by hand in the Azure or Foundry portal.
- **Every change passes one checkpoint.** Code and config reach Azure only through a pull request into `main` and its required checks. [security.md](security.md) covers that path.

## Words used here

| Word | Meaning |
| --- | --- |
| **API** | A service's front counter: the list of requests it accepts, such as "read this file" or "run this query". Each Azure service has one, written and run by Microsoft. |
| **Call** | One request to an API, and the answer that comes back. |
| **Native integration** | A link between two Azure services that Azure built, so one reacts to the other without any code of ours. We switch it on in config. |
| **Trigger** | The event that starts a piece of our code, such as "a file scanned clean". |
| **Event Grid** | Azure's messenger for events. One service announces "this happened", and whatever subscribed to that event is started. |
| **Adapter** | A thin piece of Python that talks to one service, or turns one trigger into a call to the app. It holds no business rules. |
| **Code** | Instructions that run: Python and SQL. |
| **Config** | Files that describe what should exist or when something should run, rather than the app's logic: Bicep files, agent definitions, workflows. |
| **Logic** | Code that decides. Is this record valid? Does this answer cite only records the person may see? |
| **Glue** | Code that moves data from one service to the next. Take the file from storage, send it to be read, write the result to the database. |
| **Staging** | Where extracted records wait until they pass the checks. |
| **Clean tables** | The records that passed. Only these are used to answer questions. |
| **Business views** | Saved calculations on the clean tables, such as margin by site and month. The agent reads only these. |
| **Use case** | One vertical built on this stack: its domain tables, enforcement rules, agent tools and seed data. The worked example is [multi-site restaurant groups](use-cases/restaurant.md). |
| **Ledger** | An append-only record of every agent write and every approval. Tampering with it is provable. |
| **Deploy job** | The workflow that applies code and config from `main` to Azure. Not built yet. |

## The four layers

| Layer | What it is | In this project |
| --- | --- | --- |
| **1. Runs on Azure** | The services the product runs on | Blob Storage, Document Intelligence, Azure SQL, AI Search, Azure OpenAI, Foundry, Azure Functions, and the security services |
| **2. Code we write** | The logic and glue that make this product | Python 3.12 and SQL |
| **3. Config we declare** | Files that say what exists, how it's wired and how it's set up | Bicep files, agent definitions, GitHub Actions workflows |
| **4. How we build and guard it** | The tools every change passes through | GitHub and Dependabot, pre-commit, detect-secrets, zizmor, the Python toolchain (uv, ruff, basedpyright, pytest, diff-cover, deptry, vulture, pip-audit), Claude Code with the agent guard |

## How the pieces connect

### What an API does, and doesn't

Every Azure service has an API. Microsoft wrote it and runs it; we never write Azure's APIs, we call them. An API is for any action the service offers, not only fetching things: read this file, run this query, store this, delete that.

| An API does | An API doesn't |
| --- | --- |
| Accept a request in a fixed format | Link one request to the next. Each call stands alone; a service may store data (Blob Storage keeps files, Azure SQL keeps rows), but it acts on it only when asked |
| Check who is asking, and whether they may | Call any other service |
| Do one job: read a file, run a query, store a file | Know what the answer means for this business |
| Send back the result | Decide what happens next |

### The pattern every piece follows

1. **A trigger wakes our code.** A file passes its malware scan, or a person asks a question. Azure starts the right piece of Python.
2. **Python calls a service's API.** For example: "Document Intelligence, read this file."
3. **The service does its one job and answers.** It sends back the text and tables, and that's the end of its part: it doesn't act on them or pass them on.
4. **The answer comes back to Python, and Python decides.** The answer is now data in Python's memory. Python checks it against the rules and makes the next call: look up a name in the database, save a record, send an item for review.
5. **Python stops.** Nothing runs until the next trigger.

Trigger, call, answer, decide, call again, stop. The services answer; Python decides what happens next.

### Three ways the pieces connect

| Connection | What happens | Written as |
| --- | --- | --- |
| **Native integration** | Azure wires two of its own services together, because it built that link. | Config (Bicep) |
| **Python calls a service's API** | Our code sends a request, waits for the answer, and decides what to do with it. | Python |
| **Something calls our API** | Our Python has two front counters of its own: the front door, which the person's app calls, and the tools, which the agent asks for. | Python |

The agent can't run anything itself. The model replies with a request such as "run the margin tool for site 12, August". Our Python runs that tool, and the model writes its answer from the rows the tool returns.

### Native integrations this project uses

| Link | What it does, with no code of ours |
| --- | --- |
| Blob Storage → Defender for Storage | Each upload is handed to Defender to scan as it lands. The scanning is Defender's own job; the link is switched on in config. |
| Defender for Storage → Event Grid → Azure Functions | Defender publishes each scan result to Event Grid. Our intake Function subscribes only to clean results, so a clean verdict starts intake and any other verdict never does. |
| Blob Storage → AI Search indexer | Reads each text file in the checked folder (a document's text as Document Intelligence read it) and maps its `site_id` and `allowed_groups` values into filterable fields in the index, so every search can filter by site and by the asker's groups. It never reads the original photos or PDFs, so nothing is read twice. |
| API Management → the front door | Checks the person's sign-in token and rate limit before our code runs. |
| Each service → Log Analytics | Sends each service's logs to one place. |

### Where native stops and Python starts

The native links move things around. None of them knows this business's rules: what makes a record valid, what "Cpy Ppr A4" means, who may see which site. Those decisions are Python's.

Sometimes Azure offers a native option we don't use. Foundry has a built-in search tool, but we write our own, so that our code adds the asker's site and group filter to every search rather than leaving it to configuration.

### Where the Python runs

Our Python is an ordinary app: plain Python modules holding the rules and the glue. Azure Functions is only its doorway. Each Function is an adapter that turns its trigger ("a file passed its scan", "a question came in") into a call to the app, and does nothing else. That's why the app can be tested without Azure: the tests call the app directly, with stand-ins for the services. The [testing skill](../.claude/skills/testing/SKILL.md) covers how.

### What the glue looks like

An illustration, not real code. None of the app is written yet.

```python
result = document_intelligence.read(document)     # call Azure, wait for the answer
for line in result.lines:                          # the answer is now data in Python
    item = database.find_alias(line.description)   # call Azure SQL
    if item is None:
        review_queue.add(line)                     # unknown name: a person decides
    elif line.amount <= 0:
        reject(line, "amount must be positive")    # our rule
    else:
        staging.save(line, item)                   # call Azure SQL again
```

Each call to `document_intelligence`, `database` or `staging` goes to an Azure service's API. Each `if` is a business decision that no Azure service makes for you.

## How data and questions flow

Every step says who does it. **Python** is code we write. **Azure** is a service doing its one job. **Native** is two Azure services wired together by config.

```text
DATA IN                                       WHO DOES IT
  front door hands out an upload link         Python
       │
       ▼
  Blob Storage holds the file                 Azure
       │
       ▼
  Defender scans it for malware               Azure (Defender for Storage)
       │
       │ Event Grid: a clean result           native
       │ starts intake
       ▼
  intake: verdict, site, file checks          Python
       │
       │ "read this file"                     Python calls Azure
       ▼
  Document Intelligence reads it              Azure
       │
       │ text and tables come back            to Python
       ▼
  prompt shields screen the text              Azure (Content Safety), called by Python
       │
       │ flagged, or can't be screened:       Python
       │ held for a person, never passed on
       ▼
  extraction agent proposes records           Azure, called by Python
       │
       ▼
  enforcement: accept, reject or hold         Python
       │
       ▼
  clean tables and ledger in Azure SQL        Azure, written by Python
       │
       │ all its records accepted:            Python
       │ copy its text to the checked folder
       ▼
  checked folder ──▶ search index             native (AI Search indexer)

QUESTIONS IN                                  WHO DOES IT
  a person asks a question
       │
       ▼
  API Management: sign-in, rate limit         native
       │
       ▼
  front door: the person's scope              Python (our API)
       │
       ▼
  agent in Foundry: the model picks a tool    Azure, called by Python
       │
       │ "run the margin tool, site 12"
       ▼
  the tool runs and queries a business view   Python
       │
       ▼
  Azure SQL returns only allowed rows         Azure (row-level security)
       │
       ▼
  the model writes the answer, with sources   Azure
       │
       ▼
  front door checks every source cited        Python
       │
       ▼
  answer to the person
```

## Decisions

| Decision | Choice | Why | Decided |
| --- | --- | --- | --- |
| Language for app code | **Python** | The app is data work (reading documents, checking and moving records), which is Python's strength. The security tooling is already Python, so the app and its tooling share one main language, with SQL for the database and a little bash in the checks. | 25 September 2026 |
| Database language | **SQL** | Azure SQL only speaks SQL, so this isn't a choice. | Fixed |
| Where the Python runs | **Azure Functions** | It runs small pieces of code on triggers (a file passing its scan, a request arriving), it's billed per run, and it's one service to secure. | 25 September 2026 |
| Type checker | **pyright**, strict for the app's code, run in CI as basedpyright | It's the same checker as Pylance in the editor, so the editor and CI agree. basedpyright is packaged for Python, so CI installs it pinned by hash, without downloading Node at run time. | 27 September 2026 |
| Python packages and tools | **uv**, with one lockfile (`uv.lock`) and a 7-day cooldown | One file pins every package by hash. No version uploaded in the last 7 days is used, so a hijacked release has time to be caught first. | 27 September 2026 |
| Infrastructure as code | **Bicep** | The project is Azure-only. Bicep has no state file to store and protect, and its `what-if` compares the files with live Azure, which is the core of the drift check. | 25 September 2026 |
| How documents get into search | **AI Search indexer** (native), reading only the checked folder. Python writes a document's text there, as Document Intelligence read it, only after enforcement has accepted all of its records. | No code to write for indexing, no second reading of each document, and nothing that failed intake's checks or enforcement ever becomes searchable. | 26 September 2026 |
| How the agent answers within the asker's permissions | **Entra's on-behalf-of flow**: the agent's tools query Azure SQL as the person asking | Row-level security and masking then apply to that person, and the database's audit names them. Setting the scope in `SESSION_CONTEXT` instead would rest on our code setting it right every time. | 28 September 2026 |
| How search honours roles | **Allowed groups on each document**, filtered on every search with `site_id`; document types with masked fields are never indexed | A site filter alone would let a role read in search what the database hides from it. Redacting text before indexing would be a second masking system to keep in step with the database. | 28 September 2026 |
| Agent library | **Microsoft Agent Framework** (Python) | Microsoft's library for building agents that run in Foundry. Version 1.0 supports Python. | In the original design |
| Hooks and checks | **Python and bash** | Already built. Claude Code hooks can be any command; here they're Python, like the app. | In place |

## 1. Runs on Azure

| Service | Its job | Status |
| --- | --- | --- |
| Blob Storage | Holds every uploaded file exactly as received in an upload folder, and a checked folder holding the text of fully accepted documents, which only enforcement can write to | Not built yet |
| Azure AI Document Intelligence | Reads PDFs and photos and returns their text and tables | Not built yet |
| Azure SQL Database | Holds staging, the clean tables, the business views and the ledger, and enforces who sees which rows | Not built yet |
| Azure AI Search | Finds documents for the agent (RAG), filtered to the asker's sites and groups. Its indexer fills the index from the checked folder. | Not built yet |
| Azure OpenAI | The models the agents use | Not built yet |
| Foundry Agent Service (Microsoft Foundry, formerly Azure AI Foundry) | Hosts the agents | Not built yet |
| Azure Functions | The doorway to our Python: turns each trigger into a call to the app | Not built yet |
| Event Grid | Carries events between services, such as Defender's scan results to our intake Function | Not built yet |
| Microsoft Entra ID | Sign-in, and the roles (each role is an Entra group) | Tenant in place; role groups not built yet |
| Azure Key Vault | Holds the few secrets that remain | Not built yet |
| Azure AI Content Safety | Prompt shields: screens document text for attacks hidden in documents before the model reads it | Not built yet |
| Azure API Management | The front entrance: checks sign-in tokens, and per-user rate limits and quotas | Not built yet |
| Microsoft Defender for Cloud | Threat protection; Defender for Storage scans uploads for malware | Free foundational plans in place; the rest not built yet |
| Log Analytics | Collects the services' logs, including Azure SQL auditing and Key Vault logs | Not built yet |
| Private endpoints | Keep the data services off the public internet | Not built yet |
| The foundation | Resource groups, the region lock (East US 2), the monthly budget, and the keyless deploy identity | In place |

## 2. Code we write

Azure's services do the heavy lifting: reading documents, storing, searching, writing answers. None of them knows the rules of this business. Python holds those rules and makes the calls that connect the services.

### What Python does, piece by piece

None of this code is written yet. This is what each piece will do.

**Ingestion (glue).** Runs each time an uploaded file gets a clean malware verdict.

1. Confirms the malware verdict is clean, before touching the file, and notes which version of the file Defender scanned (the ETag in the scan result). No verdict, or any other verdict, stops the file: it isn't read, fingerprinted, copied or indexed. Every later read and copy asks for that exact version, so a file changed after its scan stops too.
2. Takes the file's site from the front door's record for that exact file path. A file at a path with no record is stopped before it's read. The site never comes from the file or anything the uploader sent.
3. Records the file in the intake table with its SHA-256 fingerprint. The same file uploaded twice is refused.
4. Checks the file's type and size before paying to have it read.
5. Sends the file to Document Intelligence and receives its text and tables. Keeps the text with the file's intake record.
6. Has Content Safety's prompt shields screen that text, long text in overlapping chunks within the service's size limit. A document with any chunk flagged, or that can't be screened, stops here and is held for a person: shields detect attacks rather than remove them, so its text never reaches a model and is never indexed.
7. Passes the screened text to the extraction agent marked as untrusted, as quoted data, never as instructions, and gets back candidate records with confidence scores.
8. Looks up names it already knows. "Cpy Ppr A4" becomes the master item "copy paper, A4" through the item aliases. A name it doesn't know goes to the data-governance role for approval; it's never created automatically.
9. Writes the candidate records to staging, records the write in the ledger, and hands them to enforcement.

**Enforcement (logic, the core).** Runs on every record in staging.

1. Checks each value on its own merits, whatever the agent's confidence score or explanation says: required fields present, formats right, amounts in range, the site and the item exist, and no duplicate of a record already loaded.
2. Checks records against each other, with the use case's rules: for example, a document's lines add up to its total, and a price matches the agreed price for that date.
3. Decides: accept (move the record to the clean tables), reject (it stays in staging with the reason), or hold it for a person to approve.
4. Records every decision in the ledger.
5. Once every record from a document is accepted (a held record counts only after a person approves it), writes that document's text, as Document Intelligence read it, into the checked folder, with a `site_id` metadata value set from the front door's upload record, and an `allowed_groups` value: the groups the use case allows to read that document type in full. Only enforcement writes to the checked folder, so a document with a rejected or held record, or a site an uploader chose, never reaches search. Document types with masked fields are never written there ([decisions](architecture.md#8-decisions-and-corrections-log)).

**Agent tools (logic).** The only things the agent can ask for.

- Each tool is a Python function with one job, such as "margin for this site and month" or "the documents from one source for these dates". The use case decides which tools exist.
- The model asks for a tool by name; our Python runs it. The model never touches the database itself.
- Tools read the business views only. None of them can write, delete or change a table.
- Tools run with the asker's access, through Entra's on-behalf-of flow, so the database returns only the rows that person may see.
- The search tool asks AI Search with a filter on the asker's sites and groups.
- Anything a tool returns that came from a document or a person is data, whoever wrote it, the asker included: document passages, and the text fields extracted into tables, such as an item name or a description. It's marked as untrusted before the model sees it. Document passages are also screened again by Content Safety's prompt shields; a passage they flag, or that can't be screened, is left out and logged, never passed on.
- Every result carries record IDs, so the answer can cite its sources.

**Front door (logic and glue).** Handles every question and every upload.

1. Checks the person's Entra sign-in and looks up their role groups. API Management has already checked the token; the front door doesn't rely on that alone.
2. Gets a token for Azure SQL on the person's behalf (Entra's on-behalf-of flow), so every tool queries the database as that person. Row-level security and masking apply to them, and the agent can never widen its own access.
3. Calls the agent with the question, and runs each tool the model asks for.
4. Checks every record the answer cites. If one is outside the person's scope, the answer is blocked and logged.
5. Shows only citations to the project's own records in an answer, never an external link or image, so a hidden image link can't carry data out.
6. Hands out upload links that expire quickly and can create only one new file, at a path the front door generates in the upload folder (a new upload ID for each link). A link can't replace a file once it's written. The front door records that exact path with the uploader's site, taken from their sign-in.
7. Keeps secrets, keys and masked fields out of the logs.

**Tests.** Run on every pull request, in the `python` required check.

- Each role sees only its own rows, and masked columns stay masked.
- A site manager can't read another site's data, directly or through the agent.
- No role can delete data or change the schema.
- Every enforcement rule has a record that passes it and a record that fails it.
- Two injection eval sets, run when prompts, models, retrieval, agent tools or the screening (its code or its Content Safety settings) change, and nightly. Screening: documents carrying injected instructions, with separate cases for intake (held) and for retrieval (left out, in text that passed intake), so each screen is exercised on its own; in every case the attacked text never reaches the model. Resilience: attacks deliberately run past screening, in a document or in a field extracted from one, each paired with a clean copy, give the same answer, make the same tool calls, and keep the same scope and citations.

**Seed data.** Fills a use case with realistic synthetic data.

- Generates the use case's records and documents (CSV files, PDFs and photos), with the mess real data has: inconsistent names across sources, different source systems, missing fields, duplicates. The restaurant use case's seed data is described in [its use case](use-cases/restaurant.md#seed-data).
- Loads everything through the same ingestion and enforcement path as real data. Nothing reaches the clean tables any other way.

### What SQL does

SQL defines the database, and the database enforces the rules no code can get around. It's the authority on who sees what: Python passes the person's identity and double-checks the answer's citations, but never grants access itself. SQL covers:

- The tables, with their keys and links: the [shared tables](architecture.md#5-shared-tables) and the use case's own. Every fact has a unique key that identifies it in its source (source system plus source ID where the source assigns one, otherwise a natural key such as supplier plus invoice number), so a second load of the same record is impossible.
- Row-level security: a site manager's query returns only their site's rows, whoever runs it, the agent included.
- Masking: sensitive columns, such as pay, are hidden from roles that don't need them.
- The business views the agent reads.
- The roles, each mapped to an Entra group. No role can delete data or change the schema.
- The ledger table, append-only and tamper-evident.

SQL is written as migration scripts in the repository and applied by the deploy job. Python never changes the schema.

### What Python never does

| Job | Done by |
| --- | --- |
| Reading documents | Document Intelligence. Python sends the file and receives the result. |
| Writing answers | The model in Azure OpenAI. Python runs the tools it asks for and checks its citations. |
| Ranking search results | AI Search. Python asks, with the site and group filter. |
| Indexing documents for search | The AI Search indexer, a native integration. |
| Scanning uploads for malware | Defender for Storage. Python only reads its verdict, and stops a file without a clean one. |
| Checking sign-in tokens and rate limits at the entrance | API Management, before our code runs. |
| Storing data | Azure SQL and Blob Storage. |
| Creating or changing Azure resources, and the native links between them | Bicep files, applied by the deploy job. |
| Setting up an agent | The agent's definition file, applied by the deploy job. |
| Changing the database schema | SQL migration scripts, applied by the deploy job. |
| Deciding who holds a role | An admin, through Entra group membership. |

## 3. Config we declare

| File | What it declares | Applied by | Status |
| --- | --- | --- | --- |
| Bicep files | The app's Azure resources, their settings, and the native links between them. The foundation was set up by hand once, before the deploy job existed. | The deploy job | Not built yet |
| Agent definitions | Each agent's instructions, model, tools, identity and access, and content filters | The deploy job | Not built yet |
| GitHub Actions workflows | The required checks; the scans of `main` (secrets and known vulnerabilities, after every merge and daily); and the deploy job | GitHub | Checks and scans in place; deploy job not built yet |
| `.claude/security-stack.json` | This project's names, IDs and setup status | Read by the tooling and the agent | In place |

Nothing in this layer is set up by hand in the Azure or Foundry portal. A change made there skips the checkpoint and counts as drift: see [What doesn't go through the checkpoint](security.md#what-doesnt-go-through-the-checkpoint).

## 4. How we build and guard it

| Tool | Its job | Status |
| --- | --- | --- |
| GitHub | The repository, and the pull request into `main` that every change passes | In place |
| GitHub Actions | Runs the five required checks on every pull request; later, the deploy job | Checks in place |
| pre-commit | Runs the commit checks on your computer, and again in CI | In place |
| detect-secrets | Finds keys and passwords before they're committed | In place |
| zizmor | Finds risky settings in the workflows | In place |
| Dependabot | Keeps the pinned GitHub Actions and the Python packages current | In place |
| Claude Code | The coding agent in your terminal | In place |
| The agent guard (Python) | Blocks ways to skip the checks, and asks you before any change to enforcement. Keeps every `az` command in the project's Azure tenant, and asks you before one that changes Azure | In place |
| The security gate (Python and bash) | Refuses blocked names, hidden suppressions, and anything that weakens a check | In place |
| uv | Installs Python 3.12 and the packages, pinned by hash in `uv.lock` | In place |
| ruff | Formats and lints the Python, including size limits and a ban on patching in tests | In place |
| basedpyright (pyright) | Checks the Python's types: strict for the app's code | In place |
| pytest | Runs the tests in random order; a skipped test fails the run | In place |
| diff-cover, deptry, vulture | Coverage of the changed lines, unused or undeclared packages, and code nothing calls | In place |
| pip-audit | Checks the Python packages for known vulnerabilities, on every pull request and daily | In place |
| Package check | Decided against. A package that doesn't exist fails to resolve, the 7-day cooldown keeps out new versions, and a new dependency needs your approval (`pyproject.toml` is enforcement). Lookalike names are left to that review | Not built, by decision |

The Python checks are one script, `scripts/check_python.sh`. It runs the same way on your computer and in the `python` required check. The testing rules are in [.claude/skills/testing/SKILL.md](../.claude/skills/testing/SKILL.md).

## Reusing this stack

To build another Azure product the same way:

1. **Set up the security stack first.** Follow [setup-guide.md](setup-guide.md). It builds layer 4 and the Azure foundation, and records the new project's names and IDs in `.claude/security-stack.json`.
2. **Copy this document.** Keep layers 1, 3 and 4, the native integrations and the decisions table. If the new product doesn't need a service, remove its row rather than leaving it listed.
3. **Add a use case for the new product,** starting from [the template](use-cases/_template.md). Layer 2's shape stays the same: ingestion, enforcement, agent tools, front door, tests, seed data, and the database in SQL. The use case supplies the domain tables, the enforcement rules, the tools and the seed data: see [Use cases](architecture.md#2-use-cases) and the [restaurant example](use-cases/restaurant.md).
4. **Record every change of decision** in the decisions table, with the date and the reason.

What carries over unchanged: Python, SQL, Bicep, Azure Functions, the four layers, the native-first wiring, and the rule that, after the one-time foundation, nothing in layers 1 and 3 is set up by hand.
