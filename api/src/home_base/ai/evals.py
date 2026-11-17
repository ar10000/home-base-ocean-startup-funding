"""Evaluation of the AI tasks against hand labels (handbook section 10).

Scoring is pure and tested; running it needs a provider and a database for the AI log.
Thresholds are the handbook's; a run below any of them fails.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from home_base.ai import validators
from home_base.ai.provider import Provider
from home_base.ai.runner import AiFailed
from home_base.ai.tasks import extract_requirements as extraction
from home_base.core.context import Clock

THRESHOLDS = {  # handbook section 10, "Threshold to merge"
    "extraction_recall": 0.95,
    "extraction_precision": 0.90,
    "extraction_quotes_verbatim": 1.0,
}

Rule = tuple[str, str, tuple[str, ...]]


def rule(fact: str, operator: str, values: Iterable[object]) -> Rule:
    """A hard rule in a comparable form: one_of a single value is the same as equals it."""
    vals = tuple(sorted(str(v).lower() for v in values))
    if operator == "one_of" and len(vals) == 1:
        operator = "equals"
    return (fact, operator, vals)


@dataclass(frozen=True, slots=True)
class Score:
    found: int  # labelled rules the model found
    labelled: int
    extracted: int  # hard rules the model gave
    quotes: int
    quotes_verbatim: int

    @property
    def recall(self) -> float:
        return self.found / self.labelled if self.labelled else 1.0

    @property
    def precision(self) -> float:
        return self.found / self.extracted if self.extracted else 1.0

    @property
    def verbatim(self) -> float:
        return self.quotes_verbatim / self.quotes if self.quotes else 1.0

    def __add__(self, other: "Score") -> "Score":
        return Score(
            self.found + other.found,
            self.labelled + other.labelled,
            self.extracted + other.extracted,
            self.quotes + other.quotes,
            self.quotes_verbatim + other.quotes_verbatim,
        )


EMPTY = Score(0, 0, 0, 0, 0)


def score(expected: Sequence[Rule], got: Sequence[Rule], quotes: Sequence[str], text: str) -> Score:
    labelled, given = set(expected), set(got)
    return Score(
        found=len(labelled & given),
        labelled=len(labelled),
        extracted=len(given),
        quotes=len(quotes),
        quotes_verbatim=len(quotes) - len(validators.quotes_verbatim(quotes, text)),
    )


def load_cases(folder: Path) -> list[dict[str, Any]]:
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.yaml"))]


def evaluate_extraction(
    session: Session, provider: Provider, cases: Sequence[dict[str, Any]], clock: Clock
) -> tuple[Score, list[str]]:
    """Total score, and one line per case. A failed extraction finds nothing."""
    total, lines = EMPTY, []
    for case in cases:
        expected = [rule(r["fact"], r["operator"], r["values"]) for r in case["expected"]]
        try:
            out = extraction.extract(
                session, provider, case["name"], case["text"], clock, cached=False
            ).value
        except AiFailed as failed:
            s = score(expected, [], [], case["text"])
            reasons = "; ".join(failed.problems)  # about the fictional call only
            lines.append(f"{case['name']}: extraction failed validation twice: {reasons}")
        else:
            hard = [r for r in out.requirements if r.type == "hard"]
            got = [rule(r.fact or "", r.operator or "", r.values) for r in hard]
            s = score(expected, got, [r.quote for r in out.requirements], case["text"])
            missed = sorted(set(expected) - set(got))
            extra = sorted(set(got) - set(expected))
            lines.append(
                f"{case['name']}: found {s.found}/{s.labelled}, extracted {s.extracted}"
                + (f"; missed {missed}" if missed else "")
                + (f"; extra {extra}" if extra else "")
            )
        total = total + s
    return total, lines


def below_thresholds(total: Score) -> list[str]:
    measured = {
        "extraction_recall": total.recall,
        "extraction_precision": total.precision,
        "extraction_quotes_verbatim": total.verbatim,
    }
    return [
        f"{name} {measured[name]:.0%} is below {limit:.0%}"
        for name, limit in THRESHOLDS.items()
        if measured[name] < limit
    ]
