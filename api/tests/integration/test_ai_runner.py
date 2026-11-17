"""The AI runner against a real database: cache, retry, failure, budget, log (section 10)."""

import json
import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pydantic
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from home_base.ai import prompts
from home_base.ai.fake import FakeProvider
from home_base.ai.provider import Message
from home_base.ai.runner import AiFailed, AiTask, run
from home_base.core.context import Clock
from home_base.core.errors import AiBudgetError
from home_base.modules.audit.models import AiAction
from home_base.modules.companies.models import CompanyRow

pytestmark = pytest.mark.integration

CLOCK = Clock(at=datetime(2026, 11, 17, 10, tzinfo=UTC), today=date(2026, 11, 17), request_id="r1")
PROMPT = prompts.parse(
    "---\ntask: echo\nversion: 1\nmodel: mistral-small-latest\ntemperature: 0\n"
    "max_tokens: 50\n---\n## System\nEcho.\n\n## User\n{input}\n",
    "echo/v1",
)


class Payload(pydantic.BaseModel):
    word: str


class Out(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    word: str


def _no_x(out: Out) -> list[str]:
    return ["the word may not contain x"] if "x" in out.word else []


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def company(session: Session) -> uuid.UUID:
    row = CompanyRow(name="A")
    session.add(row)
    session.flush()
    return row.id


def _task(company: uuid.UUID | None, word: str = "sea") -> AiTask[Out]:
    return AiTask(
        prompt=PROMPT,
        payload=Payload(word=word),
        output=Out,
        validate=_no_x,
        refs=[{"entity": "question", "id": "q1"}],
        company_id=company,
    )


def _actions(session: Session) -> list[AiAction]:
    return list(session.scalars(select(AiAction).order_by(AiAction.created_at)))


def test_a_valid_reply_is_returned_and_logged_without_its_input_text(
    session: Session, company: uuid.UUID
) -> None:
    fake = FakeProvider('{"word": "sea"}')
    result = run(session, fake, _task(company, "secret-input"), CLOCK)
    assert result.value == Out(word="sea")
    assert not result.cached
    (action,) = _actions(session)
    assert action.id == result.action_id
    assert (action.task, action.prompt_version, action.status, action.retry_count) == (
        "echo",
        "echo/v1",
        "succeeded",
        0,
    )
    assert action.output == {"word": "sea"}
    assert action.input_refs == [{"entity": "question", "id": "q1"}]
    assert "secret-input" not in json.dumps([action.input_refs, action.output, action.input_hash])
    assert action.company_id == company
    assert action.request_id == "r1"


def test_the_same_input_is_served_from_the_log_without_calling_the_model(
    session: Session, company: uuid.UUID
) -> None:
    fake = FakeProvider('{"word": "sea"}')
    first = run(session, fake, _task(company), CLOCK)
    again = run(session, fake, _task(company), CLOCK)
    assert again.cached and again.action_id == first.action_id
    assert len(fake.calls) == 1
    run(session, fake, _task(company, "other"), CLOCK)
    assert len(fake.calls) == 2


def test_another_company_never_gets_a_cached_answer(session: Session, company: uuid.UUID) -> None:
    other = CompanyRow(name="B")
    session.add(other)
    session.flush()
    fake = FakeProvider('{"word": "sea"}')
    run(session, fake, _task(company), CLOCK)
    assert not run(session, fake, _task(other.id), CLOCK).cached


def test_an_invalid_reply_gets_one_retry_with_the_reasons(
    session: Session, company: uuid.UUID
) -> None:
    replies = iter(['{"word": "xyz"}', '{"word": "sea"}'])

    def reply(messages: Sequence[Message]) -> str:
        return next(replies)

    fake = FakeProvider(reply)
    result = run(session, fake, _task(company), CLOCK)
    assert result.value.word == "sea"
    assert "the word may not contain x" in fake.calls[1][-1].content
    (action,) = _actions(session)
    assert action.retry_count == 1


@pytest.mark.parametrize("bad", ['{"word": "x"}', "not json", '{"word": 1, "extra": 2}'])
def test_two_invalid_replies_fail_visibly_and_are_logged(
    session: Session, company: uuid.UUID, bad: str
) -> None:
    fake = FakeProvider(bad)
    with pytest.raises(AiFailed) as failure:
        run(session, fake, _task(company), CLOCK)
    assert len(fake.calls) == 2
    (action,) = _actions(session)
    assert action.id == failure.value.action_id
    assert (action.status, action.validation_result, action.output) == ("failed", "invalid", None)
    # a failure is never served from the cache
    with pytest.raises(AiFailed):
        run(session, fake, _task(company), CLOCK)


def test_nothing_is_called_once_today_s_budget_is_used(
    session: Session, company: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("home_base.ai.runner.AI_DAILY_BUDGET_EUR", Decimal("0.000001"))
    fake = FakeProvider('{"word": "sea"}')
    run(session, fake, _task(company, "a" * 4000), CLOCK)  # spends above the tiny budget
    with pytest.raises(AiBudgetError):
        run(session, fake, _task(company, "b"), CLOCK)
    assert len(fake.calls) == 1
    # a cached answer costs nothing, so it is still served
    assert run(session, fake, _task(company, "a" * 4000), CLOCK).cached
