import pytest

from home_base.core.db import DATABASE_URL_ENV, database_url


def test_database_url_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, "postgresql+psycopg://u:p@localhost/db")
    assert database_url() == "postgresql+psycopg://u:p@localhost/db"


@pytest.mark.parametrize("value", [None, ""])
def test_database_url_unset_or_empty_fails(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    else:
        monkeypatch.setenv(DATABASE_URL_ENV, value)
    with pytest.raises(RuntimeError, match=DATABASE_URL_ENV):
        database_url()
