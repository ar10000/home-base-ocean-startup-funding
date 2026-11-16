"""Matching tables on a real Postgres: match results keep their inputs, one current match
per company and opportunity, decisions are a dated history, and nothing links across
companies."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from home_base.core.db import Record
from home_base.modules.companies.models import CompanyFactRow, CompanyRow
from home_base.modules.matching.models import DecisionRow, MatchRow, RequirementResultRow
from home_base.modules.opportunities.models import OpportunityRow, RequirementRow

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


@dataclass
class World:
    company: CompanyRow
    other_company: CompanyRow
    opportunity: OpportunityRow
    requirement: RequirementRow
    fact: CompanyFactRow
    other_fact: CompanyFactRow


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def world(session: Session) -> World:
    company, other = CompanyRow(name="A"), CompanyRow(name="B")
    opp = OpportunityRow(
        seed_key=f"test-{uuid.uuid4()}",
        name="Example Ocean Grant",
        funder="Example Foundation",
        scope="blue_specific",
        types=["grant"],
        questions_known=False,
    )
    session.add_all([company, other, opp])
    session.flush()
    req = RequirementRow(
        opportunity_id=opp.id,
        position=0,
        hard=True,
        quote="Applicants must be based in Portugal.",
        fact="country",
        operator="equals",
        value="PT",
    )
    fact, other_fact = (
        CompanyFactRow(
            company_id=c.id, key="country", value_type="text", value_text="PT", label="sourced"
        )
        for c in (company, other)
    )
    session.add_all([req, fact, other_fact])
    session.flush()
    return World(company, other, opp, req, fact, other_fact)


def _saves(session: Session, row: Record) -> bool:
    savepoint = session.begin_nested()
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        savepoint.rollback()
        return False
    savepoint.rollback()
    return True


def _match(w: World, **overrides: Any) -> MatchRow:
    values: dict[str, Any] = {
        "company_id": w.company.id,
        "opportunity_id": w.opportunity.id,
        "fit_status": "confirmed",
        "few_explicit_rules": False,
        "rule_version": "fit-v1",
        "calculated_at": NOW,
    } | overrides
    return MatchRow(**values)


def _saved_match(session: Session, w: World) -> MatchRow:
    m = _match(w)
    session.add(m)
    session.flush()
    return m


def _result(w: World, match: MatchRow, **overrides: Any) -> RequirementResultRow:
    values: dict[str, Any] = {
        "match_id": match.id,
        "company_id": w.company.id,
        "requirement_id": w.requirement.id,
        "result": "pass",
        "fact_key": "country",
        "fact_version_id": w.fact.id,
    } | overrides
    return RequirementResultRow(**values)


@pytest.mark.parametrize("model", [MatchRow, RequirementResultRow, DecisionRow])
def test_tables_are_empty_after_the_migration(session: Session, model: type[Record]) -> None:
    assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize(
    ("overrides", "saved"),
    [
        ({}, True),
        ({"fit_status": "not_eligible"}, True),
        ({"fit_status": "maybe"}, False),
        ({"rule_version": ""}, False),
        ({"rule_version": " "}, False),
    ],
)
def test_match_checks(
    session: Session, world: World, overrides: dict[str, Any], saved: bool
) -> None:
    assert _saves(session, _match(world, **overrides)) is saved


def test_one_current_match_and_recalculations_are_kept(session: Session, world: World) -> None:
    first = _saved_match(session, world)
    assert _saves(session, _match(world, fit_status="possible")) is False
    first.superseded_at = NOW
    session.flush()
    session.add(_match(world, fit_status="possible"))
    session.flush()
    count = session.scalar(select(func.count()).select_from(MatchRow))
    assert count == 2


def test_each_company_has_its_own_current_match(session: Session, world: World) -> None:
    session.add_all([_match(world), _match(world, company_id=world.other_company.id)])
    session.flush()


@pytest.mark.parametrize(
    ("overrides", "saved"),
    [
        ({}, True),
        ({"result": "unknown", "fact_version_id": None}, True),  # the fact is missing
        ({"result": "ai_judgement", "fact_key": None, "fact_version_id": None}, True),
        ({"result": "skipped"}, False),
        ({"fact_key": None}, False),  # a fact version names its key
        ({"fact_version_id": None, "fact_key": "founder_age"}, True),  # founder fact: key only
    ],
)
def test_requirement_result_checks(
    session: Session, world: World, overrides: dict[str, Any], saved: bool
) -> None:
    match = _saved_match(session, world)
    assert _saves(session, _result(world, match, **overrides)) is saved


def test_one_result_per_requirement_in_a_match(session: Session, world: World) -> None:
    match = _saved_match(session, world)
    session.add(_result(world, match))
    session.flush()
    assert _saves(session, _result(world, match, result="fail")) is False


def test_a_result_keeps_the_fact_version_it_read(session: Session, world: World) -> None:
    """Handbook section 11: a stored result can be explained after the fact changes."""
    match = _saved_match(session, world)
    session.add(_result(world, match))
    world.fact.superseded_at = NOW
    session.flush()
    stored = session.scalars(select(RequirementResultRow)).one()
    assert session.get(CompanyFactRow, stored.fact_version_id) is world.fact


def test_a_result_cannot_read_another_companys_fact(session: Session, world: World) -> None:
    match = _saved_match(session, world)
    assert _saves(session, _result(world, match, fact_version_id=world.other_fact.id)) is False


def test_a_result_cannot_belong_to_another_companys_match(session: Session, world: World) -> None:
    match = _saved_match(session, world)
    cross = _result(
        world, match, company_id=world.other_company.id, fact_version_id=world.other_fact.id
    )
    assert _saves(session, cross) is False


@pytest.mark.parametrize(
    ("decision", "reason", "saved"),
    [
        ("pursuing", None, True),
        ("later", None, True),
        ("none", None, True),  # reversible: back to no decision
        ("not_for_us", None, True),  # the reason is optional
        ("not_for_us", "too_early", True),
        ("not_for_us", "bored", False),
        ("later", "too_early", False),  # a reason only with Not for us
        ("maybe", None, False),
    ],
)
def test_decision_checks(
    session: Session, world: World, decision: str, reason: str | None, saved: bool
) -> None:
    row = DecisionRow(
        company_id=world.company.id,
        opportunity_id=world.opportunity.id,
        decision=decision,
        reason=reason,
        changed_at=NOW,
    )
    assert _saves(session, row) is saved


def test_every_decision_change_is_kept(session: Session, world: World) -> None:
    """The decision history: every change adds a row; the latest is current."""
    for decision in ("later", "pursuing", "not_for_us"):
        session.add(
            DecisionRow(
                company_id=world.company.id,
                opportunity_id=world.opportunity.id,
                decision=decision,
                changed_at=NOW,
            )
        )
    session.flush()
    count = session.scalar(select(func.count()).select_from(DecisionRow))
    assert count == 3
