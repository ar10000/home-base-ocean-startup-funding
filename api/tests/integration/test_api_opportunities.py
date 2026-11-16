"""GET /opportunities and /opportunities/{id} on a real Postgres: what is listed, in what
order, with which labels, and nothing written by a read."""

import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from home_base.api import deps
from home_base.api.app import create_app
from home_base.core.context import Caller, Clock
from home_base.core.vocabulary import Decision
from home_base.jobs.reload_seed import reload_seed
from home_base.modules.companies import service as companies
from home_base.modules.companies.domain import FactLabel, Goal, GoalChoice, Window
from home_base.modules.companies.models import CompanyRow
from home_base.modules.matching import service as matching
from home_base.modules.matching.models import MatchRow
from home_base.modules.opportunities.seed import SeedOpportunity, load_seed_dir

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed"
TODAY = date(2026, 11, 11)
AT = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def _seeds() -> list[SeedOpportunity]:
    found = {s.name: s for s in load_seed_dir(FIXTURES, TODAY)}
    grant, accelerator = found["Fictional Ocean Grant"], found["Fictional Accelerator Batch"]
    return [
        grant,  # open, deadline 2027-01-31 (81 days), blue-specific
        accelerator,  # upcoming, expected 2027-03 with a 2026 previous edition
        replace(grant, source="near-grant.yaml", name="Near Grant", deadline=date(2026, 12, 11)),
        replace(
            grant, source="closed-grant.yaml", name="Closed Grant", deadline=date(2026, 11, 10)
        ),
        replace(accelerator, source="no-evidence.yaml", name="Rumoured Batch", evidence=()),
    ]


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def caller(session: Session) -> Caller:
    row = CompanyRow(name="A")
    session.add(row)
    session.flush()
    return Caller(row.id, uuid.uuid4())


def _client(session: Session, caller: Caller, today: date = TODAY) -> TestClient:
    app: FastAPI = create_app()
    app.dependency_overrides[deps.session] = lambda: session
    app.dependency_overrides[deps.caller] = lambda: caller
    app.dependency_overrides[deps.clock] = lambda: Clock(at=AT, today=today, request_id="t")
    return TestClient(app)


def _approve(session: Session, caller: Caller, key: str, value: str | int) -> None:
    v = companies.add_fact(
        session, caller, companies.NewFact(key, value, FactLabel.USER_PROVIDED), Clock(AT, TODAY)
    )
    companies.approve_fact(session, caller, v.id, Clock(AT, TODAY))


def _names(body: dict) -> list[str]:  # type: ignore[type-arg]
    return [i["name"] for i in body["items"]]


def test_no_opportunities_lists_nothing(session: Session, caller: Caller) -> None:
    body = _client(session, caller).get("/opportunities").json()
    assert body == {"items": [], "counts": {"confirmed": 0, "possible": 0, "not_eligible": 0}}


def test_closed_and_unbacked_upcoming_calls_are_not_listed(
    session: Session, caller: Caller
) -> None:
    reload_seed(session, _seeds(), Clock(AT, TODAY))
    names = _names(_client(session, caller).get("/opportunities").json())
    assert "Closed Grant" not in names and "Rumoured Batch" not in names
    assert sorted(names) == ["Fictional Accelerator Batch", "Fictional Ocean Grant", "Near Grant"]


def test_deadlines_are_shown_as_the_rule_says(session: Session, caller: Caller) -> None:
    reload_seed(session, _seeds(), Clock(AT, TODAY))
    items = {i["name"]: i for i in _client(session, caller).get("/opportunities").json()["items"]}
    assert items["Near Grant"]["deadline"] == {
        "kind": "days_left",
        "date": "2026-12-11",
        "days_left": 30,
    }
    assert items["Fictional Ocean Grant"]["deadline"] == {
        "kind": "date",
        "date": "2027-01-31",
        "days_left": None,
    }
    assert items["Fictional Accelerator Batch"]["deadline"]["kind"] == "rolling"
    upcoming = items["Fictional Accelerator Batch"]
    assert (upcoming["status"], upcoming["expected_month"], upcoming["based_on_last_edition"]) == (
        "upcoming",
        "2027-03",
        True,
    )


