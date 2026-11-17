"""Run the evaluation sets (handbook section 10) and compare with the thresholds.

Runs every case RUNS times with fresh answers, and judges the thresholds on the worst
run. Uses the provider from HOME_BASE_AI_PROVIDER (mistral for a real run) and the local
database for the AI log. Writes results/<task>-<prompt>-<model>.json so each change
shows its before and after. Exits 1 when a measure is below its threshold.
"""

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from home_base.core.context import Clock
from home_base.core.dates import local_today
from home_base.core.db import database_url

EVALS = Path(__file__).resolve().parent.parent / "api" / "tests" / "evals"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
RUNS = 3  # each run costs about 0.006 EUR on Claude Haiku 5.5 (D-84)


def main() -> int:
    url = database_url()
    if urlparse(url).hostname not in LOCAL_HOSTS:
        sys.stderr.write("run_evals: refusing a database that is not on localhost\n")
        return 2

    from home_base.ai import evals
    from home_base.ai.settings import provider_from_environment
    from home_base.ai.tasks import extract_requirements

    provider = provider_from_environment()
    prompt = extract_requirements.prompt()
    now = datetime.now(UTC)
    clock = Clock(at=now, today=local_today(now), request_id=f"evals-{uuid.uuid4()}")
    cases = evals.load_cases(EVALS / "extraction")
    runs: list[dict[str, Any]] = []
    failures_by_run: list[list[str]] = []
    for n in range(1, RUNS + 1):  # fresh answers each time: the model's output varies
        with Session(create_engine(url)) as session, session.begin():
            total, lines = evals.evaluate_extraction(session, provider, cases, clock)
        failures_by_run.append(evals.below_thresholds(total))
        runs.append(
            {
                "run": n,
                "recall": round(total.recall, 3),
                "precision": round(total.precision, 3),
                "quotes_verbatim": round(total.verbatim, 3),
                "below_thresholds": failures_by_run[-1],
                "lines": lines,
            }
        )
        sys.stdout.write(
            f"run {n}: recall {total.recall:.0%}, precision {total.precision:.0%}, "
            f"quotes verbatim {total.verbatim:.0%}\n"
        )
        for line in lines:
            sys.stdout.write(f"  {line}\n")
    # Judged on the worst run: a threshold met only sometimes is not met.
    failures = sorted({f for run in failures_by_run for f in run})
    model = provider.name.removeprefix("anthropic:")  # fake, mistral or the Claude model
    report = {
        "task": prompt.task,
        "prompt": prompt.label,
        "model": model,
        "run_on": now.isoformat(timespec="seconds"),
        "cases": len(cases),
        "runs": runs,
        "below_thresholds_in_any_run": failures,
    }
    results = EVALS / "results"
    results.mkdir(exist_ok=True)
    name = f"{prompt.task}-v{prompt.version}-{model}.json"
    (results / name).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(f"-> {results / name}\n")
    for failure in failures:
        sys.stdout.write(f"  BELOW THRESHOLD in at least one run: {failure}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
