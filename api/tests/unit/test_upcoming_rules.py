"""Upcoming-opportunity rules (UPC-01, UPC-02, UPC-04, UPC-05): edges and invariants."""

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from home_base.core.dates import months_before
from home_base.core.errors import ClockError, OpportunityStateError, VerificationError
from home_base.modules.opportunities.domain import (
    Evidence,
    EvidenceKind,
    FreshnessState,
    Month,
    OpportunityStatus,
)
from home_base.modules.opportunities.rules import (
    based_on_last_edition,
    evidence_counts,
    opportunity_status,
    upcoming_freshness_state,
    upcoming_is_shown,
    upcoming_review_interval_days,
)

TODAY = date(2026, 11, 9)
OPEN = OpportunityStatus.OPEN
UPCOMING = OpportunityStatus.UPCOMING
CLOSED = OpportunityStatus.CLOSED


def day(offset: int | None) -> date | None:
    return None if offset is None else TODAY + timedelta(days=offset)


# Month: the expected-month value


def test_month_first_day() -> None:
    assert Month(2026, 12).first_day == date(2026, 12, 1)


@pytest.mark.parametrize("month", [0, 13, -1])
def test_month_out_of_range_is_refused(month: int) -> None:
    with pytest.raises(ClockError):
        Month(2026, month)


# UPC-01: status boundaries (decision D-18)


@pytest.mark.parametrize(
    ("opening_in", "deadline_in", "expected"),
    [
        (1, 60, UPCOMING),  # opens tomorrow
        (0, 60, OPEN),  # the opening day counts as Open
        (-30, 0, OPEN),  # the deadline day is still open (D-15)
        (-30, -1, CLOSED),  # Closed from the day after the deadline
        (1, None, UPCOMING),  # rolling call not open yet
        (-1, None, OPEN),  # rolling call never closes
    ],
)
def test_upc_01_official_opening_boundaries(
    opening_in: int, deadline_in: int | None, expected: OpportunityStatus
) -> None:
    assert opportunity_status(day(opening_in), None, day(deadline_in), TODAY) is expected


@pytest.mark.parametrize(
    "month",
    [Month(2026, 10), Month(2026, 11), Month(2026, 12)],  # passed, current, future
)
def test_upc_01_expected_month_alone_stays_upcoming(month: Month) -> None:
    # Only a check that records the published call's opening date makes it Open.
    assert opportunity_status(None, month, None, TODAY) is UPCOMING


def test_upc_01_official_opening_wins_over_expected_month() -> None:
    assert opportunity_status(day(-1), Month(2027, 3), None, TODAY) is OPEN
    assert opportunity_status(day(1), Month(2026, 10), None, TODAY) is UPCOMING


def test_upc_01_neither_date_is_open_until_the_deadline() -> None:
    assert opportunity_status(None, None, None, TODAY) is OPEN
    assert opportunity_status(None, None, day(0), TODAY) is OPEN
    assert opportunity_status(None, None, day(-1), TODAY) is CLOSED


@given(
    st.one_of(st.none(), st.integers(min_value=-400, max_value=400)),
    st.one_of(st.none(), st.builds(Month, st.integers(2024, 2028), st.integers(1, 12))),
    st.one_of(st.none(), st.integers(min_value=-400, max_value=400)),
)
def test_upc_01_a_passed_deadline_is_always_closed(
    opening_in: int | None, month: Month | None, deadline_in: int | None
) -> None:
    status = opportunity_status(day(opening_in), month, day(deadline_in), TODAY)
    deadline_passed = deadline_in is not None and deadline_in < 0
    assert (status is CLOSED) == deadline_passed


# months_before: calendar months back, clamped to the month's last day (decision D-20)


@pytest.mark.parametrize(
    ("day_", "months", "expected"),
    [
        (date(2026, 11, 9), 18, date(2025, 5, 9)),
        (date(2026, 8, 31), 18, date(2025, 2, 28)),  # no 31 February: last day
        (date(2028, 8, 31), 6, date(2028, 2, 29)),  # leap year
        (date(2026, 1, 15), 1, date(2025, 12, 15)),  # across the year
        (date(2026, 3, 31), 0, date(2026, 3, 31)),
    ],
)
def test_months_before(day_: date, months: int, expected: date) -> None:
    assert months_before(day_, months) == expected


def test_months_before_refuses_negative_months() -> None:
    with pytest.raises(ClockError):
        months_before(TODAY, -1)


# UPC-05: evidence age (decisions D-20, D-21)


def ev(dated: date, kind: EvidenceKind = EvidenceKind.PREVIOUS_EDITION) -> Evidence:
    return Evidence(kind, dated, "https://example.org")


@pytest.mark.parametrize(
    ("dated", "expected"),
    [
        (date(2025, 5, 9), True),  # exactly 18 months still counts
        (date(2025, 5, 8), False),  # one day older does not
        (TODAY, True),
    ],
)
def test_upc_05_evidence_age_boundary(dated: date, expected: bool) -> None:
    assert evidence_counts(ev(dated), TODAY) is expected
    assert evidence_counts(ev(dated, EvidenceKind.ANNOUNCEMENT), TODAY) is expected


def test_upc_05_month_end_boundary() -> None:
    today = date(2026, 8, 31)
    assert evidence_counts(ev(date(2025, 2, 28)), today) is True
    assert evidence_counts(ev(date(2025, 2, 27)), today) is False


