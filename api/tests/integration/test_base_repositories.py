"""The tenant base repository and the audit repository on a real Postgres
(handbook sections 12 and 13): one company never sees or writes another's rows."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from home_base.core.errors import AuditError, TenantError
from home_base.core.repository import TenantRepository
from home_base.modules.audit.domain import Actor, AuditEntry
from home_base.modules.audit.models import AuditEvent
from home_base.modules.audit.repository import AuditRepository
from home_base.modules.companies.models import CompanyFactRow, CompanyRow, FactDefinitionRow

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
FOUNDER = uuid.uuid4()


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def companies(session: Session) -> tuple[CompanyRow, CompanyRow]:
    a, b = CompanyRow(name="A"), CompanyRow(name="B")
    session.add_all([a, b])
    session.flush()
    return a, b


def _fact(**overrides: object) -> CompanyFactRow:
    values: dict[str, object] = {
        "key": "country",
        "value_type": "text",
        "value_text": "PT",
        "label": "user_provided",
    } | overrides
    return CompanyFactRow(**values)


def _entry(**overrides: object) -> AuditEntry:
    values: dict[str, object] = {
        "actor": Actor.FOUNDER,
        "actor_id": FOUNDER,
        "action": "fact.added",
        "entity": "company_fact",
        "entity_id": uuid.uuid4(),
        "occurred_at": NOW,
    } | overrides
    return AuditEntry(**values)  # type: ignore[arg-type]


# Tenant base repository


def test_add_stamps_the_sessions_company(
    session: Session, companies: tuple[CompanyRow, CompanyRow]
) -> None:
    a, _ = companies
    row = TenantRepository(session, a.id).add(_fact())
    assert row.company_id == a.id


def test_add_accepts_a_row_already_stamped_for_the_same_company(
    session: Session, companies: tuple[CompanyRow, CompanyRow]
) -> None:
    a, _ = companies
    row = TenantRepository(session, a.id).add(_fact(company_id=a.id))
    assert row.company_id == a.id


def test_add_refuses_a_row_for_another_company(
    session: Session, companies: tuple[CompanyRow, CompanyRow]
) -> None:
    a, b = companies
    with pytest.raises(TenantError, match="another company"):
        TenantRepository(session, a.id).add(_fact(company_id=b.id))


def test_get_does_not_find_another_companys_row(
    session: Session, companies: tuple[CompanyRow, CompanyRow]
) -> None:
    a, b = companies
    row_b = TenantRepository(session, b.id).add(_fact())
    assert TenantRepository(session, a.id).get(CompanyFactRow, row_b.id) is None
    assert TenantRepository(session, b.id).get(CompanyFactRow, row_b.id) is row_b


def test_scoped_lists_only_the_companys_rows(
    session: Session, companies: tuple[CompanyRow, CompanyRow]
) -> None:
    a, b = companies
    TenantRepository(session, a.id).add(_fact())
    TenantRepository(session, b.id).add(_fact(value_text="ES"))
    repo = TenantRepository(session, a.id)
    rows = session.scalars(repo.scoped(CompanyFactRow)).all()
    assert [r.value_text for r in rows] == ["PT"]


def test_scoped_on_an_empty_company_is_empty(
    session: Session, companies: tuple[CompanyRow, CompanyRow]
) -> None:
    a, _ = companies
    repo = TenantRepository(session, a.id)
    assert session.scalars(repo.scoped(CompanyFactRow)).all() == []


def test_a_shared_table_is_refused(
    session: Session, companies: tuple[CompanyRow, CompanyRow]
) -> None:
    a, _ = companies
    repo = TenantRepository(session, a.id)
    with pytest.raises(TenantError, match="not a tenant table"):
        repo.scoped(FactDefinitionRow)
    with pytest.raises(TenantError, match="not a tenant table"):
        repo.add(FactDefinitionRow(key="x", value_type="text", hard_rule=False))


def test_nothing_is_committed_by_the_repository(
    engine: Engine, session: Session, companies: tuple[CompanyRow, CompanyRow]
) -> None:
    """The service owns the transaction: a rollback discards the change and its event."""
    a, _ = companies
    row = TenantRepository(session, a.id).add(_fact())
    AuditRepository(session, a.id).record(_entry(entity_id=row.id))
    session.rollback()
    with Session(engine) as other:
        assert other.scalar(select(func.count()).select_from(CompanyFactRow)) == 0
        assert other.scalar(select(func.count()).select_from(AuditEvent)) == 0


# Audit repository


def test_history_of_a_record_with_no_events_is_empty(session: Session) -> None:
    assert AuditRepository(session, None).history("opportunity", uuid.uuid4()) == []


def test_history_returns_entries_oldest_first_with_their_fields(
    session: Session, companies: tuple[CompanyRow, CompanyRow]
) -> None:
    a, _ = companies
    repo = AuditRepository(session, a.id)
    fact_id = uuid.uuid4()
    later = _entry(
        entity_id=fact_id,
        action="fact.approved",
        occurred_at=NOW + timedelta(minutes=5),
        before={"approved_at": None},
        after={"approved_at": "2026-11-11T12:05:00+00:00"},
        request_id="req-2",
    )
    earlier = _entry(entity_id=fact_id, action="fact.added", rule_version=None)
    repo.record(later)
    repo.record(earlier)
    assert repo.history("company_fact", fact_id) == [earlier, later]


def test_history_hides_another_companys_entries_but_shows_shared_ones(
    session: Session, companies: tuple[CompanyRow, CompanyRow]
) -> None:
    a, b = companies
    opportunity_id = uuid.uuid4()
    shared = _entry(
        actor=Actor.SYSTEM, actor_id=None, entity="opportunity", entity_id=opportunity_id
    )
    mine = _entry(entity="opportunity", entity_id=opportunity_id, action="decision.changed")
    theirs = _entry(entity="opportunity", entity_id=opportunity_id, action="decision.changed")
    AuditRepository(session, None).record(shared)
    AuditRepository(session, a.id).record(mine)
    AuditRepository(session, b.id).record(theirs)
    assert len(AuditRepository(session, a.id).history("opportunity", opportunity_id)) == 2
    assert AuditRepository(session, None).history("opportunity", opportunity_id) == [shared]


@pytest.mark.parametrize(
    ("before", "after", "allowed"),
    [
        (None, None, True),
        ({"value_boolean": True}, None, False),
        (None, {"value_date": "1995-02-28"}, False),
    ],
)
def test_founder_fact_entries_never_carry_values(
    session: Session,
    companies: tuple[CompanyRow, CompanyRow],
    before: dict[str, object] | None,
    after: dict[str, object] | None,
    allowed: bool,
) -> None:
    a, _ = companies
    entry = _entry(entity="founder_fact", action="founder_fact.deleted", before=before, after=after)
    repo = AuditRepository(session, a.id)
    if allowed:
        repo.record(entry)
    else:
        with pytest.raises(AuditError, match="never carry values"):
            repo.record(entry)


@pytest.mark.parametrize(
    ("actor", "actor_id", "allowed"),
    [
        (Actor.FOUNDER, FOUNDER, True),
        (Actor.FOUNDER, None, False),
        (Actor.SYSTEM, None, True),
        (Actor.JOB, FOUNDER, False),
    ],
)
def test_only_founder_entries_name_a_founder(
    session: Session, actor: Actor, actor_id: uuid.UUID | None, allowed: bool
) -> None:
    repo = AuditRepository(session, None)
    entry = _entry(actor=actor, actor_id=actor_id)
    if allowed:
        repo.record(entry)
    else:
        with pytest.raises(AuditError, match="names the founder"):
            repo.record(entry)
