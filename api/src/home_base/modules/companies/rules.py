"""Rules for companies: intent, and the values a company fact may take.

Every public function quotes the rule IDs it implements, as listed in
docs/rules/intent.yaml and docs/rules/matching.yaml. Pure functions only.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime

from home_base.config import FACT_VALUES, GOALS_SERVED_BY_TYPE
from home_base.core.errors import ClockError, IntentError
from home_base.core.vocabulary import OpportunityType
from home_base.modules.companies.domain import GoalChoice, IntentRecord


def intent_record(goals: Sequence[GoalChoice], recorded_at: datetime) -> IntentRecord:
    """A validated intent record.

    Rule INT-01: intent = goals from a fixed list, each with a window of now,
    soon or later. At least one goal; a goal appears once, with one window.
    Rule INT-02: each intent change adds a dated record.
    """
    if recorded_at.tzinfo is None:
        raise ClockError("recorded_at must be timezone-aware")
    if not goals:
        raise IntentError("an intent needs at least one goal")
    if len({g.goal for g in goals}) != len(goals):
        raise IntentError("each goal appears once, with one window")
    return IntentRecord(tuple(goals), recorded_at)


def current_intent(records: Iterable[IntentRecord]) -> IntentRecord | None:
    """The current intent, or None when the founder has set none.

    Rule INT-02: the latest record is current; earlier ones stay in the history.
    """
    ordered = sorted(records, key=lambda r: r.recorded_at)
    if len(ordered) >= 2 and ordered[-1].recorded_at == ordered[-2].recorded_at:
        raise IntentError("two intent records at the same instant")
    return ordered[-1] if ordered else None


def serves_current_goal(types: Iterable[OpportunityType], intent: IntentRecord | None) -> bool:
    """Whether an opportunity is listed with the goal-relevant ones, before "Other matches".

    Rule INT-03: intent orders and groups opportunities; it never changes a fit
    status (fit takes no intent input). An opportunity serves every goal its
    types serve, and is goal-relevant when one of them is in the current
    intent, whatever the window; with no intent, none is (decision D-43).
    """
    if intent is None:
        return False
    current = {choice.goal.value for choice in intent.goals}
    return any(GOALS_SERVED_BY_TYPE[t.value] & current for t in types)


def fact_value_allowed(key: str, value: object) -> bool:
    """Rule REQ-09: a fact with a fixed list (country, sector, legal form, consortium
    need) only takes a value from it; other facts are not limited here (D-76)."""
    listed = FACT_VALUES.get(key)
    return listed is None or value in {v for v, _ in listed}
