"""MatchingRepository on a real Postgres: stored matches keep their inputs and history;
decisions are a dated history; companies never see each other's."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from home_base.core.vocabulary import Decision, FitStatus
from home_base.modules.companies.domain import FactLabel
from home_base.modules.companies.models import CompanyRow
from home_base.modules.companies.repository import CompanyRepository
from home_base.modules.matching.domain import (
    DecisionChange,
    FitResult,
    NotForUsReason,
    RequirementOutcome,
    RequirementResult,
)
from home_base.modules.matching.repository import MatchingRepository
from home_base.modules.opportunities.repository import OpportunityRepository, StoredOpportunity
from home_base.modules.opportunities.seed import load_seed_dir

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed"
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)
T2 = T0 + timedelta(hours=2)


@dataclass
class World:
    a: MatchingRepository
    b: MatchingRepository
    companies_a: CompanyRepository
    companies_b: CompanyRepository
    opportunities: list[StoredOpportunity]


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def world(session: Session) -> World:
    a, b = CompanyRow(name="A"), CompanyRow(name="B")
    session.add_all([a, b])
    session.flush()
    opps = OpportunityRepository(session)
    opps.reload(load_seed_dir(FIXTURES, date(2026, 11, 11)), T0)
    return World(
        MatchingRepository(session, a.id),
        MatchingRepository(session, b.id),
        CompanyRepository(session, a.id),
        CompanyRepository(session, b.id),
        opps.current(),
    )


def _outcomes(w: World, opp: StoredOpportunity, fact_id: object) -> list[RequirementOutcome]:
    first, *rest = opp.requirement_ids
    return [
        RequirementOutcome(first, RequirementResult.PASS, "country", fact_id),  # type: ignore[arg-type]
        *(RequirementOutcome(r, RequirementResult.UNKNOWN) for r in rest),
    ]


def test_a_company_with_no_matches_or_decisions(world: World) -> None:
    opp = world.opportunities[0]
    assert world.a.current_matches() == []
    assert world.a.match_history(opp.id) == []
    assert world.a.decision_history(opp.id) == []
    assert world.a.decision_histories() == {}


def test_a_saved_match_reads_back_with_its_outcomes(world: World) -> None:
    opp = world.opportunities[0]
    fact = world.companies_a.add_fact_version("country", "PT", FactLabel.SOURCED, None, T0)
    fit = FitResult(FitStatus.POSSIBLE, few_explicit_rules=True)
    saved = world.a.save_match(opp.id, fit, "fit-v1", _outcomes(world, opp, fact.id), T0)
    assert world.a.current_matches() == [saved]
    assert (saved.fit, saved.rule_version, saved.calculated_at) == (fit, "fit-v1", T0)
    assert [o.requirement_id for o in saved.outcomes] == list(opp.requirement_ids)
    assert saved.outcomes[0].fact_version_id == fact.id


def test_a_match_with_no_requirements_is_stored(world: World) -> None:
    opp = world.opportunities[0]
    saved = world.a.save_match(opp.id, FitResult(FitStatus.POSSIBLE, True), "fit-v1", [], T0)
    assert saved.outcomes == ()


def test_a_recalculation_supersedes_and_history_keeps_both(world: World) -> None:
    opp = world.opportunities[0]
    first = world.a.save_match(opp.id, FitResult(FitStatus.POSSIBLE, False), "fit-v1", [], T0)
    second = world.a.save_match(opp.id, FitResult(FitStatus.CONFIRMED, False), "fit-v2", [], T1)
    assert world.a.current_matches() == [second]
    history = world.a.match_history(opp.id)
    assert [m.id for m in history] == [first.id, second.id]
    assert history[0].superseded_at == T1


def test_an_outcome_keeps_the_fact_version_after_the_fact_changes(world: World) -> None:
    opp = world.opportunities[0]
    old = world.companies_a.add_fact_version("country", "PT", FactLabel.SOURCED, None, T0)
    world.a.save_match(
        opp.id, FitResult(FitStatus.CONFIRMED, False), "fit-v1", _outcomes(world, opp, old.id), T0
    )
    world.companies_a.add_fact_version("country", "ES", FactLabel.SOURCED, None, T1)
    (stored,) = world.a.match_history(opp.id)
    assert stored.outcomes[0].fact_version_id == old.id


def test_companies_do_not_see_each_others_matches(world: World) -> None:
    opp = world.opportunities[0]
    world.b.save_match(opp.id, FitResult(FitStatus.CONFIRMED, False), "fit-v1", [], T0)
    assert world.a.current_matches() == []
    assert world.a.match_history(opp.id) == []
    world.a.save_match(opp.id, FitResult(FitStatus.NOT_ELIGIBLE, False), "fit-v1", [], T0)
    assert [m.fit.status for m in world.b.current_matches()] == [FitStatus.CONFIRMED]


def test_an_outcome_cannot_cite_another_companys_fact(world: World, session: Session) -> None:
    opp = world.opportunities[0]
    theirs = world.companies_b.add_fact_version("country", "ES", FactLabel.SOURCED, None, T0)
    with pytest.raises(IntegrityError):
        world.a.save_match(
            opp.id,
            FitResult(FitStatus.CONFIRMED, False),
            "fit-v1",
            _outcomes(world, opp, theirs.id),
            T0,
        )


def test_decisions_come_back_oldest_first_per_opportunity(world: World) -> None:
    first, second = world.opportunities[:2]
    later = DecisionChange(Decision.LATER, T0)
    no = DecisionChange(Decision.NOT_FOR_US, T2, NotForUsReason.TOO_EARLY)
    pursuing = DecisionChange(Decision.PURSUING, T1)
    world.a.add_decision(first.id, no)
    world.a.add_decision(first.id, later)
    world.a.add_decision(second.id, pursuing)
    world.b.add_decision(first.id, DecisionChange(Decision.PURSUING, T0))
    assert world.a.decision_history(first.id) == [later, no]
    assert world.a.decision_histories() == {first.id: [later, no], second.id: [pursuing]}
    assert len(world.b.decision_histories()) == 1
