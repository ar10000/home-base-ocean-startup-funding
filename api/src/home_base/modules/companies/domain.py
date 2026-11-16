"""Company vocabulary: facts (spec: Company fact; D-47 to D-51) and the founder's intent."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Goal(StrEnum):
    """A goal from the fixed list."""

    PILOT_OR_TEST_SITE = "pilot_or_test_site"
    NON_DILUTIVE_FUNDING = "non_dilutive_funding"
    ACCELERATOR_PLACE = "accelerator_place"
    FIRST_CUSTOMERS = "first_customers"
    INVESTMENT = "investment"


class Window(StrEnum):
    """When a goal matters: now (within 3 months), soon (3 to 6), later (6 to 12)."""

    NOW = "now"
    SOON = "soon"
    LATER = "later"


@dataclass(frozen=True, slots=True)
class GoalChoice:
    """One goal with its window."""

    goal: Goal
    window: Window


@dataclass(frozen=True, slots=True)
class IntentRecord:
    """One dated intent; every change adds a new record."""

    goals: tuple[GoalChoice, ...]
    recorded_at: datetime


FactValue = str | int | bool


class FactLabel(StrEnum):
    """Where a fact came from (spec: Company fact). Never changes on approval (D-48)."""

    SOURCED = "sourced"
    USER_PROVIDED = "user_provided"
    AI_SUGGESTED = "ai_suggested"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class FactVersion:
    """One version of one company fact (D-50)."""

    id: uuid.UUID
    key: str
    value: FactValue
    label: FactLabel
    source: str | None
    recorded_at: datetime
    approved_at: datetime | None
    approved_by: uuid.UUID | None
    superseded_at: datetime | None


@dataclass(frozen=True, slots=True)
class FounderFact:
    """One founder fact (D-44): the youngest founder's birth date, or a yes/no."""

    key: str
    value: date | bool
    approved_at: datetime | None
