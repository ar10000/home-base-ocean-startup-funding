"""Passages, requirement extraction checks and evaluation scoring (D-83, section 10)."""

from datetime import date
from itertools import pairwise
from pathlib import Path

import pytest

from home_base.ai import evals
from home_base.ai.fake import FakeProvider
from home_base.ai.passages import relevant, split
from home_base.ai.tasks.extract_requirements import (
    ExtractOutput,
    RequirementOut,
    Validate,
    fact_guide,
    prompt,
    seed_requirement,
)
from home_base.modules.opportunities.seed import parse_seed

EVALS = Path(__file__).resolve().parents[1] / "evals"
CALL = "Applicants must be registered in Portugal. The product must be at TRL 5 or above."

# --- passages ------------------------------------------------------------------------


def test_passages_cover_the_text_overlap_and_keep_their_offsets() -> None:
    text = " ".join(f"word{i}" for i in range(600))
    parts = split(text, size=300, overlap=60)
    assert len(parts) > 3
    for p in parts:
        assert text[p.start : p.start + len(p.text)] == p.text  # findable again
        assert not p.text.startswith(" ") or p.start == 0
    assert parts[0].start == 0
    assert parts[-1].start + len(parts[-1].text) == len(text)  # nothing left out
    assert all(b.start < a.start + len(a.text) for a, b in pairwise(parts))  # overlap
    assert [p.position for p in parts] == list(range(len(parts)))


def test_no_word_is_cut_in_half() -> None:
    text = " ".join(["seaweed"] * 200)
    for p in split(text, size=100, overlap=20):
        assert set(p.text.split()) == {"seaweed"}


@pytest.mark.parametrize("blank", ["", "   \n  "])
def test_blank_text_has_no_passages(blank: str) -> None:
    assert split(blank) == []


def test_short_text_is_one_passage() -> None:
    assert [p.text for p in split("  Open to SMEs.")] == ["Open to SMEs."]


def test_relevant_passages_are_the_closest_in_call_order() -> None:
    text = (
        "Background on the ocean economy and its history. " * 10
        + "Eligibility: companies registered in Portugal may apply. " * 3
        + "Budget and payment schedule for the projects. " * 10
    )
    parts = split(text, size=200, overlap=40)
    chosen = relevant(FakeProvider(), parts, ["Which companies are eligible to apply?"])
    assert chosen
    assert any("Eligibility" in p.text for p in chosen)
    assert [p.position for p in chosen] == sorted(p.position for p in chosen)
    assert relevant(FakeProvider(), [], ["q"]) == []
    assert relevant(FakeProvider(), parts, []) == []


# --- extraction checks ---------------------------------------------------------------


def _req(**over: object) -> RequirementOut:
    base: dict[str, object] = {
        "type": "hard",
        "fact": "country",
        "operator": "equals",
        "values": ["PT"],
        "criterion": None,
        "quote": "Applicants must be registered in Portugal.",
    }
    return RequirementOut.model_validate(base | over)


def _check(*reqs: RequirementOut) -> list[str]:
    return Validate(CALL)(ExtractOutput(requirements=list(reqs)))


def test_a_correct_extraction_is_valid() -> None:
    trl = _req(fact="trl", operator="at_least", values=["5"], quote="TRL 5 or above")
    soft = _req(
        type="soft", fact=None, operator=None, values=[], criterion="Impact", quote="product"
    )
    assert _check(_req(), trl, soft) == []


def test_a_quote_must_be_word_for_word() -> None:
    assert _check(_req(quote="Applicants must be based in Portugal.")) == [
        "quote not found word for word in the call: 'Applicants must be based in Portugal.'"
    ]


@pytest.mark.parametrize(
    ("over", "says"),
    [
        ({"fact": "revenue"}, "fact must be one of"),
        ({"operator": "about"}, "unknown operator"),
        ({"values": ["Portugal"]}, "not in its list"),
        ({"values": ["PT", "ES"]}, "takes exactly one value"),
        ({"fact": "trl", "operator": "at_least", "values": ["five"]}, "invalid literal"),
        ({"type": "soft", "criterion": None, "fact": None}, "needs its wording"),
    ],
)
def test_a_requirement_the_seed_loader_would_refuse_is_refused(
    over: dict[str, object], says: str
) -> None:
    problems = _check(_req(**over))
    assert len(problems) == 1
    assert says in problems[0]


