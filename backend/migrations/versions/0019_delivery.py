"""E11: delivery — the settings, the log of every attempt, the ladder; the card grammar.

Three tables of profile data, every row tied to its profile the way the family tables are
(0013): a ladder's medicine line and red flag, a delivery's ladder and WhatsApp message. The
settings are a history (a change is a new row). And four columns on the feed item for the
card grammar (E11-03): one number, one direction, one colour, one action — nullable for the
rows written before the grammar was a column. The audit actor may be empty for Nura's own
reach (the delivery engine), on the system channel only; and a red flag carries whether the
person who raised it is on more than one profile.

Revision ID: 0019_delivery
Revises: 0019_person_named_by
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_delivery"
down_revision = "0019_person_named_by"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


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
TRIGGER_KIND = _enum("trigger_kind", "rule", "pattern", "event")
TRIGGER_TYPE = _enum(
    "trigger_type",
    "morning",
    "dose",
    "reorder",
    "doses_untapped",
    "flag",
    "visit_tomorrow",
    "papers",
    "family_message",
    "first_week_prompt",
)
CATEGORY = _enum("delivery_category", "alert", "reminder", "context")
CHANNEL = _enum("delivery_channel", "app_push", "whatsapp", "caregiver")
OUTCOME = _enum(
    "delivery_outcome", "sent", "capped", "quiet", "no_channel", "no_scope", "skipped"
)
SUBJECT = _enum("ladder_subject", "dose", "flag")


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
    ("ix_delivery_settings_profile_id", "delivery_settings", ["profile_id"]),
    ("ix_delivery_settings_set_at", "delivery_settings", ["set_at"]),
    ("ix_delivery_ladder_profile_id", "delivery_ladder", ["profile_id"]),
    ("ix_delivery_ladder_day", "delivery_ladder", ["day"]),
    ("ix_delivery_profile_id", "delivery", ["profile_id"]),
    ("ix_delivery_dedupe_key", "delivery", ["dedupe_key"]),
    ("ix_delivery_to_person_id", "delivery", ["to_person_id"]),
    ("ix_delivery_day", "delivery", ["day"]),
)

GRAMMAR = (
    ("number", 24),
    ("direction", 8),
    ("colour", 16),
    ("action", 24),
)


def upgrade() -> None:
    op.create_table(
        "delivery_settings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("skip_quiet_days", sa.Boolean(), nullable=False),
        sa.Column("quiet_from", sa.Time(), nullable=True),
        sa.Column("quiet_until", sa.Time(), nullable=True),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("caps", sa.JSON(), nullable=False),
        sa.Column("set_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        _row_of_profile("delivery_settings"),
    )
    op.create_table(
        "delivery_ladder",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("subject", SUBJECT, nullable=False),
        sa.Column("scope", SCOPE, nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("line_id", sa.Uuid(), sa.ForeignKey("medication_line.id"), nullable=True),
        sa.Column("anchor", sa.String(length=16), nullable=True),
        sa.Column("flag_id", sa.Uuid(), sa.ForeignKey("red_flag.id"), nullable=True),
        sa.Column("rungs", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_rung", sa.Integer(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "acknowledged_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_because", sa.String(length=32), nullable=True),
        _row_of_profile("delivery_ladder"),
        sa.UniqueConstraint("profile_id", "dedupe_key", name="uq_delivery_ladder_dedupe"),
        _tied("delivery_ladder", "line_id", "medication_line"),
        _tied("delivery_ladder", "flag_id", "red_flag"),
    )
    op.create_table(
        "delivery",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("trigger_kind", TRIGGER_KIND, nullable=False),
        sa.Column("trigger_type", TRIGGER_TYPE, nullable=False),
        sa.Column("category", CATEGORY, nullable=False),
        sa.Column("scope", SCOPE, nullable=False),
        sa.Column("rule", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("why", sa.JSON(), nullable=False),
        sa.Column("to_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("for_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("standing", sa.String(length=16), nullable=True),
        sa.Column("rung", sa.Integer(), nullable=True),
        sa.Column("ladder_id", sa.Uuid(), sa.ForeignKey("delivery_ladder.id"), nullable=True),
        sa.Column("channel", CHANNEL, nullable=True),
        sa.Column("template_name", sa.String(length=32), nullable=True),
        sa.Column("outcome", OUTCOME, nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("passed_over", sa.JSON(), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("whatsapp_message.id"), nullable=True),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        _row_of_profile("delivery"),
        _tied("delivery", "ladder_id", "delivery_ladder"),
        _tied("delivery", "message_id", "whatsapp_message"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)
    with op.batch_alter_table("feed_item") as batch:
        for column, length in GRAMMAR:
            batch.add_column(sa.Column(column, sa.String(length=length), nullable=True))
    # Nura's own reach is written with no person as the actor, on the system channel only.
    with op.batch_alter_table("audit_entry") as batch:
        batch.alter_column("actor_person_id", existing_type=sa.Uuid(), nullable=True)
        batch.create_check_constraint(
            "ck_audit_entry_actor_or_system", "actor_person_id IS NOT NULL OR channel = 'system'"
        )
    # A red flag from someone on more than one profile, raised on each of them.
    with op.batch_alter_table("red_flag") as batch:
        batch.add_column(
            sa.Column("ambiguous_profile", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM audit_entry WHERE actor_person_id IS NULL")).first():
        raise RuntimeError(
            "the trail holds lines written by the system; 0019 is not downgraded over them"
        )
    with op.batch_alter_table("red_flag") as batch:
        batch.drop_column("ambiguous_profile")
    with op.batch_alter_table("audit_entry") as batch:
        batch.drop_constraint("ck_audit_entry_actor_or_system", type_="check")
        batch.alter_column("actor_person_id", existing_type=sa.Uuid(), nullable=False)
    with op.batch_alter_table("feed_item") as batch:
        for column, _ in reversed(GRAMMAR):
            batch.drop_column(column)
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    for table in ("delivery", "delivery_ladder", "delivery_settings"):
        op.drop_table(table)
