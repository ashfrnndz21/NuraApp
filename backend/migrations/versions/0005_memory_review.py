"""E00-03: what the safety review of the memory stores asked of the tables.

Provenance is tied to the profile at the table, not only at the service: `(profile_id,
artifact_id)` on event and fact points at `artifact(profile_id, id)`, and the same for
`event_id`, `episode_id`, `supersedes_id` and `provider_id`, with the `(profile_id, id)`
uniques those keys need. The single-column keys 0003 shipped stay; these are added beside
them. An event says where it came in from (`source_channel`), an appointment says who
confirmed it (`confirmed_by_person_id`), and a fact says who confirmed or disputed it
(`confirmed_by_person_id`, nullable: an extraction names nobody); a change of an
appointment's status names who confirmed the step (`status_changed_by_person_id`). The
person named is the creator of a `confirmation` row — the new table here: a yes the surface
wrote down, from the person asking only, for one act bound by a digest of its content, good
for ten minutes, used once — the spend is a conditional UPDATE on `consumed_at IS NULL`.

The event and appointment columns are NOT NULL and neither has a default, because a default
would invent a source or a confirmer. `source_channel` is filled from the artefact where an
event names one; an event with no artefact, or an appointment, that is already in the table
has no honest value, and the upgrade stops rather than make one up. Precondition for an
environment holding rows: none in `appointment`, none in `event` without an artefact.

This revision follows the login revision, so the chain reads in order: 0001, 0002, 0003_memory,
0003_consent, 0004_key_consent, 0004_login_and_sessions, 0005_memory_review. Every change is a
batch operation so it runs on SQLite (the tests) as well as Postgres; on
Postgres the batch is a plain ALTER TABLE.

Revision ID: 0005_memory_review
Revises: 0004_login_and_sessions
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_memory_review"
down_revision = "0004_login_and_sessions"
branch_labels = None
depends_on = None

SOURCE_CHANNEL = sa.Enum(
    "app",
    "whatsapp",
    "connector",
    "device",
    "clinic",
    name="source_channel",
    native_enum=False,
    length=32,
)

CONFIRM_SUBJECT = sa.Enum(
    "fact",
    "appointment",
    "appointment_status",
    name="confirm_subject",
    native_enum=False,
    length=32,
)
AUDIT_CHANNEL = sa.Enum(
    "app",
    "whatsapp",
    "share_link",
    "clinic",
    "system",
    name="audit_channel",
    native_enum=False,
    length=32,
)
CONFIRMED_BY = "fk_appointment_confirmed_by_person"
STATUS_CHANGED_BY = "fk_appointment_status_changed_by_person"
FACT_CONFIRMED_BY = "fk_fact_confirmed_by_person"

_ROW_OF_PROFILE = ("artifact", "event", "episode", "fact", "provider", "appointment")
"""The tables another row may be tied to, or will be (E05 hangs off appointment): each gets a
unique on (profile_id, id)."""

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


def _refuse_if_kept(table: str, column: str) -> None:
    """Stop rather than drop a person's word, or where an event came from, on the way down."""
    held = op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL"))
    if held:
        raise RuntimeError(
            f"{held} row(s) in {table} carry a {column} that this downgrade would drop; "
            "that is a person's word or an event's source, and it is not thrown away by a "
            "migration — move it out by hand first"
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
        batch.create_foreign_key(CONFIRMED_BY, "person", ["confirmed_by_person_id"], ["id"])

    with op.batch_alter_table("appointment") as batch:
        batch.add_column(sa.Column("status_changed_by_person_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            STATUS_CHANGED_BY, "person", ["status_changed_by_person_id"], ["id"]
        )

    with op.batch_alter_table("fact") as batch:
        batch.add_column(sa.Column("confirmed_by_person_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(FACT_CONFIRMED_BY, "person", ["confirmed_by_person_id"], ["id"])

    op.create_table(
        "confirmation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("subject", CONFIRM_SUBJECT, nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        # sha256 of the canonical JSON of what the person was shown (app.drafts.digest_of).
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel", AUDIT_CHANNEL, nullable=False),
    )
    op.create_index("ix_confirmation_profile_id", "confirmation", ["profile_id"])
    op.create_index("ix_confirmation_person_id", "confirmation", ["person_id"])


def downgrade() -> None:
    # The mirror of the upgrade: as it will not invent a source or a confirmer, this will not
    # drop one. On a database holding any of them, the downgrade stops.
    _refuse_if_kept("confirmation", "consumed_at")
    _refuse_if_kept("fact", "confirmed_by_person_id")
    _refuse_if_kept("appointment", "status_changed_by_person_id")
    _refuse_if_kept("appointment", "confirmed_by_person_id")
    _refuse_if_kept("event", "source_channel")

    op.drop_index("ix_confirmation_person_id", table_name="confirmation")
    op.drop_index("ix_confirmation_profile_id", table_name="confirmation")
    op.drop_table("confirmation")

    with op.batch_alter_table("fact") as batch:
        batch.drop_constraint(FACT_CONFIRMED_BY, type_="foreignkey")
        batch.drop_column("confirmed_by_person_id")
    with op.batch_alter_table("appointment") as batch:
        batch.drop_constraint(STATUS_CHANGED_BY, type_="foreignkey")
        batch.drop_column("status_changed_by_person_id")
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
