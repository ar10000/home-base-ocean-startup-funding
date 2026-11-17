"""Company tables on a real Postgres (decisions D-47 to D-51): empty after the migration
apart from the fact catalogue, every check at its boundary, versions, and tenant links."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from home_base.config import HARD_RULE_FACT_KEYS, KNOWLEDGE_FACT_KEYS, PERSONAL_FACT_KEYS
from home_base.core.db import Record
from home_base.modules.companies.models import (
    FOUNDER_FACT_TYPES,
    CompanyFactRow,
    CompanyRow,
    FactDefinitionRow,
    FounderFactRow,
    IntentGoalRow,
    IntentRow,
)
from home_base.modules.today.models import MilestoneRow

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
TENANT_TABLES = [CompanyRow, CompanyFactRow, FounderFactRow, IntentRow, IntentGoalRow, MilestoneRow]


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def company(session: Session) -> CompanyRow:
    row = CompanyRow(name="Example Ocean Co")
    session.add(row)
    session.flush()
    return row


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


def _fact(company: CompanyRow, **overrides: Any) -> CompanyFactRow:
    values: dict[str, Any] = {
        "company_id": company.id,
        "key": "country",
        "value_type": "text",
        "value_text": "PT",
        "label": "user_provided",
    } | overrides
    return CompanyFactRow(**values)


@pytest.mark.parametrize("model", TENANT_TABLES)
def test_tenant_tables_are_empty_after_the_migration(session: Session, model: type[Record]) -> None:
    assert session.scalar(select(func.count()).select_from(model)) == 0


def test_catalogue_holds_exactly_the_hard_rule_and_knowledge_facts(session: Session) -> None:
    rows = session.scalars(select(FactDefinitionRow)).all()
    assert {r.key for r in rows if r.hard_rule} == HARD_RULE_FACT_KEYS
    assert {r.key for r in rows if not r.hard_rule} == set(KNOWLEDGE_FACT_KEYS)  # D-80
    assert {r.key: r.value_type for r in rows if r.value_type == "integer"} == {
        "company_age": "integer",
        "team_size": "integer",
        "trl": "integer",
    }


def test_stored_founder_facts_are_the_personal_ones_minus_the_derived_age() -> None:
    assert set(FOUNDER_FACT_TYPES) == PERSONAL_FACT_KEYS - {"founder_age"}


@pytest.mark.parametrize(
    ("overrides", "saved"),
    [
        ({}, True),
        ({"key": "favourite_colour"}, False),  # not in the catalogue
        ({"value_type": "integer"}, False),  # country is text
        ({"key": "trl", "value_type": "integer", "value_text": None, "value_integer": 4}, True),
        ({"key": "trl", "value_type": "integer", "value_integer": 4}, False),  # two values
        ({"value_text": None}, False),  # no value
        ({"value_text": "  "}, False),
        ({"label": "ai_suggested"}, True),
        ({"label": "approved"}, False),
        ({"approved_at": NOW, "approved_by": uuid.uuid4()}, True),
        ({"approved_at": NOW}, False),
        ({"approved_by": uuid.uuid4()}, False),
    ],
)
def test_company_fact_checks(
    session: Session, company: CompanyRow, overrides: dict[str, Any], saved: bool
) -> None:
    assert _saves(session, _fact(company, **overrides)) is saved


def test_one_current_version_per_key_and_superseded_versions_stay(
    session: Session, company: CompanyRow
) -> None:
    """D-50: an edit adds a version and supersedes the old one; history is kept."""
    first = _fact(company, value_text="PT", approved_at=NOW, approved_by=uuid.uuid4())
    session.add(first)
    session.flush()
    assert _saves(session, _fact(company, value_text="ES")) is False  # two current versions

    first.superseded_at = NOW
    session.flush()
    session.add(_fact(company, value_text="ES"))  # D-49: the edit is unapproved
    session.flush()
    versions = session.scalars(
        select(CompanyFactRow).where(CompanyFactRow.company_id == company.id)
    ).all()
    assert len(versions) == 2
    current = [v for v in versions if v.superseded_at is None]
    assert [(v.value_text, v.approved_at) for v in current] == [("ES", None)]


def test_two_companies_each_have_their_own_current_fact(session: Session) -> None:
    a, b = CompanyRow(name="A"), CompanyRow(name="B")
    session.add_all([a, b])
    session.flush()
    session.add_all([_fact(a), _fact(b)])
    session.flush()


def test_a_fact_needs_an_existing_company(session: Session) -> None:
    row = CompanyFactRow(
        company_id=uuid.uuid4(), key="country", value_type="text", value_text="PT", label="sourced"
    )
    assert _saves(session, row) is False


@pytest.mark.parametrize(
    ("key", "values", "saved"),
    [
        ("youngest_founder_birth_date", {"value_date": date(1995, 2, 28)}, True),
        ("youngest_founder_birth_date", {"value_boolean": True}, False),
        ("woman_founder", {"value_boolean": False}, True),
        ("woman_ceo", {"value_date": date(1995, 2, 28)}, False),
        ("woman_ceo", {}, False),
        ("woman_ceo", {"value_boolean": True, "value_date": date(1995, 2, 28)}, False),
        ("founder_age", {"value_boolean": True}, False),  # derived, never stored
    ],
)
def test_founder_fact_checks(
    session: Session, company: CompanyRow, key: str, values: dict[str, Any], saved: bool
) -> None:
    assert _saves(session, FounderFactRow(company_id=company.id, key=key, **values)) is saved


def test_a_founder_fact_is_deleted_for_real(session: Session, company: CompanyRow) -> None:
    """D-51: personal data has no history; deleting it leaves nothing behind."""
    row = FounderFactRow(company_id=company.id, key="woman_ceo", value_boolean=True)
    session.add(row)
    session.flush()
    duplicate = FounderFactRow(company_id=company.id, key="woman_ceo", value_boolean=False)
    assert _saves(session, duplicate) is False
    session.execute(delete(FounderFactRow).where(FounderFactRow.id == row.id))
    remaining = session.scalar(select(func.count()).select_from(FounderFactRow))
    assert remaining == 0


def test_intent_goals_checks_and_one_goal_per_intent(session: Session, company: CompanyRow) -> None:
    intent = IntentRow(company_id=company.id, recorded_at=NOW)
    session.add(intent)
    session.flush()
    goal = IntentGoalRow(
        intent_id=intent.id, company_id=company.id, goal="investment", goal_window="now"
    )
    assert _saves(session, goal) is True
    session.add(goal)
    session.flush()
    same_goal = IntentGoalRow(
        intent_id=intent.id, company_id=company.id, goal="investment", goal_window="later"
    )
    assert _saves(session, same_goal) is False
    for field, value in [("goal", "world_peace"), ("goal_window", "someday")]:
        values: dict[str, Any] = {
            "intent_id": intent.id,
            "company_id": company.id,
            "goal": "first_customers",
            "goal_window": "soon",
        } | {field: value}
        assert _saves(session, IntentGoalRow(**values)) is False


def test_an_intent_with_no_goals_is_allowed(session: Session, company: CompanyRow) -> None:
    """Clearing every goal is a valid record: with no goals, nothing is goal-relevant."""
    assert _saves(session, IntentRow(company_id=company.id, recorded_at=NOW)) is True


def test_intent_goal_cannot_point_at_another_companys_intent(session: Session) -> None:
    a, b = CompanyRow(name="A"), CompanyRow(name="B")
    session.add_all([a, b])
    session.flush()
    intent_a = IntentRow(company_id=a.id, recorded_at=NOW)
    session.add(intent_a)
    session.flush()
    cross = IntentGoalRow(
        intent_id=intent_a.id, company_id=b.id, goal="investment", goal_window="now"
    )
    assert _saves(session, cross) is False


@pytest.mark.parametrize(
    ("milestone", "saved"), [("first_fact_approved", True), ("first_million", False)]
)
def test_milestone_from_the_fixed_list(
    session: Session, company: CompanyRow, milestone: str, saved: bool
) -> None:
    row = MilestoneRow(company_id=company.id, milestone=milestone, reached_at=NOW)
    assert _saves(session, row) is saved


def test_each_milestone_is_reached_once(session: Session, company: CompanyRow) -> None:
    first = "first_fact_approved"
    session.add(MilestoneRow(company_id=company.id, milestone=first, reached_at=NOW))
    session.flush()
    again = MilestoneRow(company_id=company.id, milestone=first, reached_at=NOW)
    assert _saves(session, again) is False
