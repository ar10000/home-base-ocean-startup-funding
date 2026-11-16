"""Signed in as company A, try to read, list and change company B's records through every
endpoint (handbook section 13). All must fail and leave B's data as it was. The second
run switches off the code's company filter, so only the database's row-level security
stands between A and B."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Select, select
from sqlalchemy.orm import Session

from home_base.api import deps
from home_base.api.app import create_app
from home_base.core.context import Caller, Clock
from home_base.core.repository import TenantRepository
from home_base.jobs.reload_seed import reload_seed
from home_base.modules.companies.models import CompanyRow
from home_base.modules.opportunities.seed import load_seed_dir
from home_base.modules.opportunities.service import current_opportunities

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed"
TODAY = date(2026, 11, 11)
CLOCK = Clock(at=datetime(2026, 11, 11, 12, 0, tzinfo=UTC), today=TODAY, request_id="t")


@dataclass
class B:
    caller: Caller
    fact_id: str
    application_id: str
    question_id: str
    opportunity_id: str


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


def _company(session: Session, name: str) -> Caller:
    row = CompanyRow(name=name)
    session.add(row)
    session.flush()
    return Caller(row.id, uuid.uuid4())


def _client(session: Session, caller: Caller) -> TestClient:
    """Each request gets its own, later instant, as real requests do."""
    ticks = iter(range(1, 10_000))
    app = create_app()
    app.dependency_overrides[deps.session] = lambda: session
    app.dependency_overrides[deps.caller] = lambda: caller
    app.dependency_overrides[deps.clock] = lambda: Clock(
        at=CLOCK.at + timedelta(seconds=next(ticks)), today=TODAY, request_id="t"
    )
    return TestClient(app)


@pytest.fixture
def b(session: Session) -> B:
    """Company B's records, made through the API as B."""
    reload_seed(session, load_seed_dir(FIXTURES, TODAY), CLOCK)
    grant = next(
        o for o in current_opportunities(session) if o.record.name == "Fictional Ocean Grant"
    )
    caller = _company(session, "B")
    client = _client(session, caller)
    fact = client.post("/facts", json={"key": "country", "value": "ES", "label": "sourced"}).json()
    client.put("/founder-facts/woman_ceo", json={"value": True})
    client.put("/intent", json={"goals": [{"goal": "investment", "window": "now"}]})
    client.put(f"/opportunities/{grant.id}/decision", json={"decision": "later"})
    app_id = client.post(f"/opportunities/{grant.id}/application").json()["application_id"]
    question = str(grant.question_ids[0])
    client.put(f"/applications/{app_id}/answers/{question}", json={"text": "B's answer."})
    return B(caller, fact["id"], app_id, question, str(grant.id))


def _b_state(session: Session, b: B) -> dict[str, Any]:
    client = _client(session, b.caller)
    app = client.get(f"/applications/{b.application_id}").json()
    page = client.get(f"/opportunities/{b.opportunity_id}")
    assert page.status_code == 200, page.json()
    return {
        "profile": client.get("/profile").json(),
        "decision": client.get(f"/opportunities/{b.opportunity_id}").json()["decision"],
        "application": (app["status"], app["submitted_at"], app["questions"][0]["answer"]),
        "goal": client.get("/today").json()["current_goal"],
    }


def _attack(session: Session, b: B) -> None:
    a = _company(session, "A")
    client = _client(session, a)
    app, q = b.application_id, b.question_id
    # Reads and lists: nothing of B's shows.
    assert client.get("/profile").json() == {"facts": [], "founder_facts": [], "stage": None}
    assert client.get("/applications").json() == []
    assert client.get(f"/applications/{app}").status_code == 404
    page = client.get(f"/opportunities/{b.opportunity_id}").json()
    assert page["decision"] == "none"
    assert not [h for h in page["history"] if h["action"] == "decision.changed"]
    assert client.get("/today").json()["current_goal"] is None
    # Changes to B's records: all refused.
    assert client.post(f"/facts/{b.fact_id}/approve").status_code in (404, 422)
    assert (
        client.put(f"/applications/{app}/answers/{q}", json={"text": "A was here."}).status_code
        == 404
    )
    assert client.post(f"/applications/{app}/answers/{q}/approve").status_code == 404
    assert client.post(f"/applications/{app}/submitted").status_code == 404
    assert client.post(f"/applications/{app}/archive-not-eligible").status_code in (404, 409)
    assert client.delete("/founder-facts/woman_ceo").status_code == 404  # A has none; B's stays


def test_company_a_cannot_reach_company_b(session: Session, b: B) -> None:
    before = _b_state(session, b)
    _attack(session, b)
    assert _b_state(session, b) == before


def test_row_level_security_holds_when_the_code_filter_is_forgotten(
    session: Session, b: B, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _b_state(session, b)

    def unfiltered(self: TenantRepository, model: Any) -> Select[Any]:
        return select(model)  # the company filter "forgotten"

    monkeypatch.setattr(TenantRepository, "scoped", unfiltered)
    _attack(session, b)
    monkeypatch.undo()
    assert _b_state(session, b) == before
