"""INT-03: goal relevance from opportunity types and the current intent (decision D-43)."""

from datetime import UTC, datetime

import pytest

from home_base.core.vocabulary import OpportunityType
from home_base.modules.companies.domain import Goal, GoalChoice, IntentRecord, Window
from home_base.modules.companies.rules import intent_record, serves_current_goal

AT = datetime(2026, 11, 9, 9, tzinfo=UTC)

# D-43, as confirmed: each type and the goals it serves.
EXPECTED = {
    OpportunityType.GRANT: {Goal.NON_DILUTIVE_FUNDING},
    OpportunityType.ACCELERATOR: {Goal.ACCELERATOR_PLACE},
    OpportunityType.TESTBED_OR_PILOT: {Goal.PILOT_OR_TEST_SITE},
    OpportunityType.PROCUREMENT_CHALLENGE: {Goal.PILOT_OR_TEST_SITE, Goal.FIRST_CUSTOMERS},
    OpportunityType.PRIZE: {Goal.NON_DILUTIVE_FUNDING},
    OpportunityType.INVESTOR_PROGRAMME: {Goal.INVESTMENT},
}


def _intent(*goals: Goal, window: Window = Window.NOW) -> IntentRecord:
    return intent_record([GoalChoice(g, window) for g in goals], AT)


@pytest.mark.parametrize("kind", list(OpportunityType))
@pytest.mark.parametrize("goal", list(Goal))
def test_int_03_every_type_and_goal_pair(kind: OpportunityType, goal: Goal) -> None:
    expected = goal in EXPECTED[kind]
    assert serves_current_goal(frozenset({kind}), _intent(goal)) is expected


def test_int_03_every_type_serves_some_goal() -> None:
    assert set(EXPECTED) == set(OpportunityType)


@pytest.mark.parametrize("window", list(Window))
def test_int_03_any_window_counts(window: Window) -> None:
    intent = _intent(Goal.INVESTMENT, window=window)
    assert serves_current_goal(frozenset({OpportunityType.INVESTOR_PROGRAMME}), intent) is True


def test_int_03_no_intent_means_nothing_is_relevant() -> None:
    assert serves_current_goal(frozenset(OpportunityType), None) is False


def test_int_03_an_opportunity_with_no_type_is_never_relevant() -> None:
    assert serves_current_goal(frozenset(), _intent(*Goal)) is False


def test_int_03_several_types_serve_the_union() -> None:
    both = frozenset({OpportunityType.ACCELERATOR, OpportunityType.GRANT})
    assert serves_current_goal(both, _intent(Goal.ACCELERATOR_PLACE)) is True
    assert serves_current_goal(both, _intent(Goal.NON_DILUTIVE_FUNDING)) is True
    assert serves_current_goal(both, _intent(Goal.INVESTMENT)) is False
