"""Week 1 demo: run the rules over the seed data and print Today for a sample company.

Only glue: every status, fit, task and order comes from the rules in api/src. Nothing
is written anywhere. Run from api/ with `uv run python ../scripts/demo_today.py`, or
`make demo` for the fictional fixtures.

The real seed set (api/seed/opportunities) is empty until the first five
opportunities are checked by hand (D-12), so `make demo` uses the fictional test
fixtures and says so.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from home_base.config import NEEDS_ATTENTION_COUNT
from home_base.core.dates import days_left, local_today
from home_base.core.errors import DomainError
from home_base.core.vocabulary import Decision, Operator
from home_base.modules.matching.domain import FactSnapshot, HardRequirement, RequirementResult
from home_base.modules.matching.rules import evaluate_requirement, fit_status, later_has_returned
from home_base.modules.opportunities.domain import (
    FreshnessState,
    OpportunityStatus,
    Verification,
    VerificationMethod,
)
from home_base.modules.opportunities.rules import (
    freshness_state,
    last_verified_date,
    opportunity_status,
    upcoming_freshness_state,
    upcoming_is_shown,
)
from home_base.modules.opportunities.seed import Scope, SeedOpportunity, load_seed_dir
from home_base.modules.today.domain import (
    AnswerState,
    Mode,
    OpportunitySnapshot,
    QuestionSnapshot,
    Task,
    TaskType,
)
from home_base.modules.today.rules import (
    applying_tasks,
    next_opening_date,
    preparing_tasks,
    time_estimate_minutes,
    today_mode,
    today_plan,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED = ROOT / "api" / "seed" / "opportunities"
DEFAULT_COMPANY = ROOT / "scripts" / "demo" / "sample-company.yaml"
LIST_OPERATORS = (Operator.ONE_OF, Operator.NOT_ONE_OF)


@dataclass(frozen=True)
class Company:
    name: str
    facts: tuple[FactSnapshot, ...]
    intent_recorded_on: date | None
    decisions: dict[str, Decision]

    @property
    def approved(self) -> frozenset[str]:
        return frozenset(f.key for f in self.facts if f.approved and f.value is not None)


@dataclass(frozen=True)
class Row:
    """One opportunity as the demo prints it, plus its Today snapshot if it is listed."""

    seed: SeedOpportunity
    status: OpportunityStatus
    freshness: FreshnessState | None
    shown: bool
    snapshot: OpportunitySnapshot | None
    few_rules: bool


def load_company(path: Path) -> Company:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    facts = tuple(
        FactSnapshot(key, item.get("value"), bool(item.get("approved")))
        for key, item in (raw.get("facts") or {}).items()
    )
    decisions = {name: Decision(d) for name, d in (raw.get("decisions") or {}).items()}
    return Company(str(raw.get("name", path.stem)), facts, raw.get("intent_recorded_on"), decisions)


def _hard(seed: SeedOpportunity) -> list[HardRequirement]:
    found = []
    for r in seed.requirements:
        if not r.hard or r.fact is None or r.operator is None:
            continue  # soft criteria never change fit (FIT-05)
        value = frozenset(r.value) if r.operator in LIST_OPERATORS else r.value
        found.append(HardRequirement(r.fact, r.operator, value, r.quote))
    return found


def build_row(seed: SeedOpportunity, company: Company, today: date) -> Row:
    status = opportunity_status(seed.opening, seed.expected_month, seed.deadline, today)
    upcoming = status is OpportunityStatus.UPCOMING
    checks = [Verification(seed.verified_on, VerificationMethod.MANUAL)]
    last = last_verified_date(checks, today)
    shown = status is not OpportunityStatus.CLOSED and (
        not upcoming or upcoming_is_shown(seed.opening, seed.expected_month, seed.evidence, today)
    )
    if upcoming:
        freshness = upcoming_freshness_state(last, seed.opening, seed.expected_month, today)
    else:
        freshness = freshness_state(last, seed.deadline, today)

    hard = _hard(seed)
    results = [evaluate_requirement(r, company.facts) for r in hard]
    fit = fit_status(results)
    if not shown:
        return Row(seed, status, freshness, False, None, fit.few_explicit_rules)

    opening = seed.opening or (seed.expected_month.first_day if seed.expected_month else None)
    decision = company.decisions.get(seed.name, Decision.NONE)
    returned = decision is Decision.LATER and later_has_returned(
        seed.deadline, opening if upcoming else None, today, chosen_again_after_return=False
    )
    unknown = frozenset(
        r.fact_key for r, res in zip(hard, results, strict=True) if res is RequirementResult.UNKNOWN
    )
    # No applications in Week 1: a question with no answer yet is still at "missing facts".
    questions = (
        tuple(QuestionSnapshot(AnswerState.MISSING_FACTS, q.required_facts) for q in seed.questions)
        if seed.questions is not None
        else None
    )
    snapshot = OpportunitySnapshot(
        name=seed.name,
        blue_specific=seed.scope is Scope.BLUE_SPECIFIC,
        fit=fit.status,
        decision=decision,
        deadline=seed.deadline,
        application=None,
        source_current=freshness is FreshnessState.CURRENT,
        later_returned=returned,
        unknown_hard_facts=unknown,
        upcoming=upcoming,
        opening=opening if upcoming else None,
        questions=questions,
    )
    return Row(seed, status, freshness, True, snapshot, fit.few_explicit_rules)


def describe(task: Task) -> str:
    """Plain wording for the demo only; in the app the AI words tasks (spec: code decides)."""
    where = f" ({task.opportunity})" if task.opportunity else ""
    match task.type:
        case TaskType.ADD_FACT:
            unlocks = f", unlocks {task.count}" if task.count else ""
            text = f"Add {task.fact}{where}{unlocks}"
        case TaskType.ANSWER_ONE_QUESTION:
            text = f"Answer 1 question: {task.fact}{where}"
        case TaskType.REVIEW_DRAFTS:
            text = f"Review {task.count} draft answers{where}"
        case TaskType.NEXT_ANSWER:
            text = f"Next unapproved answer: question {task.question}{where}"
        case _:
            text = f"{task.type.value.replace('_', ' ').capitalize()}{where}"
    dated = f", date {task.deadline}" if task.deadline else ""
    return f"{text} [{time_estimate_minutes(task.type)} min{dated}]"


def _days(row: Row, today: date) -> str:
    seed = row.seed
    if row.status is OpportunityStatus.UPCOMING:
        if seed.opening is not None:
            return f"opens {seed.opening}"
        month = seed.expected_month
        return f"expected {month.year}-{month.month:02d}" if month else "opening unknown"
    return "rolling" if seed.deadline is None else f"{days_left(seed.deadline, today)} days left"


def render(rows: list[Row], company: Company, today: date, seed_dir: Path) -> str:
    lines = [f"Today for {company.name}, {today} (seed: {seed_dir})", ""]
    lines.append(f"Opportunities ({len(rows)}):")
    for row in rows:
        s, snap = row.seed, row.snapshot
        state = f"{row.status.value}, {row.freshness.value if row.freshness else '-'}"
        if snap is None:
            lines.append(f"  - {s.name}: {state}, hidden")
            continue
        fit = snap.fit.value + (" (few explicit rules)" if row.few_rules else "")
        unknown = f", unknown: {', '.join(sorted(snap.unknown_hard_facts))}"
        lines.append(
            f"  - {s.name}: {state}, {fit}{unknown if snap.unknown_hard_facts else ''}, "
            f"{_days(row, today)}, decision {snap.decision.value}"
        )

    snapshots = [r.snapshot for r in rows if r.snapshot is not None]
    mode = today_mode(snapshots, today)
    if mode is Mode.APPLYING:
        tasks = applying_tasks(snapshots, company.approved, today)
    else:
        tasks = preparing_tasks(snapshots, company.approved, company.intent_recorded_on, today)
    plan = today_plan(tasks)
    lines += ["", f"Mode: {mode.value}"]
    if plan.one_thing is None:
        lines.append("You're all set.")  # PRI-06; PRI-17 adds the next opening in preparing
        if mode is Mode.PREPARING:
            lines.append(f"Next opening: {next_opening_date(snapshots) or 'none known'}")
    else:
        lines.append(f"One thing today: {describe(plan.one_thing)}")
        lines.append(f"Needs attention (up to {NEEDS_ATTENTION_COUNT}):")
        lines += [f"  - {describe(t)}" for t in plan.needs_attention] or ["  (nothing)"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--company", type=Path, default=DEFAULT_COMPANY)
    parser.add_argument("--today", type=date.fromisoformat, help="YYYY-MM-DD; default Lisbon today")
    args = parser.parse_args()
    today: date = args.today or local_today(datetime.now(UTC))
    try:
        seeds = load_seed_dir(args.seed_dir, today)
        company = load_company(args.company)
        if not seeds:
            sys.stdout.write(f"No opportunities in {args.seed_dir}. Nothing to show.\n")
            return 0
        rows = [build_row(s, company, today) for s in seeds]
        sys.stdout.write(render(rows, company, today, args.seed_dir) + "\n")
    except DomainError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
