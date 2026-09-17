"""#175: the body-systems map's tags on an episode.

`episode.body_systems` (a JSON list of `app.memory.models.BodySystem` values) is what the
person naming the episode said it is about — never inferred — and empty on every existing
row, which is exactly what they meant before this column existed: nothing said.

Revision ID: 0041_episode_body_systems
Revises: 0040_delivery_settings_recipient
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_episode_body_systems"
down_revision = "0040_delivery_settings_recipient"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("episode") as batch:
        batch.add_column(
            sa.Column("body_systems", sa.JSON(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("episode") as batch:
        batch.drop_column("body_systems")
