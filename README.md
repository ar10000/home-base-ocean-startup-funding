# Home Base

**Funding, matched and explained, for early-stage ocean startups.**

Home Base finds the grants, accelerators and pilot programmes an early-stage blue-economy
founder in Portugal or the EU qualifies for, says exactly why, and helps prepare the
application from facts the founder has approved. It shows one calm daily view of what to do
next, not a feed.

**[Try the demo →](https://ar10000.github.io/home-base-ocean-startup-funding/)**: a fictional founder and
fictional calls, recorded from the real app. No sign-up needed.

![Today: the founder's stage, goal, one thing to do today and what needs attention](docs/screenshots/today.png)

## Status

This is the Phase 1 MVP, paused before its AI and launch week. It is a portfolio piece,
not a live service.

| | |
|---|---|
| **Built and tested** | Rules, database and API; the web app's four screens and Profile; sign-in; tenant isolation; CI with an end-to-end test |
| **Designed, not built** | The AI layer: requirement extraction, "why it fits" wording and draft answers (ADR-004, handbook section 10) |
| **Not done** | Real, hand-checked opportunities (only fictional ones ship); hosting; design partners |

The full plan, with what was ticked and what wasn't, is in [`docs/plan.md`](docs/plan.md).

## What it does

| Screen | |
|---|---|
| **Today** | One thing to do today, chosen by rules: a missing fact, a draft to review, a deadline. Two modes: *applying* when a deadline is close, *preparing* otherwise. |
| **Opportunities** | Every call, checked against the company's approved facts: Confirmed, Possible or Not eligible, with the call's own words quoted for each requirement. |
| **Opportunity** | Why it fits or doesn't, freshness ("Source checked 12 days ago"), the founder's decision (Pursuing, Later, Not for us) and a dated history. |
| **Application** | The call's questions, autosaved answers, approval per answer, and "Mark as submitted". Nothing is ever submitted from the platform. |
| **Profile** | Company facts, all chosen from lists using the same words as the calls, each approved before matching uses it; goals with a time window; stage. |

<table>
  <tr>
    <td><img src="docs/screenshots/opportunities.png" alt="Opportunities list with fit filters"></td>
    <td><img src="docs/screenshots/opportunity.png" alt="An opportunity: each requirement checked against the founder's facts"></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/application.png" alt="Application workspace with an approved answer"></td>
    <td><img src="docs/screenshots/profile.png" alt="Profile: company facts chosen from lists and approved"></td>
  </tr>
</table>

## How it is built

The domain is one where a wrong answer costs a founder a deadline or a rejected
application. Every design choice serves one idea: **every status on screen can be traced
back to a written rule and a source.**

- **Code decides, AI explains.** Fit, freshness, priorities and progress are pure, tested
  functions. AI may only extract, judge soft criteria and word explanations. It never sets a
  status, date or score, and anything it writes is marked as AI.
- **No rule without a source.** Each of the 65 business rules (62 built; the three
  drafting rules wait for the AI layer) has an ID (`REQ-09`,
  `PRI-14`…) in [`docs/rules/*.yaml`](docs/rules/), quotes the spec section it comes from,
  and lists examples that run as tests. [`scripts/check_rules.py`](scripts/check_rules.py)
  fails the build when a rule has no code or no test, or when code cites a rule that doesn't
  exist. The generated map is [`docs/rules/traceability.md`](docs/rules/traceability.md).
- **Ambiguity is written down.** Where the spec could be read two ways, the chosen reading
  is recorded with its date and who confirmed it: 79 decisions in
  [`docs/decisions.md`](docs/decisions.md). Technology choices are ADRs in
  [`docs/adr/`](docs/adr/).
- **Two layers of tenant isolation.** Every query filters by company, and Postgres
  row-level security enforces it again: the API runs as a restricted role with the company
  set per transaction. Tests try to cross tenants and must fail.
- **An append-only audit trail.** Every change to facts, decisions and answers is audited
  in the same transaction, and the opportunity history on screen is built from it.

```mermaid
flowchart LR
  subgraph Browser
    W[React app<br/>TanStack Query<br/>typed client]
  end
  subgraph API[FastAPI]
    R[routes] --> S[services]
    S --> D[rules.py / domain.py<br/>pure, dated, tested]
    S --> P[(Postgres 16<br/>row-level security<br/>audit trail)]
  end
  K[Keycloak<br/>sign-in, PKCE]
  Y[seed YAML<br/>sourced calls] -->|reload job| P
  W -- "OpenAPI-typed calls" --> R
  W -. sign-in .-> K
  R -. verifies token .-> K
```

### Testing

| | |
|---|---|
| API | ~1,080 tests: catalogue examples, property tests (Hypothesis), and integration tests on a real Postgres 16 and Keycloak through Testcontainers. Branch coverage. |
| Mutation | `mutmut` over the rules and domain code: 90% of mutants killed, 100% for matching and Today. A CI job of its own. |
| Web | 127 Vitest + Testing Library tests against a fake API, typed from the OpenAPI schema. |
| End to end | Playwright plays the golden path against the full local stack in CI: sign up, set up a company, match, decide, apply. |
| Types | `mypy --strict` and TypeScript `strict` with `exactOptionalPropertyTypes`. The web client is generated from the API's OpenAPI schema, and CI fails if it drifts. |

## Stack

Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Postgres 16 · React 19, TypeScript, Vite,
Tailwind 4, TanStack Query, React Router · Keycloak (OIDC with PKCE) · uv, Ruff, mypy,
pytest, Hypothesis, mutmut, Testcontainers, Vitest, Playwright · GitHub Actions.

Vendors were picked EU-first (data in the EU, EU-owned where possible); see the ADRs.

## Run it locally

You need [uv](https://docs.astral.sh/uv/), Python 3.12+, Node 22.22+ and Docker.
Everything runs on your machine with fictional data only.

```sh
make setup       # install tools and git hooks
make dev-up      # Postgres and Keycloak in Docker, migrations, fictional opportunities
make demo-seed   # optional: the demo's six fictional calls instead
make dev-api     # API on 127.0.0.1:8000
make dev-web     # web app on http://localhost:5173: sign in, or register a new account
```

```sh
make all         # lint, strict types, rule traceability, unit + integration tests, web build
make mutation    # mutation tests on the rules
make e2e         # Playwright golden path against the local stack
make demo-build  # the static demo, over the recorded snapshot in web/src/demo/
```

The local Keycloak realm (`infra/keycloak/home-base-dev.json`) has a test user,
`founder@example.test`, with a local-only password in that file.

## Layout

```
docs/spec/phase-1.md   what Phase 1 does: scope, data model, rules in prose
docs/handbook.md       how it is built: architecture, testing, security, AI rules
docs/rules/            the rule catalogue (YAML) and its generated traceability map
docs/decisions.md      every reading of the spec, dated, with who confirmed it
docs/adr/              technology decisions: context, options, decision, consequences
api/src/home_base/     core/, modules/<domain>/{rules,domain,service,repository}.py, api/
api/alembic/           migrations (one concern each, in their own PRs)
api/tests/             unit, property and integration tests
web/src/               features/<screen>/, components/, lib/ (the one API client)
web/src/demo/          the public demo: a recorded snapshot and a stand-in for fetch
scripts/               rule traceability, mutation gate, seed loading, demo seed
```

## Licence

[MIT](LICENSE).
