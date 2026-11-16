"""Alembic environment: online migrations only, against Base.metadata."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import home_base.jobs.models
import home_base.modules.accounts.models
import home_base.modules.applications.models
import home_base.modules.audit.models
import home_base.modules.companies.models
import home_base.modules.matching.models
import home_base.modules.opportunities.models
import home_base.modules.today.models  # noqa: F401  (registers the tables on Base.metadata)
from home_base.core.db import Base, database_url

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# Every module's models.py is imported above, so autogenerate and `make db-check`
# see all tables.
target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url") or database_url()
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline (SQL script) migrations are not used; run against a database.")
run_migrations_online()
