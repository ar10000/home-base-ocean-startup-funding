"""Application data access: workspaces, answers and their saved versions.

Only founder actions are stored on an application (started, submitted, archived);
its status is calculated by the progress rules. Edits autosave on the answer; every
AI draft and every approval is a saved version with the facts it used. Scoped to the
session's company; times are passed in. Writes are safe to repeat (architecture
rule 9): starting twice returns the open application, submitting twice keeps the
first time.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from home_base.core.errors import ApplicationError
from home_base.core.repository import TenantRepository
from home_base.modules.applications.domain import (
    Answer,
    AnswerVersion,
    Draft,
    StoredApplication,
    VersionKind,
)
from home_base.modules.applications.models import (
    AnswerRow,
    AnswerVersionFactRow,
    AnswerVersionRow,
    ApplicationRow,
)
from home_base.modules.today.domain import AnswerState


@dataclass(frozen=True, slots=True)
class _NewVersion:
    kind: VersionKind
    text: str
    fact_version_ids: frozenset[uuid.UUID]
    ai_action_id: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None


class ApplicationRepository(TenantRepository):
    # Applications

    def start(self, opportunity_id: uuid.UUID, at: datetime) -> StoredApplication:
        """Open a workspace for an opportunity, or return the one already open."""
        row = self._open_for(opportunity_id)
        if row is None:
            row = self.add(ApplicationRow(opportunity_id=opportunity_id, started_at=at))
        return self._stored(row)

    def open_applications(self) -> list[StoredApplication]:
        rows = self.session.scalars(
            self.scoped(ApplicationRow)
            .where(ApplicationRow.archived_at.is_(None))
            .order_by(ApplicationRow.started_at, ApplicationRow.id)
        ).all()
        return [self._stored(r) for r in rows]

    def mark_submitted(self, application_id: uuid.UUID, at: datetime) -> StoredApplication:
        """The founder marks it submitted (nothing is submitted from the platform)."""
        row = self._open(application_id)
        if row.submitted_at is None:
            row.submitted_at = at
            self.session.flush()
        return self._stored(row)

    def archive(self, application_id: uuid.UUID, at: datetime) -> None:
        row = self._open(application_id)
        row.archived_at = at
        self.session.flush()

    # Answers

    def save_ai_draft(
        self, application_id: uuid.UUID, question_id: uuid.UUID, draft: Draft, at: datetime
    ) -> AnswerVersion:
        """Store an AI draft or redraft: the answer shows it, and it is saved as a version."""
        answer = self._answer(application_id, question_id, AnswerState.AI_DRAFT, draft.text, at)
        version = _NewVersion(
            VersionKind.AI_DRAFT,
            draft.text,
            draft.fact_version_ids,
            ai_action_id=draft.ai_action_id,
        )
        return self._version(answer, version, at)

    def save_edit(
        self, application_id: uuid.UUID, question_id: uuid.UUID, text: str, at: datetime
    ) -> Answer:
        """Autosave the founder's text; editing an approved answer reopens it (D-09)."""
        row = self._answer(application_id, question_id, AnswerState.EDITED, text, at)
        return Answer(row.question_id, AnswerState(row.state), row.current_text)

    def approve_answer(
        self,
        application_id: uuid.UUID,
        question_id: uuid.UUID,
        by: uuid.UUID,
        fact_version_ids: Iterable[uuid.UUID],
        at: datetime,
    ) -> AnswerVersion:
        """Approve the current text; it is saved as a version with the facts it used."""
        self._open(application_id)
        answer = self.session.scalars(
            self.scoped(AnswerRow).where(
                AnswerRow.application_id == application_id, AnswerRow.question_id == question_id
            )
        ).one_or_none()
        if answer is None:
            raise ApplicationError("there is no answer to approve")
        answer.state, answer.updated_at = AnswerState.APPROVED.value, at
        version = _NewVersion(
            VersionKind.APPROVED, answer.current_text, frozenset(fact_version_ids), approved_by=by
        )
        return self._version(answer, version, at)

    def versions(self, application_id: uuid.UUID, question_id: uuid.UUID) -> list[AnswerVersion]:
        """Every saved version of one answer, oldest first."""
        answer = self.session.scalars(
            self.scoped(AnswerRow).where(
                AnswerRow.application_id == application_id, AnswerRow.question_id == question_id
            )
        ).one_or_none()
        if answer is None:
            return []
        rows = self.session.scalars(
            self.scoped(AnswerVersionRow)
            .where(AnswerVersionRow.answer_id == answer.id)
            .order_by(AnswerVersionRow.created_at, AnswerVersionRow.id)
        ).all()
        links = self.session.scalars(
            self.scoped(AnswerVersionFactRow).where(
                AnswerVersionFactRow.answer_version_id.in_([r.id for r in rows])
            )
        ).all()
        facts: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        for link in links:
            facts[link.answer_version_id].add(link.fact_version_id)
        return [_version(r, frozenset(facts[r.id])) for r in rows]

    # Helpers

    def _open_for(self, opportunity_id: uuid.UUID) -> ApplicationRow | None:
        return self.session.scalars(
            self.scoped(ApplicationRow).where(
                ApplicationRow.opportunity_id == opportunity_id,
                ApplicationRow.archived_at.is_(None),
            )
        ).one_or_none()

    def _open(self, application_id: uuid.UUID) -> ApplicationRow:
        row = self.get(ApplicationRow, application_id)
        if row is None or row.archived_at is not None:
            raise ApplicationError("no open application")
        return row

    def _answer(
        self,
        application_id: uuid.UUID,
        question_id: uuid.UUID,
        state: AnswerState,
        text: str,
        at: datetime,
    ) -> AnswerRow:
        self._open(application_id)
        row = self.session.scalars(
            self.scoped(AnswerRow).where(
                AnswerRow.application_id == application_id, AnswerRow.question_id == question_id
            )
        ).one_or_none()
        if row is None:
            return self.add(
                AnswerRow(
                    application_id=application_id,
                    question_id=question_id,
                    state=state.value,
                    current_text=text,
                    created_at=at,
                    updated_at=at,
                )
            )
        row.state, row.current_text, row.updated_at = state.value, text, at
        self.session.flush()
        return row

    def _version(self, answer: AnswerRow, new: _NewVersion, at: datetime) -> AnswerVersion:
        row = self.add(
            AnswerVersionRow(
                answer_id=answer.id,
                kind=new.kind.value,
                text=new.text,
                ai_action_id=new.ai_action_id,
                approved_by=new.approved_by,
                created_at=at,
                updated_at=at,
            )
        )
        for fact_id in sorted(new.fact_version_ids):
            self.add(AnswerVersionFactRow(answer_version_id=row.id, fact_version_id=fact_id))
        return _version(row, new.fact_version_ids)

    def _stored(self, row: ApplicationRow) -> StoredApplication:
        answers = self.session.scalars(
            self.scoped(AnswerRow)
            .where(AnswerRow.application_id == row.id)
            .order_by(AnswerRow.question_id)
        ).all()
        return StoredApplication(
            id=row.id,
            opportunity_id=row.opportunity_id,
            started_at=row.started_at,
            submitted_at=row.submitted_at,
            answers=tuple(
                Answer(a.question_id, AnswerState(a.state), a.current_text) for a in answers
            ),
        )


def _version(row: AnswerVersionRow, facts: frozenset[uuid.UUID]) -> AnswerVersion:
    return AnswerVersion(
        id=row.id,
        kind=VersionKind(row.kind),
        text=row.text,
        saved_at=row.created_at,
        ai_action_id=row.ai_action_id,
        approved_by=row.approved_by,
        fact_version_ids=facts,
    )
