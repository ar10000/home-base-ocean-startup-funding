"""Seed opportunity files (handbook section 11) and scope (SCP-01)."""

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from home_base.core.errors import SeedError
from home_base.core.vocabulary import Operator, OpportunityType
from home_base.modules.opportunities.domain import EvidenceKind, Month
from home_base.modules.opportunities.seed import Scope, load_seed_dir, parse_seed

TODAY = date(2026, 11, 9)
HERE = Path(__file__).resolve()
FIXTURES = HERE.parents[1] / "fixtures" / "seed"
REAL_SEED = next(p / "seed" / "opportunities" for p in HERE.parents if (p / "seed").is_dir())


def record(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "Fictional Call",
        "funder": "Example Foundation",
        "scope": "blue_specific",
        "types": ["grant"],
        "source_url": "https://example.org/call",
        "retrieved_on": date(2026, 11, 1),
        "verified_on": date(2026, 11, 2),
        "verified_by": "Test",
        "deadline": date(2027, 1, 31),
        "timezone": "Europe/Lisbon",
        "requirements": [
            {
                "type": "hard",
                "fact": "country",
                "operator": "equals",
                "value": "PT",
                "quote": "In PT.",
            }
        ],
    }
    base.update(changes)
    return {k: v for k, v in base.items() if v is not ...}


def test_every_real_seed_file_is_valid() -> None:
    # Runs on the real, hand-verified set; empty until the first opportunities land (D-12).
    load_seed_dir(REAL_SEED, TODAY)


DRAFTS = REAL_SEED.parent / "drafts"


def test_every_draft_parses_once_verified() -> None:
    """Drafts are researched, not checked by hand (D-12): only the format is tested here."""
    import yaml

    drafts = sorted(DRAFTS.glob("*.yaml"))
    if not drafts:
        pytest.skip("no drafts in this copy (the public copy leaves them out, D-79)")
    for path in drafts:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["verified_on"] is None, f"{path.name}: a draft is never marked verified"
        assert raw["verified_by"] is None, f"{path.name}: a draft is never marked verified"
        filled = {**raw, "verified_on": raw["retrieved_on"], "verified_by": "format check"}
        parse_seed(filled, path.name, TODAY + timedelta(days=1))


DEMO_SEED = next(p / "scripts" / "demo" / "seed" for p in HERE.parents if (p / "scripts").is_dir())


def test_the_public_demo_calls_are_valid_and_fictional() -> None:
    """D-79: the demo's calls load like real ones, and none points at a real website."""
    calls = load_seed_dir(DEMO_SEED, date(2026, 11, 16))  # the day the snapshot was recorded
    assert len(calls) == 6
    assert all(c.source_url.startswith("https://example.org/") for c in calls)


def test_fixtures_load() -> None:
    accelerator, grant = load_seed_dir(FIXTURES, TODAY)
    assert grant.scope is Scope.BLUE_SPECIFIC
    assert grant.requirements[1].operator is Operator.AT_LEAST
    assert not grant.requirements[2].hard
    assert grant.questions is not None
    assert grant.questions[1].required_facts == frozenset()
    assert accelerator.scope is Scope.ALL_SECTORS
    assert accelerator.deadline is None
    assert accelerator.timezone is None
    assert accelerator.expected_month == Month(2027, 3)
    assert accelerator.evidence[0].kind is EvidenceKind.PREVIOUS_EDITION
    assert accelerator.questions is None  # unknown, not empty
    assert grant.types == frozenset({OpportunityType.GRANT})
    assert accelerator.types == frozenset({OpportunityType.ACCELERATOR, OpportunityType.GRANT})


def test_a_valid_record() -> None:
    seed = parse_seed(record(), "x.yaml", TODAY)
    assert seed.timezone is not None
    assert str(seed.timezone) == "Europe/Lisbon"


# SCP-01: scope


@pytest.mark.parametrize("scope", [..., None, "", "marine", "BLUE_SPECIFIC"])
def test_scp_01_scope_missing_or_unknown_is_refused(scope: object) -> None:
    with pytest.raises(SeedError, match="scope"):
        parse_seed(record(scope=scope), "x.yaml", TODAY)


# INT-03: every opportunity has one or more types (D-43)


@pytest.mark.parametrize("types", [..., None, [], ["loan"], "grant", ["grant", "grant"]])
def test_int_03_types_missing_unknown_or_repeated_are_refused(types: object) -> None:
    with pytest.raises(SeedError, match="types"):
        parse_seed(record(types=types), "x.yaml", TODAY)


