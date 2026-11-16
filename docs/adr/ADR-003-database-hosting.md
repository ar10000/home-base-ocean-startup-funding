# ADR-003: Database hosting

Status: Accepted, 2026-11-10 (replaces Supabase, accepted earlier the same day) · Owner: Andrew

## Context

PostgreSQL 16 or later, with SQLAlchemy and Alembic, is decided (handbook section 2). Andrew's constraint: start in Portugal, then the EU, so the provider is an EU-owned company with data in the EU. Sources: `research/2026-11-10-eu-owned-shortlist.md`.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| Clever Cloud PostgreSQL, Paris | French company, data in France; same vendor as hosting (ADR-007); daily backups kept 7 days; point-in-time recovery available on request | Prices only through an estimator (unverified); backup settings changed through support |
| Aiven on UpCloud, Frankfurt | Finnish company on Finnish infrastructure; point-in-time recovery listed | From $75/month; only 2 days of backups on Startup; a second vendor |
| OVHcloud Managed PostgreSQL | French; 14-day backups and point-in-time recovery on Production | 2 nodes at $81.76/month each (from a summary); a second vendor |
| Supabase, Frankfurt | Cheapest, familiar | US company: out under the constraint |

## Decision

Clever Cloud PostgreSQL in Paris, used as plain Postgres: Alembic owns the schema, and the app connects with SQLAlchemy.

## Consequences

- One vendor and one region for the database and the apps.
- Ask support to enable point-in-time recovery (pgBackRest) and confirm retention before design partners' data goes in (week 4).
- Check the plan price in the estimator before creating it.
- Moving to Aiven or OVHcloud later is a dump and restore.
