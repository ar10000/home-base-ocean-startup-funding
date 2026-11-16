"""Decisions and starting an application through the services, on a real Postgres
(DEC-01, DEC-02): dated history, audit events, safe repeats, one company at a time."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from home_base.core.context import Caller, Clock
from home_base.core.errors import DecisionError
from home_base.core.vocabulary import Decision
from home_base.modules.applications import service as applications
from home_base.modules.audit.models import AuditEvent
from home_base.modules.audit.repository import AuditRepository
from home_base.modules.companies.models import CompanyRow
from home_base.modules.matching import service as matching
from home_base.modules.matching.domain import NotForUsReason
from home_base.modules.opportunities.repository import OpportunityRepository
from home_base.modules.opportunities.seed import load_seed_dir
from home_base.modules.opportunities.service import current_opportunities

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed"
TODAY = date(2026, 11, 11)
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def _clock(minutes: int) -> Clock:
    return Clock(at=T0 + timedelta(minutes=minutes), today=TODAY, request_id=f"req-{minutes}")


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def setup(session: Session) -> tuple[Caller, Caller, uuid.UUID]:
    a, b = CompanyRow(name="A"), CompanyRow(name="B")
    session.add_all([a, b])
    session.flush()
    OpportunityRepository(session).reload(load_seed_dir(FIXTURES, TODAY), T0)
    opportunity = current_opportunities(session)[0].id
    return Caller(a.id, uuid.uuid4()), Caller(b.id, uuid.uuid4()), opportunity


def _events(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(AuditEvent)) or 0)


def test_no_decision_is_none(session: Session, setup: tuple[Caller, Caller, uuid.UUID]) -> None:
    caller, _, opp = setup
    assert matching.current_decision(session, caller.company_id, opp) is Decision.NONE
    assert (
        matching.change_decision(session, caller, opp, (Decision.NONE, None), _clock(0))
        is Decision.NONE
    )
    assert _events(session) == 0  # choosing none when there is none writes nothing


def test_each_change_is_dated_and_logged(
    session: Session, setup: tuple[Caller, Caller, uuid.UUID]
) -> None:
    caller, _, opp = setup
    matching.change_decision(session, caller, opp, (Decision.LATER, None), _clock(0))
    matching.change_decision(
        session, caller, opp, (Decision.NOT_FOR_US, NotForUsReason.TOO_EARLY), _clock(1)
    )
    matching.change_decision(session, caller, opp, (Decision.NONE, None), _clock(2))  # reversible
    assert matching.current_decision(session, caller.company_id, opp) is Decision.NONE
    history = AuditRepository(session, caller.company_id).history("opportunity", opp)
    assert [(e.before, e.after, e.request_id) for e in history] == [
        ({"decision": "none"}, {"decision": "later", "reason": None}, "req-0"),
        ({"decision": "later"}, {"decision": "not_for_us", "reason": "too_early"}, "req-1"),
        ({"decision": "not_for_us"}, {"decision": "none", "reason": None}, "req-2"),
    ]


def test_the_same_decision_again_writes_nothing(
    session: Session, setup: tuple[Caller, Caller, uuid.UUID]
) -> None:
    caller, _, opp = setup
    matching.change_decision(session, caller, opp, (Decision.LATER, None), _clock(0))
    events = _events(session)
    matching.change_decision(session, caller, opp, (Decision.LATER, None), _clock(1))
    assert _events(session) == events


def test_a_new_reason_is_a_change(
    session: Session, setup: tuple[Caller, Caller, uuid.UUID]
) -> None:
    caller, _, opp = setup
    matching.change_decision(session, caller, opp, (Decision.NOT_FOR_US, None), _clock(0))
    matching.change_decision(
        session, caller, opp, (Decision.NOT_FOR_US, NotForUsReason.OTHER), _clock(1)
    )
    assert _events(session) == 2


def test_a_reason_is_only_for_not_for_us(
    session: Session, setup: tuple[Caller, Caller, uuid.UUID]
) -> None:
    caller, _, opp = setup
    with pytest.raises(DecisionError, match="only Not for us"):
        matching.change_decision(
            session, caller, opp, (Decision.LATER, NotForUsReason.TOO_EARLY), _clock(0)
        )
    assert _events(session) == 0


def test_dec_02_starting_an_application_sets_pursuing(
    session: Session, setup: tuple[Caller, Caller, uuid.UUID]
) -> None:
    caller, _, opp = setup
    matching.change_decision(session, caller, opp, (Decision.NOT_FOR_US, None), _clock(0))
    application = applications.start_application(session, caller, opp, _clock(1))
    assert matching.current_decision(session, caller.company_id, opp) is Decision.PURSUING
    (started,) = AuditRepository(session, caller.company_id).history("application", application.id)
    assert started.action == "application.started"


def test_dec_02_starting_twice_writes_nothing_more(
    session: Session, setup: tuple[Caller, Caller, uuid.UUID]
) -> None:
    caller, _, opp = setup
    first = applications.start_application(session, caller, opp, _clock(0))
    events = _events(session)
    assert applications.start_application(session, caller, opp, _clock(1)) == first
    assert _events(session) == events


def test_one_companys_decision_is_not_anothers(
    session: Session, setup: tuple[Caller, Caller, uuid.UUID]
) -> None:
    a, b, opp = setup
    matching.change_decision(session, a, opp, (Decision.PURSUING, None), _clock(0))
    assert matching.current_decision(session, b.company_id, opp) is Decision.NONE
    assert AuditRepository(session, b.company_id).history("opportunity", opp) == []
