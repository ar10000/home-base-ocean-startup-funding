"""Progress and readiness rules.

Every public function quotes the rule IDs it implements, as listed in
docs/rules/today.yaml. Pure functions only.
"""

from collections.abc import Iterable, Sequence
from datetime import date

from home_base.config import (
    APPLICATION_DUE_WITHIN_DAYS,
    APPLYING_CLOSES_WITHIN_DAYS,
    CONFIRMED_CLOSES_WITHIN_DAYS,
    HARD_RULE_FACT_KEYS,
    INTENT_STALE_DAYS,
    NEEDS_ATTENTION_COUNT,
    OPENING_SOON_COUNT,
    OPENING_SOON_DAYS,
    POSSIBLE_CLOSES_WITHIN_DAYS,
    TIME_ESTIMATE_MINUTES,
)
from home_base.core.dates import days_left
from home_base.core.vocabulary import Decision, FitStatus
from home_base.modules.today.domain import (
    AnswerState,
    ApplicationSnapshot,
    ApplicationStatus,
    Milestone,
    Mode,
    OpportunitySnapshot,
    QuestionSnapshot,
    Ratio,
    Task,
    TaskType,
    TodayPlan,
    Unlocks,
)


def answers_ready(questions: Sequence[QuestionSnapshot]) -> Ratio | None:
    """Approved answers out of the call's questions, or None when there are none.

    Rule PRG-01: answers ready = approved / total questions.
    A call with no questions shows nothing, never "0 of 0" (decision D-23).
    """
    if not questions:
        return None
    return Ratio(sum(q.state is AnswerState.APPROVED for q in questions), len(questions))


def is_draftable(question: QuestionSnapshot, approved_facts: frozenset[str]) -> bool:
    """Whether a draft can be written for this question now.

    Rule PRG-02: draftable = questions whose required facts are all approved.
    A question with no required facts listed is not draftable (decision D-24).
    """
    return bool(question.required_facts) and question.required_facts <= approved_facts


def application_status(application: ApplicationSnapshot) -> ApplicationStatus:
    """Where an application is.

    Rule PRG-03: application status moves not started, in progress, ready,
    submitted. Started = an AI draft, an edit or an approval (D-25). Reopening
    an approved answer returns ready to in progress; a submitted application
    stays submitted (decision D-09).
    """
    if application.submitted:
        return ApplicationStatus.SUBMITTED
    states = [q.state for q in application.questions]
    if states and all(s is AnswerState.APPROVED for s in states):
        return ApplicationStatus.READY
    if any(s is not AnswerState.MISSING_FACTS for s in states):
        return ApplicationStatus.IN_PROGRESS
    return ApplicationStatus.NOT_STARTED


def _all_approved(application: ApplicationSnapshot) -> bool:
    return bool(application.questions) and all(
        q.state is AnswerState.APPROVED for q in application.questions
    )


def new_milestones(
    approved_facts: frozenset[str],
    applications: Iterable[ApplicationSnapshot],
    already_shown: frozenset[Milestone],
) -> list[Milestone]:
    """Milestones reached and not shown before, in the fixed list's order.

    Rule PRG-04: milestones come from a fixed list; each is shown once and logged
    (the service writes the log). Every hard-rule fact filled = every field in
    HARD_RULE_FACT_KEYS approved (decision D-26).
    """
    apps = list(applications)
    reached = {
        Milestone.FIRST_FACT_APPROVED: bool(approved_facts),
        Milestone.HARD_RULE_FACTS_FILLED: approved_facts >= HARD_RULE_FACT_KEYS,
        Milestone.FIRST_ANSWER_APPROVED: any(
            q.state is AnswerState.APPROVED for a in apps for q in a.questions
        ),
        Milestone.FIRST_APPLICATION_READY: any(_all_approved(a) for a in apps),
        Milestone.FIRST_APPLICATION_SUBMITTED: any(a.submitted for a in apps),
    }
    return [m for m in Milestone if reached[m] and m not in already_shown]


def readiness(
    questions: Sequence[QuestionSnapshot] | None, approved_facts: frozenset[str]
) -> Ratio | None:
    """How many of an opportunity's questions are draftable or approved.

    Rule RDY-01: readiness = draftable or approved questions / total questions;
    hidden when the questions are unknown or there are none (decision D-23).
    """
    if not questions:
        return None
    ready = sum(
        q.state is AnswerState.APPROVED or is_draftable(q, approved_facts) for q in questions
    )
    return Ratio(ready, len(questions))


