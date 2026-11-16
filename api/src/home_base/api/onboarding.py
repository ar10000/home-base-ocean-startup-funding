"""Who is signed in, and self sign-up of a company (D-64)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from home_base.api import deps
from home_base.api.auth import Identity
from home_base.core.context import Clock
from home_base.modules.accounts import service as accounts

router = APIRouter(tags=["account"])


class Me(BaseModel):
    user_id: uuid.UUID
    company_id: uuid.UUID | None  # None: onboarding comes first
    given_name: str | None  # from the token, for the greeting; never stored


class OnboardingIn(BaseModel):
    company_name: str


@router.get("/me")
def me(
    session: deps.Db,
    who: Annotated[Identity, Depends(deps.identity)],
    user_id: Annotated[uuid.UUID, Depends(deps.user)],
) -> Me:
    return Me(
        user_id=user_id, company_id=accounts.company_of(session, user_id), given_name=who.given_name
    )


@router.post("/onboarding", status_code=status.HTTP_201_CREATED)
def onboard(
    body: OnboardingIn,
    session: deps.Db,
    user_id: Annotated[uuid.UUID, Depends(deps.user)],
    clock: Annotated[Clock, Depends(deps.clock)],
) -> Me:
    company = accounts.onboard(session, user_id, body.company_name, clock)
    return Me(user_id=user_id, company_id=company, given_name=None)
