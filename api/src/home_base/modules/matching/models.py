"""Matching tables: match results with their inputs, and the founder's decisions.

A match is a stored derived value, so it keeps the rule version and the inputs that
produced it (handbook section 11): every recalculation adds a new match and supersedes
the old one, and each requirement result points to the fact version it read (D-50).
Founder facts are referenced by key only, never by row, so deleting one (D-51) leaves
no copy behind. The AI's explanation and confidence columns come with the AI (week 4).
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
from home_base.core.vocabulary import Decision, FitStatus
from home_base.modules.matching.domain import NotForUsReason, RequirementResult

FIT_STATUSES = tuple(f.value for f in FitStatus)
RESULTS = tuple(r.value for r in RequirementResult)
DECISIONS = tuple(d.value for d in Decision)
REASONS = tuple(r.value for r in NotForUsReason)


class MatchRow(Record, Base):
    """One calculation of a company's fit for one opportunity."""

    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint(one_of("fit_status", FIT_STATUSES), name="fit_status"),
        CheckConstraint("length(btrim(rule_version)) > 0", name="rule_version_not_blank"),
        UniqueConstraint("id", "company_id", name="uq_matches_id_company"),
        Index(
            "uq_matches_one_current",
            "company_id",
            "opportunity_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"), index=True)
    fit_status: Mapped[str]
    few_explicit_rules: Mapped[bool]  # FIT-04's note
    rule_version: Mapped[str]
    calculated_at: Mapped[datetime]
    superseded_at: Mapped[datetime | None]  # set when a recalculation replaces it


class RequirementResultRow(Record, Base):
    """The result of one requirement in one match, with the input it read."""

    __tablename__ = "requirement_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["match_id", "company_id"],
            ["matches.id", "matches.company_id"],
            name="fk_requirement_results_match_same_company",
        ),
        ForeignKeyConstraint(
            ["fact_version_id", "company_id"],
            ["company_facts.id", "company_facts.company_id"],
            name="fk_requirement_results_fact_same_company",
        ),
        CheckConstraint(one_of("result", RESULTS), name="result"),
        CheckConstraint(
            "fact_version_id IS NULL OR fact_key IS NOT NULL", name="fact_version_has_key"
        ),
        UniqueConstraint("match_id", "requirement_id", name="uq_requirement_results_match_req"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id"))
    result: Mapped[str]
    fact_key: Mapped[str | None]  # the fact a hard rule read, company or founder fact
    fact_version_id: Mapped[uuid.UUID | None]  # the company fact version; null for founder facts


class DecisionRow(Record, Base):
    """One dated change of the founder's decision (DEC-01): history is every row."""

    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(one_of("decision", DECISIONS), name="decision"),
        CheckConstraint("reason IS NULL OR " + one_of("reason", REASONS), name="reason"),
        CheckConstraint(
            "reason IS NULL OR decision = 'not_for_us'", name="reason_only_with_not_for_us"
        ),
        Index("ix_decisions_company_opportunity", "company_id", "opportunity_id", "changed_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"))
    decision: Mapped[str]
    reason: Mapped[str | None]  # optional, with Not for us only
    changed_at: Mapped[datetime]
