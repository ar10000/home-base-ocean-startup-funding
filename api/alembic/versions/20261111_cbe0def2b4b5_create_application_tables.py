"""create application tables

Revision ID: cbe0def2b4b5
Revises: 33d62ab7b9a9
Created: 2026-11-11 12:51:30.615573+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cbe0def2b4b5"
down_revision: str | Sequence[str] | None = "33d62ab7b9a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            "submitted_at IS NULL OR submitted_at >= started_at",
            name=op.f("ck_applications_submitted_after_started"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_applications_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_applications_opportunity_id_opportunities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint("id", "company_id", name="uq_applications_id_company"),
    )
    op.create_index(
        op.f("ix_applications_company_id"), "applications", ["company_id"], unique=False
    )
    op.create_index(
        "uq_applications_one_open",
        "applications",
        ["company_id", "opportunity_id"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_table(
        "answers",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("current_text", sa.String(), nullable=False),
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
            "state IN ('ai_draft', 'edited', 'approved')", name=op.f("ck_answers_state")
        ),
        sa.ForeignKeyConstraint(
            ["application_id", "company_id"],
            ["applications.id", "applications.company_id"],
            name="fk_answers_application_same_company",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_answers_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.id"], name=op.f("fk_answers_question_id_questions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answers")),
        sa.UniqueConstraint(
            "application_id", "question_id", name="uq_answers_application_question"
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_answers_id_company"),
    )
    op.create_index(op.f("ix_answers_application_id"), "answers", ["application_id"], unique=False)
    op.create_table(
        "answer_versions",
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("ai_action_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
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
            "(kind = 'ai_draft') = (ai_action_id IS NOT NULL)",
            name=op.f("ck_answer_versions_ai_draft_has_ai_action"),
        ),
        sa.CheckConstraint(
            "(kind = 'approved') = (approved_by IS NOT NULL)",
            name=op.f("ck_answer_versions_approval_has_approver"),
        ),
        sa.CheckConstraint(
            "kind IN ('ai_draft', 'approved')", name=op.f("ck_answer_versions_kind")
        ),
        sa.ForeignKeyConstraint(
            ["ai_action_id"],
            ["ai_actions.id"],
            name=op.f("fk_answer_versions_ai_action_id_ai_actions"),
        ),
        sa.ForeignKeyConstraint(
            ["answer_id", "company_id"],
            ["answers.id", "answers.company_id"],
            name="fk_answer_versions_answer_same_company",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_answer_versions_company_id_companies")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_versions")),
        sa.UniqueConstraint("id", "company_id", name="uq_answer_versions_id_company"),
    )
    op.create_index(
        op.f("ix_answer_versions_answer_id"), "answer_versions", ["answer_id"], unique=False
    )
    op.create_table(
        "answer_version_facts",
        sa.Column("answer_version_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("fact_version_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["answer_version_id", "company_id"],
            ["answer_versions.id", "answer_versions.company_id"],
            name="fk_answer_version_facts_version_same_company",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_answer_version_facts_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["fact_version_id", "company_id"],
            ["company_facts.id", "company_facts.company_id"],
            name="fk_answer_version_facts_fact_same_company",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_version_facts")),
        sa.UniqueConstraint(
            "answer_version_id", "fact_version_id", name="uq_answer_version_facts_pair"
        ),
    )
    op.create_index(
        op.f("ix_answer_version_facts_answer_version_id"),
        "answer_version_facts",
        ["answer_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_answer_version_facts_answer_version_id"), table_name="answer_version_facts"
    )
    op.drop_table("answer_version_facts")
    op.drop_index(op.f("ix_answer_versions_answer_id"), table_name="answer_versions")
    op.drop_table("answer_versions")
    op.drop_index(op.f("ix_answers_application_id"), table_name="answers")
    op.drop_table("answers")
    op.drop_index(
        "uq_applications_one_open",
        table_name="applications",
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.drop_index(op.f("ix_applications_company_id"), table_name="applications")
    op.drop_table("applications")
