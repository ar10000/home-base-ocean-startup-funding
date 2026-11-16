"""Accounts: users from sign-in, and self sign-up of a company (ADR-006, D-63, D-64).

A user is created the first time a valid token arrives. A user with no company is not
yet onboarded; onboarding creates the company and makes the user its founder, in one
audited transaction. Runs with the owner's rights, before the request switches to the
app role (users and memberships are not readable by it).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from home_base.core.context import Clock
from home_base.core.errors import OnboardingError
from home_base.modules.accounts.models import MembershipRow, UserRow
from home_base.modules.audit.domain import Actor, AuditEntry
from home_base.modules.audit.repository import AuditRepository
from home_base.modules.companies.models import CompanyRow


def user_for_subject(session: Session, subject: str, clock: Clock) -> uuid.UUID:
    """The user for a Keycloak subject, created on first sign-in."""
    found = session.scalars(
        select(UserRow).where(UserRow.keycloak_subject == subject)
    ).one_or_none()
    if found is not None:
        return found.id
    user = UserRow(keycloak_subject=subject, created_at=clock.at, updated_at=clock.at)
    session.add(user)
    session.flush()
    return user.id


def company_of(session: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    """The user's company, or None before onboarding (one company per founder, D-64)."""
    return session.scalars(
        select(MembershipRow.company_id).where(MembershipRow.user_id == user_id)
    ).one_or_none()


def onboard(session: Session, user_id: uuid.UUID, company_name: str, clock: Clock) -> uuid.UUID:
    """Create the user's company and make them its founder."""
    name = company_name.strip()
    if not name:
        raise OnboardingError("the company needs a name")
    # Lock the user, so two onboarding requests at once cannot create two companies.
    session.execute(select(UserRow.id).where(UserRow.id == user_id).with_for_update())
    if company_of(session, user_id) is not None:
        raise OnboardingError("you already have a company")
    company = CompanyRow(name=name, created_at=clock.at, updated_at=clock.at)
    session.add(company)
    session.flush()
    session.add(MembershipRow(user_id=user_id, company_id=company.id, role="founder"))
    AuditRepository(session, company.id).record(
        AuditEntry(
            actor=Actor.FOUNDER,
            actor_id=user_id,
            action="company.created",
            entity="company",
            entity_id=company.id,
            occurred_at=clock.at,
            request_id=clock.request_id,
        )
    )
    session.flush()
    return company.id