def test_the_order_is_fit_then_date_then_scope_then_name(session: Session, caller: Caller) -> None:
    reload_seed(session, _seeds(), Clock(AT, TODAY))
    _approve(session, caller, "country", "PT")
    _approve(session, caller, "trl", 5)
    names = _names(_client(session, caller).get("/opportunities").json())
    # Both grants Confirmed: nearer deadline first; the accelerator is Possible.
    assert names == ["Near Grant", "Fictional Ocean Grant", "Fictional Accelerator Batch"]


def test_goal_relevant_opportunities_come_first(session: Session, caller: Caller) -> None:
    reload_seed(session, _seeds(), Clock(AT, TODAY))
    _approve(session, caller, "country", "PT")
    _approve(session, caller, "trl", 5)
    companies.set_intent(
        session, caller, [GoalChoice(Goal.ACCELERATOR_PLACE, Window.NOW)], Clock(AT, TODAY)
    )
    body = _client(session, caller).get("/opportunities").json()
    assert _names(body)[0] == "Fictional Accelerator Batch"
    assert [i["goal_relevant"] for i in body["items"]] == [True, False, False]


def test_not_eligible_is_counted_but_listed_only_under_its_filter(
    session: Session, caller: Caller
) -> None:
    reload_seed(session, _seeds(), Clock(AT, TODAY))
    _approve(session, caller, "country", "ES")
    client = _client(session, caller)
    body = client.get("/opportunities").json()
    assert _names(body) == ["Fictional Accelerator Batch"]
    assert body["counts"] == {"confirmed": 0, "possible": 1, "not_eligible": 2}
    assert sorted(_names(client.get("/opportunities?fit=not_eligible").json())) == [
        "Fictional Ocean Grant",
        "Near Grant",
    ]


def test_not_for_us_is_hidden_unless_filtered(session: Session, caller: Caller) -> None:
    reload_seed(session, _seeds(), Clock(AT, TODAY))
    client = _client(session, caller)
    grant = next(
        i for i in client.get("/opportunities").json()["items"] if i["name"] == "Near Grant"
    )
    matching.change_decision(
        session, caller, uuid.UUID(grant["id"]), (Decision.NOT_FOR_US, None), Clock(AT, TODAY)
    )
    assert "Near Grant" not in _names(client.get("/opportunities").json())
    filtered = client.get("/opportunities?decision=not_for_us").json()
    assert _names(filtered) == ["Near Grant"]
    assert filtered["items"][0]["decision"] == "not_for_us"


def test_readiness_counts_draftable_questions(session: Session, caller: Caller) -> None:
    reload_seed(session, _seeds(), Clock(AT, TODAY))
    client = _client(session, caller)
    items = {i["name"]: i for i in client.get("/opportunities").json()["items"]}
    assert items["Fictional Ocean Grant"]["readiness"] == {"ready": 0, "total": 2}
    assert items["Fictional Accelerator Batch"]["readiness"] is None  # questions unknown
    _approve(session, caller, "team_size", 4)
    items = {i["name"]: i for i in client.get("/opportunities").json()["items"]}
    # "Describe your team" needs team_size; "Why now?" lists no facts, so is never draftable (D-24).
    assert items["Fictional Ocean Grant"]["readiness"] == {"ready": 1, "total": 2}


