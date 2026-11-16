"""Every domain error carries a stable message: the API turns it into problem details."""

from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest

from home_base.core.errors import DomainError
from home_base.core.vocabulary import Decision, Operator
from home_base.modules.companies.domain import Goal, GoalChoice, Window
from home_base.modules.companies.rules import current_intent, intent_record
from home_base.modules.matching.domain import FactSnapshot, HardRequirement, NotForUsReason
from home_base.modules.matching.rules import (
    applicant_form_requirement,
    approved_value,
    current_decision,
    decision_change,
    evaluate_requirement,
)
from home_base.modules.opportunities.domain import (
    Evidence,
    EvidenceKind,
    Month,
    Verification,
    VerificationMethod,
)
from home_base.modules.opportunities.rules import (
    evidence_counts,
    freshness_state,
    last_verified_date,
    upcoming_freshness_state,
    upcoming_review_interval_days,
)

TODAY = date(2026, 11, 9)
AT = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
NAIVE = datetime(2026, 11, 9, 9, 0)  # noqa: DTZ001
GOAL = GoalChoice(Goal.INVESTMENT, Window.NOW)
LATER = date(2026, 11, 10)


def _num(op: Operator, rule: object, fact: object) -> None:
    req = HardRequirement("trl", op, rule, source_quote="q")  # type: ignore[arg-type]
    evaluate_requirement(req, [FactSnapshot("trl", fact, approved=True)])  # type: ignore[arg-type]


CASES: list[tuple[str, Callable[[], object], str]] = [
    (
        "naive intent time",
        lambda: intent_record([GOAL], NAIVE),
        "recorded_at must be timezone-aware",
    ),
    ("no goals", lambda: intent_record([], AT), "an intent needs at least one goal"),
    (
        "duplicate goal",
        lambda: intent_record([GOAL, GoalChoice(Goal.INVESTMENT, Window.LATER)], AT),
        "each goal appears once, with one window",
    ),
    (
        "same-instant intents",
        lambda: current_intent([intent_record([GOAL], AT), intent_record([GOAL], AT)]),
        "two intent records at the same instant",
    ),
    (
        "two approved facts",
        lambda: approved_value(
            "trl", [FactSnapshot("trl", 3, approved=True), FactSnapshot("trl", 4, approved=True)]
        ),
        "more than one approved fact for 'trl'",
    ),
    (
        "no applicant form",
        lambda: applicant_form_requirement(frozenset(), source_quote="q"),
        "a call must accept at least one applicant form",
    ),
    (
        "number rule on text",
        lambda: _num(Operator.AT_LEAST, 4, "high"),
        "at_least on 'trl' cannot compare str with int",
    ),
    (
        "equals with another type",
        lambda: _num(Operator.EQUALS, 4, "4"),
        "equals on 'trl' cannot compare str with int",
    ),
    (
        "one_of on a number",
        lambda: _num(Operator.ONE_OF, frozenset({"PT"}), 4),
        "one_of on 'trl' cannot compare int with frozenset",
    ),
    (
        "naive decision time",
        lambda: decision_change(Decision.LATER, NAIVE),
        "changed_at must be timezone-aware",
    ),
    (
        "reason on Later",
        lambda: decision_change(Decision.LATER, AT, NotForUsReason.OTHER),
        "only Not for us takes a reason",
    ),
    (
        "same-instant decisions",
        lambda: current_decision([decision_change(Decision.LATER, AT)] * 2),
        "two decision changes at the same instant",
    ),
    ("month 13", lambda: Month(2026, 13), "month must be 1 to 12, got 13"),
    (
        "future verification",
        lambda: last_verified_date([Verification(LATER, VerificationMethod.MANUAL)], TODAY),
        "verification dated in the future: 2026-11-10",
    ),
    (
        "future last verified",
        lambda: freshness_state(LATER, None, TODAY),
        "last verified date is in the future: 2026-11-10",
    ),
    (
        "future evidence",
        lambda: evidence_counts(Evidence(EvidenceKind.ANNOUNCEMENT, LATER, "https://x"), TODAY),
        "evidence dated in the future: 2026-11-10",
    ),
    (
        "opening reached",
        lambda: upcoming_review_interval_days(TODAY, None, TODAY),
        "opening date 2026-11-09 has been reached: the call is open",
    ),
    (
        "not upcoming",
        lambda: upcoming_review_interval_days(None, None, TODAY),
        "no opening date or expected month: not an upcoming call",
    ),
    (
        "future upcoming verification",
        lambda: upcoming_freshness_state(LATER, date(2027, 1, 1), None, TODAY),
        "last verified date is in the future: 2026-11-10",
    ),
]


@pytest.mark.parametrize(("raise_it", "message"), [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_error_message(raise_it: Callable[[], object], message: str) -> None:
    with pytest.raises(DomainError) as caught:
        raise_it()
    assert str(caught.value) == message
