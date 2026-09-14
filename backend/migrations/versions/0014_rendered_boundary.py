"""E16: the boundary line on a rendered row.

Every table that records the State it was rendered from (`RenderedFromState`) gains
`boundary`, the line a row of an inferring surface was shown under (E16-01,
`app.safety.boundary`). On main those are `feed_item` (E21, 0010_feed), where a learning
card or a notice carries the line and every other card carries none, and `scheduled_push`
(E12, 0013_family), a chief's own words to him that infer nothing and carry none. So the
column is nullable; `render_from_state` decides what goes in it.

Revision ID: 0014_rendered_boundary
Revises: 0013_family
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_rendered_boundary"
down_revision = "0013_family"
branch_labels = None
depends_on = None

RENDERED = ("feed_item", "scheduled_push")


def upgrade() -> None:
    for table in RENDERED:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("boundary", sa.Text(), nullable=True))


def downgrade() -> None:
    for table in reversed(RENDERED):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("boundary")
