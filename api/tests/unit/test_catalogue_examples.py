"""Runs every example in docs/rules/*.yaml against the code that implements it.

The catalogue is the contract: if an example and the code disagree, this test fails,
and the fix starts with the spec, not with the example.
"""

import uuid
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from home_base.core.dates import days_left
from home_base.core.errors import IntentError
from home_base.core.errors import SeedError as _SeedError
from home_base.core.vocabulary import Decision, FitStatus, Operator, OpportunityType
from home_base.modules.applications.rules import (
    approvable,
    draft_citations,
    may_mark_submitted,
    unusable_citations,
)
from home_base.modules.audit.domain import Actor
from home_base.modules.companies.domain import Goal, GoalChoice, Window
from home_base.modules.companies.rules import (
    current_intent,
    fact_value_allowed,
    intent_record,
    serves_current_goal,
)
from home_base.modules.matching.domain import (
    ApplicantForm,
    Confidence,
    FactSnapshot,
    FitResult,
    HardRequirement,
    RequirementOutcome,
    RequirementResult,
    SoftCriterion,
    SoftJudgement,
    StoredMatch,
)
from home_base.modules.matching.rules import (
    APPLICANT_FORM_FACT,
    applicant_form_requirement,
    current_decision,
    decision_change,
    decision_on_application_start,
    evaluate_requirement,
    fit_status,
    founder_age,
    founder_age_fact,
    later_has_returned,
    match_changed,
    no_longer_eligible,
    shown_in_list,
    soft_result,
)
from home_base.modules.opportunities.domain import (
    Evidence,
    EvidenceKind,
    Month,
    ReloadOutcome,
    SourcedValue,
    Verification,
    VerificationMethod,
)
from home_base.modules.opportunities.rules import (
    based_on_last_edition,
    deadline_display,
    freshness_state,
    last_verified_date,
    list_sort_key,
    opportunity_status,
    reload_effects,
    resolve_sources,
    review_interval_days,
    upcoming_freshness_state,
    upcoming_is_shown,
)
from home_base.modules.opportunities.seed import parse_seed
from home_base.modules.today.domain import (
    AnswerState,
    ApplicationSnapshot,
    Milestone,
    OpportunitySnapshot,
    QuestionSnapshot,
    Task,
    TaskType,
)
from home_base.modules.today.rules import (
    answers_ready,
    application_status,
    applying_tasks,
    counts_for_priorities,
    fact_unlocks,
    is_draftable,
    new_milestones,
    next_deadline,
    next_opening_date,
    opening_soon,
    preparing_tasks,
    readiness,
    task_sort_key,
    time_estimate_minutes,
    today_mode,
    today_plan,
)


