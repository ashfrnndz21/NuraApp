"""F1: the feed's richer formats — clips, local and seasonal alerts, food cards, engagement.

Two tables gain columns. `profile.area`: where he lives, coarsely (a town or district, or the
first digits of a postcode), set on his own yes and used only to match local alerts on this
server (E09-07; `app.delivery.feed.area`). `feed_engagement.seconds`: how much of a clip or a voice
note played, on a play or a replay only; and `feed_engagement.client_id`: the id the phone gave
an event in its queue, unique on the profile, so an event flushed twice is written once (E11-08).

`card_type` gains `clip`, `recap`, `local`, `seasonal` and `food`; `card_format` gains `clip`;
`engagement_kind` gains `opened`, `played`, `replayed` and `asked_more`: non-native enums with
no database constraint, so no schema change for them. The duty card's supply is `today` from
now on (the caregiver's list has no gate); rows written before keep the `gate` they were
written with, and the caregiver's list, which shows no gate card, shows them as before.

Revision ID: 0030_feed_formats
Revises: 0028_whatsapp_opt_in
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_feed_formats"
down_revision = "0031_brief_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("profile") as batch:
        batch.add_column(sa.Column("area", sa.String(length=40), nullable=True))
    with op.batch_alter_table("feed_engagement") as batch:
        batch.add_column(sa.Column("seconds", sa.Float(), nullable=True))
        batch.add_column(sa.Column("client_id", sa.Uuid(), nullable=True))
        batch.create_unique_constraint(
            "uq_feed_engagement_client", ["profile_id", "client_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("feed_engagement") as batch:
        batch.drop_constraint("uq_feed_engagement_client", type_="unique")
        batch.drop_column("client_id")
        batch.drop_column("seconds")
    with op.batch_alter_table("profile") as batch:
        batch.drop_column("area")
