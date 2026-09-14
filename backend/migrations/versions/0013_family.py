"""E12: family — only me, the thread, the roster, the tasks, the scheduled pushes, the documents.

Six tables of profile data, every row tied to its profile the way the memory tables are
(0005): a thread card's `(profile_id, state_id)` points at `state_snapshot(profile_id, id)`,
a document's artefact at `artifact(profile_id, id)`, a task card's task at
`task(profile_id, id)`. A thread row is a message or a card, never both or neither
(`ck_thread_message_text_or_card`). A scheduled push carries `state_id` like every
rendered thing. `privacy` is the "only me" mark the key resolver reads.

Follows E21's feed revision (0010), main's head when this story was merged back; the
operator repoints `down_revision` again if another story lands first.

Revision ID: 0013_family
Revises: 0010_feed
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_family"
down_revision = "0010_feed"
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
KEY_ROLE = _enum("key_role", "chief", "caregiver", "viewer", "helper", "emergency", "clinic")
CARD_KIND = _enum("thread_card_kind", "reading", "taken", "visit", "task")
PUSH_CHANNEL = _enum("push_channel", "app", "whatsapp")
DOCUMENT_TAG = _enum("document_tag", "lpa", "medical_letter", "consent_form")


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
    ("ix_privacy_profile_id", "privacy", ["profile_id"]),
    ("ix_roster_slot_profile_id", "roster_slot", ["profile_id"]),
    ("ix_roster_slot_person_id", "roster_slot", ["person_id"]),
    ("ix_task_profile_id", "task", ["profile_id"]),
    ("ix_task_assigned_person_id", "task", ["assigned_person_id"]),
    ("ix_thread_message_profile_id", "thread_message", ["profile_id"]),
    ("ix_thread_message_author_person_id", "thread_message", ["author_person_id"]),
    ("ix_thread_message_posted_at", "thread_message", ["posted_at"]),
    ("ix_scheduled_push_profile_id", "scheduled_push", ["profile_id"]),
    ("ix_scheduled_push_state_id", "scheduled_push", ["state_id"]),
    ("ix_scheduled_push_send_at", "scheduled_push", ["send_at"]),
    ("ix_document_profile_id", "document", ["profile_id"]),
    ("ix_document_artifact_id", "document", ["artifact_id"]),
)


def upgrade() -> None:
    op.create_table(
        "privacy",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("scope", SCOPE, nullable=False),
        sa.Column("marked_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lifted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lifted_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
    )
    op.create_table(
        "roster_slot",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("role", KEY_ROLE, nullable=False),
        sa.Column("weekdays", sa.JSON(), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("from_time", sa.Time(), nullable=False),
        sa.Column("to_time", sa.Time(), nullable=False),
        sa.Column("added_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        _row_of_profile("roster_slot"),
    )
    op.create_table(
        "task",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("what", sa.String(length=80), nullable=False),
        sa.Column("assigned_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        _row_of_profile("task"),
    )
    op.create_table(
        "thread_message",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("author_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text", sa.String(length=280), nullable=True),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=True),
        sa.Column("card_kind", CARD_KIND, nullable=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("task.id"), nullable=True),
        _row_of_profile("thread_message"),
        _tied("thread_message", "state_id", "state_snapshot"),
        _tied("thread_message", "task_id", "task"),
        sa.CheckConstraint(
            "(text IS NOT NULL AND state_id IS NULL AND card_kind IS NULL)"
            " OR (text IS NULL AND state_id IS NOT NULL AND card_kind IS NOT NULL)",
            name="ck_thread_message_text_or_card",
        ),
    )
    op.create_table(
        "scheduled_push",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=False),
        sa.Column("composed_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("composed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("template_id", sa.String(length=48), nullable=True),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", PUSH_CHANNEL, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _row_of_profile("scheduled_push"),
        _tied("scheduled_push", "state_id", "state_snapshot"),
    )
    op.create_table(
        "document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=False),
        sa.Column("tag", DOCUMENT_TAG, nullable=False),
        sa.Column("added_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        _row_of_profile("document"),
        _tied("document", "artifact_id", "artifact"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    for table in ("document", "scheduled_push", "thread_message", "task", "roster_slot", "privacy"):
        op.drop_table(table)
