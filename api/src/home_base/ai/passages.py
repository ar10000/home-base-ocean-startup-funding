"""A call's text in overlapping passages, and the passages closest to a set of questions
(ADR-009, D-83). Offsets are kept so any passage can be found again in the full text."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from home_base.ai.provider import Provider

PASSAGE_CHARS = 900
OVERLAP_CHARS = 150
PER_QUESTION = 2  # passages retrieved for each eligibility question
MAX_PASSAGES = 8  # all questions together


@dataclass(frozen=True, slots=True)
class Passage:
    position: int
    start: int
    text: str


def split(text: str, size: int = PASSAGE_CHARS, overlap: int = OVERLAP_CHARS) -> list[Passage]:
    """Windows of about `size` characters, overlapping by `overlap`, cut at whitespace so
    no word is split. Blank text gives no passages."""
    if not text.strip():
        return []
    passages: list[Passage] = []
    start = len(text) - len(text.lstrip())
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + size // 2, end)
            end = cut if cut > start else end
        chunk = text[start:end]
        if chunk.strip():
            passages.append(Passage(len(passages), start, chunk))
        if end >= len(text):
            break
        next_start = max(end - overlap, start + 1)
        space = text.find(" ", next_start, end)
        start = space + 1 if space != -1 else next_start
    return passages


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    size = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / size if size else 0.0


def relevant(
    provider: Provider, passages: Sequence[Passage], questions: Sequence[str]
) -> list[Passage]:
    """The passages closest to any of the questions, in their order in the call."""
    if not passages or not questions:
        return []
    vectors = provider.embed([p.text for p in passages])
    asked = provider.embed(list(questions))
    chosen: dict[int, Passage] = {}
    for q in asked:
        ranked = sorted(
            zip(passages, vectors, strict=True),
            key=lambda pv: (-_cosine(q, pv[1]), pv[0].position),
        )
        for passage, _ in ranked[:PER_QUESTION]:
            chosen.setdefault(passage.position, passage)
    return sorted(chosen.values(), key=lambda p: p.position)[:MAX_PASSAGES]
