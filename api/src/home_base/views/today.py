"""Read model for the Today screen (spec: Today; PRI, PRG and RDY rules).

Builds one snapshot per listed opportunity from stored data, then lets the Today rules
pick the mode, the one thing today, what needs attention, the next deadline, what is
opening soon and the fact that unlocks the most. The task's sentence is worded by the
AI later (week 4); the API returns its parts. Nothing here writes.
"""

import uuid
from datetime import date

from pydantic import BaseModel
from sqlalchemy.orm import Session

from home_base.config import STAGES
from home_base.core.dates import days_left, local_today
from home_base.core.vocabulary import Decision
from home_base.modules.applications import service as applications
from home_base.modules.companies import service as companies
from home_base.modules.matching import rules as matching_rules
from home_base.modules.matching import service as matching
from home_base.modules.matching.domain import DecisionChange, RequirementResult
from home_base.modules.opportunities.domain import OpportunityStatus
from home_base.modules.opportunities.seed import Scope
from home_base.modules.opportunities.service import StoredOpportunity, current_opportunities
from home_base.modules.today import rules
from home_base.modules.today.domain import (
    AnswerState,
    ApplicationSnapshot,
    Mode,
    OpportunitySnapshot,
    QuestionSnapshot,
    Ratio,
    Task,
    TaskType,
)
from home_base.views import opportunities as base
from home_base.views.opportunities import Readiness


class TaskOut(BaseModel):
    type: TaskType
    minutes: int  # fixed per task type (PRI-10)
    opportunity_id: uuid.UUID | None
    opportunity: str | None
    deadline: date | None
    fact: str | None
    count: int | None
    question: int | None  # 1-based, in the call's order


class Goal(BaseModel):
    goal: str
    window: str


class NextDeadline(BaseModel):
    opportunity_id: uuid.UUID
    opportunity: str
    deadline: date
    days_left: int
    answers_ready: Readiness | None  # approved / total (PRG-01); None with no questions


class OpeningSoon(BaseModel):
    opportunity_id: uuid.UUID
    opportunity: str
    opening: date
    readiness: Readiness | None


class TopFact(BaseModel):
    fact: str
    matches: int  # Possible matches it would settle
    questions: int  # questions it would make draftable


class Stage(BaseModel):
    """The founder's journey stage (spec: Today > Stage; D-78): "Stage 6 of 9"."""

    value: str
    label: str
    position: int  # 1-based, in config.STAGES order
    total: int


class Today(BaseModel):
    stage: Stage | None  # None until the founder chooses one
    mode: Mode
    one_thing: TaskOut | None  # None: "You're all set" (PRI-06)
    needs_attention: list[TaskOut]
    next_opening: date | None  # with "You're all set" in preparing (PRI-17)
    next_deadline: NextDeadline | None
    current_goal: list[Goal] | None
    opening_soon: list[OpeningSoon]  # preparing only
    top_fact: TopFact | None  # preparing only


def _application(
    o: StoredOpportunity, ctx: base._Context, submitted: bool
) -> ApplicationSnapshot | None:
    if o.id not in ctx.answers:
        return None
    states = ctx.answers[o.id]
    questions = tuple(
        QuestionSnapshot(states.get(qid, AnswerState.MISSING_FACTS), q.required_facts)
        for qid, q in zip(o.question_ids, o.record.questions or (), strict=True)
    )
    return ApplicationSnapshot(questions, submitted)


def _snapshot(
    o: StoredOpportunity,
    ctx: base._Context,
    histories: dict[uuid.UUID, list[DecisionChange]],
    submitted: frozenset[uuid.UUID],
) -> OpportunitySnapshot:
    r, today = o.record, ctx.today
    item, results = base._item(o, ctx)
    upcoming = item.status is OpportunityStatus.UPCOMING
    opening = base._sort_date(o, item.status) if upcoming else None
    unknown = frozenset(
        q.fact
        for q, res in zip(r.requirements, results, strict=True)
        if q.hard and q.fact is not None and res is RequirementResult.UNKNOWN
    )
    history = histories.get(o.id, [])
    returned = item.decision is Decision.LATER and matching_rules.later_has_returned(
        r.deadline,
        opening,
        today,
        matching_rules.later_chosen_again_after_return(history, r.deadline, opening),
    )
    return OpportunitySnapshot(
        name=r.name,
        blue_specific=r.scope is Scope.BLUE_SPECIFIC,
        fit=item.fit.status,
        decision=item.decision,
        deadline=r.deadline,
        application=_application(o, ctx, o.id in submitted),
        source_current=not item.recheck_due,
        later_returned=returned,
        unknown_hard_facts=unknown,
        upcoming=upcoming,
        opening=opening,
        questions=base._questions(o, ctx),
    )


