"""Matching data access: stored matches with their inputs, and decision history.

A recalculation adds a match and supersedes the current one, so every past result
can still be explained (handbook section 11). Decisions are a dated history (DEC-01).
Scoped to the session's company; times are passed in.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from home_base.core.repository import TenantRepository
from home_base.core.vocabulary import Decision, FitStatus
from home_base.modules.matching.domain import (
    DecisionChange,
    FitResult,
    NotForUsReason,
    RequirementOutcome,
    RequirementResult,
    StoredMatch,
)
from home_base.modules.matching.models import DecisionRow, MatchRow, RequirementResultRow


class MatchingRepository(TenantRepository):
    # Matches

    def save_match(
        self,
        opportunity_id: uuid.UUID,
        fit: FitResult,
        rule_version: str,
        outcomes: Sequence[RequirementOutcome],
        at: datetime,
    ) -> StoredMatch:
        """Store a new calculation; it supersedes the current match for this opportunity."""
        current = self.session.scalars(
            self.scoped(MatchRow)
            .where(MatchRow.opportunity_id == opportunity_id, MatchRow.superseded_at.is_(None))
            .with_for_update()
        ).one_or_none()
        if current is not None:
            current.superseded_at = at
            self.session.flush()
        match = self.add(
            MatchRow(
                opportunity_id=opportunity_id,
                fit_status=fit.status.value,
                few_explicit_rules=fit.few_explicit_rules,
                rule_version=rule_version,
                calculated_at=at,
            )
        )
        for o in outcomes:
            self.add(
                RequirementResultRow(
                    match_id=match.id,
                    requirement_id=o.requirement_id,
                    result=o.result.value,
                    fact_key=o.fact_key,
                    fact_version_id=o.fact_version_id,
                )
            )
        return self._stored([match])[0]

    def current_matches(self) -> list[StoredMatch]:
        """The current match for every opportunity this company has been matched to."""
        rows = self.session.scalars(
            self.scoped(MatchRow)
            .where(MatchRow.superseded_at.is_(None))
            .order_by(MatchRow.opportunity_id)
        ).all()
        return self._stored(list(rows))

    def match_history(self, opportunity_id: uuid.UUID) -> list[StoredMatch]:
        """Every calculation for one opportunity, oldest first."""
        rows = self.session.scalars(
            self.scoped(MatchRow)
            .where(MatchRow.opportunity_id == opportunity_id)
            .order_by(MatchRow.calculated_at, MatchRow.id)
        ).all()
        return self._stored(list(rows))

    def _stored(self, matches: list[MatchRow]) -> list[StoredMatch]:
        if not matches:
            return []
        results = self.session.scalars(
            self.scoped(RequirementResultRow)
            .where(RequirementResultRow.match_id.in_([m.id for m in matches]))
            .order_by(RequirementResultRow.id)
        ).all()
        by_match: dict[uuid.UUID, list[RequirementOutcome]] = defaultdict(list)
        for r in results:
            by_match[r.match_id].append(
                RequirementOutcome(
                    requirement_id=r.requirement_id,
                    result=RequirementResult(r.result),
                    fact_key=r.fact_key,
                    fact_version_id=r.fact_version_id,
                )
            )
        return [
            StoredMatch(
                id=m.id,
                opportunity_id=m.opportunity_id,
                fit=FitResult(FitStatus(m.fit_status), m.few_explicit_rules),
                rule_version=m.rule_version,
                calculated_at=m.calculated_at,
                superseded_at=m.superseded_at,
                outcomes=tuple(by_match[m.id]),
            )
            for m in matches
        ]

    # Decisions

    def add_decision(self, opportunity_id: uuid.UUID, change: DecisionChange) -> uuid.UUID:
        row = self.add(
            DecisionRow(
                opportunity_id=opportunity_id,
                decision=change.decision.value,
                reason=change.reason.value if change.reason else None,
                changed_at=change.changed_at,
            )
        )
        return row.id

    def decision_history(self, opportunity_id: uuid.UUID) -> list[DecisionChange]:
        """Every decision change for one opportunity, oldest first."""
        return self.decision_histories().get(opportunity_id, [])

    def decision_histories(self) -> dict[uuid.UUID, list[DecisionChange]]:
        """Every opportunity's decision changes, oldest first; none decided: empty."""
        rows = self.session.scalars(
            self.scoped(DecisionRow).order_by(DecisionRow.changed_at, DecisionRow.id)
        ).all()
        found: dict[uuid.UUID, list[DecisionChange]] = defaultdict(list)
        for r in rows:
            found[r.opportunity_id].append(
                DecisionChange(
                    decision=Decision(r.decision),
                    changed_at=r.changed_at,
                    reason=NotForUsReason(r.reason) if r.reason else None,
                )
            )
        return dict(found)
