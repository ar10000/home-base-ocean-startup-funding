"""Today rules (PRI-01 to PRI-17, RDY-02) and Later returning (DEC-03)."""

from datetime import date, timedelta

import pytest

from home_base.config import TIME_ESTIMATE_MINUTES
from home_base.core.vocabulary import Decision, FitStatus
from home_base.modules.matching.rules import later_has_returned
from home_base.modules.today.domain import (
    AnswerState,
    ApplicationSnapshot,
    Mode,
    OpportunitySnapshot,
    QuestionSnapshot,
    Task,
    TaskType,
)
from home_base.modules.today.rules import (
    applying_tasks,
    counts_for_priorities,
    fact_unlocks,
    next_opening_date,
    preparing_tasks,
    task_sort_key,
    time_estimate_minutes,
    today_mode,
    today_plan,
)

TODAY = date(2026, 11, 9)


def day(offset: int | None) -> date | None:
    return None if offset is None else TODAY + timedelta(days=offset)


def application(*states: AnswerState, submitted: bool = False) -> ApplicationSnapshot:
    return ApplicationSnapshot(
        tuple(QuestionSnapshot(s, frozenset({"country"})) for s in states), submitted
    )


def opp(
    fit: FitStatus = FitStatus.POSSIBLE,
    decision: Decision = Decision.NONE,
    deadline_in: int | None = 60,
    app: ApplicationSnapshot | None = None,
    name: str = "Call",
    blue: bool = True,
    current: bool = True,
    returned: bool = False,
    unknown: tuple[str, ...] = (),
    upcoming: bool = False,
    opening_in: int | None = None,
    questions: tuple[QuestionSnapshot, ...] | None = None,
) -> OpportunitySnapshot:
    return OpportunitySnapshot(
        name,
        blue,
        fit,
        decision,
        day(deadline_in),
        app,
        current,
        returned,
        frozenset(unknown),
        upcoming,
        day(opening_in),
        questions,
    )


# PRI-08: ties go to the earliest deadline, then blue-specific, then name (D-28, D-37)


def test_pri_08_order() -> None:
    items = [
        (day(10), False, "Zeta"),
        (None, True, "Alpha"),  # rolling: after every dated one
        (day(5), False, "Beta"),
        (day(5), True, "gamma"),
        (day(5), True, "Delta"),
    ]
    ordered = sorted(items, key=lambda i: task_sort_key(*i))
    assert [i[2] for i in ordered] == ["Delta", "gamma", "Beta", "Zeta", "Alpha"]


# PRI-10: time estimates from a fixed table (D-27)


def test_pri_10_every_task_type_has_an_estimate() -> None:
    assert set(TIME_ESTIMATE_MINUTES) == {t.value for t in TaskType}


@pytest.mark.parametrize(
    ("task", "minutes"),
    [
        (TaskType.ADD_FACT, 10),
        (TaskType.REVIEW_DRAFTS, 5),
        (TaskType.START_APPLICATION, 20),
        (TaskType.DECIDE, 5),
        (TaskType.CHECK_GOALS, 5),
        (TaskType.ANSWER_ONE_QUESTION, 10),
        (TaskType.NEXT_ANSWER, 10),
        (TaskType.BACK_ON_LIST, 5),
    ],
)
def test_pri_10_table(task: TaskType, minutes: int) -> None:
    assert time_estimate_minutes(task) == minutes


# PRI-11: Applying or Preparing


def test_pri_11_nothing_is_preparing() -> None:
    assert today_mode([], TODAY) is Mode.PREPARING


@pytest.mark.parametrize(
    ("deadline_in", "expected"),
    [(0, Mode.APPLYING), (30, Mode.APPLYING), (31, Mode.PREPARING), (-1, Mode.PREPARING)],
)
def test_pri_11_confirmed_closing_within_30_days(deadline_in: int, expected: Mode) -> None:
    assert today_mode([opp(FitStatus.CONFIRMED, deadline_in=deadline_in)], TODAY) is expected


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (Decision.NONE, Mode.APPLYING),
        (Decision.PURSUING, Mode.APPLYING),
        (Decision.LATER, Mode.PREPARING),
        (Decision.NOT_FOR_US, Mode.PREPARING),
    ],
)
def test_pri_11_confirmed_needs_no_decision_or_pursuing(decision: Decision, expected: Mode) -> None:
    assert today_mode([opp(FitStatus.CONFIRMED, decision, 10)], TODAY) is expected


