"""Edges found by mutation testing: each test pins a boundary or tie-break a mutant slipped past."""

from datetime import UTC, date, datetime, timedelta

from home_base.core.vocabulary import Decision, FitStatus
from home_base.modules.companies.domain import Goal, GoalChoice, Window
from home_base.modules.companies.rules import current_intent, intent_record
from home_base.modules.matching.domain import ApplicantForm, RequirementResult
from home_base.modules.matching.rules import (
    applicant_form_requirement,
    current_decision,
    decision_change,
    fit_status,
    later_has_returned,
)
from home_base.modules.opportunities.domain import FreshnessState, Verification, VerificationMethod
from home_base.modules.opportunities.rules import last_verified_date, upcoming_freshness_state
from home_base.modules.today.domain import (
    AnswerState,
    ApplicationSnapshot,
    OpportunitySnapshot,
    QuestionSnapshot,
    Task,
    TaskType,
)
from home_base.modules.today.rules import applying_tasks, preparing_tasks

TODAY = date(2026, 11, 9)
AT = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
S = AnswerState


def day(n: int | None) -> date | None:
    return None if n is None else TODAY + timedelta(days=n)


def app(*items: tuple[AnswerState, tuple[str, ...]]) -> ApplicationSnapshot:
    return ApplicationSnapshot(tuple(QuestionSnapshot(s, frozenset(f)) for s, f in items), False)


def opp(
    name: str = "Call",
    fit: FitStatus = FitStatus.POSSIBLE,
    decision: Decision = Decision.NONE,
    deadline: int | None = 60,
    application: ApplicationSnapshot | None = None,
    blue: bool = True,
    unknown: tuple[str, ...] = (),
    upcoming: bool = False,
    opening: int | None = None,
    returned: bool = False,
    questions: tuple[QuestionSnapshot, ...] | None = None,
) -> OpportunitySnapshot:
    return OpportunitySnapshot(
        name, blue, fit, decision, day(deadline), application, True, returned,
        frozenset(unknown), upcoming, day(opening), questions,
    )  # fmt: skip


def names(tasks: list[Task]) -> list[str]:
    return [f"{t.type.value}:{t.opportunity}:{t.fact or ''}" for t in tasks]


# INT-02, DEC-01: the latest of three or more wins


def test_int_02_latest_of_three() -> None:
    goals = [
        GoalChoice(g, Window.NOW)
        for g in (Goal.INVESTMENT, Goal.FIRST_CUSTOMERS, Goal.ACCELERATOR_PLACE)
    ]
    records = [intent_record([g], AT + timedelta(days=i)) for i, g in enumerate(goals)]
    current = current_intent([records[2], records[0], records[1]])
    assert current is not None
    assert current.goals == (goals[2],)


def test_dec_01_latest_of_three() -> None:
    changes = [decision_change(d, AT + timedelta(days=i)) for i, d in enumerate(
        (Decision.LATER, Decision.NOT_FOR_US, Decision.PURSUING))]  # fmt: skip
    assert current_decision([changes[2], changes[0], changes[1]]) is Decision.PURSUING


# FIT-01, FIT-04: a confirmed fit carries no "few explicit rules" note


def test_fit_04_confirmed_has_no_note() -> None:
    result = fit_status([RequirementResult.PASS, RequirementResult.PASS])
    assert result.status is FitStatus.CONFIRMED
    assert result.few_explicit_rules is False


# REQ-05: the requirement keeps its source quote


def test_req_05_applicant_form_keeps_the_quote() -> None:
    req = applicant_form_requirement(
        frozenset({ApplicantForm.CONSORTIUM}), source_quote="Consortia only."
    )
    assert req.source_quote == "Consortia only."


# DEC-03: a call opening today is open, so its deadline counts


def test_dec_03_opening_today_counts_from_the_deadline() -> None:
    assert later_has_returned(day(200), TODAY, TODAY, False) is False
    assert later_has_returned(day(20), TODAY, TODAY, False) is True


# FRS-01: a check made today counts


def test_frs_01_verified_today() -> None:
    assert last_verified_date([Verification(TODAY, VerificationMethod.MANUAL)], TODAY) == TODAY


# UPC-04: exactly the interval old is still current


def test_upc_04_exactly_fourteen_days_is_current() -> None:
    assert upcoming_freshness_state(day(-14), day(60), None, TODAY) is FreshnessState.CURRENT
    assert upcoming_freshness_state(day(-15), day(60), None, TODAY) is FreshnessState.RECHECK_DUE


# PRI-01: blocking facts


