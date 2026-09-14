"""E19: WhatsApp — the thread, the message by reference, the proposal, the ladder.

Four tables of profile data, every row tied to its profile the way the memory tables are
(0005): a message names its thread, its artefact, its flag (E21's `red_flag`, 0010_feed)
and its State on the same profile; a proposal names its thread, its message, and the fact
and event it became; an escalation names its flag. No column holds what anyone wrote: the words are artefacts in
the region's object store, and the rows point at them.

Follows E16's rendered-boundary revision (0014_rendered_boundary), main's head when this
story merged main back; the `red_flag` table the message and the ladder point at is E21's
(0010_feed), underneath it. The number stays this story's own; the operator repoints
`down_revision` again if another story lands first.

Revision ID: 0011_whatsapp
Revises: 0014_rendered_boundary
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_whatsapp"
down_revision = "0014_rendered_boundary"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


DIRECTION = _enum("whatsapp_direction", "inbound", "outbound")
MESSAGE_KIND = _enum(
    "whatsapp_message_kind",
    "document",
    "health_event",
    "coordination",
    "red_flag",
    "answer",
    "check_in_answer",
    "reply",
    "template",
)
PROPOSAL_STATUS = _enum("whatsapp_proposal_status", "open", "confirmed", "declined", "expired")
EVENT_KIND = _enum(
    "event_kind", "reading", "visit", "message", "dose_taken", "symptom", "discharge"
)


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
    ("ix_whatsapp_thread_profile_id", "whatsapp_thread", ["profile_id"]),
    ("ix_whatsapp_thread_person_id", "whatsapp_thread", ["person_id"]),
    ("ix_whatsapp_message_profile_id", "whatsapp_message", ["profile_id"]),
    ("ix_whatsapp_message_thread_id", "whatsapp_message", ["thread_id"]),
    ("ix_whatsapp_message_at", "whatsapp_message", ["at"]),
    ("ix_whatsapp_proposal_profile_id", "whatsapp_proposal", ["profile_id"]),
    ("ix_whatsapp_proposal_thread_id", "whatsapp_proposal", ["thread_id"]),
    ("ix_whatsapp_proposal_poster_person_id", "whatsapp_proposal", ["poster_person_id"]),
    ("ix_safety_escalation_profile_id", "safety_escalation", ["profile_id"]),
    ("ix_safety_escalation_flag_id", "safety_escalation", ["flag_id"]),
)


def upgrade() -> None:
    op.create_table(
        "whatsapp_thread",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("is_patient", sa.Boolean(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_whatsapp_thread_profile_id_id"),
        sa.UniqueConstraint("profile_id", "person_id", name="uq_whatsapp_thread_person"),
    )
    op.create_table(
        "whatsapp_message",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("thread_id", sa.Uuid(), sa.ForeignKey("whatsapp_thread.id"), nullable=False),
        sa.Column("direction", DIRECTION, nullable=False),
        sa.Column("kind", MESSAGE_KIND, nullable=False),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_message_id", sa.String(length=80), nullable=True),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=True),
        sa.Column("flag_id", sa.Uuid(), sa.ForeignKey("red_flag.id"), nullable=True),
        sa.Column("template_name", sa.String(length=32), nullable=True),
        sa.Column("catalogue_key", sa.String(length=48), nullable=True),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_whatsapp_message_profile_id_id"),
        _tied("whatsapp_message", "thread_id", "whatsapp_thread"),
        _tied("whatsapp_message", "artifact_id", "artifact"),
        _tied("whatsapp_message", "flag_id", "red_flag"),
        _tied("whatsapp_message", "state_id", "state_snapshot"),
    )
    op.create_table(
        "whatsapp_proposal",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("thread_id", sa.Uuid(), sa.ForeignKey("whatsapp_thread.id"), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("whatsapp_message.id"), nullable=False),
        sa.Column("poster_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("subject", sa.String(length=64), nullable=False),
        sa.Column("attribute", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("event_kind", EVENT_KIND, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("said", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", PROPOSAL_STATUS, nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fact_id", sa.Uuid(), sa.ForeignKey("fact.id"), nullable=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_whatsapp_proposal_profile_id_id"),
        _tied("whatsapp_proposal", "thread_id", "whatsapp_thread"),
        _tied("whatsapp_proposal", "message_id", "whatsapp_message"),
        _tied("whatsapp_proposal", "fact_id", "fact"),
        _tied("whatsapp_proposal", "event_id", "event"),
    )
    op.create_table(
        "safety_escalation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("flag_id", sa.Uuid(), sa.ForeignKey("red_flag.id"), nullable=False),
        sa.Column("roster", sa.JSON(), nullable=False),
        sa.Column("told", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_safety_escalation_profile_id_id"),
        _tied("safety_escalation", "flag_id", "red_flag"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    for table in (
        "safety_escalation",
        "whatsapp_proposal",
        "whatsapp_message",
        "whatsapp_thread",
    ):
        op.drop_table(table)
