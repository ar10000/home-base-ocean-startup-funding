"""INT-04 through the services, on a real Postgres: every fact or intent change writes its
audit event and recalculates the company's matches in one transaction; repeats write
nothing; no longer eligible is calculated and archived on confirmation (D-52 to D-54)."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from home_base.core.context import Caller, Clock
from home_base.core.errors import ApplicationError
from home_base.core.vocabulary import FitStatus
from home_base.modules.applications import service as applications
from home_base.modules.applications.repository import ApplicationRepository
from home_base.modules.audit.models import AuditEvent
from home_base.modules.audit.repository import AuditRepository
from home_base.modules.companies import service as companies
from home_base.modules.companies.domain import FactLabel, Goal, GoalChoice, Window
from home_base.modules.companies.models import CompanyRow
from home_base.modules.matching import service as matching
from home_base.modules.matching.models import MatchRow
from home_base.modules.opportunities.repository import OpportunityRepository
from home_base.modules.opportunities.seed import load_seed_dir
from home_base.modules.opportunities.service import StoredOpportunity, current_opportunities

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed"
TODAY = date(2026, 11, 11)
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def _clock(minutes: int) -> Clock:
    return Clock(at=T0 + timedelta(minutes=minutes), today=TODAY, request_id=f"req-{minutes}")


@dataclass
class World:
    session: Session
    caller: Caller
    other: Caller
    grant: StoredOpportunity  # country = PT, TRL at least 4


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def world(session: Session) -> World:
    a, b = CompanyRow(name="A"), CompanyRow(name="B")
    session.add_all([a, b])
    session.flush()
    OpportunityRepository(session).reload(load_seed_dir(FIXTURES, TODAY), T0)
    grant = next(
        o for o in current_opportunities(session) if o.record.name == "Fictional Ocean Grant"
    )
    return World(session, Caller(a.id, uuid.uuid4()), Caller(b.id, uuid.uuid4()), grant)


def _fit(w: World, caller: Caller | None = None) -> FitStatus | None:
    company = (caller or w.caller).company_id
    found = {m.opportunity_id: m.fit.status for m in matching.current_matches(w.session, company)}
    return found.get(w.grant.id)


def _count(w: World, model: type[MatchRow] | type[AuditEvent]) -> int:
    return int(w.session.scalar(select(func.count()).select_from(model)) or 0)


def _approved(w: World, key: str, value: str | int, minutes: int) -> None:
    v = companies.add_fact(
        w.session, w.caller, companies.NewFact(key, value, FactLabel.USER_PROVIDED), _clock(minutes)
    )
    companies.approve_fact(w.session, w.caller, v.id, _clock(minutes + 1))


def test_int_04_adding_and_approving_facts_recalculates(world: World) -> None:
    version = companies.add_fact(
        world.session,
        world.caller,
        companies.NewFact("country", "PT", FactLabel.SOURCED),
        _clock(0),
    )
    assert _fit(world) is FitStatus.POSSIBLE  # unapproved: Unknown
    companies.approve_fact(world.session, world.caller, version.id, _clock(1))
    _approved(world, "trl", 4, 2)
    assert _fit(world) is FitStatus.CONFIRMED


def test_int_04_an_edit_needs_approving_before_it_counts(world: World) -> None:
    """D-49 through the service: editing an approved fact returns its rule to Unknown."""
    _approved(world, "country", "PT", 0)
    _approved(world, "trl", 4, 2)
    assert _fit(world) is FitStatus.CONFIRMED
    companies.add_fact(
        world.session, world.caller, companies.NewFact("trl", 3, FactLabel.USER_PROVIDED), _clock(4)
    )
    assert _fit(world) is FitStatus.POSSIBLE


def test_int_04_each_change_is_audited_with_its_request(world: World) -> None:
    version = companies.add_fact(
        world.session,
        world.caller,
        companies.NewFact("country", "PT", FactLabel.SOURCED),
        _clock(0),
    )
    companies.approve_fact(world.session, world.caller, version.id, _clock(1))
    history = AuditRepository(world.session, world.caller.company_id).history(
        "company_fact", version.id
    )
    assert [(e.action, e.actor_id, e.request_id) for e in history] == [
        ("fact.added", world.caller.user_id, "req-0"),
        ("fact.approved", world.caller.user_id, "req-1"),
    ]
    assert history[0].after == {"key": "country", "value": "PT", "label": "sourced"}


def test_int_04_approving_twice_writes_nothing_more(world: World) -> None:
    version = companies.add_fact(
        world.session,
        world.caller,
        companies.NewFact("country", "PT", FactLabel.SOURCED),
        _clock(0),
    )
    companies.approve_fact(world.session, world.caller, version.id, _clock(1))
    counts = (_count(world, AuditEvent), _count(world, MatchRow))
    companies.approve_fact(world.session, world.caller, version.id, _clock(2))
    assert (_count(world, AuditEvent), _count(world, MatchRow)) == counts


def test_int_04_an_intent_change_is_audited_and_stores_no_new_match(world: World) -> None:
    """D-54: intent never changes a fit."""
    _approved(world, "country", "PT", 0)
    matches = _count(world, MatchRow)
    record = companies.set_intent(
        world.session, world.caller, [GoalChoice(Goal.NON_DILUTIVE_FUNDING, Window.NOW)], _clock(5)
    )
    assert _count(world, MatchRow) == matches
    (event,) = [
        e
        for e in world.session.scalars(
            select(AuditEvent).where(AuditEvent.action == "intent.changed")
        )
    ]
    assert event.after == {"goals": [["non_dilutive_funding", "now"]]}
    assert record.recorded_at == _clock(5).at


def test_int_04_founder_facts_recalculate_and_their_events_carry_no_values(world: World) -> None:
    companies.set_founder_fact(world.session, world.caller, "woman_ceo", True, _clock(0))
    companies.approve_founder_fact(world.session, world.caller, "woman_ceo", _clock(1))
    assert companies.match_inputs(world.session, world.caller.company_id).facts[-1].approved
    companies.set_founder_fact(
        world.session, world.caller, "woman_ceo", True, _clock(2)
    )  # same value
    assert (
        companies.delete_founder_fact(world.session, world.caller, "woman_ceo", _clock(3)) is True
    )
    assert (
        companies.delete_founder_fact(world.session, world.caller, "woman_ceo", _clock(4)) is False
    )
    events = world.session.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity == "founder_fact")
        .order_by(AuditEvent.occurred_at)
    ).all()
    assert [(e.action, e.before, e.after) for e in events] == [
        ("founder_fact.set", None, None),
        ("founder_fact.approved", None, None),
        ("founder_fact.deleted", None, None),
    ]
    assert companies.match_inputs(world.session, world.caller.company_id).facts == ()


def test_int_04_the_approved_birth_date_feeds_founder_age(world: World) -> None:
    birth = date(1997, 2, 1)
    companies.set_founder_fact(
        world.session, world.caller, "youngest_founder_birth_date", birth, _clock(0)
    )
    assert (
        companies.match_inputs(world.session, world.caller.company_id).approved_birth_date is None
    )
    companies.approve_founder_fact(
        world.session, world.caller, "youngest_founder_birth_date", _clock(1)
    )
    assert (
        companies.match_inputs(world.session, world.caller.company_id).approved_birth_date == birth
    )


def test_int_04_no_longer_eligible_is_calculated_then_archived_on_confirmation(
    world: World,
) -> None:
    _approved(world, "country", "PT", 0)
    app = ApplicationRepository(world.session, world.caller.company_id).start(
        world.grant.id, _clock(2).at
    )
    assert applications.no_longer_eligible(world.session, world.caller.company_id) == []
    with pytest.raises(ApplicationError, match="still eligible"):
        applications.confirm_no_longer_eligible(world.session, world.caller, app.id, _clock(3))

    _approved(world, "country", "ES", 4)  # the company moved: not eligible any more
    marked = applications.no_longer_eligible(world.session, world.caller.company_id)
    assert [a.id for a in marked] == [app.id]

    applications.confirm_no_longer_eligible(world.session, world.caller, app.id, _clock(6))
    assert applications.no_longer_eligible(world.session, world.caller.company_id) == []
    assert ApplicationRepository(world.session, world.caller.company_id).open_applications() == []
    (event,) = AuditRepository(world.session, world.caller.company_id).history(
        "application", app.id
    )
    assert event.action == "application.archived_not_eligible"


def test_int_04_one_companys_change_does_not_touch_another(world: World) -> None:
    _approved(world, "country", "ES", 0)
    assert _fit(world) is FitStatus.NOT_ELIGIBLE
    assert _fit(world, world.other) is None  # never recalculated: nothing changed for B


def test_int_04_approving_a_founder_fact_twice_writes_nothing_more(world: World) -> None:
    companies.set_founder_fact(world.session, world.caller, "woman_founder", True, _clock(0))
    companies.approve_founder_fact(world.session, world.caller, "woman_founder", _clock(1))
    events = _count(world, AuditEvent)
    companies.approve_founder_fact(world.session, world.caller, "woman_founder", _clock(2))
    assert _count(world, AuditEvent) == events
