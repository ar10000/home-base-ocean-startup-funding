# ADR-008: Error tracking

Status: Accepted, 2026-11-10 · Vendor: Bugsink · Owner: Andrew

## Context

Design partners will hit errors we need to see without asking them. Home Base must never log personal data, company fact values, draft text, prompts or AI outputs (CLAUDE.md). The vendor is an EU-owned company with data in the EU. Sources: `research/2026-11-10-eu-owned-shortlist.md`.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| Bugsink, managed | Dutch company; data in the EU on Hetzner (German); works with Sentry's open-source SDKs, so we can switch by changing the DSN | Smaller vendor |
| AppSignal | Dutch company; data stored in the EU; Python and FastAPI agent | Infrastructure provider not named; its own agent, not a standard SDK |
| GlitchTip | Sentry-compatible | US company |
| Self-hosted | Full control | Another service to run |

## Decision

A hosted error tracker with EU data, for the API and the web app, through Sentry's open-source SDKs. Vendor: Bugsink (free up to 15,000 events a month; €16/month for 75,000).

## Consequences

- Scrubbing before send (`before_send`): request bodies, headers, cookies, local variables and breadcrumbs are dropped; only the error type, stack, route, release and an opaque tenant ID are sent.
- A test sends a sample error carrying a fake fact value and asserts the value is not in the outgoing payload.
- Because the SDK is standard, moving to another Sentry-compatible tracker is a configuration change.
