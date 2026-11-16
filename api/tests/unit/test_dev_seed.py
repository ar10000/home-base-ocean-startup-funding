"""The local seed script refuses any database that is not on this machine."""

import importlib.util
from pathlib import Path

import pytest

# Found by walking up, so it also works from mutmut's copy of the tests (api/mutants/).
SCRIPT = next(
    p / "scripts" / "dev_seed.py"
    for p in Path(__file__).resolve().parents
    if (p / "scripts" / "dev_seed.py").exists()
)
spec = importlib.util.spec_from_file_location("dev_seed", SCRIPT)
assert spec and spec.loader
dev_seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev_seed)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@127.0.0.1:54320/home_base",
        "postgresql+psycopg://u:p@localhost/home_base",
        "postgresql://u:p@[::1]:5432/db",
    ],
)
def test_local_databases_are_allowed(url: str) -> None:
    assert dev_seed.is_local(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@db.example.invalid:5432/home_base",
        "postgresql+psycopg://u:p@localhost.example.invalid/home_base",
        "postgresql+psycopg://u:p@10.0.0.5/home_base",
        "postgresql+psycopg:///home_base",
    ],
)
def test_other_databases_are_refused(url: str) -> None:
    assert not dev_seed.is_local(url)


def test_main_refuses_a_remote_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_BASE_DATABASE_URL", "postgresql+psycopg://u:p@db.example.invalid/x")
    assert dev_seed.main([]) == 2
