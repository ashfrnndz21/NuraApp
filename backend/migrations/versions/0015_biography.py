"""E01: onboarding — the profile's settings, the health biography, the first week.

Six tables of profile data, every reference tied to its profile the way the memory tables
are (0005). `profile_settings` is one row per save of the settings screen, superseded by the
next and resting on the event of the save. `biography_session` is one sitting, stamped once
with its read-back and once with its close. `biography_paper` names a photo and the review
card it was read into (0008), with the kind of paper the person said it was.
`biography_line` is one read-back line as answered, naming the fact it read back and, for a
"no", the dispute it opened. `activation_plan` and `plan_prompt` are the first week: one
prompt a day for a gap, due at breakfast on his clock, pending until done or skipped.

`event_kind` gains `onboarding`; it is a non-native enum with no database constraint, so no
column changes for it (as 0010 did for `engagement`).

Follows E02's capture revision (0018), main's head when this story was merged back; the
operator repoints `down_revision` again if another story lands first.

Revision ID: 0015_biography
Revises: 0018_capture_extras
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_biography"
down_revision = "0018_capture_extras"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


DENSITY = _enum("density", "detailed", "simple")
PAPER_KIND = _enum(
    "paper_kind", "discharge_letter", "lab_result", "medicine", "clinic_card", "insurance_card"
)
ANSWER = _enum("read_back_answer", "yes", "no")
PROMPT_STATUS = _enum("plan_prompt_status", "pending", "done", "skipped")


def _profile_id() -> sa.Column:
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


def _when(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


_INDEXES = (
    ("ix_profile_settings_profile_id", "profile_settings", ["profile_id"]),
    ("ix_profile_settings_set_at", "profile_settings", ["set_at"]),
    ("ix_biography_session_profile_id", "biography_session", ["profile_id"]),
    ("ix_biography_session_opened_at", "biography_session", ["opened_at"]),
    ("ix_biography_paper_profile_id", "biography_paper", ["profile_id"]),
    ("ix_biography_paper_session_id", "biography_paper", ["session_id"]),
    ("ix_biography_line_profile_id", "biography_line", ["profile_id"]),
    ("ix_biography_line_session_id", "biography_line", ["session_id"]),
    ("ix_activation_plan_profile_id", "activation_plan", ["profile_id"]),
    ("ix_activation_plan_created_at", "activation_plan", ["created_at"]),
    ("ix_plan_prompt_profile_id", "plan_prompt", ["profile_id"]),
    ("ix_plan_prompt_plan_id", "plan_prompt", ["plan_id"]),
)


def upgrade() -> None:
    op.create_table(
        "profile_settings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("density", DENSITY, nullable=False),
        sa.Column("large_text", sa.Boolean(), nullable=False),
        sa.Column("high_contrast", sa.Boolean(), nullable=False),
        sa.Column("voice_on", sa.Boolean(), nullable=False),
        sa.Column("big_targets", sa.Boolean(), nullable=False),
        sa.Column("one_thing_per_screen", sa.Boolean(), nullable=False),
        sa.Column("read_back", sa.Boolean(), nullable=False),
        sa.Column("repeat_prompts", sa.Boolean(), nullable=False),
        sa.Column("preferred_name", sa.String(length=80), nullable=True),
        sa.Column("doctor_name", sa.String(length=80), nullable=True),
        sa.Column("breakfast_time", sa.String(length=5), nullable=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("set_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        _when("set_at"),
        sa.Column("supersedes_id", sa.Uuid(), sa.ForeignKey("profile_settings.id"), nullable=True),
        _when("superseded_at", nullable=True),
        _row_of_profile("profile_settings"),
        _tied("profile_settings", "event_id", "event"),
        _tied("profile_settings", "supersedes_id", "profile_settings"),
    )
    op.create_table(
        "biography_session",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("opened_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        _when("opened_at"),
        _when("read_back_at", nullable=True),
        sa.Column("read_back_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        _when("closed_at", nullable=True),
        sa.Column("closed_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        _row_of_profile("biography_session"),
    )
    op.create_table(
        "biography_paper",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("biography_session.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=False),
        sa.Column("card_id", sa.Uuid(), sa.ForeignKey("review_card.id"), nullable=False),
        sa.Column("paper", PAPER_KIND, nullable=False),
        sa.Column("added_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        _when("added_at"),
        _row_of_profile("biography_paper"),
        _tied("biography_paper", "session_id", "biography_session"),
        _tied("biography_paper", "artifact_id", "artifact"),
        _tied("biography_paper", "card_id", "review_card"),
    )
    op.create_table(
        "biography_line",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("biography_session.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("fact_id", sa.Uuid(), sa.ForeignKey("fact.id"), nullable=False),
        sa.Column("answer", ANSWER, nullable=False),
        sa.Column("dispute_fact_id", sa.Uuid(), sa.ForeignKey("fact.id"), nullable=True),
        sa.Column("answered_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        _when("answered_at"),
        _row_of_profile("biography_line"),
        _tied("biography_line", "session_id", "biography_session"),
        _tied("biography_line", "fact_id", "fact"),
        _tied("biography_line", "dispute_fact_id", "fact"),
    )
    op.create_table(
        "activation_plan",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("biography_session.id"), nullable=True),
        sa.Column("breakfast_time", sa.String(length=5), nullable=False),
        sa.Column("first_day", sa.Date(), nullable=False),
        sa.Column("created_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        _when("created_at"),
        _row_of_profile("activation_plan"),
        _tied("activation_plan", "session_id", "biography_session"),
    )
    op.create_table(
        "plan_prompt",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("activation_plan.id"), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("gap", sa.String(length=32), nullable=False),
        _when("due_at"),
        sa.Column("status", PROMPT_STATUS, nullable=False),
        _when("done_at", nullable=True),
        sa.Column("done_by_fact_id", sa.Uuid(), sa.ForeignKey("fact.id"), nullable=True),
        _when("skipped_at", nullable=True),
        sa.Column("skipped_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        _row_of_profile("plan_prompt"),
        _tied("plan_prompt", "plan_id", "activation_plan"),
        _tied("plan_prompt", "done_by_fact_id", "fact"),
        sa.UniqueConstraint("plan_id", "gap", name="uq_plan_prompt_plan_id_gap"),
        sa.UniqueConstraint("plan_id", "day", name="uq_plan_prompt_plan_id_day"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table("plan_prompt")
    op.drop_table("activation_plan")
    op.drop_table("biography_line")
    op.drop_table("biography_paper")
    op.drop_table("biography_session")
    op.drop_table("profile_settings")