def test_upc_05_future_evidence_is_refused() -> None:
    with pytest.raises(VerificationError):
        evidence_counts(ev(TODAY + timedelta(days=1)), TODAY)


# UPC-02: when an upcoming opportunity is shown


MARCH = Month(2027, 3)
FRESH = ev(date(2026, 3, 2))
STALE = ev(date(2025, 5, 8))


def test_upc_02_official_opening_is_shown_without_evidence() -> None:
    assert upcoming_is_shown(date(2027, 2, 1), None, [], TODAY) is True
    assert upcoming_is_shown(date(2027, 2, 1), MARCH, [STALE], TODAY) is True


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ([], False),  # empty: never shown
        ([STALE], False),  # only stale evidence: hidden (UPC-05)
        ([FRESH], True),
        ([STALE, FRESH], True),  # new evidence unhides it (D-21)
    ],
)
def test_upc_02_expected_month_needs_evidence_that_counts(
    evidence: list[Evidence], expected: bool
) -> None:
    assert upcoming_is_shown(None, MARCH, evidence, TODAY) is expected


def test_upc_02_no_date_at_all_is_not_shown_as_upcoming() -> None:
    assert upcoming_is_shown(None, None, [FRESH], TODAY) is False


# UPC-04: review interval for an upcoming opportunity (decisions D-15, D-19)


@pytest.mark.parametrize(
    ("opening_in", "expected"),
    [(1, 7), (29, 7), (30, 7), (31, 14), (365, 14)],
)
def test_upc_04_official_opening_interval_boundaries(opening_in: int, expected: int) -> None:
    assert upcoming_review_interval_days(day(opening_in), None, TODAY) == expected


@pytest.mark.parametrize(
    ("today", "month", "expected"),
    [
        (date(2026, 10, 31), Month(2026, 12), 14),  # 1 December is 31 days away
        (date(2026, 11, 1), Month(2026, 12), 7),  # 30 days away
        (date(2026, 12, 1), Month(2026, 12), 7),  # the 1st itself
        (date(2026, 12, 31), Month(2026, 12), 7),  # still inside the expected month
    ],
)
def test_upc_04_expected_month_interval_boundaries(
    today: date, month: Month, expected: int
) -> None:
    assert upcoming_review_interval_days(None, month, today) == expected


def test_upc_04_expected_month_passed_is_recheck_due_even_just_checked() -> None:
    month = Month(2026, 12)
    assert upcoming_freshness_state(date(2026, 12, 31), None, month, date(2026, 12, 31)) is (
        FreshnessState.CURRENT
    )
    assert upcoming_freshness_state(date(2027, 1, 1), None, month, date(2027, 1, 1)) is (
        FreshnessState.RECHECK_DUE
    )


def test_upc_04_official_opening_wins_over_a_passed_expected_month() -> None:
    # A recorded opening date means the call is published: no "month passed" re-check.
    state = upcoming_freshness_state(TODAY, day(10), Month(2026, 10), TODAY)
    assert state is FreshnessState.CURRENT


def test_upc_04_never_verified_is_recheck_due() -> None:
    assert upcoming_freshness_state(None, day(60), None, TODAY) is FreshnessState.RECHECK_DUE
    assert upcoming_freshness_state(None, None, Month(2027, 6), TODAY) is FreshnessState.RECHECK_DUE


def test_upc_04_future_last_verified_is_refused() -> None:
    with pytest.raises(VerificationError):
        upcoming_freshness_state(day(1), day(60), None, TODAY)


@pytest.mark.parametrize(
    ("opening_in", "month"),
    [(0, None), (-5, None), (None, None)],  # opening reached, or no opening at all
)
def test_upc_04_refuses_an_opportunity_that_is_not_upcoming(
    opening_in: int | None, month: Month | None
) -> None:
    with pytest.raises(OpportunityStateError):
        upcoming_review_interval_days(day(opening_in), month, TODAY)
    with pytest.raises(OpportunityStateError):
        upcoming_freshness_state(TODAY, day(opening_in), month, TODAY)


# UPC-03: the last edition's data, labelled, until the call is published (D-42)


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        (Month(2026, 10), True),  # month passed with no call: still unpublished (Re-check due)
        (Month(2026, 11), True),  # this month
        (Month(2027, 3), True),
    ],
)
def test_upc_03_expected_month_alone_uses_the_last_edition(month: Month, expected: bool) -> None:
    assert based_on_last_edition(None, month, None, TODAY) is expected


@pytest.mark.parametrize("opening_in", [-1, 0, 1, 120])
def test_upc_03_a_recorded_opening_date_means_published(opening_in: int) -> None:
    opening = TODAY + timedelta(days=opening_in)
    assert based_on_last_edition(opening, Month(2027, 3), None, TODAY) is False
    assert based_on_last_edition(opening, None, None, TODAY) is False


@pytest.mark.parametrize(("deadline_in", "expected"), [(-1, False), (0, True), (None, True)])
def test_upc_03_closed_is_never_labelled(deadline_in: int | None, expected: bool) -> None:
    deadline = None if deadline_in is None else TODAY + timedelta(days=deadline_in)
    assert based_on_last_edition(None, Month(2027, 3), deadline, TODAY) is expected


def test_upc_03_an_open_call_without_dates_is_not_labelled() -> None:
    assert based_on_last_edition(None, None, None, TODAY) is False
