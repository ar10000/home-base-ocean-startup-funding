"""Why it fits (handbook section 10, D-82): calculated requirement results and the fit
status in; at most two sentences out, each naming the requirements it speaks about.

Validation: every requirement named was given; every number appears in a requirement
the sentence names; at most two sentences, at least one. The words never change a
status: the screen shows the fit the rules calculated, and this only explains it.
"""

import uuid
from collections.abc import Sequence

import pydantic
from sqlalchemy.orm import Session

from home_base.ai import validators
from home_base.ai.prompts import Prompt, load
from home_base.ai.provider import Provider
from home_base.ai.runner import AiResult, AiTask, run
from home_base.core.context import Clock

PROMPT_VERSION = 1
MAX_SENTENCES = 2


def prompt() -> Prompt:
    return load("why_it_fits", PROMPT_VERSION)


class RequirementIn(pydantic.BaseModel):
    ref: str  # R1, R2…
    kind: str  # hard rule or soft criterion
    about: str  # the fact it checks, or the criterion
    quote: str  # the call's own words
    result: str  # pass, fail, unknown or ai_judgement, as the rules calculated it


class WhyInput(pydantic.BaseModel):
    opportunity: str
    fit: str  # confirmed, possible or not_eligible, as the rules calculated it
    requirements: list[RequirementIn]


class Sentence(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    text: str
    requirements: list[str]


class WhyOutput(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    sentences: list[Sentence]

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.sentences if s.text.strip())


class Validate:
    def __init__(self, given: WhyInput) -> None:
        self.quotes = {r.ref: r.quote for r in given.requirements}

    def __call__(self, out: WhyOutput) -> list[str]:
        said = [s for s in out.sentences if s.text.strip()]
        if not said:
            return ["write at least one sentence"]
        problems = (
            [] if len(said) <= MAX_SENTENCES else [f"write at most {MAX_SENTENCES} sentences"]
        )
        problems += validators.only_known(
            (r for s in said for r in s.requirements), self.quotes.keys(), "requirement"
        )
        for s in said:
            if not s.requirements:
                problems.append(f"name the requirements this sentence explains: {s.text!r}")
            sources: Sequence[str] = [self.quotes[r] for r in s.requirements if r in self.quotes]
            problems += validators.numbers_cited(s.text, sources)
        return problems


def explain(
    session: Session,
    provider: Provider,
    given: WhyInput,
    about: tuple[uuid.UUID, uuid.UUID],
    clock: Clock,
) -> AiResult[WhyOutput]:
    """Word the explanation for one company and opportunity (cached by input)."""
    company_id, opportunity_id = about
    return run(
        session,
        provider,
        AiTask(
            prompt=prompt(),
            payload=given,
            output=WhyOutput,
            validate=Validate(given),
            refs=[{"entity": "opportunity", "id": str(opportunity_id)}],
            company_id=company_id,
            served=("opportunity", opportunity_id),
        ),
        clock,
    )
