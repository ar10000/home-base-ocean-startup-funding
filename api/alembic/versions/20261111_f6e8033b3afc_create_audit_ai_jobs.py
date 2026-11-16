"""create audit_events, ai_actions and job_runs

Revision ID: f6e8033b3afc
Revises: (first migration)
Created: 2026-11-11 12:06:09.636224+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6e8033b3afc"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_actions",
        sa.Column("task", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_hash", sa.String(), nullable=False),
        sa.Column("input_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_result", sa.String(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_eur", sa.Numeric(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("served_entity", sa.String(), nullable=True),
        sa.Column("served_entity_id", sa.Uuid(), nullable=True),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('succeeded', 'failed')", name=op.f("ck_ai_actions_status")),
        sa.CheckConstraint(
            "validation_result IN ('valid', 'invalid')",
            name=op.f("ck_ai_actions_validation_result"),
        ),
        sa.CheckConstraint("cost_eur >= 0", name=op.f("ck_ai_actions_cost_eur_not_negative")),
        sa.CheckConstraint(
            "input_tokens >= 0", name=op.f("ck_ai_actions_input_tokens_not_negative")
        ),
        sa.CheckConstraint("latency_ms >= 0", name=op.f("ck_ai_actions_latency_ms_not_negative")),
        sa.CheckConstraint(
            "output_tokens >= 0", name=op.f("ck_ai_actions_output_tokens_not_negative")
        ),
        sa.CheckConstraint("retry_count >= 0", name=op.f("ck_ai_actions_retry_count_not_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_actions")),
    )
    op.create_index(op.f("ix_ai_actions_company_id"), "ai_actions", ["company_id"], unique=False)
    op.create_index(
        "ix_ai_actions_served", "ai_actions", ["served_entity", "served_entity_id"], unique=False
    )
    op.create_table(
        "audit_events",
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity", sa.String(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rule_version", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor IN ('founder', 'system', 'job')", name=op.f("ck_audit_events_actor")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_company_id"), "audit_events", ["company_id"], unique=False
    )
    op.create_index("ix_audit_events_entity", "audit_events", ["entity", "entity_id"], unique=False)
    op.create_table(
        "job_runs",
        sa.Column("job", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'running') = (finished_at IS NULL)",
            name=op.f("ck_job_runs_finished_unless_running"),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name=op.f("ck_job_runs_status")
        ),
        sa.CheckConstraint("attempt >= 1", name=op.f("ck_job_runs_attempt_from_one")),
        sa.CheckConstraint("duration_ms >= 0", name=op.f("ck_job_runs_duration_ms_not_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_runs")),
    )
    op.create_index(op.f("ix_job_runs_started_at"), "job_runs", ["started_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_job_runs_started_at"), table_name="job_runs")
    op.drop_table("job_runs")
    op.drop_index("ix_audit_events_entity", table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_company_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_ai_actions_served", table_name="ai_actions")
    op.drop_index(op.f("ix_ai_actions_company_id"), table_name="ai_actions")
    op.drop_table("ai_actions")
