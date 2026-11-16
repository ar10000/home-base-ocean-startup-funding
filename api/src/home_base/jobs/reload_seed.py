"""Reload the opportunity set from the seed files and recalculate what changed (FRS-06).

Runs as the system on deploy (D-46). One transaction, owned by the caller: the reload,
its audit events and every company's recalculation are saved together or not at all.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from home_base.core.context import Clock
from home_base.modules.companies import service as companies
from home_base.modules.matching import service as matching
from home_base.modules.opportunities import service as opportunities
from home_base.modules.opportunities.seed import SeedOpportunity, load_seed_dir


def reload_seed(
    session: Session, records: list[SeedOpportunity], clock: Clock
) -> opportunities.ReloadSummary:
    summary, changed = opportunities.reload(session, records, clock)
    if changed:
        targets = [o for o in opportunities.current_opportunities(session) if o.id in set(changed)]
        for company_id in companies.company_ids(session):
            inputs = companies.match_inputs(session, company_id)
            matching.recalculate(session, company_id, targets, inputs, clock)
    return summary


def reload_seed_dir(session: Session, directory: Path, clock: Clock) -> opportunities.ReloadSummary:
    """Validate every seed file (the first bad one stops the reload), then reload."""
    return reload_seed(session, load_seed_dir(directory, clock.today), clock)
