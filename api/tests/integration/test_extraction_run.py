"""Extraction and its evaluation end to end through the runner (D-83, section 10)."""

import json
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from home_base.ai import evals
from home_base.ai.fake import FakeProvider
from home_base.ai.provider import Message
from home_base.ai.tasks.extract_requirements import extract
from home_base.core.context import Clock
from home_base.modules.audit.models import AiAction

pytestmark = pytest.mark.integration

CLOCK = Clock(at=datetime(2026, 11, 17, 9, tzinfo=UTC), today=date(2026, 11, 17))
CASES = evals.load_cases(Path(__file__).resolve().parents[1] / "evals" / "extraction")


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


def _answer_with_labels(messages: Sequence[Message]) -> str:
    """A perfect extractor for the eval set: the labels, quoting the call's first words."""
    payload: dict[str, Any] = json.loads(messages[-1].content.split("\n\n", 1)[1])
    case = next(c for c in CASES if c["name"] == payload["call"])
    return json.dumps(
        {
            "requirements": [
                {
                    "type": "hard",
                    "fact": r["fact"],
                    "operator": r["operator"],
                    "values": [str(v) for v in r["values"]],
                    "criterion": None,
                    "quote": case["text"][:25],
                }
                for r in case["expected"]
            ]
        }
    )


def test_a_perfect_extractor_scores_full_marks(session: Session) -> None:
    total, lines = evals.evaluate_extraction(
        session, FakeProvider(_answer_with_labels), CASES, CLOCK
    )
    assert (total.recall, total.precision, total.verbatim) == (1.0, 1.0, 1.0)
    assert evals.below_thresholds(total) == []
    assert len(lines) == len(CASES)


def test_a_failing_extractor_finds_nothing_and_says_so(session: Session) -> None:
    bad = FakeProvider(
        '{"requirements": [{"type": "hard", "fact": "trl", "operator": '
        '"at_least", "values": ["5"], "criterion": null, "quote": "not in it"}]}'
    )
    total, lines = evals.evaluate_extraction(session, bad, CASES[:1], CLOCK)
    assert total.found == 0 and total.labelled == len(CASES[0]["expected"])
    assert lines[0].startswith(
        f"{CASES[0]['name']}: extraction failed validation twice: quote not found"
    )
    assert "extraction_recall 0% is below 95%" in evals.below_thresholds(total)


def test_extraction_sends_only_the_eligibility_passages_and_logs_without_company(
    session: Session,
) -> None:
    case = next(c for c in CASES if c["name"] == "Coastal Innovation Voucher")
    fake = FakeProvider(_answer_with_labels)
    extract(session, fake, case["name"], case["text"], CLOCK)
    sent = json.loads(fake.calls[0][-1].content.split("\n\n", 1)[1])
    texts = " ".join(p["text"] for p in sent["passages"])
    assert "Who can apply" in texts
    assert len(texts) <= len(case["text"]) + 8 * 150  # passages, not the call many times over
    action = session.scalars(select(AiAction)).one()
    assert (action.task, action.company_id, action.status) == (
        "extract_requirements",
        None,
        "succeeded",
    )
