"""E13/E14: the flag, the notice, the what-to-do-now card, the emergency card.

Four tables of profile data, every row tied to its profile the way the memory tables are
(0005): `(profile_id, artifact_id)` points at `artifact(profile_id, id)`, a notice's flag at
`flag(profile_id, id)`, and so on, so the database itself refuses a notice about another
profile's flag. The two cards carry `state_id`, not nullable: nothing rendered reaches the
database without the State it was rendered from (0006). No column holds prose: a flag is a
code from the red-flag table, a notice a template id and codes, a card the ids of its lines.

Follows E12's family revision (0013), which follows E21's feed (0010): one head. The
`flag` table here is the flag heard in his words by the not-feeling-well button and the
symptom log (E13/E14); E21's `red_flag` (0010) is the flag tapped on the feeling cloud.

Revision ID: 0014_emergency_symptoms
Revises: 0013_family
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_emergency_symptoms"
down_revision = "0013_family"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


FLAG_KIND = _enum("flag_kind", "red_flag")
POSTURE = _enum("posture", "stable", "watch", "act")
NOTICE_KIND = _enum("notice_kind", "family_alert", "check_in")
WHAT_TO_DO_KIND = _enum("what_to_do_kind", "red_flag", "missed_dose", "rest")
CARD_FORMAT = _enum("card_format", "json", "html")


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
    ("ix_flag_profile_id", "flag", ["profile_id"]),
    ("ix_flag_code", "flag", ["code"]),
    ("ix_flag_raised_at", "flag", ["raised_at"]),
    ("ix_notice_profile_id", "notice", ["profile_id"]),
    ("ix_notice_to_person_id", "notice", ["to_person_id"]),
    ("ix_notice_created_at", "notice", ["created_at"]),
    ("ix_notice_deliver_after", "notice", ["deliver_after"]),
    ("ix_what_to_do_card_profile_id", "what_to_do_card", ["profile_id"]),
    ("ix_what_to_do_card_state_id", "what_to_do_card", ["state_id"]),
    ("ix_emergency_card_profile_id", "emergency_card", ["profile_id"]),
    ("ix_emergency_card_state_id", "emergency_card", ["state_id"]),
    ("ix_emergency_card_rendered_at", "emergency_card", ["rendered_at"]),
)


def upgrade() -> None:
    op.create_table(
        "flag",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("kind", FLAG_KIND, nullable=False),
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("posture", POSTURE, nullable=False),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=True),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raised_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        # The flags held back this time, by code: the suppression the caregiver sees.
        sa.Column("suppressed", sa.JSON(), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_flag_profile_id_id"),
        _tied("flag", "artifact_id", "artifact"),
    )
    op.create_table(
        "notice",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("kind", NOTICE_KIND, nullable=False),
        sa.Column("to_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("template", sa.String(length=48), nullable=False),
        # Codes that fill the template — a red-flag or symptom code — never the words said.
        sa.Column("slots", sa.JSON(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("flag_id", sa.Uuid(), sa.ForeignKey("flag.id"), nullable=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deliver_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_notice_profile_id_id"),
        _tied("notice", "flag_id", "flag"),
        _tied("notice", "event_id", "event"),
    )
    op.create_table(
        "what_to_do_card",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=False),
        sa.Column("kind", WHAT_TO_DO_KIND, nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        # The template ids of the lines shown, in order. The words come from the templates.
        sa.Column("line_ids", sa.JSON(), nullable=False),
        sa.Column("flag_id", sa.Uuid(), sa.ForeignKey("flag.id"), nullable=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rendered_for_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_what_to_do_card_profile_id_id"),
        _tied("what_to_do_card", "flag_id", "flag"),
        _tied("what_to_do_card", "event_id", "event"),
    )
    op.create_table(
        "emergency_card",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=False),
        sa.Column("format", CARD_FORMAT, nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("fact_ids", sa.JSON(), nullable=False),
        sa.Column("line_ids", sa.JSON(), nullable=False),
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rendered_for_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_emergency_card_profile_id_id"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    for table in ("emergency_card", "what_to_do_card", "notice", "flag"):
        op.drop_table(table)
