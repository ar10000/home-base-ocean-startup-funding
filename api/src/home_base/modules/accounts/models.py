"""Users and memberships (ADR-006 sign-in; handbook section 13).

A user is a Keycloak subject; Keycloak keeps the email and name, so neither is stored
here. A membership gives a user access to one company. Approver and actor IDs elsewhere
are kept as plain IDs, without a foreign key, so a user's account can be deleted (GDPR)
without rewriting the append-only audit trail (D-63).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from home_base.core.db import Base, Record, one_of

ROLES = ("founder",)  # Phase 1 has founders only (D-63)


class UserRow(Record, Base):
    __tablename__ = "users"

    keycloak_subject: Mapped[str] = mapped_column(unique=True)  # the token's "sub"
    archived_at: Mapped[datetime | None]


class MembershipRow(Record, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint(one_of("role", ROLES), name="role"),
        # One company per founder in Phase 1 (D-64, D-71): a user has at most one membership.
        UniqueConstraint("user_id", name="uq_memberships_user"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    role: Mapped[str]
