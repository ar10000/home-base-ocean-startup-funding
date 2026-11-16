# Home Base: rules for Claude Code

Home Base helps early-stage ocean startups find funding they qualify for and prepare
the application, with every fact sourced. Read before any change:
- docs/spec/phase-1.md (scope, data model, rules)
- docs/handbook.md sections 1, 4, 6, 15
- docs/rules/*.yaml (the rule catalogue) and docs/decisions.md
- docs/plan.md (what is being built this week)

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
  in the function docstring as "Rule XXX-NN: ...", in the test name and in the commit scope.
- Pass the date in; never call now() inside domain or rules code.
- Keep business numbers in api/src/home_base/config.py, each tagged with its rule ID.
- Write the audit event in the same transaction as the change.
- Test the empty case and the boundaries for anything showing a status, count or date.
- Run `make all` before saying a change is complete.

## Reporting
- Say "verified in tests" and "verified on staging" separately. Never imply the second.
- List rule IDs touched and tests added.
- Say plainly what you could not verify, and why.
- When unsure which reading of the spec is right, ask with the two readings, and record
  the answer in docs/decisions.md.

## Commands
- `make setup` once; `make all` before every PR; `make rules` after editing docs/rules/.
