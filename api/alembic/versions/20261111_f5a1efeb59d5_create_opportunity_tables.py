"""create opportunity tables

Revision ID: f5a1efeb59d5
Revises: f6e8033b3afc
Created: 2026-11-11 12:19:22.835583+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f5a1efeb59d5"
down_revision: str | Sequence[str] | None = "f6e8033b3afc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("seed_key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("funder", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("types", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("timezone", sa.String(), nullable=True),
        sa.Column("opening", sa.Date(), nullable=True),
        sa.Column("expected_month", sa.Date(), nullable=True),
        sa.Column("questions_known", sa.Boolean(), nullable=False),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "scope IN ('blue_specific', 'all_sectors')", name=op.f("ck_opportunities_scope")
        ),
        sa.CheckConstraint(
            "types <@ ARRAY['grant', 'accelerator', 'testbed_or_pilot', 'procurement_challenge', 'prize', 'investor_programme']::text[]",
            name=op.f("ck_opportunities_types_known"),
        ),
        sa.CheckConstraint(
            "cardinality(types) >= 1", name=op.f("ck_opportunities_at_least_one_type")
        ),
        sa.CheckConstraint(
            "deadline IS NULL OR timezone IS NOT NULL",
            name=op.f("ck_opportunities_deadline_has_timezone"),
        ),
        sa.CheckConstraint(
            "expected_month IS NULL OR extract(day FROM expected_month) = 1",
            name=op.f("ck_opportunities_expected_month_is_first_day"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunities")),
        sa.UniqueConstraint("seed_key", name=op.f("uq_opportunities_seed_key")),
    )
    op.create_table(
        "evidence",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("dated", sa.Date(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('previous_edition', 'announcement')", name=op.f("ck_evidence_kind")
        ),
        sa.CheckConstraint("left(url, 8) = 'https://'", name=op.f("ck_evidence_url_is_https")),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_evidence_opportunity_id_opportunities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
    )
    op.create_index(
        op.f("ix_evidence_opportunity_id"), "evidence", ["opportunity_id"], unique=False
    )
    op.create_table(
        "questions",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("required_facts", postgresql.ARRAY(sa.Text()), nullable=False),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("position >= 0", name=op.f("ck_questions_position_not_negative")),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_questions_opportunity_id_opportunities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
    )
    op.create_index(
        op.f("ix_questions_opportunity_id"), "questions", ["opportunity_id"], unique=False
    )
    op.create_table(
        "requirements",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("hard", sa.Boolean(), nullable=False),
        sa.Column("quote", sa.String(), nullable=False),
        sa.Column("fact", sa.String(), nullable=True),
        sa.Column("operator", sa.String(), nullable=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("criterion", sa.String(), nullable=True),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "operator IS NULL OR operator IN ('equals', 'one_of', 'not_one_of', 'at_least', 'at_most')",
            name=op.f("ck_requirements_operator_known"),
        ),
        sa.CheckConstraint(
            "(hard AND fact IS NOT NULL AND operator IS NOT NULL AND criterion IS NULL) OR (NOT hard AND fact IS NULL AND operator IS NULL AND criterion IS NOT NULL)",
            name=op.f("ck_requirements_hard_has_fact_soft_has_criterion"),
        ),
        sa.CheckConstraint(
            "length(btrim(quote)) > 0", name=op.f("ck_requirements_quote_not_blank")
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_requirements_position_not_negative")),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_requirements_opportunity_id_opportunities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirements")),
    )
    op.create_index(
        op.f("ix_requirements_opportunity_id"), "requirements", ["opportunity_id"], unique=False
    )
    op.create_table(
        "sources",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("retrieved_on", sa.Date(), nullable=False),
        sa.Column("verified_on", sa.Date(), nullable=False),
        sa.Column("verified_by", sa.String(), nullable=False),
        sa.Column("original_text", sa.String(), nullable=True),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("left(url, 8) = 'https://'", name=op.f("ck_sources_url_is_https")),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_sources_opportunity_id_opportunities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
    )
    op.create_index(op.f("ix_sources_opportunity_id"), "sources", ["opportunity_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sources_opportunity_id"), table_name="sources")
    op.drop_table("sources")
    op.drop_index(op.f("ix_requirements_opportunity_id"), table_name="requirements")
    op.drop_table("requirements")
    op.drop_index(op.f("ix_questions_opportunity_id"), table_name="questions")
    op.drop_table("questions")
    op.drop_index(op.f("ix_evidence_opportunity_id"), table_name="evidence")
    op.drop_table("evidence")
    op.drop_table("opportunities")
