"""The verified opportunity set: one YAML file per opportunity (handbook section 11).

`parse_seed` is pure: it takes one parsed YAML document and returns a validated
record or raises SeedError naming the file and the field. `load_seed_dir` only adds
reading the files. Nothing here writes to the database.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from home_base.config import FACT_VALUES, FOUNDER_FACT_KEYS, HARD_RULE_FACT_KEYS
from home_base.core.errors import SeedError
from home_base.core.vocabulary import Operator, OpportunityType
from home_base.modules.opportunities.domain import Evidence, EvidenceKind, Month

REQUIRED = ("name", "funder", "scope", "source_url", "retrieved_on", "verified_on", "verified_by")


class Scope(StrEnum):
    """Whether an opportunity is for the blue economy or open to all sectors (SCP-01)."""

    BLUE_SPECIFIC = "blue_specific"
    ALL_SECTORS = "all_sectors"


@dataclass(frozen=True, slots=True)
class SeedRequirement:
    """One extracted requirement with the exact quote from the call."""

    hard: bool
    quote: str
    fact: str | None = None
    operator: Operator | None = None
    value: Any = None  # a fact value or a list of values; checked by matching (REQ rules)
    criterion: str | None = None


@dataclass(frozen=True, slots=True)
class SeedQuestion:
    """One application question and the company facts a draft needs."""

    text: str
    required_facts: frozenset[str]


@dataclass(frozen=True, slots=True)
class SeedOpportunity:
    """One verified opportunity, as reviewed in its seed file."""

    source: str
    name: str
    funder: str
    scope: Scope
    types: frozenset[OpportunityType]
    source_url: str
    retrieved_on: date
    verified_on: date
    verified_by: str
    deadline: date | None
    timezone: ZoneInfo | None
    opening: date | None
    expected_month: Month | None
    evidence: tuple[Evidence, ...]
    requirements: tuple[SeedRequirement, ...]
    questions: tuple[SeedQuestion, ...] | None  # None: the question list is unknown


def _fail(source: str, field: str, problem: str) -> SeedError:
    return SeedError(f"{source}: {field}: {problem}")


def _date(raw: Mapping[str, Any], key: str, source: str) -> date | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, date):
        raise _fail(source, key, f"not a date: {value!r}")
    return value


def _past_date(raw: Mapping[str, Any], key: str, source: str, today: date) -> date:
    value = _date(raw, key, source)
    if value is None:
        raise _fail(source, key, "required")
    if value > today:
        raise _fail(source, key, f"in the future: {value}")
    return value


def _month(raw: Mapping[str, Any], source: str) -> Month | None:
    value = raw.get("expected_month")
    if value is None:
        return None
    try:
        year, month = str(value).split("-")
        return Month(int(year), int(month))
    except ValueError as exc:
        raise _fail(source, "expected_month", f"not YYYY-MM: {value!r}") from exc


def _requirement(item: Mapping[str, Any], source: str, i: int) -> SeedRequirement:
    where = f"requirements[{i}]"
    quote = item.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        raise _fail(source, where, "needs the exact quote from the call")
    if item.get("type") == "soft":
        criterion = item.get("criterion")
        if not isinstance(criterion, str) or not criterion.strip():
            raise _fail(source, where, "a soft criterion needs its wording")
        return SeedRequirement(hard=False, quote=quote, criterion=criterion)
    if item.get("type") != "hard":
        raise _fail(source, where, "type must be hard or soft")
    fact = item.get("fact")
    allowed = HARD_RULE_FACT_KEYS | FOUNDER_FACT_KEYS  # founder facts: REQ-06, REQ-07
    if fact not in allowed:
        raise _fail(source, where, f"fact must be one of {sorted(allowed)}")
    try:
        operator = Operator(str(item.get("operator")))
    except ValueError as exc:
        raise _fail(source, where, f"unknown operator {item.get('operator')!r}") from exc
    if "value" not in item:
        raise _fail(source, where, "a hard rule needs a value")
    values = item["value"] if isinstance(item["value"], list) else [item["value"]]
    if fact in FACT_VALUES:  # REQ-09: the same words as the company profile (D-76)
        known = {v for v, _ in FACT_VALUES[fact]}
        unknown = [v for v in values if v not in known]
        if unknown:
            raise _fail(source, where, f"{fact} values {unknown} are not in its list")
    return SeedRequirement(True, quote, fact, operator, item["value"])


def _evidence(raw: Mapping[str, Any], source: str, today: date) -> tuple[Evidence, ...]:
    found = []
    for i, item in enumerate(raw.get("evidence") or []):
        where = f"evidence[{i}]"
        try:
            kind = EvidenceKind(item.get("kind"))
        except ValueError as exc:
            raise _fail(source, where, "kind must be previous_edition or announcement") from exc
        dated = _past_date(item, "dated", f"{source}: {where}", today)
        url = item.get("source_url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise _fail(source, where, "needs an https source_url")
        found.append(Evidence(kind, dated, url))
    return tuple(found)


def _questions(raw: Mapping[str, Any], source: str) -> tuple[SeedQuestion, ...] | None:
    if "questions" not in raw or raw["questions"] is None:
        return None
    found = []
    for i, item in enumerate(raw["questions"]):
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise _fail(source, f"questions[{i}]", "needs its text")
        found.append(SeedQuestion(text, frozenset(item.get("required_facts") or [])))
    return tuple(found)


def _types(raw: Mapping[str, Any], source: str) -> frozenset[OpportunityType]:
    value = raw.get("types")
    if not isinstance(value, list) or not value:
        raise _fail(source, "types", "at least one type (D-43)")
    try:
        found = [OpportunityType(t) for t in value]
    except ValueError as exc:
        allowed = ", ".join(t.value for t in OpportunityType)
        raise _fail(source, "types", f"each must be one of: {allowed}") from exc
    if len(set(found)) != len(found):
        raise _fail(source, "types", "a type appears once")
    return frozenset(found)


def _timezone(raw: Mapping[str, Any], deadline: date | None, source: str) -> ZoneInfo | None:
    name = raw.get("timezone")
    if deadline is None:
        return None
    if not isinstance(name, str):
        raise _fail(source, "timezone", "required with a deadline (the funder's timezone)")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise _fail(source, "timezone", f"unknown timezone {name!r}") from exc


def parse_seed(raw: object, source: str, today: date) -> SeedOpportunity:
    """Validate one seed file's content.

    Rule SCP-01: every opportunity has a scope (blue-specific or all sectors);
    the seed check rejects a record without one.
    It also needs one or more opportunity types, each once (decision D-43; INT-03 reads them).
    Also refuses a record without an https source URL, a verification date or at
    least one quoted requirement (handbook section 11), dates in the future, and
    an opening date after the deadline.
    """
    if not isinstance(raw, Mapping):
        raise _fail(source, "file", "must be a YAML mapping")
    for key in REQUIRED:
        if raw.get(key) in (None, ""):
            raise _fail(source, key, "required")
    try:
        scope = Scope(raw["scope"])
    except ValueError as exc:
        raise _fail(source, "scope", "must be blue_specific or all_sectors") from exc
    if not str(raw["source_url"]).startswith("https://"):
        raise _fail(source, "source_url", "must be an https URL")
    requirements = raw.get("requirements") or []
    if not requirements:
        raise _fail(source, "requirements", "at least one quoted requirement")
    deadline = _date(raw, "deadline", source)
    opening = _date(raw, "opening", source)
    if opening is not None and deadline is not None and opening > deadline:
        raise _fail(source, "opening", f"after the deadline {deadline}")
    return SeedOpportunity(
        source=source,
        name=str(raw["name"]),
        funder=str(raw["funder"]),
        scope=scope,
        types=_types(raw, source),
        source_url=str(raw["source_url"]),
        retrieved_on=_past_date(raw, "retrieved_on", source, today),
        verified_on=_past_date(raw, "verified_on", source, today),
        verified_by=str(raw["verified_by"]),
        deadline=deadline,
        timezone=_timezone(raw, deadline, source),
        opening=opening,
        expected_month=_month(raw, source),
        evidence=_evidence(raw, source, today),
        requirements=tuple(_requirement(r, source, i) for i, r in enumerate(requirements)),
        questions=_questions(raw, source),
    )


def check_unique_names(records: Sequence[SeedOpportunity]) -> None:
    """Refuse two opportunities with the same name.

    Rule SCP-01: the seed check rejects records it cannot trust; two with one name
    would make a task that names an opportunity ambiguous.
    """
    seen: dict[str, str] = {}
    for r in records:
        if r.name in seen:
            raise SeedError(f"{r.source}: name: {r.name!r} is also used by {seen[r.name]}")
        seen[r.name] = r.source


def load_seed_dir(directory: Path, today: date) -> list[SeedOpportunity]:
    """Every *.yaml file in a directory, validated; the first bad file stops the load."""
    found = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        found.append(parse_seed(raw, path.name, today))
    check_unique_names(found)
    return found
