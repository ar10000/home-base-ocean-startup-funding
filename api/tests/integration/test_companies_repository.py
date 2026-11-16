"""CompanyRepository on a real Postgres: fact versions (D-49, D-50), founder facts
(D-51), intent history, and isolation between companies."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from home_base.core.errors import FactError
from home_base.modules.companies.domain import (
    FactLabel,
    FounderFact,
    Goal,
    GoalChoice,
    IntentRecord,
    Window,
)
from home_base.modules.companies.models import CompanyRow
from home_base.modules.companies.repository import CompanyRepository

pytestmark = pytest.mark.integration

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)
T2 = T0 + timedelta(hours=2)
FOUNDER = uuid.uuid4()
BIRTH = date(1995, 2, 28)


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def repos(session: Session) -> tuple[CompanyRepository, CompanyRepository]:
    a, b = CompanyRow(name="A"), CompanyRow(name="B")
    session.add_all([a, b])
    session.flush()
    return CompanyRepository(session, a.id), CompanyRepository(session, b.id)


# Company facts


def test_a_new_company_has_no_facts(repos: tuple[CompanyRepository, CompanyRepository]) -> None:
    a, _ = repos
    assert a.current_facts() == []
    assert a.fact_history("country") == []
    assert a.founder_facts() == []
    assert a.intents() == []


@pytest.mark.parametrize(
    ("key", "value"), [("country", "PT"), ("team_size", 0), ("trl", 9), ("team_size", 250)]
)
def test_a_fact_is_added_unapproved_with_its_label(
    repos: tuple[CompanyRepository, CompanyRepository], key: str, value: str | int
) -> None:
    a, _ = repos
    version = a.add_fact_version(key, value, FactLabel.AI_SUGGESTED, "https://example.org", T0)
    assert (version.key, version.value, version.label) == (key, value, FactLabel.AI_SUGGESTED)
    assert (version.approved_at, version.superseded_at, version.recorded_at) == (None, None, T0)
    assert a.current_facts() == [version]


@pytest.mark.parametrize(
    ("key", "value", "problem"),
    [
        ("favourite_colour", "blue", "unknown fact"),
        ("country", 351, "takes a text value"),
        ("team_size", "four", "takes a integer value"),
        ("trl", True, "takes a integer value"),  # a bool is not a number here
        ("country", False, "takes a text value"),
    ],
)
def test_unknown_keys_and_wrong_types_are_refused(
    repos: tuple[CompanyRepository, CompanyRepository], key: str, value: object, problem: str
) -> None:
    a, _ = repos
    with pytest.raises(FactError, match=problem):
        a.add_fact_version(key, value, FactLabel.USER_PROVIDED, None, T0)  # type: ignore[arg-type]


def test_an_edit_supersedes_the_current_version_and_needs_approving_again(
    repos: tuple[CompanyRepository, CompanyRepository],
) -> None:
    """D-49 and D-50: the approved version stays in history; the edit is unapproved."""
    a, _ = repos
    first = a.add_fact_version("country", "PT", FactLabel.USER_PROVIDED, None, T0)
    approved = a.approve_fact(first.id, FOUNDER, T1)
    edit = a.add_fact_version("country", "ES", FactLabel.USER_PROVIDED, None, T2)
    assert a.current_facts() == [edit]
    assert edit.approved_at is None
    history = a.fact_history("country")
    assert [(v.value, v.superseded_at) for v in history] == [("PT", T2), ("ES", None)]
    assert history[0].approved_at == approved.approved_at == T1


def test_approving_twice_keeps_the_first_approval(
    repos: tuple[CompanyRepository, CompanyRepository],
) -> None:
    a, _ = repos
    version = a.add_fact_version("trl", 4, FactLabel.SOURCED, None, T0)
    first = a.approve_fact(version.id, FOUNDER, T1)
    again = a.approve_fact(version.id, uuid.uuid4(), T2)
    assert again == first
    assert (first.approved_at, first.approved_by, first.label) == (T1, FOUNDER, FactLabel.SOURCED)


def test_only_the_current_version_can_be_approved(
    repos: tuple[CompanyRepository, CompanyRepository],
) -> None:
    a, _ = repos
    old = a.add_fact_version("trl", 4, FactLabel.SOURCED, None, T0)
    a.add_fact_version("trl", 5, FactLabel.SOURCED, None, T1)
    with pytest.raises(FactError, match="only the current version"):
        a.approve_fact(old.id, FOUNDER, T2)


def test_a_company_cannot_approve_or_see_another_companys_fact(
    repos: tuple[CompanyRepository, CompanyRepository],
) -> None:
    a, b = repos
    theirs = b.add_fact_version("country", "ES", FactLabel.USER_PROVIDED, None, T0)
    a.add_fact_version("country", "PT", FactLabel.USER_PROVIDED, None, T0)
    with pytest.raises(FactError, match="no such fact version"):
        a.approve_fact(theirs.id, FOUNDER, T1)
    assert [f.value for f in a.current_facts()] == ["PT"]
    assert [f.value for f in b.fact_history("country")] == ["ES"]


# Founder facts


def test_a_founder_fact_is_set_unapproved_then_approved(
    repos: tuple[CompanyRepository, CompanyRepository],
) -> None:
    a, _ = repos
    assert a.set_founder_fact("youngest_founder_birth_date", BIRTH, T0) == FounderFact(
        "youngest_founder_birth_date", BIRTH, None
    )
    approved = a.approve_founder_fact("youngest_founder_birth_date", FOUNDER, T1)
    assert approved.approved_at == T1
    assert a.approve_founder_fact("youngest_founder_birth_date", uuid.uuid4(), T2) == approved


def test_changing_a_founder_fact_needs_approving_again(
    repos: tuple[CompanyRepository, CompanyRepository],
) -> None:
    a, _ = repos
    a.set_founder_fact("woman_ceo", True, T0)
    a.approve_founder_fact("woman_ceo", FOUNDER, T1)
    changed = a.set_founder_fact("woman_ceo", False, T2)
    assert changed == FounderFact("woman_ceo", False, None)
    assert a.founder_facts() == [changed]


@pytest.mark.parametrize(
    ("key", "value", "problem"),
    [
        ("founder_age", 29, "unknown founder fact"),  # derived, never stored
        ("woman_ceo", BIRTH, "takes a boolean value"),
        ("youngest_founder_birth_date", True, "takes a date value"),
    ],
)
def test_founder_fact_keys_and_types_are_checked(
    repos: tuple[CompanyRepository, CompanyRepository], key: str, value: object, problem: str
) -> None:
    a, _ = repos
    with pytest.raises(FactError, match=problem):
        a.set_founder_fact(key, value, T0)  # type: ignore[arg-type]


def test_approving_a_missing_founder_fact_is_refused(
    repos: tuple[CompanyRepository, CompanyRepository],
) -> None:
    a, _ = repos
    with pytest.raises(FactError, match="no founder fact"):
        a.approve_founder_fact("woman_founder", FOUNDER, T0)


def test_deleting_a_founder_fact_removes_it_only_for_that_company(
    repos: tuple[CompanyRepository, CompanyRepository],
) -> None:
    a, b = repos
    a.set_founder_fact("woman_founder", True, T0)
    b.set_founder_fact("woman_founder", True, T0)
    assert a.delete_founder_fact("woman_founder") is True
    assert a.delete_founder_fact("woman_founder") is False  # nothing left to delete
    assert a.founder_facts() == []
    assert [f.key for f in b.founder_facts()] == ["woman_founder"]


# Intent


def test_intents_come_back_oldest_first_with_their_goals(
    repos: tuple[CompanyRepository, CompanyRepository],
) -> None:
    a, b = repos
    first = IntentRecord(
        goals=(
            GoalChoice(Goal.PILOT_OR_TEST_SITE, Window.SOON),  # the fixed list's order
            GoalChoice(Goal.NON_DILUTIVE_FUNDING, Window.NOW),
        ),
        recorded_at=T0,
    )
    second = IntentRecord(goals=(GoalChoice(Goal.INVESTMENT, Window.LATER),), recorded_at=T1)
    a.add_intent(second)
    a.add_intent(first)
    other = IntentRecord(goals=(GoalChoice(Goal.FIRST_CUSTOMERS, Window.NOW),), recorded_at=T0)
    b.add_intent(other)
    assert a.intents() == [first, second]
    assert len(b.intents()) == 1
