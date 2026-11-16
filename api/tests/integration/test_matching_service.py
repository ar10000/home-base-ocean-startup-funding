"""Matching service on a real Postgres: recalculation stores only what changed (D-52),
with its inputs, rule version and an audit event in the same transaction."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from home_base.core.context import Clock
from home_base.core.vocabulary import FitStatus, Operator
from home_base.modules.audit.models import AuditEvent
from home_base.modules.audit.repository import AuditRepository
from home_base.modules.companies.models import CompanyFactRow, CompanyRow
from home_base.modules.matching import service
from home_base.modules.matching.domain import FactInput, FitResult, MatchInputs, RequirementResult
from home_base.modules.matching.models import MatchRow
from home_base.modules.matching.repository import MatchingRepository
from home_base.modules.opportunities.repository import OpportunityRepository
from home_base.modules.opportunities.seed import SeedRequirement, load_seed_dir
from home_base.modules.opportunities.service import StoredOpportunity, current_opportunities

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed"
TODAY = date(2026, 11, 11)
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
CLOCK = Clock(at=T0, today=TODAY, request_id="req-1")
LATER = Clock(at=T0 + timedelta(hours=1), today=TODAY)
NOTHING = MatchInputs(facts=())


@dataclass
class World:
    session: Session
    a: uuid.UUID
    b: uuid.UUID
    grant: StoredOpportunity  # country = PT, TRL at least 4, one soft criterion
    accelerator: StoredOpportunity  # applicant_form one of alone/consortium

    @property
    def opportunities(self) -> list[StoredOpportunity]:
        return [self.grant, self.accelerator]


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
    OpportunityRepository(session).reload(load_seed_dir(FIXTURES, TODAY), T0)
    by_name = {o.record.name: o for o in current_opportunities(session)}
    return World(
        session,
        a.id,
        b.id,
        by_name["Fictional Ocean Grant"],
        by_name["Fictional Accelerator Batch"],
    )


def _fact(key: str, value: str | int | bool, approved: bool = True) -> FactInput:
    return FactInput(key, value, approved, uuid.uuid4())


def _real(w: World, company: uuid.UUID, facts: tuple[FactInput, ...]) -> MatchInputs:
    """Store each input as a real fact version with the same ID, superseding any current one,
    as the companies service will have done before recalculating."""
    for f in facts:
        w.session.execute(
            update(CompanyFactRow)
            .where(
                CompanyFactRow.company_id == company,
                CompanyFactRow.key == f.key,
                CompanyFactRow.superseded_at.is_(None),
            )
            .values(superseded_at=T0)
        )
        kind = (
            "boolean"
            if isinstance(f.value, bool)
            else "integer"
            if isinstance(f.value, int)
            else "text"
        )
        w.session.add(
            CompanyFactRow(
                id=f.version_id,
                company_id=company,
                key=f.key,
                value_type=kind,
                **{f"value_{kind}": f.value},
                label="user_provided",
                approved_at=T0 if f.approved else None,
                approved_by=uuid.uuid4() if f.approved else None,
            )
        )
        w.session.flush()
    return MatchInputs(facts)


def _count(session: Session, model: type[MatchRow] | type[AuditEvent]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _fits(w: World, company: uuid.UUID) -> dict[str, FitResult]:
    names = {o.id: o.record.name for o in w.opportunities}
    return {
        names[m.opportunity_id]: m.fit
        for m in MatchingRepository(w.session, company).current_matches()
    }


def test_a_company_with_no_facts_is_possible_everywhere(world: World) -> None:
    changes = service.recalculate(world.session, world.a, world.opportunities, NOTHING, CLOCK)
    assert {c.before for c in changes} == {None}
    assert _fits(world, world.a) == {
        "Fictional Ocean Grant": FitResult(FitStatus.POSSIBLE, few_explicit_rules=False),
        "Fictional Accelerator Batch": FitResult(FitStatus.POSSIBLE, few_explicit_rules=True),
    }


def test_no_opportunities_stores_nothing(world: World) -> None:
    assert service.recalculate(world.session, world.a, [], NOTHING, CLOCK) == []
    assert _count(world.session, MatchRow) == 0


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        ((_fact("country", "PT"), _fact("trl", 4)), FitStatus.CONFIRMED),  # TRL boundary
        ((_fact("country", "PT"), _fact("trl", 3)), FitStatus.NOT_ELIGIBLE),
        ((_fact("country", "ES"), _fact("trl", 9)), FitStatus.NOT_ELIGIBLE),
        ((_fact("country", "PT"), _fact("trl", 6, approved=False)), FitStatus.POSSIBLE),
        ((_fact("country", "PT"),), FitStatus.POSSIBLE),
    ],
)
def test_fit_follows_the_rules(
    world: World, facts: tuple[FactInput, ...], expected: FitStatus
) -> None:
    service.recalculate(world.session, world.a, [world.grant], _real(world, world.a, facts), CLOCK)
    assert _fits(world, world.a)["Fictional Ocean Grant"].status is expected


def test_outcomes_name_the_fact_versions_read_and_soft_criteria_are_ai_judgements(
    world: World,
) -> None:
    country, trl = _fact("country", "PT"), _fact("trl", 6, approved=False)
    service.recalculate(
        world.session, world.a, [world.grant], _real(world, world.a, (country, trl)), CLOCK
    )
    (match,) = MatchingRepository(world.session, world.a).current_matches()
    assert [(o.result, o.fact_key, o.fact_version_id) for o in match.outcomes] == [
        (RequirementResult.PASS, "country", country.version_id),
        (RequirementResult.UNKNOWN, "trl", trl.version_id),  # read, not approved
        (RequirementResult.AI_JUDGEMENT, None, None),
    ]
    assert match.rule_version == service.RULE_VERSION


def test_recalculating_with_the_same_inputs_writes_nothing(world: World) -> None:
    inputs = _real(world, world.a, (_fact("country", "PT"), _fact("trl", 5)))
    service.recalculate(world.session, world.a, world.opportunities, inputs, CLOCK)
    matches, events = _count(world.session, MatchRow), _count(world.session, AuditEvent)
    assert service.recalculate(world.session, world.a, world.opportunities, inputs, LATER) == []
    assert (_count(world.session, MatchRow), _count(world.session, AuditEvent)) == (matches, events)


def test_a_new_fact_version_with_the_same_fit_is_still_a_change(world: World) -> None:
    """The inputs read changed (D-52), so the match records the new version."""
    service.recalculate(
        world.session,
        world.a,
        [world.grant],
        _real(world, world.a, (_fact("country", "PT"),)),
        CLOCK,
    )
    changes = service.recalculate(
        world.session,
        world.a,
        [world.grant],
        _real(world, world.a, (_fact("country", "PT"),)),
        LATER,
    )
    assert [(c.before, c.after) for c in changes] == [
        (FitResult(FitStatus.POSSIBLE, False), FitResult(FitStatus.POSSIBLE, False))
    ]


def test_a_change_writes_an_audit_event_on_the_opportunity(world: World) -> None:
    service.recalculate(world.session, world.a, [world.grant], NOTHING, CLOCK)
    facts = _real(world, world.a, (_fact("country", "ES"),))
    service.recalculate(world.session, world.a, [world.grant], facts, LATER)
    history = AuditRepository(world.session, world.a).history("opportunity", world.grant.id)
    assert [(e.action, e.before, e.after) for e in history] == [
        ("match.recalculated", None, {"fit_status": "possible", "few_explicit_rules": False}),
        (
            "match.recalculated",
            {"fit_status": "possible", "few_explicit_rules": False},
            {"fit_status": "not_eligible", "few_explicit_rules": False},
        ),
    ]
    assert history[0].rule_version == service.RULE_VERSION
    assert history[0].request_id == "req-1"


def test_a_different_rule_version_is_stored_as_a_change(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.recalculate(world.session, world.a, [world.grant], NOTHING, CLOCK)
    monkeypatch.setattr(service, "RULE_VERSION", "fit-next")
    changes = service.recalculate(world.session, world.a, [world.grant], NOTHING, LATER)
    assert len(changes) == 1
    assert (
        MatchingRepository(world.session, world.a).current_matches()[0].rule_version == "fit-next"
    )


def test_founder_age_is_measured_on_the_deadline(world: World) -> None:
    """A founder-age rule reads the approved birth date, measured on the deadline."""
    young = replace(
        world.grant,
        record=replace(
            world.grant.record,
            requirements=(
                SeedRequirement(
                    True, "Founders aged 29 or under.", "founder_age", Operator.AT_MOST, 29
                ),
            ),
        ),
        requirement_ids=world.grant.requirement_ids[:1],
    )
    # The deadline is 2027-01-31: born 1997-01-31 is 30 that day; born 1997-02-01 is 29.
    for birth, expected in [
        (date(1997, 2, 1), RequirementResult.PASS),
        (date(1997, 1, 31), RequirementResult.FAIL),
    ]:
        fit, outcomes = service.evaluate(young, MatchInputs((), approved_birth_date=birth), TODAY)
        assert (outcomes[0].result, outcomes[0].fact_key, outcomes[0].fact_version_id) == (
            expected,
            "founder_age",
            None,  # founder facts are never linked by row (D-51)
        )
    _, outcomes = service.evaluate(young, NOTHING, TODAY)
    assert outcomes[0].result is RequirementResult.UNKNOWN


def test_companies_are_recalculated_separately(world: World) -> None:
    service.recalculate(
        world.session,
        world.a,
        [world.grant],
        _real(world, world.a, (_fact("country", "ES"),)),
        CLOCK,
    )
    service.recalculate(world.session, world.b, [world.grant], NOTHING, CLOCK)
    assert _fits(world, world.a)["Fictional Ocean Grant"].status is FitStatus.NOT_ELIGIBLE
    assert _fits(world, world.b)["Fictional Ocean Grant"].status is FitStatus.POSSIBLE


def test_the_rule_version_is_a_stable_fingerprint() -> None:
    assert service.RULE_VERSION.startswith("fit-")
    assert service._fingerprint() == service.RULE_VERSION
