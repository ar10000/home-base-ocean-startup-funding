# ADR-004: AI provider

Status: Accepted, 2026-11-10 (narrows the shortlist accepted earlier the same day) · Owner: Andrew

## Context

AI extracts requirements, judges soft criteria and words explanations, behind the adapter in `home_base/ai/` (handbook section 2). Prompts contain company facts. Andrew's constraint: an EU-owned provider, processing in the EU, no training on customer data. Sources: `research/2026-11-10-eu-owned-shortlist.md`.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| Mistral, EU endpoint (`api.eu.mistral.ai`) | French company; inference in EU and EFTA data centres; function calling supported | 1.1× list price; no Agents, Batch or Files API on the EU endpoint; account and billing systems may sit outside the EU; customer data is used for training unless we opt out |
| Claude (Anthropic API, Bedrock or Vertex) | Strong extraction and writing | US companies: out under the constraint |

## Decision

Mistral on the EU endpoint, with training opt-out set on the organisation before the first call. The model (Large 4 or Small 4) is chosen on the week 4 evaluation set and thresholds. If no Mistral model meets the thresholds, this ADR comes back to Andrew; we don't quietly change provider.

The week 4 evaluation also runs Claude Sonnet or Opus 5.5 on Bedrock with EU routing, as a benchmark only (Andrew, 2026-11-10). It shows what the EU-owned choice costs in quality. Using a US provider in production would need Andrew's explicit decision and a new version of this ADR.

## Consequences

- The adapter only accepts the EU base URL; any other is a configuration error.
- Check before the first call: training opt-out in the admin settings, and the zero data retention terms.
- Prompts send only the facts a task needs, never the full company record.
- The benchmark runs use the evaluation set only (fictional companies and public call texts), never a founder's data.