def test_pri_11_a_possible_match_closing_soon_is_not_enough() -> None:
    assert today_mode([opp(FitStatus.POSSIBLE, deadline_in=10)], TODAY) is Mode.PREPARING


def test_pri_11_rolling_confirmed_match_is_not_closing() -> None:
    assert today_mode([opp(FitStatus.CONFIRMED, deadline_in=None)], TODAY) is Mode.PREPARING


def test_pri_11_a_stale_source_never_decides_the_mode() -> None:
    """D-39: Re-check due leaves the opportunity out, for both ways into Applying."""
    stale_match = opp(FitStatus.CONFIRMED, deadline_in=10, current=False)
    app = application(AnswerState.AI_DRAFT)
    stale_app = opp(FitStatus.POSSIBLE, Decision.PURSUING, 200, app, current=False)
    assert today_mode([stale_match], TODAY) is Mode.PREPARING
    assert today_mode([stale_app], TODAY) is Mode.PREPARING
    assert today_mode([stale_match, opp(FitStatus.CONFIRMED, deadline_in=10)], TODAY) is (
        Mode.APPLYING
    )


def test_pri_11_not_eligible_never_decides_the_mode() -> None:
    """D-40: an application whose call became Not eligible does not keep Applying mode."""
    app = application(AnswerState.AI_DRAFT)
    gone = opp(FitStatus.NOT_ELIGIBLE, Decision.PURSUING, 200, app)
    assert today_mode([gone], TODAY) is Mode.PREPARING


@pytest.mark.parametrize(
    ("app", "deadline_in", "expected"),
    [
        (application(AnswerState.AI_DRAFT), 200, Mode.APPLYING),
        (application(AnswerState.AI_DRAFT), 0, Mode.APPLYING),  # deadline day still open
        (application(AnswerState.AI_DRAFT), -1, Mode.PREPARING),
        (application(AnswerState.AI_DRAFT), None, Mode.APPLYING),  # rolling never passes (D-37)
        (application(AnswerState.APPROVED), 200, Mode.APPLYING),  # ready counts (D-33)
        (application(AnswerState.APPROVED, submitted=True), 200, Mode.PREPARING),
        (application(AnswerState.MISSING_FACTS), 200, Mode.PREPARING),  # not started
        (application(), 200, Mode.PREPARING),
    ],
)
def test_pri_11_application_in_progress_or_ready(
    app: ApplicationSnapshot, deadline_in: int | None, expected: Mode
) -> None:
    candidate = opp(FitStatus.POSSIBLE, Decision.PURSUING, deadline_in, app)
    assert today_mode([candidate], TODAY) is expected


# PRI-12: which opportunities count for the priority lists


@pytest.mark.parametrize(
    ("decision", "returned", "current", "expected"),
    [
        (Decision.NONE, False, True, True),
        (Decision.PURSUING, False, True, True),
        (Decision.LATER, False, True, False),
        (Decision.LATER, True, True, True),
        (Decision.NOT_FOR_US, True, True, False),
        (Decision.NONE, False, False, False),  # source not current
        (Decision.LATER, True, False, False),
    ],
)
def test_pri_12_counts(decision: Decision, returned: bool, current: bool, expected: bool) -> None:
    assert counts_for_priorities(decision, returned, current, FitStatus.POSSIBLE) is expected
    assert counts_for_priorities(decision, returned, current, FitStatus.CONFIRMED) is expected


@pytest.mark.parametrize("decision", list(Decision))
def test_pri_12_not_eligible_never_counts(decision: Decision) -> None:
    """D-40: whatever the decision, return or source."""
    assert counts_for_priorities(decision, True, True, FitStatus.NOT_ELIGIBLE) is False


# DEC-03: Later returns once, 30 days before the deadline or opening (D-22, D-29, D-30)


