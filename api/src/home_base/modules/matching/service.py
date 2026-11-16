"""Matching use cases: recalculate a company's matches (INT-04, FRS-06).

The rules decide; this only gathers their inputs, stores what changed (D-52) and
writes an audit event for each change in the caller's transaction. Inputs come in
as arguments, so matching never reads another module's tables.
"""

import hashlib
import inspect
import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from home_base import config
from home_base.core import vocabulary
from home_base.core.context import Caller, Clock
from home_base.core.vocabulary import Decision
from home_base.modules.audit.domain import Actor, AuditEntry
from home_base.modules.audit.repository import AuditRepository
from home_base.modules.matching import domain, rules
from home_base.modules.matching.domain import (
    DecisionChange,
    FactSnapshot,
    FitResult,
    HardRequirement,
    MatchChange,
    MatchInputs,
    NotForUsReason,
    RequirementOutcome,
    RequirementResult,
    StoredMatch,
)
from home_base.modules.matching.repository import MatchingRepository
from home_base.modules.opportunities.service import StoredOpportunity


def _fingerprint() -> str:
    """D-55: changes exactly when the matching rules, their vocabulary or config change."""
    digest = hashlib.sha256()
    for module in (rules, domain, vocabulary, config):
        digest.update(inspect.getsource(module).encode())
    return "fit-" + digest.hexdigest()[:16]


RULE_VERSION = _fingerprint()


def _rule_value(value: Any) -> Any:
    """A seed rule value as matching compares it: a list becomes a set of strings."""
    return frozenset(str(v) for v in value) if isinstance(value, list) else value


def evaluate(
    opportunity: StoredOpportunity, inputs: MatchInputs, today: date
) -> tuple[FitResult, tuple[RequirementOutcome, ...]]:
    """One opportunity's fit and per-requirement outcomes, with the inputs each read."""
    facts = [FactSnapshot(f.key, f.value, f.approved) for f in inputs.facts]
    age = rules.founder_age_fact(inputs.approved_birth_date, opportunity.record.deadline, today)
    if age is not None:
        facts.append(age)
    versions = {f.key: f.version_id for f in inputs.facts}
    outcomes: list[RequirementOutcome] = []
    for requirement_id, req in zip(
        opportunity.requirement_ids, opportunity.record.requirements, strict=True
    ):
        if req.hard and req.fact is not None and req.operator is not None:
            hard = HardRequirement(req.fact, req.operator, _rule_value(req.value), req.quote)
            result = rules.evaluate_requirement(hard, facts)
            outcomes.append(
                RequirementOutcome(requirement_id, result, req.fact, versions.get(req.fact))
            )
        else:
            outcomes.append(RequirementOutcome(requirement_id, RequirementResult.AI_JUDGEMENT))
    fit = rules.fit_status([o.result for o in outcomes])
    return fit, tuple(outcomes)


def recalculate(
    session: Session,
    company_id: uuid.UUID,
    opportunities: Sequence[StoredOpportunity],
    inputs: MatchInputs,
    clock: Clock,
) -> list[MatchChange]:
    """Recalculate the company's match with each opportunity; store only what changed."""
    repo = MatchingRepository(session, company_id)
    audit = AuditRepository(session, company_id)
    current = {m.opportunity_id: m for m in repo.current_matches()}
    changes: list[MatchChange] = []
    for opp in opportunities:
        fit, outcomes = evaluate(opp, inputs, clock.today)
        old = current.get(opp.id)
        if not rules.match_changed(old, fit, outcomes, RULE_VERSION):
            continue
        repo.save_match(opp.id, fit, RULE_VERSION, outcomes, clock.at)
        audit.record(
            AuditEntry(
                actor=Actor.SYSTEM,
                action="match.recalculated",
                entity="opportunity",
                entity_id=opp.id,
                occurred_at=clock.at,
                before=_fit_fields(old.fit) if old else None,
                after=_fit_fields(fit),
                rule_version=RULE_VERSION,
                request_id=clock.request_id,
            )
        )
        changes.append(MatchChange(opp.id, old.fit if old else None, fit))
    return changes


def _fit_fields(fit: FitResult) -> dict[str, object]:
    return {"fit_status": fit.status.value, "few_explicit_rules": fit.few_explicit_rules}


def current_matches(session: Session, company_id: uuid.UUID) -> list[StoredMatch]:
    """The company's current match per opportunity (how other modules read matches)."""
    return MatchingRepository(session, company_id).current_matches()


def not_eligible_opportunities(session: Session, company_id: uuid.UUID) -> frozenset[uuid.UUID]:
    """Opportunities whose current match makes an open application no longer eligible
    (INT-04, calculated, D-53)."""
    return frozenset(
        m.opportunity_id
        for m in current_matches(session, company_id)
        if rules.no_longer_eligible(m.fit.status)
    )


# Decisions (DEC-01, DEC-02)


def current_decision(
    session: Session, company_id: uuid.UUID, opportunity_id: uuid.UUID
) -> Decision:
    history = MatchingRepository(session, company_id).decision_history(opportunity_id)
    return rules.current_decision(history)


def change_decision(
    session: Session,
    caller: Caller,
    opportunity_id: uuid.UUID,
    decision: tuple[Decision, NotForUsReason | None],
    clock: Clock,
) -> Decision:
    """Record the founder's decision (DEC-01: dated, logged, any can be changed). Choosing
    the current decision again, with the same reason, writes nothing."""
    choice, reason = decision
    repo = MatchingRepository(session, caller.company_id)
    history = repo.decision_history(opportunity_id)
    change = rules.decision_change(choice, clock.at, reason)
    last = history[-1] if history else None
    if last is not None and (last.decision, last.reason) == (choice, reason):
        return choice
    if last is None and choice is Decision.NONE:
        return choice
    repo.add_decision(opportunity_id, change)
    AuditRepository(session, caller.company_id).record(
        AuditEntry(
            actor=Actor.FOUNDER,
            actor_id=caller.user_id,
            action="decision.changed",
            entity="opportunity",
            entity_id=opportunity_id,
            occurred_at=clock.at,
            before={"decision": rules.current_decision(history).value},
            after={"decision": choice.value, "reason": reason.value if reason else None},
            request_id=clock.request_id,
        )
    )
    return choice


def decide_on_application_start(
    session: Session, caller: Caller, opportunity_id: uuid.UUID, clock: Clock
) -> Decision:
    """DEC-02: starting an application sets Pursuing."""
    current = current_decision(session, caller.company_id, opportunity_id)
    return change_decision(
        session, caller, opportunity_id, (rules.decision_on_application_start(current), None), clock
    )


def current_decisions(session: Session, company_id: uuid.UUID) -> dict[uuid.UUID, Decision]:
    """The current decision per opportunity the company has decided on."""
    histories = MatchingRepository(session, company_id).decision_histories()
    return {opp: rules.current_decision(changes) for opp, changes in histories.items()}


def decision_histories(
    session: Session, company_id: uuid.UUID
) -> dict[uuid.UUID, list[DecisionChange]]:
    """Every opportunity's decision changes, oldest first."""
    return MatchingRepository(session, company_id).decision_histories()