def test_values_are_written_as_the_seed_files_write_them() -> None:
    assert seed_requirement(_req(fact="trl", operator="at_least", values=["5"]))["value"] == 5
    listed = _req(operator="one_of", values=["PT", "ES"])
    assert seed_requirement(listed)["value"] == ["PT", "ES"]
    ceo = _req(fact="woman_ceo", values=["True"])
    assert seed_requirement(ceo)["value"] is True


def test_the_model_is_told_every_fact_it_may_use_and_its_values() -> None:
    guide = fact_guide()
    assert set(guide) == {
        "applicant_form", "company_age", "country", "founder_age", "legal_form",
        "sector", "team_size", "trl", "woman_ceo", "woman_founder",
    }  # fmt: skip
    assert "PT" in guide["country"]
    assert prompt().label == "extract_requirements/v2"


# --- the evaluation set and its scoring ----------------------------------------------


def test_every_labelled_rule_is_one_the_seed_loader_accepts_and_quotable() -> None:
    cases = evals.load_cases(EVALS / "extraction")
    assert len(cases) >= 3
    for case in cases:
        assert case["expected"], case["name"]
        reqs = [
            seed_requirement(
                _req(fact=r["fact"], operator=r["operator"], values=[str(v) for v in r["values"]],
                     quote=case["text"][:20])
            )
            for r in case["expected"]
        ]  # fmt: skip
        record = {
            "name": case["name"], "funder": "x", "scope": "all_sectors", "types": ["grant"],
            "source_url": "https://example.org/x", "retrieved_on": date(2026, 1, 1),
            "verified_on": date(2026, 1, 1), "verified_by": "x", "requirements": reqs,
        }  # fmt: skip
        parse_seed(record, case["name"], date(2026, 1, 2))


def test_one_of_a_single_value_counts_as_equals() -> None:
    assert evals.rule("country", "one_of", ["PT"]) == evals.rule("country", "equals", ["pt"])
    assert evals.rule("country", "one_of", ["PT", "ES"]) == evals.rule(
        "country", "one_of", ["ES", "PT"]
    )


def test_scores_count_found_missed_extra_and_quotes() -> None:
    expected = [evals.rule("trl", "at_least", [5]), evals.rule("country", "equals", ["PT"])]
    got = [evals.rule("trl", "at_least", ["5"]), evals.rule("team_size", "at_most", [49])]
    s = evals.score(expected, got, ["TRL 5 or above", "made up words"], CALL)
    assert (s.found, s.labelled, s.extracted, s.quotes, s.quotes_verbatim) == (1, 2, 2, 2, 1)
    assert (s.recall, s.precision, s.verbatim) == (0.5, 0.5, 0.5)
    assert evals.EMPTY.recall == 1.0 and evals.EMPTY.precision == 1.0


def test_thresholds_are_the_handbook_s() -> None:
    perfect = evals.Score(10, 10, 10, 10, 10)
    assert evals.below_thresholds(perfect) == []
    one_quote_off = evals.Score(10, 10, 10, 10, 9)
    assert evals.below_thresholds(one_quote_off) == ["extraction_quotes_verbatim 90% is below 100%"]
    missed = evals.Score(19, 20, 19, 19, 19)
    assert evals.below_thresholds(missed) == []  # 95% recall is the threshold itself
    assert evals.below_thresholds(evals.Score(18, 20, 18, 18, 18)) == [
        "extraction_recall 90% is below 95%"
    ]


def test_the_local_fake_finds_no_requirements_rather_than_inventing_any() -> None:
    from home_base.ai.fake import local_reply
    from home_base.ai.provider import Message
    from home_base.ai.tasks.extract_requirements import ExtractInput

    given = ExtractInput(call="c", passages=[], facts=fact_guide(), operators=["equals"])
    reply = local_reply([Message("user", prompt().user_message(given.model_dump_json()))])
    assert ExtractOutput.model_validate_json(reply).requirements == []
