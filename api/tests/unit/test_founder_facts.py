"""REQ-06, REQ-07: optional founder facts (decision D-44)."""

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from home_base.config import FOUNDER_FACT_KEYS, HARD_RULE_FACT_KEYS, PERSONAL_FACT_KEYS
from home_base.core.errors import EligibilityRuleError
from home_base.core.vocabulary import Operator
from home_base.modules.matching.domain import FactSnapshot, HardRequirement, RequirementResult
from home_base.modules.matching.rules import evaluate_requirement, founder_age, founder_age_fact
from home_base.modules.today.domain import Milestone
from home_base.modules.today.rules import new_milestones

TODAY = date(2026, 11, 10)
BORN = date(1997, 6, 15)


# REQ-06: age in whole years on the deadline, or today for a rolling call


@pytest.mark.parametrize(
    ("deadline", "expected"),
    [
        (date(2027, 6, 14), 29),  # the day before the birthday
        (date(2027, 6, 15), 30),  # the birthday counts
        (date(2027, 6, 16), 30),
        (None, 29),  # rolling: measured today
    ],
)
def test_req_06_age_on_the_deadline(deadline: date | None, expected: int) -> None:
    assert founder_age(BORN, deadline, TODAY) == expected


def test_req_06_the_deadline_wins_over_today() -> None:
    """Even when today is past the birthday, a deadline before it decides (D-44)."""
    assert founder_age(BORN, date(2027, 6, 1), date(2027, 6, 20)) == 29


@pytest.mark.parametrize(
    ("on", "expected"),
    [(date(2027, 2, 28), 22), (date(2027, 3, 1), 23), (date(2028, 2, 29), 24)],
)
def test_req_06_born_on_29_february(on: date, expected: int) -> None:
    assert founder_age(date(2004, 2, 29), on, TODAY) == expected


def test_req_06_born_on_the_deadline_is_zero() -> None:
    assert founder_age(TODAY, TODAY, TODAY) == 0


def test_req_06_a_birth_date_after_the_reference_day_is_refused() -> None:
    with pytest.raises(EligibilityRuleError, match="birth date 2026-11-11 is in the future"):
        founder_age(TODAY + timedelta(days=1), TODAY + timedelta(days=1), TODAY)
    with pytest.raises(EligibilityRuleError, match="after 2026-12-31"):
        founder_age(date(2026, 12, 31) + timedelta(days=1), date(2026, 12, 31), date(2027, 2, 1))


@given(born=st.dates(min_value=date(1900, 1, 1), max_value=TODAY), days=st.integers(0, 40_000))
def test_req_06_age_never_decreases(born: date, days: int) -> None:
    later = TODAY + timedelta(days=days)
    assert founder_age(born, later, TODAY) >= founder_age(born, TODAY, TODAY)


@pytest.mark.parametrize(
    ("deadline", "expected"),
    [
        (date(2027, 6, 14), RequirementResult.PASS),  # 29, limit "up to 29"
        (date(2027, 6, 15), RequirementResult.FAIL),  # turns 30 on the deadline
    ],
)
def test_req_06_age_limit_boundary(deadline: date, expected: RequirementResult) -> None:
    fact = founder_age_fact(BORN, deadline, TODAY)
    rule = HardRequirement("founder_age", Operator.AT_MOST, 29, "up to 29")
    assert evaluate_requirement(rule, [] if fact is None else [fact]) is expected


# REQ-07: optional, missing or deleted gives Unknown


def test_req_07_no_birth_date_gives_no_age_and_unknown() -> None:
    assert founder_age_fact(None, date(2027, 6, 14), TODAY) is None
    rule = HardRequirement("founder_age", Operator.AT_MOST, 29, "up to 29")
    assert evaluate_requirement(rule, []) is RequirementResult.UNKNOWN


@pytest.mark.parametrize("key", ["woman_founder", "woman_ceo"])
def test_req_07_women_facts_missing_or_unapproved_give_unknown(key: str) -> None:
    rule = HardRequirement(key, Operator.EQUALS, True, "q")
    assert evaluate_requirement(rule, []) is RequirementResult.UNKNOWN
    unapproved = [FactSnapshot(key, True, approved=False)]
    assert evaluate_requirement(rule, unapproved) is RequirementResult.UNKNOWN
    assert evaluate_requirement(rule, [FactSnapshot(key, True, True)]) is RequirementResult.PASS
    assert evaluate_requirement(rule, [FactSnapshot(key, False, True)]) is RequirementResult.FAIL


def test_req_07_founder_facts_stay_out_of_the_milestone() -> None:
    assert not FOUNDER_FACT_KEYS & HARD_RULE_FACT_KEYS
    reached = new_milestones(frozenset(HARD_RULE_FACT_KEYS), [], frozenset())
    assert Milestone.HARD_RULE_FACTS_FILLED in reached


def test_req_07_every_founder_fact_is_marked_personal() -> None:
    assert FOUNDER_FACT_KEYS <= PERSONAL_FACT_KEYS
    assert "youngest_founder_birth_date" in PERSONAL_FACT_KEYS
