"""Draft a call's requirements from its text, for a person to check (D-83, FRS-01).

Reads the call text from a file, retrieves its eligibility passages, extracts the
requirements with every quote checked word for word, and writes a seed draft into
api/seed/drafts/ with verified_on and verified_by empty. Nothing goes live: a draft is
moved to api/seed/opportunities/ only after a hand check (D-12). Local database only
(the AI log); the provider comes from HOME_BASE_AI_PROVIDER.
"""

import argparse
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from home_base.core.context import Clock
from home_base.core.dates import local_today
from home_base.core.db import database_url

API_DIR = Path(__file__).resolve().parent.parent / "api"
DRAFTS = API_DIR / "seed" / "drafts"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", type=Path, help="the call's text, as a UTF-8 file")
    parser.add_argument("--name", required=True)
    parser.add_argument("--funder", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--scope", choices=["blue_specific", "all_sectors"], required=True)
    parser.add_argument("--types", nargs="+", required=True)
    args = parser.parse_args(argv)

    from urllib.parse import urlparse

    url = database_url()
    if urlparse(url).hostname not in LOCAL_HOSTS:
        sys.stderr.write("extract_requirements: refusing a database that is not on localhost\n")
        return 2

    from home_base.ai.runner import AiFailed
    from home_base.ai.settings import provider_from_environment
    from home_base.ai.tasks.extract_requirements import extract, seed_requirement

    text = args.text.read_text(encoding="utf-8")
    now = datetime.now(UTC)
    clock = Clock(at=now, today=local_today(now), request_id=f"extract-{uuid.uuid4()}")
    with Session(create_engine(url)) as session, session.begin():
        try:
            result = extract(session, provider_from_environment(), args.name, text, clock)
        except AiFailed as exc:
            sys.stderr.write(f"extract_requirements: {exc}; see ai_actions {exc.action_id}\n")
            return 1
    draft = {
        "name": args.name,
        "funder": args.funder,
        "scope": args.scope,
        "types": args.types,
        "source_url": args.source_url,
        "retrieved_on": clock.today,
        "verified_on": None,
        "verified_by": None,
        "requirements": [seed_requirement(r) for r in result.value.requirements],
    }
    out = DRAFTS / f"{slug(args.name)}.yaml"
    header = (
        f"# DRAFT, extracted by AI on {clock.today} (ai_actions {result.action_id}).\n"
        "# Not verified by hand (D-12, FRS-01): check every requirement and quote first.\n"
    )
    out.write_text(header + yaml.safe_dump(draft, sort_keys=False, allow_unicode=True), "utf-8")
    sys.stdout.write(f"extract_requirements: {len(draft['requirements'])} requirements -> {out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
