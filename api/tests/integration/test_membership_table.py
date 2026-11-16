"""One company per founder (D-64, D-71): the database refuses a second membership for a
user, whichever company it names, so the rule holds even if onboarding is bypassed."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from home_base.modules.accounts.models import MembershipRow, UserRow
from home_base.modules.companies.models import CompanyRow

pytestmark = pytest.mark.integration


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


def _user_and_companies(session: Session) -> tuple[UserRow, CompanyRow, CompanyRow]:
    user = UserRow(keycloak_subject="sub-one-company")
    a, b = CompanyRow(name="A"), CompanyRow(name="B")
    session.add_all([user, a, b])
    session.flush()
    return user, a, b


def test_a_founder_has_one_membership(session: Session) -> None:
    user, a, _ = _user_and_companies(session)
    session.add(MembershipRow(user_id=user.id, company_id=a.id, role="founder"))
    session.flush()


def test_a_second_company_for_the_same_founder_is_refused(session: Session) -> None:
    user, a, b = _user_and_companies(session)
    session.add(MembershipRow(user_id=user.id, company_id=a.id, role="founder"))
    session.flush()
    session.add(MembershipRow(user_id=user.id, company_id=b.id, role="founder"))
    with pytest.raises(IntegrityError, match="uq_memberships_user"):
        session.flush()


def test_two_founders_can_each_have_a_company(session: Session) -> None:
    user, a, b = _user_and_companies(session)
    other = UserRow(keycloak_subject="sub-other")
    session.add(other)
    session.flush()
    session.add_all(
        [
            MembershipRow(user_id=user.id, company_id=a.id, role="founder"),
            MembershipRow(user_id=other.id, company_id=b.id, role="founder"),
        ]
    )
    session.flush()


def test_the_migration_downgrades_and_upgrades_again(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "aac7deecac27")
    command.upgrade(alembic_config, "head")
