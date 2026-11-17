"""Checks on AI output (handbook section 10). Each returns the problems found, in words
the model can act on in its one retry; an empty list means valid."""

import re
from collections.abc import Collection, Iterable

# A number as written in prose: 2, 2.5, 2,5, 1,200, 40%. Commas and dots are read as
# written; "2.5" and "2,5" are different strings and must each appear in a fact.
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_in(text: str) -> list[str]:
    return _NUMBER.findall(text)


def words(text: str) -> str:
    """The text with every run of whitespace (line breaks included) read as one space."""
    return " ".join(text.split())


def quotes_verbatim(quotes: Iterable[str], source: str) -> list[str]:
    """Every quote must be in the source word for word (extraction: 100%). Line wrapping is
    not part of the words (D-85): a quote copied across a line break still matches."""
    text = words(source)
    return [
        f"quote not found word for word in the call: {q!r}"
        for q in quotes
        if not words(q) or words(q) not in text
    ]


def numbers_cited(text: str, cited: Iterable[str]) -> list[str]:
    """Every number in the text must appear in one of the cited facts (drafts: 0 unsupported)."""
    sources = " ".join(cited)
    found = set(numbers_in(sources))
    return [
        f"the number {n} is in no cited fact; use only numbers from the facts"
        for n in dict.fromkeys(numbers_in(text))
        if n not in found
    ]


def within_limit(text: str, limit: int | None) -> list[str]:
    if limit is None or len(text) <= limit:
        return []
    return [f"the answer is {len(text)} characters; the limit is {limit}"]


def only_known(ids: Iterable[str], allowed: Collection[str], what: str) -> list[str]:
    """Every ID the output names must be one it was given."""
    return [f"{what} {i} was not in the input" for i in dict.fromkeys(ids) if i not in allowed]
