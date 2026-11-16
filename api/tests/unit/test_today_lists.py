"""PRI-18 and PRI-19 ties: on the same date, blue-specific comes before all-sector (D-28),
even when the all-sector name sorts first."""

from datetime import date

from home_base.core.vocabulary import Decision, FitStatus
from home_base.modules.today.domain import (
    AnswerState,
    ApplicationSnapshot,
    OpportunitySnapshot,
    QuestionSnapshot,
)
from home_base.modules.today.rules import next_deadline, opening_soon

TODAY = date(2026, 11, 9)
DAY = date(2026, 11, 20)


def _snap(name: str, blue: bool, *, upcoming: bool) -> OpportunitySnapshot:
    app = ApplicationSnapshot((QuestionSnapshot(AnswerState.AI_DRAFT, frozenset({"trl"})),), False)
    return OpportunitySnapshot(
        name=name,
        blue_specific=blue,
        fit=FitStatus.POSSIBLE,
        decision=Decision.NONE,
        deadline=None if upcoming else DAY,
        application=None if upcoming else app,
        source_current=True,
        later_returned=False,
        unknown_hard_facts=frozenset(),
        upcoming=upcoming,
        opening=DAY if upcoming else None,
        questions=None,
    )


def test_pri_18_blue_specific_first_on_the_same_opening() -> None:
    found = opening_soon(
        [_snap("Alpha", False, upcoming=True), _snap("Zulu", True, upcoming=True)], TODAY
    )
    assert [o.name for o in found] == ["Zulu", "Alpha"]


def test_pri_19_blue_specific_first_on_the_same_deadline() -> None:
    found = next_deadline(
        [_snap("Alpha", False, upcoming=False), _snap("Zulu", True, upcoming=False)], TODAY
    )
    assert found is not None and found.name == "Zulu"
