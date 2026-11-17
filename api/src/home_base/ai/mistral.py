"""Mistral over HTTPS (ADR-004, ADR-009): JSON-schema chat completions and mistral-embed.

The key comes from the environment only, and is never logged or stored. The base URL
must be Mistral's EU endpoint, or its global one, which the free tier may need: the
free tier is used with fictional data only (ADR-009).
"""

import os
from collections.abc import Sequence
from typing import Any

import httpx

from home_base.ai.provider import Completion, Message
from home_base.core.errors import AiConfigError, AiError

KEY_ENV = "HOME_BASE_MISTRAL_API_KEY"
BASE_URL_ENV = "HOME_BASE_MISTRAL_BASE_URL"
EU_BASE_URL = "https://api.eu.mistral.ai"
ALLOWED_BASE_URLS = (EU_BASE_URL, "https://api.mistral.ai")
EMBEDDING_MODEL = "mistral-embed"
TIMEOUT_SECONDS = 60.0


class MistralProvider:
    name = "mistral"
    embedding_model = EMBEDDING_MODEL

    def __init__(
        self,
        api_key: str,
        base_url: str = EU_BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if base_url not in ALLOWED_BASE_URLS:
            raise AiConfigError(f"the Mistral base URL must be one of {ALLOWED_BASE_URLS}")
        if not api_key.strip():
            raise AiConfigError(f"{KEY_ENV} is empty")
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    @classmethod
    def from_environment(cls) -> "MistralProvider":
        key = os.environ.get(KEY_ENV)
        if not key:
            raise AiConfigError(f"{KEY_ENV} is not set")
        return cls(key, os.environ.get(BASE_URL_ENV, EU_BASE_URL))

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=body)
        except httpx.HTTPError as exc:
            raise AiError(f"Mistral could not be reached ({type(exc).__name__})") from exc
        if response.status_code >= 400:
            # The status only: the body may echo the input, which is never logged.
            raise AiError(f"Mistral answered {response.status_code}")
        data: dict[str, Any] = response.json()
        return data

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Message],
        schema: dict[str, Any],
        temperature: float,
        max_tokens: int,
    ) -> Completion:
        data = self._post(
            "/v1/chat/completions",
            {
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "output", "schema": schema, "strict": True},
                },
            },
        )
        usage = data.get("usage", {})
        return Completion(
            text=str(data["choices"][0]["message"]["content"]),
            model=str(data.get("model", model)),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        data = self._post("/v1/embeddings", {"model": EMBEDDING_MODEL, "input": list(texts)})
        rows = sorted(data["data"], key=lambda r: int(r["index"]))
        return [[float(x) for x in r["embedding"]] for r in rows]