def test_pri_01_skips_answered_questions_before_a_blocked_one() -> None:
    a = app((S.AI_DRAFT, ("country",)), (S.MISSING_FACTS, ("trl",)))
    tasks = applying_tasks(
        [opp(decision=Decision.PURSUING, deadline=5, application=a)], frozenset({"country"}), TODAY
    )
    assert names(tasks)[0] == "add_fact:Call:trl"


def test_pri_01_tie_goes_to_the_earliest_question_not_the_name() -> None:
    a = app((S.MISSING_FACTS, ("trl",)), (S.MISSING_FACTS, ("sector",)))
    tasks = applying_tasks(
        [opp(decision=Decision.PURSUING, deadline=5, application=a)], frozenset(), TODAY
    )
    assert names(tasks)[0] == "add_fact:Call:trl"


def test_pri_01_beats_review_drafts_with_an_earlier_deadline() -> None:
    drafts = opp(
        "A", decision=Decision.PURSUING, deadline=2, application=app((S.AI_DRAFT, ("country",)))
    )
    blocked = opp(
        "B", decision=Decision.PURSUING, deadline=10, application=app((S.MISSING_FACTS, ("trl",)))
    )
    tasks = applying_tasks([drafts, blocked], frozenset({"country"}), TODAY)
    assert names(tasks)[:2] == ["add_fact:B:trl", "review_drafts:A:"]


def test_pri_01_a_repeated_fact_does_not_hide_later_facts() -> None:
    def blocked(name: str, deadline: int, fact: str) -> OpportunitySnapshot:
        return opp(
            name,
            decision=Decision.PURSUING,
            deadline=deadline,
            application=app((S.MISSING_FACTS, (fact,))),
        )

    tasks = applying_tasks(
        [blocked("A", 3, "trl"), blocked("B", 4, "trl"), blocked("C", 5, "sector")],
        frozenset(),
        TODAY,
    )
    assert names(tasks) == ["add_fact:A:trl", "add_fact:C:sector"]


# PRI-04, PRI-08: tasks carry their deadline and scope, and sort by them


def test_pri_08_within_a_rule_sorted_by_deadline_then_blue() -> None:
    opps = [
        opp("Late", FitStatus.CONFIRMED, deadline=9),
        opp("Early", FitStatus.CONFIRMED, deadline=3, blue=False),
        opp("Early blue", FitStatus.CONFIRMED, deadline=3),
    ]
    tasks = applying_tasks(opps, frozenset(), TODAY)
    assert [t.opportunity for t in tasks] == ["Early blue", "Early", "Late"]
    assert tasks[1] == Task(TaskType.START_APPLICATION, "Early", day(3), False)


# PRI-13 to PRI-16: preparing tasks


def test_pri_13_fact_ties_by_earliest_date() -> None:
    opps = [opp(unknown=("trl",), deadline=20), opp(unknown=("sector",), deadline=30)]
    tasks = preparing_tasks(opps, frozenset(), TODAY, TODAY)
    assert [t.fact for t in tasks] == ["trl", "sector"]
    assert tasks[0] == Task(TaskType.ADD_FACT, None, day(20), False, "trl", 1)


def test_pri_13_a_fact_for_a_rolling_call_has_no_date() -> None:
    tasks = preparing_tasks([opp(unknown=("trl",), deadline=None)], frozenset(), TODAY, TODAY)
    assert tasks == [Task(TaskType.ADD_FACT, None, None, False, "trl", 1)]


def test_pri_13_candidates_from_rules_and_questions_together() -> None:
    o = opp(
        decision=Decision.PURSUING,
        unknown=("sector",),
        questions=(QuestionSnapshot(S.MISSING_FACTS, frozenset({"trl"})),),
    )
    assert {t.fact for t in preparing_tasks([o], frozenset(), TODAY, TODAY)} == {"sector", "trl"}


def test_pri_14_to_16_task_fields() -> None:
    opps = [
        opp("Lab", deadline=None, upcoming=True, opening=5, blue=False),
        opp("Back", decision=Decision.LATER, returned=True, deadline=90, upcoming=True, opening=12),
    ]
    tasks = preparing_tasks(opps, frozenset(), None, TODAY)
    assert tasks == [
        Task(TaskType.DECIDE, "Lab", day(5), False),
        Task(TaskType.BACK_ON_LIST, "Back", day(12), True),
        Task(TaskType.CHECK_GOALS, None, None, False),
    ]


def test_pri_13_a_dated_fact_before_an_undated_one() -> None:
    opps = [opp(unknown=("sector",), deadline=None), opp(unknown=("trl",), deadline=40)]
    assert [t.fact for t in preparing_tasks(opps, frozenset(), TODAY, TODAY)] == ["trl", "sector"]
