"""The company's journey stage (D-58, D-78): optional, and only one of config.STAGES."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from home_base.config import STAGES
from home_base.modules.companies.models import CompanyRow

pytestmark = pytest.mark.integration


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


def test_a_company_starts_with_no_stage(session: Session) -> None:
    company = CompanyRow(name="A")
    session.add(company)
    session.flush()
    assert company.stage is None


@pytest.mark.parametrize("stage", [k for k, _ in STAGES])
def test_each_listed_stage_is_accepted(session: Session, stage: str) -> None:
    session.add(CompanyRow(name="A", stage=stage))
    session.flush()


@pytest.mark.parametrize("stage", ["Idea", "series_a", ""])
def test_any_other_stage_is_refused(session: Session, stage: str) -> None:
    session.add(CompanyRow(name="A", stage=stage))
    with pytest.raises(IntegrityError, match="ck_companies_stage"):
        session.flush()


def test_the_database_check_lists_exactly_the_configured_stages(session: Session) -> None:
    """If config.STAGES changes, a new migration must change the check too."""
    query = "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :name"
    check = session.execute(text(query), {"name": "ck_companies_stage"}).scalar_one()
    listed = [k for k, _ in STAGES]
    assert all(f"'{k}'" in check for k in listed)
    assert check.count("'") == 2 * len(listed)


def _as_app(session: Session, company: object) -> None:
    session.execute(text("SET LOCAL ROLE home_base_app"))
    session.execute(text("SELECT set_config('app.company_id', :c, true)"), {"c": str(company)})


def test_the_app_role_sets_its_own_company_stage_only(session: Session) -> None:
    """D-78 with D-63: the API may change its own company's stage, nothing else there."""
    own, other = CompanyRow(name="Own"), CompanyRow(name="Other")
    session.add_all([own, other])
    session.flush()
    _as_app(session, own.id)
    changed = session.execute(
        text("UPDATE companies SET stage = 'pilot', updated_at = now() WHERE id = :id"),
        {"id": own.id},
    )
    assert changed.rowcount == 1
    elsewhere = session.execute(
        text("UPDATE companies SET stage = 'pilot' WHERE id = :id"), {"id": other.id}
    )
    assert elsewhere.rowcount == 0  # row-level security hides the other company


def test_the_app_role_cannot_rename_a_company(session: Session) -> None:
    own = CompanyRow(name="Own")
    session.add(own)
    session.flush()
    _as_app(session, own.id)
    with pytest.raises(DBAPIError, match="permission denied"):
        session.execute(text("UPDATE companies SET name = 'x' WHERE id = :id"), {"id": own.id})
