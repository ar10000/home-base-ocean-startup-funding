"""Edge cases and invariants for matching rules (REQ-01 to REQ-05, FIT-01 to FIT-05)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from home_base.core.errors import EligibilityRuleError
from home_base.core.vocabulary import FitStatus, Operator
from home_base.modules.matching.domain import (
    ApplicantForm,
    FactSnapshot,
    HardRequirement,
    RequirementResult,
)
from home_base.modules.matching.rules import (
    applicant_form_requirement,
    approved_value,
    evaluate_requirement,
    fit_status,
)

R = RequirementResult


def req(operator: Operator, value: object, key: str = "country") -> HardRequirement:
    return HardRequirement(key, operator, value, source_quote="Applicants must be based in PT")  # type: ignore[arg-type]


# REQ-01 / REQ-02: comparisons and their boundaries


@pytest.mark.parametrize(
    ("operator", "rule", "fact", "expected"),
    [
        (Operator.EQUALS, "PT", "PT", R.PASS),
        (Operator.EQUALS, "PT", "ES", R.FAIL),
        (Operator.EQUALS, True, True, R.PASS),
        (Operator.ONE_OF, frozenset({"PT", "ES"}), "ES", R.PASS),
        (Operator.NOT_ONE_OF, frozenset({"PT"}), "ES", R.PASS),
        (Operator.AT_MOST, 5, 5, R.PASS),
        (Operator.AT_MOST, 5, 6, R.FAIL),
        (Operator.AT_LEAST, 5, 4, R.FAIL),
    ],
)
def test_req_01_req_02_comparisons(
    operator: Operator, rule: object, fact: str | int | bool, expected: RequirementResult
) -> None:
    facts = [FactSnapshot("country", fact, approved=True)]
    assert evaluate_requirement(req(operator, rule), facts) is expected


@pytest.mark.parametrize(
    ("operator", "rule", "fact"),
    [
        (Operator.AT_LEAST, 5, "5"),  # text fact on a numeric rule
        (Operator.AT_LEAST, 5, True),  # booleans are not numbers
        (Operator.EQUALS, 1, True),  # 1 == True in Python; not here
        (Operator.ONE_OF, frozenset({"PT"}), 3),
        (Operator.EQUALS, frozenset({"PT"}), "PT"),
    ],
)
def test_req_01_mismatched_types_are_refused_not_guessed(
    operator: Operator, rule: object, fact: str | int | bool
) -> None:
    with pytest.raises(EligibilityRuleError):
        evaluate_requirement(req(operator, rule), [FactSnapshot("country", fact, approved=True)])


# REQ-03: missing, unapproved and duplicated facts


def test_req_03_other_facts_do_not_count() -> None:
    facts = [FactSnapshot("sector", "aquaculture", approved=True)]
    assert evaluate_requirement(req(Operator.EQUALS, "PT"), facts) is R.UNKNOWN


def test_req_03_unapproved_value_is_ignored_even_when_an_approved_one_exists() -> None:
    facts = [
        FactSnapshot("country", "ES", approved=False),
        FactSnapshot("country", "PT", approved=True),
    ]
    assert approved_value("country", facts) == "PT"


def test_req_03_two_approved_values_for_one_fact_is_an_error() -> None:
    facts = [FactSnapshot("country", "PT", True), FactSnapshot("country", "ES", True)]
    with pytest.raises(EligibilityRuleError):
        approved_value("country", facts)


def test_req_03_zero_is_a_value_not_a_missing_fact() -> None:
    facts = [FactSnapshot("team_size", 0, approved=True)]
    assert evaluate_requirement(req(Operator.AT_LEAST, 1, key="team_size"), facts) is R.FAIL


# REQ-05: applicant form


def test_req_05_a_call_must_accept_some_applicant_form() -> None:
    with pytest.raises(EligibilityRuleError):
        applicant_form_requirement(frozenset(), source_quote="")


def test_req_05_consortium_company_meets_consortium_call() -> None:
    requirement = applicant_form_requirement(frozenset({ApplicantForm.CONSORTIUM}), "quote")
    facts = [FactSnapshot("applicant_form", "consortium", approved=True)]
    assert evaluate_requirement(requirement, facts) is R.PASS


# FIT-01 to FIT-05: invariants that must hold for any list of results

results = st.lists(st.sampled_from(list(RequirementResult)), max_size=12)


@given(results)
def test_fit_03_any_failing_hard_rule_is_not_eligible(rs: list[RequirementResult]) -> None:
    if R.FAIL in rs:
        assert fit_status(rs).status is FitStatus.NOT_ELIGIBLE


@given(results, st.lists(st.just(R.AI_JUDGEMENT), max_size=5))
def test_fit_05_adding_soft_judgements_never_changes_fit(
    rs: list[RequirementResult], soft: list[RequirementResult]
) -> None:
    assert fit_status(rs) == fit_status(rs + soft)


@given(results)
def test_fit_01_confirmed_only_with_two_or_more_hard_rules_all_passing(
    rs: list[RequirementResult],
) -> None:
    hard = [r for r in rs if r is not R.AI_JUDGEMENT]
    confirmed = fit_status(rs).status is FitStatus.CONFIRMED
    assert confirmed == (len(hard) >= 2 and all(r is R.PASS for r in hard))


@given(results)
def test_fit_02_settling_an_unknown_as_pass_never_lowers_fit(rs: list[RequirementResult]) -> None:
    order = {FitStatus.NOT_ELIGIBLE: 0, FitStatus.POSSIBLE: 1, FitStatus.CONFIRMED: 2}
    settled = [R.PASS if r is R.UNKNOWN else r for r in rs]
    assert order[fit_status(settled).status] >= order[fit_status(rs).status]


@given(results)
def test_fit_04_note_shown_exactly_when_fewer_than_two_hard_rules(
    rs: list[RequirementResult],
) -> None:
    hard = [r for r in rs if r is not R.AI_JUDGEMENT]
    result = fit_status(rs)
    if result.status is not FitStatus.CONFIRMED:
        assert result.few_explicit_rules == (len(hard) < 2)


def test_fit_04_one_failing_rule_is_still_not_eligible() -> None:
    result = fit_status([R.FAIL])
    assert result.status is FitStatus.NOT_ELIGIBLE
    assert result.few_explicit_rules is True
