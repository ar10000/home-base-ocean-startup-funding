# Verified opportunity set

One YAML file per opportunity (handbook section 11). Every file is checked by
`tests/unit/test_seed.py` in CI: a file without a scope, an https source URL, a
verification date or at least one quoted requirement fails the build.

Only add opportunities checked by hand against the official source (decision D-12).

```yaml
name: Example Ocean Grant           # from the official source
funder: Example Foundation
scope: blue_specific                # or all_sectors (SCP-01)
types: [grant]                      # one or more of: grant, accelerator, testbed_or_pilot,
                                    # procurement_challenge, prize, investor_programme (D-43)
source_url: https://example.org/call
retrieved_on: 2026-11-01
verified_on: 2026-11-02             # last manual check (FRS-01)
verified_by: Andrew
deadline: 2027-01-31                # omit for a rolling call
timezone: Europe/Lisbon             # the funder's timezone; required with a deadline
opening: null                       # official opening date, for an upcoming call
expected_month: null                # YYYY-MM when only expected (UPC-02)
evidence: []                        # for an expected month: previous_edition or announcement
requirements:                       # at least one, each with the exact quote
  - {type: hard, fact: country, operator: equals, value: PT, quote: "Applicants must be based in Portugal."}
  - {type: soft, criterion: Clear environmental benefit, quote: "Projects should show a clear benefit to ocean health."}
questions:                          # omit when the question list is unknown
  - {text: Describe your team., required_facts: [team_size]}
```
