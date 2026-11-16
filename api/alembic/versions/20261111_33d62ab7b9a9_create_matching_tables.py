"""create matching tables

Revision ID: 33d62ab7b9a9
Revises: bf183e109344
Created: 2026-11-11 12:47:14.544038+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "33d62ab7b9a9"
down_revision: str | Sequence[str] | None = "bf183e109344"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
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
            "decision IN ('none', 'pursuing', 'later', 'not_for_us')",
            name=op.f("ck_decisions_decision"),
        ),
        sa.CheckConstraint(
            "reason IS NULL OR decision = 'not_for_us'",
            name=op.f("ck_decisions_reason_only_with_not_for_us"),
        ),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN ('not_relevant', 'too_early', 'too_much_work', 'other')",
            name=op.f("ck_decisions_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_decisions_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_decisions_opportunity_id_opportunities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decisions")),
    )
    op.create_index(
        "ix_decisions_company_opportunity",
        "decisions",
        ["company_id", "opportunity_id", "changed_at"],
        unique=False,
    )
    op.create_table(
        "matches",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("fit_status", sa.String(), nullable=False),
        sa.Column("few_explicit_rules", sa.Boolean(), nullable=False),
        sa.Column("rule_version", sa.String(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
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
            "fit_status IN ('confirmed', 'possible', 'not_eligible')",
            name=op.f("ck_matches_fit_status"),
        ),
        sa.CheckConstraint(
            "length(btrim(rule_version)) > 0", name=op.f("ck_matches_rule_version_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_matches_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_matches_opportunity_id_opportunities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_matches")),
        sa.UniqueConstraint("id", "company_id", name="uq_matches_id_company"),
    )
    op.create_index(op.f("ix_matches_company_id"), "matches", ["company_id"], unique=False)
    op.create_index(op.f("ix_matches_opportunity_id"), "matches", ["opportunity_id"], unique=False)
    op.create_index(
        "uq_matches_one_current",
        "matches",
        ["company_id", "opportunity_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_table(
        "requirement_results",
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("result", sa.String(), nullable=False),
        sa.Column("fact_key", sa.String(), nullable=True),
        sa.Column("fact_version_id", sa.Uuid(), nullable=True),
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
            "result IN ('pass', 'fail', 'unknown', 'ai_judgement')",
            name=op.f("ck_requirement_results_result"),
        ),
        sa.CheckConstraint(
            "fact_version_id IS NULL OR fact_key IS NOT NULL",
            name=op.f("ck_requirement_results_fact_version_has_key"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_requirement_results_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["fact_version_id", "company_id"],
            ["company_facts.id", "company_facts.company_id"],
            name="fk_requirement_results_fact_same_company",
        ),
        sa.ForeignKeyConstraint(
            ["match_id", "company_id"],
            ["matches.id", "matches.company_id"],
            name="fk_requirement_results_match_same_company",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_requirement_results_requirement_id_requirements"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement_results")),
        sa.UniqueConstraint("match_id", "requirement_id", name="uq_requirement_results_match_req"),
    )
    op.create_index(
        op.f("ix_requirement_results_match_id"), "requirement_results", ["match_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_requirement_results_match_id"), table_name="requirement_results")
    op.drop_table("requirement_results")
    op.drop_index(
        "uq_matches_one_current",
        table_name="matches",
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.drop_index(op.f("ix_matches_opportunity_id"), table_name="matches")
    op.drop_index(op.f("ix_matches_company_id"), table_name="matches")
    op.drop_table("matches")
    op.drop_index("ix_decisions_company_opportunity", table_name="decisions")
    op.drop_table("decisions")
