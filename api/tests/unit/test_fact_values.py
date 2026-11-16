"""Rule REQ-09: listed facts only take listed values, in the profile and the seed (D-76)."""

from datetime import date
from pathlib import Path

import pytest

from home_base.config import FACT_VALUES
from home_base.core.errors import SeedError
from home_base.modules.companies.rules import fact_value_allowed
from home_base.modules.opportunities.seed import load_seed_dir

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "seed" / "fictional-ocean-grant.yaml"
COUNTRY_RULE = "fact: country, operator: equals, value: PT"


def _seed(tmp_path: Path, fact: str, value: str) -> Path:
    """The fictional grant with its country rule replaced by the one under test."""
    text = FIXTURE.read_text(encoding="utf-8")
    assert COUNTRY_RULE in text
    rule = f"fact: {fact}, operator: one_of, value: {value}"
    (tmp_path / "value-test.yaml").write_text(text.replace(COUNTRY_RULE, rule), encoding="utf-8")
    return tmp_path


def test_req_09_every_list_has_unique_values_and_labels() -> None:
    for key, values in FACT_VALUES.items():
        assert len({v for v, _ in values}) == len(values), key
        assert all(label.strip() for _, label in values), key


def test_req_09_the_27_member_states_and_outside_the_eu() -> None:
    countries = [v for v, _ in FACT_VALUES["country"]]
    assert len(countries) == 28
    assert countries[-1] == "OTHER"
    assert "GR" in countries
    assert "EL" not in countries


@pytest.mark.parametrize(("key", "value"), [("trl", 12), ("team_size", "four"), ("unknown", "x")])
def test_req_09_unlisted_facts_are_left_to_their_own_checks(key: str, value: object) -> None:
    assert fact_value_allowed(key, value)


def test_req_09_a_seed_with_a_listed_value_loads(tmp_path: Path) -> None:
    loaded = load_seed_dir(
        _seed(tmp_path, "sector", "[blue_biotechnology, ocean_energy]"), date(2026, 11, 16)
    )
    assert loaded[0].name == "Fictional Ocean Grant"


@pytest.mark.parametrize(
    ("fact", "value"),
    [
        ("sector", "[Aquaculture]"),
        ("country", "[PT, EL]"),
        ("legal_form", "[Lda]"),
        ("applicant_form", "[both]"),
    ],
)
def test_req_09_a_seed_with_an_unlisted_value_is_refused(
    tmp_path: Path, fact: str, value: str
) -> None:
    with pytest.raises(SeedError, match="not in its list"):
        load_seed_dir(_seed(tmp_path, fact, value), date(2026, 11, 16))
