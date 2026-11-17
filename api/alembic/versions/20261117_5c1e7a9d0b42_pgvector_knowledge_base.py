"""pgvector, the knowledge base facts, and the embedding tables

ADR-009 and D-80. Adds the `vector` extension; the four knowledge-base text facts
(config.KNOWLEDGE_FACT_KEYS, not hard-rule facts); `fact_embeddings`, a tenant table
under row-level security like company_facts; and `source_passages`, shared call text
read-only for the API like the other opportunity data. Embeddings are 1024 numbers
(config.EMBEDDING_DIMENSIONS, mistral-embed); another size needs a new migration.

Revision ID: 5c1e7a9d0b42
Revises: 7af87ad58066
Created: 2026-11-17 10:05:00.000000+00:00
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "5c1e7a9d0b42"
down_revision: str | Sequence[str] | None = "7af87ad58066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "home_base_app"
SETTING = "NULLIF(current_setting('app.company_id', true), '')::uuid"
DIMENSIONS = 1024  # config.EMBEDDING_DIMENSIONS as it stood when this was written
KNOWLEDGE = [  # D-80, fixed IDs so every environment gets the same rows
    ("01a1e8f1-e319-7a9d-9787-58ba22e0b6db", "description"),
    ("01a1e8f1-e31a-770f-8367-ece48eb98887", "impact"),
    ("01a1e8f1-e31b-75cc-96d3-11aa49047b6a", "team"),
    ("01a1e8f1-e31c-7a6d-a92d-f5318aeb53e6", "traction"),
]


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

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
            {"id": uuid.UUID(i), "key": k, "value_type": "text", "hard_rule": False}
            for i, k in KNOWLEDGE
        ],
    )

    op.create_table(
        "fact_embeddings",
        *_timestamps(),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("fact_version_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("embedding", Vector(DIMENSIONS), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_fact_embeddings_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["fact_version_id", "company_id"],
            ["company_facts.id", "company_facts.company_id"],
            name="fk_fact_embeddings_fact_version",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_embeddings")),
        sa.UniqueConstraint("fact_version_id", "model", name="uq_fact_embeddings_version_model"),
    )
    op.create_index(
        op.f("ix_fact_embeddings_company_id"), "fact_embeddings", ["company_id"], unique=False
    )

    op.create_table(
        "source_passages",
        *_timestamps(),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("embedding", Vector(DIMENSIONS), nullable=False),
        sa.CheckConstraint("position >= 0", name=op.f("ck_source_passages_position_not_negative")),
        sa.CheckConstraint(
            "length(btrim(text)) > 0", name=op.f("ck_source_passages_text_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_source_passages_source_id_sources")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_passages")),
        sa.UniqueConstraint("source_id", "model", "position", name="uq_source_passages_position"),
    )
    op.create_index(
        op.f("ix_source_passages_source_id"), "source_passages", ["source_id"], unique=False
    )

    # D-63 for the new tables: a company's embeddings only its own; passages read-only.
    op.execute(f"GRANT SELECT, INSERT ON fact_embeddings TO {APP_ROLE}")
    op.execute("ALTER TABLE fact_embeddings ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_only ON fact_embeddings TO {APP_ROLE} "
        f"USING (company_id = {SETTING}) WITH CHECK (company_id = {SETTING})"
    )
    op.execute(f"GRANT SELECT ON source_passages TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE ALL ON source_passages FROM {APP_ROLE}")
    op.execute("DROP POLICY IF EXISTS tenant_only ON fact_embeddings")
    op.execute(f"REVOKE ALL ON fact_embeddings FROM {APP_ROLE}")
    op.drop_index(op.f("ix_source_passages_source_id"), table_name="source_passages")
    op.drop_table("source_passages")
    op.drop_index(op.f("ix_fact_embeddings_company_id"), table_name="fact_embeddings")
    op.drop_table("fact_embeddings")
    op.execute(
        "DELETE FROM fact_definitions WHERE key IN " f"({', '.join(repr(k) for _, k in KNOWLEDGE)})"
    )
    # The extension stays: dropping it would fail if anything else came to use it.
