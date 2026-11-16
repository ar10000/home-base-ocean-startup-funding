"""Per-request dependencies: the database transaction, the clock, the caller.

One transaction per request: committed when the route returns, rolled back on any
error, so a change and its audit event are saved together or not at all.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from home_base.api import auth
from home_base.api.auth import Identity
from home_base.core.context import Caller, Clock
from home_base.core.dates import local_today
from home_base.core.db import database_url
from home_base.core.errors import NotOnboardedError, NotSignedInError
from home_base.modules.accounts import service as accounts


@lru_cache(maxsize=1)
def engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)


def session() -> Iterator[Session]:
    """Declared through `Db` below, so the commit happens before the response is sent."""
    with Session(engine()) as s:
        try:
            yield s
            s.commit()
        except BaseException:
            s.rollback()
            raise


# scope="function": the transaction ends (commit or rollback) when the route returns and
# before the response is sent, so a client that reads right after a write sees it. With the
# default scope, FastAPI sends the response first and commits after (found 2026-11-16).
Db = Annotated[Session, Depends(session, scope="function")]


def clock(request: Request) -> Clock:
    """Read the clock once per request; rules and services get it passed in."""
    now = datetime.now(UTC)
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    return Clock(at=now, today=local_today(now), request_id=request_id)


def identity(request: Request) -> Identity:
    """The verified sign-in token from the Authorization header."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise NotSignedInError("sign in to continue")
    return auth.verifier().verify(token)


def user(
    db: Db,
    who: Annotated[Identity, Depends(identity)],
    now: Annotated[Clock, Depends(clock)],
) -> uuid.UUID:
    """The signed-in user, created on first sign-in (D-64)."""
    return accounts.user_for_subject(db, who.subject, now)


def caller(db: Db, user_id: Annotated[uuid.UUID, Depends(user)]) -> Caller:
    """The signed-in founder and their company; a user with no company is not onboarded."""
    company = accounts.company_of(db, user_id)
    if company is None:
        raise NotOnboardedError("set up your company first")
    return Caller(company_id=company, user_id=user_id)


APP_ROLE = "home_base_app"


def tenant_session(db: Db, who: Annotated[Caller, Depends(caller)]) -> Iterator[Session]:
    """The request's transaction as the app role with the caller's company set, so the
    database's row-level security is the second guard (handbook section 13, D-63).
    Both are reset when the request ends."""
    db.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
    db.execute(text("SELECT set_config('app.company_id', :c, true)"), {"c": str(who.company_id)})
    try:
        yield db
    finally:
        db.execute(text("RESET ROLE"))
        db.execute(text("SELECT set_config('app.company_id', '', true)"))


TenantDb = Annotated[Session, Depends(tenant_session, scope="function")]
