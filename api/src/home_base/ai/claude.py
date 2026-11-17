"""Claude through the Anthropic API (D-84): the demo and the evaluations, fictional data only.

Andrew, 2026-11-17: Claude instead of Mistral for the demo and evals, on credits he
already has. ADR-004 still governs real founders' data (an EU provider); this provider
is never for them. The key comes from ANTHROPIC_API_KEY in the environment only.

- Model: claude-haiku-5-5, whatever model a prompt file names (those name Mistral's).
- Output: `output_config.format` with the task's JSON schema, so the reply is JSON.
- No temperature: the model rejects non-default sampling settings; thinking stays on
  (its default) at effort "medium", and max_tokens leaves room for it.
- Refusals: Haiku has no server-side fallback; a refusal is an AiError, so the runner
  logs it and nothing is saved.
- Embeddings: Anthropic has none, so they are computed locally (local_embed.py).
"""

from collections.abc import Sequence
from typing import Any

import anthropic
import httpx2

from home_base.ai.local_embed import LocalEmbedder
from home_base.ai.provider import Completion, Message
from home_base.core.errors import AiConfigError, AiError

MODEL = "claude-haiku-5-5"  # D-84: cheapest; about 0.03-0.05 EUR per eval run and recording
EFFORT = "medium"
MAX_TOKENS = 16000  # thinking and the answer together


class AnthropicProvider:
    name = f"anthropic:{MODEL}"

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        embedder: LocalEmbedder | None = None,
    ) -> None:
        try:
            self._client = client or anthropic.Anthropic(max_retries=2)
        except anthropic.AnthropicError as exc:
            raise AiConfigError("ANTHROPIC_API_KEY is not set") from exc
        self._embedder = embedder or LocalEmbedder()
        self.embedding_model = self._embedder.embedding_model

    @classmethod
    def with_transport(cls, transport: httpx2.BaseTransport) -> "AnthropicProvider":
        """For tests: a client that never reaches the network."""
        client = anthropic.Anthropic(
            api_key="test-key", http_client=httpx2.Client(transport=transport), max_retries=0
        )
        return cls(client)

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Message],
        schema: dict[str, Any],
        temperature: float,
        max_tokens: int,
    ) -> Completion:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        turns: Any = [
            {"role": m.role, "content": m.content} for m in messages if m.role != "system"
        ]
        output_config: Any = {
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": schema},
        }
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=max(MAX_TOKENS, max_tokens),
                system=system,
                messages=turns,
                output_config=output_config,
            )
        except anthropic.APIConnectionError as exc:
            raise AiError("Claude could not be reached") from exc
        except anthropic.APIStatusError as exc:
            # The status only: an error body may echo the input, which is never logged.
            raise AiError(f"Claude answered {exc.status_code}") from exc
        if response.stop_reason == "refusal":
            raise AiError("Claude declined this request")
        if response.stop_reason == "max_tokens":
            raise AiError("Claude ran out of room before finishing")
        text = next((b.text for b in response.content if b.type == "text"), "")
        return Completion(
            text=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embedder.embed(texts)
