# Engineering handbook: Home Base

Nov 9, 2026 · @Andrew

## 1. Purpose and source of truth

This handbook defines how Home Base is built: structure, conventions, checks, tests, logging, security and release. It exists so that every change, whether written by Andrew or by Claude Code, is consistent, testable and auditable, and so that no business rule is ever invented during implementation.

### Source-of-truth order

When two documents disagree, the higher one wins until the lower one is corrected.

1. **[Reference document](https://claude.ai/artifact/1afSUZRJUrdEzyBhz4PSb5):** vision, principles, architecture direction.
2. **[Phase 1 spec](https://claude.ai/artifact/1HA36sxkLjJrWkjihSs5JQ):** scope, data model, screens, business rules.
3. **This handbook:** how the code is written, checked and released.
4. **Decision records (ADRs)** in the repository: specific technical choices and their reasons.
5. **Rule catalogue and tests** in the repository: the executable form of the spec's rules.
6. **Code.**

### Non-negotiable rules

- **No rule without a source.** Every business rule in code has a rule ID that traces back to the spec. If the spec doesn't say it, the code doesn't do it: the spec is updated first.
- **No claim without evidence.** "Done" means the definition of done in section 15 is met. "Verified in tests" and "verified on the deployed app" are different claims and are always stated separately.
- **Code decides, AI explains.** Deterministic code sets every status, score, date and priority. AI extracts, words and drafts, and its output is always validated and marked.
- **Nothing leaves the platform without a person.** No email, submission or external write happens without explicit founder approval.

### How to use this handbook

- Read sections 1, 4, 6 and 15 before any change.
- The repository's `CLAUDE.md` (section 16) summarises this handbook for Claude Code and links back here.
- Changing a rule in this handbook requires an ADR when it affects architecture, tooling or security.

## 2. Stack

The stack follows the reference document: Python backend, React and TypeScript frontend, PostgreSQL, EU hosting. Choices marked **default** are what this handbook assumes; each is confirmed or replaced by the ADR named, before the first line of code (section 17).

| Layer | Choice | Status |
| --- | --- | --- |
| Language, backend | Python 3.12, fully typed | Decided |
| Web framework | FastAPI | Default · ADR-001 |
| Validation and schemas | Pydantic v2 | Decided (follows FastAPI) |
| Database | PostgreSQL 16 | Decided |
| ORM and migrations | SQLAlchemy 2.0 (typed), Alembic | Decided |
| Database hosting | Managed Postgres in the EU | Default · ADR-003 |
| Background jobs | Postgres-backed queue, no Redis | Default · ADR-005 |
| Python packaging | uv, one lockfile | Decided |
| Frontend | React, TypeScript (strict), Vite, single-page app | Default · ADR-002 |
| Data fetching and routing | TanStack Query, React Router | Default · ADR-002 |
| Styling | Tailwind, configured with the Calm tide tokens | Default · ADR-002 |
| API contract | OpenAPI from the backend; TypeScript client generated from it | Decided |
| AI provider | Behind an adapter; provider with EU processing and no training on customer data | Default · ADR-004 |
| Sign-in | Email magic link through a managed auth provider | Default · ADR-006 |
| Hosting | EU region, containers | Default · ADR-007 |
| Error tracking | EU-hosted error tracking | Default · ADR-008 |
| Tests | pytest, Hypothesis, mutmut; Vitest, Testing Library; Playwright | Decided |
| CI | GitHub Actions | Decided |
| Local environment | Docker Compose: API, worker, Postgres, frontend | Decided |

**Deliberately not used in Phase 1:** microservices, Redis, vector search, n8n, a separate admin app, and any AI agent framework. Each can be added later through an ADR when a real need appears.

## 3. Repository structure

One repository, two applications (`api`, `web`), shared documentation. Backend code is organised by **domain module**, and inside each module by **layer**.

```text
home-base/
  CLAUDE.md                  # rules for Claude Code (section 16)
  README.md                  # purpose, setup, how to run checks
  docs/
    adr/                     # ADR-001-web-framework.md, ...
    rules/                   # rule catalogue: one YAML file per domain (section 6)
    runbooks/                # deploy, rollback, re-verify an opportunity
  api/
    pyproject.toml           # uv, ruff, mypy, pytest, mutmut config
    alembic/                 # migrations
    src/home_base/
      config.py              # settings and named constants
      logging.py             # structured logging setup
      core/                  # ids, clock, errors, shared types
      modules/
        companies/           # companies, company facts
        opportunities/       # opportunities, sources, requirements, verification
        matching/            # fit rules and match results
        applications/        # applications, questions, drafts
        today/               # priorities and progress
        audit/               # event history and AI action log
      ai/                    # provider adapter, prompts, schemas, evaluation
      jobs/                  # background tasks
      api/                   # FastAPI routers, request and response models
    tests/
      unit/  integration/  contract/  evals/
      fixtures/              # seed opportunities, sample companies
  web/
    package.json
    src/
      api/                   # generated client, never edited by hand
      components/            # shared UI: Card, Pill, StatusChip, RecordPage
      features/              # today/, opportunities/, applications/
      styles/                # Calm tide tokens
    tests/  e2e/
  infra/
    docker-compose.yml
  .github/workflows/         # ci.yml, deploy.yml
  .pre-commit-config.yaml
```

### Inside each backend module

| File | Holds | May import |
| --- | --- | --- |
| `domain.py` | Entities, value objects, pure business rules | `core` only |
| `rules.py` | Rule functions with their rule IDs (where the module has rules) | `domain`, `core` |
| `repository.py` | Database access for this module's tables | `domain`, SQLAlchemy |
| `service.py` | Use cases: orchestrates rules, repository, AI, audit | Everything above, other modules' services |
| `models.py` | SQLAlchemy tables | SQLAlchemy |
| `schemas.py` | API request and response models | Pydantic, `domain` |

Modules talk to each other only through `service.py`, never through another module's repository or tables.

## 4. Architecture rules

Each rule below is checked automatically where possible (import-linter, tests) and in every review otherwise.

1. **Business rules are pure functions.** Code in `domain.py` and `rules.py` takes values and returns values: no database, no network, no clock, no AI, no logging. The current date is passed in as an argument. This makes every rule unit-testable and deterministic.
2. **Layers only import downward.** `api` → `service` → `rules` / `domain` / `repository`. Enforced with import-linter contracts in CI.
3. **One canonical record per entity.** Each table belongs to one module. Other modules reference it by ID through that module's service; nobody copies its data into their own tables. Derived values (fit status, days left) are calculated, or stored as a snapshot with the inputs and rule version that produced them.
4. **AI sits behind one adapter.** All model calls go through `ai/`: one interface, one place for retries, timeouts, cost tracking and logging. No module calls a provider SDK directly.
5. **AI never decides.** Status, fit, priority, progress and dates come from rule functions. AI output is an input to a human or a display, never to a rule.
6. **Every AI output is validated.** Structured outputs are parsed into Pydantic models; anything that fails validation is rejected and logged, never saved partially.
7. **Every state change writes history.** Services record an audit event in the same database transaction as the change (section 12). If the event can't be written, the change doesn't happen.
8. **No business logic in the frontend.** The web app displays what the API returns. Labels like "Confirmed" or "12 days" come from the API, so web and API can never disagree.
9. **Every external effect is idempotent.** Jobs and API writes can safely run twice: they carry an idempotency key or check state first.
10. **Time is explicit.** Store UTC; display in Europe/Lisbon unless the user's profile says otherwise; never call `now()` inside a rule.
11. **Configuration, not constants in code.** Review intervals, thresholds and time estimates live in `config.py` as named, documented values that carry the rule ID that uses them (section 6).

## 5. Coding conventions

| Topic | Convention |
| --- | --- |
| Typing | Python: `mypy --strict`, no `Any` without a comment saying why. TypeScript: `strict: true`, no `any`. |
| Naming | Python `snake_case`, classes `PascalCase`; TypeScript `camelCase`, components `PascalCase`. Domain words match the spec exactly: opportunity, requirement, match, fit, application, question, draft, company fact. |
| IDs | UUIDv7 for every primary key (time-ordered, safe to expose). Never expose database sequence numbers. |
| Dates and times | Store `timestamptz` in UTC. Deadlines are stored as a date plus the funder's timezone, because "closes 21 Nov" means end of day there. Display in Europe/Lisbon by default. |
| Day counts | "Days left" uses calendar dates, not 24-hour periods: deadline date minus today's date in Lisbon, rounded down. One function owns this (rule PRI-07). |
| Money | Amounts in integer cents with an ISO currency code. Never floats. Displayed with the founder's locale. |
| Enums | Fit status, application status, requirement result and task type are Python `StrEnum`s mirrored in Postgres enums and the generated TypeScript client. Adding a value needs a migration. |
| Errors | Domain errors are typed exceptions (`EligibilityRuleError`, `SourceStaleError`); the API maps them to RFC 9457 problem responses. Never return a bare 500 with a message. |
| Nulls | "Unknown" is a real state in this product. Missing facts are `None` and handled explicitly; never default them to `0`, `False` or an empty string. |
| Constants | Named, documented values in `config.py`, each tagged with its rule ID: `REVIEW_INTERVAL_DAYS = 14  # FRS-02`. No magic numbers in rules. |
| Comments | Explain why, not what. A rule function's docstring quotes its rule ID and one-line statement from the rule catalogue. |
| Size | Functions under about 40 lines, files under about 400. Bigger means a missing concept. |
| Dependencies | Each new dependency needs a one-line reason in the PR. Pinned versions, one lockfile per app. |

## 6. Business rules as specification

Every rule in the Phase 1 spec gets a stable ID, a YAML entry in `docs/rules/`, a function that implements it, and at least one test named after it. CI fails if any of the four is missing for a rule.

### How a rule is written

```yaml
# docs/rules/matching.yaml
- id: FIT-02
  statement: An opportunity is Possible when no hard rule fails and at least one is Unknown.
  spec: Phase 1 spec > Fit and freshness rules > Fit status per opportunity
  implemented_in: home_base.modules.matching.rules.fit_status
  inputs: [requirement_results]
  output: FitStatus
  examples:
    - given: [pass, pass, unknown]
      expect: possible
    - given: [pass, fail, unknown]
      expect: not_eligible
```

The `examples` become parametrised tests automatically, so the catalogue and the tests can never drift apart. A rule change starts in the spec, then the YAML, then the tests, then the code: in that order, in one pull request.

### Phase 1 rule catalogue

| ID | Rule | Spec section |
| --- | --- | --- |
| REQ-01 | A hard rule passes when its approved fact meets it | Fit and freshness rules |
| REQ-02 | A hard rule fails when its approved fact does not meet it | Fit and freshness rules |
| REQ-03 | A hard rule is Unknown when its fact is missing or not approved | Fit and freshness rules |
| REQ-04 | A soft criterion is shown as an AI judgement with confidence, never as pass or fail | Fit and freshness rules |
| FIT-01 | Confirmed when every hard rule passes | Fit status per opportunity |
| FIT-02 | Possible when no hard rule fails and at least one is Unknown | Fit status per opportunity |
| FIT-03 | Not eligible when any hard rule fails; hidden by default | Fit status per opportunity |
| FIT-04 | Fewer than two hard rules, none failing → Possible, with the note "few explicit rules" | Fit status per opportunity |
| FIT-05 | Soft criteria never change the fit status | Fit status per opportunity |
| FRS-01 | Each opportunity carries a last verified date, set only by a manual check | Freshness |
| FRS-02 | Review interval is 14 days | Freshness |
| FRS-03 | Review interval is 7 days when the deadline is within 30 days | Freshness |
| FRS-04 | Past its interval → Re-check due: still listed with a flag, excluded from priorities and Today's deadlines | Freshness |
| FRS-05 | Deadline passed → Closed: hidden, kept in history | Freshness |
| FRS-06 | A change found in a re-check is logged and the opportunity's matches are recalculated | Freshness |
| PRI-01 | Priority 1: a missing fact blocks an answer due within 14 days | Your one thing today |
| PRI-02 | Priority 2: AI drafts await review in an application due within 14 days | Your one thing today |
| PRI-03 | Priority 3: a Possible match closes within 21 days and one fact would decide it | Your one thing today |
| PRI-04 | Priority 4: a Confirmed match closes within 30 days with no application | Your one thing today |
| PRI-05 | Priority 5: next unapproved answer in the earliest-deadline application | Your one thing today |
| PRI-06 | Nothing matches → the "You're all set" state | Your one thing today |
| PRI-07 | Days left = deadline date minus today in Lisbon, rounded down | Progress |
| PRI-08 | Ties go to the earliest deadline | Your one thing today |
| PRI-09 | Needs attention = next 3 tasks, excluding the one thing today | Needs attention |
| PRI-10 | Time estimates come from a fixed table per task type | Your one thing today |
| PRG-01 | Answers ready = approved / total questions | Progress |
| PRG-02 | Draftable = questions whose required facts are all approved | Progress |
| PRG-03 | Application status moves not started → in progress → ready → submitted (reopening an approved answer returns ready to in progress, decision D-09) | Progress |
| DRF-01 | A draft may only use approved company facts | Where the AI is involved |
| DRF-02 | Every draft stores links to the facts it used | Where the AI is involved |
| DRF-03 | Nothing is submitted from the platform; "submitted" is set by the founder | Progress |
| PRI-11 | Today is in Applying mode when an application is in progress with a future deadline, or a Confirmed match with no decision or Pursuing closes within 30 days; otherwise Preparing | Your one thing today |
| PRI-12 | Priority lists use only opportunities with no decision or Pursuing, plus Later once it has returned | Your one thing today |
| PRI-13 | Preparing 1: the missing fact with the most unlocks → "Add \[fact\]" | Preparing mode |
| PRI-14 | Preparing 2: an upcoming opportunity opens within 30 days and has no decision | Preparing mode |
| PRI-15 | Preparing 3: an opportunity on Later has returned | Preparing mode |
| PRI-16 | Preparing 4: intent untouched for 90 days → "Check your goals" | Preparing mode |
| PRI-17 | Preparing 5: nothing matches → "You're all set", with the next opening date | Preparing mode |
| INT-01 | Intent = goals from a fixed list, each with a window: now, soon or later | Intent |
| INT-02 | Each intent change adds a dated record; the latest is current | Intent |
| INT-03 | Intent orders and groups opportunities; it never changes a fit status | Intent |
| INT-04 | An intent or fact change recalculates every match; nothing is deleted, and an application no longer eligible is marked, then archived on confirmation | Intent |
| DEC-01 | Decision per opportunity: none, Pursuing, Later or Not for us; each change is dated and logged | Founder decisions |
| DEC-02 | Starting an application sets Pursuing | Founder decisions |
| DEC-03 | Later returns once, 30 days before the deadline or opening, as "Back on your list" | Founder decisions |
| DEC-04 | Not for us: left out of Today and the default list; visible under its filter | Founder decisions |
| UPC-01 | Status is Open, Upcoming or Closed | Upcoming opportunities |
| UPC-02 | Upcoming is shown only with an official opening date, or an expected month backed by evidence | Upcoming opportunities |
| UPC-03 | Until the call is published, fit and readiness use the last edition, labelled as such | Upcoming opportunities |
| UPC-04 | Review every 14 days, every 7 when the opening is within 30 days; expected month passed with no call → Re-check due | Upcoming opportunities |
| RDY-01 | Readiness = draftable or approved questions / total questions; hidden when the questions are unknown | Readiness and milestones |
| RDY-02 | Unlocks per missing fact = Possible matches where it is the only unknown hard rule + questions it makes draftable | Readiness and milestones |
| PRG-04 | Milestones come from a fixed list; each is shown once and logged | Readiness and milestones |
| REQ-05 | Applicant form (alone or consortium) is a hard rule; a consortium-only call fails for a company applying alone | Requirement types |
| FRS-07 | Sources disagree → the official one wins; no official source → Re-check due | Freshness |
| UPC-05 | Evidence older than 18 months does not count; the opportunity stays hidden until checked by hand | Upcoming opportunities |
| SCP-01 | Every opportunity has a scope (blue-specific or all sectors); the seed check rejects a record without one | Which opportunities are included |
| SCP-02 | When fit and deadline are equal, blue-specific sorts before all-sector | Which opportunities are included |

### Traceability check

A CI script (`scripts/check_rules.py`) reads the catalogue and the code and fails the build when:

- a rule ID in the catalogue has no implementing function or no test;
- a function in a `rules.py` has no rule ID in its docstring;
- a rule ID appears in code or tests but not in the catalogue.

It also writes `docs/rules/traceability.md`, a generated table of rule → function → tests, which is part of the portfolio case study.

## 7. Git workflow, commits and pull requests

### Branches

- `main` is always deployable and protected: no direct pushes, CI must pass, linear history (squash merge).
- One short-lived branch per change: `feat/`, `fix/`, `rule/`, `chore/`, `docs/`, `migration/`. Merged within two days or split.

### Commits

Conventional Commits, checked by a commit-msg hook. A commit that implements or changes a business rule names the rule ID in its scope.

```text
feat(matching): FIT-02 possible status when a hard rule is unknown
fix(today): PRI-07 days left counted in Lisbon calendar days
rule(freshness): FRS-03 shorter review interval near the deadline
migration(opportunities): add last_verified_at
```

### Pull requests

Every PR, including ones opened by Claude Code, uses the template in `.github/pull_request_template.md`:

- **What and why**, in two or three sentences.
- **Rule IDs touched**, or "none".
- **Spec section** it implements.
- **Evidence:** test names added or changed; for user-facing changes, a screenshot or recording from the running app.
- **Verified:** "in tests" and/or "on staging", stated separately, never implied.
- **Risk and rollback:** what could break, and how to undo it.

### Hard rules

- **One concern per PR.** Under about 400 changed lines, excluding generated files.
- **Migrations get their own PR**, merged and deployed before the feature that uses them. An irreversible migration (data rewrite, dropped column) always ships alone, with its rollback plan in the PR.
- **Re-run CI on `main` after every merge.** A merge can silently pick up an earlier commit than the branch head; the post-merge run catches it.
- **Generated files** (API client, traceability table) are regenerated by CI and committed only through their own command, never edited by hand.

## 8. Pre-commit hooks and local checks

Hooks run on staged files in seconds; CI runs the same checks on the whole repository, so skipping a hook locally never gets code past CI.

| Hook | Checks | When |
| --- | --- | --- |
| ruff format, ruff check | Python formatting and lint, including import sorting and common bugs | pre-commit |
| mypy --strict | Python types | pre-commit |
| prettier, eslint | TypeScript formatting and lint, including React hooks rules | pre-commit |
| tsc --noEmit | TypeScript types | pre-commit |
| gitleaks | Secrets, keys and tokens | pre-commit |
| check-yaml, check-json, end-of-file, trailing-whitespace, check-added-large-files (500 KB) | File hygiene | pre-commit |
| no-debug | No `print(`, `breakpoint(`, `console.log(` outside scripts | pre-commit |
| rule-ids | Rule functions carry a rule ID that exists in the catalogue | pre-commit |
| commitlint | Conventional Commit format | commit-msg |
| fast unit tests | Unit tests for the modules touched, under 30 seconds | pre-push |

### One command for everything

A `Makefile` gives the same entry points to Andrew, Claude Code and CI:

| Command | Runs |
| --- | --- |
| `make check` | All hooks on all files, plus the rule traceability check |
| `make test` | Unit and integration tests with coverage |
| `make mutate` | Mutation testing on rule modules (section 9) |
| `make evals` | AI evaluation sets (section 10) |
| `make e2e` | Playwright end-to-end tests against the local stack |
| `make db-check` | Alembic: migrations apply, downgrade where reversible, and match the models |
| `make client` | Regenerate the TypeScript API client from OpenAPI |
| `make all` | Everything CI runs, in CI's order |

Nothing is called done until `make all` passes locally or in CI.

## 9. Testing strategy

Rules are tested hardest, because they decide what founders see. Every level has a gate in CI; a failing gate blocks the merge.

| Level | What it covers | Tools | Gate |
| --- | --- | --- | --- |
| Rule tests | Every rule ID, from its catalogue examples plus edge cases | pytest, parametrised | 100% of rule IDs covered; 100% branch coverage of `rules.py` |
| Property tests | Invariants that must hold for any input | Hypothesis | All pass |
| Mutation tests | That rule tests would catch a changed rule | mutmut on `rules.py` and `domain.py` | At least 90% of mutants killed; matching and today modules 100% |
| Unit tests | Services and domain code with fakes for the database and AI | pytest | 85% line coverage overall |
| Integration tests | Repositories, migrations, transactions, audit events, against a real Postgres | pytest, Testcontainers | All pass; no database mocks |
| Contract tests | API responses match the OpenAPI schema; breaking changes flagged | Schemathesis, OpenAPI diff | No unflagged breaking change |
| Frontend tests | Components render each state: loading, empty, error, data | Vitest, Testing Library | 70% coverage on `features/` |
| End-to-end | The Phase 1 workflow, from profile to approved draft | Playwright, seeded stack | Golden path green on every PR |
| AI evaluations | Extraction, judgement and drafting quality | Own harness (section 10) | Thresholds in section 10 |
| Live checks | The deployed app, after each deploy | Smoke tests, read-only checks | All pass, or automatic rollback |

### Test families that must exist

- **Empty and partial data.** Every rule and screen is tested with nothing in it: no facts, no requirements, no opportunities, no applications. A rule must never return a reassuring result on empty input. FIT-04 exists for exactly this reason: zero hard rules can never mean Confirmed.
- **Boundaries.** Deadline today, tomorrow, at exactly 7, 14, 21 and 30 days; the night of a daylight-saving change; a deadline at end of day in another timezone; a call with no deadline ("Rolling"); an expected opening month that has just passed; intent at exactly 90 days; a Later opportunity at exactly 30 days.
- **Invariants (property tests).** Adding a failing rule never improves a fit status. Approving a fact never lowers "answers ready". Days left decreases by exactly one per calendar day. The one thing today is never a task from a stale or closed opportunity.
- **Audit completeness.** Every service method that changes state is tested to write exactly one matching audit event, in the same transaction.
- **Two readers, one truth.** Where two paths read the same data (list and detail, Today and Opportunities), a test asserts they produce the same status and days left for the same record.

### Test data

- `tests/fixtures/` holds the sample company (Mareva Seaweed) and the verified opportunity set (section 11), as versioned files.
- No production data in tests, ever. Fixtures are built from public calls and invented companies.
- Tests use a fixed clock passed as an argument; no test depends on the real date.
- A flaky test is fixed or quarantined, with an issue, the same day. Retrying until green is not allowed.

## 10. AI engineering

The AI does five jobs in Phase 1, and each has a schema, a validator and an evaluation set before it ships.

| Task | Input | Output | Validator | Human check |
| --- | --- | --- | --- | --- |
| Requirement extraction | Text of the official call | Requirements, each with type (hard or soft), field, operator, value and a quote | Every quote is an exact substring of the call text; fields and operators from a closed list | Checked by hand before the opportunity goes live (FRS-01) |
| Soft-criterion judgement | One soft criterion, relevant approved facts | Reading, confidence (high, medium, low), facts used | Facts used exist and are approved | Shown as "AI judgement"; never sets status (FIT-05) |
| Why it fits | Calculated requirement results and fit status | Two sentences | Mentions only requirements present in the input; no new eligibility claims | Marked as AI |
| Draft answer | One question, its limit, approved facts | Answer text with fact IDs per sentence | Every fact ID approved and owned by the company; every number in the text appears in a cited fact; length within the limit | Founder approves, edits or redrafts (DRF-01) |
| One thing today wording | Task type and its fields | One sentence | Names only entities present in the input | Task chosen by code (PRI rules) |

### Prompts

- Prompts live in `ai/prompts/<task>/v<n>.md` with front matter: task, version, model, temperature, output schema. Never inline strings in code.
- Any change to a prompt, model or schema creates a new version and runs that task's evaluation set before merge.
- Every AI action log entry records the prompt version, model and input hash (section 12).

### Calls

- Structured output only, parsed into Pydantic models. Invalid output: one retry with the validation error, then the task fails visibly and goes to manual handling. Nothing is saved partially.
- Temperature 0 for extraction and judgement; low for drafting and wording.
- Timeouts, a maximum output length, and a cost budget per call and per day, enforced in the adapter.
- Responses are cached by input hash, so re-running the same input costs nothing and gives the same result.
- Inputs are minimised: only the facts a task needs, never the whole company profile, never contact details.

### Evaluation sets and thresholds

Built from the verified opportunity set (section 11), labelled by hand, stored in `tests/evals/`.

| Task | Measure | Threshold to merge |
| --- | --- | --- |
| Extraction | Recall of hard rules (a missed rule can wrongly show Confirmed) | ≥ 95% |
| Extraction | Precision of hard rules | ≥ 90% |
| Extraction | Quotes found verbatim in the source | 100% |
| Judgement | Agreement with hand labels | ≥ 80%, and no "high confidence" disagreements |
| Why it fits | Claims beyond the input | 0 |
| Drafts | Unsupported numbers or facts | 0 |
| Drafts | Within the character limit | 100% |
| Drafts | Rubric score (relevance, clarity, completeness), by a separate grader model, spot-checked by hand | ≥ 4 / 5 average |

Evaluations run in CI when anything under `ai/` changes, and nightly. Results are stored with the prompt version, so every change shows its before and after. A drop of more than 2 points on any measure blocks the merge.

## 11. Data, migrations and seed data

### Schema rules

- Every table has `id` (UUIDv7), `created_at`, `updated_at`; tenant-owned tables also have `company_id`, indexed and never null.
- Foreign keys and `NOT NULL` wherever the domain allows; checks in the database (enums, positive amounts), not only in code.
- No hard deletes of business records in Phase 1: records are archived with `archived_at`, and the audit trail keeps the history. GDPR deletion is the one exception (section 13).
- Derived values that are stored (a match's fit status) also store the rule version and the input snapshot that produced them, so any past result can be explained.

### Migrations

- Alembic only; never edit the database by hand in any environment.
- Each migration is small, named for what it does, and tested in CI: upgrade from empty, upgrade from the previous release, and downgrade where reversible.
- **Expand, then contract.** Add the new column or table, deploy code that writes both, backfill, switch reads, then remove the old one in a later release. Never rename in place.
- Irreversible migrations (data rewrites, drops) ship alone, after a backup, with the rollback plan written in the PR.
- `make db-check` fails when the models and the migrations disagree.

### Seed data: the verified opportunity set

The Phase 1 opportunity set is code-reviewed data, not something typed into the app.

- Stored as one YAML file per opportunity in `api/seed/opportunities/`, with: name, funder, official source URL, retrieval date, verification date, deadline and timezone, extracted requirements (each with its source quote), and the name of who verified it.
- A loader validates every file against the schema and refuses any opportunity without a source URL, a verification date or at least one quoted requirement.
- Changing a seed file is a normal PR: the diff shows exactly what changed in a call, and when.
- The same files are the ground truth for the extraction evaluation set (section 10).

### Backups and environments

- Daily automated backups of production, kept 30 days; a restore is tested once before launch and then monthly.
- Staging uses seed data and invented companies only; production data never leaves production.

## 12. Logging, audit trail and observability

The app keeps four separate records, each with one job. They share a `request_id`, so any screen a founder sees can be traced back through every step that produced it.

| Record | Answers | Where | Kept |
| --- | --- | --- | --- |
| Application logs | What did the system do, and did it fail? | JSON logs to the log service | 30 days |
| Audit trail | Who changed what, when, from what to what? | `audit_events` table, append-only | As long as the record exists |
| AI action log | What did the AI receive, return and get validated against? | `ai_actions` table | As long as the record exists |
| Job runs | Which background task ran, how long, with what result? | `job_runs` table | 90 days |

### Application logs

- Structured JSON through structlog. Every line carries: `timestamp`, `level`, `event`, `request_id`, `company_id` where relevant, `module`, `duration_ms` for timed operations, and the git SHA.
- **Levels:** `error` = needs action; `warning` = unexpected but handled (a retry, a validation failure); `info` = a business event (opportunity verified, match recalculated); `debug` = off in production.
- **Never logged:** email addresses, names, company facts' values, draft text, call text, prompts or AI outputs, tokens, keys, cookies. Log IDs and counts instead. A test scans log output in CI for these patterns.

### Audit trail

- One row per state change: `actor` (founder, system or job), `action`, `entity` and `entity_id`, `before` and `after` (changed fields only), `rule_version` when a rule decided it, `request_id`, `occurred_at`.
- Written in the same transaction as the change (architecture rule 7).
- Append-only: the application's database role has no `UPDATE` or `DELETE` on the table.
- It is what the **History** section shows on every record page.

### AI action log

- One row per model call: `task`, `prompt_version`, `model`, `input_hash`, references to the input records, the validated output, validation result, retry count, tokens, cost, latency, status, and the record it served.
- This is what lets a founder, or an interviewer, ask "why did the app say this?" and get a complete answer.

### Monitoring and alerts

- Error tracking (EU region) for the API, worker and web app, with releases tied to git SHAs.
- A `/health` endpoint returns status, git SHA and current migration, so a deploy can be verified in one call.
- Dashboard measures: job failures, AI cost per day, latest evaluation scores, number of opportunities with a re-check due, API latency (p95).
- Alerts: any job failing twice in a row; AI spend at 80% of the daily budget; any opportunity with a deadline within 7 days and a re-check due.

## 13. Security and privacy

Founders trust Home Base with unpublished company data, so isolation and minimal access are designed in, not added later.

### Tenant isolation, two layers

1. **Application:** every repository query filters on the current `company_id`, taken from the session, never from the request body. A shared base repository makes the filter impossible to forget.
2. **Database:** Postgres row-level security on every tenant table, as a second guard if the first fails.
3. **Tested:** an integration test signs in as company A and tries to read, list and change company B's records through every endpoint. All must fail.

### Authentication and sessions

- Email magic link through the auth provider (ADR-006); no passwords stored by Home Base.
- HTTP-only, secure, same-site cookies; short sessions with refresh; sign-out everywhere available.
- Every API route requires a session by default; public routes are listed explicitly and reviewed.

### Secrets and dependencies

- Secrets only in the hosting platform's secret store and a local `.env` that is git-ignored. gitleaks runs in pre-commit and CI.
- Separate keys per environment; production keys are never on a laptop.
- Dependency and container scanning in CI (pip-audit, npm audit, image scan); high-severity findings block the merge.

### Web security basics

- Content-Security-Policy without `unsafe-inline`, verified against the deployed site, not only locally.
- Input validated by Pydantic at the API edge; output encoded by React; no raw HTML from AI or users is ever rendered.
- Rate limits on sign-in and on AI-backed endpoints.

### Personal data (GDPR)

- Data minimisation: Phase 1 stores a founder's name and email, and company facts. Nothing else personal.
- EU hosting and an AI provider with EU processing and no training on customer data (ADR-004, ADR-007).
- **Export:** a founder can download all their company's data as JSON.
- **Deletion:** a founder can delete their account; company data is erased within 30 days, including backups as they expire. The audit trail keeps only an anonymous record that a deletion happened.
- A short privacy notice and a list of sub-processors are published before the first design partner signs up.

## 14. CI/CD, environments and release

### Pipeline on every pull request

Stages run in this order; the first failure stops the run.

1. **Static checks:** all pre-commit hooks on all files, rule traceability check.
2. **Build:** API image, web bundle, regenerated API client (must match the committed one).
3. **Rule and unit tests,** with coverage gates.
4. **Integration and contract tests** against Postgres in a container.
5. **Migration checks:** upgrade from empty, upgrade from the last release, downgrade where reversible.
6. **Mutation tests** on the rule modules touched by the PR (full run nightly).
7. **AI evaluations** when `ai/` changed (full run nightly).
8. **End-to-end tests** on a seeded stack.
9. **Security scans:** secrets, dependencies, container image.
10. **Preview deploy** of the PR, with its link posted on the PR.

After merge, the same pipeline runs again on `main` (section 7), then deploys to staging.

### Environments

| Environment | Purpose | Data | Deploys |
| --- | --- | --- | --- |
| Local | Development | Seed data, invented companies | Docker Compose |
| Preview | Review one PR | Seed data | Automatically per PR |
| Staging | Final check before production | Seed data, invented companies | Automatically from `main` |
| Production | Design partners | Real founders' data | Manually, from a tagged release |

### Releases

- Production releases are tagged (`v0.3.0`), with a changelog generated from the Conventional Commits.
- Migrations deploy first, as their own step; the application deploys after.
- **After every deploy:** smoke tests, then read-only checks on the live app: `/health` shows the expected git SHA and migration; key pages load; Today and Opportunities agree on statuses and days left for the seed records. Results are posted to the release.
- **Rollback:** redeploy the previous tag. Because migrations are expand-then-contract, the previous version always runs on the current schema.
- Feature flags for anything a design partner should see before others; flags are removed within two releases.

## 15. Definition of done

A change is done only when every applicable line is true. The PR template repeats this list; unchecked lines need a written reason.

**Specification**

- [ ] The change implements a spec section, named in the PR.
- [ ] Every business rule touched has its ID in the catalogue, its function and its tests; the traceability check passes.
- [ ] No rule, threshold or label was invented; anything missing from the spec was raised and added to the spec first.

**Quality**

- [ ] `make all` passes: lint, types, tests, coverage, mutation and migration checks, and evaluations if `ai/` changed.
- [ ] Empty-data and boundary cases are tested for anything that shows a status, a count or a date.
- [ ] New state changes write audit events, tested.
- [ ] Logs contain no personal data, secrets or document text.

**Product**

- [ ] Every screen state is handled: loading, empty, error and data.
- [ ] Labels, colours and layout follow the interface principles and the Calm tide tokens.
- [ ] Keyboard navigation and contrast checked for new UI.

**Evidence**

- [ ] Verified in tests, stated in the PR.
- [ ] Verified on staging (or the preview) for anything user-facing, with a screenshot or recording.
- [ ] After the production release: verified live, through the post-deploy checks.
- [ ] Docs updated where behaviour changed: spec, rule catalogue, ADR, runbook or README.

## 16. Working with Claude Code

Claude Code builds most of the code, so its instructions are part of the engineering system. The repository's `CLAUDE.md` is short and points here for detail; this is its full text.

```markdown
# Home Base: rules for Claude Code

Home Base helps early-stage ocean startups find funding they qualify for and prepare
the application, with every fact sourced. Read before any change:
- docs/spec/phase-1.md (scope, data model, rules)
- docs/handbook.md sections 1, 4, 6, 15
- docs/rules/*.yaml (the rule catalogue)

## Never
- Never invent a business rule, threshold, label or status. If the spec doesn't say it,
  stop and ask. Propose the spec change; don't implement it.
- Never let AI output set a status, score, date or priority. Code decides, AI explains.
- Never call an AI provider outside home_base/ai/.
- Never log personal data, company fact values, draft text, prompts or AI outputs.
- Never edit generated files (web/src/api/, docs/rules/traceability.md) by hand.
- Never put a migration in the same PR as feature code.
- Never mark work done without the evidence below.

## Always
- Work in small PRs, one concern each, using the PR template.
- For a rule: update the YAML catalogue first, then tests, then code. Put the rule ID
  in the function docstring, the test name and the commit scope.
- Pass the date in; never call now() inside domain or rules code.
- Write the audit event in the same transaction as the change.
- Test the empty case and the boundaries for anything showing a status, count or date.
- Run `make all` before saying a change is complete.

## Reporting
- Say "verified in tests" and "verified on staging" separately. Never imply the second.
- List rule IDs touched and tests added.
- Say plainly what you could not verify, and why.
- When unsure which reading of the spec is right, ask with the two readings.
```

### How Andrew works with it

- **One task per session**, taken from the milestone plan, with the spec section and rule IDs named in the prompt.
- **Plan first:** Claude Code proposes the change (files, tests, rule IDs), Andrew approves, then it implements.
- **Review like a colleague's PR:** read the tests first, then the code. A rule change without a failing-then-passing test is sent back.
- **Verify independently:** Andrew checks user-facing changes himself on the preview or staging before merging.

## 17. Open decisions

Thirteen decisions remain; none blocks writing the ADRs, and all should be closed before the first feature PR. Order: the product decisions first (they shape the data), then the ADRs.

| ID | Decision | Recommendation | Status |
| --- | --- | --- | --- |
| D-11 | One-sentence purpose for README and reference doc | "Home Base helps early-stage ocean startups in Portugal find the funding they actually qualify for, and prepare the application, with every fact sourced." | Proposed |
| D-12 | The first 15 to 20 opportunities and their official sources | Portugal plus a handful of EU programmes; researched and verified by hand | Open |
| D-10 | Weekly time budget and decision date | Fill the two blanks in the reference doc, section 14 | Open |
| D-09 | Can an approved answer be reopened, and what happens to status? | Yes: reopening returns the application from ready to in progress; logged. A submitted application stays submitted | Confirmed 2026-11-09 |
| D-13 | Product name, domain and brand | Working name Home Base; separate from andrewryan.consulting | Open |
| ADR-001 | Web framework | FastAPI: typed, OpenAPI built in, matches the generated client | Proposed |
| ADR-002 | Frontend setup | React, TypeScript, Vite single-page app; no server rendering needed | Proposed |
| ADR-003 | Database hosting | Managed Postgres in an EU region, with automated backups | Open |
| ADR-004 | AI provider | One provider behind the adapter; choose by EU processing terms, no training on data, and evaluation results | Open |
| ADR-005 | Background jobs | Postgres-backed queue; no Redis in Phase 1 | Proposed |
| ADR-006 | Sign-in | Managed auth with email magic links | Open |
| ADR-007 | Hosting | EU-region container hosting with preview environments | Open |
| ADR-008 | Error tracking | EU-hosted error tracking | Proposed |

Each ADR is one page in `docs/adr/`: context, options considered, decision, consequences. Vendors are chosen during the ADRs, after checking each provider's current EU data terms and pricing, never from memory.
