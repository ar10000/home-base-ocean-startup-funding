"""What every AI provider offers: one structured completion, and embeddings (ADR-009)."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class Completion:
    """The model's raw reply (JSON text) and what it cost in tokens."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class Message:
    role: str  # system, user or assistant
    content: str


class Provider(Protocol):
    """A chat model with JSON-schema output, and an embedding model."""

    name: str  # which provider and model answers, part of the cache key
    embedding_model: str

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Message],
        schema: dict[str, Any],
        temperature: float,
        max_tokens: int,
    ) -> Completion: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def normalised(vector: Sequence[float]) -> list[float]:
    """The vector scaled to length 1 (all zeros stays all zeros)."""
    length = math.sqrt(sum(x * x for x in vector))
    return [x / length for x in vector] if length else list(vector)
