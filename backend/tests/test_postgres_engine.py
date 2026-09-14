"""The engine a deployment gets on Postgres, and the URL it is given.

The SQLite busy-wait (`app.db.make_engine`: BEGIN IMMEDIATE and a lock timeout) exists for a
laptop's one-file database; on Postgres it must not run — Postgres writers wait on row locks,
and `BEGIN IMMEDIATE` is not Postgres. These tests build the engine without connecting, so they
run in the SQLite suite too; the `backend-postgres` CI job runs the rest of the suite on a real
Postgres through `NURA_TEST_DATABASE_URL`.
"""

from __future__ import annotations

from sqlalchemy import event

from app.db import _begin_immediate, _no_implicit_begin, make_engine
from app.settings import database_url_for, load_settings


def test_a_platform_url_is_given_the_asyncpg_driver() -> None:
    assert (
        database_url_for("postgres://nura:pw@db.internal:5432/nura")
        == "postgresql+asyncpg://nura:pw@db.internal:5432/nura"
    )
    assert (
        database_url_for("postgresql://nura:pw@db.internal/nura")
        == "postgresql+asyncpg://nura:pw@db.internal/nura"
    )


def test_libpq_sslmode_becomes_asyncpg_ssl() -> None:
    assert (
        database_url_for("postgres://u:p@h/db?sslmode=require")
        == "postgresql+asyncpg://u:p@h/db?ssl=require"
    )
    assert (
        database_url_for("postgresql://u:p@h/db?application_name=nura&sslmode=verify-full")
        == "postgresql+asyncpg://u:p@h/db?application_name=nura&ssl=verify-full"
    )


def test_other_urls_are_left_as_given() -> None:
    for url in (
        "sqlite+aiosqlite:///./dev.db",
        "sqlite+aiosqlite://",
        "postgresql+asyncpg://u:p@h/db",
    ):
        assert database_url_for(url) == url


def test_settings_read_the_url_through_the_same_door() -> None:
    settings = load_settings({"NURA_REGION": "SG", "NURA_DATABASE_URL": "postgres://u:p@h/db"})
    assert settings.database_url == "postgresql+asyncpg://u:p@h/db"


def test_the_sqlite_busy_wait_is_not_installed_on_postgres() -> None:
    engine = make_engine("postgresql+asyncpg://u:p@db.invalid/nura")
    assert engine.dialect.name == "postgresql"
    assert not event.contains(engine.sync_engine, "begin", _begin_immediate)
    assert not event.contains(engine.sync_engine, "connect", _no_implicit_begin)
    assert engine.pool._pre_ping  # type: ignore[attr-defined]


def test_the_sqlite_busy_wait_is_installed_on_sqlite() -> None:
    engine = make_engine("sqlite+aiosqlite://")
    assert event.contains(engine.sync_engine, "begin", _begin_immediate)
    assert event.contains(engine.sync_engine, "connect", _no_implicit_begin)
