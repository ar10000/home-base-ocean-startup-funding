"""Application use cases. "No longer eligible" is calculated, never stored (D-53)."""

import uuid

from sqlalchemy.orm import Session

from home_base.ai import retrieval
from home_base.ai.provider import Provider
from home_base.ai.runner import AiTask, run
from home_base.ai.tasks import draft_answer as draft_task
from home_base.core.context import Caller, Clock
from home_base.core.errors import ApplicationError, NotFoundError
from home_base.modules.applications import rules
from home_base.modules.applications.domain import (
    Answer,
    AnswerVersion,
    Draft,
    StoredApplication,
    VersionKind,
)
from home_base.modules.applications.repository import ApplicationRepository
from home_base.modules.audit.domain import Actor, AuditEntry
from home_base.modules.audit.repository import AuditRepository
from home_base.modules.companies.repository import CompanyRepository
from home_base.modules.matching import service as matching
from home_base.modules.opportunities.service import current_opportunities
from home_base.modules.today.domain import AnswerState


def open_applications(session: Session, company_id: uuid.UUID) -> list[StoredApplication]:
    return ApplicationRepository(session, company_id).open_applications()


def start_application(
    session: Session, caller: Caller, opportunity_id: uuid.UUID, clock: Clock
) -> StoredApplication:
    """Open the workspace (or return the open one) and set the decision to Pursuing
    (DEC-02), with its audit events, in the caller's transaction."""
    repo = ApplicationRepository(session, caller.company_id)
    already = {a.opportunity_id: a for a in repo.open_applications()}.get(opportunity_id)
    application = repo.start(opportunity_id, clock.at)
    if already is None:
        AuditRepository(session, caller.company_id).record(
            AuditEntry(
                actor=Actor.FOUNDER,
                actor_id=caller.user_id,
                action="application.started",
                entity="application",
                entity_id=application.id,
                occurred_at=clock.at,
                after={"opportunity_id": str(opportunity_id)},
                request_id=clock.request_id,
            )
        )
    matching.decide_on_application_start(session, caller, opportunity_id, clock)
    return application


def no_longer_eligible(session: Session, company_id: uuid.UUID) -> list[StoredApplication]:
    """Open applications whose opportunity the company is no longer eligible for (INT-04,
    calculated from the current match, D-53)."""
    not_eligible = matching.not_eligible_opportunities(session, company_id)
    return [
        a
        for a in ApplicationRepository(session, company_id).open_applications()
        if a.opportunity_id in not_eligible
    ]


def confirm_no_longer_eligible(
    session: Session, caller: Caller, application_id: uuid.UUID, clock: Clock
) -> None:
    """The founder confirms: the application is archived, never deleted (INT-04)."""
    if application_id not in {a.id for a in no_longer_eligible(session, caller.company_id)}:
        raise ApplicationError("this application is still eligible")
    ApplicationRepository(session, caller.company_id).archive(application_id, clock.at)
    AuditRepository(session, caller.company_id).record(
        AuditEntry(
            actor=Actor.FOUNDER,
            actor_id=caller.user_id,
            action="application.archived_not_eligible",
            entity="application",
            entity_id=application_id,
            occurred_at=clock.at,
            request_id=clock.request_id,
        )
    )


# Answers and submission (D-62)


def _open_application(
    session: Session, caller: Caller, application_id: uuid.UUID
) -> StoredApplication:
    """An open application the founder can still change: one whose call was removed from
    the seed set is kept read-only (D-73)."""
    found = {a.id: a for a in open_applications(session, caller.company_id)}.get(application_id)
    if found is None:
        raise NotFoundError("no such application")
    if found.opportunity_id not in {o.id for o in current_opportunities(session)}:
        raise ApplicationError("this call is no longer listed, so the application is read-only")
    return found


def _check_question(
    session: Session, application: StoredApplication, question_id: uuid.UUID
) -> None:
    """A question belongs to the application's opportunity, or it is not found."""
    opp = {o.id: o for o in current_opportunities(session)}.get(application.opportunity_id)
    if opp is None or question_id not in opp.question_ids:
        raise NotFoundError("no such question in this application")


def _state(application: StoredApplication, question_id: uuid.UUID) -> AnswerState:
    found = {a.question_id: a.state for a in application.answers}
    return found.get(question_id, AnswerState.MISSING_FACTS)


def edit_answer(
    session: Session, caller: Caller, ref: tuple[uuid.UUID, uuid.UUID], text: str, clock: Clock
) -> Answer:
    """Autosave the founder's text; a change of state (to edited, or reopening an
    approved answer, D-09) is audited, a text-only save is not (D-62)."""
    application_id, question_id = ref
    application = _open_application(session, caller, application_id)
    _check_question(session, application, question_id)
    before = _state(application, question_id)
    answer = ApplicationRepository(session, caller.company_id).save_edit(
        application_id, question_id, text, clock.at
    )
    if answer.state is not before:
        _audit(
            session,
            caller,
            clock,
            "answer.edited",
            application_id,
            before,
            answer.state,
            question_id,
        )
    return answer


