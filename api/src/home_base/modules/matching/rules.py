"""Matching rules: requirement results and fit status.

Every public function quotes the rule IDs it implements, as listed in
docs/rules/matching.yaml. Pure functions only: no I/O, no clock, no AI.
"""

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import assert_never

from home_base.config import LATER_RETURNS_DAYS_BEFORE, MIN_HARD_RULES_FOR_CONFIDENT_FIT
from home_base.core.dates import days_left, local_today
from home_base.core.errors import ClockError, DecisionError, EligibilityRuleError
from home_base.core.vocabulary import Decision, FitStatus, Operator
from home_base.modules.matching.domain import (
    ApplicantForm,
    DecisionChange,
    FactSnapshot,
    FactValue,
    FitResult,
    HardRequirement,
    NotForUsReason,
    RequirementOutcome,
    RequirementResult,
    SoftJudgement,
    StoredMatch,
)

APPLICANT_FORM_FACT = "applicant_form"
FOUNDER_AGE_FACT = "founder_age"


def approved_value(fact_key: str, facts: Iterable[FactSnapshot]) -> FactValue | None:
    """The approved value of a fact, or None when it is missing or not approved.

    Rule REQ-03: a hard rule is Unknown when its fact is missing or not approved.
    """
    matches = [f for f in facts if f.key == fact_key and f.approved and f.value is not None]
    if len(matches) > 1:
        raise EligibilityRuleError(f"more than one approved fact for {fact_key!r}")
    return matches[0].value if matches else None


def founder_age(birth_date: date, deadline: date | None, today: date) -> int:
    """The youngest founder's age in whole years on the day a call measures it.

    Rule REQ-06: a founder-age rule compares the youngest founder's age, on the
    call's deadline, with the call's limit. Always the deadline, so a match never
    changes on a birthday; a rolling call measures it today (decision D-44).
    A birthday on that day counts; someone born on 29 February turns a year
    older on 1 March in a non-leap year.
    """
    on = deadline if deadline is not None else today
    if birth_date > min(on, today):
        raise EligibilityRuleError(f"birth date {birth_date} is in the future or after {on}")
    before_birthday = (on.month, on.day) < (birth_date.month, birth_date.day)
    return on.year - birth_date.year - before_birthday


def founder_age_fact(
    approved_birth_date: date | None, deadline: date | None, today: date
) -> FactSnapshot | None:
    """The derived founder_age fact a call's hard rule checks, or None.

    Rule REQ-07: founder facts are optional; with no approved birth date (never
    given, or deleted) there is no founder_age fact, so its rule is Unknown
    (REQ-03), never Fail. The caller passes only an approved birth date.
    """
    if approved_birth_date is None:
        return None
    age = founder_age(approved_birth_date, deadline, today)
    return FactSnapshot(FOUNDER_AGE_FACT, age, approved=True)


def evaluate_requirement(
    requirement: HardRequirement, facts: Iterable[FactSnapshot]
) -> RequirementResult:
    """Check one hard requirement against the company's facts.

    Rule REQ-01: a hard rule passes when its approved fact meets it.
    Rule REQ-02: a hard rule fails when its approved fact does not meet it.
    Rule REQ-03: a hard rule is Unknown when its fact is missing or not approved.
    """
    value = approved_value(requirement.fact_key, facts)
    if value is None:
        return RequirementResult.UNKNOWN
    if _meets(requirement, value):
        return RequirementResult.PASS
    return RequirementResult.FAIL


def soft_result(judgement: SoftJudgement) -> RequirementResult:
    """The result shown for a soft criterion, whatever the AI concluded.

    Rule REQ-04: a soft criterion is shown as an AI judgement with confidence,
    never as pass or fail. The confidence travels with the judgement itself.
    """
    del judgement  # the judgement is displayed, never turned into pass or fail
    return RequirementResult.AI_JUDGEMENT


def applicant_form_requirement(
    accepted: frozenset[ApplicantForm], source_quote: str
) -> HardRequirement:
    """Build the hard requirement for how a company may apply.

    Rule REQ-05: applicant form (alone or consortium) is a hard rule; a
    consortium-only call fails for a company applying alone.
    """
    if not accepted:
        raise EligibilityRuleError("a call must accept at least one applicant form")
    return HardRequirement(
        fact_key=APPLICANT_FORM_FACT,
        operator=Operator.ONE_OF,
        value=frozenset(form.value for form in accepted),
        source_quote=source_quote,
    )


def hard_results(results: Iterable[RequirementResult]) -> list[RequirementResult]:
    """Keep only the results of hard rules.

    Rule FIT-05: soft criteria never change the fit status.
    """
    return [r for r in results if r is not RequirementResult.AI_JUDGEMENT]


def fit_status(results: Sequence[RequirementResult]) -> FitResult:
    """Fit status of one opportunity from its requirement results.

    Rule FIT-01: Confirmed when every hard rule passes.
    Rule FIT-02: Possible when no hard rule fails and at least one is Unknown.
    Rule FIT-03: Not eligible when any hard rule fails.
    Rule FIT-04: fewer than two hard rules gives Possible, with the note "few explicit rules".
    Rule FIT-05: soft criteria never change the fit status.

    Precedence: a failing hard rule always gives Not eligible, even when there
    are fewer than two hard rules (decision D-14 in docs/decisions.md).
    """
    hard = hard_results(results)
    few = len(hard) < MIN_HARD_RULES_FOR_CONFIDENT_FIT
    if RequirementResult.FAIL in hard:
        return FitResult(FitStatus.NOT_ELIGIBLE, few_explicit_rules=few)
    if few or RequirementResult.UNKNOWN in hard:
        return FitResult(FitStatus.POSSIBLE, few_explicit_rules=few)
    return FitResult(FitStatus.CONFIRMED, few_explicit_rules=False)


