"""E22-04: the pharmacist's review queue.

One table of operator data, `review_item`: a source proposed for the allowlist, or one of the
first fifty renderings of a kind of card, de-identified — lines only, no profile id, no
names. It is not profile data and carries no `profile_id`; the source a review would
allowlist is the existing global `source` row, whose `review_status` already keeps a pending
source unused. See docs/adr/0007-the-pharmacist-review-queue.md.

Follows main's head when this story was pushed (0020_feelings); the operator repoints
`down_revision` if another story lands first.

Revision ID: 0021_language
Revises: 0020_feelings
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_language"
down_revision = "0020_feelings"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


REVIEW_KIND = _enum("review_kind", "source", "card")
REVIEW_VERDICT = _enum("review_verdict", "pending", "approved", "rejected", "rewritten")


def upgrade() -> None:
    op.create_table(
        "review_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", REVIEW_KIND, nullable=False),
        sa.Column("card_type", sa.String(length=32), nullable=True),
        sa.Column("sample_number", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("source.id"), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("catalogue_ids", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("verdict", REVIEW_VERDICT, nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("proposed", sa.JSON(), nullable=True),
        sa.Column("decided_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("digest", name="uq_review_item_digest"),
    )
    op.create_index("ix_review_item_card_type", "review_item", ["card_type"])
    op.create_index("ix_review_item_created_at", "review_item", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_review_item_created_at", table_name="review_item")
    op.drop_index("ix_review_item_card_type", table_name="review_item")
    op.drop_table("review_item")
