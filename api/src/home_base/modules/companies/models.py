"""Company tables: companies, the fact catalogue, company facts, founder facts and
intents (spec: Data model; decisions D-47 to D-51).

Tenant tables carry `company_id`. Links between tenant tables include `company_id`
in the foreign key, so a row can never point at another company's row. Users and
memberships come with sign-in (week 2, step 6).
"""

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from home_base.config import EMBEDDING_DIMENSIONS, STAGES
from home_base.core.db import Base, Record, one_of
from home_base.modules.companies.domain import Goal, Window

VALUE_TYPES = ("text", "integer", "boolean")
LABELS = ("sourced", "user_provided", "ai_suggested", "unverified")
# Founder facts as stored (D-44); founder_age is derived from the birth date, never stored.
FOUNDER_FACT_TYPES = {
    "youngest_founder_birth_date": "date",
    "woman_founder": "boolean",
    "woman_ceo": "boolean",
}
GOALS = tuple(g.value for g in Goal)
WINDOWS = tuple(w.value for w in Window)

_APPROVAL_PAIRED = "(approved_at IS NULL) = (approved_by IS NULL)"


def _typed_value(type_column: str, types: tuple[str, ...]) -> str:
    """SQL: exactly the value column for the row's type is set."""
    cases = []
    for t in types:
        others = " AND ".join(f"value_{o} IS NULL" for o in types if o != t)
        cases.append(f"({type_column} = '{t}' AND value_{t} IS NOT NULL AND {others})")
    return " OR ".join(cases)


class CompanyRow(Record, Base):
    """The tenant root."""

    __tablename__ = "companies"
    __table_args__ = (CheckConstraint(one_of("stage", tuple(k for k, _ in STAGES)), name="stage"),)

    name: Mapped[str]
    stage: Mapped[str | None]  # the founder's journey stage (D-78); None until chosen
    archived_at: Mapped[datetime | None]


class FactDefinitionRow(Record, Base):
    """The catalogue of fact keys (D-47). Shared, not tenant data."""

    __tablename__ = "fact_definitions"
    __table_args__ = (
        CheckConstraint(one_of("value_type", VALUE_TYPES), name="value_type"),
        CheckConstraint("key ~ '^[a-z][a-z0-9_]*$'", name="key_is_snake_case"),
        UniqueConstraint("key", "value_type", name="uq_fact_definitions_key_value_type"),
    )

    key: Mapped[str] = mapped_column(unique=True)
    value_type: Mapped[str]
    hard_rule: Mapped[bool]  # checked by hard rules, and part of PRG-04's milestone (D-26)


class CompanyFactRow(Record, Base):
    """One version of one company fact (D-50): edits add versions, never overwrite."""

    __tablename__ = "company_facts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["key", "value_type"],
            ["fact_definitions.key", "fact_definitions.value_type"],
            name="fk_company_facts_definition",
        ),
        CheckConstraint(_typed_value("value_type", VALUE_TYPES), name="value_matches_type"),
        CheckConstraint(
            "value_text IS NULL OR length(btrim(value_text)) > 0", name="text_not_blank"
        ),
        CheckConstraint(one_of("label", LABELS), name="label"),
        CheckConstraint(_APPROVAL_PAIRED, name="approval_paired"),
        UniqueConstraint("id", "company_id", name="uq_company_facts_id_company"),
        Index(
            "uq_company_facts_one_current",
            "company_id",
            "key",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    key: Mapped[str]
    value_type: Mapped[str]
    value_text: Mapped[str | None]
    value_integer: Mapped[int | None]
    value_boolean: Mapped[bool | None]
    label: Mapped[str]  # where it came from; never changes (D-48)
    source: Mapped[str | None]  # a URL or document the value came from
    approved_at: Mapped[datetime | None]
    approved_by: Mapped[uuid.UUID | None]  # the founder's user ID; FK with users (step 6)
    superseded_at: Mapped[datetime | None]  # set when a newer version replaces this one


class FactEmbeddingRow(Record, Base):
    """One approved text fact version, embedded for retrieval (ADR-009, D-81).

    Written when a text fact version is approved; a new version gets its own row. Only
    the vector and the model are stored here, never the text (it stays on the fact).
    """

    __tablename__ = "fact_embeddings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["fact_version_id", "company_id"],
            ["company_facts.id", "company_facts.company_id"],
            name="fk_fact_embeddings_fact_version",
        ),
        UniqueConstraint("fact_version_id", "model", name="uq_fact_embeddings_version_model"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    fact_version_id: Mapped[uuid.UUID]
    model: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))


class FounderFactRow(Record, Base):
    """One founder fact (D-44, D-51). Personal data: no history, deleted for real."""

    __tablename__ = "founder_facts"
    __table_args__ = (
        CheckConstraint(one_of("key", tuple(FOUNDER_FACT_TYPES)), name="key"),
        CheckConstraint(
            " OR ".join(
                f"(key = '{k}' AND value_{t} IS NOT NULL AND value_"
                f"{'boolean' if t == 'date' else 'date'} IS NULL)"
                for k, t in FOUNDER_FACT_TYPES.items()
            ),
            name="value_matches_key",
        ),
        CheckConstraint(_APPROVAL_PAIRED, name="approval_paired"),
        UniqueConstraint("company_id", "key", name="uq_founder_facts_company_key"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    key: Mapped[str]
    value_date: Mapped[date | None]
    value_boolean: Mapped[bool | None]
    approved_at: Mapped[datetime | None]
    approved_by: Mapped[uuid.UUID | None]


class IntentRow(Record, Base):
    """One dated intent (INT-02): every change adds a record; the latest is current."""

    __tablename__ = "intents"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_intents_id_company"),
        Index("ix_intents_company_recorded", "company_id", "recorded_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    recorded_at: Mapped[datetime]


class IntentGoalRow(Record, Base):
    """One goal with its window, in one intent (INT-01)."""

    __tablename__ = "intent_goals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["intent_id", "company_id"],
            ["intents.id", "intents.company_id"],
            name="fk_intent_goals_intent_same_company",
        ),
        CheckConstraint(one_of("goal", GOALS), name="goal"),
        CheckConstraint(one_of("goal_window", WINDOWS), name="goal_window"),
        UniqueConstraint("intent_id", "goal", name="uq_intent_goals_intent_goal"),
    )

    intent_id: Mapped[uuid.UUID] = mapped_column(index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    goal: Mapped[str]
    goal_window: Mapped[str]  # now, soon or later ("window" is reserved in SQL)
