"""E05-03, E05-04, E02-05, E03-05: the visit day — logistics, the consult recording, clips.

Two tables of profile data. `consult_recording` is one recording of one visit as kept: the
VOICE artefact (a consult, `Recording.CONSULT`), the transcript artefact the region's
transcriber heard in it, the RECORDING consent it rested on when the bytes landed, how long
the phone listened, the language the notice was spoken in and whether the doctor was named.
`consult_segment` is one stretch of it: who spoke (patient, doctor, family, unknown), from
when to when in seconds, and where those words are in the transcript by character offset —
never the words. Both are tied to their visit and their artefacts on the same profile.

Three tables gain columns. `visit_summary.recording_artifact_id`: the recording a card's
transcript was heard from. `summary_item.clip_start_s` and `clip_end_s`: where in that
recording the item was said. `task.appointment_id` and `task.errand`: a family task that is
part of a visit's logistics, "drive Pa to Dr Tan" (`errand` is `drive`).

`card_type` gains `visit_logistics` and `confirm_subject` gains `drive`: non-native enums with
no database constraint, so no schema change for them.

Follows main's head when this story was merged back (0017 → 0015_biography → 0019_row_scope
→ 0019_person_named_by → this); the operator repoints `down_revision` if another story lands first.

Revision ID: 0020_visit_day
Revises: 0019_person_named_by
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_visit_day"
down_revision = "0019_person_named_by"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


SPEAKER = _enum("consult_speaker", "patient", "doctor", "family", "unknown")
ERRAND = _enum("task_errand", "drive")


def _profile_id() -> sa.Column[sa.Uuid]:
    return sa.Column(
        "profile_id", sa.Uuid(), sa.ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )


def _row_of_profile(table: str) -> sa.UniqueConstraint:
    return sa.UniqueConstraint("profile_id", "id", name=f"uq_{table}_profile_id_id")


def _tied(table: str, column: str, referred: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["profile_id", column],
        [f"{referred}.profile_id", f"{referred}.id"],
        name=f"fk_{table}_{column.removesuffix('_id')}_profile",
    )


_INDEXES = (
    ("ix_consult_recording_profile_id", "consult_recording", ["profile_id"]),
    ("ix_consult_recording_appointment_id", "consult_recording", ["appointment_id"]),
    ("ix_consult_recording_artifact_id", "consult_recording", ["artifact_id"]),
    ("ix_consult_recording_started_at", "consult_recording", ["started_at"]),
    ("ix_consult_segment_profile_id", "consult_segment", ["profile_id"]),
    ("ix_consult_segment_recording_id", "consult_segment", ["recording_id"]),
)


def _has(table: str) -> bool:
    """Whether a table is there. The migration test runs every revision but one in order, so a
    revision that widens another story's table says so rather than assuming it."""
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    op.create_table(
        "consult_recording",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=False),
        sa.Column(
            "transcript_artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=True
        ),
        sa.Column("consent_id", sa.Uuid(), sa.ForeignKey("consent.id"), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notice_language", sa.String(length=16), nullable=False),
        sa.Column("doctor_named", sa.Boolean(), nullable=False),
        sa.Column("heard_confidence", sa.Float(), nullable=True),
        sa.Column(
            "recorded_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False
        ),
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=False),
        _row_of_profile("consult_recording"),
        _tied("consult_recording", "appointment_id", "appointment"),
        _tied("consult_recording", "artifact_id", "artifact"),
        _tied("consult_recording", "transcript_artifact_id", "artifact"),
    )
    op.create_table(
        "consult_segment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column(
            "recording_id", sa.Uuid(), sa.ForeignKey("consult_recording.id"), nullable=False
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("speaker", SPEAKER, nullable=False),
        sa.Column("start_s", sa.Float(), nullable=False),
        sa.Column("end_s", sa.Float(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        _row_of_profile("consult_segment"),
        _tied("consult_segment", "recording_id", "consult_recording"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)
    if _has("visit_summary"):
        _widen_the_summary()
    if _has("task"):
        _widen_the_task()


def _widen_the_summary() -> None:
    with op.batch_alter_table("visit_summary") as summary:
        summary.add_column(sa.Column("recording_artifact_id", sa.Uuid(), nullable=True))
        summary.create_foreign_key(
            "fk_visit_summary_recording_artifact_id_artifact",
            "artifact",
            ["recording_artifact_id"],
            ["id"],
        )
        summary.create_foreign_key(
            "fk_visit_summary_recording_artifact_profile",
            "artifact",
            ["profile_id", "recording_artifact_id"],
            ["profile_id", "id"],
        )
    with op.batch_alter_table("summary_item") as item:
        item.add_column(sa.Column("clip_start_s", sa.Float(), nullable=True))
        item.add_column(sa.Column("clip_end_s", sa.Float(), nullable=True))


def _widen_the_task() -> None:
    with op.batch_alter_table("task") as task:
        task.add_column(sa.Column("appointment_id", sa.Uuid(), nullable=True))
        task.add_column(sa.Column("errand", ERRAND, nullable=True))
        task.create_foreign_key(
            "fk_task_appointment_id_appointment", "appointment", ["appointment_id"], ["id"]
        )
        task.create_foreign_key(
            "fk_task_appointment_profile",
            "appointment",
            ["profile_id", "appointment_id"],
            ["profile_id", "id"],
        )


def downgrade() -> None:
    if _has("task"):
        with op.batch_alter_table("task") as task:
            task.drop_constraint("fk_task_appointment_profile", type_="foreignkey")
            task.drop_constraint("fk_task_appointment_id_appointment", type_="foreignkey")
            task.drop_column("errand")
            task.drop_column("appointment_id")
    if _has("visit_summary"):
        with op.batch_alter_table("summary_item") as item:
            item.drop_column("clip_end_s")
            item.drop_column("clip_start_s")
        with op.batch_alter_table("visit_summary") as summary:
            summary.drop_constraint(
                "fk_visit_summary_recording_artifact_profile", type_="foreignkey"
            )
            summary.drop_constraint(
                "fk_visit_summary_recording_artifact_id_artifact", type_="foreignkey"
            )
            summary.drop_column("recording_artifact_id")
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table("consult_segment")
    op.drop_table("consult_recording")
