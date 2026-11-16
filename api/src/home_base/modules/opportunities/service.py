"""Opportunity use cases. Other modules read opportunities through here."""

import uuid

from sqlalchemy.orm import Session

from home_base.core.context import Clock
from home_base.modules.audit.domain import Actor, AuditEntry
from home_base.modules.audit.repository import AuditRepository
from home_base.modules.opportunities import rules
from home_base.modules.opportunities.domain import ReloadOutcome
from home_base.modules.opportunities.repository import (
    OpportunityRepository,
    ReloadSummary,
    StoredOpportunity,
)
from home_base.modules.opportunities.seed import SeedOpportunity, check_unique_names

__all__ = [
    "ReloadSummary",
    "StoredOpportunity",
    "current_opportunities",
    "reload",
    "removed_opportunities",
]


def current_opportunities(session: Session) -> list[StoredOpportunity]:
    """Every opportunity not archived (D-46), with its requirement and question IDs."""
    return OpportunityRepository(session).current()


def removed_opportunities(session: Session) -> list[StoredOpportunity]:
    """Opportunities removed from the seed set, as they last were (D-73)."""
    return OpportunityRepository(session).removed()


def reload(
    session: Session, records: list[SeedOpportunity], clock: Clock
) -> tuple[ReloadSummary, list[uuid.UUID]]:
    """Make the opportunity tables match the seed files (D-46) and log each change
    (FRS-06), as the system. Returns the summary and the opportunities whose matches
    must be recalculated; the caller recalculates them in the same transaction."""
    check_unique_names(records)
    summary = OpportunityRepository(session).reload(records, clock.at)
    audit = AuditRepository(session, None)
    to_recalculate: list[uuid.UUID] = []
    for outcome, keys in (
        (ReloadOutcome.ADDED, summary.added),
        (ReloadOutcome.CHANGED, summary.changed),
        (ReloadOutcome.UNCHANGED, summary.unchanged),
        (ReloadOutcome.ARCHIVED, summary.archived),
    ):
        effects = rules.reload_effects(outcome)
        for key in keys:
            if effects.audit:
                audit.record(
                    AuditEntry(
                        actor=Actor.SYSTEM,
                        action=f"opportunity.{outcome.value}",
                        entity="opportunity",
                        entity_id=summary.ids[key],
                        occurred_at=clock.at,
                        after={"seed_key": key},
                        request_id=clock.request_id,
                    )
                )
            if effects.recalculate:
                to_recalculate.append(summary.ids[key])
    return summary, to_recalculate
