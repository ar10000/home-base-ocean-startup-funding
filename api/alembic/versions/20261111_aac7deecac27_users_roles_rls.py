"""users, memberships, app role and row-level security

Revision ID: aac7deecac27
Revises: cbe0def2b4b5
Created: 2026-11-11 15:59:37.009364+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "aac7deecac27"
down_revision: str | Sequence[str] | None = "cbe0def2b4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The role the API runs as (handbook section 13, layer 2). The login user switches to it
# per request with SET LOCAL ROLE and sets app.company_id; the reload job and migrations
# keep the owner's rights. Roles are cluster-wide, so it is created only if missing.
APP_ROLE = "home_base_app"
SETTING = "NULLIF(current_setting('app.company_id', true), '')::uuid"  # unset or empty: no company

# Tenant tables, each row visible and writable only for the session's company.
TENANT = [
    "company_facts",
    "founder_facts",
    "intents",
    "intent_goals",
    "milestones",
    "matches",
    "requirement_results",
    "decisions",
    "applications",
    "answers",
    "answer_versions",
    "answer_version_facts",
]
# Logs with shared (company-less) rows: readable when shared or the company's own;
# the app only ever writes its own company's.
SHARED_LOGS = ["audit_events", "ai_actions"]
# Shared opportunity data: read-only for the app; the reload job writes it.
SHARED_READ = [
    "opportunities",
    "sources",
    "requirements",
    "questions",
    "evidence",
    "fact_definitions",
    "alembic_version",
]
# What the app may do, by table. No UPDATE or DELETE on the audit trail (append-only);
# DELETE only where a hard delete is allowed (founder facts, D-51).
GRANTS = {
    **{t: "SELECT, INSERT, UPDATE" for t in TENANT},
    "founder_facts": "SELECT, INSERT, UPDATE, DELETE",
    "audit_events": "SELECT, INSERT",
    "ai_actions": "SELECT, INSERT",
    "job_runs": "SELECT, INSERT, UPDATE",
    "companies": "SELECT",
    **{t: "SELECT" for t in SHARED_READ},
}


def _security_up() -> None:
    op.execute(
        f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN;
            END IF;
        END $$;
        """
    )
    op.execute(f"GRANT {APP_ROLE} TO CURRENT_USER")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    for table, rights in GRANTS.items():
        op.execute(f"GRANT {rights} ON {table} TO {APP_ROLE}")
    for table in TENANT:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_only ON {table} TO {APP_ROLE} "
            f"USING (company_id = {SETTING}) WITH CHECK (company_id = {SETTING})"
        )
    for table in SHARED_LOGS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_or_shared ON {table} TO {APP_ROLE} "
            f"USING (company_id IS NULL OR company_id = {SETTING}) "
            f"WITH CHECK (company_id = {SETTING})"
        )
    op.execute("ALTER TABLE companies ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY own_company ON companies TO {APP_ROLE} USING (id = {SETTING})")


def _security_down() -> None:
    op.execute("DROP POLICY IF EXISTS own_company ON companies")
    op.execute("ALTER TABLE companies DISABLE ROW LEVEL SECURITY")
    for table in SHARED_LOGS:
        op.execute(f"DROP POLICY IF EXISTS tenant_or_shared ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in TENANT:
        op.execute(f"DROP POLICY IF EXISTS tenant_only ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in GRANTS:
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    # The role itself is left in place: roles are cluster-wide and may serve other databases.


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("keycloak_subject", sa.String(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("keycloak_subject", name=op.f("uq_users_keycloak_subject")),
    )
    op.create_table(
        "memberships",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
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
        sa.CheckConstraint("role IN ('founder')", name=op.f("ck_memberships_role")),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_memberships_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memberships_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint("user_id", "company_id", name="uq_memberships_user_company"),
    )
    op.create_index(op.f("ix_memberships_company_id"), "memberships", ["company_id"], unique=False)
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)
    _security_up()


def downgrade() -> None:
    _security_down()
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_company_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("users")
