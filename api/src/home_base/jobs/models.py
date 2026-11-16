"""Job runs: which background task ran, how long, with what result (handbook section 12).

Kept 90 days; the clean-up job comes with the job runner (ADR-005).
"""

from datetime import datetime

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from home_base.core.db import Base, Record, one_of

JOB_RUN_STATUSES = ("running", "succeeded", "failed")


class JobRun(Record, Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        CheckConstraint(one_of("status", JOB_RUN_STATUSES), name="status"),
        CheckConstraint("attempt >= 1", name="attempt_from_one"),
        CheckConstraint("duration_ms >= 0", name="duration_ms_not_negative"),
        CheckConstraint(
            "(status = 'running') = (finished_at IS NULL)", name="finished_unless_running"
        ),
    )

    job: Mapped[str]
    status: Mapped[str]
    attempt: Mapped[int]
    started_at: Mapped[datetime] = mapped_column(index=True)
    finished_at: Mapped[datetime | None]
    duration_ms: Mapped[int | None]
    error: Mapped[str | None]  # the exception type and message; never personal data
    request_id: Mapped[str | None]
