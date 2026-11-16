"""SCP-02: the Opportunities list's order within a group (decision D-41)."""

from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from home_base.core.vocabulary import FitStatus
from home_base.modules.opportunities.rules import list_sort_key

Row = tuple[FitStatus, date | None, bool, str]


def _ordered(rows: list[Row]) -> list[str]:
    return [r[3] for r in sorted(rows, key=lambda r: list_sort_key(*r))]


def test_scp_02_empty_list_stays_empty() -> None:
    assert _ordered([]) == []


def test_scp_02_full_order() -> None:
    rows: list[Row] = [
        (FitStatus.NOT_ELIGIBLE, date(2026, 11, 20), True, "Gone"),
        (FitStatus.POSSIBLE, None, True, "Rolling"),
        (FitStatus.POSSIBLE, date(2026, 12, 1), False, "General"),
        (FitStatus.POSSIBLE, date(2026, 12, 1), True, "Blue"),
        (FitStatus.POSSIBLE, date(2026, 11, 25), False, "Soon"),
        (FitStatus.CONFIRMED, date(2027, 6, 1), False, "Later fit"),
    ]
    assert _ordered(rows) == ["Later fit", "Soon", "Blue", "General", "Rolling", "Gone"]


def test_scp_02_name_ignores_case() -> None:
    rows: list[Row] = [
        (FitStatus.POSSIBLE, None, True, "beta"),
        (FitStatus.POSSIBLE, None, True, "Alpha"),
    ]
    assert _ordered(rows) == ["Alpha", "beta"]


@given(
    fit=st.sampled_from(FitStatus),
    when=st.none() | st.dates(),
    name_a=st.text(max_size=5),
    name_b=st.text(max_size=5),
)
def test_scp_02_blue_specific_first_when_fit_and_date_are_equal(
    fit: FitStatus, when: date | None, name_a: str, name_b: str
) -> None:
    assert list_sort_key(fit, when, True, name_a) < list_sort_key(fit, when, False, name_b)
