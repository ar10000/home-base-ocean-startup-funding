# ruff: noqa: E501  (raw SQL statements read best on one line)
"""Row-level security and the app role, on a real Postgres (handbook section 13, layer 2).

Each test switches to home_base_app with a company set, as every API request will, and
then queries without any company filter: the database alone must keep companies apart,
keep the audit trail append-only, and keep the shared opportunity data read-only.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from home_base.modules.audit.models import AuditEvent
from home_base.modules.companies.models import CompanyFactRow, CompanyRow, FounderFactRow
from home_base.modules.opportunities.models import OpportunityRow

pytestmark = pytest.mark.integration

AT = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


@dataclass
class World:
    a: uuid.UUID
    b: uuid.UUID
    fact_b: uuid.UUID


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def world(session: Session) -> World:
    """Two companies with a fact each, an audit event each and a shared one, written as the
    owner (as the services do before the app role is switched on)."""
    a, b = CompanyRow(name="A"), CompanyRow(name="B")
    session.add_all([a, b])
    session.flush()
    facts = {
        c.id: CompanyFactRow(
            company_id=c.id, key="country", value_type="text", value_text=v, label="sourced"
        )
        for c, v in ((a, "PT"), (b, "ES"))
    }
    session.add_all(facts.values())
    for company in (a.id, b.id, None):
        session.add(
            AuditEvent(
                actor="system",
                company_id=company,
                action="x",
                entity="e",
                entity_id=uuid.uuid4(),
                occurred_at=AT,
            )
        )
    session.add(FounderFactRow(company_id=a.id, key="woman_ceo", value_boolean=True))
    session.flush()
    return World(a.id, b.id, facts[b.id].id)


def _as_app(session: Session, company: uuid.UUID | None) -> None:
    session.execute(text("SET LOCAL ROLE home_base_app"))
    if company is not None:
        session.execute(text("SELECT set_config('app.company_id', :c, true)"), {"c": str(company)})


def _count(session: Session, sql: str) -> int:
    return int(session.execute(text(sql)).scalar_one())


def _refused(session: Session, sql: str, **params: object) -> bool:
    savepoint = session.begin_nested()
    try:
        session.execute(text(sql), params)
    except DBAPIError:
        savepoint.rollback()
        return True
    savepoint.rollback()
    return False


def test_a_company_sees_only_its_own_rows_with_no_filter(session: Session, world: World) -> None:
    _as_app(session, world.a)
    assert session.execute(text("SELECT value_text FROM company_facts")).scalars().all() == ["PT"]
    assert _count(session, "SELECT count(*) FROM companies") == 1


def test_without_a_company_set_nothing_is_visible(session: Session, world: World) -> None:
    _as_app(session, None)
    assert _count(session, "SELECT count(*) FROM company_facts") == 0
    assert _count(session, "SELECT count(*) FROM companies") == 0


def test_an_empty_company_setting_sees_nothing(session: Session, world: World) -> None:
    """After a request the setting is cleared to empty; that must mean no company, not an error."""
    _as_app(session, None)
    session.execute(text("SELECT set_config('app.company_id', '', true)"))
    assert _count(session, "SELECT count(*) FROM company_facts") == 0


def test_another_companys_row_cannot_be_written(session: Session, world: World) -> None:
    _as_app(session, world.a)
    insert = (
        "INSERT INTO company_facts (id, company_id, key, value_type, value_text, label, created_at, updated_at)"
        " VALUES (gen_random_uuid(), :b, 'sector', 'text', 'x', 'sourced', now(), now())"
    )
    assert _refused(session, insert, b=str(world.b))  # the policy's WITH CHECK
    changed = session.execute(
        text("UPDATE company_facts SET source = 'mine now' WHERE id = :id"),
        {"id": str(world.fact_b)},
    )
    assert changed.rowcount == 0  # invisible, so untouched  # type: ignore[attr-defined]


def test_the_audit_trail_is_append_only_for_the_app(session: Session, world: World) -> None:
    _as_app(session, world.a)
    assert _count(session, "SELECT count(*) FROM audit_events") == 2  # its own and the shared one
    assert not _refused(
        session,
        "INSERT INTO audit_events (id, actor, company_id, action, entity, entity_id, occurred_at, created_at, updated_at)"
        " VALUES (gen_random_uuid(), 'founder', :a, 'y', 'e', gen_random_uuid(), now(), now(), now())",
        a=str(world.a),
    )
    assert _refused(session, "UPDATE audit_events SET action = 'rewritten'")
    assert _refused(session, "DELETE FROM audit_events")


def test_the_app_cannot_write_a_shared_audit_event(session: Session, world: World) -> None:
    _as_app(session, world.a)
    assert _refused(
        session,
        "INSERT INTO audit_events (id, actor, company_id, action, entity, entity_id, occurred_at, created_at, updated_at)"
        " VALUES (gen_random_uuid(), 'system', NULL, 'y', 'e', gen_random_uuid(), now(), now(), now())",
    )


def test_shared_opportunity_data_is_read_only_for_the_app(session: Session, world: World) -> None:
    session.add(
        OpportunityRow(
            seed_key=f"k-{uuid.uuid4()}",
            name="N",
            funder="F",
            scope="blue_specific",
            types=["grant"],
            questions_known=False,
        )
    )
    session.flush()
    _as_app(session, world.a)
    assert _count(session, "SELECT count(*) FROM opportunities") == 1
    assert _refused(session, "UPDATE opportunities SET name = 'changed'")
    assert _refused(session, "DELETE FROM opportunities")


def test_only_founder_facts_can_be_deleted_by_the_app(session: Session, world: World) -> None:
    _as_app(session, world.a)
    deleted = session.execute(text("DELETE FROM founder_facts"))
    assert deleted.rowcount == 1  # type: ignore[attr-defined]
    assert _refused(session, "DELETE FROM company_facts")


def test_accounts_are_not_readable_by_the_app(session: Session, world: World) -> None:
    """Users and memberships are read to sign a request in, before switching role."""
    _as_app(session, world.a)
    assert _refused(session, "SELECT count(*) FROM users")
    assert _refused(session, "SELECT count(*) FROM memberships")


def test_a_membership_role_is_from_the_fixed_list(session: Session, world: World) -> None:
    session.execute(
        text(
            "INSERT INTO users (id, keycloak_subject, created_at, updated_at) VALUES (gen_random_uuid(), 'sub-1', now(), now())"
        )
    )
    user = session.execute(
        text("SELECT id FROM users WHERE keycloak_subject = 'sub-1'")
    ).scalar_one()
    ok = "INSERT INTO memberships (id, user_id, company_id, role, created_at, updated_at) VALUES (gen_random_uuid(), :u, :c, :r, now(), now())"
    assert not _refused(session, ok, u=user, c=str(world.a), r="founder")
    assert _refused(session, ok, u=user, c=str(world.b), r="admin")
