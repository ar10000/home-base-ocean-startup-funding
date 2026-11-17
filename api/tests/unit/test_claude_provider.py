"""Claude through the Anthropic SDK, against a mock transport (D-84). Never the network."""

import json

import httpx2
import pytest

from home_base.ai.claude import MODEL, AnthropicProvider
from home_base.ai.local_embed import padded
from home_base.ai.provider import Message
from home_base.ai.runner import input_hash
from home_base.ai.settings import provider_from_environment
from home_base.ai.tasks.draft_answer import DraftInput, prompt
from home_base.config import EMBEDDING_DIMENSIONS
from home_base.core.errors import AiError


def _reply(**over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": [
            {"type": "thinking", "thinking": "", "signature": "s"},
            {"type": "text", "text": '{"ok": true}'},
        ],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 120, "output_tokens": 40},
    }
    return body | over


def _provider(handler: object) -> tuple[AnthropicProvider, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def answer(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request)  # type: ignore[operator, no-any-return]

    return AnthropicProvider.with_transport(httpx2.MockTransport(answer)), seen


def _complete(provider: AnthropicProvider) -> object:
    return provider.complete(
        model="mistral-small-latest",
        messages=[Message("system", "Be exact."), Message("user", "Facts: {}")],
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        temperature=0.2,
        max_tokens=300,
    )


def test_it_asks_claude_for_json_in_the_task_s_schema() -> None:
    provider, seen = _provider(lambda r: httpx2.Response(200, json=_reply()))
    out = _complete(provider)
    body = json.loads(seen[0].content)
    assert body["model"] == MODEL  # whatever model the prompt file names
    assert body["system"] == "Be exact."
    assert body["messages"] == [{"role": "user", "content": "Facts: {}"}]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert body["output_config"]["effort"] == "medium"
    assert "temperature" not in body  # the model rejects sampling settings
    assert "thinking" not in body  # it cannot be turned off
    assert body["max_tokens"] >= 16000  # room for thinking and the answer
    assert body["model"] == "claude-haiku-5-5"  # D-84: the cheapest model
    assert (out.text, out.model, out.input_tokens, out.output_tokens) == (  # type: ignore[attr-defined]
        '{"ok": true}',
        MODEL,
        120,
        40,
    )


@pytest.mark.parametrize(
    ("stop", "says"),
    [("refusal", "declined"), ("max_tokens", "ran out of room")],
)
def test_a_reply_that_did_not_finish_is_an_error(stop: str, says: str) -> None:
    provider, _ = _provider(lambda r: httpx2.Response(200, json=_reply(stop_reason=stop)))
    with pytest.raises(AiError, match=says):
        _complete(provider)


def test_an_api_error_says_the_status_but_never_echoes_the_body() -> None:
    error = {"type": "error", "error": {"type": "invalid_request_error", "message": "secret fact"}}
    provider, _ = _provider(lambda r: httpx2.Response(400, json=error))
    with pytest.raises(AiError) as raised:
        _complete(provider)
    assert str(raised.value) == "Claude answered 400"


def test_the_cache_key_differs_by_provider() -> None:
    given = DraftInput(question="q", limit=None, facts=[])
    assert input_hash(prompt(), given, "fake") != input_hash(
        prompt(), given, AnthropicProvider.name
    )


def test_local_embeddings_are_padded_to_the_column_without_changing_closeness() -> None:
    a, b = padded([3.0, 4.0]), padded([4.0, 3.0])
    assert len(a) == EMBEDDING_DIMENSIONS
    assert a[:2] == [0.6, 0.8] and set(a[2:]) == {0.0}
    assert sum(x * y for x, y in zip(a, b, strict=True)) == pytest.approx(0.96)
    with pytest.raises(ValueError):
        padded([1.0] * (EMBEDDING_DIMENSIONS + 1))


def test_anthropic_is_chosen_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_BASE_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = provider_from_environment()
    assert isinstance(provider, AnthropicProvider)
    assert provider.embedding_model == "bge-small-en-v1.5"