def task_sort_key(
    deadline: date | None, blue_specific: bool, name: str
) -> tuple[bool, date, bool, str]:
    """Sort key for tasks that match the same priority rule.

    Rule PRI-08: ties go to the earliest deadline (in preparing mode, the earliest
    opening or deadline), then blue-specific before all-sector, then name A to Z
    (decision D-28). A rolling call sorts after every dated one (D-37).
    """
    return (deadline is None, deadline or date.max, not blue_specific, name.casefold())


def time_estimate_minutes(task: TaskType) -> int:
    """Minutes shown next to a task.

    Rule PRI-10: time estimates come from a fixed table per task type (D-27).
    """
    return TIME_ESTIMATE_MINUTES[task.value]


def _deadline_not_passed(deadline: date | None, today: date) -> bool:
    return deadline is None or days_left(deadline, today) >= 0


def today_mode(opportunities: Iterable[OpportunitySnapshot], today: date) -> Mode:
    """Which priority list Today uses.

    Rule PRI-11: Applying when an application is in progress with a future
    deadline, or a Confirmed match with no decision or Pursuing closes within
    30 days; otherwise Preparing. A Ready application counts too (D-33); the
    deadline day is still open and a rolling call never passes (D-22, D-37).
    Only opportunities with a current source (D-39) that are not Not eligible
    (D-40) decide the mode.
    """
    for o in opportunities:
        if not o.source_current or o.fit is FitStatus.NOT_ELIGIBLE:
            continue
        app = o.application
        if (
            app is not None
            and application_status(app) in (ApplicationStatus.IN_PROGRESS, ApplicationStatus.READY)
            and _deadline_not_passed(o.deadline, today)
        ):
            return Mode.APPLYING
        if (
            o.fit is FitStatus.CONFIRMED
            and o.decision in (Decision.NONE, Decision.PURSUING)
            and o.deadline is not None
            and 0 <= days_left(o.deadline, today) <= APPLYING_CLOSES_WITHIN_DAYS
        ):
            return Mode.APPLYING
    return Mode.PREPARING


def counts_for_priorities(
    decision: Decision, later_returned: bool, source_current: bool, fit: FitStatus
) -> bool:
    """Whether an opportunity can produce a task in Today.

    Rule PRI-12: priority lists use only opportunities with a current source and
    no decision or Pursuing, plus Later once it has returned (DEC-03); never a
    Not eligible one (D-40).
    """
    if not source_current or fit is FitStatus.NOT_ELIGIBLE:
        return False
    if decision is Decision.LATER:
        return later_returned
    return decision in (Decision.NONE, Decision.PURSUING)


def _within(deadline: date | None, today: date, days: int) -> bool:
    return deadline is not None and 0 <= days_left(deadline, today) <= days


def _blocking_fact(application: ApplicationSnapshot, approved: frozenset[str]) -> str | None:
    """The missing fact that blocks the most answers; ties to the earliest question (D-31)."""
    blocked: dict[str, int] = {}
    first: dict[str, int] = {}
    for position, q in enumerate(application.questions):
        if q.state is not AnswerState.MISSING_FACTS:
            continue
        for fact in sorted(q.required_facts - approved):
            # Only the ranking matters, so any constant offset is equivalent.
            blocked[fact] = blocked.get(fact, 0) + 1  # pragma: no mutate
            first.setdefault(fact, position)
    if not blocked:
        return None
    return min(blocked, key=lambda f: (-blocked[f], first[f], f))


def _next_answer(application: ApplicationSnapshot) -> int | None:
    """1-based position of the first drafted or edited, unapproved answer (D-34)."""
    for position, q in enumerate(application.questions, start=1):
        if q.state in (AnswerState.AI_DRAFT, AnswerState.EDITED):
            return position
    return None


def _task(
    o: OpportunitySnapshot,
    kind: TaskType,
    *,
    fact: str | None = None,
    count: int | None = None,
    question: int | None = None,
) -> Task:
    return Task(kind, o.name, o.deadline, o.blue_specific, fact, count, question)


def _key(task: Task) -> tuple[bool, date, bool, str]:
    # Only "Check your goals" has no opportunity, and there is one; the default is unseen.
    name = task.opportunity or ""  # pragma: no mutate
    return task_sort_key(task.deadline, task.blue_specific, name)


def applying_tasks(
    opportunities: Iterable[OpportunitySnapshot], approved_facts: frozenset[str], today: date
) -> list[Task]:
    """Every applying-mode task, in priority order; ties by PRI-08.

    Rule PRI-01: applying 1, a missing fact blocks an answer in an application
    due within 14 days (the fact blocking the most answers, D-31).
    Rule PRI-02: applying 2, AI drafts await review in an application due within
    14 days (AI drafts only, D-35).
    Rule PRI-03: applying 3, a Possible match closes within 21 days and one fact
    would decide it.
    Rule PRI-04: applying 4, a Confirmed match closes within 30 days with no
    application.
    Rule PRI-05: applying 5, next unapproved answer in the earliest-deadline
    application (the first drafted or edited answer, D-34).
    "Within N days" includes day N and today (D-22). Only opportunities that count
    (PRI-12) give tasks. One "Add [fact]" per fact.
    """
    counted = _counted(opportunities)
    found: list[list[Task]] = [[], [], [], [], []]
    for o in counted:
        _collect_applying(o, approved_facts, today, found)
    found[4] = sorted(found[4], key=_key)[:1]  # only the earliest-deadline application
    return _merge(found)


