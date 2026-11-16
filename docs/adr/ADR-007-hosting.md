# ADR-007: Hosting

Status: Accepted, 2026-11-10 (replaces Render, accepted earlier the same day) · Owner: Andrew

## Context

The API and the worker are containers from one image (ADR-005); the web app is static files (ADR-002). We need preview (one per pull request), staging and production environments; previews and staging hold seed data only (handbook section 14). The provider is an EU-owned company with data in the EU. Sources: `research/2026-11-10-eu-owned-shortlist.md`.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| Clever Cloud, Paris | French company, Paris data centres; a documented GitHub Action creates a review app per pull request, comments its link and deletes it on close | Review apps get no database by themselves; container prices unverified (estimator) |
| Upsun | French company; previews built in | Runs on AWS, GCP, Azure, IBM or OVHcloud. Previews clone the parent's database by default, and the option that stops this can't be used with the GitHub integration: production data could reach a preview |
| Render, Fly.io | Convenient | US companies: out under the constraint |

## Decision

Clever Cloud in Paris for the API, the worker and the web app, in every environment.

## Consequences

- Previews use the `CleverCloud/clever-cloud-review-app` action. Each preview gets its own development-plan PostgreSQL loaded with seed data only, created and deleted by the same workflow; never a copy of production.
- Pull requests from forks get no preview (secrets aren't passed to them).
- Check instance prices in the estimator before the first deploy.
