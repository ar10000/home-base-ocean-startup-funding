"""Drafting an answer through the API, on a real Postgres with the fake provider
(D-81, DRF-01, DRF-02, ADR-009)."""

import json
import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from home_base.ai.fake import FakeProvider, local_reply
from home_base.ai.provider import Message
from home_base.api import deps
from home_base.api.app import create_app
from home_base.core.context import Caller, Clock
from home_base.jobs.reload_seed import reload_seed
from home_base.modules.applications.models import AnswerVersionFactRow, AnswerVersionRow
from home_base.modules.audit.models import AiAction, AuditEvent
from home_base.modules.companies.models import CompanyRow, FactEmbeddingRow
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
        # A failed draft commits its AI log entry (by design); clear what that kept.
        s.execute(text("TRUNCATE companies, ai_actions, audit_events, opportunities CASCADE"))
        s.commit()


def _company(session: Session, name: str) -> Caller:
    row = CompanyRow(name=name)
    session.add(row)
    session.flush()
    return Caller(row.id, uuid.uuid4())


def _client(session: Session, caller: Caller, provider: FakeProvider) -> TestClient:
    app = create_app()
    app.dependency_overrides[deps.session] = lambda: session
    app.dependency_overrides[deps.caller] = lambda: caller
    app.dependency_overrides[deps.clock] = lambda: CLOCK
    app.dependency_overrides[deps.ai_provider] = lambda: provider
    return TestClient(app)


@pytest.fixture
def a(session: Session) -> Caller:
    return _company(session, "A")


@pytest.fixture
def grant(session: Session) -> StoredOpportunity:
    reload_seed(session, load_seed_dir(FIXTURES, TODAY), CLOCK)
    return next(
        o for o in current_opportunities(session) if o.record.name == "Fictional Ocean Grant"
    )


def _fact(client: TestClient, key: str, value: Any, approve: bool = True) -> str:
    made = client.post("/facts", json={"key": key, "value": value, "label": "user_provided"})
    assert made.status_code == 201, made.text
    fact_id = str(made.json()["id"])
    if approve:
        client.post(f"/facts/{fact_id}/approve")
    return fact_id


def _start(client: TestClient, grant: StoredOpportunity) -> tuple[str, str]:
    app_id = str(client.post(f"/opportunities/{grant.id}/application").json()["application_id"])
    first = client.get(f"/applications/{app_id}").json()["questions"][0]["id"]
    return app_id, str(first)


def _sent(provider: FakeProvider) -> dict[str, Any]:
    """The task input the model received, from the last call."""
    content = provider.calls[-1][-1].content
    found: dict[str, Any] = json.loads(content[content.index("{") :])
    return found


def test_a_draft_is_built_from_approved_facts_and_links_to_them(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    fake = FakeProvider(local_reply)
    client = _client(session, a, fake)
    team = _fact(client, "team_size", 4)
    impact = _fact(client, "team", "Two marine biologists and a naval engineer.")
    app_id, question = _start(client, grant)

    done = client.post(f"/applications/{app_id}/answers/{question}/draft")

    assert done.status_code == 200, done.text
    q = done.json()["questions"][0]
    assert q["state"] == "ai_draft"
    assert "Team size: 4." in q["answer"]
    assert sorted(q["built_from"]) == sorted([team, impact])
    assert {(s["fact"], s["value"]) for s in q["sources"]} == {
        ("team_size", "4"),
        ("team", "Two marine biologists and a naval engineer."),
    }
    version = session.scalars(select(AnswerVersionRow)).one()
    assert version.kind == "ai_draft"
    links = session.scalars(select(AnswerVersionFactRow.fact_version_id)).all()
    assert sorted(map(str, links)) == sorted([team, impact])  # DRF-02
    action = session.get(AiAction, version.ai_action_id)
    assert action is not None
    assert (action.task, action.status, action.served_entity) == (
        "draft_answer",
        "succeeded",
        "application",
    )
    assert {"entity": "company_fact", "id": team} in action.input_refs
    assert "marine" not in json.dumps(action.input_refs)  # references only, never text
    drafted = (
        select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "answer.drafted")
    )
    assert session.scalar(drafted) == 1


