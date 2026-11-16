"""ApplicationRepository on a real Postgres: workspaces, autosaved answers, saved versions
with their facts, safe repeats, and isolation between companies."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from home_base.core.errors import ApplicationError
from home_base.modules.applications.domain import Draft, VersionKind
from home_base.modules.applications.repository import ApplicationRepository
from home_base.modules.audit.models import AiAction
from home_base.modules.companies.domain import FactLabel
from home_base.modules.companies.models import CompanyRow
from home_base.modules.companies.repository import CompanyRepository
from home_base.modules.opportunities.repository import OpportunityRepository, StoredOpportunity
from home_base.modules.opportunities.seed import load_seed_dir
from home_base.modules.today.domain import AnswerState

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed"
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
T1, T2, T3 = (T0 + timedelta(hours=h) for h in (1, 2, 3))
FOUNDER = uuid.uuid4()


@dataclass
class World:
    a: ApplicationRepository
    b: ApplicationRepository
    facts_a: CompanyRepository
    facts_b: CompanyRepository
    opportunity: StoredOpportunity
    ai_action_id: uuid.UUID


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def world(session: Session) -> World:
    a, b = CompanyRow(name="A"), CompanyRow(name="B")
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
    session.add_all([a, b, ai])
    session.flush()
    opps = OpportunityRepository(session)
    opps.reload(load_seed_dir(FIXTURES, date(2026, 11, 11)), T0)
    with_questions = [o for o in opps.current() if o.question_ids]
    assert with_questions, "the tests need a fixture with questions"
    return World(
        ApplicationRepository(session, a.id),
        ApplicationRepository(session, b.id),
        CompanyRepository(session, a.id),
        CompanyRepository(session, b.id),
        with_questions[0],
        ai.id,
    )


def test_a_company_with_no_applications(world: World) -> None:
    assert world.a.open_applications() == []


def test_starting_twice_returns_the_same_open_application(world: World) -> None:
    first = world.a.start(world.opportunity.id, T0)
    again = world.a.start(world.opportunity.id, T1)
    assert again == first
    assert (first.started_at, first.submitted_at, first.answers) == (T0, None, ())
    assert world.a.open_applications() == [first]


def test_an_archived_application_can_be_started_again(world: World) -> None:
    first = world.a.start(world.opportunity.id, T0)
    world.a.archive(first.id, T1)
    assert world.a.open_applications() == []
    second = world.a.start(world.opportunity.id, T2)
    assert second.id != first.id
    with pytest.raises(ApplicationError, match="no open application"):
        world.a.archive(first.id, T3)


def test_submitting_twice_keeps_the_first_time(world: World) -> None:
    app = world.a.start(world.opportunity.id, T0)
    assert world.a.mark_submitted(app.id, T1).submitted_at == T1
    assert world.a.mark_submitted(app.id, T2).submitted_at == T1


def test_a_draft_edit_and_approval_flow(world: World) -> None:
    app = world.a.start(world.opportunity.id, T0)
    question = world.opportunity.question_ids[0]
    fact = world.facts_a.add_fact_version("team_size", 4, FactLabel.USER_PROVIDED, None, T0)
    draft = world.a.save_ai_draft(
        app.id, question, Draft("Four people.", world.ai_action_id, frozenset({fact.id})), T1
    )
    edit = world.a.save_edit(app.id, question, "Four people, two engineers.", T2)
    approved = world.a.approve_answer(app.id, question, FOUNDER, [fact.id], T3)

    assert (draft.kind, draft.ai_action_id, draft.fact_version_ids) == (
        VersionKind.AI_DRAFT,
        world.ai_action_id,
        frozenset({fact.id}),
    )
    assert edit.state is AnswerState.EDITED
    assert (approved.kind, approved.text, approved.approved_by) == (
        VersionKind.APPROVED,
        "Four people, two engineers.",
        FOUNDER,
    )
    assert world.a.versions(app.id, question) == [draft, approved]  # edits are not versions
    (answer,) = world.a.open_applications()[0].answers
    assert (answer.state, answer.text) == (AnswerState.APPROVED, "Four people, two engineers.")


def test_editing_an_approved_answer_reopens_it(world: World) -> None:
    app = world.a.start(world.opportunity.id, T0)
    question = world.opportunity.question_ids[0]
    world.a.save_edit(app.id, question, "Our team.", T0)
    world.a.approve_answer(app.id, question, FOUNDER, [], T1)
    assert world.a.save_edit(app.id, question, "Our team of four.", T2).state is AnswerState.EDITED


def test_an_answer_with_no_versions_and_an_unknown_answer(world: World) -> None:
    app = world.a.start(world.opportunity.id, T0)
    question = world.opportunity.question_ids[0]
    assert world.a.versions(app.id, question) == []
    world.a.save_edit(app.id, question, "Draft by hand.", T1)
    assert world.a.versions(app.id, question) == []
    with pytest.raises(ApplicationError, match="no answer to approve"):
        world.a.approve_answer(app.id, uuid.uuid4(), FOUNDER, [], T2)


def test_writing_to_an_archived_application_is_refused(world: World) -> None:
    app = world.a.start(world.opportunity.id, T0)
    world.a.archive(app.id, T1)
    question = world.opportunity.question_ids[0]
    with pytest.raises(ApplicationError, match="no open application"):
        world.a.save_edit(app.id, question, "Too late.", T2)


def test_companies_cannot_touch_each_others_applications(world: World) -> None:
    theirs = world.b.start(world.opportunity.id, T0)
    question = world.opportunity.question_ids[0]
    assert world.a.open_applications() == []
    with pytest.raises(ApplicationError, match="no open application"):
        world.a.save_edit(theirs.id, question, "Not mine.", T1)
    with pytest.raises(ApplicationError, match="no open application"):
        world.a.mark_submitted(theirs.id, T1)
    assert world.b.open_applications()[0].answers == ()
