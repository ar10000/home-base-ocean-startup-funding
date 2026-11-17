"""Every model call goes through `run` (handbook section 10, section 12).

1. The input is hashed with the prompt version and model; a succeeded call with the same
   hash is reused, so the same input costs nothing and gives the same result.
2. Today's spend is checked against config.AI_DAILY_BUDGET_EUR.
3. The reply is parsed into the task's schema and validated. If either fails, the model
   gets one retry with the reasons. A second failure is logged and raised: nothing else
   is saved.
4. One `ai_actions` row records task, prompt version, model, input hash, references to
   the input records (never their text), the validated output, tokens, cost, latency.

Nothing here logs a prompt, an input or an output.
"""

import hashlib
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import time as day_time
from decimal import Decimal
from typing import Any

import pydantic
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from home_base.ai.prompts import Prompt
from home_base.ai.provider import Completion, Message, Provider
from home_base.config import AI_DAILY_BUDGET_EUR, AI_PRICE_PER_MILLION_TOKENS
from home_base.core.context import Clock
from home_base.core.errors import AiBudgetError, AiError
from home_base.modules.audit.models import AiAction

MILLION = Decimal(1_000_000)
_DEAREST = max(AI_PRICE_PER_MILLION_TOKENS.values())


@dataclass(frozen=True, slots=True)
class AiResult[T]:
    value: T
    action_id: uuid.UUID
    cached: bool


def cost_eur(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """List price of one call; a model not in the table counts as the dearest."""
    name = model.removeprefix("fake:")
    price_in, price_out = AI_PRICE_PER_MILLION_TOKENS.get(name, _DEAREST)
    return (price_in * input_tokens + price_out * output_tokens) / MILLION


def input_hash(prompt: Prompt, payload: pydantic.BaseModel, provider: str) -> str:
    """The same task, input and provider: the same answer (D-84: providers never share)."""
    text = f"{prompt.label}\n{prompt.model}\n{provider}\n{payload.model_dump_json()}"
    return hashlib.sha256(text.encode()).hexdigest()


def spent_today(session: Session, clock: Clock) -> Decimal:
    start = datetime.combine(clock.at.astimezone(UTC).date(), day_time.min, tzinfo=UTC)
    total = session.scalar(
        select(func.coalesce(func.sum(AiAction.cost_eur), 0)).where(AiAction.created_at >= start)
    )
    return Decimal(total or 0)


def _attempt[T: pydantic.BaseModel](
    completion: Completion, output: type[T], validate: Callable[[T], list[str]]
) -> tuple[T | None, list[str]]:
    try:
        value = output.model_validate_json(completion.text)
    except pydantic.ValidationError as exc:
        problems = [f"{'.'.join(map(str, e['loc'])) or 'reply'}: {e['msg']}" for e in exc.errors()]
        return None, problems
    problems = validate(value)
    return (None if problems else value), problems


@dataclass(frozen=True, slots=True)
class AiTask[T: pydantic.BaseModel]:
    """One call to make: the prompt, its input, the schema and checks for its output, and
    what it is about (references, never text)."""

    prompt: Prompt
    payload: pydantic.BaseModel
    output: type[T]
    validate: Callable[[T], list[str]]
    refs: Sequence[Mapping[str, Any]]
    company_id: uuid.UUID | None
    served: tuple[str, uuid.UUID] | None = None
    cached: bool = True  # evaluations turn it off, to measure fresh answers


def run[T: pydantic.BaseModel](
    session: Session, provider: Provider, task: AiTask[T], clock: Clock
) -> AiResult[T]:
    prompt, payload, output, validate = task.prompt, task.payload, task.output, task.validate
    refs, company_id, served = task.refs, task.company_id, task.served
    digest = input_hash(prompt, payload, provider.name)
    hit = session.scalars(
        select(AiAction)
        .where(
            AiAction.input_hash == digest,
            AiAction.status == "succeeded",
            AiAction.company_id.is_(None)
            if company_id is None
            else AiAction.company_id == company_id,
        )
        .order_by(AiAction.created_at.desc())
        .limit(1)
    ).first()
    if task.cached and hit is not None and hit.output is not None:
        return AiResult(output.model_validate(hit.output), hit.id, cached=True)

    if spent_today(session, clock) >= AI_DAILY_BUDGET_EUR:
        raise AiBudgetError("today's AI budget is used up; try again tomorrow")

    schema = output.model_json_schema()
    messages = [
        Message("system", prompt.system),
        Message("user", prompt.user_message(payload.model_dump_json())),
    ]
    started = time.monotonic()
    tokens_in = tokens_out = 0
    model = prompt.model
    value: T | None = None
    problems: list[str] = []
    retries = 0
    for attempt in range(2):
        retries = attempt
        completion = provider.complete(
            model=prompt.model,
            messages=messages,
            schema=schema,
            temperature=prompt.temperature,
            max_tokens=prompt.max_tokens,
        )
        model = completion.model
        tokens_in += completion.input_tokens
        tokens_out += completion.output_tokens
        value, problems = _attempt(completion, output, validate)
        if value is not None:
            break
        messages = [
            *messages,
            Message("assistant", completion.text),
            Message(
                "user",
                "That reply is not valid:\n- "
                + "\n- ".join(problems)
                + "\nReply again with JSON that fixes every point.",
            ),
        ]

    action = AiAction(
        task=prompt.task,
        prompt_version=prompt.label,
        model=model,
        input_hash=digest,
        input_refs=[dict(r) for r in refs],
        output=value.model_dump(mode="json") if value is not None else None,
        validation_result="valid" if value is not None else "invalid",
        retry_count=retries,
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        cost_eur=cost_eur(model, tokens_in, tokens_out),
        latency_ms=int((time.monotonic() - started) * 1000),
        status="succeeded" if value is not None else "failed",
        served_entity=served[0] if served else None,
        served_entity_id=served[1] if served else None,
        company_id=company_id,
        request_id=clock.request_id,
    )
    session.add(action)
    session.flush()
    if value is None:
        raise AiFailed(action.id, problems)
    return AiResult(value, action.id, cached=False)


class AiFailed(AiError):
    """Both attempts were invalid. The failed action is in the log (`action_id`)."""

    def __init__(self, action_id: uuid.UUID, problems: list[str]) -> None:
        super().__init__(f"the AI could not give a valid answer ({len(problems)} problems)")
        self.action_id = action_id
        self.problems = problems
