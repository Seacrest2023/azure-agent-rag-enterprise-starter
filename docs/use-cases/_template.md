# Use case: your vertical

A use case applies the baseline to one vertical. Copy this file to `docs/use-cases/<vertical>.md` and fill it in. Everything specific to the domain lives here: the research, the data model, the rules and the examples. The machinery stays in the generic docs, [architecture.md](../architecture.md) and [stack.md](../stack.md). The [restaurant use case](restaurant.md) is a worked example.

**Status:** not designed yet.

## Answer these first

An agent asks the owner these questions before it drafts anything else. The answers shape every section below.

1. **The domain.** Who runs the operation, how many sites or teams there are, and which decisions the agent should help with.
2. **The sources.** Every system and document type the data comes from: its format (CSV, PDF, image, feed), how often it arrives, and which system is the source of truth for each fact.
3. **The entities.** The things the business counts and prices (items, people, orders, suppliers), and the names each source uses for them.
4. **The roles.** Who asks questions, and what each role may see: which sites, which document types, which fields.
5. **Sensitive fields.** Pay, personal details, or anything else that must be masked, and which document types hold them. Those document types are never indexed for search.
6. **The questions.** Ten questions people will ask the agent, in their own words. They become the first agent tools and the first eval set.

## The problem

What is messy about this domain's data, and what a good answer is worth.

## How the design was derived

| Step | Input | What it contributed |
| --- | --- | --- |
| 1 | | |

## Domain terms

| Term | Plain meaning |
| --- | --- |
| | |

## Data model

Tables marked **shared** are the baseline's [shared tables](../architecture.md#5-shared-tables); the rest belong to this use case. Give every table its grain and its unique key: source system + source ID where the source assigns one, otherwise a natural key.

### Dimensions

| # | Table | Grain | Unique key |
| --- | --- | --- | --- |
| | | | |

### Facts

| # | Table | Grain | Unique key |
| --- | --- | --- | --- |
| | | | |

### Gold views

- **`vw_<name>`**: the question it answers.

## Roles in this use case

The baseline's [roles](../architecture.md#6-roles-and-access), in this domain's terms. Search filters on the groups allowed to read each document type in full ([decisions](../architecture.md#8-decisions-and-corrections-log)), so list them here.

| Document type | Groups allowed to read it in full | Masked fields (never indexed if any) |
| --- | --- | --- |
| | | |

## Enforcement rules

The checks each record must pass before it reaches Silver. Write them as test cases first, including the cases that must not trigger ([testing skill](../../.claude/skills/testing/SKILL.md)).

## Decisions and corrections

| Decision | Reason |
| --- | --- |
| | |

## Through the pipeline

One real document followed from upload to an answer: what intake checks, what the extraction agent proposes, what enforcement accepts or holds, and what a person asking sees.

## Seed data

What the generator produces, with the mess real data has.

## Open items

- None yet.
