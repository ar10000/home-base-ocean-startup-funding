"""Today screen (spec: Today). The route only calls the view."""

from typing import Annotated

from fastapi import APIRouter, Depends

from home_base.api import deps
from home_base.core.context import Caller, Clock
from home_base.views.today import Today, today_view

router = APIRouter(tags=["today"])


@router.get("/today")
def get_today(
    session: deps.TenantDb,
    caller: Annotated[Caller, Depends(deps.caller)],
    clock: Annotated[Clock, Depends(deps.clock)],
) -> Today:
    return today_view(session, caller.company_id, clock.today)
