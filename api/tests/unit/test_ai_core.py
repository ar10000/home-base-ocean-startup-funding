"""The AI layer's parts that need no database (handbook section 10, ADR-009)."""

import json
from decimal import Decimal

import httpx
import pytest

from home_base.ai import prompts, validators
from home_base.ai.fake import FakeProvider, hashed_embedding
from home_base.ai.mistral import EU_BASE_URL, MistralProvider
from home_base.ai.provider import Message
from home_base.ai.runner import cost_eur
from home_base.config import EMBEDDING_DIMENSIONS
from home_base.core.errors import AiConfigError, AiError

# --- validators ---------------------------------------------------------------------


def test_a_quote_must_be_word_for_word_in_the_call() -> None:
    call = "Applicants must be based in Portugal. Technology at TRL 4 or above."
    assert validators.quotes_verbatim(["Applicants must be based in Portugal."], call) == []
    assert validators.quotes_verbatim(["Applicants must be based in portugal."], call)
    assert validators.quotes_verbatim(["based in Portugal and Spain"], call)
    assert validators.quotes_verbatim([], call) == []


def test_a_line_break_in_the_call_is_read_as_a_space_but_every_word_must_match() -> None:
    """D-85: calls wrap lines inside sentences; the words still have to be exact."""
    call = "and the quality and efficiency of\n  implementation (20%)."
    assert validators.quotes_verbatim(["quality and efficiency of implementation"], call) == []
    assert validators.quotes_verbatim(["quality and  efficiency\tof implementation"], call) == []
    assert validators.quotes_verbatim(["quality and efficiency of execution"], call)
    assert validators.quotes_verbatim(["qualityand efficiency"], call)  # words, not letters
    assert validators.quotes_verbatim(["   "], call)  # an empty quote quotes nothing


@pytest.mark.parametrize(
    ("text", "facts", "bad"),
    [
        ("We absorb 2 t of nitrogen a year.", ["Absorbs 2 t of nitrogen a year."], []),
        ("We absorb 3 t of nitrogen.", ["Absorbs 2 t of nitrogen a year."], ["3"]),
        ("A 40% cut.", ["Cut losses by 40%."], []),
        ("Revenue of 1,200 euros.", ["Revenue: 1,200 euros."], []),
        ("Revenue of 1200 euros.", ["Revenue: 1,200 euros."], ["1200"]),
        ("2.5 hectares.", ["2,5 hectares."], ["2.5"]),
        ("No figures here.", [], []),
        ("Founded in 2024.", [], ["2024"]),
    ],
)
def test_every_number_must_appear_in_a_cited_fact(
    text: str, facts: list[str], bad: list[str]
) -> None:
    problems = validators.numbers_cited(text, facts)
    assert [p.split()[2] for p in problems] == bad


def test_the_limit_is_in_characters_and_none_means_no_limit() -> None:
    assert validators.within_limit("abc", 3) == []
    assert validators.within_limit("abcd", 3) == ["the answer is 4 characters; the limit is 3"]
    assert validators.within_limit("x" * 10_000, None) == []


def test_only_ids_from_the_input_may_be_named() -> None:
    assert validators.only_known(["a", "b"], {"a", "b", "c"}, "fact") == []
    assert validators.only_known(["a", "z", "z"], {"a"}, "fact") == ["fact z was not in the input"]


# --- prompts ------------------------------------------------------------------------

PROMPT = """---
task: demo
version: 2
model: mistral-small-latest
temperature: 0.2
max_tokens: 300
---
## System
Be brief.

## User
Here: {input}
"""


def test_a_prompt_file_is_parsed_into_its_parts() -> None:
    p = prompts.parse(PROMPT, "demo/v2")
    assert (p.task, p.version, p.model, p.temperature, p.max_tokens) == (
        "demo",
        2,
        "mistral-small-latest",
        0.2,
        300,
    )
    assert p.system == "Be brief."
    assert p.user_message('{"a": 1}') == 'Here: {"a": 1}'
    assert p.label == "demo/v2"


