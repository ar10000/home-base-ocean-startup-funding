"""Company data access: fact versions, founder facts and intent history (D-47 to D-51).

Every method is scoped to the session's company (TenantRepository). Times are passed
in by the caller, never read from a clock here (architecture rule 10).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import delete, select

from home_base.core.errors import FactError, TenantError
from home_base.core.repository import TenantRepository
from home_base.modules.companies.domain import (
    FactLabel,
    FactValue,
    FactVersion,
    FounderFact,
    Goal,
    GoalChoice,
    IntentRecord,
    Window,
)
from home_base.modules.companies.models import (
    FOUNDER_FACT_TYPES,
    CompanyFactRow,
    CompanyRow,
    FactDefinitionRow,
    FounderFactRow,
    IntentGoalRow,
    IntentRow,
)


def _value_type(value: FactValue) -> str:
    if isinstance(value, bool):  # before int: bool is an int in Python
        return "boolean"
    if isinstance(value, int):
        return "integer"
    return "text"


def _value(row: CompanyFactRow) -> FactValue:
    value = {"text": row.value_text, "integer": row.value_integer, "boolean": row.value_boolean}[
        row.value_type
    ]
    assert value is not None  # the value_matches_type check guarantees it
    return value


def _version(row: CompanyFactRow) -> FactVersion:
    return FactVersion(
        id=row.id,
        key=row.key,
        value=_value(row),
        label=FactLabel(row.label),
        source=row.source,
        recorded_at=row.created_at,
        approved_at=row.approved_at,
        approved_by=row.approved_by,
        superseded_at=row.superseded_at,
    )


class CompanyRepository(TenantRepository):
    # The journey stage (D-78), on the company row itself (row-level security: own row only)

    def stage(self) -> str | None:
        row = self.session.get(CompanyRow, self.company_id)
        return row.stage if row else None

    def set_stage(self, stage: str, at: datetime) -> None:
        row = self.session.get(CompanyRow, self.company_id)
        if row is None:
            raise TenantError("no such company")
        row.stage, row.updated_at = stage, at
        self.session.flush()

    # Company facts (D-47, D-49, D-50)

    def current_facts(self) -> list[FactVersion]:
        """The current version of every fact the company has, by key."""
        rows = self.session.scalars(
            self.scoped(CompanyFactRow)
            .where(CompanyFactRow.superseded_at.is_(None))
            .order_by(CompanyFactRow.key)
        ).all()
        return [_version(r) for r in rows]

    def fact_history(self, key: str) -> list[FactVersion]:
        """Every version of one fact, oldest first."""
        rows = self.session.scalars(
            self.scoped(CompanyFactRow)
            .where(CompanyFactRow.key == key)
            .order_by(CompanyFactRow.created_at, CompanyFactRow.id)
        ).all()
        return [_version(r) for r in rows]

    def add_fact_version(
        self, key: str, value: FactValue, label: FactLabel, source: str | None, at: datetime
    ) -> FactVersion:
        """Record a new value: it supersedes the current version and is unapproved (D-49)."""
        definition = self.session.scalars(
            select(FactDefinitionRow).where(FactDefinitionRow.key == key)
        ).one_or_none()
        if definition is None:
            raise FactError(f"unknown fact {key!r}")
        value_type = _value_type(value)
        if value_type != definition.value_type:
            raise FactError(f"{key!r} takes a {definition.value_type} value, not {value_type}")
        current = self.session.scalars(
            self.scoped(CompanyFactRow)
            .where(CompanyFactRow.key == key, CompanyFactRow.superseded_at.is_(None))
            .with_for_update()
        ).one_or_none()
        if current is not None:
            current.superseded_at = at
            self.session.flush()
        row = CompanyFactRow(
            key=key,
            value_type=value_type,
            value_text=value if value_type == "text" else None,
            value_integer=value if value_type == "integer" else None,
            value_boolean=value if value_type == "boolean" else None,
            label=label.value,
            source=source,
            created_at=at,
            updated_at=at,
        )
        return _version(self.add(row))

    def fact_version(self, version_id: uuid.UUID) -> FactVersion | None:
        """One of this company's fact versions, or None."""
        row = self.get(CompanyFactRow, version_id)
        return _version(row) if row else None

    def approve_fact(self, version_id: uuid.UUID, by: uuid.UUID, at: datetime) -> FactVersion:
        """Approve the current version of a fact; approving it again changes nothing."""
        row = self.get(CompanyFactRow, version_id)
        if row is None:
            raise FactError("no such fact version")
        if row.superseded_at is not None:
            raise FactError("only the current version of a fact can be approved")
        if row.approved_at is None:
            row.approved_at, row.approved_by = at, by
            self.session.flush()
        return _version(row)

    # Founder facts (D-44, D-51): no history; deleted for real

    def founder_facts(self) -> list[FounderFact]:
        rows = self.session.scalars(self.scoped(FounderFactRow).order_by(FounderFactRow.key)).all()
        return [_founder_fact(r) for r in rows]

    def set_founder_fact(self, key: str, value: date | bool, at: datetime) -> FounderFact:
        """Set a founder fact's value; a new value needs approving again (D-49)."""
        expected = FOUNDER_FACT_TYPES.get(key)
        if expected is None:
            raise FactError(f"unknown founder fact {key!r}")
        given = "boolean" if isinstance(value, bool) else "date"
        if given != expected:
            raise FactError(f"{key!r} takes a {expected} value, not {given}")
        value_date = value if isinstance(value, date) and not isinstance(value, bool) else None
        value_boolean = value if isinstance(value, bool) else None
        row = self._founder_row(key)
        if row is None:
            row = self.add(
                FounderFactRow(
                    key=key,
                    value_date=value_date,
                    value_boolean=value_boolean,
                    created_at=at,
                    updated_at=at,
                )
            )
        else:
            row.value_date, row.value_boolean = value_date, value_boolean
            row.approved_at = row.approved_by = None
            row.updated_at = at
            self.session.flush()
        return _founder_fact(row)

    def approve_founder_fact(self, key: str, by: uuid.UUID, at: datetime) -> FounderFact:
        row = self._founder_row(key)
        if row is None:
            raise FactError(f"no founder fact {key!r}")
        if row.approved_at is None:
            row.approved_at, row.approved_by = at, by
            self.session.flush()
        return _founder_fact(row)

    def delete_founder_fact(self, key: str) -> bool:
        """Delete a founder fact entirely; False when there was none."""
        result = self.session.execute(
            delete(FounderFactRow).where(
                FounderFactRow.company_id == self.company_id, FounderFactRow.key == key
            )
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    def _founder_row(self, key: str) -> FounderFactRow | None:
        return self.session.scalars(
            self.scoped(FounderFactRow).where(FounderFactRow.key == key)
        ).one_or_none()

    # Intent (INT-01, INT-02): every change adds a dated record

    def add_intent(self, record: IntentRecord) -> uuid.UUID:
        intent = self.add(IntentRow(recorded_at=record.recorded_at))
        for choice in record.goals:
            self.add(
                IntentGoalRow(
                    intent_id=intent.id, goal=choice.goal.value, goal_window=choice.window.value
                )
            )
        return intent.id

    def intents(self) -> list[IntentRecord]:
        """Every intent record, oldest first, with its goals in the fixed list's order."""
        intents = self.session.scalars(
            self.scoped(IntentRow).order_by(IntentRow.recorded_at, IntentRow.id)
        ).all()
        goals = self.session.scalars(self.scoped(IntentGoalRow)).all()
        order = list(Goal)
        by_intent: dict[uuid.UUID, list[GoalChoice]] = {}
        for g in goals:
            by_intent.setdefault(g.intent_id, []).append(
                GoalChoice(Goal(g.goal), Window(g.goal_window))
            )
        return [
            IntentRecord(
                goals=tuple(sorted(by_intent.get(i.id, []), key=lambda c: order.index(c.goal))),
                recorded_at=i.recorded_at,
            )
            for i in intents
        ]


def _founder_fact(row: FounderFactRow) -> FounderFact:
    value: date | bool | None = row.value_date if row.value_date is not None else row.value_boolean
    assert value is not None  # the value_matches_key check guarantees it
    return FounderFact(key=row.key, value=value, approved_at=row.approved_at)
