"""Web Push: the browsers a person asked to get reminders on (ADR 0001).

One table of profile data, tied to its profile like every other: a person's subscription on
one browser, from one login session, with the push service's endpoint and the browser's two
keys. Revoked when he stops reminders; `gone_at` when the push service forgot the endpoint.

Revision ID: 0024_push_subscription
Revises: 0023_delivery
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_push_subscription"
down_revision = "0023_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscription",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("session.id"), nullable=False),
        sa.Column("endpoint", sa.String(length=1024), nullable=False),
        sa.Column("p256dh", sa.String(length=128), nullable=False),
        sa.Column("auth", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gone_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_push_subscription_profile_id_id"),
    )
    op.create_index("ix_push_subscription_profile_id", "push_subscription", ["profile_id"])
    op.create_index("ix_push_subscription_person_id", "push_subscription", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_push_subscription_person_id", table_name="push_subscription")
    op.drop_index("ix_push_subscription_profile_id", table_name="push_subscription")
    op.drop_table("push_subscription")
