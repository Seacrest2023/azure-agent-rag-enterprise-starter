# AI risk mapping

This page maps the baseline to the [FINOS AI Governance Framework](https://air-governance-framework.finos.org/) as published on 28 September 2026 (version 2.0, October 2025, and its updates since): its 23 mitigations and 23 risks, in FINOS's own numbering. [control-mapping.md](control-mapping.md) answers the general audit question (SOC 2, ISO/IEC 27001, NIST CSF). This page answers the AI-specific one: which risks of running an agent over an organisation's own data this baseline mitigates today, which it mitigates by design once the later phases are built, and which it leaves to whoever adopts it.

As of 28 September 2026. Each FINOS mitigation carries its own references to ISO/IEC 42001 Annex A, the EU AI Act and NIST SP 800-53 Rev 5, and each FINOS risk to the OWASP Top 10 for LLM Applications (2025) and the OWASP Top 10 for Agentic Applications (2026). This page inherits those references from FINOS rather than deriving its own, so a reader who works in any of those five can find their number here. Frameworks not mapped: NIST AI RMF, the CSA AI Controls Matrix and MITRE ATLAS. [The OWASP view](#the-owasp-view) arranges the same statuses by the OWASP Top 10 for LLM Applications 2026 and the OWASP Top 10 for Agentic Applications, with the method that closes each gap.

## How to read this

Two agents are in scope, and every row says which:

- **Coding agent**: the agent that builds the baseline, in Claude Code and Copilot Chat on the owner's computer or through cloud connectors. Its controls are the repository security stack, and they are built: the checks are numbered as in the [checks inventory](checks-inventory.md).
- **Product agent**: the agent that will answer questions over the data. Its controls are the security plan in [architecture.md, section 10](architecture.md#10-security), numbered as items there, and most of them are not built yet.

| Status | Meaning |
| --- | --- |
| **In place** | Built and working, with a check or setting to point at. |
| **Partial** | Part is built; the row says what is missing and where that is recorded. |
| **Not built yet** | Designed and numbered in the security plan, not built. The row names the items. |
| **Not covered** | Left to the adopter, or a design choice not to do it; the row says which. |
| **n/a** | The mitigation does not apply to that agent. |

A status never moves up without a change to the check or item it names. Nothing here is a claim of conformance to ISO/IEC 42001 or the EU AI Act: whether a deployment is in scope of either, and at what risk class, is the adopter's determination.

## Coverage at a glance

Counted by what applies to each agent: 13 of FINOS's 23 mitigations apply to the coding agent, and 22 to the product agent.

| | Apply | In place | Partial | Not built yet | Not covered | n/a |
| --- | --- | --- | --- | --- | --- | --- |
| Coding agent | 13 | 2 | 9 | 0 | 2 | 10 |
| Product agent | 22 | 0 | 1 | 18 | 3 | 1 |

Read the two rows together: the repository security stack is built and the product is a design. For the coding agent, 11 of the 13 mitigations that apply are built, 2 in place and 9 Partial; each Partial names what's missing, and the [next section](#what-closes-the-partials) sorts those gaps into four open items and two limits of the guard. Its 2 not covered are a contract (007) and a design choice (015). That is the order the baseline commits to, enforcement before data, and the product agent's row is the backlog in FINOS's numbering.

## What closes the Partials

Four open items and two limits of the guard keep the coding agent's nine Partials from In place. The items hold eight of the nine; 003 is held by a limit alone. The first three items are in [security.md, "What's left for you"](security.md#whats-left-for-you):

| Open item | Rows it holds Partial | What closes it |
| --- | --- | --- |
| The agent acts with the owner's own GitHub sign-in | 011, 018, 023 | The agent's own GitHub account ("What's left for you", 1), the first of the two settings that close [independent review](control-mapping.md#the-two-controls-a-solo-owner-cannot-fully-evidence) |
| The agent acts with the owner's own Azure sign-in | 012, 018, 023 | A read-only Azure login for the agent day to day ("What's left for you", 5) |
| Each connector's reach, and which MCP servers load, haven't been reviewed | 001, 020 | The owner's review ("What's left for you", 2 and 4) |
| The guard's prompts and the owner's answers leave no record | 004, 021 | A hook that records each prompt and answer; not built yet |

The first three are the owner's steps and need no code. They would take the coding agent to 5 of its 11 built rows In place (011, 012 and 020 move up), and the hook to 7 (004 and 021). The other four (001, 003, 018, 023) would stay Partial, because each names a limit of the guard itself: it can't see inside a script the agent writes and then runs (018, 023), and what the agent reads goes to its model unscreened (001, 003). A sealed workspace for the agent ([workstation-hardening.md](workstation-hardening.md)) limits what such a script can reach, though the guard still doesn't see it.

## The mitigations

One row per FINOS mitigation, in FINOS order. PREV is preventative, DET is detective. References are FINOS's own.

| FINOS mitigation | Coding agent | Product agent | FINOS's references |
| --- | --- | --- | --- |
| **AIR-DET-001** AI Data Leakage Prevention and Detection | **Partial.** What enters the repository is screened: secrets at commit, at the pull request, and on main after each merge and daily (checks 11, 21, 44); private keys at commit (check 13); listed names at commit and at the pull request (checks 16, 17, 25). From the terminal, a request that sends data, a request to a host off the allowlist, a gist, a push to another remote or inline code that opens a connection asks the owner first (check 72). What the agent sends to its own model is not screened, and the cloud connectors that can copy files out of GitHub are an open review (security.md, "What's left for you", 2). | **Not built yet.** Private endpoints with public access off (item 12); search filtered on the asker's groups, with masked document types never indexed (item 17); logs that redact keys, tokens and masked fields (item 21). | ISO 42001: A.7.2, A.6.2.6, A.5.2; EU AI Act: none listed; 800-53: AC-4, AC-20, AU-13, CA-3, CA-7, IR-4, IR-9, MP-6, SA-9, SC-7, SC-8, SC-28, SI-4, SI-20 |
| **AIR-PREV-002** Data Filtering From External Knowledge Bases | **n/a.** The coding agent has no knowledge base of its own. | **Not built yet.** A document's text is indexed only after enforcement has accepted all of its records (item 15); text is screened for hidden instructions before the model sees it, and a flagged document is held for a person and never indexed (item 18); every staged value is validated on its own merits (item 8). | ISO 42001: A.7.2, A.7.3, A.7.4, A.7.6; EU AI Act: none listed; 800-53: AC-4, AC-22, MP-6, PT-2, SI-4, SI-12, SI-15, SI-19 |
| **AIR-PREV-003** User/App/Model Firewalling/Filtering | **Partial.** Egress is filtered: a request that sends data, a host off the allowlist, or inline network code asks the owner, and in modes that cannot ask it refuses (check 72); the deny rules keep the owner's sign-ins and `.env` files out of what the agent reads (check 70). What the agent reads is not screened for hidden instructions before its model sees it; the guard, not the agent, decides where data may go. | **Not built yet.** Prompt shields on document text and every field taken from it, in overlapping chunks, failing closed; tool results marked untrusted and passed as quoted data; read-only tools; outbound calls only to the project's Azure endpoints; no external links or images in answers (item 18). Per-user rate limits and quotas (item 20). | ISO 42001: A.6.1.3, A.6.2.2, A.9.2; EU AI Act: none listed; 800-53: AC-4, SC-5, SC-7, SI-4, SI-10, SI-15 |
| **AIR-DET-004** AI System Observability | **Partial.** What happens on GitHub is recorded: pull request history that cannot be rewritten (check 51), check history and Actions logs (checks 21 to 45), settings read back on demand (check 66). The guard's prompts in the terminal, and the owner's answers, leave no record. | **Not built yet.** Azure SQL auditing and Key Vault logs to Log Analytics, Defender for Cloud on (item 14); an append-only ledger of every agent write and every approval, reviewed regularly with digest verification (item 23). | ISO 42001: A.6.2.6, A.6.2.8; EU AI Act: none listed; 800-53: AC-2, AU-2, AU-3, AU-6, AU-11, AU-12, CA-7, IR-4, IR-5, RA-10, SI-4, SI-7 |
| **AIR-PREV-005** System Acceptance Testing | **In place.** The controls are themselves tested on every pull request: 283 tests of the gate, the settings script and the guard (check 23), the app's tests with 80% coverage of changed lines and no skipped test counted green (checks 35 to 37), known vulnerabilities (check 40). | **Not built yet.** Access tests per role in CI, including that a site manager cannot read another site's data directly or through the agent (item 9); a test that no role holds delete or schema-change rights (item 10); two prompt-injection eval sets that must pass before release (item 18). | ISO 42001: A.6.2.4, A.6.2.5; EU AI Act: Art. 9, Art. 15; 800-53: CA-2, CA-6, CM-4, SA-4, SA-11, SI-2, SI-6 |
| **AIR-PREV-006** Data Quality & Classification/Sensitivity | **n/a.** No AI data in the build. | **Not built yet.** Enforcement validates every staged value before it reaches the clean tables (item 8); a unique key on every fact and a fingerprint on every file block duplicates (item 16); sensitive columns masked by role and document types with masked fields never indexed (architecture sections 6 and 8, item 17). | ISO 42001: A.7.4, A.7.2, A.4.3; EU AI Act: Art. 10; 800-53: AC-1, AC-4, AC-16, AT-2, AT-3, CA-7, CM-13, PM-11, PM-22, PM-23, RA-2, SI-7, SI-10, SI-12, SI-18 |
| **AIR-PREV-007** Legal and Contractual Frameworks for AI Systems | **Not covered.** Terms with GitHub and the model providers are the adopter's (enterprise-level-gaps.md, vendor management). | **Not covered.** Terms with Microsoft for Azure OpenAI, Document Intelligence and Content Safety are the adopter's. | ISO 42001: A.2.3, A.10.2, A.10.3, A.8.5; EU AI Act: none listed; 800-53: AC-20, CA-3, IR-6, PM-30, PS-7, SA-4, SA-9, SR-2, SR-3, SR-5, SR-8 |
| **AIR-PREV-008** Quality of Service (QoS) and DDoS Prevention for AI Systems | **n/a.** The build has no service to protect. | **Not built yet.** Per-user rate limits and quotas through API Management (item 20); private endpoints (item 12). | ISO 42001: A.6.2.6, A.4.5; EU AI Act: none listed; 800-53: SC-5, SC-6, SC-7, SI-4, SI-10, SI-13, IR-4, CA-7 |
| **AIR-DET-009** AI System Alerting and Denial of Wallet (DoW) / Spend Monitoring | **n/a.** The coding agent's own token spend is the vendor's meter, outside this repository. | **Partial.** A monthly budget on the subscription alerts its owners as spending approaches it (check 63, in place). Per-user quotas (item 20) are not built. | ISO 42001: A.6.2.6, A.4.2; EU AI Act: none listed; 800-53: AC-2, CA-7, IR-4, SC-5, SC-6, SI-4 |
| **AIR-PREV-010** AI Model Version Pinning | **n/a.** The coding agent's model is chosen in the tool, not pinned in the repository. | **Not built yet.** Each agent's definition, its model included, kept in the repository and applied only by the deploy job (item 25); a scheduled drift check that compares the live agent with its definition (item 26). | ISO 42001: A.6.2.3, A.6.2.5, A.6.2.6, A.4.4; EU AI Act: none listed; 800-53: CM-2, CM-3, CM-4, CM-8, AU-2, SA-4, SA-10, SA-22, SR-4, SR-8 |
| **AIR-DET-011** Human Feedback Loop for AI Systems | **Partial.** The owner's answer is the loop: the guard asks before an enforcement change, a rule or setting change, a connector tool that touches enforcement, an Azure change, or an enforcement merge (checks 3 to 6 and 8); every review thread must be resolved before a merge (check 67); a lowering is recorded in the inventory's Lowered from the baseline table. What is open: from a cloud connector no guard asks, and GitHub does not hold the owner's own pull requests, so the loop there is the five checks (security.md, "Cloud to cloud"). | **Not built yet.** Extracted records wait in staging for enforcement (item 8); a document that fails screening is held for a person (items 15 and 18); term mappings, item aliases and rule changes are approved by the data governance role and recorded in the ledger (architecture section 6). | ISO 42001: A.6.2.6, A.8.2, A.8.3, A.3.3; EU AI Act: Art. 14, Art. 72; 800-53: CA-7, IR-6, PM-26, RA-5, SI-2, SI-4, AT-2, CA-2 |
| **AIR-PREV-012** Role-Based Access Control for AI Data | **Partial.** CI and deploy identities are scoped: read-only workflow token (check 54), deploy sign-in only from one environment and only from main (checks 59 and 65), deploy identity limited to the app resource group (check 64). The terminal agent works with the owner's own Azure sign-in; a read-only login for day-to-day work is open (security.md, "What's left for you", 5). | **Not built yet.** Each role is an Entra ID group mapped to a database role; row-level security on every table that carries a site; dynamic data masking; per-role views; the agent reads Gold views only and writes only to staging (architecture section 6); access tests in CI (item 9); no role holds delete or schema-change rights (item 10). | ISO 42001: A.3.2, A.7.2; EU AI Act: none listed; 800-53: AC-1, AC-2, AC-3, AC-5, AC-6, AC-16, AU-2, AU-6, IA-2, IA-4, IA-5, CM-12 |
| **AIR-DET-013** Providing Citations and Source Traceability for AI-Generated Information | **n/a.** The build produces code, which the checks judge; it does not produce answers. | **Not built yet.** Every answer cites records the asker can see, and an answer whose citation falls outside their scope is blocked and logged (item 19); the front end shows only citations to the project's own records (item 18). | ISO 42001: A.8.2, A.6.1.2, A.6.2.7; EU AI Act: Art. 13, Art. 86; 800-53: AU-10, SA-8, AC-16, SI-7, AT-2 |
| **AIR-PREV-014** Encryption of AI Data at Rest | **n/a.** The repository is GitHub's to encrypt. | **Not built yet.** The app's resources do not exist yet. When they do they are declared as infrastructure code, scanned on every pull request (items 13 and 24), with the remaining secrets in Key Vault (item 11). | ISO 42001: A.7.2; EU AI Act: none listed; 800-53: SC-28, SC-12, SC-13, CP-9, AC-19, SA-9, CM-3 |
| **AIR-DET-015** Using Large Language Models for Automated Evaluation (LLM-as-a-Judge) | **Not covered.** A design choice: the checks are rules and tests, not a second model's opinion. | **Not covered.** A design choice: enforcement validates every staged value by rule, whatever the confidence score or explanation (item 8). No judge model is planned. | ISO 42001: A.6.2.4, A.6.2.6; EU AI Act: none listed; 800-53: CA-2, CA-7, AU-6, RA-10, SA-11, SI-4, SI-7, SI-15 |
| **AIR-DET-016** Preserving Source Data Access Controls in AI Systems | **n/a.** No source data in the build. | **Not built yet.** The agent's tools query Azure SQL as the person asking, through Entra's on-behalf-of flow, so row-level security and masking apply to that person and the database's audit names them (item 7, architecture section 8); every search is filtered on the document's site and allowed groups against the asker's groups (item 17). | ISO 42001: A.7.2, A.7.3, A.9.2; EU AI Act: none listed; 800-53: AC-3, AC-4, AC-6, AC-16, AC-21, AU-2, AU-6, CA-7, CA-8, SI-4, SI-7 |
| **AIR-PREV-017** AI Firewall Implementation and Management | **n/a.** See 003. | **Not built yet.** Azure AI Content Safety prompt shields on every document and every field taken from one, failing closed: a document that is flagged, or that cannot be screened, never reaches the model (item 18). | ISO 42001: A.6.1.3, A.6.2.2, A.9.2; EU AI Act: none listed; 800-53: AC-4, SC-5, SC-7, SI-3, SI-4, SI-10, SI-15 |
| **AIR-PREV-018** Agent Authority Least Privilege Framework | **Partial.** The guard bounds what the agent may do from the terminal: no enforcement change, rule or setting change, or Azure change without the owner's yes, every Azure command inside the project's tenant (checks 3 to 8), no reading the owner's sign-ins or printing a token (checks 70 and 71), and no data out to a host the owner did not choose (check 72); in Copilot Chat it refuses rather than asks (check 68). What is open: the agent still acts with the owner's own Azure and GitHub sign-ins, and the guard cannot see inside a script the agent writes and then runs (security.md). | **Not built yet.** Read-only tools that reach only the project's Azure endpoints (item 18); reads Gold views only, writes only to staging through enforcement (architecture section 7); runs as the asker, so it can never widen anyone's access (item 7); its tools, identity and permissions declared in the repository and applied by the deploy job alone (item 25). | ISO 42001: none listed; EU AI Act: none listed; 800-53: AC-6, AC-2, AC-3, AC-5 |
| **AIR-PREV-019** Tool Chain Validation and Sanitization | **In place.** Every tool the required checks install is pinned by hash and read from main before any pull request file is on disk (checks 41 to 43); actions pinned to full commit SHAs (check 55); hook pins are full commit hashes and the pinned lists are frozen (checks 29 and 69); a pull request cannot rewrite the workflow that judges it (checks 26 to 28); new package versions wait seven days (check 43). | **Not built yet.** Every tool result that carries document or user text is marked untrusted and passed as quoted data, never instructions (item 18); the tools an agent may call are declared in the repository (item 25). | ISO 42001: none listed; EU AI Act: none listed; 800-53: SI-10, SI-15, SC-4 |
| **AIR-PREV-020** MCP Server Security Governance | **Partial.** A connector tool that touches enforcement asks the owner (check 6). Which MCP servers load, and which repositories each connector can reach and what it may do there, is the owner's review (security.md, "What's left for you", 2 and 4). | **n/a.** The design has no MCP servers; the agent's tools are its own, declared in the repository (item 25). | ISO 42001: none listed; EU AI Act: none listed; 800-53: SA-9, SC-8, SI-4, SR-3, SR-4, SR-5 |
| **AIR-DET-021** Agent Decision Audit and Explainability | **Partial.** FINOS's Tier 0, its recommendation for software development with code reviews, is met: the risk analysis and the rationale for each lowering are written down (security.md, enterprise-level-gaps.md, the inventory's Lowered from the baseline table), a person is in the loop (011), and GitHub keeps the record of every change (checks 47 to 51). Not met: the guard's prompts and the owner's answers are not logged. | **Not built yet.** An append-only, cryptographically chained ledger of every agent write and every approval (architecture section 5, item 23); blocked answers logged (item 19); citations on every answer (013). | ISO 42001: A.8.3, A.6.2.6; EU AI Act: Art. 12, Art. 13, Art. 26, Art. 72, Art. 86; 800-53: AU-2, AU-3, AU-6, CA-7 |
| **AIR-PREV-022** Multi-Agent Isolation and Segmentation | **n/a.** Coding sessions do not talk to each other; the guard judges each command on its own, in Claude Code and Copilot Chat alike (check 68). | **Not covered.** The design is a single product agent. A use case that adds agents gives each its own definition and identity (item 25); isolation between them is not designed. | ISO 42001: none listed; EU AI Act: none listed; 800-53: SC-7, SC-32, AC-4, SC-3 |
| **AIR-PREV-023** Agentic System Credential Protection Framework | **Partial.** Claude Code cannot read the owner's sign-in files or `.env` files in any permission mode (check 70), and the guard refuses commands that read or copy them or print a token (check 71). CI signs in to Azure with no stored credential, from one environment only (checks 46 and 65); secrets and private keys cannot be committed and main is rescanned daily (checks 11, 13, 21, 44). What is open: the agent still acts with the owner's own Azure and GitHub sign-ins, and a script it writes and then runs is not seen (security.md). | **Not built yet.** Managed identities everywhere, the few remaining secrets in Key Vault, no keys in app settings (item 11); uploads through short-lived, single-file SAS tokens (item 15); logs and telemetry that redact connection strings, tokens, keys and masked fields (item 21). | ISO 42001: none listed; EU AI Act: none listed; 800-53: IA-5, SC-28, AC-3, AU-6 |

## The risks

One row per FINOS risk, with the mitigations FINOS lists for it and where each stands here. OWASP references are FINOS's. A risk whose every mitigation is n/a for an agent does not apply to that agent.

| FINOS risk | OWASP | Mitigations FINOS lists | Coding agent today | Product agent |
| --- | --- | --- | --- | --- |
| **AIR-RC-001** Information Leaked To Hosted Model | LLM02 | 001, 002, 004, 006, 007, 012, 015, 020 | Partial: 001, 004, 012, 020; Not covered: 007, 015 | Not built yet: 001, 002, 004, 006, 012; Not covered: 007, 015 |
| **AIR-SEC-002** Information Leaked to Vector Store | LLM02, LLM08 | 006, 014, 016 | n/a | Not built yet: 006, 014, 016 |
| **AIR-OP-004** Hallucination and Inaccurate Outputs | LLM09 | 005, 006, 013, 015 | In place: 005; Not covered: 015 | Not built yet: 005, 006, 013; Not covered: 015 |
| **AIR-OP-005** Foundation Model Versioning | LLM09 | 004, 005, 010, 011, 015 | In place: 005; Partial: 004, 011; Not covered: 015 | Not built yet: 004, 005, 010, 011; Not covered: 015 |
| **AIR-OP-006** Non-Deterministic Behaviour | LLM09 | 004, 005, 010, 011, 015 | In place: 005; Partial: 004, 011; Not covered: 015 | Not built yet: 004, 005, 010, 011; Not covered: 015 |
| **AIR-OP-007** Availability of Foundational Model | LLM10 | 003, 004, 008, 009, 017 | Partial: 003, 004 | Partial: 009; Not built yet: 003, 004, 008, 017 |
| **AIR-SEC-008** Tampering With the Foundational Model | LLM03 | 007, 012, 020 | Partial: 012, 020; Not covered: 007 | Not built yet: 012; Not covered: 007 |
| **AIR-SEC-009** Data Poisoning | LLM03, LLM04, LLM05 | 002, 006, 012 | Partial: 012 | Not built yet: 002, 006, 012 |
| **AIR-SEC-010** Prompt Injection | LLM01, LLM04, LLM06, LLM10, ASI01 | 003, 017, 019 | In place: 019; Partial: 003 | Not built yet: 003, 017, 019 |
| **AIR-OP-014** Inadequate System Alignment | LLM07, ASI10 | 004, 005, 011, 015 | In place: 005; Partial: 004, 011; Not covered: 015 | Not built yet: 004, 005, 011; Not covered: 015 |
| **AIR-OP-016** Bias and Discrimination | none listed | 005, 006, 011, 015 | In place: 005; Partial: 011; Not covered: 015 | Not built yet: 005, 006, 011; Not covered: 015 |
| **AIR-OP-017** Lack of Explainability | ASI09 | 013 | n/a | Not built yet: 013 |
| **AIR-OP-018** Model Overreach / Expanded Use | LLM06 | 003, 004, 011, 017, 018 | Partial: 003, 004, 011, 018 | Not built yet: 003, 004, 011, 017, 018 |
| **AIR-OP-019** Data Quality and Drift | none listed | 004, 006, 015 | Partial: 004; Not covered: 015 | Not built yet: 004, 006; Not covered: 015 |
| **AIR-OP-020** Reputational Risk | LLM09 | 003, 007, 011, 013, 017 | Partial: 003, 011; Not covered: 007 | Not built yet: 003, 011, 013, 017; Not covered: 007 |
| **AIR-RC-022** Regulatory Compliance and Oversight | none listed | 005, 006, 007, 013, 014, 016, 021 | In place: 005; Partial: 021; Not covered: 007 | Not built yet: 005, 006, 013, 014, 016, 021; Not covered: 007 |
| **AIR-RC-023** Intellectual Property (IP) and Copyright | none listed | 006, 007 | Not covered: 007 | Not built yet: 006; Not covered: 007 |
| **AIR-SEC-024** Agent Action Authorization Bypass | LLM06, ASI02, ASI03 | 004, 018, 019, 021, 022, 023 | In place: 019; Partial: 004, 018, 021, 023 | Not built yet: 004, 018, 019, 021, 023; Not covered: 022 |
| **AIR-SEC-025** Tool Chain Manipulation and Injection | LLM01, ASI02, ASI05 | 004, 019, 021 | In place: 019; Partial: 004, 021 | Not built yet: 004, 019, 021 |
| **AIR-SEC-026** MCP Server Supply Chain Compromise | ASI04 | 004, 020, 023 | Partial: 004, 020, 023 | Not built yet: 004, 023 |
| **AIR-SEC-027** Agent State Persistence Poisoning | ASI06 | 004, 022 | Partial: 004 | Not built yet: 004; Not covered: 022 |
| **AIR-OP-028** Multi-Agent Trust Boundary Violations | ASI07, ASI08, ASI10 | 004, 022 | Partial: 004 | Not built yet: 004; Not covered: 022 |
| **AIR-SEC-029** Agent-Mediated Credential Discovery and Harvesting | LLM01, LLM06, ASI03 | 004, 023 | Partial: 004, 023 | Not built yet: 004, 023 |

## The OWASP view

The same statuses, arranged by the two OWASP lists: the [OWASP Top 10 for LLM Applications 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) (published August 2026) and the [OWASP Top 10 for Agentic Applications](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/) (ASI01 to ASI10, published December 2025). Each entry says what's in place, the gap, and the method: the approach that closes the gap, not a plan to build it.

**How the statuses are set.** An entry's FINOS risks are the ones whose OWASP references, in [The risks](#the-risks), cite it. Its mitigations are those risks' mitigations, with their statuses from [The mitigations](#the-mitigations). For each agent, an entry is:

- **In place** when every mitigation that applies is In place;
- **Partial** when at least one is built, but not all are In place;
- **Not built yet** when none is built;
- **n/a** when none applies.

A Not covered mitigation applies but isn't built, as in [Coverage at a glance](#coverage-at-a-glance), so it keeps an entry from In place, and the gap names it. An entry moves only when a mitigation row moves.

**The 2025 numbers.** FINOS's references use the 2025 edition of the LLM list. The 2026 edition kept all ten entries, moved eight and renamed one. This table gives both numbers, so a reader working from either edition finds the entry.

### OWASP Top 10 for LLM Applications 2026

| 2026 | Entry | 2025 | FINOS risks | Coding agent | Product agent |
| --- | --- | --- | --- | --- | --- |
| LLM01 | Prompt Injection | LLM01 | SEC-010, SEC-025, SEC-029 | Partial | Not built yet |
| LLM02 | Sensitive Information Disclosure | LLM02 | RC-001, SEC-002 | Partial | Not built yet |
| LLM03 | Excessive Agency | LLM06 | SEC-010, OP-018, SEC-024, SEC-029 | Partial | Not built yet |
| LLM04 | Supply Chain | LLM03 | SEC-008, SEC-009 | Partial | Not built yet |
| LLM05 | Data and Model Poisoning | LLM04 | SEC-009, SEC-010 | Partial | Not built yet |
| LLM06 | Unbounded Consumption | LLM10 | OP-007, SEC-010 | Partial | Partial |
| LLM07 | Misinformation | LLM09 | OP-004, OP-005, OP-006, OP-020 | Partial | Not built yet |
| LLM08 | Hidden Context Exposure | LLM07, as System Prompt Leakage | OP-014 | Partial | Not built yet |
| LLM09 | Vector and Embedding Weaknesses | LLM08 | SEC-002 | n/a | Not built yet |
| LLM10 | Improper Output Handling | LLM05 | SEC-009 | Partial | Not built yet |

Every entry that applies to the coding agent is Partial: its controls are built, and each has a limit named in [What closes the Partials](#what-closes-the-partials). None is In place, because no entry's mitigations are all In place. The product agent is design, apart from the budget alert under LLM06.

#### LLM01:2026 Prompt Injection

- **In place:** in Claude Code and Copilot Chat on the owner's computer, the guard, not the agent, decides what each tool call may reach. No enforcement, rule, setting or Azure change without the owner (checks 3 to 8); no reading the owner's sign-ins or printing a token (checks 70 and 71); no data out to a site off the allowlist without the owner (check 72); in Copilot Chat, it refuses where Claude Code would ask (check 68). It reads every command in a tool call the way the shell would, and if it can't run, the call is blocked (check 9). `AGENTS.md` tells agents that what they read is data, not instructions.
- **Designed for the product agent:** prompt shields over document text and every field taken from it, failing closed; every tool result that came from a document or a person marked untrusted and passed as quoted data; read-only tools; outbound calls only to the project's Azure endpoints; two injection eval sets (item 18).
- **Gap:** what the coding agent reads reaches its model unscreened. The guard judges each tool call, not what a script the agent writes and then runs goes on to do. A cloud connector runs no guard, so there only the required checks hold (security.md, "Cloud to cloud").
- **Method:** bound what an injected instruction can reach, rather than trying to catch every one. Decide each action's authority outside the model: the guard for the coding agent, and read-only tools running as the asker for the product. Screen untrusted text wherever a screen exists, and fail closed when it can't run. Pass everything a document or a person wrote as data. Test with an attacked and a clean copy of the same input. For scripts the guard can't read, a sealed workspace limits what they can reach ([workstation-hardening.md](workstation-hardening.md)). For connectors, which run no guard, narrow what each may reach, and give the agent its own account so its changes wait for the owner.

#### LLM02:2026 Sensitive Information Disclosure

- **In place:** secrets are screened at commit, at the pull request, and on `main` after each merge and daily (checks 11, 21, 44); private keys at commit (check 13); listed names at commit and at the pull request (checks 16, 17, 25). CI signs in to Azure with no stored secret (checks 46 and 65). The owner's sign-in files and `.env` files are kept out of the agent's reads (check 70) and its commands (check 71), and data leaves only for allowlisted sites or with the owner's yes (check 72).
- **Designed for the product agent:** private endpoints (item 12); search filtered on the asker's groups, with masked document types never indexed (item 17); logs that redact keys, tokens and masked fields (item 21).
- **Gap:** what the agent sends to its own model isn't screened, and each connector's reach is an open review ([security.md, "What's left for you"](security.md#whats-left-for-you), 2). Terms with the model providers are the adopter's (007).
- **Method:** keep the value out of reach, rather than scan for it on the way out. Hold no secrets where the agent works, deny the agent the owner's credentials, admit into the model's context only what the asker may see, and allowlist where data may go. Scanning is the second layer.

#### LLM03:2026 Excessive Agency

- **In place:** in Claude Code and Copilot Chat, the guard asks before an enforcement, rule, setting, connector or Azure change and before an enforcement merge, and refuses in modes that can't ask (checks 3 to 8, 68). Every `az` command stays in the project's tenant (check 7). CI's token is read-only, and Actions can't approve pull requests (check 54). The deploy identity reaches only the app resource group (check 64).
- **Designed for the product agent:** read-only tools that reach only the project's endpoints (item 18); it reads business views and writes only to staging (architecture section 7); it runs as the asker (item 7); its tools, identity and permissions are declared in the repository and applied only by the deploy job (item 25); no role holds delete or schema-change rights (item 10).
- **Gap:** the coding agent acts with the owner's own GitHub and Azure sign-ins, so neither platform can tell it from the owner. From a cloud connector, no guard asks at all.
- **Method:** give every agent its own identity with only the rights its job needs: write, not admin, on GitHub, and read-only in Azure day to day. Decide authority per call, outside the model. Require a named person's yes for anything that changes the controls. Declare each agent's tools and permissions as code, so widening them is a reviewed change.

#### LLM04:2026 Supply Chain

- **In place:** every tool the checks install is pinned by hash and read from `main` first (checks 41 and 42), and the pinned lists are frozen (check 29). Actions are pinned to full commit SHAs (check 55) and hook repositories to full commit hashes (check 69). New versions wait seven days (check 43). A known vulnerability blocks a merge, and `main` is re-audited daily (checks 40 and 45). A new dependency needs the owner, because `pyproject.toml` is an enforcement file. FINOS files these under 019, which it doesn't list for this entry's risks, so they don't set its status.
- **Designed for the product agent:** each agent's model pinned in its definition, applied by the deploy job, with a drift check (items 25 and 26).
- **Gap:** which MCP servers load, and each connector's reach, are the owner's review (020). The dependencies pre-commit installs for its hooks in CI aren't hash-pinned. A lookalike package name is caught only by the owner's review. Terms with vendors are the adopter's (007).
- **Method:** pin everything fetched by a content hash or a full commit hash, and verify it on arrival. Wait out a cooldown on new releases. Freeze what the trusted jobs install. Treat agent extensions (MCP servers, connectors, editor extensions) as dependencies: pinned, and reviewed before they load.

#### LLM05:2026 Data and Model Poisoning

- **In place:** the coding agent trains nothing and has no knowledge base. What it reads is the repository, and nothing reaches `main` without the required checks (check 47). In a guarded session, a change to an enforcement file also needs the owner (checks 3 and 5). From a cloud connector no guard asks, and GitHub doesn't hold the owner's own pull requests, so there the required checks are the only gate (security.md, "Cloud to cloud").
- **Designed for the product agent:** a document's text is indexed only after enforcement has accepted all of its records (item 15); it's screened before the model reads it, and a flagged document is held for a person (item 18); every staged value is validated on its own merits (item 8); fingerprints and unique keys stop the same data loading twice (item 16).
- **Gap:** the product side is design; what the coding agent reads isn't screened.
- **Method:** for a system that retrieves rather than trains, poisoning is an ingestion problem. Record where each document came from, accept every record before anything is indexed, hold what fails screening for a person, and make every load idempotent.

#### LLM06:2026 Unbounded Consumption

- **In place:** a monthly budget alerts the subscription's owners as spending approaches it (check 63). For the coding agent, FINOS's mitigations here are egress filtering (check 72) and observability (004); its own token spend is the vendor's meter, outside the repository.
- **Designed for the product agent:** per-user rate limits and quotas through API Management (item 20); private endpoints (item 12).
- **Gap:** the budget detects after the money is spent. Nothing caps spending or requests today.
- **Method:** prevent before detecting. Per-person quotas and rate limits at the gateway, a cap on tokens per request and per conversation, a hard spending cap that stops the service rather than alerting, and alerts as the last layer.

#### LLM07:2026 Misinformation

- **In place:** the coding agent's output is code, and deterministic checks judge all of it: lint, types, tests with 80% of changed lines covered and no skipped test counted green, dependencies, dead code and known vulnerabilities (checks 32 to 40). The controls themselves are tested on every pull request (check 23). No model judges another model's output, by design (015).
- **Designed for the product agent:** every answer cites records the asker can see, and an answer citing outside their scope is blocked and logged (item 19); answers show only citations to the project's own records (item 18); enforcement validates every staged value whatever the confidence score (item 8).
- **Gap:** grounding and the citation check are design.
- **Method:** ground every answer in records the asker may see, and show them. Block, rather than warn, when a citation falls outside scope. Make verdicts deterministic, rules and tests, so the same input gets the same answer. Never treat a confidence score as validation.

#### LLM08:2026 Hidden Context Exposure

The 2026 edition renamed System Prompt Leakage and widened it to everything an application puts in front of the model that the user doesn't see: retrieved documents and tool definitions as well as the system prompt. FINOS's references cover the system prompt; this page maps the rest to the items below.

- **In place:** the coding agent's instructions are files in the repository (`AGENTS.md`, `CLAUDE.md`), with nothing hidden in them to extract. In a guarded session, changing them needs the owner (checks 3 and 53); from a cloud connector, only the required checks stand in the way (security.md, "Cloud to cloud"). Secrets can't be committed, and `main` is rescanned daily (checks 11, 21, 44). The owner's sign-ins and `.env` files never enter the agent's context (checks 70 and 71).
- **Designed for the product agent:** each agent's instructions and tool definitions kept in the repository and applied only by the deploy job, with a drift check (items 25 and 26); the few remaining secrets in Key Vault (item 11); retrieval filtered on the asker before a passage enters the context, and masked document types never indexed (item 17); tool results marked untrusted (item 18).
- **Gap:** until the product runs, only its design keeps a secret, or another person's data, out of its context.
- **Method:** assume anything placed before the model can be shown to the person using it. Put nothing in the context they may not see: filter retrieval on the asker before, never after; keep credentials out of prompts and tool definitions; version instructions and tool definitions as code.

#### LLM09:2026 Vector and Embedding Weaknesses

- **In place:** n/a. The coding agent has no index.
- **Designed for the product agent:** only accepted documents are indexed (item 15); every search is filtered on the document's site and allowed groups against the asker's groups, and masked document types are never indexed (item 17); tools query as the asker through the on-behalf-of flow (item 7).
- **Gap:** all of it is design.
- **Method:** enforce permissions inside the retrieval query, against the asker's identity, never by trimming results afterwards. Take them from the same groups the database uses, so search can't show what the database hides.

#### LLM10:2026 Improper Output Handling

- **In place:** the coding agent's output is code, and nothing reaches `main` without the checks (checks 32 to 40, 47); no suppression can switch one off (check 24). FINOS maps this entry only to data poisoning, so its status rests on 012, not on these checks.
- **Designed for the product agent:** answers show only citations to the project's own records, never external links or images, and tool results pass as quoted data (item 18).
- **Gap:** the product's output handling is design.
- **Method:** treat model output as untrusted input to whatever comes next. Validate it deterministically before it lands, render no active content from it (links, images, markup), and never run it without a check.

### OWASP Top 10 for Agentic Applications

These IDs are FINOS's own references, so no crosswalk is needed. The coding agent is Partial on nine and n/a on one; the product agent is Not built yet on all ten.

| Entry | FINOS risks | Coding agent | Product agent |
| --- | --- | --- | --- |
| ASI01 Agent Goal Hijack | SEC-010 | Partial | Not built yet |
| ASI02 Tool Misuse | SEC-024, SEC-025 | Partial | Not built yet |
| ASI03 Identity and Privilege Abuse | SEC-024, SEC-029 | Partial | Not built yet |
| ASI04 Agentic Supply Chain Vulnerabilities | SEC-026 | Partial | Not built yet |
| ASI05 Unexpected Code Execution | SEC-025 | Partial | Not built yet |
| ASI06 Memory and Context Poisoning | SEC-027 | Partial | Not built yet |
| ASI07 Insecure Inter-Agent Communication | OP-028 | Partial | Not built yet |
| ASI08 Cascading Failures | OP-028 | Partial | Not built yet |
| ASI09 Human-Agent Trust Exploitation | OP-017 | n/a | Not built yet |
| ASI10 Rogue Agents | OP-014, OP-028 | Partial | Not built yet |

- **ASI01 Agent Goal Hijack.** Stands as LLM01. `AGENTS.md` also states the project's purpose and tells agents to stop on anything outside it: a tripwire, not a control, because a hijack works by overriding instructions. **Method:** state each agent's purpose in its rules, and rely on the checks that hold whatever it was told.
- **ASI02 Tool Misuse.** In Claude Code and Copilot Chat on the owner's computer, the guard judges every tool call (checks 1 to 8, 68, 71, 72); connector tools called from there that touch enforcement ask (check 6), but a cloud connector's own calls meet only the required checks; Copilot Chat's extension installs are refused (check 68). The product agent's tools are read-only and declared in the repository (items 18 and 25). **Method:** allow each tool only the actions its job needs, judge every call outside the model, and keep the tool list itself as reviewed code.
- **ASI03 Identity and Privilege Abuse.** CI's identities are scoped (checks 54, 59, 64, 65), and the owner's sign-ins are unreadable to the agent (checks 70 and 71), but the coding agent acts with the owner's own sign-ins. The product agent runs as the asker, on managed identities (items 7 and 11). **Method:** one identity per agent, least privilege, credentials an agent can use but never read, and actions run as the person they're for.
- **ASI04 Agentic Supply Chain Vulnerabilities.** Connector tools that touch enforcement ask (check 6), and Copilot Chat's extension installs are refused (check 68); which MCP servers load, and each connector's reach, are the owner's review (020). The product design has no MCP servers. **Method:** treat MCP servers, connectors and editor extensions as dependencies: an allowlist of which may load, pinned versions, and a review before each is added.
- **ASI05 Unexpected Code Execution.** In the sessions it runs in, the guard reads every command in a tool call the way the shell would, and if it can't run, the call is blocked (check 9). CI runs a pull request's code without credentials and with a read-only token (setup prompt, decision 2; check 54). What a script the agent writes and then runs goes on to do isn't read, and a cloud connector runs no guard. **Method:** run agent-written code where it can reach nothing that matters: a sealed workspace without the owner's sign-ins ([workstation-hardening.md](workstation-hardening.md)), and CI jobs that hold no credentials.
- **ASI06 Memory and Context Poisoning.** The files that tell the coding agent what to do in future sessions, `AGENTS.md` and `CLAUDE.md`, are enforcement files (checks 3 and 53). The product design keeps no agent memory. **Gap:** two kinds of instruction file aren't in CODEOWNERS, so a change to one merges on green: the skills in `.claude/skills/`, which Claude Code loads as instructions, and the prompt templates in `docs/prompts/` and `docs/security-setup-prompt.md`, which are handed to agents to run. And from a cloud connector, even a listed file changes with only the required checks in the way, because no guard asks and GitHub doesn't hold the owner's own pull requests (security.md, "Cloud to cloud"). **Method:** treat every file an agent loads or is handed as instructions as enforcement (rules, skills, prompt templates), so changing what a future session is told needs the owner. Give the agent its own account, so GitHub holds its changes to those files for the owner whichever way it connects.
- **ASI07 Insecure Inter-Agent Communication.** Coding sessions don't talk to each other, and the product design is a single agent; isolation between agents isn't designed (022). **Method:** if agents are added, give each its own identity, authenticate every message between them, and judge each agent's actions as if the message came from outside.
- **ASI08 Cascading Failures.** The guard and the gate fail closed (checks 1 to 9, 24 to 30), and every change passes one checkpoint before `main` (check 47). **Method:** fail closed at every step, so an error stops the flow instead of passing it on, and keep one checkpoint every change must pass.
- **ASI09 Human-Agent Trust Exploitation.** For the coding agent, n/a in FINOS's mapping; still, each stop the guard makes says what it's asking and recommends a way forward, and the owner's answers aren't recorded (004, 021). The product agent cites every answer and blocks one that cites outside the asker's scope (items 18 and 19). **Method:** show the evidence behind every answer and every request for approval, keep requests rare enough to be read, and record each answer.
- **ASI10 Rogue Agents.** The required checks hold whatever the coding agent does, and the guard does in the sessions it runs in. The product agent's definition is code, with a scheduled drift check (items 25 and 26). The guard's prompts and answers leave no record. **Method:** declare what each agent may be, compare the live agent with its definition on a schedule, fail loudly on drift, and log every approval.

## What this page is for

Three uses.

1. **A threat model with a backlog attached.** The product agent column is the security plan restated as the risks each item mitigates. When an item is built, its rows move to In place in the same pull request, and the risk table shows which FINOS risks that closed.
2. **A bridge to the AI standards.** A reader working to ISO/IEC 42001, the EU AI Act, NIST SP 800-53 or either OWASP list finds their numbering in the last column without a second mapping exercise. The OWASP view goes the other way: it starts from each OWASP entry, in the 2026 numbering, and says what's in place, the gap and the method.
3. **The gaps, named.** Two mitigations are design choices (015, 022) and one is contractual (007). The rest of what is missing is the product itself, and it is numbered.

## Keeping this page current

A pull request that builds a security plan item moves every row that names it, and a pull request that adds, lowers or changes a check updates the rows that cite it, in the same pull request as [control-mapping.md](control-mapping.md). Coverage at a glance and What closes the Partials are counted from the mitigations table, so a row that moves updates both. When FINOS publishes a new version, the references in the last column are re-read from its mitigation pages before anything else here changes. The OWASP view is counted from the mitigations table in the same way, so a row that moves updates every entry that cites it. When OWASP publishes a new edition, its numbers go into the crosswalk first, and then FINOS's references are re-read.
