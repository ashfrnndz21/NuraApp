"""The migrations and the models must agree.

Migrations are never deleted, so the only way the two drift apart is a column added to one
and not the other. This loads every revision in the directory, runs them in dependency
order against an empty database, and checks the tables they build against the tables the
models declare.

Two stories built side by side each branch from the same revision, so the directory can hold
more than one head at a time. That is allowed here; the operator joins the heads with a merge
revision. What is not allowed is a revision that names a parent the directory does not hold.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Inspector, Table, create_engine, inspect

from app.audit.models import AuditEntry
from app.identity.models import Person, Profile
from app.keys.models import Key
from app.memory.models import Appointment, Artifact, Episode, Event, Fact, Provider

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"

TABLES: tuple[Table, ...] = (
    Person.__table__,
    Profile.__table__,
    Key.__table__,
    AuditEntry.__table__,
    Artifact.__table__,
    Event.__table__,
    Fact.__table__,
    Episode.__table__,
    Provider.__table__,
    Appointment.__table__,
)


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parents(module: ModuleType) -> tuple[str, ...]:
    """A merge revision names several parents; every other revision names one or none."""
    down = module.down_revision
    if down is None:
        return ()
    return (down,) if isinstance(down, str) else tuple(down)


@pytest.fixture
def revisions() -> dict[str, ModuleType]:
    found = {module.revision: module for module in map(_load, sorted(VERSIONS.glob("*.py")))}
    assert found, "no migrations found"
    return found


def _in_order(revisions: dict[str, ModuleType]) -> tuple[ModuleType, ...]:
    """Every revision after all of its parents; siblings by file name, so the run is stable."""
    applied: list[str] = []
    waiting = dict(revisions)
    while waiting:
        ready = sorted(
            (rev for rev, module in waiting.items() if set(_parents(module)) <= set(applied)),
            key=lambda rev: revisions[rev].__name__,
        )
        assert ready, f"these revisions never become applicable: {sorted(waiting)}"
        applied.extend(ready)
        for rev in ready:
            del waiting[rev]
    return tuple(revisions[rev] for rev in applied)


def test_every_revision_links_to_one_the_directory_holds(
    revisions: dict[str, ModuleType],
) -> None:
    roots = [rev for rev, module in revisions.items() if not _parents(module)]
    assert roots == ["0001_accounts"]
    for module in revisions.values():
        for parent in _parents(module):
            assert parent in revisions, f"{module.revision} revises {parent}, which is not here"


def _tied(built: Inspector, table: Table) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    """Every foreign key on the built table, as (columns, referred table, referred columns)."""
    return {
        (
            tuple(key["constrained_columns"]),
            key["referred_table"],
            tuple(key["referred_columns"]),
        )
        for key in built.get_foreign_keys(table.name)
    }


def _tied_by_model(table: Table) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(element.parent.name for element in key.elements),
            key.referred_table.name,
            tuple(element.column.name for element in key.elements),
        )
        for key in table.foreign_key_constraints
    }


def test_the_migrations_build_the_tables_the_models_declare(
    revisions: dict[str, ModuleType],
) -> None:
    ordered = _in_order(revisions)
    engine = create_engine("sqlite+pysqlite://")
    with engine.begin() as connection:
        for migration in ordered:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()

        built = inspect(connection)
        assert set(built.get_table_names()) >= {table.name for table in TABLES}
        for table in TABLES:
            assert {column["name"] for column in built.get_columns(table.name)} == {
                column.name for column in table.columns
            }, table.name
            assert {
                column["name"] for column in built.get_columns(table.name) if column["nullable"]
            } == {column.name for column in table.columns if column.nullable}, table.name

        # The ties that keep provenance on the profile survive the batch rewrite (0004), and
        # so do the checks 0003 put on the fact table.
        for table in (Artifact, Event, Fact, Episode, Provider, Appointment):
            assert _tied(built, table.__table__) == _tied_by_model(table.__table__), table.name
        assert {check["name"] for check in built.get_check_constraints("fact")} >= {
            "ck_fact_has_provenance",
            "ck_fact_confidence",
        }

        for migration in reversed(ordered):
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
        assert inspect(connection).get_table_names() == []
    engine.dispose()
