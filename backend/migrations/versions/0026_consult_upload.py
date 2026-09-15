"""#129: a consult recording sent in chunks as it is made.

One table of profile data, tied to its profile the way the visit tables are (0022).
`consult_upload` is a recording on its way in: which visit, the RECORDING consent it was opened
on, who opened it, the recorder's container, when the phone began listening, how many chunks
and bytes have arrived, and when the doctor said yes. It ends put together into a
`consult_recording` (`recording_id`, `finished_at`) or thrown away (`discarded_at`,
`discarded_because`: no, left, no_answer, unfinished, no_consent). The chunks themselves are
bytes in the region's object store, never a column, and are let go of either way. The row
holds no words and no audio.

Revision ID: 0026_consult_upload
Revises: 0025_family_story
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_consult_upload"
down_revision = "0025_family_story"
branch_labels = None
depends_on = None


def _tied(table: str, column: str, referred: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["profile_id", column],
        [f"{referred}.profile_id", f"{referred}.id"],
        name=f"fk_{table}_{column.removesuffix('_id')}_profile",
    )


_INDEXES = (
    ("ix_consult_upload_profile_id", "consult_upload", ["profile_id"]),
    ("ix_consult_upload_appointment_id", "consult_upload", ["appointment_id"]),
)


def upgrade() -> None:
    op.create_table(
        "consult_upload",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=False),
        sa.Column("consent_id", sa.Uuid(), sa.ForeignKey("consent.id"), nullable=False),
        sa.Column("started_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chunks", sa.Integer(), nullable=False),
        sa.Column("received_bytes", sa.Integer(), nullable=False),
        sa.Column("doctor_said_yes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discarded_because", sa.String(16), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "recording_id", sa.Uuid(), sa.ForeignKey("consult_recording.id"), nullable=True
        ),
        sa.UniqueConstraint("profile_id", "id", name="uq_consult_upload_profile_id_id"),
        _tied("consult_upload", "appointment_id", "appointment"),
        _tied("consult_upload", "recording_id", "consult_recording"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table("consult_upload")
