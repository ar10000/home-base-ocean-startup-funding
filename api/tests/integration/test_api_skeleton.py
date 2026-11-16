"""The API skeleton on a real Postgres: health, RFC 9457 problems, one transaction per
request, the clock, and no caller until sign-in exists."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

import pytest
from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from home_base.api import deps
from home_base.api.app import create_app
from home_base.core import errors
from home_base.core.context import Caller, Clock
from home_base.core.db import DATABASE_URL_ENV
from home_base.modules.companies.models import CompanyRow

pytestmark = pytest.mark.integration

COMMITTED = ("committed-co", "rolled-back-co")


@pytest.fixture
def app(
    alembic_config: Config, postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[FastAPI]:
    command.upgrade(alembic_config, "head")
    monkeypatch.setenv(DATABASE_URL_ENV, postgres_url)
    monkeypatch.setenv("GIT_SHA", "abc1234")
    deps.engine.cache_clear()
    application = create_app()

    class Body(BaseModel):
        name: str

    @application.post("/test/write")
    def write(
        body: Body, session: Annotated[Session, Depends(deps.session)], fail: bool = False
    ) -> dict[str, str]:
        session.add(CompanyRow(name=body.name))
        session.flush()
        if fail:
            raise errors.FactError("unknown fact 'x'")
        return {"ok": "yes"}

    @application.get("/test/raise/{kind}")
    def raise_(kind: str) -> None:
        raise getattr(errors, kind)("what went wrong")

    @application.get("/test/clock")
    def show_clock(clock: Annotated[Clock, Depends(deps.clock)]) -> dict[str, str | None]:
        return {
            "at": clock.at.isoformat(),
            "today": clock.today.isoformat(),
            "request_id": clock.request_id,
        }

    @application.get("/test/me")
    def me(caller: Annotated[Caller, Depends(deps.caller)]) -> dict[str, str]:
        return {"company": str(caller.company_id)}

    yield application
    # These tests really commit; remove what they wrote so other tests see an empty database.
    with Session(deps.engine()) as s, s.begin():
        s.execute(delete(CompanyRow).where(CompanyRow.name.in_(COMMITTED)))
    deps.engine.cache_clear()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _companies(engine: Engine, name: str) -> int:
    with Session(engine) as s:
        return int(
            s.scalar(select(func.count()).select_from(CompanyRow).where(CompanyRow.name == name))
            or 0
        )


def test_health_reports_status_sha_and_migration(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["git_sha"] == "abc1234"
    assert body["migration"]  # the head revision


@pytest.mark.parametrize(
    ("kind", "status", "slug"),
    [
        ("NotFoundError", 404, "not-found"),
        ("TenantError", 404, "not-found"),
        ("NotSignedInError", 401, "not-signed-in"),
        ("FactError", 422, "fact"),
        ("IntentError", 422, "intent"),
        ("DecisionError", 422, "decision"),
        ("ApplicationError", 409, "application"),
        ("ClockError", 422, "clock"),
        ("EligibilityRuleError", 500, "internal"),  # our data, not the caller's fault
    ],
)
def test_domain_errors_are_problem_details(
    client: TestClient, kind: str, status: int, slug: str
) -> None:
    response = client.get(f"/test/raise/{kind}")
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"] == f"urn:home-base:problem:{slug}"
    assert body["status"] == status
    if status == 500:
        assert body["detail"] == "Something went wrong on our side."  # nothing internal leaks
    else:
        assert body["detail"] == "what went wrong"


def test_a_bad_body_is_a_validation_problem(client: TestClient) -> None:
    response = client.post("/test/write", json={})
    assert response.status_code == 422
    assert response.json()["type"] == "urn:home-base:problem:validation"
    assert "name" in response.json()["detail"]


def test_a_request_commits_when_it_succeeds(client: TestClient, engine: Engine) -> None:
    assert client.post("/test/write", json={"name": "committed-co"}).status_code == 200
    assert _companies(engine, "committed-co") == 1


def test_a_request_that_fails_writes_nothing(client: TestClient, engine: Engine) -> None:
    response = client.post("/test/write?fail=true", json={"name": "rolled-back-co"})
    assert response.status_code == 422
    assert _companies(engine, "rolled-back-co") == 0


def test_the_clock_is_read_once_and_carries_the_request_id(client: TestClient) -> None:
    body = client.get("/test/clock", headers={"x-request-id": "req-42"}).json()
    at = datetime.fromisoformat(body["at"])
    assert at.tzinfo is not None and at.utcoffset() == UTC.utcoffset(at)
    assert body["request_id"] == "req-42"
    assert client.get("/test/clock").json()["request_id"]  # generated when absent


def test_nobody_is_signed_in_until_sign_in_exists(client: TestClient) -> None:
    response = client.get("/test/me")
    assert response.status_code == 401
    assert response.json()["type"] == "urn:home-base:problem:not-signed-in"