@pytest.mark.parametrize(
    ("deadline_in", "opening_in", "expected"),
    [
        (30, None, True),
        (31, None, False),
        (0, None, True),
        (200, 30, True),  # upcoming: counts from the opening
        (200, 31, False),
        (20, 31, False),  # upcoming: the deadline does not bring it back early
        (20, -5, True),  # opening passed: the call is open, so the deadline counts
        (None, None, False),  # rolling: never returns by itself
        (None, 10, True),
    ],
)
def test_dec_03_return_boundaries(
    deadline_in: int | None, opening_in: int | None, expected: bool
) -> None:
    assert later_has_returned(day(deadline_in), day(opening_in), TODAY, False) is expected


def test_dec_03_returns_only_once() -> None:
    assert later_has_returned(day(5), None, TODAY, True) is False


# PRI-01 to PRI-06, PRI-09: the applying list

S = AnswerState
APPROVED = frozenset({"country"})


def qs(*items: tuple[AnswerState, tuple[str, ...]]) -> ApplicationSnapshot:
    return ApplicationSnapshot(tuple(QuestionSnapshot(s, frozenset(f)) for s, f in items), False)


def labels(tasks: list[Task]) -> list[str]:
    return [
        f"{t.type.value}:{t.opportunity}:{t.fact or t.count or t.question or ''}" for t in tasks
    ]


def test_pri_06_nothing_gives_the_all_set_state() -> None:
    assert applying_tasks([], APPROVED, TODAY) == []
    plan = today_plan([])
    assert plan.one_thing is None
    assert plan.needs_attention == ()


@pytest.mark.parametrize(
    ("deadline_in", "found"), [(14, True), (0, True), (15, False), (-1, False)]
)
def test_pri_01_due_within_14_days(deadline_in: int, found: bool) -> None:
    app = qs((S.MISSING_FACTS, ("trl",)))
    tasks = applying_tasks(
        [opp(deadline_in=deadline_in, decision=Decision.PURSUING, app=app)], APPROVED, TODAY
    )
    assert (labels(tasks)[:1] == ["add_fact:Call:trl"]) is found


def test_pri_01_the_fact_blocking_most_answers_ties_to_earliest_question() -> None:
    app = qs(
        (S.MISSING_FACTS, ("team_size",)),
        (S.MISSING_FACTS, ("trl", "team_size")),
        (S.MISSING_FACTS, ("trl",)),
        (S.MISSING_FACTS, ("sector",)),
    )
    tasks = applying_tasks(
        [opp(deadline_in=5, decision=Decision.PURSUING, app=app)], APPROVED, TODAY
    )
    assert labels(tasks)[0] == "add_fact:Call:team_size"  # 2 each; team_size asked first


def test_pri_01_one_add_fact_task_per_fact() -> None:
    a = opp(
        name="A", deadline_in=3, decision=Decision.PURSUING, app=qs((S.MISSING_FACTS, ("trl",)))
    )
    b = opp(
        name="B", deadline_in=4, decision=Decision.PURSUING, app=qs((S.MISSING_FACTS, ("trl",)))
    )
    assert labels(applying_tasks([b, a], APPROVED, TODAY)) == ["add_fact:A:trl"]


def test_pri_01_a_question_with_no_listed_facts_blocks_nothing() -> None:
    app = qs((S.MISSING_FACTS, ()))
    assert (
        applying_tasks([opp(deadline_in=5, decision=Decision.PURSUING, app=app)], APPROVED, TODAY)
        == []
    )


def test_pri_02_counts_ai_drafts_only() -> None:
    app = qs((S.AI_DRAFT, ("country",)), (S.AI_DRAFT, ("country",)), (S.EDITED, ("country",)))
    tasks = applying_tasks(
        [opp(deadline_in=10, decision=Decision.PURSUING, app=app)], APPROVED, TODAY
    )
    assert labels(tasks) == ["review_drafts:Call:2", "next_answer:Call:1"]


