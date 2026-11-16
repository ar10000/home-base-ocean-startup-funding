"""Application screen and its writes (spec: Application). Routes only call services and
views; every write is audited in the request's transaction."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from home_base.api import deps
from home_base.core.context import Caller, Clock
from home_base.modules.applications import service as applications
from home_base.views import application as views

router = APIRouter(prefix="/applications", tags=["applications"])

SessionDep = deps.TenantDb
CallerDep = Annotated[Caller, Depends(deps.caller)]
ClockDep = Annotated[Clock, Depends(deps.clock)]


class AnswerIn(BaseModel):
    text: str


@router.get("")
def list_applications(
    session: SessionDep, caller: CallerDep, clock: ClockDep
) -> list[views.ApplicationSummary]:
    return views.application_list(session, caller.company_id, clock.today)


@router.get("/{application_id}")
def get_application(
    application_id: uuid.UUID, session: SessionDep, caller: CallerDep, clock: ClockDep
) -> views.ApplicationOut:
    return views.application_view(session, caller.company_id, application_id, clock.today)


@router.put("/{application_id}/answers/{question_id}")
def save_answer(
    application_id: uuid.UUID,
    question_id: uuid.UUID,
    body: AnswerIn,
    session: SessionDep,
    caller: CallerDep,
    clock: ClockDep,
) -> views.ApplicationOut:
    """Autosave the founder's text (D-62)."""
    applications.edit_answer(session, caller, (application_id, question_id), body.text, clock)
    return views.application_view(session, caller.company_id, application_id, clock.today)


@router.post("/{application_id}/answers/{question_id}/approve")
def approve_answer(
    application_id: uuid.UUID,
    question_id: uuid.UUID,
    session: SessionDep,
    caller: CallerDep,
    clock: ClockDep,
) -> views.ApplicationOut:
    applications.approve_answer(session, caller, (application_id, question_id), clock)
    return views.application_view(session, caller.company_id, application_id, clock.today)


@router.post("/{application_id}/submitted")
def mark_submitted(
    application_id: uuid.UUID, session: SessionDep, caller: CallerDep, clock: ClockDep
) -> views.ApplicationOut:
    """The founder marks it submitted; nothing is submitted from the platform."""
    applications.mark_submitted(session, caller, application_id, clock)
    return views.application_view(session, caller.company_id, application_id, clock.today)


@router.post("/{application_id}/archive-not-eligible", status_code=204)
def archive_not_eligible(
    application_id: uuid.UUID, session: SessionDep, caller: CallerDep, clock: ClockDep
) -> None:
    """Confirm an application no longer eligible: it is archived, never deleted (INT-04)."""
    applications.confirm_no_longer_eligible(session, caller, application_id, clock)
