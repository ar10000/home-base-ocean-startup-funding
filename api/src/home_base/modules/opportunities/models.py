"""Opportunity tables: opportunities, sources, requirements, questions, evidence.

The seed files in api/seed/opportunities/ are the source of truth (handbook section 11,
decision D-46): these tables are a copy, reloaded from the files on every deploy, keyed
by `seed_key` (the file name). Nothing is hard-deleted: rows a reload replaces get
`archived_at`. Opportunities are shared records, so they carry no company_id.
"""

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from home_base.config import EMBEDDING_DIMENSIONS
from home_base.core.db import Base, Record, one_of
from home_base.core.vocabulary import Operator, OpportunityType
from home_base.modules.opportunities.domain import EvidenceKind

# Same values as seed.Scope (SCP-01); a unit test keeps them equal.
SCOPES = ("blue_specific", "all_sectors")
OPPORTUNITY_TYPES = tuple(t.value for t in OpportunityType)
OPERATORS = tuple(o.value for o in Operator)
EVIDENCE_KINDS = tuple(k.value for k in EvidenceKind)


def _array_values(column: str, values: tuple[str, ...]) -> str:
    return f"{column} <@ ARRAY[{', '.join(repr(v) for v in values)}]::text[]"


class Archivable:
    archived_at: Mapped[datetime | None]


class OpportunityRow(Record, Archivable, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(one_of("scope", SCOPES), name="scope"),
        CheckConstraint(_array_values("types", OPPORTUNITY_TYPES), name="types_known"),
        CheckConstraint("cardinality(types) >= 1", name="at_least_one_type"),
        CheckConstraint("deadline IS NULL OR timezone IS NOT NULL", name="deadline_has_timezone"),
        CheckConstraint(
            "expected_month IS NULL OR extract(day FROM expected_month) = 1",
            name="expected_month_is_first_day",
        ),
    )

    seed_key: Mapped[str] = mapped_column(unique=True)  # the seed file name, without .yaml
    name: Mapped[str]
    funder: Mapped[str]
    scope: Mapped[str]
    types: Mapped[list[str]] = mapped_column(ARRAY(Text))
    deadline: Mapped[date | None]
    timezone: Mapped[str | None]  # IANA name, e.g. Europe/Lisbon; required with a deadline
    opening: Mapped[date | None]  # official opening date, for an upcoming call
    expected_month: Mapped[date | None]  # stored as the 1st of the month (D-19)
    questions_known: Mapped[bool]  # false: the question list is unknown, not empty


class SourceRow(Record, Archivable, Base):
    """Where an opportunity came from, and when it was last checked by hand (FRS-01)."""

    __tablename__ = "sources"
    __table_args__ = (CheckConstraint("left(url, 8) = 'https://'", name="url_is_https"),)

    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"), index=True)
    url: Mapped[str]
    retrieved_on: Mapped[date]
    verified_on: Mapped[date]
    verified_by: Mapped[str]
    original_text: Mapped[str | None]  # kept as evidence once ingestion stores it (week 4)


class SourcePassageRow(Record, Base):
    """One passage of a call's text, embedded for retrieval (ADR-009, D-83). Shared data."""

    __tablename__ = "source_passages"
    __table_args__ = (
        UniqueConstraint("source_id", "model", "position", name="uq_source_passages_position"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        CheckConstraint("length(btrim(text)) > 0", name="text_not_blank"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    position: Mapped[int]  # order in the call text, from 0
    start: Mapped[int]  # character offset in the call text, so a quote can be found again
    text: Mapped[str]
    model: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))


class RequirementRow(Record, Archivable, Base):
    """One eligibility rule or criterion, with the exact quote from the call."""

    __tablename__ = "requirements"
    __table_args__ = (
        CheckConstraint(
            "operator IS NULL OR " + one_of("operator", OPERATORS), name="operator_known"
        ),
        CheckConstraint(
            "(hard AND fact IS NOT NULL AND operator IS NOT NULL AND criterion IS NULL)"
            " OR (NOT hard AND fact IS NULL AND operator IS NULL AND criterion IS NOT NULL)",
            name="hard_has_fact_soft_has_criterion",
        ),
        CheckConstraint("length(btrim(quote)) > 0", name="quote_not_blank"),
        CheckConstraint("position >= 0", name="position_not_negative"),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"), index=True)
    position: Mapped[int]  # order in the seed file
    hard: Mapped[bool]
    quote: Mapped[str]
    fact: Mapped[str | None]
    operator: Mapped[str | None]
    value: Mapped[Any | None] = mapped_column(JSONB)  # a fact value or a list of values
    criterion: Mapped[str | None]


class QuestionRow(Record, Archivable, Base):
    """One application question and the company facts a draft needs."""

    __tablename__ = "questions"
    __table_args__ = (CheckConstraint("position >= 0", name="position_not_negative"),)

    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"), index=True)
    position: Mapped[int]
    text: Mapped[str]
    required_facts: Mapped[list[str]] = mapped_column(ARRAY(Text))


class EvidenceRow(Record, Archivable, Base):
    """What backs an expected opening month (UPC-02, UPC-05)."""

    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(one_of("kind", EVIDENCE_KINDS), name="kind"),
        CheckConstraint("left(url, 8) = 'https://'", name="url_is_https"),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"), index=True)
    kind: Mapped[str]
    dated: Mapped[date]  # the previous edition's opening date, or the announcement's date
    url: Mapped[str]
