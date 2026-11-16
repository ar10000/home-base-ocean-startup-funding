# Phase 1 spec: opportunity to application

Nov 9, 2026 · @Andrew

## Purpose and goal

This spec details Phase 1 of the Blue Founder Home Base. The [reference document](https://claude.ai/artifact/1afSUZRJUrdEzyBhz4PSb5) sets the vision and direction; this one says what to build first, how, and how to know it works. It changes as the build and user feedback teach things; the reference document should change much less often.

How it is built, checked and released is defined in the [Engineering handbook](https://claude.ai/artifact/SHpUze25wbH6t3mUfwCgkZ); the rules below carry the IDs listed in its rule catalogue.

**Goal:** one complete workflow, built properly and used by three design partners.

**A funding opportunity is found → its requirements are extracted → it is matched against a company profile → the founder gets an explanation of why it fits → an application workspace is generated → existing company information is reused to draft it.**

**Target maturity:** design-partner product. Deployed for a small number of real founders, with documented limitations, monitoring and feedback loops; not presented as production software.

**Timebox:** four weeks from the start of the build, kept firm. When something doesn't fit, the scope shrinks (fewer opportunities, more checked by hand), not the deadline.

## Scope

**In scope**

- Authentication and company profiles.
- Core data model: companies, company facts, opportunities, sources, requirements, applications, drafts, AI action logs.
- A basic company knowledge base, filled with the founder.
- An opportunity database for Portugal and a handful of EU programmes, each sourced, dated and verified.
- Requirement extraction, explainable matching and grounded application drafting.
- An application workspace: requirements, missing information, reusable facts, draft answers, review status.
- Founder intent: what the company is working towards and when, kept with its full history.
- Founder decisions per opportunity: Pursuing, Later or Not for us, all reversible.
- Upcoming opportunities: recurring calls and new batches shown before they open, with the evidence for the expected date.
- Readiness per opportunity, and the facts that would raise it most.
- A Today view with two modes: applying, when a deadline is close, and preparing, when nothing needs applying to yet.

**Out of scope for Phase 1**

- The full guided journey and dashboard (Phase 2).
- Worksheets, decks and document generation beyond application answers (Phase 3).
- Email, calendar and document integrations, background agents (Phase 4).
- MCP server and advanced agents (Phase 5).
- Programme dashboards (Phase 6).
- Automated monitoring of every source: early on, freshness is checked by hand.
- Watching a programme or funder, the weekly "what's new for you" email and the weekly recap (Phase 1.5).
- Public tenders and procurement calls: different rules, and mostly for more mature companies.
- Streaks, points, badges and leaderboards. Progress is shown against the founder's own goals, never scored.

## The workflow in eight steps

The workflow is a sequence of observable steps, not one opaque AI call. Each step has a stored output, so it can be tested, debugged, measured and shown.

| Step | What happens | Output and check |
| --- | --- | --- |
| 1. Ingest | The opportunity is added from its official source | Source URL, retrieval date, original text kept as evidence |
| 2. Extract | Structured fields and requirements are pulled from the text | Validated structured record; uncertain or conflicting fields sent for review |
| 3. Verify | Source status and freshness are checked | Last verification date; the opportunity is shown as current only once verified |
| 4. Check rules | Explicit eligibility rules are compared with structured company facts | Deterministic pass, fail or unknown per rule |
| 5. Interpret | AI interprets qualitative or ambiguous criteria | Assessment with stated uncertainty and the text it relied on |
| 6. Explain | The match is explained to the founder | Confirmed fit, possible fit and unknowns, each claim linked to its source; missing company information listed |
| 7. Create workspace | An application workspace is created | Requirements mapped to reusable company facts, gaps flagged |
| 8. Draft | Selected answers are drafted from approved facts | Drafts with source links, marked for founder review; nothing submitted |

## Data model

Only the entities Phase 1 needs, designed so later phases extend them rather than replace them.

| Entity | Holds |
| --- | --- |
| Company | Profile: sector, stage, country, team size, technology readiness |
| Company fact | One reusable fact (description, impact figure, team bio, traction) with its source, date and status |
| Opportunity | Programme or call: description, funding, deadline, geography, status (open, upcoming or closed), and for an upcoming one its opening date or expected month with the evidence; scope: blue-specific or open to all sectors |
| Source | Where an opportunity came from: URL, retrieval date, last verification date, original text |
| Requirement | One eligibility rule or evaluation criterion, structured where possible, linked to its source text |
| Match | Company × opportunity: per-requirement result (pass, fail, unknown), explanation, confidence |
| Application | Workspace for one opportunity: mapped requirements, gaps, status |
| Draft answer | Generated text for one question, the facts it used, review status |
| AI action | Log of each AI step: inputs, output, model and prompt version, time, outcome |
| Intent | What the company is working towards (goals from a fixed list) and the target window, with the date set. Each change adds a new record; the latest is current, earlier ones stay as history |
| Decision | Company × opportunity: Pursuing, Later or Not for us, optional reason, date. Each change adds a new record, so history is kept |
| Milestone | One reached progress moment from a fixed list, with its date, so it is shown once |

Every company fact carries one of four labels: **sourced**, **user-provided**, **AI-suggested** or **unverified**. Drafts may only use facts the founder has approved.

## Matching and explanations

Matching is layered so the founder can see why something fits.

1. **Deterministic checks first** for explicit rules: country, company age, sector, legal form, technology readiness level, deadline.
2. **Structured scoring** for transparent comparison between opportunities that pass the hard rules.
3. **AI interpretation only** for qualitative or ambiguous criteria, with the uncertainty stated.

The explanation always separates three things:

- **Confirmed fit:** rules the company clearly meets, with the source line.
- **AI judgements:** soft criteria read by the AI, with its confidence; they inform the founder but never set the fit status.
- **Unknowns:** what the platform couldn't verify, and which company information would settle it.

## Data freshness and verification

The opportunity data is the product's core asset and its biggest risk, so Phase 1 keeps it deliberately small and checked by hand.

- A small, curated set of opportunities: Portugal plus a handful of EU programmes.
- Each opportunity is verified by hand against its official source before it is shown as current.
- Every opportunity shows its last verification date; anything past its review date is flagged.
- Record the hours spent on verification each week. Coverage only grows when that time is sustainable.
- Automated monitoring comes later, source by source, once the manual process shows what changes and how often.

### Which opportunities are included

The niche is the founder, not the opportunity: the set holds blue-specific opportunities and a short, curated list of general ones. Research on 14 real opportunities (November 2026) showed a blue-only set would often be empty, while a broad set would make freshness unmanageable.

- A blue-specific opportunity is included when it is relevant to early-stage blue economy founders in Portugal.
- A general opportunity is included only if all three hold: a typical early-stage blue founder in Portugal is eligible; it offers real money or a meaningful programme; it runs on a known schedule, so keeping it fresh is cheap.
- Target for Phase 1: about 10 to 12 blue-specific and 5 to 8 general opportunities.
- Every opportunity carries a scope: blue-specific or open to all sectors. It shows as a quiet label, and blue-specific sorts first when fit and deadline are equal.
- The Opportunities list sorts goal-relevant opportunities first, then "Other matches"; within each, by fit (Confirmed, Possible, Not eligible), then earliest deadline (or opening, for an upcoming call; no date last), then blue-specific first, then name.
- Investors and funds without a call are not opportunities; they belong to the investor pipeline (Phase 4).

## Reliability, testing and evaluation

Quality is measured, not judged from a few good demos.

- **Tests:** unit tests for domain rules and deterministic eligibility checks; integration tests for the database, APIs and the AI provider adapter; end-to-end tests for the full workflow.
- **Evaluation sets:** a small, repeatable benchmark for extraction, matching and drafting, built from real opportunities and including awkward edge cases.
- **Validation:** structured-output validation, source-grounding checks, explicit handling of missing or conflicting information.
- **Versioning:** prompts, models and workflow versions recorded with each AI action, so changes can be traced and compared.
- **Failure handling:** retries, idempotent jobs, a visible failure state, and a human review path when a step can't safely continue.
- **Monitoring:** job failures, AI quality, latency and cost, with enough tracing to reconstruct any match or draft a founder asks about.
- **Regression checks** before changing prompts, models or matching logic that could change what founders see.

## Screens and interface

Designed screens are on the [wireframe canvas](https://claude.ai/artifact/J9fTqDJMp2ooe1iwbpxHVd), in the Calm tide visual direction. Phase 1 builds four of them.

| Screen | Shows only | Main action |
| --- | --- | --- |
| Today | Applying: one suggested next step, the next deadline with application progress, items needing attention, new matches. Preparing: one suggested next step, opportunities opening soon with readiness, the fact that unlocks the most | Open the suggested step |
| Opportunities | Each match with its fit, deadline or opening, readiness, the founder's decision and when its source was last checked; filter by fit and decision | Open an opportunity |
| Opportunity | Deadline and source check, AI summary of why it fits, eligibility checked against company facts, readiness, the founder's decision (Pursuing, Later, Not for us), history | Start application |
| Application | Question list with status, one draft at a time, what is missing, the facts it was built from | Approve or redraft |

Interface rules for Phase 1, from the reference document's interface principles:

- **One record template:** header with the key facts and one main action, sections below, a history with sources at the bottom.
- **Search** from the sidebar and Cmd+K across opportunities, questions and company facts.
- **Autosave and undo** in the application workspace; no save buttons.
- **AI content inline and marked** with the coral sparkle; approve, edit or redraft in place.
- **Fixed status colours:** sea green confirmed, warm sand deadlines, grey unknown, coral AI.

## Screen data

Every item shown on a Phase 1 screen, and where it comes from. **Stored** means saved in the database, **calculated** means derived by deterministic code at display time, **AI** means generated by a model and always marked as such.

### Today

| Item | What it is | Type |
| --- | --- | --- |
| Greeting and name | Founder's first name, morning/afternoon by local time | Stored + calculated |
| Stage | Current journey stage; set by the founder in Phase 1 | Stored |
| Your one thing today | The single highest-priority task (rules below) | Calculated; sentence worded by AI |
| Time estimate | "About 10 minutes", from a fixed table per task type | Calculated |
| Next deadline | Days until the earliest deadline among opportunities with an open application | Calculated |
| Answers ready | Approved answers / total questions for that application | Calculated |
| Needs attention | Up to 3 tasks, next in priority after the one thing today | Calculated |
| New matches | Up to 3 matches created since the last visit, not "not eligible" | Calculated |
| Mode | Applying or preparing (rules below) | Calculated |
| Current goal | Latest intent and its window, for example "Seed round, in 6 to 12 months" | Stored |
| Opening soon (preparing) | Up to 3 upcoming opportunities by opening date, each with its readiness | Stored + calculated |
| Fact that unlocks the most (preparing) | The missing fact with the most unlocks, and what it unlocks | Calculated |
| Milestone line | Shown once when a milestone is reached; fixed wording per milestone | Calculated |

### Opportunities

| Item | What it is | Type |
| --- | --- | --- |
| Name, type | From the official source, extracted and checked by hand | Stored |
| Fit | Confirmed, possible or not eligible (rules below) | Calculated |
| Deadline | Shown as days left when 30 days or fewer, otherwise as a date; "Rolling" when open-ended | Stored + calculated |
| Checked X ago | Time since the source was last verified | Stored |
| Re-check flag | Source past its review interval (rules below) | Calculated |
| New badge | Match created since the founder's last visit | Calculated |
| Filter counts | Number of matches per fit status | Calculated |
| Status | Open, or upcoming as "Opens \[date\]" or "Expected around \[month\]" | Stored + calculated |
| Readiness | "Ready for n of m questions" | Calculated |
| Your decision | Pursuing, Later or Not for us; none by default | Stored |
| Scope label | Blue-specific or open to all sectors | Stored |

### Opportunity

| Item | What it is | Type |
| --- | --- | --- |
| Title, deadline, source link | From the source record | Stored |
| Source checked date | Last manual verification | Stored |
| Why it fits | Two-sentence summary of the rule results and company facts | AI, from calculated results only |
| Eligibility list | One line per requirement: pass, fail, unknown or AI judgement | Calculated (hard rules) / AI (soft criteria) |
| History | Matching, verification and AI events for this record | Stored (event log) |
| Questions and draftable count | Total questions; questions whose required facts are all approved | Stored + calculated |
| Decision buttons | Pursuing, Later, Not for us; the current one highlighted; any can be changed | Stored |
| Opening and evidence | For an upcoming opportunity: opening date or expected month, and what it is based on | Stored |

### Application

| Item | What it is | Type |
| --- | --- | --- |
| Question list and status | Each question as missing facts, AI draft, edited or approved | Stored |
| Question text and limit | From the call | Stored |
| Draft answer | Generated from approved facts, then editable; autosaved | AI, then founder |
| Missing | Required facts with no approved value | Calculated |
| Built from N facts | Links from the draft to the facts it used | Stored |
| Ready count and days left | Approved / total; days until deadline | Calculated |

## Fit and freshness rules

### Requirement types

- **Hard rules** can be checked mechanically against a structured company fact: country, sector, legal form, company age, team size, technology readiness level, consortium need, and whether the call is still open; and against the optional founder facts below.
- **Soft criteria** need interpretation, such as "clear environmental benefit" or "strong team". The AI assesses them and states its confidence.
- Applicant form is a hard rule: applies alone, or needs a consortium. A consortium-only call is Not eligible for a company applying alone, with no AI judgement involved.

### Founder facts

Some calls limit who may apply by the founders' age or by women's leadership. Three optional **founder facts** let hard rules check this; they are personal data, so Home Base keeps them to the minimum a rule needs.

- **Youngest founder's birth date:** one date per company, never one per founder. A hard rule compares the youngest founder's age in whole years on the call's deadline with the call's limit, even when the call measures age on the day of applying, so a match never changes on a birthday. A call with no deadline measures it on the day the match is calculated. The birth date is used only by calls with an age limit.
- **At least one woman founder** (yes or no) and **woman CEO** (yes or no). Each call's hard rule uses the one its text names; any other wording, such as majority ownership, stays a quoted soft criterion.
- They are never required. Home Base asks for one only when a call the founder can see needs it, with a one-line reason, and the founder can delete it at any time; its rules then return to Unknown.
- They are never logged, never sent to the AI provider, and never count towards the "every hard-rule fact filled" milestone.

### Result per requirement

| Result | Meaning |
| --- | --- |
| Pass | The fact exists, is approved, and meets the rule |
| Fail | The fact exists, is approved, and does not meet the rule |
| Unknown | The fact the rule needs is missing or not yet approved |
| AI judgement | Soft criterion; the AI's reading with high, medium or low confidence |

### Fit status per opportunity

The status depends **only on hard rules**, so it is deterministic and testable. Soft criteria are shown as AI judgements but never change the status.

| Status | Rule |
| --- | --- |
| Confirmed | Every hard rule passes |
| Possible | No hard rule fails, and at least one is unknown |
| Not eligible | At least one hard rule fails; hidden from lists by default |

An opportunity with fewer than two extracted hard rules is shown as Possible with the note "few explicit rules", so a vague call never looks like a confident match. If one of those rules fails, it is Not eligible: a failing hard rule always wins.

### Freshness

- Every opportunity has a **last verified** date: the day its details were checked by hand against the official source.
- **Review interval:** 14 days by default, 7 days when the deadline is 0 to 30 days away, both included.
- **Re-check due:** more days than the interval have passed since the last verified date (day 15 for a 14-day interval), or the opportunity has never been checked by hand. The opportunity stays visible with a flag, but is excluded from "your one thing today" and from Today's deadlines until re-verified.
- **Closed:** the deadline has passed. The deadline day itself is still open; Closed starts the day after. Hidden from Opportunities and Today; kept in history.
- Any change found during a re-check is written to the opportunity's history, and its matches are recalculated.
- When two sources disagree on a date, amount or rule, the official source wins. With no official source, the opportunity is set to Re-check due until checked by hand. When two official sources disagree, the value is hidden and the opportunity is Re-check due.

## Intent, decisions and upcoming opportunities

A founder's plans change, so the app stores them as dated choices, never as fixed settings. None of them changes a fit status: fit stays a pure function of hard rules and approved facts.

### Intent

- Intent is one or more goals from a fixed list: pilot or test site, non-dilutive funding, accelerator or incubator place, first customers, investment. Each goal has a window: now (within 3 months), soon (3 to 6 months) or later (6 to 12 months).
- Every change adds a new intent record with its date. The latest is current; earlier ones stay in the history.
- Intent sets relevance, not fit. Opportunities whose type serves a current goal are listed first; the others stay visible under "Other matches".
- Each opportunity has one or more types: grant, accelerator or incubator, testbed or pilot programme, procurement or innovation challenge, prize or competition, investor programme with a call. Grants and prizes serve non-dilutive funding; accelerators and incubators serve an accelerator or incubator place; testbeds and pilots serve a pilot or test site; procurement and innovation challenges serve a pilot or test site and first customers; investor programmes serve investment. A goal is current when it is in the latest intent, whatever its window.
- Changing intent or a company fact recalculates every match. Nothing is deleted: an application whose opportunity becomes Not eligible is marked "No longer eligible" and archived when the founder confirms.
- Intent untouched for 90 days triggers a "Check your goals" task in preparing mode.

### Founder decisions

| Decision | Effect |
| --- | --- |
| None (default) | Treated as a candidate everywhere |
| Pursuing | Set by the founder, or automatically when an application is started |
| Later | Left out of Today until 30 days before its deadline or opening date, then returns once as "Back on your list", shown until the founder changes the decision. A call with no deadline or opening date never returns by itself |
| Not for us | Left out of Today and the default list; visible under the "Not for us" filter; optional reason: not relevant, too early, too much work, other |

Every decision can be changed at any time. Each change is written to the opportunity's history with its date.

### Upcoming opportunities

- An opportunity is Open (accepting applications), Upcoming (not open yet) or Closed. Status is calculated: with an official opening date it is Open from that day; with only an expected month it stays Upcoming until a check records the published call's opening date; it is Closed from the day after the deadline.
- An upcoming opportunity needs either an official opening date from the organiser, or an expected month backed by evidence: the previous edition's dates or an organiser announcement. Without evidence, it is not shown.
- Shown as "Opens \[date\]" when official, and "Expected around \[month\]" with "based on \[evidence\]" when estimated.
- Until the new call is published, fit and readiness use the previous edition's requirements and questions, labelled "based on last edition". A call counts as published once a check records its official opening date; until then the opportunity's own record holds the last edition's requirements and questions. When the call is published, requirements are extracted again and matches recalculated.
- Freshness applies as for open calls: review every 14 days, every 7 days when the opening is within 30 days. An expected month that passes with no call published sets "Re-check due". For an expected month, the opening counts as the 1st of that month, the 7-day interval also applies during the month itself, and the month has passed from the 1st of the next month.
- Evidence older than 18 months does not count. Its age is from its own date (the previous edition's opening date, or the announcement's publication date); exactly 18 months still counts. An opportunity whose only evidence is older stays hidden until a check by hand adds newer evidence.

## Priorities and progress

### Your one thing today

Today runs in one of two modes, chosen by code. **Applying** when an application is in progress with a future deadline, or a Confirmed match with no decision or Pursuing closes within 30 days. **Preparing** otherwise. Only opportunities with a current source that are not Not eligible decide the mode. The mode decides which priority list is used.

A fixed priority list; the first rule that matches wins, and ties go to the earliest deadline, then blue-specific first, then opportunity name. "Within N days" includes day N and today, and a future deadline includes today. Only opportunities with a current source count, with no decision or Pursuing (Later counts once it has returned), and never a Not eligible one. In applying mode:

1. A **missing fact** blocks an answer in an application due within 14 days → "Add \[fact\]": the fact that blocks the most answers in that application, ties to the earliest question.
2. **AI drafts await review** in an application due within 14 days → "Review \[n\] draft answers".
3. A **possible-fit** opportunity closes within 21 days and one missing fact would decide it → "Answer 1 question for \[opportunity\]".
4. A **confirmed** match closes within 30 days and has no application yet → "Start your \[opportunity\] application".
5. Otherwise, the **next unapproved answer** in the application with the earliest deadline.
6. Nothing left → the "You're all set" empty state.

The code picks the task; the AI only words the sentence, from the task's type and fields. The time estimate comes from a fixed table per task type (add a fact 10 minutes, review a draft 5 minutes, start an application 20 minutes, decide on an opportunity 5 minutes, check your goals 5 minutes, answer 1 question 10 minutes, next unapproved answer 10 minutes, back on your list 5 minutes).

### Needs attention

The next up to 3 tasks from the same priority list, excluding the one already shown as the one thing today.

### Preparing mode

The same rules of the game: a fixed list, first match wins, the code picks and the AI only words it. Ties go to the earliest opening or deadline.

1. A missing fact would settle the most Possible matches, or unlock the most questions across upcoming and Pursuing opportunities → "Add \[fact\]".
2. An upcoming opportunity opens within 30 days and has no decision → "Decide on \[opportunity\]: opens \[date\]".
3. An opportunity on Later has returned → "\[Opportunity\] is back on your list".
4. Intent untouched for more than 90 days, or never set → "Check your goals are still right".
5. Nothing left → the "You're all set" empty state, with the next opening date.

Preparing mode shows, under the one thing today: up to 3 opportunities opening soon, by opening date, each with its readiness; and the one fact that unlocks the most, with what it unlocks.

### Progress

- **Answers ready** = approved answers / total questions in the call; not shown when the call has no questions.
- **Draftable** = questions whose required facts are all approved; a question with no required facts listed is not draftable.
- **Application status:** not started → in progress (at least one answer has an AI draft, an edit or an approval) → ready (all answers approved) → submitted (marked by the founder; nothing is submitted from the platform). Reopening an approved answer returns a ready application to in progress; a submitted one stays submitted.
- **Days left** = deadline date minus today in Lisbon time, rounded down; shown as days when 30 or fewer, otherwise as a date.
- **Stage:** chosen by the founder in Phase 1; calculated from journey milestones from Phase 2.

### Readiness and milestones

Progress shows everywhere, always as the founder's own numbers, calculated by code from approved facts.

- Readiness per opportunity = draftable or approved questions / total questions, shown as "Ready for 6 of 8 questions". For an upcoming opportunity it uses the last edition's questions, labelled as such. Not shown when the question list is unknown or empty.
- Unlocks per missing fact = the number of Possible matches where it is the only unknown hard rule, plus the number of questions it would make draftable across upcoming and Pursuing opportunities. Shown as "Adding \[fact\] settles 2 matches and unlocks 4 answers".
- Milestones, from a fixed list: first fact approved, every hard-rule fact filled (every fact field hard rules can check has an approved value), first answer approved, first application ready, first application marked submitted. Each is shown once, as a short warm line on Today, and kept in the history.
- No streaks, points, badges or comparisons with other founders.

### Where the AI is involved

| Step | AI role | Human check |
| --- | --- | --- |
| Requirement extraction | Reads the call and proposes structured requirements | Checked by hand before the opportunity goes live |
| Soft criteria | Gives a reading with confidence | Shown as AI judgement; never sets the status |
| Why it fits | Words a summary from calculated results | Marked as AI |
| Draft answers | Writes from approved facts only | Founder approves, edits or redrafts |
| One thing today | Words the sentence | Task chosen by code |

## Definition of done

- [ ] Three design partners have profiles and have used the workflow on real opportunities.
- [ ] Every opportunity shown is sourced, dated and hand-verified.
- [ ] Each match shows confirmed fit, possible fit and unknowns, with sources.
- [ ] Changing intent or a decision updates matches and Today, and the full history stays readable.
- [ ] At least one design partner who is not applying yet uses Today in preparing mode.
- [ ] At least one design partner has started a real application from a generated workspace.
- [ ] The evaluation set runs automatically and its results are recorded.
- [ ] Known limitations are written down and visible to design partners.
- [ ] A short demo video and written case study, labelling each capability as implemented, experimental, manual or planned.

## Open questions

- [ ] Which design partners, and which subsectors do they cover?
- [ ] Which Portuguese and EU programmes make the first set?
- [ ] Which recurring programmes and accelerator batches have previous-edition dates reliable enough to show as upcoming?
- [ ] When does Phase 1.5 (watching, weekly email, weekly recap) start: straight after Phase 1, or after design-partner feedback?
- [ ] Flask or FastAPI?
- [ ] Which AI provider first, and what monthly cost ceiling?
- [ ] Where is it hosted in the EU?
