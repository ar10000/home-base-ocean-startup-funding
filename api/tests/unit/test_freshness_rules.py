"""Freshness rules (FRS-01 to FRS-05, FRS-07) and days left (PRI-07): edges and invariants."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from home_base.core.dates import days_left, local_today
from home_base.core.errors import ClockError, VerificationError
from home_base.modules.opportunities.domain import (
    FreshnessState,
    SourcedValue,
    Verification,
    VerificationMethod,
)
from home_base.modules.opportunities.rules import (
    freshness_state,
    last_verified_date,
    resolve_sources,
    review_interval_days,
)

TODAY = date(2026, 11, 9)
MANUAL = VerificationMethod.MANUAL


# PRI-07: days left in the Lisbon calendar


def test_pri_07_late_evening_utc_is_already_tomorrow_in_lisbon_summer() -> None:
    # 23:30 UTC on 30 June is 00:30 on 1 July in Lisbon (UTC+1 in summer).
    assert local_today(datetime(2026, 6, 30, 23, 30, tzinfo=UTC)) == date(2026, 7, 1)


def test_pri_07_same_instant_in_winter_stays_on_the_same_day() -> None:
    # Lisbon is UTC+0 in winter.
    assert local_today(datetime(2026, 12, 30, 23, 30, tzinfo=UTC)) == date(2026, 12, 30)


def test_pri_07_dst_change_night_does_not_shift_the_count() -> None:
    before = local_today(datetime(2026, 3, 28, 23, 59, tzinfo=ZoneInfo("Europe/Lisbon")))
    after = local_today(datetime(2026, 3, 29, 0, 1, tzinfo=ZoneInfo("Europe/Lisbon")))
    assert days_left(date(2026, 4, 1), before) - days_left(date(2026, 4, 1), after) == 1


def test_pri_07_naive_datetimes_are_refused() -> None:
    with pytest.raises(ClockError):
        local_today(datetime(2026, 11, 9, 9, 0))  # noqa: DTZ001  (the point of the test)


# FRS-01: only manual checks set the last verified date


def test_frs_01_latest_manual_check_wins() -> None:
    checks = [Verification(date(2026, 10, 1), MANUAL), Verification(date(2026, 11, 2), MANUAL)]
    assert last_verified_date(checks, TODAY) == date(2026, 11, 2)


def test_frs_01_no_checks_means_never_verified() -> None:
    assert last_verified_date([], TODAY) is None


def test_frs_01_future_verification_is_refused() -> None:
    with pytest.raises(VerificationError):
        last_verified_date([Verification(TODAY + timedelta(days=1), MANUAL)], TODAY)


# FRS-02 / FRS-03: the interval switches exactly at 30 days


@pytest.mark.parametrize(
    ("days", "expected"),
    [(-1, 14), (0, 7), (1, 7), (29, 7), (30, 7), (31, 14), (365, 14)],
)
def test_frs_02_frs_03_interval_boundaries(days: int, expected: int) -> None:
    assert review_interval_days(TODAY + timedelta(days=days), TODAY) == expected


# FRS-04 / FRS-05: state boundaries


@pytest.mark.parametrize(
    ("age", "deadline_in", "expected"),
    [
        (0, 60, FreshnessState.CURRENT),
        (14, 60, FreshnessState.CURRENT),
        (15, 60, FreshnessState.RECHECK_DUE),
        (7, 10, FreshnessState.CURRENT),
        (8, 10, FreshnessState.RECHECK_DUE),
        (0, 0, FreshnessState.CURRENT),
        (0, -1, FreshnessState.CLOSED),
        (40, -1, FreshnessState.CLOSED),
    ],
)
def test_frs_04_frs_05_state_boundaries(
    age: int, deadline_in: int, expected: FreshnessState
) -> None:
    state = freshness_state(TODAY - timedelta(days=age), TODAY + timedelta(days=deadline_in), TODAY)
    assert state is expected


def test_frs_04_rolling_call_uses_the_default_interval_and_never_closes() -> None:
    assert freshness_state(TODAY - timedelta(days=14), None, TODAY) is FreshnessState.CURRENT
    assert freshness_state(TODAY - timedelta(days=15), None, TODAY) is FreshnessState.RECHECK_DUE


@pytest.mark.parametrize(
    ("deadline_in", "expected"),
    [
        (None, FreshnessState.RECHECK_DUE),
        (60, FreshnessState.RECHECK_DUE),
        (0, FreshnessState.RECHECK_DUE),
        (-1, FreshnessState.CLOSED),
    ],
)
def test_frs_04_never_verified_is_recheck_due(
    deadline_in: int | None, expected: FreshnessState
) -> None:
    # Decision D-17: never checked by hand is never current; a passed deadline still closes it.
    deadline = None if deadline_in is None else TODAY + timedelta(days=deadline_in)
    assert freshness_state(None, deadline, TODAY) is expected


def test_frs_04_future_last_verified_is_refused() -> None:
    with pytest.raises(VerificationError):
        freshness_state(TODAY + timedelta(days=1), None, TODAY)


@given(
    st.integers(min_value=0, max_value=400),
    st.one_of(st.none(), st.integers(min_value=-30, max_value=400)),
)
def test_frs_05_a_passed_deadline_is_always_closed_whatever_the_check(
    age: int, deadline_in: int | None
) -> None:
    deadline = None if deadline_in is None else TODAY + timedelta(days=deadline_in)
    state = freshness_state(TODAY - timedelta(days=age), deadline, TODAY)
    assert (state is FreshnessState.CLOSED) == (deadline is not None and deadline < TODAY)


# FRS-07: conflicting sources


def claim(value: str, official: bool) -> SourcedValue:
    return SourcedValue(value, official, "https://example.org")


def test_frs_07_no_claims_gives_no_value_and_no_recheck() -> None:
    result = resolve_sources([])
    assert (result.value, result.recheck_due) == (None, False)


def test_frs_07_two_official_sources_disagreeing_needs_a_recheck() -> None:
    result = resolve_sources([claim("30 Jan", True), claim("31 Jan", True)])
    assert (result.value, result.recheck_due) == (None, True)


@given(st.lists(st.tuples(st.sampled_from(["a", "b", "c"]), st.booleans()), max_size=6))
def test_frs_07_a_shown_value_always_comes_from_some_source(claims: list[tuple[str, bool]]) -> None:
    result = resolve_sources(claim(v, o) for v, o in claims)
    if result.value is not None:
        assert result.value in {v for v, _ in claims}
    assert not (result.recheck_due and result.value is not None)


def test_frs_07_agreeing_unofficial_sources_are_shown_without_a_recheck() -> None:
    # FRS-07 only applies when sources disagree; agreement needs no official source.
    result = resolve_sources([claim("30 Jan", False), claim("30 Jan", False)])
    assert (result.value, result.recheck_due) == ("30 Jan", False)
