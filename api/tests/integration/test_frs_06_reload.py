"""FRS-06 through the reload job, on a real Postgres: each change from the seed files is
logged and the affected matches are recalculated for every company, in one transaction
(D-46, D-52)."""

import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from home_base.core.context import Caller, Clock
from home_base.core.vocabulary import FitStatus
from home_base.jobs.reload_seed import reload_seed, reload_seed_dir
from home_base.modules.audit.models import AuditEvent
from home_base.modules.companies import service as companies
from home_base.modules.companies.domain import FactLabel
from home_base.modules.companies.models import CompanyRow
from home_base.modules.matching import service as matching
from home_base.modules.matching.models import MatchRow
from home_base.modules.opportunities.seed import SeedOpportunity, load_seed_dir

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed"
TODAY = date(2026, 11, 11)
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def _clock(hours: int) -> Clock:
    return Clock(at=T0 + timedelta(hours=hours), today=TODAY, request_id=f"deploy-{hours}")


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def seeds() -> list[SeedOpportunity]:
    return load_seed_dir(FIXTURES, TODAY)


@pytest.fixture
def portuguese(session: Session) -> Caller:
    """A company in Portugal at TRL 5, both facts approved."""
    row = CompanyRow(name="PT Co")
    session.add(row)
    session.flush()
    caller = Caller(row.id, uuid.uuid4())
    for key, value in (("country", "PT"), ("trl", 5)):
        v = companies.add_fact(
            session, caller, companies.NewFact(key, value, FactLabel.USER_PROVIDED), _clock(-2)
        )
        companies.approve_fact(session, caller, v.id, _clock(-2))
    return caller


def _grant(seeds: list[SeedOpportunity]) -> SeedOpportunity:
    return next(s for s in seeds if s.name == "Fictional Ocean Grant")


def _fits(session: Session, caller: Caller) -> list[FitStatus]:
    return sorted(m.fit.status for m in matching.current_matches(session, caller.company_id))


def _events(session: Session, action: str) -> int:
    query = select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
    return int(session.scalar(query) or 0)


def test_frs_06_reloading_with_no_companies_and_no_files(session: Session) -> None:
    summary = reload_seed(session, [], _clock(0))
    assert (summary.added, summary.changed, summary.archived) == ([], [], [])
    assert int(session.scalar(select(func.count()).select_from(AuditEvent)) or 0) == 0


def test_frs_06_first_reload_logs_each_opportunity_and_matches_every_company(
    session: Session, seeds: list[SeedOpportunity], portuguese: Caller
) -> None:
    reload_seed_dir(session, FIXTURES, _clock(0))
    assert _events(session, "opportunity.added") == len(seeds)
    assert _fits(session, portuguese) == [FitStatus.CONFIRMED, FitStatus.POSSIBLE]


def test_frs_06_an_unchanged_reload_writes_nothing(
    session: Session, seeds: list[SeedOpportunity], portuguese: Caller
) -> None:
    reload_seed(session, seeds, _clock(0))
    counts = [
        int(session.scalar(select(func.count()).select_from(m)) or 0)
        for m in (AuditEvent, MatchRow)
    ]
    summary = reload_seed(session, seeds, _clock(1))
    assert len(summary.unchanged) == len(seeds)
    assert [
        int(session.scalar(select(func.count()).select_from(m)) or 0)
        for m in (AuditEvent, MatchRow)
    ] == counts


def test_frs_06_a_changed_call_is_logged_and_its_matches_recalculated(
    session: Session, seeds: list[SeedOpportunity], portuguese: Caller
) -> None:
    reload_seed(session, seeds, _clock(0))
    grant = _grant(seeds)
    stricter = replace(
        grant,
        requirements=tuple(
            replace(r, value=6) if r.fact == "trl" else r for r in grant.requirements
        ),
    )
    others = [s for s in seeds if s is not grant]
    summary = reload_seed(session, [stricter, *others], _clock(1))
    assert summary.changed == ["fictional-ocean-grant"]
    assert _events(session, "opportunity.changed") == 1
    assert _fits(session, portuguese) == [FitStatus.NOT_ELIGIBLE, FitStatus.POSSIBLE]  # TRL 5 < 6
    (event,) = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "opportunity.changed")
    ).all()
    assert (event.company_id, event.actor, event.request_id) == (None, "system", "deploy-1")


def test_frs_06_an_archived_call_is_logged_and_keeps_its_last_match(
    session: Session, seeds: list[SeedOpportunity], portuguese: Caller
) -> None:
    reload_seed(session, seeds, _clock(0))
    grant = _grant(seeds)
    matches = int(session.scalar(select(func.count()).select_from(MatchRow)) or 0)
    reload_seed(session, [s for s in seeds if s is not grant], _clock(1))
    assert _events(session, "opportunity.archived") == 1
    assert int(session.scalar(select(func.count()).select_from(MatchRow)) or 0) == matches


def test_frs_06_every_company_is_recalculated(
    session: Session, seeds: list[SeedOpportunity], portuguese: Caller
) -> None:
    row = CompanyRow(name="New Co")
    session.add(row)
    session.flush()
    newcomer = Caller(row.id, uuid.uuid4())
    reload_seed(session, seeds, _clock(0))
    assert _fits(session, newcomer) == [FitStatus.POSSIBLE, FitStatus.POSSIBLE]  # no facts yet
    assert _fits(session, portuguese) == [FitStatus.CONFIRMED, FitStatus.POSSIBLE]