def test_pri_02_not_beyond_14_days() -> None:
    app = qs((S.AI_DRAFT, ("country",)))
    tasks = applying_tasks(
        [opp(deadline_in=15, decision=Decision.PURSUING, app=app)], APPROVED, TODAY
    )
    assert labels(tasks) == ["next_answer:Call:1"]


@pytest.mark.parametrize(
    ("deadline_in", "unknown", "found"),
    [(21, ("trl",), True), (22, ("trl",), False), (5, ("trl", "sector"), False), (5, (), False)],
)
def test_pri_03_possible_with_one_deciding_fact(
    deadline_in: int, unknown: tuple[str, ...], found: bool
) -> None:
    tasks = applying_tasks([opp(deadline_in=deadline_in, unknown=unknown)], APPROVED, TODAY)
    assert (labels(tasks) == ["answer_one_question:Call:trl"]) is found


@pytest.mark.parametrize(("deadline_in", "found"), [(30, True), (31, False), (None, False)])
def test_pri_04_confirmed_without_application(deadline_in: int | None, found: bool) -> None:
    tasks = applying_tasks([opp(FitStatus.CONFIRMED, deadline_in=deadline_in)], APPROVED, TODAY)
    assert (labels(tasks) == ["start_application:Call:"]) is found


def test_pri_04_not_when_an_application_exists() -> None:
    app = qs((S.APPROVED, ("country",)))
    tasks = applying_tasks([opp(FitStatus.CONFIRMED, deadline_in=5, app=app)], APPROVED, TODAY)
    assert tasks == []


def test_pri_05_first_drafted_or_edited_answer_in_the_earliest_application() -> None:
    late = opp(
        name="Late", deadline_in=90, decision=Decision.PURSUING, app=qs((S.EDITED, ("country",)))
    )
    early = opp(
        name="Early",
        deadline_in=60,
        decision=Decision.PURSUING,
        app=qs((S.APPROVED, ("country",)), (S.MISSING_FACTS, ("trl",)), (S.EDITED, ("country",))),
    )
    assert labels(applying_tasks([late, early], APPROVED, TODAY)) == ["next_answer:Early:3"]


def test_pri_05_skips_submitted_and_passed_applications() -> None:
    submitted = ApplicationSnapshot((QuestionSnapshot(S.EDITED, frozenset({"country"})),), True)
    passed = qs((S.EDITED, ("country",)))
    tasks = applying_tasks(
        [
            opp(name="S", deadline_in=60, decision=Decision.PURSUING, app=submitted),
            opp(name="P", deadline_in=-1, decision=Decision.PURSUING, app=passed),
        ],
        APPROVED,
        TODAY,
    )
    assert tasks == []


def test_pri_12_only_counted_opportunities_give_tasks() -> None:
    hidden = [
        opp(FitStatus.CONFIRMED, Decision.NOT_FOR_US, 5),
        opp(FitStatus.CONFIRMED, Decision.LATER, 5),
        opp(FitStatus.CONFIRMED, Decision.NONE, 5, current=False),
    ]
    assert applying_tasks(hidden, APPROVED, TODAY) == []
    back = opp(FitStatus.CONFIRMED, Decision.LATER, 5, returned=True)
    assert labels(applying_tasks([back], APPROVED, TODAY)) == ["start_application:Call:"]


def test_pri_01_to_05_priority_order_wins_over_deadline() -> None:
    blocked = opp(
        name="Z",
        deadline_in=14,
        decision=Decision.PURSUING,
        app=qs((S.MISSING_FACTS, ("trl",)), (S.AI_DRAFT, ("country",))),
    )
    start = opp(FitStatus.CONFIRMED, name="A", deadline_in=1)
    possible = opp(name="M", deadline_in=2, unknown=("sector",))
    assert labels(applying_tasks([start, possible, blocked], APPROVED, TODAY)) == [
        "add_fact:Z:trl",
        "review_drafts:Z:1",
        "answer_one_question:M:sector",
        "start_application:A:",
        "next_answer:Z:2",
    ]


