"""Requirement extraction (handbook section 10, D-83): the passages of a call about
eligibility in; structured requirements out, each with the call's exact words.

Retrieval first: the call is split into passages and only those closest to the
eligibility questions are sent (ADR-009). Validation: every quote is an exact substring
of the full call text, and every requirement passes the seed loader's own checks (facts,
operators and listed values from closed lists, REQ-09). The output is a draft for a
person to check (FRS-01): it never goes live by itself.
"""

from collections.abc import Sequence
from datetime import date
from typing import Any, Literal

import pydantic
from sqlalchemy.orm import Session

from home_base.ai import passages as calls
from home_base.ai import validators
from home_base.ai.prompts import Prompt, load
from home_base.ai.provider import Provider
from home_base.ai.runner import AiResult, AiTask, run
from home_base.config import FACT_VALUES, FOUNDER_FACT_KEYS, HARD_RULE_FACT_KEYS
from home_base.core.context import Clock
from home_base.core.errors import SeedError
from home_base.core.vocabulary import Operator
from home_base.modules.opportunities.seed import parse_seed

PROMPT_VERSION = 2
NUMBER_FACTS = frozenset({"company_age", "team_size", "trl"})
YES_NO_FACTS = frozenset({"woman_founder", "woman_ceo"})

# What retrieval looks for in a call: who may apply, and on what conditions.
QUESTIONS = (
    "Who is eligible to apply? Which countries, which types of company or organisation?",
    "How old or how large may the company be? Number of employees, years since founding.",
    "What technology readiness level (TRL) or stage of development is required?",
    "Which sectors or activities are covered?",
    "May companies apply alone, or must they form a consortium with partners?",
    "Are there conditions about the founders, such as age or gender?",
    "How are proposals evaluated? Award criteria, impact, innovation, team.",
)


def prompt() -> Prompt:
    return load("extract_requirements", PROMPT_VERSION)


def fact_guide() -> dict[str, str]:
    """For the model: each fact it may use and the values it takes."""
    guide = {k: "one of: " + ", ".join(v for v, _ in vals) for k, vals in FACT_VALUES.items()}
    guide |= {
        "company_age": "whole years since founding",
        "team_size": "number of people",
        "trl": "1 to 9",
        "founder_age": "the youngest founder's age in years",
        "woman_founder": "true or false",
        "woman_ceo": "true or false",
    }
    allowed = HARD_RULE_FACT_KEYS | FOUNDER_FACT_KEYS
    return {k: v for k, v in sorted(guide.items()) if k in allowed}


class PassageIn(pydantic.BaseModel):
    ref: str
    text: str


class ExtractInput(pydantic.BaseModel):
    call: str
    passages: list[PassageIn]
    facts: dict[str, str]
    operators: list[str]


class RequirementOut(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    type: Literal["hard", "soft"]
    fact: str | None  # hard rules only
    operator: str | None  # hard rules only
    values: list[str]  # hard rules only; one value except for one_of and not_one_of
    criterion: str | None  # soft criteria only
    quote: str


class ExtractOutput(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    requirements: list[RequirementOut]


def _value(fact: str, operator: str, values: Sequence[str]) -> object:
    def one(v: str) -> object:
        if fact in NUMBER_FACTS or fact == "founder_age":
            return int(v)
        if fact in YES_NO_FACTS:
            return {"true": True, "false": False}[v.strip().lower()]
        return v

    if operator in {Operator.ONE_OF, Operator.NOT_ONE_OF}:
        return [one(v) for v in values]
    if len(values) != 1:
        raise ValueError(f"{operator} takes exactly one value")
    return one(values[0])


def seed_requirement(r: RequirementOut) -> dict[str, Any]:
    """One requirement as a seed file writes it."""
    if r.type == "soft":
        return {"type": "soft", "criterion": r.criterion, "quote": r.quote}
    return {
        "type": "hard",
        "fact": r.fact,
        "operator": r.operator,
        "value": _value(r.fact or "", r.operator or "", r.values),
        "quote": r.quote,
    }


class Validate:
    def __init__(self, call_text: str) -> None:
        self.call_text = call_text

    def __call__(self, out: ExtractOutput) -> list[str]:
        problems = validators.quotes_verbatim((r.quote for r in out.requirements), self.call_text)
        for i, r in enumerate(out.requirements):
            try:
                record = seed_requirement(r)
            except (ValueError, KeyError) as exc:
                problems.append(f"requirement {i + 1}: {exc}")
                continue
            check = {
                "name": "check",
                "funder": "check",
                "scope": "all_sectors",
                "types": ["grant"],
                "source_url": "https://example.org/check",
                "retrieved_on": date(2026, 1, 1),
                "verified_on": date(2026, 1, 1),
                "verified_by": "check",
                "requirements": [record],
            }
            try:
                parse_seed(check, "extraction", date(2026, 1, 2))
            except SeedError as exc:
                problems.append(f"requirement {i + 1}: {exc}")
        return problems


def extract(  # noqa: PLR0913  (cached is only for evaluations)
    session: Session,
    provider: Provider,
    call_name: str,
    call_text: str,
    clock: Clock,
    cached: bool = True,
) -> AiResult[ExtractOutput]:
    """Requirements from a call's text, through its eligibility passages."""
    chosen = calls.relevant(provider, calls.split(call_text), QUESTIONS)
    given = ExtractInput(
        call=call_name,
        passages=[PassageIn(ref=f"P{p.position + 1}", text=p.text) for p in chosen],
        facts=fact_guide(),
        operators=[o.value for o in Operator],
    )
    return run(
        session,
        provider,
        AiTask(
            prompt=prompt(),
            payload=given,
            output=ExtractOutput,
            validate=Validate(call_text),
            refs=[{"entity": "call_text", "id": f"{call_name}"}],
            company_id=None,
            cached=cached,
        ),
        clock,
    )
