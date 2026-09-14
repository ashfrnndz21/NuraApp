"""E17: the feeling cloud, feeling inference and smart nudges.

Four tables of profile data, each tied to its profile the way the memory tables are (0005):

- `feeling_tap`: one tap on the cloud — his word as a code, the SYMPTOM event it was written
  as, the flag a red word raised, the one question it asked and its answer, and why the word
  was on the cloud, by code and id. No words of his beyond the word he tapped.
- `feeling_note`: what a tap and its answer were read into — at most two things to tell the
  doctor, who does the next thing, the spoken twin, the reasons by id — rendered from State
  with the boundary line (`Surface.FEELING_INFERENCE`), like every rendered row.
- `nudge`: a smart nudge as it was handed to delivery (E11), rendered from State.
- `nudge_response`: what a person did with one — seen, accepted, dismissed — resting on an
  ENGAGEMENT event.

`red_flag.feeling`, `feeling_tap.word` and `feeling_note.word` are checked strings with no
database constraint (0010), so the words the cloud gained (pain, short of breath, low, worried,
poor sleep, swollen ankles, upset stomach) need no change to an existing table.

Follows W3's revision (0019_person_named_by), main's head when this story merged main back; the operator repoints `down_revision` if another story lands first.

Revision ID: 0020_feelings
Revises: 0019_person_named_by
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_feelings"
down_revision = "0019_person_named_by"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


FEELING = _enum(
    "feeling",
    "fall",
    "chest_tightness",
    "breathless_at_rest",
    "one_sided_swelling",
    "worst_headache",
    "sudden_blurring",
    "confusion",
    "shaky_sweaty",
    "weight_gain",
    "dizzy",
    "cramps",
    "thirsty",
    "tired",
    "aches",
    "headache",
    "pain",
    "breathless",
    "low",
    "worried",
    "cant_sleep",
    "swollen_ankles",
    "stomach_upset",
    "fine",
)
FOLLOW_UP = _enum(
    "feeling_follow_up", "since_when", "more_than_yesterday", "at_rest", "one_side", "worst_ever"
)
ANSWER = _enum(
    "feeling_answer",
    "today",
    "yesterday",
    "few_days",
    "week_or_more",
    "more",
    "same",
    "less",
    "yes",
    "no",
)
OUTCOME = _enum("feeling_outcome", "for_the_doctor", "watch")
NUDGE_KIND = _enum(
    "nudge_kind", "anticipation", "check_in", "pattern", "commitment", "recognition", "presence"
)
SCOPE = _enum(
    "scope",
    "medicines",
    "visits",
    "readings",
    "records",
    "notes",
    "money",
    "family",
    "emergency",
    "ask",
    "send",
    "profile",
)
CAPS_CLASS = _enum("caps_class", "flag", "one", "supply", "held")
RESPONSE_KIND = _enum("nudge_response_kind", "seen", "accepted", "dismissed")


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


def _when(name: str, nullable: bool = False) -> sa.Column[sa.DateTime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


_INDEXES = (
    ("ix_feeling_tap_profile_id", "feeling_tap", ["profile_id"]),
    ("ix_feeling_tap_tapped_at", "feeling_tap", ["tapped_at"]),
    ("ix_feeling_note_profile_id", "feeling_note", ["profile_id"]),
    ("ix_feeling_note_state_id", "feeling_note", ["state_id"]),
    ("ix_feeling_note_tap_id", "feeling_note", ["tap_id"]),
    ("ix_feeling_note_created_at", "feeling_note", ["created_at"]),
    ("ix_nudge_profile_id", "nudge", ["profile_id"]),
    ("ix_nudge_state_id", "nudge", ["state_id"]),
    ("ix_nudge_day", "nudge", ["day"]),
    ("ix_nudge_handed_over_at", "nudge", ["handed_over_at"]),
    ("ix_nudge_response_profile_id", "nudge_response", ["profile_id"]),
    ("ix_nudge_response_nudge_id", "nudge_response", ["nudge_id"]),
    ("ix_nudge_response_at", "nudge_response", ["at"]),
)


def upgrade() -> None:
    op.create_table(
        "feeling_tap",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("word", FEELING, nullable=False),
        sa.Column("red", sa.Boolean(), nullable=False),
        sa.Column("flag_id", sa.Uuid(), sa.ForeignKey("red_flag.id"), nullable=True),
        sa.Column("follow_up", FOLLOW_UP, nullable=True),
        sa.Column("answer", ANSWER, nullable=True),
        _when("answered_at", nullable=True),
        sa.Column("emphasised", sa.Boolean(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("cloud_state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=True),
        sa.Column("by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        _when("tapped_at"),
        sa.UniqueConstraint("profile_id", "id", name="uq_feeling_tap_profile_id_id"),
        _tied("feeling_tap", "event_id", "event"),
        _tied("feeling_tap", "flag_id", "red_flag"),
    )
    op.create_table(
        "feeling_note",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=False),
        sa.Column("boundary", sa.Text(), nullable=True),
        sa.Column("tap_id", sa.Uuid(), sa.ForeignKey("feeling_tap.id"), nullable=False),
        sa.Column("word", FEELING, nullable=False),
        sa.Column("answer", ANSWER, nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("headline", sa.String(length=200), nullable=False),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("then", sa.String(length=200), nullable=False),
        sa.Column("voice", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("outcome", OUTCOME, nullable=False),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=True),
        _when("created_at"),
        sa.UniqueConstraint("profile_id", "id", name="uq_feeling_note_profile_id_id"),
        _tied("feeling_note", "tap_id", "feeling_tap"),
        _tied("feeling_note", "appointment_id", "appointment"),
    )
    op.create_table(
        "nudge",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=False),
        sa.Column("boundary", sa.Text(), nullable=True),
        sa.Column("kind", NUDGE_KIND, nullable=False),
        sa.Column("scope", SCOPE, nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("voice", sa.JSON(), nullable=False),
        sa.Column("why", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.JSON(), nullable=False),
        sa.Column("cap_class", CAPS_CLASS, nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        _when("send_after"),
        _when("expires_at"),
        sa.Column("dedupe_key", sa.String(length=120), nullable=False),
        sa.Column("memo_id", sa.Uuid(), nullable=True),
        _when("handed_over_at"),
        sa.Column(
            "handed_over_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False
        ),
        sa.UniqueConstraint("profile_id", "id", name="uq_nudge_profile_id_id"),
        sa.UniqueConstraint("profile_id", "dedupe_key", name="uq_nudge_dedupe"),
    )
    op.create_table(
        "nudge_response",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("nudge_id", sa.Uuid(), sa.ForeignKey("nudge.id"), nullable=False),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("kind", RESPONSE_KIND, nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        _when("at"),
        sa.UniqueConstraint("profile_id", "id", name="uq_nudge_response_profile_id_id"),
        _tied("nudge_response", "nudge_id", "nudge"),
        _tied("nudge_response", "event_id", "event"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    for table in ("nudge_response", "nudge", "feeling_note", "feeling_tap"):
        op.drop_table(table)
