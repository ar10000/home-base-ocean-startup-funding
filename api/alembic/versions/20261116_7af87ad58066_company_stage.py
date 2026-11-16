"""company stage

The founder's journey stage on Today (spec: Today > Stage; D-58, D-78). Optional: None
until the founder chooses one. The database checks it is one of config.STAGES, as the list
stood when this migration was written (a later change to the list needs its own migration).
The API's role may update only the stage (and updated_at) of its own company: row-level
security already limits it to that row (D-63); it may not rename or archive a company.

Revision ID: 7af87ad58066
Revises: ae9669b7f4c1
Created: 2026-11-16 15:49:12.359541+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7af87ad58066"
down_revision: str | Sequence[str] | None = "ae9669b7f4c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("stage", sa.String(), nullable=True))
    op.create_check_constraint(
        op.f("ck_companies_stage"),
        "companies",
        "stage IN ('idea', 'validation', 'foundations', 'prototype', 'pilot', "
        "'non_dilutive_funding', 'raise_prep', 'first_round', 'growth')",
    )
    op.execute("GRANT UPDATE (stage, updated_at) ON companies TO home_base_app")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (stage, updated_at) ON companies FROM home_base_app")
    op.drop_constraint(op.f("ck_companies_stage"), "companies", type_="check")
    op.drop_column("companies", "stage")
