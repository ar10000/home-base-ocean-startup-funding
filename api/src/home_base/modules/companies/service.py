"""Company use cases: facts, founder facts and intent (INT-01, INT-02, INT-04; D-47 to D-54).

Every change writes its audit event and recalculates the company's matches in the
caller's transaction, so the change, its history and its effect on matches are saved
together or not at all (architecture rule 7). A repeated change that alters nothing
writes nothing. Founder fact events never carry values (D-51).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from home_base.config import STAGES
from home_base.core.context import Caller, Clock
from home_base.core.errors import FactError, StageError
from home_base.modules.audit.domain import Actor, AuditEntry
from home_base.modules.audit.repository import AuditRepository
from home_base.modules.companies import rules
from home_base.modules.companies.domain import (
    FactLabel,
    FactValue,
    FactVersion,
    FounderFact,
    GoalChoice,
    IntentRecord,
)
from home_base.modules.companies.models import CompanyRow
from home_base.modules.companies.repository import CompanyRepository
from home_base.modules.matching import service as matching
from home_base.modules.matching.domain import FactInput, MatchChange, MatchInputs
from home_base.modules.opportunities.service import current_opportunities


@dataclass(frozen=True, slots=True)
class NewFact:
    key: str
    value: FactValue
    label: FactLabel
    source: str | None = None


def company_ids(session: Session) -> list[uuid.UUID]:
    """Every company not archived: for system jobs that act on all tenants (FRS-06)."""
    return list(
        session.scalars(
            select(CompanyRow.id).where(CompanyRow.archived_at.is_(None)).order_by(CompanyRow.id)
        ).all()
    )


def match_inputs(session: Session, company_id: uuid.UUID) -> MatchInputs:
    """What matching reads for this company: current company facts, the yes/no founder
    facts, and the approved birth date (age is derived per call, D-44)."""
    repo = CompanyRepository(session, company_id)
    facts = [
        FactInput(f.key, f.value, f.approved_at is not None, f.id) for f in repo.current_facts()
    ]
    birth: date | None = None
    for f in repo.founder_facts():
        approved = f.approved_at is not None
        if isinstance(f.value, bool):  # woman founder, woman CEO
            facts.append(FactInput(f.key, f.value, approved))
        elif approved:  # the birth date, the only date-valued founder fact
            birth = f.value
    return MatchInputs(tuple(facts), approved_birth_date=birth)


def current_intent(session: Session, company_id: uuid.UUID) -> IntentRecord | None:
    """The current intent (INT-02), or None when the founder has set none."""
    return rules.current_intent(CompanyRepository(session, company_id).intents())


def recalculate_matches(session: Session, company_id: uuid.UUID, clock: Clock) -> list[MatchChange]:
    """Recalculate every match after a change.

    Rule INT-04: an intent or fact change recalculates every match; nothing is
    deleted. Only what changed is stored (D-52); an intent change alone stores no
    new match (D-54).
    """
    return matching.recalculate(
        session,
        company_id,
        current_opportunities(session),
        match_inputs(session, company_id),
        clock,
    )


# Company facts


def add_fact(session: Session, caller: Caller, fact: NewFact, clock: Clock) -> FactVersion:
    """Record a new value (unapproved, D-49), audit it, and recalculate."""
    if not rules.fact_value_allowed(fact.key, fact.value):
        raise FactError(f"{fact.value!r} is not one of the values for {fact.key}")
    repo = CompanyRepository(session, caller.company_id)
    previous = next((f for f in repo.current_facts() if f.key == fact.key), None)
    version = repo.add_fact_version(fact.key, fact.value, fact.label, fact.source, clock.at)
    _audit(
        session,
        caller,
        clock,
        "fact.added",
        "company_fact",
        version.id,
        before={"key": fact.key, "value": previous.value} if previous else None,
        after={"key": fact.key, "value": fact.value, "label": fact.label.value},
    )
    recalculate_matches(session, caller.company_id, clock)
    return version


def approve_fact(
    session: Session, caller: Caller, version_id: uuid.UUID, clock: Clock
) -> FactVersion:
    """Approve a fact version; approving it again changes and writes nothing."""
    repo = CompanyRepository(session, caller.company_id)
    before = repo.fact_version(version_id)
    version = repo.approve_fact(version_id, caller.user_id, clock.at)
    if before is not None and before.approved_at is None:
        _audit(
            session,
            caller,
            clock,
            "fact.approved",
            "company_fact",
            version.id,
            before={"approved_at": None},
            after={"approved_at": clock.at.isoformat()},
        )
        recalculate_matches(session, caller.company_id, clock)
    return version


# Founder facts (D-44, D-51): events carry no values


def _founder_entity(company_id: uuid.UUID, key: str) -> uuid.UUID:
    """A stable ID per company and founder fact, so its history can be read."""
    return uuid.uuid5(company_id, key)


def set_founder_fact(
    session: Session, caller: Caller, key: str, value: date | bool, clock: Clock
) -> FounderFact:
    repo = CompanyRepository(session, caller.company_id)
    previous = next((f for f in repo.founder_facts() if f.key == key), None)
    fact = repo.set_founder_fact(key, value, clock.at)
    if previous is None or previous.value != value:
        _audit(
            session,
            caller,
            clock,
            "founder_fact.set",
            "founder_fact",
            _founder_entity(caller.company_id, key),
        )
        recalculate_matches(session, caller.company_id, clock)
    return fact


def approve_founder_fact(session: Session, caller: Caller, key: str, clock: Clock) -> FounderFact:
    repo = CompanyRepository(session, caller.company_id)
    previous = next((f for f in repo.founder_facts() if f.key == key), None)
    fact = repo.approve_founder_fact(key, caller.user_id, clock.at)
    if previous is not None and previous.approved_at is None:
        _audit(
            session,
            caller,
            clock,
            "founder_fact.approved",
            "founder_fact",
            _founder_entity(caller.company_id, key),
        )
        recalculate_matches(session, caller.company_id, clock)
    return fact


def delete_founder_fact(session: Session, caller: Caller, key: str, clock: Clock) -> bool:
    """Delete a founder fact entirely (D-51); its rules return to Unknown (REQ-07)."""
    deleted = CompanyRepository(session, caller.company_id).delete_founder_fact(key)
    if deleted:
        _audit(
            session,
            caller,
            clock,
            "founder_fact.deleted",
            "founder_fact",
            _founder_entity(caller.company_id, key),
        )
        recalculate_matches(session, caller.company_id, clock)
    return deleted


# Intent


def set_intent(
    session: Session, caller: Caller, goals: Sequence[GoalChoice], clock: Clock
) -> IntentRecord:
    """Add a dated intent record (INT-01, INT-02), audit it, and recalculate (D-54)."""
    record = rules.intent_record(goals, clock.at)
    intent_id = CompanyRepository(session, caller.company_id).add_intent(record)
    _audit(
        session,
        caller,
        clock,
        "intent.changed",
        "intent",
        intent_id,
        after={"goals": [[g.goal.value, g.window.value] for g in record.goals]},
    )
    recalculate_matches(session, caller.company_id, clock)
    return record


def stage(session: Session, company_id: uuid.UUID) -> str | None:
    """The company's journey stage (D-78), or None until the founder chooses one."""
    return CompanyRepository(session, company_id).stage()


def set_stage(session: Session, caller: Caller, stage: str, clock: Clock) -> None:
    """Set the journey stage the founder chose (spec: Today > Stage; D-78), audited.
    Choosing the current stage again writes nothing."""
    if stage not in {k for k, _ in STAGES}:
        raise StageError(f"{stage!r} is not one of the stages")
    repo = CompanyRepository(session, caller.company_id)
    before = repo.stage()
    if before == stage:
        return
    repo.set_stage(stage, clock.at)
    _audit(
        session,
        caller,
        clock,
        "company.stage_changed",
        "company",
        caller.company_id,
        before={"stage": before},
        after={"stage": stage},
    )


def _audit(  # noqa: PLR0913  (an audit entry has this many parts)
    session: Session,
    caller: Caller,
    clock: Clock,
    action: str,
    entity: str,
    entity_id: uuid.UUID,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
) -> None:
    AuditRepository(session, caller.company_id).record(
        AuditEntry(
            actor=Actor.FOUNDER,
            actor_id=caller.user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            occurred_at=clock.at,
            before=before,
            after=after,
            request_id=clock.request_id,
        )
    )
