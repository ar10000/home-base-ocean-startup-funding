# ADR-009: AI layer and retrieval

Status: Accepted, 2026-11-17 (extends ADR-004) · Owner: Andrew

## Context

Week 4 adds the AI jobs in handbook section 10: requirement extraction, "why it fits", draft answers and the one-thing wording. Two needs shape how they are built:

- **Drafts must use only what is relevant.** Handbook section 10: "only the facts a task needs, never the whole company profile". With the knowledge base (spec: Scope, "a basic company knowledge base"; data model, company facts such as description, impact figure, team bio, traction), a company holds free-text facts as well as the seven structured ones, so the facts for a question have to be found, not listed by hand.
- **Calls are long.** An official call runs to many pages; extraction should read the passages about eligibility, not the whole document at once, and every quote must still be checked against the full text.

Both are retrieval-augmented generation (RAG): embed the text, retrieve the closest passages, generate from those only.

Andrew, 2026-11-17: Phase 1 is paused as a portfolio piece; it needs "AI and RAG", built as free as possible. The demo and the evaluations use Mistral's free "Experiment" tier, which may use inputs for training, acceptable only because those inputs are fictional.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| A. pgvector in the existing Postgres, Mistral embeddings | One database: retrieval obeys the same row-level security as the facts; no new service; free extension | Embedding dimension fixed per column (1024 for `mistral-embed`) |
| B. A separate vector database (Qdrant, Weaviate) | Purpose-built | A second store to secure and keep in sync; tenant isolation done twice |
| C. No embeddings: send all approved facts | Simplest | Breaks "only the facts a task needs"; does not scale to a knowledge base or a long call |
| Local model through Ollama | Nothing leaves the machine; free | The dev Mac has 8 GB RAM and a full disk; small models fall short on extraction |

## Decision

A, with three providers behind one interface in `home_base/ai/`:

- **Fake** for tests and CI: deterministic outputs per task and a hashing embedder (same 1024 dimensions), so no test ever calls a network.
- **Mistral** for the demo recording and evaluations, on the free tier with fictional data only, through the EU endpoint where the free tier allows it. Production use (real founders' data) stays as ADR-004 says: a paid organisation with the training opt-out, before the first real call.
- The provider is chosen by configuration; the key is read from the environment, never from a file in the repository and never logged.

Retrieval:

- **Facts:** each approved text fact version is embedded once (`fact_embeddings`, row-level security like `company_facts`). A draft retrieves the approved facts closest to the question (top k), always adds the facts the question requires, and sends only those.
- **Calls:** a call's source text is split into overlapping passages, and extraction retrieves those closest to a fixed set of eligibility questions and extracts from them only; every quote is then checked as an exact substring of the full call text (handbook section 10). The extraction command (D-83) retrieves in memory, since the call is not in the database yet; `source_passages` (shared, read-only for the API) is where passages go once call texts are kept with the seed set, which Phase 1 does not do yet.

## Consequences

- Postgres runs the `pgvector/pgvector:pg16` image locally, in CI and in Testcontainers (same Postgres 16, plus the extension). Clever Cloud's managed Postgres lists pgvector; check the version before deploying.
- Every model call goes through one runner: input hash, cache, schema parsing, one retry with the validation error, validators, the `ai_actions` log, a daily cost budget. Nothing is saved partially.
- Embedding text sends company facts to the provider, so the same rules apply as for prompts: minimal input, fictional data only on the free tier.
- Changing the embedding model means a new column dimension (a migration) and re-embedding.
