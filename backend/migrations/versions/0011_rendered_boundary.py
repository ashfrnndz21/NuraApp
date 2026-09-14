"""E16: the boundary line on a rendered row.

`feed_item` gains `boundary`, the line a card of an inferring surface was shown under
(E16-01, `app.safety.boundary`): a learning card or a notice carries it, a card that shows
the record back carries none, so the column is nullable. `RenderedFromState` declares the
column for every rendered table; `feed_item` is the one on main (E21, 0010_feed), and the
rendered tables still on their own branches create theirs with it.

Revision ID: 0011_rendered_boundary
Revises: 0010_feed
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_rendered_boundary"
down_revision = "0010_feed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("feed_item") as feed_item:
        feed_item.add_column(sa.Column("boundary", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("feed_item") as feed_item:
        feed_item.drop_column("boundary")
