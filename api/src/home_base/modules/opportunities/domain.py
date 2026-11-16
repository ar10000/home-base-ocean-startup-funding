"""Opportunity vocabulary for status, freshness and source checks."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from home_base.core.errors import ClockError


class VerificationMethod(StrEnum):
    """How an opportunity's details were checked against the official source."""

    MANUAL = "manual"
    AUTOMATED = "automated"


class OpportunityStatus(StrEnum):
    """Whether an opportunity accepts applications (spec: Upcoming opportunities)."""

    OPEN = "open"
    UPCOMING = "upcoming"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class Month:
    """A calendar month, for an opening that is only expected ("Expected around March")."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ClockError(f"month must be 1 to 12, got {self.month}")

    @property
    def first_day(self) -> date:
        """The 1st of the month: the day an expected opening counts from (decision D-19)."""
        return date(self.year, self.month, 1)

    @property
    def first_day_after(self) -> date:
        """The 1st of the next month: from this day the month has passed (decision D-19)."""
        if self.month == 12:
            return date(self.year + 1, 1, 1)
        return date(self.year, self.month + 1, 1)


class EvidenceKind(StrEnum):
    """What backs an expected opening month (spec: Upcoming opportunities)."""

    PREVIOUS_EDITION = "previous_edition"
    ANNOUNCEMENT = "announcement"


@dataclass(frozen=True, slots=True)
class Evidence:
    """One piece of evidence for an expected opening.

    `dated` is the evidence's own date: the previous edition's opening date, or the
    announcement's publication date (decision D-20).
    """

    kind: EvidenceKind
    dated: date
    source_url: str


class FreshnessState(StrEnum):
    """Whether an opportunity can be trusted today (spec: Freshness)."""

    CURRENT = "current"
    RECHECK_DUE = "recheck_due"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class Verification:
    """One check of an opportunity against its source."""

    verified_on: date
    method: VerificationMethod


@dataclass(frozen=True, slots=True)
class SourcedValue:
    """One source's claim about a date, amount or rule of an opportunity."""

    value: str
    official: bool
    source_url: str


@dataclass(frozen=True, slots=True)
class SourceResolution:
    """The value to show, or None, and whether the opportunity needs a re-check."""

    value: str | None
    recheck_due: bool


class ReloadOutcome(StrEnum):
    """What a reload from the seed files did to one opportunity (D-46)."""

    ADDED = "added"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class ReloadEffects:
    """What follows from a reload outcome: an audit event, a recalculation of matches."""

    audit: bool
    recalculate: bool


class DeadlineKind(StrEnum):
    """How a deadline is shown (SCP-03)."""

    ROLLING = "rolling"
    DAYS_LEFT = "days_left"
    DATE = "date"


@dataclass(frozen=True, slots=True)
class DeadlineDisplay:
    kind: DeadlineKind
    days_left: int | None = None
