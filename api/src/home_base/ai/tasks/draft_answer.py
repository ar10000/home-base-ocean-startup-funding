"""Draft answer (handbook section 10, D-81): one question, its limit, approved facts in;
sentences out, each with the facts it used.

Facts go to the model under short references (F1, F2…), never IDs or anything else
about the company. Validation: every cited reference was given (DRF-01), every number
in a sentence appears in a fact that sentence cites, the whole answer is within the
limit, and there is at least one sentence.
"""

from collections.abc import Sequence

import pydantic

from home_base.ai import validators
from home_base.ai.prompts import Prompt, load
from home_base.modules.applications.rules import unusable_citations

PROMPT_VERSION = 2


def prompt() -> Prompt:
    return load("draft_answer", PROMPT_VERSION)


class FactIn(pydantic.BaseModel):
    ref: str  # F1, F2…
    fact: str  # what the fact is, in words: "team size", "impact"
    value: str


class DraftInput(pydantic.BaseModel):
    question: str
    limit: int | None  # characters; None when the call gives no limit
    facts: list[FactIn]


class Sentence(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    text: str
    facts: list[str]  # the references this sentence used


class DraftOutput(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    sentences: list[Sentence]

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.sentences if s.text.strip())


def validator(given: DraftInput) -> "Validate":
    return Validate(given)


class Validate:
    """The checks for one input; callable on the model's output."""

    def __init__(self, given: DraftInput) -> None:
        self.values = {f.ref: f.value for f in given.facts}
        self.limit = given.limit

    def __call__(self, out: DraftOutput) -> list[str]:
        if not any(s.text.strip() for s in out.sentences):
            return ["write at least one sentence"]
        cited = [ref for s in out.sentences for ref in s.facts]
        problems = [
            f"fact {ref} was not given; cite only the facts listed"
            for ref in unusable_citations(cited, self.values.keys())
        ]
        for s in out.sentences:
            sources: Sequence[str] = [self.values[r] for r in s.facts if r in self.values]
            problems += validators.numbers_cited(s.text, sources)
        problems += validators.within_limit(out.text, self.limit)
        return problems
