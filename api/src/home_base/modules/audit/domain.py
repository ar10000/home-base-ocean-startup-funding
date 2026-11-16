"""Audit vocabulary (handbook section 12): one entry per state change."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class Actor(StrEnum):
    """Who made a change."""

    FOUNDER = "founder"
    SYSTEM = "system"
    JOB = "job"


# Entities whose values are personal data: their audit entries record that a change
# happened, never the values (decision D-51).
VALUE_FREE_ENTITIES = frozenset({"founder_fact"})


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One state change: who changed what, when, from what to what (changed fields only)."""

    actor: Actor
    action: str
    entity: str
    entity_id: uuid.UUID
    occurred_at: datetime
    actor_id: uuid.UUID | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    rule_version: str | None = None
    request_id: str | None = None
