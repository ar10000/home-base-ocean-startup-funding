"""one membership per user

One company per founder in Phase 1 (D-64, D-71), enforced by the database as well as by
onboarding. The unique user_id replaces the (user_id, company_id) pair and the plain index
on user_id, which it makes redundant. Onboarding already refused a second company, so no
existing row can break it; if one did, the upgrade stops rather than choosing for us.

Revision ID: ae9669b7f4c1
Revises: aac7deecac27
Created: 2026-11-15 22:38:18.794654+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "ae9669b7f4c1"
down_revision: str | Sequence[str] | None = "aac7deecac27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_constraint(op.f("uq_memberships_user_company"), "memberships", type_="unique")
    op.create_unique_constraint("uq_memberships_user", "memberships", ["user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_memberships_user", "memberships", type_="unique")
    op.create_unique_constraint(
        op.f("uq_memberships_user_company"),
        "memberships",
        ["user_id", "company_id"],
        postgresql_nulls_not_distinct=False,
    )
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)
