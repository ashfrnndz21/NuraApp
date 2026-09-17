"""RE-01: `feed_item.private_to`, his alone (docs/recommendation-engine.md §2.4).

A card resting on his own search history — later, an asked topic — is not something a scope
can hide from a caregiver: every key that reaches him at all reaches `Scope.ASK`. A nullable
person id is the one exception a `Scope` cannot express (`app.delivery.feed.rank._visible_to`).
Rows written before this carry no value, and are visible to everyone their scope already let
in, exactly as before.

Revision ID: 0041_feed_item_private_to
Revises: 0039_feeling_question_marker
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_feed_item_private_to"
down_revision = "0040_monotonic_tiebreak"
branch_labels = None
depends_on = None

PRIVATE_TO_FK = "fk_feed_item_private_to_person"


def upgrade() -> None:
    with op.batch_alter_table("feed_item") as batch:
        batch.add_column(sa.Column("private_to", sa.Uuid(), nullable=True))
        batch.create_foreign_key(PRIVATE_TO_FK, "person", ["private_to"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("feed_item") as batch:
        batch.drop_constraint(PRIVATE_TO_FK, type_="foreignkey")
        batch.drop_column("private_to")
