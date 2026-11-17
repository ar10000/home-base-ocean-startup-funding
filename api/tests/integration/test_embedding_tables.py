"""The retrieval tables (ADR-009) and the knowledge-base facts (D-80)."""

from collections.abc import Iterator
from datetime import date

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from home_base.config import EMBEDDING_DIMENSIONS, KNOWLEDGE_FACT_KEYS
from home_base.modules.companies.models import (
    CompanyFactRow,
    CompanyRow,
    FactDefinitionRow,
    FactEmbeddingRow,
)
from home_base.modules.opportunities.models import OpportunityRow, SourcePassageRow, SourceRow

pytestmark = pytest.mark.integration


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


def _vector(hot: int) -> list[float]:
    v = [0.0] * EMBEDDING_DIMENSIONS
    v[hot] = 1.0
    return v


def _fact(session: Session, company: CompanyRow, key: str, value: str) -> CompanyFactRow:
    fact = CompanyFactRow(
        company_id=company.id, key=key, value_type="text", value_text=value, label="user_provided"
    )
    session.add(fact)
    session.flush()
    return fact


def _as_app(session: Session, company: CompanyRow) -> None:
    session.execute(text("SET LOCAL ROLE home_base_app"))
    session.execute(text("SELECT set_config('app.company_id', :c, true)"), {"c": str(company.id)})


def test_the_knowledge_base_facts_are_text_and_not_hard_rule_facts(session: Session) -> None:
    rows = session.scalars(
        select(FactDefinitionRow).where(FactDefinitionRow.key.in_(KNOWLEDGE_FACT_KEYS))
    ).all()
    assert sorted(r.key for r in rows) == sorted(KNOWLEDGE_FACT_KEYS)
    assert all(r.value_type == "text" and not r.hard_rule for r in rows)


def test_retrieval_orders_facts_by_closeness(session: Session) -> None:
    company = CompanyRow(name="A")
    session.add(company)
    session.flush()
    near = _fact(session, company, "impact", "Absorbs 2 t of nitrogen a year.")
    far = _fact(session, company, "team", "Two marine biologists.")
    session.add_all(
        [
            FactEmbeddingRow(
                company_id=company.id, fact_version_id=near.id, model="m", embedding=_vector(1)
            ),
            FactEmbeddingRow(
                company_id=company.id, fact_version_id=far.id, model="m", embedding=_vector(2)
            ),
        ]
    )
    session.flush()
    query = (
        select(FactEmbeddingRow.fact_version_id)
        .order_by(FactEmbeddingRow.embedding.cosine_distance(_vector(1)))
        .limit(1)
    )
    assert session.scalar(query) == near.id


def test_an_embedding_must_belong_to_its_fact_s_company(session: Session) -> None:
    own, other = CompanyRow(name="Own"), CompanyRow(name="Other")
    session.add_all([own, other])
    session.flush()
    fact = _fact(session, own, "team", "Two founders.")
    session.add(
        FactEmbeddingRow(
            company_id=other.id, fact_version_id=fact.id, model="m", embedding=_vector(0)
        )
    )
    with pytest.raises(DBAPIError, match="fk_fact_embeddings_fact_version"):
        session.flush()


def test_the_app_sees_only_its_own_company_s_embeddings(session: Session) -> None:
    own, other = CompanyRow(name="Own"), CompanyRow(name="Other")
    session.add_all([own, other])
    session.flush()
    for company in (own, other):
        fact = _fact(session, company, "team", "Two founders.")
        session.add(
            FactEmbeddingRow(
                company_id=company.id, fact_version_id=fact.id, model="m", embedding=_vector(0)
            )
        )
    session.flush()
    _as_app(session, own)
    seen = session.execute(text("SELECT company_id FROM fact_embeddings")).scalars().all()
    assert seen == [own.id]


def test_the_app_cannot_write_call_passages(session: Session) -> None:
    opportunity = OpportunityRow(
        seed_key="call",
        name="Call",
        funder="F",
        scope="blue_specific",
        types=["grant"],
        questions_known=False,
    )
    session.add(opportunity)
    session.flush()
    source = SourceRow(
        opportunity_id=opportunity.id,
        url="https://example.org/call",
        retrieved_on=date(2026, 11, 1),
        verified_on=date(2026, 11, 2),
        verified_by="Test",
    )
    session.add(source)
    session.flush()
    session.add(
        SourcePassageRow(
            source_id=source.id,
            position=0,
            start=0,
            text="Open to SMEs.",
            model="m",
            embedding=_vector(0),
        )
    )
    session.flush()
    company = CompanyRow(name="A")
    session.add(company)
    session.flush()
    _as_app(session, company)
    assert session.execute(text("SELECT count(*) FROM source_passages")).scalar_one() == 1
    with pytest.raises(DBAPIError, match="permission denied"):
        session.execute(text("DELETE FROM source_passages"))
