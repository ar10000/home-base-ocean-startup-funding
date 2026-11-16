"""Application tables on a real Postgres: one open application per company and call,
answer versions tied to their AI call or approver, the fact versions each was built
from, and nothing linking across companies."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from home_base.core.db import Record
from home_base.modules.applications.models import (
    AnswerRow,
    AnswerVersionFactRow,
    AnswerVersionRow,
    ApplicationRow,
)
from home_base.modules.audit.models import AiAction
from home_base.modules.companies.models import CompanyFactRow, CompanyRow
from home_base.modules.opportunities.models import OpportunityRow, QuestionRow

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
FOUNDER = uuid.uuid4()


@dataclass
class World:
    company: CompanyRow
    other_company: CompanyRow
    opportunity: OpportunityRow
    question: QuestionRow
    fact: CompanyFactRow
    other_fact: CompanyFactRow
    ai_action: AiAction


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def world(session: Session) -> World:
    company, other = CompanyRow(name="A"), CompanyRow(name="B")
    opp = OpportunityRow(
        seed_key=f"test-{uuid.uuid4()}",
        name="Example Ocean Grant",
        funder="Example Foundation",
        scope="blue_specific",
        types=["grant"],
        questions_known=True,
    )
    ai = AiAction(
        task="draft_answer",
        prompt_version="v1",
        model="test-model",
        input_hash="sha256:0",
        input_refs=[],
        validation_result="valid",
        retry_count=0,
        input_tokens=0,
        output_tokens=0,
        cost_eur=Decimal(0),
        latency_ms=0,
        status="succeeded",
    )
    session.add_all([company, other, opp, ai])
    session.flush()
    question = QuestionRow(
        opportunity_id=opp.id, position=0, text="Describe your team.", required_facts=["team_size"]
    )
    fact, other_fact = (
        CompanyFactRow(
            company_id=c.id,
            key="team_size",
            value_type="integer",
            value_integer=4,
            label="user_provided",
            approved_at=NOW,
            approved_by=FOUNDER,
        )
        for c in (company, other)
    )
    session.add_all([question, fact, other_fact])
    session.flush()
    return World(company, other, opp, question, fact, other_fact, ai)


def _saves(session: Session, row: Record) -> bool:
    savepoint = session.begin_nested()
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        savepoint.rollback()
        return False
    savepoint.rollback()
    return True


def _application(w: World, **overrides: Any) -> ApplicationRow:
    values: dict[str, Any] = {
        "company_id": w.company.id,
        "opportunity_id": w.opportunity.id,
        "started_at": NOW,
    } | overrides
    return ApplicationRow(**values)


def _saved(session: Session, row: Record) -> Any:
    session.add(row)
    session.flush()
    return row


def _answer(w: World, application: ApplicationRow, **overrides: Any) -> AnswerRow:
    values: dict[str, Any] = {
        "application_id": application.id,
        "company_id": w.company.id,
        "question_id": w.question.id,
        "state": "ai_draft",
        "current_text": "We are a team of four.",
    } | overrides
    return AnswerRow(**values)


def _version(w: World, answer: AnswerRow, **overrides: Any) -> AnswerVersionRow:
    values: dict[str, Any] = {
        "answer_id": answer.id,
        "company_id": w.company.id,
        "kind": "ai_draft",
        "text": "We are a team of four.",
        "ai_action_id": w.ai_action.id,
    } | overrides
    return AnswerVersionRow(**values)


def _answer_in_new_application(session: Session, w: World) -> AnswerRow:
    application = _saved(session, _application(w))
    answer: AnswerRow = _saved(session, _answer(w, application))
    return answer


@pytest.mark.parametrize(
    "model", [ApplicationRow, AnswerRow, AnswerVersionRow, AnswerVersionFactRow]
)
def test_tables_are_empty_after_the_migration(session: Session, model: type[Record]) -> None:
    assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize(
    ("submitted_at", "saved"),
    [(None, True), (NOW, True), (NOW + timedelta(days=1), True), (NOW - timedelta(days=1), False)],
)
def test_submitted_is_never_before_started(
    session: Session, world: World, submitted_at: datetime | None, saved: bool
) -> None:
    assert _saves(session, _application(world, submitted_at=submitted_at)) is saved


def test_one_open_application_per_company_and_call(session: Session, world: World) -> None:
    first = _saved(session, _application(world))
    assert _saves(session, _application(world)) is False
    first.archived_at = NOW
    session.flush()
    assert _saves(session, _application(world)) is True


@pytest.mark.parametrize(
    ("state", "saved"),
    [("ai_draft", True), ("edited", True), ("approved", True), ("missing_facts", False)],
)
def test_answer_state(session: Session, world: World, state: str, saved: bool) -> None:
    application = _saved(session, _application(world))
    assert _saves(session, _answer(world, application, state=state)) is saved


def test_one_answer_per_question(session: Session, world: World) -> None:
    application = _saved(session, _application(world))
    _saved(session, _answer(world, application))
    assert _saves(session, _answer(world, application, state="edited")) is False


def test_an_answer_cannot_belong_to_another_companys_application(
    session: Session, world: World
) -> None:
    application = _saved(session, _application(world))
    cross = _answer(world, application, company_id=world.other_company.id)
    assert _saves(session, cross) is False


@pytest.mark.parametrize(
    ("overrides", "saved"),
    [
        ({}, True),
        ({"ai_action_id": None}, False),  # an AI draft names its AI call
        ({"kind": "approved", "ai_action_id": None, "approved_by": FOUNDER}, True),
        ({"kind": "approved", "ai_action_id": None}, False),  # an approval names its approver
        ({"approved_by": FOUNDER}, False),  # an AI draft is not an approval
        ({"kind": "edited"}, False),  # edits are autosaved on the answer, not versions
    ],
)
def test_answer_version_checks(
    session: Session, world: World, overrides: dict[str, Any], saved: bool
) -> None:
    answer = _answer_in_new_application(session, world)
    assert _saves(session, _version(world, answer, **overrides)) is saved


def test_a_version_keeps_the_fact_versions_it_was_built_from(
    session: Session, world: World
) -> None:
    answer = _answer_in_new_application(session, world)
    version = _saved(session, _version(world, answer))
    session.add(
        AnswerVersionFactRow(
            answer_version_id=version.id, company_id=world.company.id, fact_version_id=world.fact.id
        )
    )
    world.fact.superseded_at = NOW  # the fact changes later
    session.flush()
    link = session.scalars(select(AnswerVersionFactRow)).one()
    assert session.get(CompanyFactRow, link.fact_version_id) is world.fact


def test_a_version_cannot_use_another_companys_fact(session: Session, world: World) -> None:
    answer = _answer_in_new_application(session, world)
    version = _saved(session, _version(world, answer))
    cross = AnswerVersionFactRow(
        answer_version_id=version.id,
        company_id=world.company.id,
        fact_version_id=world.other_fact.id,
    )
    assert _saves(session, cross) is False


def test_each_fact_is_linked_once_per_version(session: Session, world: World) -> None:
    answer = _answer_in_new_application(session, world)
    version = _saved(session, _version(world, answer))
    link = {
        "answer_version_id": version.id,
        "company_id": world.company.id,
        "fact_version_id": world.fact.id,
    }
    _saved(session, AnswerVersionFactRow(**link))
    assert _saves(session, AnswerVersionFactRow(**link)) is False