def test_pri_09_next_three_after_the_one_thing() -> None:
    opps = [opp(FitStatus.CONFIRMED, name=n, deadline_in=i + 1) for i, n in enumerate("ABCDE")]
    plan = today_plan(applying_tasks(opps, APPROVED, TODAY))
    assert plan.one_thing is not None
    assert plan.one_thing.opportunity == "A"
    assert [t.opportunity for t in plan.needs_attention] == ["B", "C", "D"]


def test_pri_09_fewer_than_three() -> None:
    plan = today_plan(applying_tasks([opp(FitStatus.CONFIRMED, deadline_in=3)], APPROVED, TODAY))
    assert plan.needs_attention == ()


def test_pri_01_most_blocking_beats_asked_first() -> None:
    app = qs(
        (S.MISSING_FACTS, ("sector",)),
        (S.MISSING_FACTS, ("trl",)),
        (S.MISSING_FACTS, ("trl",)),
    )
    tasks = applying_tasks(
        [opp(deadline_in=5, decision=Decision.PURSUING, app=app)], APPROVED, TODAY
    )
    assert labels(tasks)[0] == "add_fact:Call:trl"  # D-31: blocks 2 answers, sector only 1


# RDY-02: unlocks per missing fact


def q1(*facts: str, state: AnswerState = AnswerState.MISSING_FACTS) -> QuestionSnapshot:
    return QuestionSnapshot(state, frozenset(facts))


def test_rdy_02_nothing_unlocks_nothing() -> None:
    unlocks = fact_unlocks("trl", [], frozenset())
    assert (unlocks.matches, unlocks.questions, unlocks.total) == (0, 0, 0)


def test_rdy_02_possible_matches_where_it_is_the_only_unknown() -> None:
    opps = [
        opp(unknown=("trl",)),
        opp(unknown=("trl", "sector")),
        opp(FitStatus.CONFIRMED, unknown=("trl",)),  # not a Possible match
        opp(unknown=("trl",), decision=Decision.NOT_FOR_US),  # does not count (D-38)
    ]
    assert fact_unlocks("trl", opps, frozenset()).matches == 1


def test_rdy_02_questions_across_upcoming_and_pursuing_only() -> None:
    questions = (q1("trl"), q1("trl", "sector"), q1("trl", state=AnswerState.APPROVED), q1())
    opps = [
        opp(decision=Decision.PURSUING, questions=questions),
        opp(upcoming=True, opening_in=40, questions=(q1("trl"),)),
        opp(decision=Decision.NONE, questions=(q1("trl"),)),  # open, not Pursuing
    ]
    assert fact_unlocks("trl", opps, frozenset()).questions == 2


def test_rdy_02_other_facts_already_approved_count() -> None:
    opps = [opp(decision=Decision.PURSUING, questions=(q1("trl", "sector"),))]
    assert fact_unlocks("trl", opps, frozenset({"sector"})).questions == 1


def test_rdy_02_an_approved_fact_unlocks_nothing() -> None:
    assert fact_unlocks("trl", [opp(unknown=("trl",))], frozenset({"trl"})).total == 0


def test_rdy_02_application_questions_win_over_the_call_list() -> None:
    app = ApplicationSnapshot((q1("trl"), q1("trl")), False)
    o = opp(decision=Decision.PURSUING, app=app, questions=(q1("trl"),))
    assert fact_unlocks("trl", [o], frozenset()).questions == 2


# PRI-13 to PRI-17: the preparing list

RECENT = TODAY - timedelta(days=10)


def prep(opps: list[OpportunitySnapshot], intent: date | None = RECENT) -> list[str]:
    return labels(preparing_tasks(opps, frozenset(), intent, TODAY))


def test_pri_17_nothing_gives_all_set_and_no_opening() -> None:
    assert prep([]) == []
    assert next_opening_date([]) is None


def test_pri_13_most_unlocks_first_and_none_without_unlocks() -> None:
    opps = [
        opp(name="A", unknown=("trl",), deadline_in=50),
        opp(name="B", unknown=("sector",), deadline_in=90),
        opp(name="C", unknown=("sector",), deadline_in=80),
        opp(name="D", unknown=("trl", "team_size"), deadline_in=10),  # two unknown: settles nothing
    ]
    assert prep(opps) == ["add_fact:None:sector", "add_fact:None:trl"]
    tasks = preparing_tasks(opps, frozenset(), RECENT, TODAY)
    assert [t.fact for t in tasks] == ["sector", "trl"]


