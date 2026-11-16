"""Read models for the Opportunities and Opportunity screens (spec: Screens).

Read-only and above the services (like jobs/): it gathers each module's data through
its service and lets the rules decide every status, flag, order and label. Nothing
here writes; an opportunity not yet matched is evaluated on the fly, not stored.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from home_base.core.errors import NotFoundError
from home_base.core.vocabulary import Decision, FitStatus
from home_base.modules.applications import service as applications
from home_base.modules.audit.repository import AuditRepository
from home_base.modules.companies import rules as company_rules
from home_base.modules.companies import service as companies
from home_base.modules.matching import rules as matching_rules
from home_base.modules.matching import service as matching
from home_base.modules.matching.domain import MatchInputs, RequirementResult
from home_base.modules.opportunities import rules as opportunity_rules
from home_base.modules.opportunities.domain import FreshnessState, OpportunityStatus
from home_base.modules.opportunities.seed import Scope
from home_base.modules.opportunities.service import StoredOpportunity, current_opportunities
from home_base.modules.today import rules as today_rules
from home_base.modules.today.domain import AnswerState, QuestionSnapshot

# Response models


class Fit(BaseModel):
    status: FitStatus
    few_explicit_rules: bool


class Deadline(BaseModel):
    kind: str  # how to show it: rolling, days_left or date (SCP-03)
    date: date | None  # the deadline itself; None for a rolling call
    days_left: int | None


class Readiness(BaseModel):
    ready: int
    total: int


class OpportunityItem(BaseModel):
    id: uuid.UUID
    name: str
    funder: str
    types: list[str]
    scope: Scope
    fit: Fit
    decision: Decision
    status: OpportunityStatus  # open or upcoming; closed calls are not listed
    opening: date | None  # official opening, for an upcoming call
    expected_month: str | None  # YYYY-MM, when only expected
    deadline: Deadline
    checked_on: date
    checked_days_ago: int
    recheck_due: bool
    readiness: Readiness | None
    based_on_last_edition: bool
    goal_relevant: bool


class OpportunityList(BaseModel):
    items: list[OpportunityItem]
    counts: dict[FitStatus, int]  # per fit, before the fit filter (spec: Filter counts)


class RequirementLine(BaseModel):
    hard: bool
    quote: str
    fact: str | None
    criterion: str | None
    result: RequirementResult


class EvidenceLine(BaseModel):
    kind: str
    dated: date
    url: str


class HistoryLine(BaseModel):
    action: str
    occurred_at: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class OpportunityDetail(OpportunityItem):
    source_url: str
    requirements: list[RequirementLine]
    questions_total: int | None  # None: the question list is unknown
    questions_draftable: int
    evidence: list[EvidenceLine]
    history: list[HistoryLine]


# Assembly


@dataclass(frozen=True, slots=True)
class _Context:
    today: date
    inputs: MatchInputs
    approved: frozenset[str]
    matches: dict[uuid.UUID, Any]
    decisions: dict[uuid.UUID, Decision]
    intent: Any
    answers: dict[uuid.UUID, dict[uuid.UUID, AnswerState]]  # opportunity → question → state


def _context(session: Session, company_id: uuid.UUID, today: date) -> _Context:
    inputs = companies.match_inputs(session, company_id)
    answers = {
        a.opportunity_id: {x.question_id: x.state for x in a.answers}
        for a in applications.open_applications(session, company_id)
    }
    return _Context(
        today=today,
        inputs=inputs,
        approved=frozenset(f.key for f in inputs.facts if f.approved),
        matches={m.opportunity_id: m for m in matching.current_matches(session, company_id)},
        decisions=matching.current_decisions(session, company_id),
        intent=companies.current_intent(session, company_id),
        answers=answers,
    )


def _status(o: StoredOpportunity, today: date) -> OpportunityStatus:
    r = o.record
    return opportunity_rules.opportunity_status(r.opening, r.expected_month, r.deadline, today)


def _listed(o: StoredOpportunity, today: date) -> bool:
    """Closed calls are hidden (FRS-05); upcoming ones need evidence that counts (UPC-02)."""
    r = o.record
    status = _status(o, today)
    if status is OpportunityStatus.CLOSED:
        return False
    if status is OpportunityStatus.UPCOMING:
        return opportunity_rules.upcoming_is_shown(r.opening, r.expected_month, r.evidence, today)
    return True


def _questions(o: StoredOpportunity, ctx: _Context) -> tuple[QuestionSnapshot, ...] | None:
    if o.record.questions is None:
        return None
    states = ctx.answers.get(o.id, {})
    return tuple(
        QuestionSnapshot(states.get(qid, AnswerState.MISSING_FACTS), q.required_facts)
        for qid, q in zip(o.question_ids, o.record.questions, strict=True)
    )


def _fit_and_outcomes(o: StoredOpportunity, ctx: _Context) -> tuple[Fit, list[RequirementResult]]:
    stored = ctx.matches.get(o.id)
    if stored is not None:
        fit, outcomes = stored.fit, stored.outcomes
    else:
        fit, outcomes = matching.evaluate(o, ctx.inputs, ctx.today)
    results = [x.result for x in outcomes]
    return Fit(status=fit.status, few_explicit_rules=fit.few_explicit_rules), results


def _item(o: StoredOpportunity, ctx: _Context) -> tuple[OpportunityItem, list[RequirementResult]]:
    r, today = o.record, ctx.today
    status = _status(o, today)
    if status is OpportunityStatus.UPCOMING:
        freshness = opportunity_rules.upcoming_freshness_state(
            r.verified_on, r.opening, r.expected_month, today
        )
    else:
        freshness = opportunity_rules.freshness_state(r.verified_on, r.deadline, today)
    shown = opportunity_rules.deadline_display(r.deadline, today)
    ready = today_rules.readiness(_questions(o, ctx), ctx.approved)
    fit, results = _fit_and_outcomes(o, ctx)
    month = r.expected_month
    item = OpportunityItem(
        id=o.id,
        name=r.name,
        funder=r.funder,
        types=sorted(t.value for t in r.types),
        scope=r.scope,
        fit=fit,
        decision=ctx.decisions.get(o.id, Decision.NONE),
        status=status,
        opening=r.opening,
        expected_month=f"{month.year:04d}-{month.month:02d}" if month else None,
        deadline=Deadline(
            kind=shown.kind.value,
            date=r.deadline,
            days_left=shown.days_left,
        ),
        checked_on=r.verified_on,
        checked_days_ago=(today - r.verified_on).days,
        recheck_due=freshness is FreshnessState.RECHECK_DUE,
        readiness=Readiness(ready=ready.done, total=ready.total) if ready else None,
        based_on_last_edition=opportunity_rules.based_on_last_edition(
            r.opening, r.expected_month, r.deadline, today
        ),
        goal_relevant=company_rules.serves_current_goal(r.types, ctx.intent),
    )
    return item, results


def _sort_date(o: StoredOpportunity, status: OpportunityStatus) -> date | None:
    """The deadline, or for an upcoming call its opening (the 1st of an expected month,
    D-19); no date sorts last (D-41)."""
    r = o.record
    if status is OpportunityStatus.UPCOMING:
        if r.opening is not None:
            return r.opening
        return date(r.expected_month.year, r.expected_month.month, 1) if r.expected_month else None
    return r.deadline


def list_opportunities(
    session: Session,
    company_id: uuid.UUID,
    today: date,
    fit_filter: FitStatus | None = None,
    decision_filter: Decision | None = None,
) -> OpportunityList:
    """The Opportunities list: listed calls the decision filter shows (DEC-04), goal-relevant
    first (INT-03), then the D-41 order (SCP-02); Not eligible only under its filter."""
    ctx = _context(session, company_id, today)
    rows = []
    for o in current_opportunities(session):
        if not _listed(o, today):
            continue
        item, _ = _item(o, ctx)
        if matching_rules.shown_in_list(item.decision, decision_filter):
            rows.append((o, item))
    counts = {f: 0 for f in FitStatus}
    for _, item in rows:
        counts[item.fit.status] += 1
    visible = [
        (o, i)
        for o, i in rows
        if (
            i.fit.status is fit_filter if fit_filter else i.fit.status is not FitStatus.NOT_ELIGIBLE
        )
    ]

    def key(pair: tuple[StoredOpportunity, OpportunityItem]) -> tuple[bool, Any]:
        o, i = pair
        sort = opportunity_rules.list_sort_key(
            i.fit.status, _sort_date(o, i.status), i.scope is Scope.BLUE_SPECIFIC, i.name
        )
        return (not i.goal_relevant, sort)

    return OpportunityList(items=[i for _, i in sorted(visible, key=key)], counts=counts)


def opportunity_detail(
    session: Session, company_id: uuid.UUID, opportunity_id: uuid.UUID, today: date
) -> OpportunityDetail:
    found = {o.id: o for o in current_opportunities(session)}.get(opportunity_id)
    if found is None:
        raise NotFoundError("no such opportunity")
    ctx = _context(session, company_id, today)
    item, results = _item(found, ctx)
    r = found.record
    questions = _questions(found, ctx)
    history = AuditRepository(session, company_id).history("opportunity", found.id)
    return OpportunityDetail(
        **item.model_dump(),
        source_url=r.source_url,
        requirements=[
            RequirementLine(
                hard=q.hard, quote=q.quote, fact=q.fact, criterion=q.criterion, result=res
            )
            for q, res in zip(r.requirements, results, strict=True)
        ],
        questions_total=len(questions) if questions is not None else None,
        questions_draftable=sum(today_rules.is_draftable(q, ctx.approved) for q in questions or ()),
        evidence=[
            EvidenceLine(kind=e.kind.value, dated=e.dated, url=e.source_url) for e in r.evidence
        ],
        history=[
            HistoryLine(
                action=e.action,
                occurred_at=e.occurred_at.isoformat(),
                before=e.before,
                after=e.after,
            )
            for e in history
        ],
    )