def _find(relative: str) -> Path:
    """The nearest parent folder holding `relative` (also works from mutmut's copy)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / relative).is_dir():
            return parent / relative
    raise FileNotFoundError(relative)


RULES_DIR = _find("docs/rules")


def _requirement(given: dict[str, Any]) -> str:
    rule = given["rule"]
    value = frozenset(rule) if isinstance(rule, list) else rule
    req = HardRequirement("trl", Operator(given["operator"]), value, source_quote="example")
    facts = [FactSnapshot("trl", given["fact"], approved=given["approved"])]
    return evaluate_requirement(req, facts).value


def _soft(given: dict[str, Any]) -> str:
    criterion = SoftCriterion("Clear environmental benefit", source_quote="example")
    judgement = SoftJudgement(criterion, Confidence(given["confidence"]), "example")
    return soft_result(judgement).value


def _applicant_form(given: dict[str, Any]) -> str:
    accepted = frozenset(ApplicantForm(a) for a in given["accepts"])
    req = applicant_form_requirement(accepted, source_quote="example")
    facts = [FactSnapshot(APPLICANT_FORM_FACT, given["company"], approved=True)]
    return evaluate_requirement(req, facts).value


def _fit(given: list[str]) -> str:
    return fit_status([RequirementResult(r) for r in given]).status.value


def _last_verified(given: dict[str, Any]) -> date | None:
    checks = [Verification(d, VerificationMethod(m)) for d, m in given["checks"]]
    return last_verified_date(checks, given["today"])


def _interval(given: dict[str, Any]) -> int:
    return review_interval_days(given["deadline"], given["today"])


def _freshness(given: dict[str, Any]) -> str:
    return freshness_state(given["last_verified"], given["deadline"], given["today"]).value


def _sources(given: list[list[Any]]) -> dict[str, Any]:
    claims = [SourcedValue(str(v), official=o, source_url="https://example.org") for v, o in given]
    result = resolve_sources(claims)
    return {"value": result.value, "recheck_due": result.recheck_due}


def _month(value: str | None) -> Month | None:
    if value is None:
        return None
    year, month = value.split("-")
    return Month(int(year), int(month))


def _status(given: dict[str, Any]) -> str:
    month = _month(given["expected_month"])
    return opportunity_status(given["opening"], month, given["deadline"], given["today"]).value


def _last_edition(given: dict[str, Any]) -> bool:
    month = _month(given["expected_month"])
    return based_on_last_edition(given["opening"], month, given["deadline"], given["today"])


def _shown(given: dict[str, Any]) -> str:
    evidence = [
        Evidence(EvidenceKind.PREVIOUS_EDITION, d, "https://example.org") for d in given["evidence"]
    ]
    month = _month(given["expected_month"])
    shown = upcoming_is_shown(given["opening"], month, evidence, given["today"])
    return "shown" if shown else "hidden"


def _upcoming_freshness(given: dict[str, Any]) -> str:
    month = _month(given["expected_month"])
    state = upcoming_freshness_state(
        given["last_verified"], given["opening"], month, given["today"]
    )
    return state.value


def _goals(pairs: list[list[str]]) -> list[GoalChoice]:
    return [GoalChoice(Goal(g), Window(w)) for g, w in pairs]


def _intent(given: dict[str, Any]) -> str:
    at = datetime.fromisoformat("2026-11-09T09:00:00+00:00")
    try:
        intent_record(_goals(given["goals"]), at)
    except IntentError:
        return "refused"
    return "valid"


def _current_intent(given: dict[str, Any]) -> list[list[str]] | None:
    records = [intent_record(_goals(g), datetime.fromisoformat(at)) for at, g in given["records"]]
    current = current_intent(records)
    return None if current is None else [[c.goal.value, c.window.value] for c in current.goals]


def _serves_goal(given: dict[str, Any]) -> bool:
    goals = given["goals"]
    at = datetime.fromisoformat("2026-11-09T09:00:00+00:00")
    intent = (
        None
        if goals is None
        else intent_record([GoalChoice(Goal(g), Window.NOW) for g in goals], at)
    )
    return serves_current_goal(frozenset(OpportunityType(t) for t in given["types"]), intent)


def _founder_age(given: dict[str, Any]) -> int:
    return founder_age(given["birth_date"], given["deadline"], given["today"])


def _founder_rule(given: dict[str, Any]) -> str:
    fact = founder_age_fact(given["birth_date"], given["deadline"], given["today"])
    rule = HardRequirement("founder_age", Operator.AT_MOST, given["at_most"], "q")
    return evaluate_requirement(rule, [] if fact is None else [fact]).value


def _decision(given: dict[str, Any]) -> str:
    changes = [
        decision_change(Decision(d), datetime.fromisoformat(at)) for at, d in given["changes"]
    ]
    return current_decision(changes).value


def _on_start(given: dict[str, Any]) -> str:
    return decision_on_application_start(Decision(given["current"])).value


def _listed(given: dict[str, Any]) -> bool:
    decision_filter = None if given["filter"] is None else Decision(given["filter"])
    return shown_in_list(Decision(given["decision"]), decision_filter)


def _states(states: list[str]) -> list[QuestionSnapshot]:
    return [QuestionSnapshot(AnswerState(s), frozenset({"country"})) for s in states]


def _answers_ready(given: dict[str, Any]) -> str | None:
    ratio = answers_ready(_states(given["questions"]))
    return None if ratio is None else str(ratio)


def _draftable(given: dict[str, Any]) -> bool:
    question = QuestionSnapshot(AnswerState.MISSING_FACTS, frozenset(given["required"]))
    return is_draftable(question, frozenset(given["approved"]))


def _app_status(given: dict[str, Any]) -> str:
    snapshot = ApplicationSnapshot(tuple(_states(given["questions"])), given["submitted"])
    return application_status(snapshot).value


def _fact_value(given: dict[str, Any]) -> bool:
    return fact_value_allowed(given["key"], given["value"])


def _approvable(given: dict[str, Any]) -> bool:
    return approvable(given["text"])


def _unusable(given: dict[str, Any]) -> list[str]:
    return unusable_citations(given["cited"], frozenset(given["usable"]))


def _citations(given: dict[str, Any]) -> list[str]:
    return draft_citations(given["sentences"])


def _may_submit(given: dict[str, Any]) -> bool:
    return may_mark_submitted(Actor(given["actor"]))


def _milestones(given: dict[str, Any]) -> list[str]:
    apps = [ApplicationSnapshot(tuple(_states(s)), sub) for s, sub in given["applications"]]
    shown = frozenset(Milestone(m) for m in given["shown"])
    return [m.value for m in new_milestones(frozenset(given["approved_facts"]), apps, shown)]


def _readiness(given: dict[str, Any]) -> str | None:
    questions = given["questions"]
    snapshots = (
        None
        if questions is None
        else [QuestionSnapshot(AnswerState(s), frozenset(req)) for s, req in questions]
    )
    ratio = readiness(snapshots, frozenset(given["approved"]))
    return None if ratio is None else str(ratio)


def _sort(given: dict[str, Any]) -> str:
    return "a" if task_sort_key(*given["a"]) < task_sort_key(*given["b"]) else "b"


def _list_order(given: dict[str, Any]) -> str:
    def key(item: list[Any]) -> tuple[int, bool, date, bool, str]:
        fit, when, blue, name = item
        return list_sort_key(FitStatus(fit), when, blue, name)

    return "a" if key(given["a"]) < key(given["b"]) else "b"


def _minutes(given: dict[str, Any]) -> int:
    return time_estimate_minutes(TaskType(given["task"]))


_APP_STATES = {
    "in_progress": ((AnswerState.AI_DRAFT,), False),
    "ready": ((AnswerState.APPROVED,), False),
    "submitted": ((AnswerState.APPROVED,), True),
}


def _mode(given: dict[str, Any]) -> str:
    opps = []
    for fit, decision, deadline, status, *rest in given["opportunities"]:
        current = rest[0] if rest else True
        app = None
        if status is not None:
            states, submitted = _APP_STATES[status]
            questions = tuple(QuestionSnapshot(s, frozenset({"country"})) for s in states)
            app = ApplicationSnapshot(questions, submitted)
        opps.append(
            OpportunitySnapshot(
                "Call",
                True,
                FitStatus(fit),
                Decision(decision),
                deadline,
                app,
                current,
                False,
                frozenset(),
                False,
                None,
                None,
            )
        )
    return today_mode(opps, given["today"]).value


def _counts(given: dict[str, Any]) -> bool:
    decision = Decision(given["decision"])
    return counts_for_priorities(
        decision, given["later_returned"], given["source_current"], FitStatus(given["fit"])
    )


def _later(given: dict[str, Any]) -> bool:
    return later_has_returned(
        given["deadline"], given["opening"], given["today"], given["chosen_again_after_return"]
    )


def _opportunity(o: dict[str, Any]) -> OpportunitySnapshot:
    questions = o["questions"]
    app = (
        None
        if questions is None
        else ApplicationSnapshot(
            tuple(QuestionSnapshot(AnswerState(s), frozenset(f)) for s, f in questions), False
        )
    )
    return OpportunitySnapshot(
        o["name"],
        True,
        FitStatus(o["fit"]),
        Decision(o["decision"]),
        o["deadline"],
        app,
        True,
        o.get("later_returned", False),
        frozenset(o["unknown"]),
        o.get("upcoming", False),
        o.get("opening"),
        None,
    )


def _label(task: Task) -> str:
    detail = task.fact or task.count or task.question
    parts = [task.type.value, task.opportunity or ""] + ([str(detail)] if detail else [])
    return ":".join(parts)


def _applying(given: dict[str, Any]) -> list[Task]:
    opps = [_opportunity(o) for o in given["opportunities"]]
    return applying_tasks(opps, frozenset(given["approved"]), given["today"])


def _first_task(given: dict[str, Any]) -> str | None:
    tasks = _applying(given)
    return _label(tasks[0]) if tasks else None


def _plan(given: dict[str, Any]) -> str | None:
    plan = today_plan(_applying(given))
    if plan.one_thing is None:
        return None
    return f"{_label(plan.one_thing)} | " + ", ".join(_label(t) for t in plan.needs_attention)


def _rdy_02(given: dict[str, Any]) -> str:
    opps = [_opportunity(o) for o in given["opportunities"]]
    u = fact_unlocks(given["fact"], opps, frozenset(given["approved"]))
    m = "match" if u.matches == 1 else "matches"
    q = "question" if u.questions == 1 else "questions"
    return f"{u.matches} {m}, {u.questions} {q}"


def _preparing(given: dict[str, Any]) -> str | None:
    opps = [_opportunity(o) for o in given["opportunities"]]
    approved = frozenset(given["approved"])
    tasks = preparing_tasks(opps, approved, given["intent_recorded_on"], given["today"])
    return _label(tasks[0]) if tasks else None


def _next_opening(given: dict[str, Any]) -> str | None:
    found = next_opening_date([_opportunity(o) for o in given["opportunities"]])
    return None if found is None else found.isoformat()


def _scope(given: dict[str, Any]) -> str:
    record = {
        "name": "Fictional Call",
        "funder": "Example Foundation",
        "scope": given["scope"],
        "types": ["grant"],
        "source_url": "https://example.org/call",
        "retrieved_on": date(2026, 11, 1),
        "verified_on": date(2026, 11, 2),
        "verified_by": "Test",
        "requirements": [
            {"type": "hard", "fact": "country", "operator": "equals", "value": "PT", "quote": "q"}
        ],
    }
    try:
        parse_seed(record, "example.yaml", date(2026, 11, 9))
    except _SeedError:
        return "refused"
    return "valid"


def _days_left(given: dict[str, Any]) -> int:
    return days_left(given["deadline"], given["today"])


def _int_04(given: dict[str, Any]) -> object:
    if "no_longer_eligible" in given:
        fit = given["no_longer_eligible"]
        return no_longer_eligible(FitStatus(fit) if fit else None)
    requirement = uuid.uuid5(uuid.NAMESPACE_URL, "requirement")

    def parts(m: dict[str, Any]) -> tuple[FitResult, tuple[RequirementOutcome, ...]]:
        outcomes = tuple(
            RequirementOutcome(
                requirement, RequirementResult(r), "country", uuid.uuid5(uuid.NAMESPACE_URL, v)
            )
            for r, v in zip(m["results"], m["facts"], strict=True)
        )
        return FitResult(FitStatus(m["fit"]), False), outcomes

    stored = None
    if given["stored"] is not None:
        fit, outcomes = parts(given["stored"])
        stored = StoredMatch(
            uuid.uuid5(uuid.NAMESPACE_URL, "match"),
            uuid.uuid5(uuid.NAMESPACE_URL, "opportunity"),
            fit,
            given["stored"]["rule_version"],
            datetime.fromisoformat("2026-11-11T12:00:00+00:00"),
            None,
            outcomes,
        )
    fit, outcomes = parts(given["calculated"])
    changed = match_changed(stored, fit, outcomes, given["calculated"]["rule_version"])
    return "store" if changed else "skip"


def _reload_effects(given: str) -> dict[str, bool]:
    effects = reload_effects(ReloadOutcome(given))
    return {"audit": effects.audit, "recalculate": effects.recalculate}


def _deadline_display(given: dict[str, Any]) -> list[object]:
    shown = deadline_display(given["deadline"], given["today"])
    return [shown.kind.value, shown.days_left]


def _opening_soon(given: dict[str, Any]) -> list[str]:
    found = opening_soon([_opportunity(o) for o in given["opportunities"]], given["today"])
    return [o.name for o in found]


def _next_deadline(given: dict[str, Any]) -> str | None:
    found = next_deadline([_opportunity(o) for o in given["opportunities"]], given["today"])
    return found.name if found else None


ADAPTERS: dict[str, Callable[[Any], object]] = {
    "REQ-01": _requirement,
    "REQ-02": _requirement,
    "REQ-03": _requirement,
    "REQ-04": _soft,
    "REQ-05": _applicant_form,
    "REQ-06": _founder_age,
    "REQ-07": _founder_rule,
    "FIT-01": _fit,
    "FIT-02": _fit,
    "FIT-03": _fit,
    "FIT-04": _fit,
    "FIT-05": _fit,
    "FRS-01": _last_verified,
    "FRS-02": _interval,
    "FRS-03": _interval,
    "FRS-04": _freshness,
    "FRS-05": _freshness,
    "FRS-06": _reload_effects,
    "FRS-07": _sources,
    "PRI-07": _days_left,
    "UPC-01": _status,
    "UPC-03": _last_edition,
    "SCP-01": _scope,
    "SCP-02": _list_order,
    "SCP-03": _deadline_display,
    "INT-01": _intent,
    "INT-02": _current_intent,
    "INT-03": _serves_goal,
    "INT-04": _int_04,
    "DEC-01": _decision,
    "DEC-02": _on_start,
    "DEC-04": _listed,
    "PRG-01": _answers_ready,
    "PRG-02": _draftable,
    "PRG-03": _app_status,
    "PRG-04": _milestones,
    "PRG-05": _approvable,
    "DRF-01": _unusable,
    "DRF-02": _citations,
    "DRF-03": _may_submit,
    "REQ-09": _fact_value,
    "RDY-01": _readiness,
    "PRI-01": _first_task,
    "PRI-02": _first_task,
    "PRI-03": _first_task,
    "PRI-04": _first_task,
    "PRI-05": _first_task,
    "PRI-06": _plan,
    "PRI-08": _sort,
    "PRI-13": _preparing,
    "PRI-14": _preparing,
    "PRI-15": _preparing,
    "PRI-16": _preparing,
    "PRI-17": _next_opening,
    "PRI-18": _opening_soon,
    "PRI-19": _next_deadline,
    "RDY-02": _rdy_02,
    "PRI-09": _plan,
    "PRI-10": _minutes,
    "PRI-11": _mode,
    "PRI-12": _counts,
    "DEC-03": _later,
    "UPC-02": _shown,
    "UPC-04": _upcoming_freshness,
    "UPC-05": _shown,
}


def _catalogue() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(RULES_DIR.glob("*.yaml")):
        entries.extend(yaml.safe_load(path.read_text(encoding="utf-8")) or [])
    return entries


def _examples() -> list[Any]:
    cases = []
    for rule in _catalogue():
        for i, example in enumerate(rule.get("examples", [])):
            cases.append(pytest.param(rule["id"], example, id=f"{rule['id']}-example-{i + 1}"))
    return cases


def test_every_implemented_rule_has_an_adapter_and_examples() -> None:
    implemented = {r["id"] for r in _catalogue() if r["status"] == "implemented"}
    assert implemented == set(ADAPTERS), "add an adapter (or examples) for each implemented rule"
    without = [
        r["id"] for r in _catalogue() if r["status"] == "implemented" and not r.get("examples")
    ]
    assert without == []


@pytest.mark.parametrize(("rule_id", "example"), _examples())
def test_catalogue_example(rule_id: str, example: dict[str, Any]) -> None:
    assert ADAPTERS[rule_id](example["given"]) == example["expect"]
