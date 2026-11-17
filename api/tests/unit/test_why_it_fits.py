"""Why it fits: input, checks and the local reply (D-82, handbook section 10)."""

import json

from home_base.ai.fake import local_reply
from home_base.ai.provider import Message
from home_base.ai.tasks.why_it_fits import (
    RequirementIn,
    Sentence,
    Validate,
    WhyInput,
    WhyOutput,
    prompt,
)

GIVEN = WhyInput(
    opportunity="Tidal Pilot Fund",
    fit="possible",
    requirements=[
        RequirementIn(
            ref="R1",
            kind="hard rule",
            about="country",
            quote="Open to companies registered in Portugal, Spain or France.",
            result="pass",
        ),
        RequirementIn(
            ref="R2",
            kind="hard rule",
            about="team size",
            quote="Applicants must have fewer than 51 employees.",
            result="unknown",
        ),
    ],
)


def _check(*sentences: tuple[str, list[str]]) -> list[str]:
    out = WhyOutput(sentences=[Sentence(text=t, requirements=r) for t, r in sentences])
    return Validate(GIVEN)(out)


def test_two_grounded_sentences_are_valid() -> None:
    assert (
        _check(
            ("You are based in an eligible country.", ["R1"]),
            ("Add your team size: the call is for fewer than 51 employees.", ["R2"]),
        )
        == []
    )


def test_more_than_two_sentences_are_refused() -> None:
    three = [("A.", ["R1"]), ("B.", ["R1"]), ("C.", ["R2"])]
    assert "write at most 2 sentences" in _check(*three)


def test_every_sentence_names_given_requirements() -> None:
    assert _check(("You fit.", [])) == ["name the requirements this sentence explains: 'You fit.'"]
    assert _check(("You fit.", ["R7"])) == ["requirement R7 was not in the input"]


def test_a_number_must_come_from_a_named_requirement() -> None:
    assert _check(("The call is for fewer than 50 employees.", ["R2"])) == [
        "the number 50 is in no cited fact; use only numbers from the facts"
    ]


def test_an_empty_explanation_is_refused() -> None:
    assert _check() == ["write at least one sentence"]


def test_the_prompt_loads_at_temperature_zero() -> None:
    p = prompt()
    assert (p.label, p.temperature) == ("why_it_fits/v1", 0.0)


def test_the_local_reply_names_the_deciding_requirement_and_is_valid() -> None:
    reply = local_reply([Message("user", prompt().user_message(GIVEN.model_dump_json()))])
    out = WhyOutput.model_validate_json(reply)
    assert out.text == "May fit: Applicants must have fewer than 51 employees."
    assert Validate(GIVEN)(out) == []
    not_eligible = GIVEN.model_copy(update={"fit": "not_eligible"})
    reply = local_reply([Message("user", json.dumps(not_eligible.model_dump()))])
    # nothing failed, so it falls back to the first requirement
    assert json.loads(reply)["sentences"][0]["requirements"] == ["R1"]