@pytest.mark.parametrize(
    "broken",
    ["no front matter", PROMPT.replace("{input}", "nothing"), PROMPT.replace("## User\n", "")],
)
def test_a_broken_prompt_file_is_refused(broken: str) -> None:
    with pytest.raises(AiConfigError):
        prompts.parse(broken, "demo/v2")


def test_an_unknown_prompt_is_refused() -> None:
    with pytest.raises(AiConfigError, match="no prompt"):
        prompts.load("nothing_like_this", 1)


# --- fake provider ------------------------------------------------------------------


def test_fake_embeddings_have_the_right_size_and_put_shared_words_closer() -> None:
    a = hashed_embedding("seaweed farm nitrogen uptake")
    b = hashed_embedding("nitrogen uptake of a seaweed line")
    c = hashed_embedding("port logistics software")
    assert len(a) == EMBEDDING_DIMENSIONS

    def dot(x: list[float], y: list[float]) -> float:
        return sum(i * j for i, j in zip(x, y, strict=True))

    assert dot(a, b) > dot(a, c)
    assert hashed_embedding("") == [0.0] * EMBEDDING_DIMENSIONS


def test_the_fake_replies_as_told_and_records_the_call() -> None:
    fake = FakeProvider(lambda messages: json.dumps({"n": len(messages)}))
    out = fake.complete(
        model="m", messages=[Message("user", "hi")], schema={}, temperature=0, max_tokens=10
    )
    assert out.text == '{"n": 1}'
    assert out.model == "fake:m"
    assert len(fake.calls) == 1


# --- Mistral client, against a mock transport (never the network) --------------------


def _mistral(handler: httpx.MockTransport) -> MistralProvider:
    return MistralProvider("test-key", EU_BASE_URL, transport=handler)


def test_mistral_asks_for_strict_json_schema_output_and_reads_the_usage() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": "mistral-small-2506",
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            },
        )

    out = _mistral(httpx.MockTransport(answer)).complete(
        model="mistral-small-latest",
        messages=[Message("system", "s"), Message("user", "u")],
        schema={"type": "object"},
        temperature=0,
        max_tokens=50,
    )
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == f"{EU_BASE_URL}/v1/chat/completions"
    assert seen[0].headers["Authorization"] == "Bearer test-key"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]
    assert (out.text, out.model, out.input_tokens, out.output_tokens) == (
        '{"ok": true}',
        "mistral-small-2506",
        12,
        3,
    )


def test_mistral_embeddings_come_back_in_input_order() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["model"] == "mistral-embed"
        return httpx.Response(
            200,
            json={"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]},
        )

    vectors = _mistral(httpx.MockTransport(answer)).embed(["first", "second"])
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert _mistral(httpx.MockTransport(answer)).embed([]) == []


def test_a_mistral_error_says_the_status_but_never_echoes_the_body() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "secret company fact in the input"})

    with pytest.raises(AiError) as error:
        _mistral(httpx.MockTransport(answer)).embed(["x"])
    assert str(error.value) == "Mistral answered 422"


@pytest.mark.parametrize("url", ["https://api.openai.com", "http://api.eu.mistral.ai", ""])
def test_only_mistral_s_own_endpoints_are_accepted(url: str) -> None:
    with pytest.raises(AiConfigError, match="base URL"):
        MistralProvider("k", url)


def test_an_empty_key_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(AiConfigError):
        MistralProvider("  ")
    monkeypatch.delenv("HOME_BASE_MISTRAL_API_KEY", raising=False)
    with pytest.raises(AiConfigError, match="not set"):
        MistralProvider.from_environment()


# --- cost ---------------------------------------------------------------------------


def test_cost_is_the_list_price_and_an_unknown_model_counts_as_the_dearest() -> None:
    assert cost_eur("mistral-small-latest", 1_000_000, 1_000_000) == Decimal("0.75")
    assert cost_eur("fake:mistral-small-latest", 2_000_000, 0) == Decimal("0.30")
    assert cost_eur("something-new", 1_000_000, 0) == Decimal("0.70")  # the dearest listed
    assert cost_eur("claude-haiku-5-5", 1_000_000, 100_000) == Decimal("0.15")
    assert cost_eur("mistral-small-latest", 0, 0) == 0
