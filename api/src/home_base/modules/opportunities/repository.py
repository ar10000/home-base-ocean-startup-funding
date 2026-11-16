"""Opportunity data access: reload from the seed files, read the current set (D-46).

Opportunities are shared records (no company), so this does not use TenantRepository.
The seed files are the source of truth: `reload` makes the tables match them. Nothing
is deleted: replaced child rows and opportunities whose file is gone get `archived_at`.
Times are passed in by the caller.
"""

import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from home_base.core.vocabulary import Operator, OpportunityType
from home_base.modules.opportunities.domain import Evidence, EvidenceKind, Month
from home_base.modules.opportunities.models import (
    EvidenceRow,
    OpportunityRow,
    QuestionRow,
    RequirementRow,
    SourceRow,
)
from home_base.modules.opportunities.seed import (
    Scope,
    SeedOpportunity,
    SeedQuestion,
    SeedRequirement,
)

Child = TypeVar("Child", SourceRow, RequirementRow, QuestionRow, EvidenceRow)
CHILDREN = (SourceRow, RequirementRow, QuestionRow, EvidenceRow)


@dataclass(frozen=True, slots=True)
class StoredOpportunity:
    """A current opportunity with the IDs matching and applications refer to."""

    id: uuid.UUID
    record: SeedOpportunity
    requirement_ids: tuple[uuid.UUID, ...]  # in the record's requirement order
    question_ids: tuple[uuid.UUID, ...]  # in the record's question order


@dataclass(slots=True)
class ReloadSummary:
    """What a reload changed, by seed key, for the audit trail."""

    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)
    ids: dict[str, uuid.UUID] = field(default_factory=dict)  # every key above, by seed key


def _seed_key(record: SeedOpportunity) -> str:
    return Path(record.source).stem


def _evidence_order(e: Evidence) -> tuple[date, str, str]:
    return (e.dated, e.kind.value, e.source_url)


def _canonical(record: SeedOpportunity) -> SeedOpportunity:
    """The record with evidence in a fixed order, so file order is not a change."""
    return replace(record, evidence=tuple(sorted(record.evidence, key=_evidence_order)))


class OpportunityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def current(self) -> list[StoredOpportunity]:
        """Every opportunity not archived, by seed key."""
        rows = self.session.scalars(
            select(OpportunityRow)
            .where(OpportunityRow.archived_at.is_(None))
            .order_by(OpportunityRow.seed_key)
        ).all()
        return [self._stored(r) for r in rows]

    def removed(self) -> list[StoredOpportunity]:
        """Opportunities whose seed file was removed (D-46), as they last were: with the
        child rows archived together with them (D-73)."""
        rows = self.session.scalars(
            select(OpportunityRow)
            .where(OpportunityRow.archived_at.is_not(None))
            .order_by(OpportunityRow.seed_key)
        ).all()
        return [self._stored(r, as_archived=True) for r in rows]

    def reload(self, records: list[SeedOpportunity], at: datetime) -> ReloadSummary:
        """Make the tables match the seed files; returns what changed."""
        summary = ReloadSummary()
        by_key = {_seed_key(r): r for r in records}
        existing = {
            r.seed_key: r
            for r in self.session.scalars(select(OpportunityRow).with_for_update()).all()
        }
        for key in sorted(by_key):
            record = by_key[key]
            row = existing.get(key)
            if row is None:
                summary.ids[key] = self._insert(record, at)
                summary.added.append(key)
                continue
            summary.ids[key] = row.id
            if row.archived_at is None and self._stored(row).record == _canonical(record):
                summary.unchanged.append(key)
            else:
                self._replace(row, record, at)
                summary.changed.append(key)
        for key, row in sorted(existing.items()):
            if key not in by_key and row.archived_at is None:
                row.archived_at = at
                self._archive_children(row.id, at)
                summary.archived.append(key)
                summary.ids[key] = row.id
        self.session.flush()
        return summary

    # Writing

    def _insert(self, record: SeedOpportunity, at: datetime) -> uuid.UUID:
        row = OpportunityRow(seed_key=_seed_key(record), created_at=at, updated_at=at)
        self._set_fields(row, record)
        self.session.add(row)
        self.session.flush()
        self._insert_children(row.id, record, at)
        return row.id

    def _replace(self, row: OpportunityRow, record: SeedOpportunity, at: datetime) -> None:
        self._archive_children(row.id, at)
        self._set_fields(row, record)
        row.archived_at = None  # a file that comes back makes the opportunity current again
        row.updated_at = at
        self._insert_children(row.id, record, at)

    @staticmethod
    def _set_fields(row: OpportunityRow, r: SeedOpportunity) -> None:
        row.name, row.funder, row.scope = r.name, r.funder, r.scope.value
        row.types = sorted(t.value for t in r.types)
        row.deadline, row.opening = r.deadline, r.opening
        row.timezone = r.timezone.key if r.timezone else None
        row.expected_month = (
            date(r.expected_month.year, r.expected_month.month, 1) if r.expected_month else None
        )
        row.questions_known = r.questions is not None

    def _insert_children(self, opp_id: uuid.UUID, r: SeedOpportunity, at: datetime) -> None:
        stamp = {"opportunity_id": opp_id, "created_at": at, "updated_at": at}
        self.session.add(
            SourceRow(
                url=r.source_url,
                retrieved_on=r.retrieved_on,
                verified_on=r.verified_on,
                verified_by=r.verified_by,
                **stamp,
            )
        )
        for i, q in enumerate(r.requirements):
            self.session.add(
                RequirementRow(
                    position=i,
                    hard=q.hard,
                    quote=q.quote,
                    fact=q.fact,
                    operator=q.operator.value if q.operator else None,
                    value=q.value,
                    criterion=q.criterion,
                    **stamp,
                )
            )
        for i, question in enumerate(r.questions or ()):
            self.session.add(
                QuestionRow(
                    position=i,
                    text=question.text,
                    required_facts=sorted(question.required_facts),
                    **stamp,
                )
            )
        for e in r.evidence:
            self.session.add(
                EvidenceRow(kind=e.kind.value, dated=e.dated, url=e.source_url, **stamp)
            )
        self.session.flush()

    def _archive_children(self, opp_id: uuid.UUID, at: datetime) -> None:
        for model in CHILDREN:
            self.session.execute(
                update(model)
                .where(model.opportunity_id == opp_id, model.archived_at.is_(None))
                .values(archived_at=at)
            )

    # Reading

    def _children(
        self, model: type[Child], opp_id: uuid.UUID, archived_at: datetime | None = None
    ) -> list[Child]:
        """Child rows in insertion order (UUIDv7 IDs sort by time): the current ones, or
        with `archived_at` those archived at that moment (a removed opportunity's last)."""
        state = (
            model.archived_at.is_(None) if archived_at is None else model.archived_at == archived_at
        )
        query = select(model).where(model.opportunity_id == opp_id, state).order_by(model.id)
        return list(self.session.scalars(query).all())

    def _stored(self, row: OpportunityRow, *, as_archived: bool = False) -> StoredOpportunity:
        at = row.archived_at if as_archived else None
        (source,) = self._children(SourceRow, row.id, at)
        reqs = sorted(self._children(RequirementRow, row.id, at), key=lambda q: q.position)
        questions = sorted(self._children(QuestionRow, row.id, at), key=lambda q: q.position)
        evidence = self._children(EvidenceRow, row.id, at)
        month = row.expected_month
        record = SeedOpportunity(
            source=f"{row.seed_key}.yaml",
            name=row.name,
            funder=row.funder,
            scope=Scope(row.scope),
            types=frozenset(OpportunityType(t) for t in row.types),
            source_url=source.url,
            retrieved_on=source.retrieved_on,
            verified_on=source.verified_on,
            verified_by=source.verified_by,
            deadline=row.deadline,
            timezone=ZoneInfo(row.timezone) if row.timezone else None,
            opening=row.opening,
            expected_month=Month(month.year, month.month) if month else None,
            evidence=tuple(
                sorted(
                    (Evidence(EvidenceKind(e.kind), e.dated, e.url) for e in evidence),
                    key=_evidence_order,
                )
            ),
            requirements=tuple(
                SeedRequirement(
                    hard=q.hard,
                    quote=q.quote,
                    fact=q.fact,
                    operator=Operator(q.operator) if q.operator else None,
                    value=q.value,
                    criterion=q.criterion,
                )
                for q in reqs
            ),
            questions=(
                tuple(SeedQuestion(q.text, frozenset(q.required_facts)) for q in questions)
                if row.questions_known
                else None
            ),
        )
        return StoredOpportunity(
            id=row.id,
            record=record,
            requirement_ids=tuple(q.id for q in reqs),
            question_ids=tuple(q.id for q in questions),
        )