def _meets(requirement: HardRequirement, value: FactValue) -> bool:
    """Compare an approved fact value with a requirement, refusing mismatched types."""
    rule = requirement.value
    match requirement.operator:
        case Operator.EQUALS:
            if isinstance(rule, frozenset) or type(rule) is not type(value):
                raise _type_error(requirement, value)
            return value == rule
        case Operator.ONE_OF | Operator.NOT_ONE_OF:
            if not isinstance(rule, frozenset) or not isinstance(value, str):
                raise _type_error(requirement, value)
            inside = value in rule
            return inside if requirement.operator is Operator.ONE_OF else not inside
        case Operator.AT_LEAST | Operator.AT_MOST:
            if not (_is_number(rule) and _is_number(value)):
                raise _type_error(requirement, value)
            # Type narrowing only: the check above has already raised for anything else.
            assert isinstance(rule, int) and isinstance(value, int)  # pragma: no mutate
            return value >= rule if requirement.operator is Operator.AT_LEAST else value <= rule
        case unreachable:  # pragma: no cover  (mypy proves every operator is handled)
            assert_never(unreachable)  # pragma: no mutate


def _is_number(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _type_error(requirement: HardRequirement, value: FactValue) -> EligibilityRuleError:
    return EligibilityRuleError(
        f"{requirement.operator} on {requirement.fact_key!r} cannot compare "
        f"{type(value).__name__} with {type(requirement.value).__name__}"
    )


def decision_change(
    decision: Decision, changed_at: datetime, reason: NotForUsReason | None = None
) -> DecisionChange:
    """A validated decision change.

    Rule DEC-01: decision per opportunity is none, Pursuing, Later or Not for us;
    each change is dated. Only Not for us takes an (optional) reason.
    """
    if changed_at.tzinfo is None:
        raise ClockError("changed_at must be timezone-aware")
    if reason is not None and decision is not Decision.NOT_FOR_US:
        raise DecisionError("only Not for us takes a reason")
    return DecisionChange(decision, changed_at, reason)


def current_decision(changes: Iterable[DecisionChange]) -> Decision:
    """The current decision; none when the founder has made none.

    Rule DEC-01: every decision can be changed at any time; the latest change wins.
    """
    ordered = sorted(changes, key=lambda c: c.changed_at)
    if len(ordered) >= 2 and ordered[-1].changed_at == ordered[-2].changed_at:
        raise DecisionError("two decision changes at the same instant")
    return ordered[-1].decision if ordered else Decision.NONE


def decision_on_application_start(current: Decision) -> Decision:
    """The decision once an application is started.

    Rule DEC-02: starting an application sets Pursuing, whatever it was before.
    """
    del current  # every starting point leads to Pursuing
    return Decision.PURSUING


def shown_in_list(decision: Decision, decision_filter: Decision | None) -> bool:
    """Whether a match appears in the Opportunities list.

    Rule DEC-04: Not for us is left out of the default list (no filter) and
    visible under its filter; a decision filter shows exactly that decision.
    """
    if decision_filter is None:
        return decision is not Decision.NOT_FOR_US
    return decision is decision_filter


def later_has_returned(
    deadline: date | None, opening: date | None, today: date, chosen_again_after_return: bool
) -> bool:
    """Whether an opportunity on Later is back on the founder's list.

    Rule DEC-03: Later returns once, 30 days before the deadline or opening, as
    "Back on your list". Day 30 counts (D-22). An upcoming call counts from its
    opening; once open, from its deadline. It stays back until the founder
    changes the decision; Later chosen again after it returned never returns,
    and a call with no deadline or opening never returns by itself (D-29, D-30).
    """
    if chosen_again_after_return:
        return False
    return _in_return_window(deadline, opening, today)


def _in_return_window(deadline: date | None, opening: date | None, today: date) -> bool:
    basis = opening if opening is not None and opening > today else deadline
    return basis is not None and days_left(basis, today) <= LATER_RETURNS_DAYS_BEFORE


def later_chosen_again_after_return(
    changes: Sequence[DecisionChange], deadline: date | None, opening: date | None
) -> bool:
    """Whether the current Later was chosen again after the opportunity had returned.

    Rule DEC-03: Later chosen again after it returned never returns. The latest
    change is Later, an earlier change was Later too, and on the day of the latest
    one the opportunity was already back. Later chosen for the first time inside
    the window is back straight away (D-60).
    """
    ordered = sorted(changes, key=lambda c: c.changed_at)
    if not ordered or ordered[-1].decision is not Decision.LATER:
        return False
    if not any(c.decision is Decision.LATER for c in ordered[:-1]):
        return False
    chosen_on = local_today(ordered[-1].changed_at)
    return _in_return_window(deadline, opening, chosen_on)


def match_changed(
    stored: StoredMatch | None,
    fit: FitResult,
    outcomes: tuple[RequirementOutcome, ...],
    rule_version: str,
) -> bool:
    """Whether a recalculation stores a new match.

    Rule INT-04: an intent or fact change recalculates every match; nothing is
    deleted. A new match is stored only when the fit, a requirement's result, the
    requirements, the fact versions read or the rule version changed (D-52).
    """
    if stored is None:
        return True
    return (stored.fit, stored.outcomes, stored.rule_version) != (fit, outcomes, rule_version)


def no_longer_eligible(fit: FitStatus | None) -> bool:
    """Whether an open application is shown as no longer eligible.

    Rule INT-04: an application no longer eligible is marked, then archived on
    confirmation. Calculated from its current match, never stored (D-53).
    """
    return fit is FitStatus.NOT_ELIGIBLE