def test_pri_13_ties_go_to_the_earliest_date_then_fact_name() -> None:
    opps = [opp(unknown=("trl",), deadline_in=30), opp(unknown=("sector",), deadline_in=20)]
    assert [t.fact for t in preparing_tasks(opps, frozenset(), RECENT, TODAY)] == ["sector", "trl"]
    same = [opp(unknown=("trl",), deadline_in=20), opp(unknown=("sector",), deadline_in=20)]
    assert [t.fact for t in preparing_tasks(same, frozenset(), RECENT, TODAY)] == ["sector", "trl"]


@pytest.mark.parametrize(
    ("opening_in", "decision", "found"),
    [
        (30, Decision.NONE, True),
        (31, Decision.NONE, False),
        (-3, Decision.NONE, True),  # expected month started, still upcoming (D-38)
        (10, Decision.PURSUING, False),
        (10, Decision.LATER, False),
    ],
)
def test_pri_14_upcoming_opening_within_30_days_with_no_decision(
    opening_in: int, decision: Decision, found: bool
) -> None:
    o = opp(name="Lab", decision=decision, deadline_in=None, upcoming=True, opening_in=opening_in)
    assert (prep([o]) == ["decide:Lab:"]) is found


def test_pri_15_later_once_returned() -> None:
    assert prep([opp(name="R", decision=Decision.LATER, returned=True)]) == ["back_on_list:R:"]
    assert prep([opp(name="R", decision=Decision.LATER, returned=False)]) == []


@pytest.mark.parametrize(
    ("intent", "found"),
    [(TODAY - timedelta(days=91), True), (TODAY - timedelta(days=90), False), (None, True)],
)
def test_pri_16_check_your_goals(intent: date | None, found: bool) -> None:
    assert (prep([], intent) == ["check_goals:None:"]) is found


def test_pri_13_to_16_priority_order() -> None:
    opps = [
        opp(name="Lab", deadline_in=None, upcoming=True, opening_in=5),
        opp(name="Back", decision=Decision.LATER, returned=True, deadline_in=3),
        opp(name="Poss", unknown=("trl",), deadline_in=90),
    ]
    assert prep(opps, None) == [
        "add_fact:None:trl",
        "decide:Lab:",
        "back_on_list:Back:",
        "check_goals:None:",
    ]


def test_pri_17_next_opening_skips_not_for_us_and_open_calls() -> None:
    opps = [
        opp(upcoming=True, opening_in=40, decision=Decision.LATER),
        opp(upcoming=True, opening_in=20, decision=Decision.NOT_FOR_US),
        opp(deadline_in=5),
    ]
    assert next_opening_date(opps) == TODAY + timedelta(days=40)


def test_pri_17_next_opening_skips_not_eligible() -> None:
    """D-40."""
    opps = [
        opp(FitStatus.NOT_ELIGIBLE, upcoming=True, opening_in=10),
        opp(upcoming=True, opening_in=40),
    ]
    assert next_opening_date(opps) == TODAY + timedelta(days=40)
    assert next_opening_date(opps[:1]) is None


def test_rdy_02_not_eligible_gives_no_unlocks() -> None:
    """D-40: neither its questions nor the preparing task they would rank."""
    gone = opp(
        FitStatus.NOT_ELIGIBLE,
        Decision.PURSUING,
        upcoming=True,
        opening_in=20,
        questions=(q1("trl"),),
    )
    assert fact_unlocks("trl", [gone], frozenset()).total == 0
    assert preparing_tasks([gone], frozenset(), RECENT, TODAY) == []


def test_pri_13_a_fact_that_only_a_question_needs() -> None:
    o = opp(decision=Decision.PURSUING, deadline_in=40, questions=(q1("trl"),))
    tasks = preparing_tasks([o], frozenset(), RECENT, TODAY)
    assert [(t.fact, t.count, t.deadline) for t in tasks] == [
        ("trl", 1, TODAY + timedelta(days=40))
    ]
