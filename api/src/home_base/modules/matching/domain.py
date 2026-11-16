"""Matching vocabulary: requirements, company facts as matching sees them, results."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from home_base.core.vocabulary import Decision, FitStatus, Operator

FactValue = str | int | bool


class RequirementResult(StrEnum):
    """Result of checking one requirement against a company (spec: Result per requirement)."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    AI_JUDGEMENT = "ai_judgement"


class ApplicantForm(StrEnum):
    """Whether a company applies on its own or as part of a consortium."""

    ALONE = "alone"
    CONSORTIUM = "consortium"


class Confidence(StrEnum):
    """The AI's stated confidence in a soft-criterion judgement."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class HardRequirement:
    """One eligibility rule that can be checked mechanically against a company fact."""

    fact_key: str
    operator: Operator
    value: FactValue | frozenset[str]
    source_quote: str


@dataclass(frozen=True, slots=True)
class SoftCriterion:
    """One criterion that needs interpretation, such as "clear environmental benefit"."""

    statement: str
    source_quote: str


@dataclass(frozen=True, slots=True)
class SoftJudgement:
    """The AI's reading of one soft criterion. Shown to the founder; never sets fit."""

    criterion: SoftCriterion
    confidence: Confidence
    explanation: str


@dataclass(frozen=True, slots=True)
class FactSnapshot:
    """A company fact as matching needs it: the value and whether the founder approved it."""

    key: str
    value: FactValue | None
    approved: bool


@dataclass(frozen=True, slots=True)
class FitResult:
    """Fit status plus the "few explicit rules" note (FIT-04)."""

    status: FitStatus
    few_explicit_rules: bool


class NotForUsReason(StrEnum):
    """Optional reason given with Not for us."""

    NOT_RELEVANT = "not_relevant"
    TOO_EARLY = "too_early"
    TOO_MUCH_WORK = "too_much_work"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class DecisionChange:
    """One dated change of decision, written to the opportunity's history."""

    decision: Decision
    changed_at: datetime
    reason: NotForUsReason | None = None


@dataclass(frozen=True, slots=True)
class RequirementOutcome:
    """One requirement's result in a stored match, with the input it read."""

    requirement_id: uuid.UUID
    result: RequirementResult
    fact_key: str | None = None
    fact_version_id: uuid.UUID | None = None  # the company fact version; None for founder facts


@dataclass(frozen=True, slots=True)
class StoredMatch:
    """One calculation of a company's fit for one opportunity, as stored."""

    id: uuid.UUID
    opportunity_id: uuid.UUID
    fit: FitResult
    rule_version: str
    calculated_at: datetime
    superseded_at: datetime | None
    outcomes: tuple[RequirementOutcome, ...]


@dataclass(frozen=True, slots=True)
class FactInput:
    """A fact as a recalculation reads it: the current value, whether it is approved,
    and the company fact version it came from (None for founder facts, D-51)."""

    key: str
    value: FactValue
    approved: bool
    version_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class MatchInputs:
    """Everything a company's recalculation reads (passed in by the companies service)."""

    facts: tuple[FactInput, ...]
    approved_birth_date: date | None = None  # the youngest founder's, for founder_age (D-44)


@dataclass(frozen=True, slots=True)
class MatchChange:
    """A stored change of match for one opportunity (D-52)."""

    opportunity_id: uuid.UUID
    before: FitResult | None
    after: FitResult
