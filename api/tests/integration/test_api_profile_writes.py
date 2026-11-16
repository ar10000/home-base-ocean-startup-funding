"""Profile, decision and start-application writes through the API, on a real Postgres:
each is validated, audited and recalculates; typed values only; one company at a time."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from home_base.api import deps
from home_base.api.app import create_app
from home_base.core.context import Caller, Clock
from home_base.jobs.reload_seed import reload_seed
from home_base.modules.audit.repository import AuditRepository
from home_base.modules.companies.models import CompanyRow
from home_base.modules.opportunities.seed import load_seed_dir
from home_base.modules.opportunities.service import current_opportunities

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed"
TODAY = date(2026, 11, 11)
CLOCK = Clock(at=datetime(2026, 11, 11, 12, 0, tzinfo=UTC), today=TODAY, request_id="t")


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
    app = create_app()
    app.dependency_overrides[deps.session] = lambda: session
    app.dependency_overrides[deps.caller] = lambda: caller
    app.dependency_overrides[deps.clock] = lambda: CLOCK
    return TestClient(app)


@pytest.fixture
def a(session: Session) -> Caller:
    return _company(session, "A")


def _grant(session: Session) -> uuid.UUID:
    reload_seed(session, load_seed_dir(FIXTURES, TODAY), CLOCK)
    return next(
        o.id for o in current_opportunities(session) if o.record.name == "Fictional Ocean Grant"
    )


def _grant_fit(client: TestClient) -> str:
    items = client.get("/opportunities").json()["items"]
    return str(next(i["fit"]["status"] for i in items if i["name"] == "Fictional Ocean Grant"))


def test_an_empty_profile(session: Session, a: Caller) -> None:
    assert _client(session, a).get("/profile").json() == {
        "facts": [],
        "founder_facts": [],
        "stage": None,
    }


def test_add_approve_and_edit_a_fact(session: Session, a: Caller) -> None:
    _grant(session)
    client = _client(session, a)
    for key, value in (("country", "PT"), ("trl", 4)):
        added = client.post("/facts", json={"key": key, "value": value, "label": "user_provided"})
        assert added.status_code == 201 and added.json()["approved"] is False
        assert client.post(f"/facts/{added.json()['id']}/approve").json()["approved"] is True
    assert _grant_fit(client) == "confirmed"
    client.post("/facts", json={"key": "trl", "value": 3, "label": "user_provided"})
    assert _grant_fit(client) == "possible"  # the edit needs approving again (D-49)
    profile = client.get("/profile").json()
    assert [(f["key"], f["value"], f["approved"]) for f in profile["facts"]] == [
        ("country", "PT", True),
        ("trl", 3, False),
    ]


@pytest.mark.parametrize(
    ("body", "status", "kind"),
    [
        ({"key": "trl", "value": "4", "label": "user_provided"}, 422, "fact"),  # text for a number
        ({"key": "trl", "value": True, "label": "user_provided"}, 422, "fact"),
        ({"key": "favourite_colour", "value": "blue", "label": "user_provided"}, 422, "fact"),
        ({"key": "trl", "value": 4, "label": "approved"}, 422, "validation"),
        ({"key": "trl", "label": "user_provided"}, 422, "validation"),
        ({"key": "trl", "value": 4.5, "label": "user_provided"}, 422, "validation"),
        # REQ-09: listed facts only take listed values (D-76)
        ({"key": "country", "value": "pt", "label": "user_provided"}, 422, "fact"),
        ({"key": "sector", "value": "Aquaculture", "label": "user_provided"}, 422, "fact"),
        ({"key": "legal_form", "value": "Lda", "label": "user_provided"}, 422, "fact"),
        ({"key": "applicant_form", "value": "both", "label": "user_provided"}, 422, "fact"),
    ],
)
def test_bad_facts_are_refused_with_a_problem(
    session: Session, a: Caller, body: dict[str, Any], status: int, kind: str
) -> None:
    response = _client(session, a).post("/facts", json=body)
    assert response.status_code == status
    assert response.json()["type"] == f"urn:home-base:problem:{kind}"


def test_another_companys_fact_cannot_be_approved(session: Session, a: Caller) -> None:
    b = _company(session, "B")
    theirs = (
        _client(session, b)
        .post("/facts", json={"key": "country", "value": "ES", "label": "sourced"})
        .json()
    )
    response = _client(session, a).post(f"/facts/{theirs['id']}/approve")
    assert response.status_code == 422  # "no such fact version", never confirming it exists
    assert _client(session, b).get("/profile").json()["facts"][0]["approved"] is False


def test_founder_facts_set_approve_delete(session: Session, a: Caller) -> None:
    client = _client(session, a)
    assert client.put(
        "/founder-facts/youngest_founder_birth_date", json={"value": "1997-02-01"}
    ).json() == {
        "key": "youngest_founder_birth_date",
        "value": "1997-02-01",
        "approved": False,
    }
    assert (
        client.post("/founder-facts/youngest_founder_birth_date/approve").json()["approved"] is True
    )
    assert client.put("/founder-facts/woman_ceo", json={"value": "yes"}).status_code == 422
    assert client.delete("/founder-facts/youngest_founder_birth_date").status_code == 204
    assert client.delete("/founder-facts/youngest_founder_birth_date").status_code == 404
    assert client.get("/profile").json()["founder_facts"] == []


def test_intent_is_validated_and_recorded(session: Session, a: Caller) -> None:
    client = _client(session, a)
    assert (
        client.put("/intent", json={"goals": []}).json()["type"] == "urn:home-base:problem:intent"
    )
    twice = {
        "goals": [
            {"goal": "investment", "window": "now"},
            {"goal": "investment", "window": "later"},
        ]
    }
    assert client.put("/intent", json=twice).status_code == 422
    ok = client.put("/intent", json={"goals": [{"goal": "investment", "window": "later"}]})
    assert ok.json()["goals"] == [{"goal": "investment", "window": "later"}]
    assert client.get("/today").json()["current_goal"] == [
        {"goal": "investment", "window": "later"}
    ]


def test_decisions_through_the_api(session: Session, a: Caller) -> None:
    grant = _grant(session)
    client = _client(session, a)
    assert client.put(f"/opportunities/{grant}/decision", json={"decision": "later"}).json() == {
        "decision": "later"
    }
    bad = client.put(
        f"/opportunities/{grant}/decision", json={"decision": "later", "reason": "too_early"}
    )
    assert (bad.status_code, bad.json()["type"]) == (422, "urn:home-base:problem:decision")
    unknown = client.put(f"/opportunities/{uuid.uuid4()}/decision", json={"decision": "later"})
    assert unknown.status_code == 404
    history = AuditRepository(session, a.company_id).history("opportunity", grant)
    assert [e.action for e in history if e.action == "decision.changed"] == ["decision.changed"]


def test_starting_an_application_sets_pursuing_and_repeats_safely(
    session: Session, a: Caller
) -> None:
    grant = _grant(session)
    client = _client(session, a)
    first = client.post(f"/opportunities/{grant}/application")
    again = client.post(f"/opportunities/{grant}/application")
    assert first.status_code == 201 and again.json() == first.json()
    page = client.get(f"/opportunities/{grant}").json()
    assert page["decision"] == "pursuing"
    assert client.post(f"/opportunities/{uuid.uuid4()}/application").status_code == 404


def test_req_09_listed_values_are_accepted_and_offered(session: Session, a: Caller) -> None:
    client = _client(session, a)
    for key, value in (
        ("sector", "marine_living_resources"),
        ("legal_form", "private_limited"),
        ("country", "OTHER"),
    ):
        added = client.post("/facts", json={"key": key, "value": value, "label": "user_provided"})
        assert added.status_code == 201, key
    options = client.get("/fact-options").json()
    assert set(options) == {"country", "sector", "legal_form", "applicant_form"}
    assert options["applicant_form"] == [
        {"value": "alone", "label": "Alone"},
        {"value": "consortium", "label": "In a consortium"},
    ]
    assert {"value": "PT", "label": "Portugal"} in options["country"]


def test_d78_the_founder_sets_a_stage_shown_on_profile_and_today(
    session: Session, a: Caller
) -> None:
    client = _client(session, a)
    assert client.get("/profile").json()["stage"] is None
    assert client.get("/today").json()["stage"] is None
    stages = client.get("/stages").json()
    assert [s["value"] for s in stages][:2] == ["idea", "validation"]
    assert len(stages) == 9
    assert client.put("/stage", json={"stage": "non_dilutive_funding"}).status_code == 204
    assert client.get("/profile").json()["stage"] == "non_dilutive_funding"
    assert client.get("/today").json()["stage"] == {
        "value": "non_dilutive_funding",
        "label": "Non-dilutive funding",
        "position": 6,
        "total": 9,
    }


def test_d78_a_stage_change_is_audited_once(session: Session, a: Caller) -> None:
    client = _client(session, a)
    client.put("/stage", json={"stage": "pilot"})
    client.put("/stage", json={"stage": "pilot"})  # the same again: nothing written
    client.put("/stage", json={"stage": "growth"})
    rows = session.execute(
        text(
            "SELECT before, after FROM audit_events "
            "WHERE action = 'company.stage_changed' ORDER BY occurred_at, id"
        )
    ).all()
    assert [(r.before, r.after) for r in rows] == [
        ({"stage": None}, {"stage": "pilot"}),
        ({"stage": "pilot"}, {"stage": "growth"}),
    ]


@pytest.mark.parametrize("stage", ["Pilot", "series_a", ""])
def test_d78_an_unknown_stage_is_refused(session: Session, a: Caller, stage: str) -> None:
    response = _client(session, a).put("/stage", json={"stage": stage})
    assert response.status_code == 422
    assert response.json()["type"] == "urn:home-base:problem:stage"
