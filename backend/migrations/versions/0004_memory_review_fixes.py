"""E00-03: what the safety review of the memory stores asked of the tables.

Provenance is tied to the profile at the table, not only at the service: `(profile_id,
artifact_id)` on event and fact points at `artifact(profile_id, id)`, and the same for
`event_id`, `episode_id`, `supersedes_id` and `provider_id`, with the `(profile_id, id)`
uniques those keys need. The single-column keys 0003 shipped stay; these are added beside
them. An event says where it came in from (`source_channel`), and an appointment says who
confirmed it (`confirmed_by_person_id`).

Both new columns are NOT NULL and neither has a default, because a default would invent a
source or a confirmer. `source_channel` is filled from the artefact where an event names one;
an event with no artefact, or an appointment, that is already in the table has no honest
value, and the upgrade stops rather than make one up.

Every change is a batch operation so it runs on SQLite (the tests) as well as Postgres; on
Postgres the batch is a plain ALTER TABLE.

Revision ID: 0004_memory_review
Revises: 0003_memory
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_memory_review"
down_revision = "0003_memory"
branch_labels = None
depends_on = None

SOURCE_CHANNEL = sa.Enum(
    "app", "whatsapp", "connector", "device", "clinic",
    name="source_channel", native_enum=False, length=32
)

CONFIRMED_BY = "fk_appointment_confirmed_by_person"

_ROW_OF_PROFILE = ("artifact", "event", "episode", "fact", "provider")
"""The tables another row may be tied to: each gets a unique on (profile_id, id)."""

_TIED = (
    ("event", "artifact_id", "artifact"),
    ("event", "episode_id", "episode"),
    ("fact", "artifact_id", "artifact"),
    ("fact", "event_id", "event"),
    ("fact", "episode_id", "episode"),
    ("fact", "supersedes_id", "fact"),
    ("appointment", "provider_id", "provider"),
    ("appointment", "episode_id", "episode"),
)
"""(table, column, referred table): the reference carries the profile with it."""


def _unique(table: str) -> str:
    return f"uq_{table}_profile_id_id"


def _tie(table: str, column: str) -> str:
    return f"fk_{table}_{column.removesuffix('_id')}_profile"


def _refuse_if_any(table: str, column: str) -> None:
    """Stop rather than invent a value for rows that predate the column."""
    left = op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table} WHERE {column} IS NULL"))
    if left:
        raise RuntimeError(
            f"{left} row(s) in {table} have no {column} and there is no honest value to give "
            "them; sort them out by hand before upgrading"
        )


def upgrade() -> None:
    for table in _ROW_OF_PROFILE:
        with op.batch_alter_table(table) as batch:
            batch.create_unique_constraint(_unique(table), ["profile_id", "id"])

    for table, column, referred in _TIED:
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                _tie(table, column),
                referred,
                ["profile_id", column],
                ["profile_id", "id"],
            )

    with op.batch_alter_table("event") as batch:
        batch.add_column(sa.Column("source_channel", SOURCE_CHANNEL, nullable=True))
    op.execute(
        "UPDATE event SET source_channel = "
        "(SELECT artifact.source_channel FROM artifact WHERE artifact.id = event.artifact_id) "
        "WHERE artifact_id IS NOT NULL"
    )
    _refuse_if_any("event", "source_channel")
    with op.batch_alter_table("event") as batch:
        batch.alter_column("source_channel", existing_type=SOURCE_CHANNEL, nullable=False)

    with op.batch_alter_table("appointment") as batch:
        batch.add_column(sa.Column("confirmed_by_person_id", sa.Uuid(), nullable=True))
    _refuse_if_any("appointment", "confirmed_by_person_id")
    with op.batch_alter_table("appointment") as batch:
        batch.alter_column("confirmed_by_person_id", existing_type=sa.Uuid(), nullable=False)
        batch.create_foreign_key(
            CONFIRMED_BY, "person", ["confirmed_by_person_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("appointment") as batch:
        batch.drop_constraint(CONFIRMED_BY, type_="foreignkey")
        batch.drop_column("confirmed_by_person_id")
    with op.batch_alter_table("event") as batch:
        batch.drop_column("source_channel")

    for table, column, _ in reversed(_TIED):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(_tie(table, column), type_="foreignkey")

    for table in reversed(_ROW_OF_PROFILE):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(_unique(table), type_="unique")
