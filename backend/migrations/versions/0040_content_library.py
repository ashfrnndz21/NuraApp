"""The content library: Activities, Care Services, Resources and Community.

One table, `content_item`, global like `source` — not profile data, so no `profile_id` — one
row per (region, slug, language). `content_type` reuses the feed's own `card_type` enum
(grown by this story with six new members: activity, care_service, resource, local_event,
volunteer, support_group), so the pharmacist's review queue holds every item exactly like a
card's first fifty (`app.language.review`, ADR 0007). `review_status` gates whether a route
ever answers a row: pending until a pharmacist approves it, the same three states `source`
already uses. `review_item_id` is nullable because a row is written, then queued, in two
statements (`app.delivery.content.service.seed_content` / `queue_content_item`).

Numbered off the current head (0039_feeling_question_marker) when this story was pushed; the
operator repoints `down_revision` if another story lands first.

Revision ID: 0040_content_library
Revises: 0039_feeling_question_marker
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_content_library"
down_revision = "0039_feeling_question_marker"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


CONTENT_REVIEW_STATUS = _enum("content_review_status", "pending", "approved", "rejected")


def upgrade() -> None:
    op.create_table(
        "content_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("review_status", CONTENT_REVIEW_STATUS, nullable=False),
        sa.Column(
            "review_item_id", sa.Uuid(), sa.ForeignKey("review_item.id"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "region", "slug", "language", name="uq_content_item_slug_language"
        ),
    )
    op.create_index("ix_content_item_created_at", "content_item", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_content_item_created_at", table_name="content_item")
    op.drop_table("content_item")
