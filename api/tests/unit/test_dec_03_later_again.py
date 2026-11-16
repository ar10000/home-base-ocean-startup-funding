"""DEC-03 with D-60: when a Later was chosen again after the opportunity had returned."""

from datetime import date, datetime

import pytest

from home_base.core.vocabulary import Decision
from home_base.modules.matching.domain import DecisionChange
from home_base.modules.matching.rules import later_chosen_again_after_return

DEADLINE = date(2026, 12, 31)  # back on the list from 2026-12-01 (30 days before)


def _on(day: str, decision: Decision) -> DecisionChange:
    return DecisionChange(decision, datetime.fromisoformat(f"{day}T10:00:00+00:00"))


L, P = Decision.LATER, Decision.PURSUING


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ([], False),
        ([_on("2026-10-01", L)], False),  # one Later: returns on 2026-12-01
        ([_on("2026-12-05", L)], False),  # first Later inside the window: back now (D-60)
        ([_on("2026-10-01", L), _on("2026-12-02", P)], False),  # not on Later
        (
            [_on("2026-10-01", L), _on("2026-11-01", P), _on("2026-11-10", L)],
            False,
        ),  # before window
        ([_on("2026-10-01", L), _on("2026-11-01", P), _on("2026-11-30", L)], False),  # day 31
        ([_on("2026-10-01", L), _on("2026-11-01", P), _on("2026-12-01", L)], True),  # day 30
        ([_on("2026-10-01", L), _on("2026-12-02", P), _on("2026-12-05", L)], True),
        ([_on("2026-12-03", L), _on("2026-12-04", P), _on("2026-12-05", L)], True),
        ([_on("2026-12-05", L), _on("2026-12-02", P), _on("2026-10-01", L)], True),  # any order
        # The earlier Later need not be the first change, nor the one just before:
        (
            [
                _on("2026-10-01", P),
                _on("2026-10-15", L),
                _on("2026-11-01", P),
                _on("2026-12-05", L),
            ],
            True,
        ),
        ([_on("2026-10-01", P), _on("2026-12-02", L), _on("2026-12-05", L)], True),
        ([_on("2026-10-01", P), _on("2026-11-01", P), _on("2026-12-05", L)], False),
    ],
)
def test_dec_03_later_chosen_again_after_return(
    changes: list[DecisionChange], expected: bool
) -> None:
    assert later_chosen_again_after_return(changes, DEADLINE, None) is expected


def test_dec_03_a_call_with_no_date_never_counts_as_returned() -> None:
    changes = [_on("2026-10-01", L), _on("2026-11-01", P), _on("2026-12-05", L)]
    assert later_chosen_again_after_return(changes, None, None) is False


def test_dec_03_an_upcoming_call_counts_from_its_opening() -> None:
    opening = date(2027, 1, 15)  # back from 2026-12-16
    before = [_on("2026-10-01", L), _on("2026-11-01", P), _on("2026-12-15", L)]
    after = [_on("2026-10-01", L), _on("2026-11-01", P), _on("2026-12-16", L)]
    assert later_chosen_again_after_return(before, None, opening) is False
    assert later_chosen_again_after_return(after, None, opening) is True
