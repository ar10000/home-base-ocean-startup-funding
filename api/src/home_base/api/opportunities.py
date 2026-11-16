"""Opportunities and Opportunity screens (spec: Screens). Routes only call the views."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from home_base.api import deps
from home_base.core.context import Caller, Clock
from home_base.core.errors import NotFoundError
from home_base.core.vocabulary import Decision, FitStatus
from home_base.modules.applications import service as applications
from home_base.modules.matching import service as matching
from home_base.modules.matching.domain import NotForUsReason
from home_base.modules.opportunities.service import current_opportunities
from home_base.views import opportunities as views

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

SessionDep = deps.TenantDb
CallerDep = Annotated[Caller, Depends(deps.caller)]
ClockDep = Annotated[Clock, Depends(deps.clock)]


@router.get("")
def list_opportunities(
    session: SessionDep,
    caller: CallerDep,
    clock: ClockDep,
    fit: FitStatus | None = None,
    decision: Decision | None = None,
) -> views.OpportunityList:
    """The company's matches: Not eligible only under its filter, Not for us only under its
    decision filter."""
    return views.list_opportunities(session, caller.company_id, clock.today, fit, decision)


@router.get("/{opportunity_id}")
def get_opportunity(
    opportunity_id: uuid.UUID, session: SessionDep, caller: CallerDep, clock: ClockDep
) -> views.OpportunityDetail:
    return views.opportunity_detail(session, caller.company_id, opportunity_id, clock.today)


class DecisionIn(BaseModel):
    decision: Decision
    reason: NotForUsReason | None = None  # only with Not for us (DEC-01)


class DecisionOut(BaseModel):
    decision: Decision


class StartedOut(BaseModel):
    application_id: uuid.UUID


def _known(session: Session, opportunity_id: uuid.UUID) -> None:
    """Writes against an opportunity need it to exist and be current."""
    if opportunity_id not in {o.id for o in current_opportunities(session)}:
        raise NotFoundError("no such opportunity")


@router.put("/{opportunity_id}/decision")
def set_decision(
    opportunity_id: uuid.UUID,
    body: DecisionIn,
    session: SessionDep,
    caller: CallerDep,
    clock: ClockDep,
) -> DecisionOut:
    _known(session, opportunity_id)
    decided = matching.change_decision(
        session, caller, opportunity_id, (body.decision, body.reason), clock
    )
    return DecisionOut(decision=decided)


@router.post("/{opportunity_id}/application", status_code=status.HTTP_201_CREATED)
def start_application(
    opportunity_id: uuid.UUID, session: SessionDep, caller: CallerDep, clock: ClockDep
) -> StartedOut:
    """Open the workspace (or return the open one) and set Pursuing (DEC-02)."""
    _known(session, opportunity_id)
    application = applications.start_application(session, caller, opportunity_id, clock)
    return StartedOut(application_id=application.id)
