"""Base repository for tenant tables (handbook section 13, isolation layer 1).

Every query on a tenant table goes through `scoped`, which filters on the session's
`company_id`, and every write goes through `add`, which stamps it. The company comes
from the signed-in session, never from a request body. Row-level security is the
second layer (week 2, step 6).

Repositories never commit: the service owns the transaction, so a change and its
audit event are saved together or not at all (architecture rule 7).
"""

import uuid
from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from home_base.core.db import Base
from home_base.core.errors import TenantError

Row = TypeVar("Row", bound=Base)


def _company_column(model: type[Base]) -> Any:
    column = getattr(model, "company_id", None)
    if column is None:
        raise TenantError(f"{model.__name__} is not a tenant table")
    return column


class TenantRepository:
    """Database access scoped to one company."""

    def __init__(self, session: Session, company_id: uuid.UUID) -> None:
        self.session = session
        self.company_id = company_id

    def scoped(self, model: type[Row]) -> Select[tuple[Row]]:
        """`SELECT model` limited to this company's rows."""
        return select(model).where(_company_column(model) == self.company_id)

    def get(self, model: type[Row], row_id: uuid.UUID) -> Row | None:
        """One of this company's rows by ID; another company's row is not found."""
        return self.session.scalars(
            self.scoped(model).where(model.id == row_id)  # type: ignore[attr-defined]
        ).one_or_none()

    def add(self, row: Row) -> Row:
        """Stage a new row for this company; refuses a row stamped for another one."""
        _company_column(type(row))
        current = getattr(row, "company_id", None)
        if current is None:
            row.company_id = self.company_id  # type: ignore[attr-defined]
        elif current != self.company_id:
            raise TenantError(f"{type(row).__name__} belongs to another company")
        self.session.add(row)
        self.session.flush()
        return row
