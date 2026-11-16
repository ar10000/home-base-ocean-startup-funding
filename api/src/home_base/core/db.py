"""SQLAlchemy base shared by every module's models.py (handbook sections 3 and 11).

Each module declares its own tables on `Base`; Alembic reads `Base.metadata`. The
`Record` mixin gives every table its `id` (UUIDv7), `created_at` and `updated_at`.
Timestamps are timezone-aware and stored in UTC (architecture rule 10).
"""

import os
import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from home_base.core.ids import new_id

DATABASE_URL_ENV = "HOME_BASE_DATABASE_URL"

# Stable constraint names, so Alembic can find and drop them in later migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: DateTime(timezone=True)}


class Record:
    """Columns every table has (handbook section 11)."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


def one_of(column: str, values: tuple[str, ...]) -> str:
    """SQL for a CHECK that `column` holds one of `values` (enums checked in the database)."""
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def database_url() -> str:
    """The database URL from the environment. No default, so nothing connects by accident."""
    url = os.environ.get(DATABASE_URL_ENV)
    if not url:
        raise RuntimeError(f"{DATABASE_URL_ENV} is not set")
    return url
