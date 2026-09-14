"""E03: the timeline — artefacts hanging off episodes and visits, the chief's notes about a
clinic, and when each person last looked at what changed.

Three tables of profile data, every row tied to its profile the way the memory tables are
(0005): an attachment's `(profile_id, artifact_id)` points at `artifact(profile_id, id)` and
its episode or visit at the same profile's; a note's provider likewise. An attachment hangs
off exactly one thing (`ck_attachment_hangs_off_one_thing`) and the same artefact hangs off
the same thing once. A provider note is the second short free-text column the graph allows,
beside the patient's own note (0001), and is refused by the service when it names a
medicine or a condition. A look is a row per look, never edited.

Branches from E02's capture revision (0018), main's head when this story was cut; the
operator repoints `down_revision` at merge if another story lands first.

Revision ID: 0016_timeline
Revises: 0018_capture_extras
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_timeline"
down_revision = "0018_capture_extras"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


ATTACHED_HOW = _enum("attached_how", "manual", "ingestion")


def _profile_id() -> sa.Column[sa.Uuid]:
    return sa.Column(
        "profile_id", sa.Uuid(), sa.ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )


def _tied(table: str, column: str, referred: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["profile_id", column],
        [f"{referred}.profile_id", f"{referred}.id"],
        name=f"fk_{table}_{column.removesuffix('_id')}_profile",
    )


_INDEXES = (
    ("ix_attachment_profile_id", "attachment", ["profile_id"]),
    ("ix_attachment_artifact_id", "attachment", ["artifact_id"]),
    ("ix_attachment_attached_at", "attachment", ["attached_at"]),
    ("ix_provider_note_profile_id", "provider_note", ["profile_id"]),
    ("ix_provider_note_provider_id", "provider_note", ["provider_id"]),
    ("ix_provider_note_written_at", "provider_note", ["written_at"]),
    ("ix_last_looked_profile_id", "last_looked", ["profile_id"]),
    ("ix_last_looked_person_id", "last_looked", ["person_id"]),
    ("ix_last_looked_looked_at", "last_looked", ["looked_at"]),
)


def upgrade() -> None:
    op.create_table(
        "attachment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=False),
        sa.Column("episode_id", sa.Uuid(), sa.ForeignKey("episode.id"), nullable=True),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=True),
        sa.Column("how", ATTACHED_HOW, nullable=False),
        sa.Column("attached_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_attachment_profile_id_id"),
        sa.CheckConstraint(
            "(episode_id IS NULL) <> (appointment_id IS NULL)",
            name="ck_attachment_hangs_off_one_thing",
        ),
        sa.UniqueConstraint(
            "profile_id", "artifact_id", "episode_id", "appointment_id", name="uq_attachment_once"
        ),
        _tied("attachment", "artifact_id", "artifact"),
        _tied("attachment", "episode_id", "episode"),
        _tied("attachment", "appointment_id", "appointment"),
    )
    op.create_table(
        "provider_note",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("provider_id", sa.Uuid(), sa.ForeignKey("provider.id"), nullable=False),
        # A line about the place, in the chief's words. Never health content: the service
        # refuses a note naming a medicine or a condition.
        sa.Column("text", sa.String(length=280), nullable=False),
        sa.Column("written_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_provider_note_profile_id_id"),
        _tied("provider_note", "provider_id", "provider"),
    )
    op.create_table(
        "last_looked",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("looked_at", sa.DateTime(timezone=True), nullable=False),
        # The spine as seen at the look, id to status: nothing of what the visits were.
        sa.Column("appointments", sa.JSON(), nullable=False),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    for table in ("last_looked", "provider_note", "attachment"):
        op.drop_table(table)
