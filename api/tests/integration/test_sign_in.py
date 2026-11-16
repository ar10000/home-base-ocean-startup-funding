"""Sign-in against a real Keycloak (ADR-006) and self sign-up of a company (D-64), on a
real Postgres. Only the database session is overridden: tokens, users and companies are
real."""

import base64
import json
from collections.abc import Iterator

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from home_base.api import auth, deps
from home_base.api.app import create_app
from home_base.modules.accounts.models import UserRow

pytestmark = pytest.mark.integration

PASSWORD = "test-only-not-a-secret"  # the fake test realm's password, not a secret


@pytest.fixture
def session(alembic_config: Config, engine: Engine) -> Iterator[Session]:
    command.upgrade(alembic_config, "head")
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture
def issuer(keycloak_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = f"{keycloak_url}/realms/home-base"
    monkeypatch.setenv(auth.ISSUER_ENV, url)
    monkeypatch.setenv(auth.AUDIENCE_ENV, "home-base-api")
    auth.verifier.cache_clear()
    yield url
    auth.verifier.cache_clear()


def _token(issuer: str, username: str) -> str:
    response = httpx.post(
        f"{issuer}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "home-base-web",
            "username": username,
            "password": PASSWORD,
        },
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def _client(session: Session, token: str | None = None) -> TestClient:
    app = create_app()
    app.dependency_overrides[deps.session] = lambda: session
    client = TestClient(app)
    if token:
        client.headers["authorization"] = f"Bearer {token}"
    return client


def _problem(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["type"].rsplit(":", 1)[-1]


def test_no_token_is_not_signed_in(session: Session, issuer: str) -> None:
    assert _problem(_client(session).get("/today")) == (401, "not-signed-in")
    assert _problem(_client(session, "not-a-token").get("/today")) == (401, "not-signed-in")


def test_a_tampered_token_is_refused(session: Session, issuer: str) -> None:
    header, payload, signature = _token(issuer, "founder-one").split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["sub"] = "someone-else"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    assert _problem(_client(session, f"{header}.{forged}.{signature}").get("/me")) == (
        401,
        "not-signed-in",
    )


def test_sign_in_not_configured_refuses_everything(
    session: Session, issuer: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _token(issuer, "founder-one")
    monkeypatch.delenv(auth.ISSUER_ENV)
    auth.verifier.cache_clear()
    assert _problem(_client(session, token).get("/me")) == (401, "not-signed-in")


def test_first_sign_in_creates_the_user_once_and_asks_for_onboarding(
    session: Session, issuer: str
) -> None:
    client = _client(session, _token(issuer, "founder-one"))
    me = client.get("/me").json()
    assert (me["company_id"], me["given_name"]) == (None, "Ana")
    assert client.get("/me").json()["user_id"] == me["user_id"]
    assert session.scalar(select(func.count()).select_from(UserRow)) == 1
    assert _problem(client.get("/today")) == (403, "not-onboarded")


def test_onboarding_creates_the_company_once(session: Session, issuer: str) -> None:
    client = _client(session, _token(issuer, "founder-one"))
    assert _problem(client.post("/onboarding", json={"company_name": "  "})) == (409, "onboarding")
    created = client.post("/onboarding", json={"company_name": "Blue Kelp Lda"})
    assert created.status_code == 201
    company = created.json()["company_id"]
    assert client.get("/me").json()["company_id"] == company
    assert _problem(client.post("/onboarding", json={"company_name": "Second Co"})) == (
        409,
        "onboarding",
    )
    assert client.get("/today").status_code == 200


def test_two_founders_get_separate_companies(session: Session, issuer: str) -> None:
    one = _client(session, _token(issuer, "founder-one"))
    two = _client(session, _token(issuer, "founder-two"))
    one.post("/onboarding", json={"company_name": "One Lda"})
    two.post("/onboarding", json={"company_name": "Two Lda"})
    one.post("/facts", json={"key": "country", "value": "PT", "label": "user_provided"})
    assert one.get("/me").json()["company_id"] != two.get("/me").json()["company_id"]
    assert two.get("/profile").json()["facts"] == []
    assert [f["key"] for f in one.get("/profile").json()["facts"]] == ["country"]
