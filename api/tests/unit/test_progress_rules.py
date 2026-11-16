"""Progress and readiness rules (PRG-01 to PRG-04, RDY-01): empty cases and boundaries."""

import pytest

from home_base.config import HARD_RULE_FACT_KEYS
from home_base.modules.matching.rules import APPLICANT_FORM_FACT
from home_base.modules.today.domain import (
    AnswerState,
    ApplicationSnapshot,
    ApplicationStatus,
    Milestone,
    QuestionSnapshot,
    Ratio,
)
from home_base.modules.today.rules import (
    answers_ready,
    application_status,
    is_draftable,
    new_milestones,
    readiness,
)

A = AnswerState


def q(state: AnswerState, *required: str) -> QuestionSnapshot:
    return QuestionSnapshot(state, frozenset(required))


def app(*states: AnswerState, submitted: bool = False) -> ApplicationSnapshot:
    return ApplicationSnapshot(tuple(q(s, "country") for s in states), submitted)


# PRG-01: answers ready = approved / total


def test_prg_01_counts_approved_answers() -> None:
    questions = [q(A.APPROVED), q(A.EDITED), q(A.AI_DRAFT), q(A.MISSING_FACTS)]
    assert answers_ready(questions) == Ratio(1, 4)


def test_prg_01_no_questions_is_hidden() -> None:
    assert answers_ready([]) is None


def test_ratio_reads_n_of_m() -> None:
    assert str(Ratio(6, 8)) == "6 of 8"


# PRG-02: draftable = every required fact approved; none listed is not draftable


@pytest.mark.parametrize(
    ("required", "approved", "expected"),
    [
        ({"country"}, {"country"}, True),
        ({"country", "trl"}, {"country", "trl", "sector"}, True),
        ({"country", "trl"}, {"country"}, False),
        ({"country"}, set(), False),
        (set(), {"country"}, False),  # D-24
        (set(), set(), False),
    ],
)
def test_prg_02_draftable(required: set[str], approved: set[str], expected: bool) -> None:
    assert is_draftable(q(A.MISSING_FACTS, *required), frozenset(approved)) is expected


# PRG-03: application status


@pytest.mark.parametrize(
    ("application", "expected"),
    [
        (app(), ApplicationStatus.NOT_STARTED),  # no questions can never be ready
        (app(A.MISSING_FACTS, A.MISSING_FACTS), ApplicationStatus.NOT_STARTED),
        (app(A.AI_DRAFT, A.MISSING_FACTS), ApplicationStatus.IN_PROGRESS),  # D-25
        (app(A.EDITED, A.MISSING_FACTS), ApplicationStatus.IN_PROGRESS),
        (app(A.APPROVED, A.MISSING_FACTS), ApplicationStatus.IN_PROGRESS),
        (app(A.APPROVED, A.APPROVED), ApplicationStatus.READY),
        (app(A.APPROVED, A.EDITED), ApplicationStatus.IN_PROGRESS),  # reopened (D-09)
        (app(A.APPROVED, A.EDITED, submitted=True), ApplicationStatus.SUBMITTED),
        (app(submitted=True), ApplicationStatus.SUBMITTED),
    ],
)
def test_prg_03_status(application: ApplicationSnapshot, expected: ApplicationStatus) -> None:
    assert application_status(application) is expected


# PRG-04: milestones from a fixed list, each shown once


ALL_HARD = frozenset(HARD_RULE_FACT_KEYS)


def test_prg_04_fixed_list() -> None:
    assert [m.value for m in Milestone] == [
        "first_fact_approved",
        "hard_rule_facts_filled",
        "first_answer_approved",
        "first_application_ready",
        "first_application_submitted",
    ]


def test_prg_04_hard_rule_fact_keys_cover_the_applicant_form() -> None:
    assert APPLICANT_FORM_FACT in HARD_RULE_FACT_KEYS
    assert len(HARD_RULE_FACT_KEYS) == 7


def test_prg_04_nothing_yet_gives_no_milestone() -> None:
    assert new_milestones(frozenset(), [], frozenset()) == []


def test_prg_04_hard_rule_facts_need_every_field() -> None:
    almost = ALL_HARD - {"trl"}
    assert Milestone.HARD_RULE_FACTS_FILLED not in new_milestones(almost, [], frozenset())
    assert Milestone.HARD_RULE_FACTS_FILLED in new_milestones(ALL_HARD, [], frozenset())


def test_prg_04_non_hard_rule_facts_do_not_fill_the_list() -> None:
    extra = frozenset({"website", "founder_bio"})
    assert new_milestones(extra, [], frozenset()) == [Milestone.FIRST_FACT_APPROVED]


def test_prg_04_application_milestones_in_list_order() -> None:
    apps = [app(A.APPROVED, A.APPROVED, submitted=True)]
    assert new_milestones(ALL_HARD, apps, frozenset()) == list(Milestone)


def test_prg_04_submitted_without_every_answer_approved_is_not_ready() -> None:
    apps = [app(A.APPROVED, A.EDITED, submitted=True)]
    found = new_milestones(frozenset(), apps, frozenset())
    assert found == [Milestone.FIRST_ANSWER_APPROVED, Milestone.FIRST_APPLICATION_SUBMITTED]


def test_prg_04_each_milestone_is_shown_once() -> None:
    apps = [app(A.APPROVED, A.APPROVED)]
    shown = frozenset(new_milestones(ALL_HARD, apps, frozenset()))
    assert new_milestones(ALL_HARD, apps, shown) == []


# RDY-01: readiness = draftable or approved / total


def test_rdy_01_counts_draftable_or_approved_once() -> None:
    questions = [q(A.APPROVED, "country"), q(A.MISSING_FACTS, "country"), q(A.EDITED, "trl")]
    assert readiness(questions, frozenset({"country"})) == Ratio(2, 3)


def test_rdy_01_approved_counts_even_if_a_fact_was_withdrawn() -> None:
    assert readiness([q(A.APPROVED, "trl")], frozenset()) == Ratio(1, 1)


@pytest.mark.parametrize("questions", [None, []])
def test_rdy_01_unknown_or_no_questions_is_hidden(
    questions: list[QuestionSnapshot] | None,
) -> None:
    assert readiness(questions, frozenset({"country"})) is None
