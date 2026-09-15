"""Revision 0026 names every stewardship's relationship by its code (#137's review)."""

from __future__ import annotations

import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from tests.conftest import on_an_empty_database
from tests.test_migration import _load

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"

KEPT = {
    "daughter": "daughter",
    "your daughter": "daughter",
    "Anak perempuan anda": "daughter",
    "您的女儿": "daughter",
    "son": "son",
    "husband": "spouse",
    "kakak atau adik perempuan anda": "sibling",
    "sister": "sibling",
    "your granddaughter": "grandchild",
    "Father": "other_family",
    "family": "other_family",
    "anak saudara lelaki anda": "other_family",
    "helper": "helper",
    "Jiran": "neighbour",
    "your friend": "friend",
    "best mate from school": "other",
}


async def test_0026_maps_the_phrases_it_knows_and_the_rest_to_other() -> None:
    migration = _load(VERSIONS / "0026_relationship_codes.py")

    def walk(connection: sa.Connection) -> None:
        # The two columns the revision reads and writes, as 0023 left them.
        meta = sa.MetaData()
        table = sa.Table(
            "stewardship",
            meta,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("relationship", sa.String(80), nullable=True),
        )
        meta.create_all(connection)
        ids = {phrase: uuid.uuid4() for phrase in KEPT}
        nobody = uuid.uuid4()
        for phrase, row_id in ids.items():
            connection.execute(table.insert().values(id=row_id, relationship=phrase))
        connection.execute(table.insert().values(id=nobody, relationship=None))

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        rows = {row_id: kept for row_id, kept in connection.execute(sa.select(table.c.id, table.c.relationship))}
        assert {phrase: rows[row_id] for phrase, row_id in ids.items()} == KEPT
        assert rows[nobody] is None

        # Down and up again: the codes stay codes.
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            migration.upgrade()
        again = {row_id: kept for row_id, kept in connection.execute(sa.select(table.c.id, table.c.relationship))}
        assert again == rows

    await on_an_empty_database(walk)
