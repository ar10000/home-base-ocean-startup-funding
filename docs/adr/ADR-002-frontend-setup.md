# ADR-002: Frontend setup

Status: Accepted, 2026-11-10 · Owner: Andrew

## Context

Phase 1 has four screens behind sign-in (Today, Opportunities, Opportunity, Application) for a handful of design partners. Nothing is public, so search indexing and first-paint for anonymous visitors do not matter. Styling uses the Calm tide tokens; the API client is generated (handbook section 2).

## Options considered

| Option | For | Against |
| --- | --- | --- |
| React, TypeScript (strict), Vite single-page app | Static build, served from any host; one runtime (the API) to operate; fast local builds | No server rendering (not needed behind sign-in) |
| Next.js | Server rendering, file routing | A second server runtime to host and secure; its data layer overlaps with the generated client |
| Server-rendered templates from the API | One app | Weak fit for the interactive Application workspace; no typed client |

## Decision

React with TypeScript strict and Vite, as a single-page app. TanStack Query for data fetching, React Router for routing, Tailwind configured with the Calm tide tokens.

## Consequences

- The web app is static files; hosting (ADR-007) only needs to serve them and proxy `/api`.
- All data goes through the generated client in `web/src/api/`, never hand-written fetch calls.
- If a public marketing page is needed later, it is a separate site, not a reason to add server rendering here.
