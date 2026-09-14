"""E05-01, E05-02, E05-05, E05-06: the visit loop.

Six tables. `flag` is a safety row — a red-flag word heard, a medicine change heard for
E04's reconcile — written before anything is ranked and never shown as it stands. `brief` is the
pre-visit brief for one appointment as rendered, `question` one question to ask the doctor
(generated from a gap, a memo or a flag, or a person's own; superseded, never edited), `memo`
one line in his words filed against the next appointment, `visit_summary` what the doctor said
read from a transcript held in the object store, and `summary_item` one thing heard on it. The
four a person is shown carry `state_id`: the State snapshot each was rendered from.

Follows E04's medicines revision (0009_medicines). `confirm_subject` gains `question` and `visit_summary`, checked strings with no database
constraint, so no schema change there. `artifact_kind` gains `transcript` the same way.

Revision ID: 0010_visits
Revises: 0009_medicines
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_visits"
down_revision = "0009_medicines"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


FLAG_KIND = _enum("flag_kind", "red_flag", "medicine_change_heard")
QUESTION_SOURCE = _enum("question_source", "gap", "memo", "flag", "person")
MEMO_KIND = _enum("memo_kind", "action", "ask", "bring", "tell")
MEMO_SOURCE = _enum("memo_source", "visit", "conversation", "person")
ITEM_KIND = _enum("summary_item_kind", "action", "medication_change", "follow_up", "fact_heard")
ITEM_STATE = _enum("summary_item_state", "proposed", "confirmed", "rejected")


def _profile_column() -> sa.Column[sa.Uuid]:
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
    ("ix_flag_profile_id", "flag", ["profile_id"]),
    ("ix_flag_raised_at", "flag", ["raised_at"]),
    ("ix_brief_profile_id", "brief", ["profile_id"]),
    ("ix_brief_appointment_id", "brief", ["appointment_id"]),
    ("ix_brief_state_id", "brief", ["state_id"]),
    ("ix_brief_built_at", "brief", ["built_at"]),
    ("ix_question_profile_id", "question", ["profile_id"]),
    ("ix_question_appointment_id", "question", ["appointment_id"]),
    ("ix_question_state_id", "question", ["state_id"]),
    ("ix_question_created_at", "question", ["created_at"]),
    ("ix_memo_profile_id", "memo", ["profile_id"]),
    ("ix_memo_state_id", "memo", ["state_id"]),
    ("ix_memo_created_at", "memo", ["created_at"]),
    ("ix_visit_summary_profile_id", "visit_summary", ["profile_id"]),
    ("ix_visit_summary_appointment_id", "visit_summary", ["appointment_id"]),
    ("ix_visit_summary_artifact_id", "visit_summary", ["artifact_id"]),
    ("ix_visit_summary_state_id", "visit_summary", ["state_id"]),
    ("ix_visit_summary_created_at", "visit_summary", ["created_at"]),
    ("ix_summary_item_profile_id", "summary_item", ["profile_id"]),
    ("ix_summary_item_summary_id", "summary_item", ["summary_id"]),
)


def upgrade() -> None:
    op.create_table(
        "flag",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_column(),
        sa.Column("kind", FLAG_KIND, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=64), nullable=False),
        sa.Column("fact_ids", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=True),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=True),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_flag_profile_id_id"),
        _tied("flag", "artifact_id", "artifact"),
        _tied("flag", "appointment_id", "appointment"),
    )
    op.create_table(
        "brief",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_column(),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("since_state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=True),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_brief_profile_id_id"),
        _tied("brief", "appointment_id", "appointment"),
    )
    op.create_table(
        "question",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_column(),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("source", QUESTION_SOURCE, nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=True),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("slots", sa.JSON(), nullable=False),
        sa.Column("text", sa.String(length=120), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("added_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("removed", sa.Boolean(), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), sa.ForeignKey("question.id"), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_question_profile_id_id"),
        _tied("question", "appointment_id", "appointment"),
        _tied("question", "supersedes_id", "question"),
    )
    op.create_table(
        "memo",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_column(),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=True),
        sa.Column("kind", MEMO_KIND, nullable=False),
        sa.Column("source", MEMO_SOURCE, nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("slots", sa.JSON(), nullable=False),
        sa.Column("text", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), sa.ForeignKey("memo.id"), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_memo_profile_id_id"),
        _tied("memo", "appointment_id", "appointment"),
        _tied("memo", "supersedes_id", "memo"),
    )
    op.create_table(
        "visit_summary",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_column(),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("red_flag", sa.Boolean(), nullable=False),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_visit_summary_profile_id_id"),
        _tied("visit_summary", "appointment_id", "appointment"),
        _tied("visit_summary", "artifact_id", "artifact"),
    )
    op.create_table(
        "summary_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_column(),
        sa.Column("summary_id", sa.Uuid(), sa.ForeignKey("visit_summary.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", ITEM_KIND, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("span", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("text", sa.String(length=120), nullable=False),
        sa.Column("state", ITEM_STATE, nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("memo_id", sa.Uuid(), sa.ForeignKey("memo.id"), nullable=True),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=True),
        sa.Column("fact_id", sa.Uuid(), sa.ForeignKey("fact.id"), nullable=True),
        sa.Column("flag_id", sa.Uuid(), sa.ForeignKey("flag.id"), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_summary_item_profile_id_id"),
        _tied("summary_item", "summary_id", "visit_summary"),
        _tied("summary_item", "memo_id", "memo"),
        _tied("summary_item", "appointment_id", "appointment"),
        _tied("summary_item", "fact_id", "fact"),
        _tied("summary_item", "flag_id", "flag"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    for table in ("summary_item", "visit_summary", "memo", "question", "brief", "flag"):
        op.drop_table(table)