def test_only_approved_facts_of_the_company_are_sent(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    other = _company(session, "B")
    _fact(_client(session, other, FakeProvider()), "traction", "Other company's secret pilot")
    fake = FakeProvider(local_reply)
    client = _client(session, a, fake)
    _fact(client, "team_size", 4)
    _fact(client, "impact", "Unapproved claim of 90% less waste.", approve=False)
    app_id, question = _start(client, grant)

    client.post(f"/applications/{app_id}/answers/{question}/draft")

    sent = json.dumps(_sent(fake))
    assert "4" in sent
    assert "Unapproved" not in sent  # DRF-01
    assert "secret pilot" not in sent  # another tenant's fact
    assert all("secret" not in t and "Unapproved" not in t for t in fake.embedded)


def test_retrieval_sends_the_required_facts_and_at_most_four_more(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    fake = FakeProvider(local_reply)
    client = _client(session, a, fake)
    _fact(client, "team_size", 4)
    _fact(client, "team", "Our team: two marine biologists and an engineer.")
    for key, value in [
        ("description", "Seaweed farming off Peniche."),
        ("impact", "Nitrogen uptake from coastal water."),
        ("traction", "One pilot with a fish farm."),
        ("country", "PT"),
        ("trl", 5),
        ("legal_form", "private_limited"),
    ]:
        _fact(client, key, value)
    app_id, question = _start(client, grant)  # "Describe your team.", requires team_size

    client.post(f"/applications/{app_id}/answers/{question}/draft")

    facts = _sent(fake)["facts"]
    assert facts[0]["fact"] == "team size"  # required facts come first
    assert len(facts) == 1 + 4
    assert "team" in [f["fact"] for f in facts]  # the closest to the question is retrieved
    embedded = len(fake.embedded)
    client.post(f"/applications/{app_id}/answers/{question}/draft")
    assert len(fake.embedded) == embedded + 1  # facts are embedded once; only the question again
    count = select(func.count()).select_from(FactEmbeddingRow)
    assert session.scalar(count) == 8


def _invalid(messages: Sequence[Message]) -> str:
    return json.dumps({"sentences": [{"text": "We employ 99 people.", "facts": ["F1"]}]})


def test_an_unsupported_number_fails_the_draft_and_saves_nothing_but_the_log(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    fake = FakeProvider(_invalid)
    client = _client(session, a, fake)
    _fact(client, "team_size", 4)
    app_id, question = _start(client, grant)

    failed = client.post(f"/applications/{app_id}/answers/{question}/draft")

    assert failed.status_code == 502
    assert failed.json()["type"] == "urn:home-base:problem:ai"
    assert len(fake.calls) == 2  # one retry, with the reasons
    assert "the number 99 is in no cited fact" in fake.calls[1][-1].content
    assert client.get(f"/applications/{app_id}").json()["questions"][0]["state"] == (
        "missing_facts"
    )
    assert session.scalar(select(func.count()).select_from(AnswerVersionRow)) == 0
    statuses = session.scalars(select(AiAction.status)).all()
    assert statuses == ["failed"]


def _cites_unknown(messages: Sequence[Message]) -> str:
    return json.dumps({"sentences": [{"text": "We are four.", "facts": ["F9"]}]})


def test_a_draft_citing_a_fact_it_was_not_given_is_refused(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    client = _client(session, a, FakeProvider(_cites_unknown))
    _fact(client, "team_size", 4)
    app_id, question = _start(client, grant)
    assert client.post(f"/applications/{app_id}/answers/{question}/draft").status_code == 502
    assert session.scalar(select(func.count()).select_from(AnswerVersionRow)) == 0


def test_no_approved_facts_means_no_draft(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    fake = FakeProvider(local_reply)
    client = _client(session, a, fake)
    _fact(client, "team_size", 4, approve=False)
    app_id, question = _start(client, grant)
    refused = client.post(f"/applications/{app_id}/answers/{question}/draft")
    assert refused.status_code == 409
    assert "approve at least one company fact" in refused.json()["detail"]
    assert fake.calls == []


def test_an_approved_answer_is_not_redrafted(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    client = _client(session, a, FakeProvider(local_reply))
    _fact(client, "team_size", 4)
    app_id, question = _start(client, grant)
    client.post(f"/applications/{app_id}/answers/{question}/draft")
    client.post(f"/applications/{app_id}/answers/{question}/approve")
    refused = client.post(f"/applications/{app_id}/answers/{question}/draft")
    assert refused.status_code == 409
    assert "edit it to reopen" in refused.json()["detail"]


def test_approving_a_draft_keeps_the_facts_it_was_built_from(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    client = _client(session, a, FakeProvider(local_reply))
    team = _fact(client, "team_size", 4)
    app_id, question = _start(client, grant)
    client.post(f"/applications/{app_id}/answers/{question}/draft")
    page = client.post(f"/applications/{app_id}/answers/{question}/approve").json()
    assert page["questions"][0]["built_from"] == [team]


def test_why_it_fits_words_the_calculated_fit_and_is_cached(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    fake = FakeProvider(local_reply)
    client = _client(session, a, fake)
    _fact(client, "country", "PT")
    first = client.post(f"/opportunities/{grant.id}/why-it-fits")
    assert first.status_code == 200, first.text
    fit = client.get(f"/opportunities/{grant.id}").json()["fit"]["status"]
    assert fit == "possible"
    assert first.json()["text"] == "May fit: Technology at TRL 4 or above."
    again = client.post(f"/opportunities/{grant.id}/why-it-fits")
    assert again.json() == first.json()
    assert len(fake.calls) == 1  # same results, same words, no second call
    sent = _sent(fake)
    assert sent["fit"] == "possible"
    assert [r["result"] for r in sent["requirements"]] == ["pass", "unknown", "ai_judgement"]
    _fact(client, "trl", 5)  # the results change, so the words are worked out again
    assert client.post(f"/opportunities/{grant.id}/why-it-fits").json()["text"].startswith("Fits")
    assert len(fake.calls) == 2


def test_why_it_fits_never_changes_the_fit(
    session: Session, a: Caller, grant: StoredOpportunity
) -> None:
    def contradicting(messages: Sequence[Message]) -> str:
        return json.dumps({"sentences": [{"text": "You are eligible.", "requirements": ["R1"]}]})

    client = _client(session, a, FakeProvider(contradicting))
    before = client.get(f"/opportunities/{grant.id}").json()["fit"]
    client.post(f"/opportunities/{grant.id}/why-it-fits")
    assert client.get(f"/opportunities/{grant.id}").json()["fit"] == before
