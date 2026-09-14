"""The migration and the models must agree.

Migrations are never deleted, so the only way the two drift apart is a column added to one
and not the other. This runs 0001 against an empty database and checks the tables it builds
against the tables the models declare.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Table, create_engine, inspect

from app.identity.models import Person, Profile
from app.keys.models import Key

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migration() -> ModuleType:
    return _load("0001_accounts_profiles_and_keys")


def test_the_first_migration_builds_the_tables_the_models_declare(migration: ModuleType) -> None:
    tables: tuple[Table, ...] = (Person.__table__, Profile.__table__, Key.__table__)
    engine = create_engine("sqlite+pysqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

        built = inspect(connection)
        assert set(built.get_table_names()) == {table.name for table in tables}
        for table in tables:
            assert {column["name"] for column in built.get_columns(table.name)} == {
                column.name for column in table.columns
            }

        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert inspect(connection).get_table_names() == []
    engine.dispose()
