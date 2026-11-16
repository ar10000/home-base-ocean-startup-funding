"""GET /today on a real Postgres: the rules pick the mode, the one thing, what needs
attention, the next deadline, what is opening soon and the fact that unlocks most."""

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
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from home_base.api import deps
from home_base.api.app import create_app
from home_base.core.context import Caller, Clock
from home_base.core.vocabulary import Decision
from home_base.jobs.reload_seed import reload_seed
from home_base.modules.applications import service as applications
from home_base.modules.applications.repository import ApplicationRepository
from home_base.modules.companies import service as companies
from home_base.modules.companies.domain import FactLabel, Goal, GoalChoice, Window
from home_base.modules.companies.models import CompanyRow
from home_base.modules.matching import service as matching
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


@pytest.fixture
def caller(session: Session) -> Caller:
    row = CompanyRow(name="A")
    session.add(row)
    session.flush()
    return Caller(row.id, uuid.uuid4())


def _today(session: Session, caller: Caller) -> dict[str, Any]:
    app = create_app()
    app.dependency_overrides[deps.session] = lambda: session
    app.dependency_overrides[deps.caller] = lambda: caller
    app.dependency_overrides[deps.clock] = lambda: CLOCK
    body: dict[str, Any] = TestClient(app).get("/today").json()
    return body


def _load(session: Session) -> dict[str, StoredOpportunity]:
    seeds = {s.name: s for s in load_seed_dir(FIXTURES, TODAY)}
    soon = replace(
        seeds["Fictional Accelerator Batch"],
        source="soon-batch.yaml",
        name="Soon Batch",
        expected_month=None,
        evidence=(),
        opening=date(2026, 11, 30),  # 19 days away
        verified_on=date(2026, 11, 10),  # current
    )
    reload_seed(session, [*seeds.values(), soon], CLOCK)
    return {o.record.name: o for o in current_opportunities(session)}


def _approve(session: Session, caller: Caller, key: str, value: str | int) -> None:
    v = companies.add_fact(
        session, caller, companies.NewFact(key, value, FactLabel.USER_PROVIDED), CLOCK
    )
    companies.approve_fact(session, caller, v.id, CLOCK)


def _kinds(tasks: list[dict[str, Any]]) -> list[tuple[str, str | None]]:
    return [(t["type"], t["fact"] or t["opportunity"]) for t in tasks]


def test_nothing_yet_asks_to_check_goals(session: Session, caller: Caller) -> None:
    """No opportunities and no intent: preparing, and the never-set intent is untouched."""
    body = _today(session, caller)
    assert body["mode"] == "preparing"
    assert (body["one_thing"]["type"], body["one_thing"]["minutes"]) == ("check_goals", 5)
    assert body["needs_attention"] == [] and body["opening_soon"] == []
    assert (body["next_deadline"], body["current_goal"], body["top_fact"]) == (None, None, None)


def test_preparing_shows_the_fact_that_settles_a_match_and_what_opens_soon(
    session: Session, caller: Caller
) -> None:
    opportunities = _load(session)
    body = _today(session, caller)
    assert body["mode"] == "preparing"
    one = body["one_thing"]
    assert (one["type"], one["fact"], one["count"], one["deadline"]) == (
        "add_fact",
        "applicant_form",
        1,
        "2026-11-30",
    )
    assert _kinds(body["needs_attention"]) == [("decide", "Soon Batch"), ("check_goals", None)]
    assert body["needs_attention"][0]["opportunity_id"] == str(opportunities["Soon Batch"].id)
    assert body["opening_soon"] == [
        {
            "opportunity_id": str(opportunities["Soon Batch"].id),
            "opportunity": "Soon Batch",
            "opening": "2026-11-30",
            "readiness": None,  # its questions are unknown
        }
    ]
    assert body["top_fact"] == {"fact": "applicant_form", "matches": 1, "questions": 0}


def test_calls_past_their_review_date_produce_no_tasks(session: Session, caller: Caller) -> None:
    """Only a current source counts (PRI-12). The fixture accelerator, verified 2026-10-21,
    also needs applicant_form, but it is past its review date, so the fact settles one
    match (Soon Batch), not two."""
    _load(session)
    body = _today(session, caller)
    assert body["top_fact"] == {"fact": "applicant_form", "matches": 1, "questions": 0}
    assert "Fictional Accelerator Batch" not in {t["opportunity"] for t in body["needs_attention"]}


def test_pursuing_adds_its_unlocks_in_date_then_name_order(
    session: Session, caller: Caller
) -> None:
    opportunities = _load(session)
    matching.change_decision(
        session, caller, opportunities["Fictional Ocean Grant"].id, (Decision.PURSUING, None), CLOCK
    )
    _approve(session, caller, "country", "PT")
    body = _today(session, caller)
    assert _kinds([body["one_thing"], *body["needs_attention"]]) == [
        ("add_fact", "applicant_form"),  # 1 match, opens 2026-11-30
        ("add_fact", "team_size"),  # 1 question, deadline 2027-01-31
        ("add_fact", "trl"),  # 1 match, same date: by name
        ("decide", "Soon Batch"),
    ]


def test_an_application_in_progress_switches_to_applying(session: Session, caller: Caller) -> None:
    opportunities = _load(session)
    grant = opportunities["Fictional Ocean Grant"]
    applications.start_application(session, caller, grant.id, CLOCK)
    app_id = applications.open_applications(session, caller.company_id)[0].id
    ApplicationRepository(session, caller.company_id).save_edit(
        app_id, grant.question_ids[0], "We are four.", CLOCK.at
    )
    body = _today(session, caller)
    assert body["mode"] == "applying"
    assert (body["one_thing"]["type"], body["one_thing"]["question"]) == ("next_answer", 1)
    assert body["next_deadline"] == {
        "opportunity_id": str(grant.id),
        "opportunity": "Fictional Ocean Grant",
        "deadline": "2027-01-31",
        "days_left": 81,
        "answers_ready": {"ready": 0, "total": 2},
    }
    assert body["opening_soon"] == [] and body["top_fact"] is None  # preparing only


def test_a_submitted_application_is_not_the_next_deadline(session: Session, caller: Caller) -> None:
    opportunities = _load(session)
    grant = opportunities["Fictional Ocean Grant"]
    application = applications.start_application(session, caller, grant.id, CLOCK)
    ApplicationRepository(session, caller.company_id).mark_submitted(application.id, CLOCK.at)
    assert _today(session, caller)["next_deadline"] is None


def test_the_current_goal_is_shown(session: Session, caller: Caller) -> None:
    companies.set_intent(session, caller, [GoalChoice(Goal.INVESTMENT, Window.LATER)], CLOCK)
    body = _today(session, caller)
    assert body["current_goal"] == [{"goal": "investment", "window": "later"}]
    assert body["one_thing"] is None  # intent just set, nothing else: "You're all set"


def test_another_companys_application_does_not_change_today(
    session: Session, caller: Caller
) -> None:
    opportunities = _load(session)
    other = CompanyRow(name="B")
    session.add(other)
    session.flush()
    b = Caller(other.id, uuid.uuid4())
    grant = opportunities["Fictional Ocean Grant"]
    applications.start_application(session, b, grant.id, CLOCK)
    app_id = applications.open_applications(session, b.company_id)[0].id
    ApplicationRepository(session, b.company_id).save_edit(
        app_id, grant.question_ids[0], "B's answer.", CLOCK.at
    )
    assert _today(session, b)["mode"] == "applying"
    assert _today(session, caller)["mode"] == "preparing"
