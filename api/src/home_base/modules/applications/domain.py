"""Application vocabulary: applications, answers and answer versions as stored."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from home_base.modules.today.domain import AnswerState


class VersionKind(StrEnum):
    """A saved answer version: an AI draft or redraft, or the founder's approval."""

    AI_DRAFT = "ai_draft"
    APPROVED = "approved"


@dataclass(frozen=True, slots=True)
class Draft:
    """An AI draft or redraft to store: its text, the AI call, the fact versions it used."""

    text: str
    ai_action_id: uuid.UUID
    fact_version_ids: frozenset[uuid.UUID]


@dataclass(frozen=True, slots=True)
class Answer:
    """The current answer to one question: its state and autosaved text."""

    question_id: uuid.UUID
    state: AnswerState
    text: str


@dataclass(frozen=True, slots=True)
class AnswerVersion:
    """One saved version, with the AI call or approver behind it and the facts it used."""

    id: uuid.UUID
    kind: VersionKind
    text: str
    saved_at: datetime
    ai_action_id: uuid.UUID | None
    approved_by: uuid.UUID | None
    fact_version_ids: frozenset[uuid.UUID]


@dataclass(frozen=True, slots=True)
class StoredApplication:
    """One open application with its answers by question."""

    id: uuid.UUID
    opportunity_id: uuid.UUID
    started_at: datetime
    submitted_at: datetime | None
    answers: tuple[Answer, ...]
