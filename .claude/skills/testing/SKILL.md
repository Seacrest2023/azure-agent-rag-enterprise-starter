---
name: testing
description: Decides which tests to write for a change in this repository and how, so tests prove real behaviour without becoming a maintenance burden. Covers unit, behavioural, event, integration, end-to-end and model evals, fakes instead of mocks, where silent failures hide, and the access tests the product can't ship without. Use it whenever you write or change application code or tests here, fix a bug, add a pipeline stage, enforcement rule, access rule, agent tool or prompt, or when asked what or how to test, even if tests aren't mentioned.
---

# Testing

A test earns its place when it fails because a behaviour someone relies on broke, and keeps passing through refactors that don't change behaviour. Tests that check how the code works inside break on every refactor and still miss real failures. Everything below follows from that.

## Pick the level

Test each behaviour once, at the lowest level that can prove it.

| The change | Test | Folder |
| --- | --- | --- |
| Pure logic with cases: an enforcement rule, parser, normaliser, calculation | **Unit.** A table of cases, including the ones that must not trigger. Add a property test (hypothesis) when inputs are messy: dates, amounts, OCR text, item names. | `tests/unit` |
| What a use case does for its caller: take in a file, promote staging to Silver, answer a question | **Behavioural.** Build the app through the composition root with fakes for external services, call the entry point, check the outcome. The default for application code. | `tests/behaviour` |
| An event that starts work: a file uploaded, a scan result, one stage finishing | **Event.** Give the handler the event exactly as its producer sends it, and check that the handler acted on it: a write proves nothing about the read. Azure can deliver an event more than once, so the same event twice gives one result. A malformed event is rejected, not crashed on. Producer and handler share one event model. | `tests/events` |
| What the database or storage actually does: row-level security, masking, permissions, unique keys, transactions, the SQL itself, migrations | **Integration.** Real SQL Server and Azurite in containers. | `tests/integration` |
| What only the deployed system can show: Entra groups to database roles, identities, Function triggers and bindings, private endpoints, settings, the deploy | **End-to-end.** Extend one of the few journeys in the dev environment, with a case that must be refused. | `tests/e2e` |
| Prompts, models, retrieval, agent tools, or the screening of document text | **Eval.** Score a small golden set against a threshold, and compare with the current version: keep the change only if the scores hold. Include two injection sets: documents carrying injected instructions that screening must catch, with separate cases for intake (held) and retrieval (left out), each asserting the attacked text never reaches the model, and attacks run past screening, in a document or in a field extracted from one, each paired with a clean copy, that must give the same answer, make the same tool calls, and keep the same scope and citations. | `tests/evals` |

Three cases need no table:

- **Bug fix.** First a test that fails because of the bug, at the lowest level that shows it. Then the fix.
- **Refactor.** No new tests. If tests break while behaviour hasn't changed, they were testing implementation: rewrite them against behaviour.
- **Retired behaviour.** Delete its tests in the same change, and name what retired them in the commit message. Stale red tests teach everyone to ignore red.

## Where failures hide

Most tests go where the logic is. The few extra ones go where a failure would be silent, with everything green while the product is wrong. At each of these spots, test the thing that must not happen:

- **A default that carries on after a failure.** A missing setting, identity or scope must stop the work, never let it run unfiltered.
- **A handoff.** A stage wrote its output; check that the next stage read it and acted.
- **A fallback that hides a dead main path:** a cache, a retry, a default value.
- **Old and new paths side by side** during a change: prove the new one runs and the old one is gone.
- **A test more privileged than production.** Seeding and querying as the admin connection proves nothing about access; query as the restricted identity.
- **Instructions hidden in a document.** An answer that quietly follows them still looks fine. The injection evals check that screening catches them, and that an attack run past screening leaves the answer, the tool calls, the scope and the citations the same as its clean copy's.

## Rules

1. **Public entry points, observable outcomes.** Check rows stored, values returned, events published and ledger entries. Never check which functions were called, or a value the test itself put in. That is what lets the code change without the tests changing.
2. **Fakes, not patches.** Each external service (Azure OpenAI, Document Intelligence, AI Search, Blob Storage, publishing events, the clock) sits behind a small interface that the composition root, the one place the app is assembled, hands to the code. Adapters stay thin: they translate and call, with no business logic, so faking them loses nothing. An Azure Function is an adapter too. It turns its trigger into a call to the app, so tests call the app directly. Tests assemble the app the same way and swap in fakes from `tests/fakes`: one shared fake per service, not a mock per test. Don't patch project code (`mock.patch`, `monkeypatch.setattr`): patches couple tests to internals and skip the real wiring. `monkeypatch.setenv` is fine.
3. **Every fake has a real twin.** A fake implements the same `Protocol` as the real adapter, so the type checker catches signature drift. Write an adapter's tests once and run them against the fake and the real thing: the container in integration, or the dev resource for services with no local version. A fake that drifts from the real service then fails in CI, not in production.
4. **The database is real wherever it is the point.** Row-level security, masking, permissions, unique keys and transactions only mean something in the real engine. Behavioural tests use the in-memory repository for everything else.
5. **Builders for test data:** functions with sensible defaults, so a test states only the fields that matter to it, like `an_invoice_line(amount="12.345")`. Synthetic data only: no real customer records, names or pay.
6. **One behaviour per test, named for it:** `test_low_confidence_amount_goes_to_review`.
7. **Deterministic.** No sleeps, and no real clock or randomness (inject them). No network in unit, behavioural and event tests. Each test builds its own app and fakes and shares no state with other tests, so tests pass in any order. A failure that depends on the order means a test leaks state: fix the leak. A flaky test is fixed, not retried until it passes.
8. **See it fail.** Write the test before the code, or break the code briefly and watch the test go red. A test never seen failing may test nothing.
9. **Friction is a design signal.** More than three fakes, or a screen of setup for one test, means the code under test does too much. Split the code; don't grow the test.

