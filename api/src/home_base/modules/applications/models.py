"""Application tables: applications, answers, answer versions and the facts each used.

Only what the founder does is stored: starting an application and marking it submitted
(nothing is submitted from the platform). The application's status is calculated by
the progress rules, never stored. Each answer keeps its current state and autosaved
text; every AI draft or redraft and every approval is a saved version that links to
the AI call that produced it and to the exact company fact versions it used (D-50).
Drafts never use founder facts (D-44), so versions link to company facts only.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from home_base.core.db import Base, Record, one_of
from home_base.modules.today.domain import AnswerState

# An answer row exists once there is a draft, an edit or an approval; "missing facts"
# is calculated for questions without one.
ANSWER_STATES = tuple(s.value for s in AnswerState if s is not AnswerState.MISSING_FACTS)
VERSION_KINDS = ("ai_draft", "approved")


class ApplicationRow(Record, Base):
    """One company's workspace for one opportunity."""

    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "submitted_at IS NULL OR submitted_at >= started_at", name="submitted_after_started"
        ),
        UniqueConstraint("id", "company_id", name="uq_applications_id_company"),
        Index(
            "uq_applications_one_open",
            "company_id",
            "opportunity_id",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"))
    started_at: Mapped[datetime]
    submitted_at: Mapped[datetime | None]  # set by the founder, never by the platform
    archived_at: Mapped[datetime | None]  # e.g. no longer eligible, once the founder confirms


class AnswerRow(Record, Base):
    """The answer to one question in one application."""

    __tablename__ = "answers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["application_id", "company_id"],
            ["applications.id", "applications.company_id"],
            name="fk_answers_application_same_company",
        ),
        CheckConstraint(one_of("state", ANSWER_STATES), name="state"),
        UniqueConstraint("id", "company_id", name="uq_answers_id_company"),
        UniqueConstraint("application_id", "question_id", name="uq_answers_application_question"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"))
    state: Mapped[str]  # ai_draft, edited or approved
    current_text: Mapped[str]  # autosaved; the latest draft or edit


class AnswerVersionRow(Record, Base):
    """A saved version of an answer: an AI draft or redraft, or an approval."""

    __tablename__ = "answer_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["answer_id", "company_id"],
            ["answers.id", "answers.company_id"],
            name="fk_answer_versions_answer_same_company",
        ),
        CheckConstraint(one_of("kind", VERSION_KINDS), name="kind"),
        CheckConstraint(
            "(kind = 'ai_draft') = (ai_action_id IS NOT NULL)", name="ai_draft_has_ai_action"
        ),
        CheckConstraint(
            "(kind = 'approved') = (approved_by IS NOT NULL)", name="approval_has_approver"
        ),
        UniqueConstraint("id", "company_id", name="uq_answer_versions_id_company"),
    )

    answer_id: Mapped[uuid.UUID] = mapped_column(index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    kind: Mapped[str]
    text: Mapped[str]
    ai_action_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_actions.id"))
    approved_by: Mapped[uuid.UUID | None]  # the founder's user ID; FK with users (step 6)


class AnswerVersionFactRow(Record, Base):
    """One company fact version an answer version was built from ("Built from N facts")."""

    __tablename__ = "answer_version_facts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["answer_version_id", "company_id"],
            ["answer_versions.id", "answer_versions.company_id"],
            name="fk_answer_version_facts_version_same_company",
        ),
        ForeignKeyConstraint(
            ["fact_version_id", "company_id"],
            ["company_facts.id", "company_facts.company_id"],
            name="fk_answer_version_facts_fact_same_company",
        ),
        UniqueConstraint(
            "answer_version_id", "fact_version_id", name="uq_answer_version_facts_pair"
        ),
    )

    answer_version_id: Mapped[uuid.UUID] = mapped_column(index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    fact_version_id: Mapped[uuid.UUID]
