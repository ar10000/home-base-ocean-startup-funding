"""The company profile: facts, founder facts and intent (D-47 to D-51, INT-01/02/04).

Routes only call services; every write is audited and recalculates matches in the
request's transaction. Values must arrive as their real JSON type ("4" is not 4).
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, StrictBool, StrictInt, StrictStr

from home_base.api import deps
from home_base.config import FACT_VALUES, STAGES
from home_base.core.context import Caller, Clock
from home_base.core.errors import NotFoundError
from home_base.modules.companies import service as companies
from home_base.modules.companies.domain import (
    FactLabel,
    FactVersion,
    FounderFact,
    Goal,
    GoalChoice,
    Window,
)
from home_base.modules.companies.repository import CompanyRepository

router = APIRouter(tags=["profile"])

SessionDep = deps.TenantDb
CallerDep = Annotated[Caller, Depends(deps.caller)]
ClockDep = Annotated[Clock, Depends(deps.clock)]


class FactIn(BaseModel):
    key: StrictStr
    value: StrictBool | StrictInt | StrictStr
    label: FactLabel
    source: str | None = None


class FactOut(BaseModel):
    id: uuid.UUID
    key: str
    value: bool | int | str
    label: FactLabel
    source: str | None
    recorded_at: datetime
    approved: bool


class FounderFactIn(BaseModel):
    value: StrictBool | date


class FounderFactOut(BaseModel):
    key: str
    value: bool | date
    approved: bool


class FactOption(BaseModel):
    value: str
    label: str


class Profile(BaseModel):
    facts: list[FactOut]
    founder_facts: list[FounderFactOut]
    stage: str | None  # D-78: None until the founder chooses one


class StageIn(BaseModel):
    stage: str


class GoalIn(BaseModel):
    goal: Goal
    window: Window


class IntentIn(BaseModel):
    goals: list[GoalIn]


class IntentOut(BaseModel):
    goals: list[GoalIn]
    recorded_at: datetime


def _fact(v: FactVersion) -> FactOut:
    return FactOut(
        id=v.id,
        key=v.key,
        value=v.value,
        label=v.label,
        source=v.source,
        recorded_at=v.recorded_at,
        approved=v.approved_at is not None,
    )


def _founder(f: FounderFact) -> FounderFactOut:
    return FounderFactOut(key=f.key, value=f.value, approved=f.approved_at is not None)


@router.get("/profile")
def get_profile(session: SessionDep, caller: CallerDep) -> Profile:
    repo = CompanyRepository(session, caller.company_id)
    return Profile(
        facts=[_fact(v) for v in repo.current_facts()],
        founder_facts=[_founder(f) for f in repo.founder_facts()],
        stage=repo.stage(),
    )


@router.post("/facts", status_code=status.HTTP_201_CREATED)
def add_fact(body: FactIn, session: SessionDep, caller: CallerDep, clock: ClockDep) -> FactOut:
    fact = companies.NewFact(body.key, body.value, body.label, body.source)
    return _fact(companies.add_fact(session, caller, fact, clock))


@router.post("/facts/{version_id}/approve")
def approve_fact(
    version_id: uuid.UUID, session: SessionDep, caller: CallerDep, clock: ClockDep
) -> FactOut:
    return _fact(companies.approve_fact(session, caller, version_id, clock))


@router.get("/stages")
def stages() -> list[FactOption]:
    """The journey stages in order, with their labels (D-78)."""
    return [FactOption(value=k, label=label) for k, label in STAGES]


@router.put("/stage", status_code=status.HTTP_204_NO_CONTENT)
def set_stage(body: StageIn, session: SessionDep, caller: CallerDep, clock: ClockDep) -> Response:
    companies.set_stage(session, caller, body.stage, clock)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/fact-options")
def fact_options() -> dict[str, list[FactOption]]:
    """The values each listed fact may take, with their labels (REQ-09, D-76), so the
    profile offers exactly the words the seed files use."""
    return {
        key: [FactOption(value=v, label=label) for v, label in values]
        for key, values in FACT_VALUES.items()
    }


@router.put("/founder-facts/{key}")
def set_founder_fact(
    key: str, body: FounderFactIn, session: SessionDep, caller: CallerDep, clock: ClockDep
) -> FounderFactOut:
    return _founder(companies.set_founder_fact(session, caller, key, body.value, clock))


@router.post("/founder-facts/{key}/approve")
def approve_founder_fact(
    key: str, session: SessionDep, caller: CallerDep, clock: ClockDep
) -> FounderFactOut:
    return _founder(companies.approve_founder_fact(session, caller, key, clock))


@router.delete("/founder-facts/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_founder_fact(
    key: str, session: SessionDep, caller: CallerDep, clock: ClockDep
) -> Response:
    if not companies.delete_founder_fact(session, caller, key, clock):
        raise NotFoundError(f"no founder fact {key!r}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/intent")
def set_intent(
    body: IntentIn, session: SessionDep, caller: CallerDep, clock: ClockDep
) -> IntentOut:
    goals = [GoalChoice(g.goal, g.window) for g in body.goals]
    record = companies.set_intent(session, caller, goals, clock)
    return IntentOut(
        goals=[GoalIn(goal=g.goal, window=g.window) for g in record.goals],
        recorded_at=record.recorded_at,
    )