A failing test you can't fix goes to the owner. It is never skipped, marked as expected to fail, or deleted to get to green. That is the repository's one rule: agents never skip or change enforcement without the owner's approval.

## Don't test

- Framework and SDK behaviour: pydantic's own validation, the Azure SDK's retries.
- Plain data classes, constants and pass-through glue; behavioural tests already run them.
- Private helpers directly.
- Exact model wording.
- Logging, except the audit ledger, which is product behaviour.
- A behaviour that a lower-level test already proves.

## Access tests

Leaking one site's data to another is the product's main risk, so these tests are never skipped or traded for an eval. They live in `tests/access`, whatever their level, and run with the integration tests. `.github/CODEOWNERS` lists that folder, so every change there is an enforcement change the owner approves.

- **Every Gold view, and every path the product's agent reads through:** an allowed and a denied case per role, against real SQL, as the restricted identity. A site manager sees their own site, never another's, directly or through the agent. Masked columns stay masked (architecture Section 10, item 9).
- **No scope, no answer.** A request without the asker's scope fails with an error. It never runs unfiltered, and never returns an empty result the agent could present as fact.
- **No role holds delete or schema-change rights** (item 10).
- **Search and citations:** search results are filtered to the asker's sites, and an answer citing a record outside their scope is blocked and logged (items 17 and 19).
- **Protected:** with the first access tests, also protect their file in the security gate. Add a `protect <file> test_names_of "access test cases"` line to `scripts/security_gate.sh`, like the lines for the gate's and the guard's own tests. Removing or renaming a case then fails the gate outright. The gate tracks test names, so give each access case its own `def test_…` rather than a parametrize row.

Evals measure answer quality. They never stand in for these guarantees.

## When

- **A new flow** starts with a walking skeleton: one end-to-end test that pushes a trivial file through every stage in dev. Unit and behavioural tests fill in as each stage becomes real.
- **Enforcement rules:** write the cases first. They are the specification.
- **A new external service:** its adapter and twin tests come first; then other tests use the fake.
- **A document that broke extraction** joins the eval set, anonymised.
- **Before committing,** run the unit, behavioural and event tests; they take seconds. The command is in the README's development setup. Pull requests also run the integration and access tests. End-to-end runs after each deploy to dev. Evals run when prompts, models, retrieval, agent tools or the screening of document text change, and nightly.

## Coverage

At least 80% of changed lines, and 90% for the enforcement layer. Coverage points at untested code; don't write tests just to raise it.

## Writing the test

Follow the nearest existing test in the same folder. For the first of its kind:

```python
# Behavioural: the app assembled as in production, fakes at the edges.
def test_low_confidence_amount_goes_to_review():
    fakes = Fakes()
    app = build_app(test_settings(), fakes)

    app.intake.promote(a_staged_invoice_line(amount_confidence=0.6))

    assert app.silver.invoice_lines() == []
    assert fakes.review_queue.items[0].reason == "low_confidence:amount"
```

```python
# Event: the handler acts on what the producer really sends, once.
def test_ocr_event_writes_staging_rows_once():
    fakes = Fakes()
    app = build_app(test_settings(), fakes)
    app.ocr.finish(an_invoice_file(lines=3))  # the producer publishes to the fake
    event = fakes.events.published[-1]

    app.handle(event)
    app.handle(event)  # delivered again

    assert len(app.staging.rows_for(event.intake_id)) == 3
```

```python
# Integration: row-level security in the real engine, queried as the restricted user.
def test_site_manager_sees_only_their_site(sql):  # sql: SQL Server container fixture
    sql.as_admin().seed(sales_at("site-a"), sales_at("site-b"))

    rows = sql.as_user("site_manager", scope=["site-a"]).query(
        "SELECT DISTINCT site_id FROM gold.vw_finance_summary"
    )

    assert {r.site_id for r in rows} == {"site-a"}
```
