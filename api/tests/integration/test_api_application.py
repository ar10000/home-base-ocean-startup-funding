"""The Application screen and its writes through the API, on a real Postgres (PRG-01 to
PRG-03, D-09, D-53, D-62)."""

import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from home_base.api import deps
from home_base.api.app import create_app
from home_base.core.context import Caller, Clock
from home_base.jobs.reload_seed import reload_seed
from home_base.modules.audit.models import AuditEvent
from home_base.modules.companies.models import CompanyRow
from home_base.modules.opportunities.seed import load_seed_dir
from home_base.modules.opportunities.service import StoredOpportunity, current_opportunities

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


@pytest.fixture
def grant(session: Session) -> StoredOpportunity:
    seeds = load_seed_dir(FIXTURES, TODAY)
    other = replace(
        next(s for s in seeds if s.name == "Fictional Ocean Grant"),
        source="other.yaml",
        name="Other Grant",
    )
    reload_seed(session, [*seeds, other], CLOCK)
    return next(
        o for o in current_opportunities(session) if o.record.name == "Fictional Ocean Grant"
    )


def _start(client: TestClient, grant: StoredOpportunity) -> str:
    return str(client.post(f"/opportunities/{grant.id}/application").json()["application_id"])


def _events(session: Session, action: str) -> int:
    query = select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
    return int(session.scalar(query) or 0)


def test_no_applications(session: Session, a: Caller) -> None:
    assert _client(session, a).get("/applications").json() == []


def test_a_new_application(session: Session, a: Caller, grant: StoredOpportunity) -> None:
    client = _client(session, a)
    page: dict[str, Any] = client.get(f"/applications/{_start(client, grant)}").json()
    assert (page["status"], page["answers_ready"], page["opportunity"]) == (
        "not_started",
        {"ready": 0, "total": 2},
        "Fictional Ocean Grant",
    )
    assert page["deadline"] == {"kind": "date", "date": "2027-01-31", "days_left": None}
    assert [
        (q["position"], q["state"], q["missing"], q["draftable"], q["answer"])
        for q in page["questions"]
    ] == [
        (1, "missing_facts", ["team_size"], False, None),
        (2, "missing_facts", [], False, None),  # no facts listed: never draftable (D-24)
    ]
    assert page["no_longer_eligible"] is False


