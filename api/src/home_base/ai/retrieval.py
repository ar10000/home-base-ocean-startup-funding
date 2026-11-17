"""Retrieval over a company's approved facts (ADR-009, D-81).

Each approved fact version is embedded once per embedding model, from a short text
("team size: 4", "impact: Absorbs 2 t of nitrogen a year."), and kept in
`fact_embeddings` under the company's row-level security. A question is embedded and
the closest approved facts are returned. Embedding calls send fact text to the provider
under the same rules as prompts, and are not written to the AI action log: they produce
no text anyone reads.
"""

import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from home_base.ai.provider import Provider
from home_base.config import FACT_VALUES
from home_base.modules.companies.domain import FactValue, FactVersion
from home_base.modules.companies.models import FactEmbeddingRow

TOP_K = 4  # D-81: the closest approved facts added to the question's required ones


_NAMES = {  # the spec's words where the key is not plain English
    "trl": "technology readiness level",
    "applicant_form": "consortium need",
    "description": "what the company does",
}


def fact_name(key: str) -> str:
    return _NAMES.get(key, key.replace("_", " "))


def value_text(key: str, value: FactValue) -> str:
    """A fact's value in words: a listed value's label, yes or no, or as written."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    labels = dict(FACT_VALUES.get(key, ()))
    return labels.get(str(value), str(value))


def fact_text(fact: FactVersion) -> str:
    return f"{fact_name(fact.key)}: {value_text(fact.key, fact.value)}"


def ensure_embeddings(
    session: Session, provider: Provider, company_id: uuid.UUID, facts: Sequence[FactVersion]
) -> None:
    """Embed the given fact versions that have no embedding for this provider's model."""
    model = provider.embedding_model
    have = set(
        session.scalars(
            select(FactEmbeddingRow.fact_version_id).where(
                FactEmbeddingRow.company_id == company_id,
                FactEmbeddingRow.model == model,
                FactEmbeddingRow.fact_version_id.in_([f.id for f in facts]),
            )
        )
    )
    missing = [f for f in facts if f.id not in have]
    if not missing:
        return
    vectors = provider.embed([fact_text(f) for f in missing])
    session.add_all(
        FactEmbeddingRow(company_id=company_id, fact_version_id=f.id, model=model, embedding=v)
        for f, v in zip(missing, vectors, strict=True)
    )
    session.flush()


def closest(
    session: Session,
    provider: Provider,
    company_id: uuid.UUID,
    query: str,
    among: Collection[uuid.UUID],
) -> list[uuid.UUID]:
    """The TOP_K fact versions among `among` closest to the query, closest first."""
    if not among:
        return []
    (vector,) = provider.embed([query])
    distance = FactEmbeddingRow.embedding.cosine_distance(vector)
    rows = session.scalars(
        select(FactEmbeddingRow.fact_version_id)
        .where(
            FactEmbeddingRow.company_id == company_id,
            FactEmbeddingRow.model == provider.embedding_model,
            FactEmbeddingRow.fact_version_id.in_(list(among)),
        )
        .order_by(distance, FactEmbeddingRow.fact_version_id)
        .limit(TOP_K)
    )
    return list(rows)
