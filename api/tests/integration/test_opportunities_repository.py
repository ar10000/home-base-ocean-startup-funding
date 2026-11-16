"""OpportunityRepository on a real Postgres: reloading from the seed files (D-46)."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from home_base.modules.opportunities.domain import Evidence, EvidenceKind
from home_base.modules.opportunities.models import OpportunityRow, RequirementRow
from home_base.modules.opportunities.repository import OpportunityRepository, ReloadSummary
from home_base.modules.opportunities.seed import SeedOpportunity, load_seed_dir

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed"
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(days=1)
T2 = T0 + timedelta(days=2)


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def seeds() -> list[SeedOpportunity]:
    found = load_seed_dir(FIXTURES, date(2026, 11, 11))
    assert len(found) >= 2, "the tests need at least two fixtures"
    return found


def _count(
    session: Session, model: type[OpportunityRow] | type[RequirementRow], **where: object
) -> int:
    query = select(func.count()).select_from(model)
    if "archived" in where:
        column = model.archived_at
        query = query.where(column.is_not(None) if where["archived"] else column.is_(None))
    return int(session.scalar(query) or 0)


def test_reloading_nothing_into_an_empty_database(session: Session) -> None:
    repo = OpportunityRepository(session)
    assert repo.reload([], T0) == ReloadSummary()
    assert repo.current() == []


def test_first_reload_adds_every_file_and_reads_back_the_same_records(
    session: Session, seeds: list[SeedOpportunity]
) -> None:
    repo = OpportunityRepository(session)
    summary = repo.reload(seeds, T0)
    assert summary.added == sorted(Path(s.source).stem for s in seeds)
    assert (summary.changed, summary.unchanged, summary.archived) == ([], [], [])
    stored = repo.current()
    assert sorted((s.record for s in stored), key=lambda r: r.source) == sorted(
        seeds, key=lambda r: r.source
    )
    for s in stored:
        assert len(s.requirement_ids) == len(s.record.requirements)
        assert len(s.question_ids) == len(s.record.questions or ())


def test_reloading_the_same_files_changes_nothing(
    session: Session, seeds: list[SeedOpportunity]
) -> None:
    repo = OpportunityRepository(session)
    repo.reload(seeds, T0)
    ids = {s.id: s.requirement_ids for s in repo.current()}
    requirements = _count(session, RequirementRow)
    summary = repo.reload(seeds, T1)
    assert summary.unchanged == sorted(Path(s.source).stem for s in seeds)
    assert summary.added == summary.changed == summary.archived == []
    assert _count(session, RequirementRow) == requirements
    assert {s.id: s.requirement_ids for s in repo.current()} == ids


def test_evidence_in_a_different_order_is_not_a_change(
    session: Session, seeds: list[SeedOpportunity]
) -> None:
    first = replace(
        seeds[0],
        evidence=(
            Evidence(EvidenceKind.ANNOUNCEMENT, date(2026, 7, 2), "https://example.org/a"),
            Evidence(EvidenceKind.PREVIOUS_EDITION, date(2026, 3, 1), "https://example.org/b"),
        ),
    )
    repo = OpportunityRepository(session)
    repo.reload([first], T0)
    shuffled = replace(first, evidence=tuple(reversed(first.evidence)))
    assert repo.reload([shuffled], T1).unchanged == [Path(first.source).stem]


def test_a_changed_file_archives_the_old_rows_and_keeps_the_opportunity(
    session: Session, seeds: list[SeedOpportunity]
) -> None:
    repo = OpportunityRepository(session)
    repo.reload(seeds, T0)
    before = {s.record.source: s for s in repo.current()}
    target = seeds[0]
    edited = replace(target, name=target.name + " (2027)", requirements=target.requirements[:1])
    summary = repo.reload([edited, *seeds[1:]], T1)
    key = Path(target.source).stem
    assert summary.changed == [key]
    after = {s.record.source: s for s in repo.current()}
    assert after[target.source].id == before[target.source].id  # same opportunity
    assert after[target.source].record == edited
    assert set(after[target.source].requirement_ids).isdisjoint(
        before[target.source].requirement_ids
    )
    archived = _count(session, RequirementRow, archived=True)
    assert archived == len(target.requirements)  # old rows kept, archived, never deleted


def test_a_removed_file_archives_the_opportunity_and_a_returning_one_restores_it(
    session: Session, seeds: list[SeedOpportunity]
) -> None:
    repo = OpportunityRepository(session)
    repo.reload(seeds, T0)
    gone = seeds[0]
    key = Path(gone.source).stem
    summary = repo.reload(seeds[1:], T1)
    assert summary.archived == [key]
    assert gone.source not in {s.record.source for s in repo.current()}
    assert _count(session, OpportunityRow) == len(seeds)  # still there, archived

    back = repo.reload(seeds, T2)
    assert back.changed == [key]
    assert gone in [s.record for s in repo.current()]
