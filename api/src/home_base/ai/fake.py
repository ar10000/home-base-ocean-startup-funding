"""A provider for tests and CI: no network, same answer for the same input (ADR-009).

Completions come from a function the test gives (or a fixed reply); embeddings from the
hashing trick, so texts sharing words are close, which is enough to test retrieval.
"""

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from typing import Any

from home_base.ai.provider import Completion, Message, normalised
from home_base.config import EMBEDDING_DIMENSIONS

FAKE_EMBEDDING_MODEL = "fake-embed"
Reply = Callable[[Sequence[Message]], str]


def hashed_embedding(text: str) -> list[float]:
    """Bag of words hashed into EMBEDDING_DIMENSIONS buckets, normalised."""
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        bucket = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big")
        vector[bucket % EMBEDDING_DIMENSIONS] += 1.0
    return normalised(vector)


class FakeProvider:
    name = "fake"
    embedding_model = FAKE_EMBEDDING_MODEL

    def __init__(self, reply: Reply | str = "{}") -> None:
        self._reply = reply
        self.calls: list[Sequence[Message]] = []
        self.embedded: list[str] = []

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Message],
        schema: dict[str, Any],
        temperature: float,
        max_tokens: int,
    ) -> Completion:
        self.calls.append(messages)
        text = self._reply if isinstance(self._reply, str) else self._reply(messages)
        size = sum(len(m.content) for m in messages)
        return Completion(text, f"fake:{model}", size // 4, len(text) // 4)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return [hashed_embedding(t) for t in texts]


def _payload(messages: Sequence[Message]) -> dict[str, Any]:
    """The task input: the JSON object at the end of the last user message."""
    text = next(m.content for m in reversed(messages) if m.role == "user")
    start = text.find("{")
    try:
        found = json.loads(text[start:]) if start >= 0 else {}
    except json.JSONDecodeError:
        return {}
    return found if isinstance(found, dict) else {}


_LEAD = {"confirmed": "Fits", "possible": "May fit", "not_eligible": "Does not fit"}


def _why(payload: dict[str, Any]) -> str:
    """Why it fits, mechanically: the deciding requirement in the call's own words."""
    reqs = payload.get("requirements", [])
    fit = str(payload.get("fit"))
    wanted = {"not_eligible": "fail", "possible": "unknown"}.get(fit, "pass")
    key = next((r for r in reqs if r["result"] == wanted), reqs[0] if reqs else None)
    if key is None:
        return json.dumps({"sentences": []})
    text = f"{_LEAD.get(fit, 'Fit')}: {key['quote'].rstrip('.')}."
    return json.dumps({"sentences": [{"text": text, "requirements": [key["ref"]]}]})


def local_reply(messages: Sequence[Message]) -> str:
    """A plain, valid reply built from the input alone, for the local stack without a key:
    it restates the input, clearly mechanical, never invented."""
    payload = _payload(messages)
    if "passages" in payload:  # extraction: a fake cannot read a call, so it finds nothing
        return json.dumps({"requirements": []})
    if "requirements" in payload:
        return _why(payload)
    facts = payload.get("facts", [])
    sentences = [
        {"text": f"{f['fact'].capitalize()}: {f['value'].rstrip('.')}.", "facts": [f["ref"]]}
        for f in facts
    ]
    return json.dumps({"sentences": sentences})
