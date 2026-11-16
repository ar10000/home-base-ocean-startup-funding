# ADR-006: Sign-in

Status: Accepted, 2026-11-10 (replaces Supabase Auth) · Owner: Andrew

## Context

The spec says founders sign in with an email magic link; Home Base stores no passwords (handbook section 13). The provider is an EU-owned company with data in the EU. Sources: `research/2026-11-10-eu-owned-shortlist.md`.

None of the EU-owned managed providers checked documents magic links. All of them document **one-time codes sent by email**.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| A. Keycloak on Clever Cloud, email one-time codes | Same French vendor as ADR-003 and ADR-007; free up to 100 users | Codes instead of links: a spec change |
| B. Our own magic links (signed single-use token, emailed through Lettermint) | Matches the spec; all data with us | We own security-sensitive code (token expiry, single use, rate limits); the handbook says a managed provider |
| C. Hanko, email passcodes | German company | Hosted on AWS Frankfurt (US-owned infrastructure); codes, not links |

## Decision

A: Keycloak on Clever Cloud, with a one-time code sent by email (Andrew, 2026-11-10). A code typed from the email is as passwordless as a link, and we don't build authentication ourselves.

## Consequences

- Sign-in is "email one-time code" everywhere it said "email magic link": `docs/plan.md` here; the handbook (section 2 stack table, section 13, section 17) is updated in its source and re-exported.
- Keycloak sends its email through Lettermint (Dutch, EU-only infrastructure), from €10/month for 10,000 emails.
- The API verifies Keycloak's tokens and maps the user to a tenant; tenant isolation stays in our code and row-level security (plan, week 2).
- Check before building: Keycloak's per-user price and its billing period, and the code's length, expiry and attempt limits.