def approve_answer(
    session: Session, caller: Caller, ref: tuple[uuid.UUID, uuid.UUID], clock: Clock
) -> AnswerVersion:
    """Approve the current text; built from the latest AI draft's facts (D-62). Approving
    an answer already approved writes nothing and returns its approval."""
    application_id, question_id = ref
    application = _open_application(session, caller, application_id)
    _check_question(session, application, question_id)
    repo = ApplicationRepository(session, caller.company_id)
    versions = repo.versions(application_id, question_id)
    before = _state(application, question_id)
    if before is AnswerState.APPROVED and versions and versions[-1].kind is VersionKind.APPROVED:
        return versions[-1]
    current = {a.question_id: a.text for a in application.answers}.get(question_id, "")
    if not rules.approvable(current):
        raise ApplicationError("write an answer before approving it")
    drafts = [v for v in versions if v.kind is VersionKind.AI_DRAFT]
    facts = drafts[-1].fact_version_ids if drafts else frozenset()
    version = repo.approve_answer(application_id, question_id, caller.user_id, facts, clock.at)
    _audit(
        session,
        caller,
        clock,
        "answer.approved",
        application_id,
        before,
        AnswerState.APPROVED,
        question_id,
    )
    return version


def draft_answer(
    session: Session,
    caller: Caller,
    ref: tuple[uuid.UUID, uuid.UUID],
    provider: Provider,
    clock: Clock,
) -> AnswerVersion:
    """Draft (or redraft) one answer from approved facts (D-81, DRF-01, DRF-02).

    The question's required facts and the approved facts closest to it are the only
    facts sent. A valid draft replaces the answer's text, is saved as an AI draft with
    links to every fact it cited, and is audited. An invalid one raises; nothing is
    saved but the AI action log. An approved answer is reopened by editing it first.
    """
    application_id, question_id = ref
    application = _open_application(session, caller, application_id)
    _check_question(session, application, question_id)
    before = _state(application, question_id)
    if before is AnswerState.APPROVED:
        raise ApplicationError("this answer is approved; edit it to reopen it before redrafting")
    opp = {o.id: o for o in current_opportunities(session)}[application.opportunity_id]
    question = dict(zip(opp.question_ids, opp.record.questions or (), strict=True))[question_id]

    usable = [
        f
        for f in CompanyRepository(session, caller.company_id).current_facts()
        if f.approved_at is not None and f.superseded_at is None
    ]
    if not usable:
        raise ApplicationError("approve at least one company fact before drafting")
    required = [f for f in usable if f.key in question.required_facts]
    retrieval.ensure_embeddings(session, provider, caller.company_id, usable)
    near = retrieval.closest(
        session,
        provider,
        caller.company_id,
        question.text,
        among={f.id for f in usable} - {f.id for f in required},
    )
    by_id = {f.id: f for f in usable}
    chosen = [*required, *(by_id[i] for i in near)]
    refs = {f"F{n}": f for n, f in enumerate(chosen, start=1)}
    payload = draft_task.DraftInput(
        question=question.text,
        limit=None,  # the seed files carry no limits yet
        facts=[
            draft_task.FactIn(
                ref=r, fact=retrieval.fact_name(f.key), value=retrieval.value_text(f.key, f.value)
            )
            for r, f in refs.items()
        ],
    )
    result = run(
        session,
        provider,
        AiTask(
            prompt=draft_task.prompt(),
            payload=payload,
            output=draft_task.DraftOutput,
            validate=draft_task.validator(payload),
            refs=[{"entity": "question", "id": str(question_id)}]
            + [{"entity": "company_fact", "id": str(f.id)} for f in chosen],
            company_id=caller.company_id,
            served=("application", application_id),
        ),
        clock,
    )
    cited = rules.draft_citations(s.facts for s in result.value.sentences)
    fact_ids = [refs[r].id for r in cited]
    if rules.unusable_citations(fact_ids, by_id.keys()):  # DRF-01, checked again on IDs
        raise ApplicationError("the draft cited a fact that is not approved")
    version = ApplicationRepository(session, caller.company_id).save_ai_draft(
        application_id,
        question_id,
        Draft(result.value.text, result.action_id, frozenset(fact_ids)),
        clock.at,
    )
    _audit(
        session,
        caller,
        clock,
        "answer.drafted",
        application_id,
        before,
        AnswerState.AI_DRAFT,
        question_id,
    )
    return version


def mark_submitted(
    session: Session, caller: Caller, application_id: uuid.UUID, clock: Clock
) -> StoredApplication:
    """The founder marks it submitted (DRF-03: nothing is submitted from the platform)."""
    if not rules.may_mark_submitted(Actor.FOUNDER):  # the only actor this path serves
        raise ApplicationError("only the founder marks an application submitted")
    before = _open_application(session, caller, application_id)
    application = ApplicationRepository(session, caller.company_id).mark_submitted(
        application_id, clock.at
    )
    if before.submitted_at is None:
        AuditRepository(session, caller.company_id).record(
            AuditEntry(
                actor=Actor.FOUNDER,
                actor_id=caller.user_id,
                action="application.submitted",
                entity="application",
                entity_id=application_id,
                occurred_at=clock.at,
                request_id=clock.request_id,
            )
        )
    return application


def _audit(  # noqa: PLR0913  (an answer event has this many parts)
    session: Session,
    caller: Caller,
    clock: Clock,
    action: str,
    application_id: uuid.UUID,
    before: AnswerState,
    after: AnswerState,
    question_id: uuid.UUID,
) -> None:
    AuditRepository(session, caller.company_id).record(
        AuditEntry(
            actor=Actor.FOUNDER,
            actor_id=caller.user_id,
            action=action,
            entity="application",
            entity_id=application_id,
            occurred_at=clock.at,
            before={"question_id": str(question_id), "state": before.value},
            after={"question_id": str(question_id), "state": after.value},
            request_id=clock.request_id,
        )
    )