@pytest.mark.parametrize(
    "requirement",
    [
        {"type": "hard", "fact": "founder_age", "operator": "at_most", "value": 29, "quote": "q"},
        {
            "type": "hard",
            "fact": "woman_founder",
            "operator": "equals",
            "value": True,
            "quote": "q",
        },
        {"type": "hard", "fact": "woman_ceo", "operator": "equals", "value": True, "quote": "q"},
    ],
)
def test_req_06_07_founder_facts_are_accepted_in_seed_files(requirement: dict[str, Any]) -> None:
    seed = parse_seed(record(requirements=[requirement]), "x.yaml", TODAY)
    assert seed.requirements[0].fact == requirement["fact"]


def test_int_03_several_types() -> None:
    seed = parse_seed(record(types=["accelerator", "investor_programme"]), "x.yaml", TODAY)
    assert seed.types == frozenset(
        {OpportunityType.ACCELERATOR, OpportunityType.INVESTOR_PROGRAMME}
    )


# Handbook section 11: source, verification, quoted requirements


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"source_url": ...}, "source_url"),
        ({"source_url": "http://example.org/call"}, "source_url"),
        ({"verified_on": ...}, "verified_on"),
        ({"verified_on": date(2026, 11, 10)}, "verified_on"),
        ({"verified_on": "2 November"}, "verified_on"),
        ({"requirements": []}, "requirements"),
        ({"requirements": ...}, "requirements"),
        ({"name": ""}, "name"),
        ({"timezone": ...}, "timezone"),
        ({"timezone": "Mars/Olympus"}, "timezone"),
        ({"opening": date(2027, 2, 1)}, "opening"),
        ({"expected_month": "March"}, "expected_month"),
    ],
)
def test_refused(changes: dict[str, Any], field: str) -> None:
    with pytest.raises(SeedError, match=field):
        parse_seed(record(**changes), "x.yaml", TODAY)


@pytest.mark.parametrize(
    "requirement",
    [
        {"type": "hard", "fact": "country", "operator": "equals", "value": "PT"},  # no quote
        {"type": "hard", "fact": "country", "operator": "equals", "value": "PT", "quote": " "},
        {"type": "hard", "fact": "revenue", "operator": "equals", "value": 1, "quote": "q"},
        {"type": "hard", "fact": "country", "operator": "near", "value": "PT", "quote": "q"},
        {"type": "hard", "fact": "country", "operator": "equals", "quote": "q"},  # no value
        {"type": "soft", "quote": "q"},  # no criterion
        {"type": "maybe", "quote": "q"},
    ],
)
def test_bad_requirements_are_refused(requirement: dict[str, Any]) -> None:
    with pytest.raises(SeedError, match="requirements"):
        parse_seed(record(requirements=[requirement]), "x.yaml", TODAY)


@pytest.mark.parametrize(
    "evidence",
    [
        {"kind": "rumour", "dated": date(2026, 3, 1), "source_url": "https://example.org"},
        {"kind": "announcement", "dated": date(2026, 12, 1), "source_url": "https://example.org"},
        {"kind": "announcement", "dated": date(2026, 3, 1), "source_url": "http://example.org"},
        {"kind": "announcement", "source_url": "https://example.org"},  # no date
    ],
)
def test_bad_evidence_is_refused(evidence: dict[str, Any]) -> None:
    with pytest.raises(SeedError, match="evidence"):
        parse_seed(record(expected_month="2027-03", evidence=[evidence]), "x.yaml", TODAY)


def test_a_question_needs_text() -> None:
    with pytest.raises(SeedError, match="questions"):
        parse_seed(record(questions=[{"required_facts": ["trl"]}]), "x.yaml", TODAY)


def test_not_a_mapping_is_refused() -> None:
    with pytest.raises(SeedError, match="mapping"):
        parse_seed(["a", "list"], "x.yaml", TODAY)


def test_a_rolling_call_needs_no_timezone() -> None:
    seed = parse_seed(record(deadline=..., timezone=...), "x.yaml", TODAY)
    assert (seed.deadline, seed.timezone) == (None, None)


def test_the_readme_example_is_a_valid_seed_file() -> None:
    import re

    import yaml

    text = (REAL_SEED / "README.md").read_text(encoding="utf-8")
    example = re.search(r"```yaml\n(.*?)```", text, re.S)
    assert example is not None
    parse_seed(yaml.safe_load(example.group(1)), "README.md", TODAY)


def test_scp_01_two_opportunities_with_one_name_are_refused(tmp_path: Path) -> None:
    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text((FIXTURES / "fictional-ocean-grant.yaml").read_text())
    with pytest.raises(SeedError, match="also used by a.yaml"):
        load_seed_dir(tmp_path, date(2026, 11, 11))
