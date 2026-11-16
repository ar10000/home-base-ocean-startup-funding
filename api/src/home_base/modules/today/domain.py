"""Today vocabulary: questions and applications as progress rules need them."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from home_base.core.vocabulary import Decision, FitStatus


class AnswerState(StrEnum):
    """Where one question's answer is (spec: Application > Question list and status)."""

    MISSING_FACTS = "missing_facts"
    AI_DRAFT = "ai_draft"
    EDITED = "edited"
    APPROVED = "approved"


class ApplicationStatus(StrEnum):
    """Application status (spec: Progress)."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    SUBMITTED = "submitted"


class Milestone(StrEnum):
    """Milestones from the fixed list, in the spec's order (spec: Readiness and milestones)."""

    FIRST_FACT_APPROVED = "first_fact_approved"
    HARD_RULE_FACTS_FILLED = "hard_rule_facts_filled"
    FIRST_ANSWER_APPROVED = "first_answer_approved"
    FIRST_APPLICATION_READY = "first_application_ready"
    FIRST_APPLICATION_SUBMITTED = "first_application_submitted"


@dataclass(frozen=True, slots=True)
class QuestionSnapshot:
    """One question of a call: its answer state and the company facts it needs."""

    state: AnswerState
    required_facts: frozenset[str]


@dataclass(frozen=True, slots=True)
class ApplicationSnapshot:
    """One application: its questions in the call's order, and whether it was marked submitted."""

    questions: tuple[QuestionSnapshot, ...]
    submitted: bool


@dataclass(frozen=True, slots=True)
class Ratio:
    """A count out of a total, shown as "6 of 8"."""

    done: int
    total: int

    def __str__(self) -> str:
        return f"{self.done} of {self.total}"


class Mode(StrEnum):
    """Which priority list Today uses (spec: Your one thing today)."""

    APPLYING = "applying"
    PREPARING = "preparing"


class TaskType(StrEnum):
    """Today's task types; each has a fixed time estimate (PRI-10)."""

    ADD_FACT = "add_fact"
    REVIEW_DRAFTS = "review_drafts"
    ANSWER_ONE_QUESTION = "answer_one_question"
    START_APPLICATION = "start_application"
    NEXT_ANSWER = "next_answer"
    DECIDE = "decide"
    BACK_ON_LIST = "back_on_list"
    CHECK_GOALS = "check_goals"


@dataclass(frozen=True, slots=True)
class OpportunitySnapshot:
    """One match as Today needs it."""

    name: str
    blue_specific: bool
    fit: FitStatus
    decision: Decision
    deadline: date | None
    application: ApplicationSnapshot | None
    source_current: bool
    later_returned: bool
    unknown_hard_facts: frozenset[str]
    upcoming: bool
    opening: date | None  # official opening, or the 1st of the expected month (D-19)
    questions: tuple[QuestionSnapshot, ...] | None  # the call's (or last edition's) questions


@dataclass(frozen=True, slots=True)
class Unlocks:
    """What approving one missing fact would do (RDY-02)."""

    matches: int
    questions: int

    @property
    def total(self) -> int:
        return self.matches + self.questions


@dataclass(frozen=True, slots=True)
class Task:
    """One task Today can show. The AI only words it; the code picks it."""

    type: TaskType
    opportunity: str | None
    deadline: date | None
    blue_specific: bool
    fact: str | None = None
    count: int | None = None
    question: int | None = None  # 1-based position in the call's order


@dataclass(frozen=True, slots=True)
class TodayPlan:
    """The one thing today, or None for the "You're all set" state, and what needs attention."""

    one_thing: Task | None
    needs_attention: tuple[Task, ...]
