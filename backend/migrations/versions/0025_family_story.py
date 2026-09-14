"""E21-05, E11-01: a photo the family shares in the thread, and the family's WhatsApp group.

Two tables of profile data, each tied to its profile the way the family tables are (0013).
A shared photo names the thread message it came with and the artefact it is, under the
family scope; it carries the poster's yes to its being one of his story cards and, once, the
poster taking it back. The family group names the provider's handle for the group and who
opened it; who is in it is never stored — it is worked out from the keys each time.

Revision ID: 0025_family_story
Revises: 0024_push_subscription
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_family_story"
down_revision = "0024_push_subscription"
branch_labels = None
depends_on = None


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
    ("ix_thread_photo_profile_id", "thread_photo", ["profile_id"]),
    ("ix_thread_photo_message_id", "thread_photo", ["message_id"]),
    ("ix_thread_photo_posted_at", "thread_photo", ["posted_at"]),
    ("ix_whatsapp_group_profile_id", "whatsapp_group", ["profile_id"]),
)


def upgrade() -> None:
    op.create_table(
        "thread_photo",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("thread_message.id"), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=False),
        sa.Column("author_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("on_his_feed", sa.Boolean(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        _row_of_profile("thread_photo"),
        _tied("thread_photo", "message_id", "thread_message"),
        _tied("thread_photo", "artifact_id", "artifact"),
        sa.UniqueConstraint("message_id", name="uq_thread_photo_message"),
    )
    op.create_table(
        "whatsapp_group",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("provider_group_id", sa.String(length=80), nullable=False),
        sa.Column("opened_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        _row_of_profile("whatsapp_group"),
        sa.UniqueConstraint("profile_id", name="uq_whatsapp_group_profile"),
        sa.UniqueConstraint("provider_group_id", name="uq_whatsapp_group_provider"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table("whatsapp_group")
    op.drop_table("thread_photo")
