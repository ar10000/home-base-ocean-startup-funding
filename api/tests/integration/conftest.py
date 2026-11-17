"""A real Postgres 16 per test session, through Testcontainers (handbook section 9)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from testcontainers.community.postgres import PostgresContainer

API_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("pgvector/pgvector:pg16", driver="psycopg") as pg:
        yield pg.get_connection_url()


@pytest.fixture
def engine(postgres_url: str) -> Iterator[Engine]:
    eng = create_engine(postgres_url)
    yield eng
    eng.dispose()


@pytest.fixture
def alembic_config(postgres_url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    cfg.attributes["configure_logger"] = False
    return cfg


KEYCLOAK_IMAGE = "quay.io/keycloak/keycloak:26.0.7"
REALM = API_DIR / "tests" / "fixtures" / "keycloak" / "realm.json"


@pytest.fixture(scope="session")
def keycloak_url() -> Iterator[str]:
    """A real Keycloak with the test realm (ADR-006), started once per session."""
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import LogMessageWaitStrategy

    container = (
        DockerContainer(KEYCLOAK_IMAGE)
        .with_command("start-dev --import-realm")
        .with_env("KC_BOOTSTRAP_ADMIN_USERNAME", "admin")
        .with_env("KC_BOOTSTRAP_ADMIN_PASSWORD", "test-only-not-a-secret")
        .with_volume_mapping(str(REALM), "/opt/keycloak/data/import/realm.json", "ro")
        .with_exposed_ports(8080)
        .waiting_for(LogMessageWaitStrategy("Running the server").with_startup_timeout(180))
    )
    with container:
        yield f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8080)}"
