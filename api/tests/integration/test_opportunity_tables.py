"""Opportunity tables on a real Postgres: empty after the migration, every check at its
boundary, and every record the seed loader accepts fits (handbook section 11, D-46)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from home_base.core.db import Record
from home_base.modules.opportunities.models import (
    SCOPES,
    EvidenceRow,
    OpportunityRow,
    QuestionRow,
    RequirementRow,
    SourceRow,
)
from home_base.modules.opportunities.seed import Scope, SeedOpportunity, load_seed_dir

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed"
TODAY = date(2026, 11, 11)
TABLES = [OpportunityRow, SourceRow, RequirementRow, QuestionRow, EvidenceRow]


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


def _opportunity(**overrides: Any) -> OpportunityRow:
    values: dict[str, Any] = {
        "seed_key": f"test-{uuid.uuid4()}",
        "name": "Example Ocean Grant",
        "funder": "Example Foundation",
        "scope": "blue_specific",
        "types": ["grant"],
        "questions_known": False,
    } | overrides
    return OpportunityRow(**values)


def _saved_opportunity(session: Session) -> OpportunityRow:
    row = _opportunity()
    session.add(row)
    session.flush()
    return row


def _saves(session: Session, row: Record) -> bool:
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return False
    session.rollback()
    return True


def _rows(seed: SeedOpportunity) -> tuple[OpportunityRow, list[Record]]:
    """Map one loaded seed record to rows: the shape the reload service will write."""
    month = seed.expected_month
    opp = OpportunityRow(
        seed_key=Path(seed.source).stem,
        name=seed.name,
        funder=seed.funder,
        scope=seed.scope.value,
        types=sorted(t.value for t in seed.types),
        deadline=seed.deadline,
        timezone=seed.timezone.key if seed.timezone else None,
        opening=seed.opening,
        expected_month=date(month.year, month.month, 1) if month else None,
        questions_known=seed.questions is not None,
    )
    opp.id = uuid.uuid4()
    children: list[Record] = [
        SourceRow(
            opportunity_id=opp.id,
            url=seed.source_url,
            retrieved_on=seed.retrieved_on,
            verified_on=seed.verified_on,
            verified_by=seed.verified_by,
        )
    ]
    for i, r in enumerate(seed.requirements):
        children.append(
            RequirementRow(
                opportunity_id=opp.id,
                position=i,
                hard=r.hard,
                quote=r.quote,
                fact=r.fact,
                operator=r.operator.value if r.operator else None,
                value=r.value,
                criterion=r.criterion,
            )
        )
    for i, q in enumerate(seed.questions or ()):
        children.append(
            QuestionRow(
                opportunity_id=opp.id,
                position=i,
                text=q.text,
                required_facts=sorted(q.required_facts),
            )
        )
    for e in seed.evidence:
        children.append(
            EvidenceRow(opportunity_id=opp.id, kind=e.kind.value, dated=e.dated, url=e.source_url)
        )
    return opp, children


def test_scopes_match_the_seed_enum() -> None:
    assert set(SCOPES) == {s.value for s in Scope}


@pytest.mark.parametrize("model", TABLES)
def test_tables_are_empty_after_the_migration(session: Session, model: type[Record]) -> None:
    assert session.scalar(select(func.count()).select_from(model)) == 0


def test_every_seed_fixture_fits_the_tables(session: Session) -> None:
    seeds = load_seed_dir(FIXTURES, TODAY)
    assert seeds, "fixtures are missing"
    for seed in seeds:
        opp, children = _rows(seed)
        session.add(opp)
        session.flush()
        session.add_all(children)
        session.flush()
    count = session.scalar(select(func.count()).select_from(OpportunityRow))
    assert count == len(seeds)


def test_requirement_value_keeps_its_json_type(session: Session) -> None:
    opp = _saved_opportunity(session)
    row = RequirementRow(
        opportunity_id=opp.id,
        position=0,
        hard=True,
        quote="Applicants must be based in the EU.",
        fact="country",
        operator="one_of",
        value=["PT", "ES"],
    )
    session.add(row)
    session.flush()
    session.expire(row)
    assert row.value == ["PT", "ES"]


def test_seed_key_is_unique(session: Session) -> None:
    session.add(_opportunity(seed_key="same"))
    session.flush()
    assert _saves(session, _opportunity(seed_key="same")) is False


@pytest.mark.parametrize(
    ("overrides", "saved"),
    [
        ({"scope": "all_sectors"}, True),
        ({"scope": "ocean"}, False),
        ({"types": ["grant", "prize"]}, True),
        ({"types": []}, False),
        ({"types": ["grant", "loan"]}, False),
        ({"deadline": date(2027, 1, 20), "timezone": "Europe/Brussels"}, True),
        ({"deadline": date(2027, 1, 20), "timezone": None}, False),
        ({"timezone": "Europe/Lisbon"}, True),
        ({"expected_month": date(2027, 4, 1)}, True),
        ({"expected_month": date(2027, 4, 2)}, False),
    ],
)
def test_opportunity_checks(session: Session, overrides: dict[str, Any], saved: bool) -> None:
    assert _saves(session, _opportunity(**overrides)) is saved


@pytest.mark.parametrize(
    ("url", "saved"),
    [("https://example.org/call", True), ("http://example.org/call", False), ("", False)],
)
def test_source_and_evidence_urls_are_https(session: Session, url: str, saved: bool) -> None:
    opp = _saved_opportunity(session)
    source = SourceRow(
        opportunity_id=opp.id,
        url=url,
        retrieved_on=TODAY,
        verified_on=TODAY,
        verified_by="Andrew",
    )
    assert _saves(session, source) is saved
    opp = _saved_opportunity(session)
    evidence = EvidenceRow(opportunity_id=opp.id, kind="announcement", dated=TODAY, url=url)
    assert _saves(session, evidence) is saved


@pytest.mark.parametrize(
    ("overrides", "saved"),
    [
        ({}, True),
        ({"operator": "between"}, False),
        ({"fact": None}, False),
        ({"operator": None}, False),
        ({"criterion": "Clear ocean benefit"}, False),
        ({"hard": False, "fact": None, "operator": None, "criterion": "Clear benefit"}, True),
        ({"hard": False, "fact": None, "operator": None, "criterion": None}, False),
        ({"quote": ""}, False),
        ({"quote": "   "}, False),
        ({"position": -1}, False),
    ],
)
def test_requirement_checks(session: Session, overrides: dict[str, Any], saved: bool) -> None:
    opp = _saved_opportunity(session)
    values: dict[str, Any] = {
        "opportunity_id": opp.id,
        "position": 0,
        "hard": True,
        "quote": "Applicants must be based in Portugal.",
        "fact": "country",
        "operator": "equals",
        "value": "PT",
    } | overrides
    assert _saves(session, RequirementRow(**values)) is saved


@pytest.mark.parametrize(("kind", "saved"), [("previous_edition", True), ("rumour", False)])
def test_evidence_kind_is_checked(session: Session, kind: str, saved: bool) -> None:
    opp = _saved_opportunity(session)
    row = EvidenceRow(opportunity_id=opp.id, kind=kind, dated=TODAY, url="https://example.org")
    assert _saves(session, row) is saved


def test_children_need_an_existing_opportunity(session: Session) -> None:
    row = QuestionRow(opportunity_id=uuid.uuid4(), position=0, text="Team?", required_facts=[])
    assert _saves(session, row) is False


def test_archiving_keeps_the_row(session: Session) -> None:
    """No hard deletes (handbook section 11): a reload archives what it replaces."""
    opp = _saved_opportunity(session)
    opp.archived_at = datetime(2026, 11, 11, tzinfo=UTC)
    session.flush()
    assert session.get(OpportunityRow, opp.id) is not None
