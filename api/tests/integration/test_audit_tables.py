"""audit_events, ai_actions and job_runs on a real Postgres: empty after the migration,
and every database check holds at its boundary (handbook sections 11 and 12)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from home_base.core.db import Record
from home_base.jobs.models import JobRun
from home_base.modules.audit.models import AiAction, AuditEvent

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


def _audit(**overrides: Any) -> AuditEvent:
    values: dict[str, Any] = {
        "actor": "system",
        "action": "opportunity.verified",
        "entity": "opportunity",
        "entity_id": uuid.uuid4(),
        "occurred_at": NOW,
    } | overrides
    return AuditEvent(**values)


def _ai(**overrides: Any) -> AiAction:
    values: dict[str, Any] = {
        "task": "extract_requirements",
        "prompt_version": "v1",
        "model": "test-model",
        "input_hash": "sha256:0",
        "input_refs": [{"entity": "source", "id": str(uuid.uuid4())}],
        "validation_result": "valid",
        "retry_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_eur": Decimal(0),
        "latency_ms": 0,
        "status": "succeeded",
    } | overrides
    return AiAction(**values)


def _job(**overrides: Any) -> JobRun:
    values: dict[str, Any] = {
        "job": "recheck_due",
        "status": "succeeded",
        "attempt": 1,
        "started_at": NOW,
        "finished_at": NOW,
        "duration_ms": 0,
    } | overrides
    return JobRun(**values)


def _saves(session: Session, row: Record) -> bool:
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return False
    session.rollback()
    return True


@pytest.mark.parametrize("model", [AuditEvent, AiAction, JobRun])
def test_tables_are_empty_after_the_migration(session: Session, model: type[Record]) -> None:
    assert session.scalar(select(func.count()).select_from(model)) == 0


def test_every_row_gets_a_uuid7_id_and_utc_timestamps(session: Session) -> None:
    row = _audit()
    session.add(row)
    session.flush()
    session.refresh(row)
    assert row.id.version == 7
    assert row.created_at.utcoffset() is not None
    assert row.updated_at >= row.created_at


@pytest.mark.parametrize(("actor", "saved"), [("founder", True), ("job", True), ("admin", False)])
def test_audit_actor_is_one_of_the_three(session: Session, actor: str, saved: bool) -> None:
    assert _saves(session, _audit(actor=actor)) is saved


def test_audit_before_and_after_keep_changed_fields_as_json(session: Session) -> None:
    row = _audit(before={"decision": "later"}, after={"decision": "pursuing"})
    session.add(row)
    session.flush()
    session.expire(row)
    assert row.after == {"decision": "pursuing"}


@pytest.mark.parametrize(
    "field", ["retry_count", "input_tokens", "output_tokens", "latency_ms", "cost_eur"]
)
@pytest.mark.parametrize(("value", "saved"), [(0, True), (-1, False)])
def test_ai_action_counts_and_cost_are_not_negative(
    session: Session, field: str, value: int, saved: bool
) -> None:
    assert _saves(session, _ai(**{field: value})) is saved


@pytest.mark.parametrize(
    ("field", "value"), [("validation_result", "partial"), ("status", "timed_out")]
)
def test_ai_action_enums_are_checked(session: Session, field: str, value: str) -> None:
    assert _saves(session, _ai(**{field: value})) is False


def test_ai_action_cost_is_stored_unrounded(session: Session) -> None:
    """Money is rounded at display or export, never in storage."""
    cost = Decimal("0.000012345678901234")
    row = _ai(cost_eur=cost)
    session.add(row)
    session.flush()
    session.expire(row)
    assert row.cost_eur == cost


@pytest.mark.parametrize(("attempt", "saved"), [(1, True), (0, False)])
def test_job_attempt_counts_from_one(session: Session, attempt: int, saved: bool) -> None:
    assert _saves(session, _job(attempt=attempt)) is saved


@pytest.mark.parametrize(
    ("status", "finished_at", "saved"),
    [
        ("running", None, True),
        ("running", NOW, False),
        ("succeeded", NOW, True),
        ("succeeded", None, False),
        ("failed", None, False),
        ("cancelled", NOW, False),
    ],
)
def test_job_is_finished_exactly_when_not_running(
    session: Session, status: str, finished_at: datetime | None, saved: bool
) -> None:
    row = _job(status=status, finished_at=finished_at, duration_ms=None)
    assert _saves(session, row) is saved


@pytest.mark.parametrize(("duration_ms", "saved"), [(0, True), (-1, False)])
def test_job_duration_is_not_negative(session: Session, duration_ms: int, saved: bool) -> None:
    assert _saves(session, _job(duration_ms=duration_ms)) is saved
