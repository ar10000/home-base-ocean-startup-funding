# EU-owned vendor shortlist

Research input, not a decision. Andrew's constraint (2026-11-10): start in Portugal, then the
EU, so vendors should be **EU-owned companies with data in the EU**, not only EU-hosted.
This replaces the US-owned picks in `2026-11-10-vendor-shortlist.md` (Supabase, Render,
Bedrock). Read on 2026-11-10 from the vendors' own pages; **unverified** means the page
didn't load or didn't say.

## Database (ADR-003)

| Option | Company | Data | Backups | Price |
| --- | --- | --- | --- | --- |
| Clever Cloud PostgreSQL | Nantes, France | Hosted in France, "not subject to the Cloud Act" (product FAQ) | Daily, kept 7 days; point-in-time recovery (pgBackRest) on request to support | **Unverified**: the page is a JavaScript estimator |
| Aiven on UpCloud | Helsinki, Finland (UpCloud is Finnish too) | Frankfurt, Helsinki, Amsterdam and other EU regions | Point-in-time recovery listed; 2 days on Startup (inferred from a flattened table) | Startup from $75/month |
| OVHcloud Managed PostgreSQL | France | Gravelines, Roubaix, Strasbourg, Paris and others | Production plan: 14 days, point-in-time recovery included | Production $81.76/month per node, 2 nodes (from a page summary) |
| Exoscale | Lausanne, Switzerland | EU and Swiss zones | Hobbyist 2 days, Startup 3 | **Unverified**; the service runs on Aiven |

## Hosting with previews (ADR-007)

| Option | Company | Previews per pull request | Notes |
| --- | --- | --- | --- |
| Clever Cloud | France; Paris data centres (five availability zones from October 2026) | Yes: the `CleverCloud/clever-cloud-review-app` GitHub Action creates an app per pull request, comments the link and deletes it on close | Review apps get no database by themselves; we attach one. Container prices **unverified** (estimator). |
| Upsun (Platform.sh SAS) | Paris, France | Yes, built in | Runs on AWS, GCP, Azure, IBM or OVHcloud; no page ties a region to OVHcloud. **Preview environments clone the parent's database by default**, and the push option that turns this off can't be used with the GitHub integration. That conflicts with "previews hold seed data only" (handbook section 14). From €19/month in fixed fees plus usage. |

## AI provider (ADR-004)

| Option | Company | EU processing | Training | Notes |
| --- | --- | --- | --- | --- |
| Mistral, EU endpoint `api.eu.mistral.ai` | Paris, France | Inference in EU and EFTA data centres; billed at 1.1× list price | **Used for training unless the customer opts out** (DPA §2.3): we must opt out | The EU endpoint has no Agents, Batch or Files API; function calling works. Account, keys and billing ("control plane") may be handled outside the EU. Zero data retention exists; terms not read. Prices per million tokens: Large 4 $0.70 in / $2.10 out; Small 4 $0.15 / $0.60. |

No other EU-owned frontier provider was checked. Claude (Anthropic, and Bedrock or Vertex) is US-owned, so it is out under this constraint.

## Sign-in (ADR-006)

None of the EU-owned options documents **magic links**; all of them document **email one-time codes**.

| Option | Company | Data | Email sign-in | Price |
| --- | --- | --- | --- | --- |
| Keycloak on Clever Cloud | France (with Please Open-It) | Clever Cloud | One-time codes by email; magic links not mentioned | Free up to 100 users, then €0.05 per user (billing period not stated) |
| Hanko | Kiel, Germany | AWS Frankfurt (US-owned infrastructure) | Email passcode; magic links not found | Free up to 10,000 users; Pro $29/month |
| ZITADEL | St. Gallen, Switzerland per its terms, but its site footer gives a San Francisco address | EU region available | Not confirmed | Free; Pro $100/month |
| Ory | **US** (Ory Corp, Arizona) | | | Dropped |

## Error tracking (ADR-008)

| Option | Company | Data | Fit | Price |
| --- | --- | --- | --- | --- |
| Bugsink (managed) | Utrecht, Netherlands | EU, on Hetzner (German) | Works with Sentry's open-source SDKs: point the DSN at it | Free 15k events; €16/month for 75k |
| AppSignal | Amsterdam, Netherlands | "All customer data is stored in the European Union"; provider not named | Its own Python agent, with FastAPI support | Free 30k requests; from €22/month |
| GlitchTip | **US** LLC (EU instance on DigitalOcean Frankfurt) | | | Dropped |

## Transactional email (for ADR-006)

| Option | Company | Data | Price |
| --- | --- | --- | --- |
| Lettermint | Netherlands, founder-owned | EU only, on its own infrastructure; backups in Germany; "no US cloud providers" | Free 300/month; €10/month for 10,000 |
| Scaleway Transactional Email, Brevo | France | **Unverified** (the pages refused automated reading or didn't render) | |

## Sources

[Clever Cloud PostgreSQL docs](https://www.clever.cloud/developers/doc/deploy/databases/postgresql/), [Clever Cloud PostgreSQL product page](https://www.clever.cloud/product/postgresql/), [Clever Cloud infrastructure](https://www.clever.cloud/infrastructure/), [Clever Cloud about](https://www.clever.cloud/about/), [Clever Cloud GitHub review apps](https://www.clever.cloud/developers/doc/tools/github/), [Clever Cloud Keycloak](https://www.clever.cloud/product/managed-keycloak-as-a-service/), [Clever Cloud pricing](https://www.clever.cloud/pricing/), [Aiven about](https://aiven.io/about), [Aiven clouds](https://aiven.io/docs/platform/reference/list_of_clouds), [Aiven pricing](https://aiven.io/pricing), [OVHcloud PostgreSQL](https://www.ovhcloud.com/en/public-cloud/postgresql/), [Exoscale PostgreSQL](https://www.exoscale.com/dbaas/postgresql/), [Upsun impressum](https://upsun.com/trust-center/legal/impressum/), [Upsun environments](https://developer.upsun.com/docs/environments/index.md), [Upsun PostgreSQL](https://developer.upsun.com/docs/add-services/postgresql/index.md), [Upsun pricing](https://upsun.com/pricing/), [Mistral regional inference](https://docs.mistral.ai/inference/regional-inference), [Mistral DPA](https://legal.mistral.ai/terms/data-processing-addendum), [Mistral pricing](https://docs.mistral.ai/inference/pricing), [Hanko pricing](https://hanko.io/pricing), [Hanko legal notice](https://hanko.io/legal-notice), [ZITADEL pricing](https://zitadel.com/pricing), [ZITADEL terms](https://zitadel.com/docs/legal/terms-of-service), [Ory privacy](https://www.ory.com/legal/privacy), [Bugsink](https://www.bugsink.com/), [Bugsink EU](https://www.bugsink.com/european-error-tracking/), [AppSignal](https://appsignal.com/), [GlitchTip hosting](https://glitchtip.com/documentation/hosted-architecture), [Lettermint EU](https://lettermint.co/european-email), [Lettermint pricing](https://lettermint.co/pricing).