def test_recheck_due_after_the_review_interval(session: Session, caller: Caller) -> None:
    reload_seed(session, _seeds(), Clock(AT, TODAY))
    # The grant was verified 2026-11-02; with a far deadline it is reviewed every 14 days.
    on_day_14 = {
        i["name"]: i
        for i in _client(session, caller, date(2026, 11, 16)).get("/opportunities").json()["items"]
    }
    on_day_15 = {
        i["name"]: i
        for i in _client(session, caller, date(2026, 11, 17)).get("/opportunities").json()["items"]
    }
    assert on_day_14["Fictional Ocean Grant"]["recheck_due"] is False
    assert on_day_15["Fictional Ocean Grant"]["recheck_due"] is True
    assert on_day_15["Fictional Ocean Grant"]["checked_days_ago"] == 15


def test_a_read_writes_nothing_even_when_nothing_was_matched(
    session: Session, caller: Caller
) -> None:
    reload_seed(session, _seeds(), Clock(AT, TODAY))
    row = CompanyRow(name="Unmatched")  # created after the reload: never recalculated
    session.add(row)
    session.flush()
    before = session.scalar(select(func.count()).select_from(MatchRow))
    body = _client(session, Caller(row.id, uuid.uuid4())).get("/opportunities").json()
    assert {i["fit"]["status"] for i in body["items"]} == {"possible"}
    assert session.scalar(select(func.count()).select_from(MatchRow)) == before


def test_the_opportunity_page(session: Session, caller: Caller) -> None:
    reload_seed(session, _seeds(), Clock(AT, TODAY))
    _approve(session, caller, "country", "PT")
    client = _client(session, caller)
    grant_id = next(
        i["id"]
        for i in client.get("/opportunities").json()["items"]
        if i["name"] == "Fictional Ocean Grant"
    )
    matching.change_decision(
        session, caller, uuid.UUID(grant_id), (Decision.LATER, None), Clock(AT, TODAY)
    )
    page = client.get(f"/opportunities/{grant_id}").json()
    assert [(r["hard"], r["fact"], r["result"]) for r in page["requirements"]] == [
        (True, "country", "pass"),
        (True, "trl", "unknown"),
        (False, None, "ai_judgement"),
    ]
    assert (page["questions_total"], page["questions_draftable"], page["decision"]) == (
        2,
        0,
        "later",
    )
    assert page["source_url"] == "https://example.org/fictional-ocean-grant"
    assert [h["action"] for h in page["history"]][-1] == "decision.changed"
    assert "match.recalculated" in [h["action"] for h in page["history"]]


def test_an_unknown_opportunity_is_not_found(session: Session, caller: Caller) -> None:
    response = _client(session, caller).get(f"/opportunities/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["type"] == "urn:home-base:problem:not-found"


def test_another_companys_history_is_not_shown(session: Session, caller: Caller) -> None:
    reload_seed(session, _seeds(), Clock(AT, TODAY))
    other = CompanyRow(name="B")
    session.add(other)
    session.flush()
    b = Caller(other.id, uuid.uuid4())
    grant_id = next(
        i["id"]
        for i in _client(session, caller).get("/opportunities").json()["items"]
        if i["name"] == "Near Grant"
    )
    matching.change_decision(
        session, b, uuid.UUID(grant_id), (Decision.PURSUING, None), Clock(AT, TODAY)
    )
    page = _client(session, caller).get(f"/opportunities/{grant_id}").json()
    assert page["decision"] == "none"
    assert "decision.changed" not in [h["action"] for h in page["history"]]


def test_an_upcoming_call_with_an_official_opening_sorts_by_that_date(
    session: Session, caller: Caller
) -> None:
    accelerator = next(s for s in _seeds() if s.name == "Fictional Accelerator Batch")
    official = replace(
        accelerator,
        source="opening-batch.yaml",
        name="Opening Batch",
        expected_month=None,
        evidence=(),  # an official opening date needs no evidence (UPC-02)
        opening=date(2026, 12, 1),
    )
    reload_seed(session, [accelerator, official], Clock(AT, TODAY))
    body = _client(session, caller).get("/opportunities").json()
    assert _names(body) == ["Opening Batch", "Fictional Accelerator Batch"]  # Dec 1 before Mar 1
    assert body["items"][0]["opening"] == "2026-12-01"
