"""Intent rules (INT-01, INT-02): validation, history and the current record."""

from datetime import UTC, datetime, timedelta

import pytest

from home_base.core.errors import ClockError, IntentError
from home_base.modules.companies.domain import Goal, GoalChoice, Window
from home_base.modules.companies.rules import current_intent, intent_record

AT = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
INVEST_LATER = GoalChoice(Goal.INVESTMENT, Window.LATER)
PILOT_NOW = GoalChoice(Goal.PILOT_OR_TEST_SITE, Window.NOW)


# INT-01: goals from a fixed list, each with one window


def test_int_01_fixed_lists() -> None:
    assert {g.value for g in Goal} == {
        "pilot_or_test_site",
        "non_dilutive_funding",
        "accelerator_place",
        "first_customers",
        "investment",
    }
    assert [w.value for w in Window] == ["now", "soon", "later"]


def test_int_01_one_or_more_goals() -> None:
    record = intent_record([INVEST_LATER, PILOT_NOW], AT)
    assert record.goals == (INVEST_LATER, PILOT_NOW)
    assert record.recorded_at == AT


def test_int_01_no_goals_is_refused() -> None:
    with pytest.raises(IntentError):
        intent_record([], AT)


def test_int_01_a_goal_has_one_window() -> None:
    with pytest.raises(IntentError):
        intent_record([INVEST_LATER, GoalChoice(Goal.INVESTMENT, Window.NOW)], AT)


def test_int_01_naive_time_is_refused() -> None:
    with pytest.raises(ClockError):
        intent_record([PILOT_NOW], datetime(2026, 11, 9, 9, 0))  # noqa: DTZ001


# INT-02: every change adds a dated record; the latest is current


def test_int_02_no_records_means_no_current_intent() -> None:
    assert current_intent([]) is None


def test_int_02_latest_is_current_whatever_the_order() -> None:
    old = intent_record([INVEST_LATER], AT - timedelta(days=30))
    new = intent_record([PILOT_NOW], AT)
    assert current_intent([new, old]) == new
    assert current_intent([old, new]) == new


def test_int_02_two_records_at_the_same_instant_are_refused() -> None:
    with pytest.raises(IntentError):
        current_intent([intent_record([INVEST_LATER], AT), intent_record([PILOT_NOW], AT)])
