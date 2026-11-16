"""A write is committed before its response is sent, so a client that reads straight after
it sees the change. FastAPI's default would send the response first and commit after; the
session dependencies are declared with scope="function" to prevent that (deps.Db)."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from home_base.api import deps
from home_base.api.app import create_app
from home_base.core.context import Caller
from home_base.core.db import DATABASE_URL_ENV
from home_base.modules.companies.models import CompanyRow

pytestmark = pytest.mark.integration


@pytest.fixture
def company(
    alembic_config: Config, engine: Engine, postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[uuid.UUID]:
    command.upgrade(alembic_config, "head")
    monkeypatch.setenv(DATABASE_URL_ENV, postgres_url)
    deps.engine.cache_clear()
    with Session(engine) as s:
        row = CompanyRow(name="Commit Test")
        s.add(row)
        s.commit()
        company_id = row.id
    yield company_id
    deps.engine.cache_clear()
    # This test commits (the others roll back): remove what it wrote, so later tests start
    # from the empty database they expect.
    with engine.begin() as c:
        c.execute(text("TRUNCATE companies, audit_events CASCADE"))


def test_a_fact_is_committed_before_the_response_starts(engine: Engine, company: uuid.UUID) -> None:
    seen_at_response: list[int] = []

    def committed_facts() -> int:
        with engine.connect() as c:
            query = text("SELECT count(*) FROM company_facts WHERE company_id = :c")
            return int(c.execute(query, {"c": company}).scalar_one())

    app = create_app()
    app.dependency_overrides[deps.caller] = lambda: Caller(company, uuid.uuid4())

    async def watched(scope: dict[str, Any], receive: Any, send: Any) -> None:
        async def check_then_send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start" and scope["path"] == "/facts":
                seen_at_response.append(committed_facts())
            await send(message)

        await app(scope, receive, check_then_send)

    with TestClient(watched) as client:
        response = client.post(
            "/facts", json={"key": "team_size", "value": 4, "label": "user_provided"}
        )
    assert response.status_code == 201
    assert seen_at_response == [1]
