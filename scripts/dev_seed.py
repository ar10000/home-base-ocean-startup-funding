"""Load fictional opportunities into the local database, for `make dev`.

Reads the seed files from --seed-dir (default: the fictional test fixtures, since the
real seed set waits for Andrew's checks, D-12) and reloads them as the deploy job does
(D-46). Refuses any database that is not on localhost, so it never touches a hosted one.
"""

import argparse
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from home_base.core.context import Clock
from home_base.core.dates import local_today
from home_base.core.db import database_url

API_DIR = Path(__file__).resolve().parent.parent / "api"
DEFAULT_SEED = API_DIR / "tests" / "fixtures" / "seed"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_local(url: str) -> bool:
    """True only for a database on this machine."""
    return urlparse(url).hostname in LOCAL_HOSTS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    url = database_url()
    if not is_local(url):
        sys.stderr.write("dev_seed: refusing a database that is not on localhost\n")
        return 2

    # Imported after the guard: nothing that touches matching or the database loads first.
    from home_base.jobs.reload_seed import reload_seed_dir

    now = datetime.now(UTC)
    clock = Clock(at=now, today=local_today(now), request_id=f"dev-seed-{uuid.uuid4()}")
    with Session(create_engine(url)) as session, session.begin():
        summary = reload_seed_dir(session, args.seed_dir, clock)
    counts = f"added {len(summary.added)}, changed {len(summary.changed)}"
    sys.stdout.write(f"dev_seed: {counts}, archived {len(summary.archived)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