def _collect_applying(
    o: OpportunitySnapshot, approved: frozenset[str], today: date, found: list[list[Task]]
) -> None:
    app = o.application
    live = app is not None and not app.submitted and _deadline_not_passed(o.deadline, today)
    if app is not None and live and _within(o.deadline, today, APPLICATION_DUE_WITHIN_DAYS):
        fact = _blocking_fact(app, approved)
        if fact is not None:
            found[0].append(_task(o, TaskType.ADD_FACT, fact=fact))
        drafts = sum(q.state is AnswerState.AI_DRAFT for q in app.questions)
        if drafts:
            found[1].append(_task(o, TaskType.REVIEW_DRAFTS, count=drafts))
    if (
        o.fit is FitStatus.POSSIBLE
        and len(o.unknown_hard_facts) == 1
        and _within(o.deadline, today, POSSIBLE_CLOSES_WITHIN_DAYS)
    ):
        (fact,) = o.unknown_hard_facts
        found[2].append(_task(o, TaskType.ANSWER_ONE_QUESTION, fact=fact))
    if (
        o.fit is FitStatus.CONFIRMED
        and app is None
        and _within(o.deadline, today, CONFIRMED_CLOSES_WITHIN_DAYS)
    ):
        found[3].append(_task(o, TaskType.START_APPLICATION))
    position = _next_answer(app) if app is not None and live else None
    if position is not None:
        found[4].append(_task(o, TaskType.NEXT_ANSWER, question=position))


def _merge(found: list[list[Task]]) -> list[Task]:
    """Rule lists in priority order, each sorted by PRI-08; one "Add [fact]" per fact."""
    ordered: list[Task] = []
    seen_facts: set[str | None] = set()
    for tasks in found:
        for task in sorted(tasks, key=_key):
            if task.type is TaskType.ADD_FACT:
                if task.fact in seen_facts:
                    continue
                seen_facts.add(task.fact)
            ordered.append(task)
    return ordered


def today_plan(tasks: Sequence[Task]) -> TodayPlan:
    """The one thing today and what needs attention, from a priority-ordered list.

    Rule PRI-06: nothing matches gives the "You're all set" state (no one thing).
    Rule PRI-09: needs attention = the next 3 tasks, excluding the one thing today.
    """
    if not tasks:
        return TodayPlan(None, ())
    return TodayPlan(tasks[0], tuple(tasks[1 : 1 + NEEDS_ATTENTION_COUNT]))


def _counted(opportunities: Iterable[OpportunitySnapshot]) -> list[OpportunitySnapshot]:
    return [
        o
        for o in opportunities
        if counts_for_priorities(o.decision, o.later_returned, o.source_current, o.fit)
    ]


def _questions_of(o: OpportunitySnapshot) -> tuple[QuestionSnapshot, ...]:
    if o.application is not None:
        return o.application.questions
    return o.questions or ()


def _date_of(o: OpportunitySnapshot) -> date | None:
    return o.opening if o.upcoming else o.deadline


def _unlocks_question(q: QuestionSnapshot, fact: str, approved: frozenset[str]) -> bool:
    return q.state is not AnswerState.APPROVED and q.required_facts - approved == {fact}


def fact_unlocks(
    fact: str, opportunities: Iterable[OpportunitySnapshot], approved_facts: frozenset[str]
) -> Unlocks:
    """What approving one missing fact would settle and unlock.

    Rule RDY-02: unlocks per missing fact = Possible matches where it is the only
    unknown hard rule + questions it makes draftable across upcoming and Pursuing
    opportunities. A question counts when this fact is the only one it still
    needs (D-24). Only opportunities that count for Today are used (D-38), so a
    Not eligible one gives no unlocks (D-40).
    """
    if fact in approved_facts:
        return Unlocks(0, 0)
    counted = _counted(opportunities)
    matches = sum(o.fit is FitStatus.POSSIBLE and o.unknown_hard_facts == {fact} for o in counted)
    questions = sum(
        _unlocks_question(q, fact, approved_facts)
        for o in counted
        if o.upcoming or o.decision is Decision.PURSUING
        for q in _questions_of(o)
    )
    return Unlocks(matches, questions)


