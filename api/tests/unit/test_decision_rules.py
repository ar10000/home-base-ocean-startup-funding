"""Founder decision rules (DEC-01, DEC-02, DEC-04)."""

from datetime import UTC, datetime, timedelta

import pytest

from home_base.core.errors import ClockError, DecisionError
from home_base.core.vocabulary import Decision
from home_base.modules.matching.domain import (
    NotForUsReason,
)
from home_base.modules.matching.rules import (
    current_decision,
    decision_change,
    decision_on_application_start,
    shown_in_list,
)

AT = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)


# DEC-01: none, Pursuing, Later or Not for us; each change dated


def test_dec_01_no_change_means_none() -> None:
    assert current_decision([]) is Decision.NONE


def test_dec_01_latest_change_wins_whatever_the_order() -> None:
    later = decision_change(Decision.LATER, AT - timedelta(days=3))
    pursuing = decision_change(Decision.PURSUING, AT)
    assert current_decision([pursuing, later]) is Decision.PURSUING


def test_dec_01_any_decision_can_be_changed() -> None:
    for first in Decision:
        for second in Decision:
            changes = [decision_change(first, AT), decision_change(second, AT + timedelta(1))]
            assert current_decision(changes) is second


def test_dec_01_not_for_us_takes_an_optional_reason() -> None:
    assert decision_change(Decision.NOT_FOR_US, AT).reason is None
    change = decision_change(Decision.NOT_FOR_US, AT, NotForUsReason.TOO_EARLY)
    assert change.reason is NotForUsReason.TOO_EARLY
    assert {r.value for r in NotForUsReason} == {
        "not_relevant",
        "too_early",
        "too_much_work",
        "other",
    }


@pytest.mark.parametrize("decision", [Decision.NONE, Decision.PURSUING, Decision.LATER])
def test_dec_01_only_not_for_us_has_a_reason(decision: Decision) -> None:
    with pytest.raises(DecisionError):
        decision_change(decision, AT, NotForUsReason.OTHER)


def test_dec_01_two_changes_at_the_same_instant_are_refused() -> None:
    with pytest.raises(DecisionError):
        current_decision(
            [decision_change(Decision.LATER, AT), decision_change(Decision.PURSUING, AT)]
        )


def test_dec_01_naive_time_is_refused() -> None:
    with pytest.raises(ClockError):
        decision_change(Decision.LATER, datetime(2026, 11, 9, 9, 0))  # noqa: DTZ001


# DEC-02: starting an application sets Pursuing


@pytest.mark.parametrize("current", list(Decision))
def test_dec_02_starting_an_application_sets_pursuing(current: Decision) -> None:
    assert decision_on_application_start(current) is Decision.PURSUING


# DEC-04: Not for us is left out of the default list and shown under its filter


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (Decision.NONE, True),
        (Decision.PURSUING, True),
        (Decision.LATER, True),
        (Decision.NOT_FOR_US, False),
    ],
)
def test_dec_04_default_list(decision: Decision, expected: bool) -> None:
    assert shown_in_list(decision, None) is expected


@pytest.mark.parametrize("decision_filter", list(Decision))
def test_dec_04_a_decision_filter_shows_exactly_that_decision(decision_filter: Decision) -> None:
    for decision in Decision:
        assert shown_in_list(decision, decision_filter) is (decision is decision_filter)
