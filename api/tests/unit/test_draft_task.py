"""The draft-answer task's input, checks and prompt (D-81, DRF-01, DRF-02)."""

import json

import pytest

from home_base.ai.fake import FakeProvider, local_reply
from home_base.ai.mistral import MistralProvider
from home_base.ai.provider import Message
from home_base.ai.retrieval import fact_text, value_text
from home_base.ai.settings import provider_from_environment
from home_base.ai.tasks.draft_answer import DraftInput, DraftOutput, FactIn, Sentence, prompt
from home_base.core.errors import AiConfigError

GIVEN = DraftInput(
    question="Describe your team.",
    limit=120,
    facts=[
        FactIn(ref="F1", fact="team size", value="4"),
        FactIn(ref="F2", fact="impact", value="Absorbs 2 t of nitrogen a year."),
    ],
)


def _check(*sentences: tuple[str, list[str]]) -> list[str]:
    out = DraftOutput(sentences=[Sentence(text=t, facts=f) for t, f in sentences])
    from home_base.ai.tasks.draft_answer import validator

    return validator(GIVEN)(out)


def test_a_grounded_draft_is_valid() -> None:
    assert _check(("We are a team of 4.", ["F1"]), ("We absorb 2 t of nitrogen.", ["F2"])) == []


def test_a_linking_sentence_may_cite_nothing_if_it_states_no_number() -> None:
    assert _check(("We are 4.", ["F1"]), ("That matters here.", [])) == []


def test_a_number_must_be_in_a_fact_that_sentence_cites() -> None:
    # 2 is in F2, but this sentence cites only F1
    assert _check(("We absorb 2 t.", ["F1"])) == [
        "the number 2 is in no cited fact; use only numbers from the facts"
    ]


def test_citing_a_fact_not_given_is_refused() -> None:
    assert _check(("We are 4.", ["F1", "F7"])) == [
        "fact F7 was not given; cite only the facts listed"
    ]


def test_an_empty_draft_is_refused() -> None:
    assert _check() == ["write at least one sentence"]
    assert _check(("  ", [])) == ["write at least one sentence"]


def test_the_limit_counts_the_joined_text() -> None:
    long = ("We are 4. " * 13, ["F1"])
    assert any("the limit is 120" in p for p in _check(long))


def test_the_text_joins_the_sentences() -> None:
    out = DraftOutput(sentences=[Sentence(text=" A. ", facts=[]), Sentence(text="B.", facts=[])])
    assert out.text == "A. B."


def test_the_prompt_file_loads_and_takes_the_input() -> None:
    p = prompt()
    assert (p.task, p.version, p.label) == ("draft_answer", 2, "draft_answer/v2")
    assert p.temperature <= 0.3  # handbook section 10: low for drafting
    assert GIVEN.model_dump_json() in p.user_message(GIVEN.model_dump_json())


def test_the_local_reply_cites_each_fact_and_passes_the_checks() -> None:
    p = prompt()
    reply = local_reply([Message("user", p.user_message(GIVEN.model_dump_json()))])
    out = DraftOutput.model_validate_json(reply)
    assert [s.facts for s in out.sentences] == [["F1"], ["F2"]]
    from home_base.ai.tasks.draft_answer import validator

    assert validator(GIVEN.model_copy(update={"limit": None}))(out) == []
    assert json.loads(local_reply([Message("user", "no input")])) == {"sentences": []}


def test_facts_read_in_words() -> None:
    assert value_text("country", "PT") == "Portugal"
    assert value_text("woman_ceo", True) == "yes"
    assert value_text("team_size", 4) == "4"
    assert value_text("impact", "As written.") == "As written."


def test_the_provider_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOME_BASE_AI_PROVIDER", raising=False)
    assert isinstance(provider_from_environment(), FakeProvider)
    monkeypatch.setenv("HOME_BASE_AI_PROVIDER", "mistral")
    monkeypatch.setenv("HOME_BASE_MISTRAL_API_KEY", "k")
    assert isinstance(provider_from_environment(), MistralProvider)
    monkeypatch.setenv("HOME_BASE_AI_PROVIDER", "openai")
    with pytest.raises(AiConfigError):
        provider_from_environment()


def test_fact_text_names_the_fact() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from home_base.modules.companies.domain import FactLabel, FactVersion

    fact = FactVersion(
        uuid4(), "team_size", 4, FactLabel.USER_PROVIDED, None, datetime.now(UTC), None, None, None
    )
    assert fact_text(fact) == "team size: 4"
