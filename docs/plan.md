# Phase 1 build plan

Four weeks, kept firm (spec: Timebox). When something doesn't fit, scope shrinks, not the
deadline. Each week ends with something demonstrable and `make all` green.

Rules done: 62 of 65 (see docs/rules/traceability.md). Left: DRF-01 to DRF-03 (drafting, week 4).

**Paused 2026-11-16** after week 3, and published as a portfolio piece with a static demo
(D-79). Week 4 (AI, deploy, design partners) was not started.

## Week 1: rules and data, no UI

Goal: every deterministic rule implemented and tested; the seed data loads.

- [x] Repository, tooling, CI, rule catalogue, traceability check
- [x] Matching rules: REQ-01 to REQ-05, FIT-01 to FIT-05
- [x] Freshness rules: FRS-01 to FRS-05, FRS-07; days left (PRI-07)
- [x] Andrew: confirm D-14 to D-17 in docs/decisions.md
- [x] Upcoming and scope rules: UPC-01 to UPC-05, SCP-01, SCP-02 (D-41, D-42)
- [x] Progress and readiness: PRG-01 to PRG-04, RDY-01, RDY-02
- [x] Today: both priority lists and the mode (PRI-01 to PRI-17), as pure functions over plain data
- [x] Intent and decisions: INT-01 to INT-03, DEC-01 to DEC-04 (INT-03: D-43). INT-04 is a service rule, moved to week 2
- [x] Founder facts for age and women-led calls: REQ-06, REQ-07 (D-44)
- [x] Seed YAML format and loader with validation (SCP-01), with types (D-43)
- [ ] ~~The first 5 hand-checked opportunities (D-12)~~ Moved to week 2: scope shrinks, not the deadline (spec: Timebox). See "Seed opportunities" in week 2.
- [x] Add mutmut to CI (handbook gate: 90% killed, matching and today 100%)

Demo: run the rules over the seed data in a script and print Today for a sample company.
(`make demo` runs it on the fictional fixtures; run it on `api/seed/opportunities` once the first 5 are checked by hand.)

## Week 2: database and API

- [x] ADR-001 to ADR-008 accepted (defaults unless there's a reason) (all accepted 2026-11-10, EU-owned vendors: Clever Cloud, Mistral, Keycloak on Clever Cloud, Bugsink, Lettermint. The AI model is picked on the week 4 evaluation)
- [ ] Seed opportunities, checked by hand (D-12), carried from week 1:
  - EIC Accelerator Open 2027: approved by Andrew; waits for its `verified_on` date and the quote confirmations
  - BlueInvest Readiness Assistance: waits for the application window (asked lu-blueinvest@pwc.lu); needs the previous-beneficiary fact first (REQ-08, its own rule PR)
  - EEA Blue Growth Call 2: hidden until a dated source; the launch event on 2026-11-12 may give one
  - Candidates to research: StartUP Voucher, Mar 2030 aquaculture, Ocean Hackathon Peniche
- [x] Postgres schema and Alembic migrations (own PRs); audit_events, ai_actions, job_runs (tooling #30; audit #32, opportunities #33, companies #34, matching #35, applications #36; D-46 to D-51. Users, memberships and the audit_events role come with step 6)
- [x] Repositories with integration tests on a real Postgres (Testcontainers) (tenant base and audit #38, companies #39, opportunities #40, matching #41, applications #42)
- [x] Services: matching recalculation (FRS-06, INT-04), decisions, intent history (recalculation #44, INT-04 #45, FRS-06 #46, decisions and starting an application #47; D-52 to D-55)
- [x] FastAPI routes for Today, Opportunities, Opportunity, Application; RFC 9457 errors (skeleton #48, opportunities #49, Today #51, profile and decision writes #52, Application #53; D-56 to D-62; SCP-03, PRI-18, PRI-19)
- [ ] Email-code sign-in (Keycloak, ADR-006); tenant isolation (filter plus row-level security) with a test that tries to cross tenants

Demo: the API returns Today for a seeded company, and every change shows in the audit trail.

## Week 3: interface

- [x] Web app shell with Calm tide tokens; generated API client (D-65)
- [x] Today (both modes), Opportunities, Opportunity, Application, matching the wireframes (D-66 to D-70)
- [x] Empty, loading and error states for each screen
- [x] Playwright golden path: profile, match, decide, start application (D-74)

Demo: a founder can go from profile to an application workspace without AI.

## Week 4: AI, then ship to design partners

- [ ] AI adapter, requirement extraction with verbatim-quote check, eval set and thresholds
- [ ] Draft answers from approved facts only (DRF-01 to DRF-03), every number cited
- [ ] "Why it fits" and "one thing today" wording, marked as AI
- [ ] Deploy to the EU; smoke tests; known limitations written down
- [ ] Three design partners onboarded

Demo: the full workflow on a real opportunity, recorded for the case study.
