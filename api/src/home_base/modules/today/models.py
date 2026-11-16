"""Milestones table: each reached progress moment, stored so it is shown once (PRG-04)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from home_base.core.db import Base, Record, one_of
from home_base.modules.today.domain import Milestone

MILESTONES = tuple(m.value for m in Milestone)


class MilestoneRow(Record, Base):
    __tablename__ = "milestones"
    __table_args__ = (
        CheckConstraint(one_of("milestone", MILESTONES), name="milestone"),
        UniqueConstraint("company_id", "milestone", name="uq_milestones_company_milestone"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    milestone: Mapped[str]
    reached_at: Mapped[datetime]
