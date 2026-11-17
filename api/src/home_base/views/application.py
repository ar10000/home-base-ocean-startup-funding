"""Read model for the Application screen (spec: Application; PRG-01 to PRG-03, D-53).

The questions in the call's order, each with its state, what it is missing, whether it
can be drafted, the current text and what it was built from; plus the status, answers
ready and days left. Nothing here writes.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel
from sqlalchemy.orm import Session

from home_base.ai import retrieval
from home_base.core.errors import NotFoundError
from home_base.modules.applications import service as applications
from home_base.modules.applications.repository import ApplicationRepository
from home_base.modules.companies import service as companies
from home_base.modules.companies.repository import CompanyRepository
from home_base.modules.opportunities import rules as opportunity_rules
from home_base.modules.opportunities.service import (
    StoredOpportunity,
    current_opportunities,
    removed_opportunities,
)
from home_base.modules.today import rules as today_rules
from home_base.modules.today.domain import (
    AnswerState,
    ApplicationSnapshot,
    ApplicationStatus,
    QuestionSnapshot,
)
from home_base.views.opportunities import Deadline, Readiness


class CitedFact(BaseModel):
    """A fact version an answer was built from (DRF-02), in words."""

    id: uuid.UUID
    fact: str  # the key, e.g. "team_size" or "impact"
    value: str


class QuestionOut(BaseModel):
    id: uuid.UUID
    position: int  # 1-based, in the call's order
    text: str
    required_facts: list[str]
    missing: list[str]  # required facts with no approved value
    draftable: bool  # PRG-02
    state: AnswerState
    answer: str | None
    built_from: list[uuid.UUID]  # fact versions of the latest saved version (DRF-02)
    sources: list[CitedFact]  # the same facts, with their values as they were then


class ApplicationOut(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    opportunity: str
    deadline: Deadline
    started_at: datetime
    submitted_at: datetime | None
    status: ApplicationStatus  # PRG-03
    answers_ready: Readiness | None  # PRG-01
    no_longer_eligible: bool  # D-53: confirm to archive
    call_removed: bool  # D-73: the call left the seed set; the application is read-only
    questions_known: bool
    questions: list[QuestionOut]


class ApplicationSummary(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    opportunity: str
    status: ApplicationStatus
    answers_ready: Readiness | None
    call_removed: bool  # D-73


def _opportunity(session: Session, opportunity_id: uuid.UUID) -> tuple[StoredOpportunity, bool]:
    """The application's opportunity, and whether its call was removed (D-73)."""
    current = {o.id: o for o in current_opportunities(session)}.get(opportunity_id)
    if current is not None:
        return current, False
    removed = {o.id: o for o in removed_opportunities(session)}.get(opportunity_id)
    if removed is None:
        raise NotFoundError("no such application")
    return removed, True


def _sources(repo: CompanyRepository, ids: frozenset[uuid.UUID]) -> list[CitedFact]:
    found = (repo.fact_version(i) for i in sorted(ids))
    return [
        CitedFact(id=f.id, fact=f.key, value=retrieval.value_text(f.key, f.value))
        for f in found
        if f is not None
    ]


def application_view(
    session: Session, company_id: uuid.UUID, application_id: uuid.UUID, today: date
) -> ApplicationOut:
    found = {a.id: a for a in applications.open_applications(session, company_id)}.get(
        application_id
    )
    if found is None:
        raise NotFoundError("no such application")
    opp, call_removed = _opportunity(session, found.opportunity_id)
    inputs = companies.match_inputs(session, company_id)
    approved = frozenset(f.key for f in inputs.facts if f.approved)
    answers = {a.question_id: a for a in found.answers}
    repo = ApplicationRepository(session, company_id)
    facts_repo = CompanyRepository(session, company_id)
    questions: list[QuestionOut] = []
    snapshots: list[QuestionSnapshot] = []
    for i, (qid, q) in enumerate(zip(opp.question_ids, opp.record.questions or (), strict=True)):
        answer = answers.get(qid)
        state = answer.state if answer else AnswerState.MISSING_FACTS
        snapshot = QuestionSnapshot(state, q.required_facts)
        snapshots.append(snapshot)
        versions = repo.versions(found.id, qid) if answer else []
        questions.append(
            QuestionOut(
                id=qid,
                position=i + 1,
                text=q.text,
                required_facts=sorted(q.required_facts),
                missing=sorted(q.required_facts - approved),
                draftable=today_rules.is_draftable(snapshot, approved),
                state=state,
                answer=answer.text if answer else None,
                built_from=sorted(versions[-1].fact_version_ids) if versions else [],
                sources=_sources(facts_repo, versions[-1].fact_version_ids) if versions else [],
            )
        )
    status = today_rules.application_status(
        ApplicationSnapshot(tuple(snapshots), found.submitted_at is not None)
    )
    shown = opportunity_rules.deadline_display(opp.record.deadline, today)
    ready = today_rules.answers_ready(snapshots)
    return ApplicationOut(
        id=found.id,
        opportunity_id=opp.id,
        opportunity=opp.record.name,
        deadline=Deadline(
            kind=shown.kind.value, date=opp.record.deadline, days_left=shown.days_left
        ),
        started_at=found.started_at,
        submitted_at=found.submitted_at,
        status=status,
        answers_ready=Readiness(ready=ready.done, total=ready.total) if ready else None,
        no_longer_eligible=found.id
        in {a.id for a in applications.no_longer_eligible(session, company_id)},
        call_removed=call_removed,
        questions_known=opp.record.questions is not None,
        questions=questions,
    )


def application_list(
    session: Session, company_id: uuid.UUID, today: date
) -> list[ApplicationSummary]:
    """Open applications, including those whose call was removed from the seed set,
    which stay visible read-only (D-73)."""
    found = []
    for a in applications.open_applications(session, company_id):
        view = application_view(session, company_id, a.id, today)
        found.append(
            ApplicationSummary(
                id=view.id,
                opportunity_id=view.opportunity_id,
                opportunity=view.opportunity,
                status=view.status,
                answers_ready=view.answers_ready,
                call_removed=view.call_removed,
            )
        )
    return found