def _task(task: Task, ids: dict[str, uuid.UUID]) -> TaskOut:
    return TaskOut(
        type=task.type,
        minutes=rules.time_estimate_minutes(task.type),
        opportunity_id=ids.get(task.opportunity) if task.opportunity else None,
        opportunity=task.opportunity,
        deadline=task.deadline,
        fact=task.fact,
        count=task.count,
        question=task.question,
    )


def _ratio(ratio: Ratio | None) -> Readiness | None:
    return Readiness(ready=ratio.done, total=ratio.total) if ratio else None


def today_view(session: Session, company_id: uuid.UUID, today: date) -> Today:
    ctx = base._context(session, company_id, today)
    histories = matching.decision_histories(session, company_id)
    submitted = frozenset(
        a.opportunity_id
        for a in applications.open_applications(session, company_id)
        if a.submitted_at is not None
    )
    listed = [o for o in current_opportunities(session) if base._listed(o, today)]
    snapshots = [_snapshot(o, ctx, histories, submitted) for o in listed]
    ids = {o.record.name: o.id for o in listed}  # names are unique (SCP-01)

    mode = rules.today_mode(snapshots, today)
    intent = ctx.intent
    recorded_on = local_today(intent.recorded_at) if intent else None
    if mode is Mode.APPLYING:
        tasks = rules.applying_tasks(snapshots, ctx.approved, today)
    else:
        tasks = rules.preparing_tasks(snapshots, ctx.approved, recorded_on, today)
    plan = rules.today_plan(tasks)

    nearest = rules.next_deadline(snapshots, today)
    next_due = None
    if nearest is not None and nearest.deadline is not None and nearest.application is not None:
        next_due = NextDeadline(
            opportunity_id=ids[nearest.name],
            opportunity=nearest.name,
            deadline=nearest.deadline,
            days_left=days_left(nearest.deadline, today),
            answers_ready=_ratio(rules.answers_ready(nearest.application.questions)),
        )

    soon: list[OpeningSoon] = []
    top: TopFact | None = None
    if mode is Mode.PREPARING:
        for s in rules.opening_soon(snapshots, today):
            assert s.opening is not None  # opening_soon keeps only dated openings
            soon.append(
                OpeningSoon(
                    opportunity_id=ids[s.name],
                    opportunity=s.name,
                    opening=s.opening,
                    readiness=_ratio(rules.readiness(s.questions, ctx.approved)),
                )
            )
        fact_task = next((t for t in tasks if t.type is TaskType.ADD_FACT and t.fact), None)
        if fact_task is not None and fact_task.fact is not None:
            unlocks = rules.fact_unlocks(fact_task.fact, snapshots, ctx.approved)
            top = TopFact(fact=fact_task.fact, matches=unlocks.matches, questions=unlocks.questions)

    chosen = companies.stage(session, company_id)
    order = [k for k, _ in STAGES]
    stage = (
        Stage(
            value=chosen,
            label=dict(STAGES)[chosen],
            position=order.index(chosen) + 1,
            total=len(STAGES),
        )
        if chosen in order
        else None
    )
    return Today(
        stage=stage,
        mode=mode,
        one_thing=_task(plan.one_thing, ids) if plan.one_thing else None,
        needs_attention=[_task(t, ids) for t in plan.needs_attention],
        next_opening=rules.next_opening_date(snapshots)
        if plan.one_thing is None and mode is Mode.PREPARING
        else None,
        next_deadline=next_due,
        current_goal=[Goal(goal=g.goal.value, window=g.window.value) for g in intent.goals]
        if intent
        else None,
        opening_soon=soon,
        top_fact=top,
    )
