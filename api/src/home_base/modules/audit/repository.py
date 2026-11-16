"""Audit trail access: append an entry, read a record's history (handbook section 12).

Append-only: there is no update or delete here. An entry belongs to the session's
company, or to no company for shared records such as opportunities; a history shows
the company's own entries and the shared ones, never another company's.
"""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from home_base.core.errors import AuditError
from home_base.modules.audit.domain import VALUE_FREE_ENTITIES, Actor, AuditEntry
from home_base.modules.audit.models import AuditEvent


class AuditRepository:
    def __init__(self, session: Session, company_id: uuid.UUID | None) -> None:
        self.session = session
        self.company_id = company_id  # None: a change to a shared record, by system or job

    def record(self, entry: AuditEntry) -> uuid.UUID:
        """Stage one entry in the caller's transaction; returns its ID."""
        if entry.entity in VALUE_FREE_ENTITIES and (entry.before or entry.after):
            raise AuditError(f"{entry.entity} entries never carry values (D-51)")
        if (entry.actor is Actor.FOUNDER) != (entry.actor_id is not None):
            raise AuditError("a founder entry names the founder; system and job entries don't")
        row = AuditEvent(
            actor=entry.actor.value,
            actor_id=entry.actor_id,
            company_id=self.company_id,
            action=entry.action,
            entity=entry.entity,
            entity_id=entry.entity_id,
            before=entry.before,
            after=entry.after,
            rule_version=entry.rule_version,
            request_id=entry.request_id,
            occurred_at=entry.occurred_at,
        )
        self.session.add(row)
        self.session.flush()
        return row.id

    def history(self, entity: str, entity_id: uuid.UUID) -> list[AuditEntry]:
        """A record's entries, oldest first: this company's and shared ones."""
        visible = (
            AuditEvent.company_id.is_(None)
            if self.company_id is None
            else or_(AuditEvent.company_id == self.company_id, AuditEvent.company_id.is_(None))
        )
        rows = self.session.scalars(
            select(AuditEvent)
            .where(AuditEvent.entity == entity, AuditEvent.entity_id == entity_id, visible)
            .order_by(AuditEvent.occurred_at, AuditEvent.id)
        ).all()
        return [
            AuditEntry(
                actor=Actor(r.actor),
                action=r.action,
                entity=r.entity,
                entity_id=r.entity_id,
                occurred_at=r.occurred_at,
                actor_id=r.actor_id,
                before=r.before,
                after=r.after,
                rule_version=r.rule_version,
                request_id=r.request_id,
            )
            for r in rows
        ]
