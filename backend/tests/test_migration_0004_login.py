"""Revision 0004 writes the `profile` scope into every key that was cut before it existed."""

from __future__ import annotations

import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from tests.conftest import on_an_empty_database
from tests.test_migration import _load

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
BEFORE = (
    "0001_accounts_profiles_and_keys",
    "0002_audit_entry",
    "0003_memory_stores",
    "0003_consent_record",
    "0004_key_consent",
)


def _keys() -> sa.TableClause:
    return sa.table("key", sa.column("id", sa.Uuid()), sa.column("scopes", sa.JSON()))


async def test_0004_backfills_profile_into_existing_key_scopes_and_takes_it_back_out() -> None:
    before = [_load(VERSIONS / f"{name}.py") for name in BEFORE]
    login = _load(VERSIONS / "0004_login_and_sessions.py")

    def walk(connection: sa.Connection) -> None:
        for migration in before:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()

        # A person, his profile, and a caregiver key cut before the profile scope existed.
        pa, daughter, profile, key = (uuid.uuid4() for _ in range(4))
        person = sa.table(
            "person",
            sa.column("id", sa.Uuid()),
            sa.column("region", sa.String()),
            sa.column("display_name", sa.String()),
            sa.column("language", sa.String()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        )
        profiles = sa.table(
            "profile",
            sa.column("id", sa.Uuid()),
            sa.column("region", sa.String()),
            sa.column("display_name", sa.String()),
            sa.column("language", sa.String()),
            sa.column("owner_person_id", sa.Uuid()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        )
        keys = sa.table(
            "key",
            sa.column("id", sa.Uuid()),
            sa.column("profile_id", sa.Uuid()),
            sa.column("holder_person_id", sa.Uuid()),
            sa.column("role", sa.String()),
            sa.column("scopes", sa.JSON()),
            sa.column("granted_by_person_id", sa.Uuid()),
            sa.column("granted_at", sa.DateTime(timezone=True)),
        )
        now = sa.func.now()
        for person_id, name in ((pa, "Pa"), (daughter, "Daughter")):
            connection.execute(
                person.insert().values(
                    id=person_id, region="SG", display_name=name, language="en", created_at=now
                )
            )
        connection.execute(
            profiles.insert().values(
                id=profile,
                region="SG",
                display_name="Pa",
                language="en",
                owner_person_id=pa,
                created_at=now,
            )
        )
        connection.execute(
            keys.insert().values(
                id=key,
                profile_id=profile,
                holder_person_id=daughter,
                role="caregiver",
                scopes=["medicines", "visits"],
                granted_by_person_id=pa,
                granted_at=now,
            )
        )

        with Operations.context(MigrationContext.configure(connection)):
            login.upgrade()
        held = connection.execute(sa.select(_keys().c.scopes)).scalar_one()
        assert held == ["medicines", "profile", "visits"]

        with Operations.context(MigrationContext.configure(connection)):
            login.downgrade()
        held = connection.execute(sa.select(_keys().c.scopes)).scalar_one()
        assert held == ["medicines", "visits"]

    await on_an_empty_database(walk)