def test_an_approved_fact_makes_a_question_draftable(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    client = _client(session, a)
    app_id = _start(client, grant)
    fact = client.post(
        "/facts", json={"key": "team_size", "value": 4, "label": "user_provided"}
    ).json()
    assert (
        client.get(f"/applications/{app_id}").json()["questions"][0]["draftable"] is False
    )  # not approved
    client.post(f"/facts/{fact['id']}/approve")
    first = client.get(f"/applications/{app_id}").json()["questions"][0]
    assert (first["missing"], first["draftable"]) == ([], True)


def test_edit_approve_reopen_and_submit(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    client = _client(session, a)
    app_id = _start(client, grant)
    q1, q2 = (str(q) for q in grant.question_ids)
    page = client.put(f"/applications/{app_id}/answers/{q1}", json={"text": "We are four."}).json()
    assert (page["status"], page["questions"][0]["state"], page["questions"][0]["answer"]) == (
        "in_progress",
        "edited",
        "We are four.",
    )
    client.put(
        f"/applications/{app_id}/answers/{q1}", json={"text": "We are four people."}
    )  # autosave
    client.post(f"/applications/{app_id}/answers/{q1}/approve")
    client.put(f"/applications/{app_id}/answers/{q2}", json={"text": "The window is now."})
    page = client.post(f"/applications/{app_id}/answers/{q2}/approve").json()
    assert (page["status"], page["answers_ready"]) == ("ready", {"ready": 2, "total": 2})

    page = client.put(f"/applications/{app_id}/answers/{q1}", json={"text": "We are five."}).json()
    assert page["status"] == "in_progress"  # reopening an approved answer (D-09)
    client.post(f"/applications/{app_id}/answers/{q1}/approve")
    page = client.post(f"/applications/{app_id}/submitted").json()
    assert page["status"] == "submitted" and page["submitted_at"] is not None
    # State changes are audited; the text-only autosave is not (D-62).
    assert (_events(session, "answer.edited"), _events(session, "answer.approved")) == (3, 3)
    assert _events(session, "application.submitted") == 1


def test_repeats_write_nothing(session: Session, a: Caller, grant: StoredOpportunity) -> None:
    client = _client(session, a)
    app_id = _start(client, grant)
    q1 = str(grant.question_ids[0])
    client.put(f"/applications/{app_id}/answers/{q1}", json={"text": "Ours."})
    client.post(f"/applications/{app_id}/answers/{q1}/approve")
    client.post(f"/applications/{app_id}/submitted")
    events = int(session.scalar(select(func.count()).select_from(AuditEvent)) or 0)
    client.post(f"/applications/{app_id}/answers/{q1}/approve")
    client.post(f"/applications/{app_id}/submitted")
    assert int(session.scalar(select(func.count()).select_from(AuditEvent)) or 0) == events


def test_approving_an_answer_that_does_not_exist_is_refused(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    client = _client(session, a)
    app_id = _start(client, grant)
    response = client.post(f"/applications/{app_id}/answers/{grant.question_ids[0]}/approve")
    assert (response.status_code, response.json()["type"]) == (
        409,
        "urn:home-base:problem:application",
    )


def test_a_question_from_another_call_is_not_found(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    client = _client(session, a)
    app_id = _start(client, grant)
    other = next(o for o in current_opportunities(session) if o.record.name == "Other Grant")
    response = client.put(
        f"/applications/{app_id}/answers/{other.question_ids[0]}", json={"text": "x"}
    )
    assert response.status_code == 404
    assert client.get(f"/applications/{app_id}").json()["status"] == "not_started"


def test_no_longer_eligible_through_the_api(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    client = _client(session, a)
    app_id = _start(client, grant)
    assert (
        client.post(f"/applications/{app_id}/archive-not-eligible").status_code == 409
    )  # still eligible
    fact = client.post(
        "/facts", json={"key": "country", "value": "ES", "label": "user_provided"}
    ).json()
    client.post(f"/facts/{fact['id']}/approve")
    assert client.get(f"/applications/{app_id}").json()["no_longer_eligible"] is True
    assert client.post(f"/applications/{app_id}/archive-not-eligible").status_code == 204
    assert client.get(f"/applications/{app_id}").status_code == 404
    assert client.get("/applications").json() == []


def test_another_companys_application_is_not_found(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    b = _company(session, "B")
    theirs = _start(_client(session, b), grant)
    client = _client(session, a)
    assert client.get(f"/applications/{theirs}").status_code == 404
    q1 = grant.question_ids[0]
    assert client.put(f"/applications/{theirs}/answers/{q1}", json={"text": "x"}).status_code == 404
    assert client.post(f"/applications/{theirs}/submitted").status_code == 404
    assert _client(session, b).get(f"/applications/{theirs}").json()["status"] == "not_started"


def test_the_list_summarises_each_open_application(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    client = _client(session, a)
    app_id = _start(client, grant)
    assert client.get("/applications").json() == [
        {
            "id": app_id,
            "opportunity_id": str(grant.id),
            "opportunity": "Fictional Ocean Grant",
            "status": "not_started",
            "answers_ready": {"ready": 0, "total": 2},
            "call_removed": False,
        }
    ]


def test_an_application_whose_call_was_removed_stays_visible_read_only(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    """D-73: removing the call from the seed set keeps the application, read-only, with the
    questions the call last had."""
    client = _client(session, a)
    app_id = _start(client, grant)
    q1 = str(grant.question_ids[0])
    client.put(f"/applications/{app_id}/answers/{q1}", json={"text": "We are four."})
    before = client.get(f"/applications/{app_id}").json()
    assert before["call_removed"] is False

    remaining = [s for s in load_seed_dir(FIXTURES, TODAY) if s.name != "Fictional Ocean Grant"]
    reload_seed(session, remaining, CLOCK)

    listed = {x["id"]: x for x in client.get("/applications").json()}
    assert listed[app_id]["call_removed"] is True
    page = client.get(f"/applications/{app_id}").json()
    assert page["call_removed"] is True
    assert [q["text"] for q in page["questions"]] == [q["text"] for q in before["questions"]]
    assert page["questions"][0]["answer"] == "We are four."

    for refused in (
        client.put(f"/applications/{app_id}/answers/{q1}", json={"text": "changed"}),
        client.post(f"/applications/{app_id}/answers/{q1}/approve"),
        client.post(f"/applications/{app_id}/submitted"),
    ):
        assert refused.status_code == 409
        assert refused.json()["detail"] == (
            "this call is no longer listed, so the application is read-only"
        )
    assert client.get(f"/applications/{app_id}").json()["questions"][0]["answer"] == "We are four."


def test_a_call_that_comes_back_makes_its_application_editable_again(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    client = _client(session, a)
    app_id = _start(client, grant)
    seeds = load_seed_dir(FIXTURES, TODAY)
    reload_seed(session, [s for s in seeds if s.name != "Fictional Ocean Grant"], CLOCK)
    reload_seed(session, seeds, CLOCK)
    page = client.get(f"/applications/{app_id}").json()
    assert page["call_removed"] is False
    q1 = page["questions"][0]["id"]
    assert client.put(f"/applications/{app_id}/answers/{q1}", json={"text": "x"}).status_code == 200


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_prg_05_a_blank_answer_cannot_be_approved(
    session: Session, a: Caller, grant: StoredOpportunity, text: str
) -> None:
    client = _client(session, a)
    app_id = _start(client, grant)
    q1 = str(grant.question_ids[0])
    client.put(f"/applications/{app_id}/answers/{q1}", json={"text": text})
    refused = client.post(f"/applications/{app_id}/answers/{q1}/approve")
    assert refused.status_code == 409
    assert refused.json()["detail"] == "write an answer before approving it"
    question = client.get(f"/applications/{app_id}").json()["questions"][0]
    assert question["state"] != "approved"


def test_prg_05_a_question_never_answered_cannot_be_approved(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    client = _client(session, a)
    app_id = _start(client, grant)
    refused = client.post(f"/applications/{app_id}/answers/{grant.question_ids[0]}/approve")
    assert refused.status_code == 409
