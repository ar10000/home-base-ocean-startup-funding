# Vendor shortlist for ADR-003, ADR-004, ADR-006 and ADR-007

Research input, not a decision. **Superseded for vendor choice by `2026-11-10-eu-owned-shortlist.md`** (EU-owned companies only). Read 2026-11-10 from the vendors' own pages unless marked
**(secondary)**. Prices and terms change: re-check the linked page before accepting an ADR.
**Unverified** means the page did not load or did not say it.

## ADR-003: Database hosting (managed Postgres, EU, automated backups)

| Option | EU location | Price (entry for production) | Backups | Notes |
| --- | --- | --- | --- | --- |
| Supabase Pro | Frankfurt (eu-central-1), Paris, Ireland, Stockholm | from $25/month, includes a Micro instance (1 GB RAM, shared) | daily, kept 7 days; point-in-time recovery +$100/month per 7 days | The same vendor can host sign-in (ADR-006). The company is US-based **(secondary)**. |
| Aiven Startup | Frankfurt, Amsterdam (cloud chosen per service) | from $75/month | 2 days on Startup, 14 on Business **(the page's columns were hard to read, so this mapping is inferred)** | The company is Finnish **(secondary)**. Cheaper plans keep a single backup only. |
| Scaleway Managed PostgreSQL | Paris, Amsterdam | **unverified** (the page returned 403); about €11 to €80/month **(secondary)** | backups €0.03/GB/month **(secondary)** | The company is EU-owned **(secondary)**. Check in a browser. |

Sources: [Supabase pricing](https://supabase.com/pricing), [Supabase regions](https://supabase.com/docs/guides/platform/regions), [Aiven pricing](https://aiven.io/pricing?product=pg), [Scaleway pricing](https://www.scaleway.com/en/pricing/managed-databases/) (did not load), [hoststack.dev (secondary)](https://hoststack.dev/blog/scaleway-postgresql-pricing-2026).

## ADR-004: AI provider (EU processing, no training on customer data)

| Option | EU processing | Training | Retention | Notes |
| --- | --- | --- | --- | --- |
| Anthropic API (direct) | **No.** Inference can only be "global" or "us"; workspaces are US-only | Not used for training (Commercial Terms) | Prompts and outputs not kept by default, except Covered Models (Fable 5, Mythos 5), which are kept 30 days | Ruled out by the EU requirement as things stand. |
| Claude on AWS Bedrock, EU geographic routing | Haiku, Sonnet and Opus 5.5: routing kept within the EU from Frankfurt, Ireland or Paris. Fable and Mythos: global routing only, so **not EU** | Model providers have no access to prompts and completions; I found no explicit no-training sentence | Default retention follows the model's policy; AWS may keep data for abuse prevention | The per-model EU list came from a summarised page: **verify it on the model pages**. |
| Mistral API | The company is French; an EU-only endpoint is **unverified** | Not used for training unless you opt in, but Labs and preview models are excluded from that protection | **unverified** | The terms page doesn't say whether the API's training setting starts as opt-in or opt-out. Check the admin settings. |
| Claude on Google Vertex AI | **unverified** (the page lists no EU region) | | | |

The handbook also requires that the final choice rests on evaluation results (the Week 4 eval set), not on terms alone.

Sources: [Anthropic data residency](https://platform.claude.com/docs/en/manage-claude/data-residency), [Anthropic retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention), [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms), [Bedrock regions](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html), [Bedrock inference profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html), [Bedrock retention](https://docs.aws.amazon.com/bedrock/latest/userguide/data-retention.html), [Mistral terms](https://legal.mistral.ai/terms/commercial-terms-of-service), [Vertex Claude](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/partner-models/use-claude).

## ADR-006: Sign-in (managed auth, email magic link)

| Option | EU data | Magic link | Price | Notes |
| --- | --- | --- | --- | --- |
| Supabase Auth | **unverified** whether auth data follows the project's region | Yes, single use, 1-hour expiry | in Supabase Pro (50,000 monthly active users free **(secondary)**) | Built-in email allows 2 per hour and isn't for production, so it needs our own email provider. |
| Auth0 | EU tenant locality ("EU", "EU-2"); the plan required is **unverified** | Passwordless on every plan ("magic link" wording **unverified**) | Free up to 25,000 users; Essentials from $35/month | |
| Ory Network Production | EU data storage on Production and above | One-time codes by email; magic links **not documented** | $770/year | Codes differ from the magic link in the spec: a spec question. |
| Clerk | No EU residency found | | | Drop unless that changes. |

Sources: [Supabase passwordless](https://supabase.com/docs/guides/auth/auth-email-passwordless), [Supabase email sending](https://supabase.com/docs/guides/auth/auth-smtp), [Auth0 pricing](https://auth0.com/pricing), [Auth0 tenants](https://auth0.com/docs/get-started/auth0-overview/create-tenants), [Ory pricing](https://www.ory.com/pricing), [Ory one-time code](https://www.ory.com/docs/kratos/passwordless/one-time-code), [Clerk docs](https://clerk.com/docs).

## ADR-007: Hosting (EU containers, preview environments)

| Option | EU region | Previews per pull request | Price | Notes |
| --- | --- | --- | --- | --- |
| Render | Frankfurt | Built in; needs the Pro workspace plan; billed by the second | Pro price **unverified** | Stacked pull requests supported from 2026-11-18. |
| Fly.io | Frankfurt (fra) | Through a GitHub Action (`superfly/fly-pr-review-apps`); the region must be set to `fra` | smallest machine $2.19/month × 1.154 for Frankfurt, about $2.53 | Volumes $0.15/GB/month; egress $0.02/GB. |
| Scaleway Serverless Containers | Paris **(secondary)** | **unverified** | **unverified** (the page returned 403) | EU-owned **(secondary)**. |
| Clever Cloud | "Several regions in Europe" | Not found in the docs | Interactive estimator only | |

Sources: [Render regions](https://render.com/docs/regions), [Render previews](https://render.com/docs/preview-environments), [Render pricing](https://render.com/pricing), [Fly.io pricing](https://fly.io/pricing), [Fly.io review apps](https://docs.fly.io/blueprints/review-apps-guide), [Clever Cloud pricing](https://clever.cloud/pricing/), [Scaleway serverless](https://www.scaleway.com/en/pricing/serverless/) (did not load).
