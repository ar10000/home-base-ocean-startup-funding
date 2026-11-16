"""create company tables

Revision ID: bf183e109344
Revises: f5a1efeb59d5
Created: 2026-11-11 12:29:51.278464+00:00
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bf183e109344"
down_revision: str | Sequence[str] | None = "f5a1efeb59d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("name", sa.String(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )
    op.create_table(
        "fact_definitions",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value_type", sa.String(), nullable=False),
        sa.Column("hard_rule", sa.Boolean(), nullable=False),
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
            "key ~ '^[a-z][a-z0-9_]*$'", name=op.f("ck_fact_definitions_key_is_snake_case")
        ),
        sa.CheckConstraint(
            "value_type IN ('text', 'integer', 'boolean')",
            name=op.f("ck_fact_definitions_value_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_definitions")),
        sa.UniqueConstraint("key", "value_type", name="uq_fact_definitions_key_value_type"),
        sa.UniqueConstraint("key", name=op.f("uq_fact_definitions_key")),
    )
    # D-47: the seven hard-rule fact keys (config.HARD_RULE_FACT_KEYS; spec: Requirement
    # types). Types follow matching's FactValue: text, or whole numbers for counts and TRL.
    # Fixed IDs, so the migration gives every environment the same rows.
    definitions = sa.table(
        "fact_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("value_type", sa.String()),
        sa.column("hard_rule", sa.Boolean()),
    )
    op.bulk_insert(
        definitions,
        [
            {"id": uuid.UUID(i), "key": k, "value_type": t, "hard_rule": True}
            for i, k, t in [
                ("01a1ca96-21b1-77ad-b540-e61c8b12fb16", "applicant_form", "text"),
                ("01a1ca96-21b2-7a63-88da-2ba443ada61d", "company_age", "integer"),
                ("01a1ca96-21b3-79d7-aabd-d79fdf763cad", "country", "text"),
                ("01a1ca96-21b4-7c02-a371-199b1750c553", "legal_form", "text"),
                ("01a1ca96-21b5-7c0b-8a41-aeee130138c0", "sector", "text"),
                ("01a1ca96-21b6-7eb5-957d-866f6b5a1d71", "team_size", "integer"),
                ("01a1ca96-21b7-7f6e-81ec-d7f4429cc2d7", "trl", "integer"),
            ]
        ],
    )
    op.create_table(
        "company_facts",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value_type", sa.String(), nullable=False),
        sa.Column("value_text", sa.String(), nullable=True),
        sa.Column("value_integer", sa.Integer(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
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
            "(value_type = 'text' AND value_text IS NOT NULL AND value_integer IS NULL AND value_boolean IS NULL) OR (value_type = 'integer' AND value_integer IS NOT NULL AND value_text IS NULL AND value_boolean IS NULL) OR (value_type = 'boolean' AND value_boolean IS NOT NULL AND value_text IS NULL AND value_integer IS NULL)",
            name=op.f("ck_company_facts_value_matches_type"),
        ),
        sa.CheckConstraint(
            "label IN ('sourced', 'user_provided', 'ai_suggested', 'unverified')",
            name=op.f("ck_company_facts_label"),
        ),
        sa.CheckConstraint(
            "(approved_at IS NULL) = (approved_by IS NULL)",
            name=op.f("ck_company_facts_approval_paired"),
        ),
        sa.CheckConstraint(
            "value_text IS NULL OR length(btrim(value_text)) > 0",
            name=op.f("ck_company_facts_text_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_company_facts_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["key", "value_type"],
            ["fact_definitions.key", "fact_definitions.value_type"],
            name="fk_company_facts_definition",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_facts")),
        sa.UniqueConstraint("id", "company_id", name="uq_company_facts_id_company"),
    )
    op.create_index(
        op.f("ix_company_facts_company_id"), "company_facts", ["company_id"], unique=False
    )
    op.create_index(
        "uq_company_facts_one_current",
        "company_facts",
        ["company_id", "key"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_table(
        "founder_facts",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
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
            "(key = 'youngest_founder_birth_date' AND value_date IS NOT NULL AND value_boolean IS NULL) OR (key = 'woman_founder' AND value_boolean IS NOT NULL AND value_date IS NULL) OR (key = 'woman_ceo' AND value_boolean IS NOT NULL AND value_date IS NULL)",
            name=op.f("ck_founder_facts_value_matches_key"),
        ),
        sa.CheckConstraint(
            "key IN ('youngest_founder_birth_date', 'woman_founder', 'woman_ceo')",
            name=op.f("ck_founder_facts_key"),
        ),
        sa.CheckConstraint(
            "(approved_at IS NULL) = (approved_by IS NULL)",
            name=op.f("ck_founder_facts_approval_paired"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_founder_facts_company_id_companies")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_founder_facts")),
        sa.UniqueConstraint("company_id", "key", name="uq_founder_facts_company_key"),
    )
    op.create_index(
        op.f("ix_founder_facts_company_id"), "founder_facts", ["company_id"], unique=False
    )
    op.create_table(
        "intents",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
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
            ["company_id"], ["companies.id"], name=op.f("fk_intents_company_id_companies")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intents")),
        sa.UniqueConstraint("id", "company_id", name="uq_intents_id_company"),
    )
    op.create_index(
        "ix_intents_company_recorded", "intents", ["company_id", "recorded_at"], unique=False
    )
    op.create_table(
        "milestones",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("milestone", sa.String(), nullable=False),
        sa.Column("reached_at", sa.DateTime(timezone=True), nullable=False),
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
            "milestone IN ('first_fact_approved', 'hard_rule_facts_filled', 'first_answer_approved', 'first_application_ready', 'first_application_submitted')",
            name=op.f("ck_milestones_milestone"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_milestones_company_id_companies")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestones")),
        sa.UniqueConstraint("company_id", "milestone", name="uq_milestones_company_milestone"),
    )
    op.create_index(op.f("ix_milestones_company_id"), "milestones", ["company_id"], unique=False)
    op.create_table(
        "intent_goals",
        sa.Column("intent_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("goal", sa.String(), nullable=False),
        sa.Column("goal_window", sa.String(), nullable=False),
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
            "goal IN ('pilot_or_test_site', 'non_dilutive_funding', 'accelerator_place', 'first_customers', 'investment')",
            name=op.f("ck_intent_goals_goal"),
        ),
        sa.CheckConstraint(
            "goal_window IN ('now', 'soon', 'later')", name=op.f("ck_intent_goals_goal_window")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_intent_goals_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["intent_id", "company_id"],
            ["intents.id", "intents.company_id"],
            name="fk_intent_goals_intent_same_company",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intent_goals")),
        sa.UniqueConstraint("intent_id", "goal", name="uq_intent_goals_intent_goal"),
    )
    op.create_index(op.f("ix_intent_goals_intent_id"), "intent_goals", ["intent_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_intent_goals_intent_id"), table_name="intent_goals")
    op.drop_table("intent_goals")
    op.drop_index(op.f("ix_milestones_company_id"), table_name="milestones")
    op.drop_table("milestones")
    op.drop_index("ix_intents_company_recorded", table_name="intents")
    op.drop_table("intents")
    op.drop_index(op.f("ix_founder_facts_company_id"), table_name="founder_facts")
    op.drop_table("founder_facts")
    op.drop_index(
        "uq_company_facts_one_current",
        table_name="company_facts",
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.drop_index(op.f("ix_company_facts_company_id"), table_name="company_facts")
    op.drop_table("company_facts")
    op.drop_table("fact_definitions")
    op.drop_table("companies")
