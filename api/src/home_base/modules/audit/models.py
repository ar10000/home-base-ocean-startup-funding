"""Audit trail and AI action log tables (handbook section 12).

Both are append-only records. The database role that enforces "no UPDATE or DELETE"
on audit_events comes with row-level security (plan, week 2 step 6).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Index, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from home_base.core.db import Base, Record, one_of

ACTORS = ("founder", "system", "job")
VALIDATION_RESULTS = ("valid", "invalid")
AI_ACTION_STATUSES = ("succeeded", "failed")


class AuditEvent(Record, Base):
    """One row per state change: who changed what, when, from what to what."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(one_of("actor", ACTORS), name="actor"),
        Index("ix_audit_events_entity", "entity", "entity_id"),
    )

    actor: Mapped[str]
    actor_id: Mapped[uuid.UUID | None]  # the founder's user ID; null for system and job
    company_id: Mapped[uuid.UUID | None] = mapped_column(index=True)  # null for shared records
    action: Mapped[str]
    entity: Mapped[str]
    entity_id: Mapped[uuid.UUID]
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # changed fields only
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rule_version: Mapped[str | None]  # when a rule decided it
    request_id: Mapped[str | None]
    occurred_at: Mapped[datetime]


class AiAction(Record, Base):
    """One row per model call: what the AI received, returned and was validated against."""

    __tablename__ = "ai_actions"
    __table_args__ = (
        CheckConstraint(one_of("validation_result", VALIDATION_RESULTS), name="validation_result"),
        CheckConstraint(one_of("status", AI_ACTION_STATUSES), name="status"),
        CheckConstraint("retry_count >= 0", name="retry_count_not_negative"),
        CheckConstraint("input_tokens >= 0", name="input_tokens_not_negative"),
        CheckConstraint("output_tokens >= 0", name="output_tokens_not_negative"),
        CheckConstraint("cost_eur >= 0", name="cost_eur_not_negative"),
        CheckConstraint("latency_ms >= 0", name="latency_ms_not_negative"),
        Index("ix_ai_actions_served", "served_entity", "served_entity_id"),
    )

    task: Mapped[str]
    prompt_version: Mapped[str]
    model: Mapped[str]
    input_hash: Mapped[str]
    input_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # [{entity, id}], never text
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # the validated output only
    validation_result: Mapped[str]
    retry_count: Mapped[int]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    # Unscaled numeric: never rounded in storage, only at display or export.
    cost_eur: Mapped[Decimal] = mapped_column(Numeric)
    latency_ms: Mapped[int]
    status: Mapped[str]
    served_entity: Mapped[str | None]  # the record it served
    served_entity_id: Mapped[uuid.UUID | None]
    company_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    request_id: Mapped[str | None]