def _fact_tasks(counted: list[OpportunitySnapshot], approved: frozenset[str]) -> list[Task]:
    candidates: set[str] = set()
    for o in counted:
        candidates |= o.unknown_hard_facts
        for q in _questions_of(o):
            candidates |= q.required_facts
    tasks = []
    for fact in sorted(candidates - approved):
        unlocks = fact_unlocks(fact, counted, approved)
        if unlocks.total == 0:
            continue
        affected = [
            d
            for o in counted
            if (d := _date_of(o)) is not None
            and (
                fact in o.unknown_hard_facts
                or any(fact in q.required_facts for q in _questions_of(o))
            )
        ]
        tasks.append(
            Task(TaskType.ADD_FACT, None, min(affected, default=None), False, fact, unlocks.total)
        )
    # Facts were added in name order and the sort is stable, so equal ties stay A to Z.
    return sorted(
        tasks,
        key=lambda t: (
            -(t.count or 0),  # pragma: no mutate  (a fact task's count is always >= 1)
            t.deadline is None,
            t.deadline or date.max,
        ),
    )


def preparing_tasks(
    opportunities: Iterable[OpportunitySnapshot],
    approved_facts: frozenset[str],
    intent_recorded_on: date | None,
    today: date,
) -> list[Task]:
    """Every preparing-mode task, in priority order.

    Rule PRI-13: preparing 1, the missing fact with the most unlocks gives
    "Add [fact]" (total unlocks; none, no task; D-36).
    Rule PRI-14: preparing 2, an upcoming opportunity opens within 30 days and
    has no decision (an expected month still upcoming counts, D-38).
    Rule PRI-15: preparing 3, an opportunity on Later has returned.
    Rule PRI-16: preparing 4, intent untouched for more than 90 days, or never
    set, gives "Check your goals" (D-22, D-32).
    Ties go to the earliest opening or deadline (PRI-08).
    """
    counted = _counted(opportunities)
    decide = [
        Task(TaskType.DECIDE, o.name, o.opening, o.blue_specific)
        for o in counted
        if o.upcoming
        and o.decision is Decision.NONE
        and o.opening is not None
        and days_left(o.opening, today) <= OPENING_SOON_DAYS
    ]
    back = [
        Task(TaskType.BACK_ON_LIST, o.name, _date_of(o), o.blue_specific)
        for o in counted
        if o.decision is Decision.LATER
    ]
    goals = []
    if intent_recorded_on is None or (today - intent_recorded_on).days > INTENT_STALE_DAYS:
        goals.append(Task(TaskType.CHECK_GOALS, None, None, False))
    return _fact_tasks(counted, approved_facts) + _merge([decide, back, goals])


def next_opening_date(opportunities: Iterable[OpportunitySnapshot]) -> date | None:
    """The next opening date shown with the "You're all set" state.

    Rule PRI-17: preparing 5, nothing matches gives "You're all set", with the
    next opening date: the earliest among upcoming calls not marked Not for us
    (D-38) and not Not eligible (D-40).
    """
    openings = [
        o.opening
        for o in opportunities
        if o.upcoming
        and o.opening is not None
        and o.decision is not Decision.NOT_FOR_US
        and o.fit is not FitStatus.NOT_ELIGIBLE
    ]
    return min(openings, default=None)


def opening_soon(
    opportunities: Iterable[OpportunitySnapshot], today: date
) -> list[OpportunitySnapshot]:
    """The opportunities Preparing mode lists as opening soon.

    Rule PRI-18: up to 3 upcoming opportunities that count for Today, opening within
    30 days (PRI-14's window, D-61), by opening date; ties blue-specific first, then
    name (D-28). Each is shown with its readiness (RDY-01).
    """
    found = [
        o
        for o in _counted(opportunities)
        if o.upcoming and o.opening is not None and _within(o.opening, today, OPENING_SOON_DAYS)
    ]
    found.sort(key=lambda o: (o.opening, not o.blue_specific, o.name))
    return found[:OPENING_SOON_COUNT]


def next_deadline(
    opportunities: Iterable[OpportunitySnapshot], today: date
) -> OpportunitySnapshot | None:
    """The opportunity whose deadline Today shows as the next deadline.

    Rule PRI-19: the earliest deadline, today or later, among opportunities that
    count for Today with an application not yet marked submitted (D-61); ties
    blue-specific first, then name (D-28). Shown with its answers ready (PRG-01).
    """
    found = [
        o
        for o in _counted(opportunities)
        if o.application is not None
        and not o.application.submitted
        and o.deadline is not None
        and days_left(o.deadline, today) >= 0
    ]
    found.sort(key=lambda o: (o.deadline, not o.blue_specific, o.name))
    return found[0] if found else None
