"""#144: delivery settings per recipient, the profile's own row as the default.

`delivery_settings.for_person_id` names whose quiet hours and channels a row is: null for
the profile's own default (E11-05, unchanged), or a key holder's own (Mei's weekdays, Kit's
weekends) when they have set theirs. `app.delivery.triggers.preferences.current` reads a
recipient's newest row when there is one, and falls back to the profile's default row —
never the other way round. Every row this migration runs over is the profile's own: null on
all of them, exactly what they already meant.

Revision ID: 0040_delivery_settings_recipient
Revises: 0039_key_successor_waived
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_delivery_settings_recipient"
down_revision = "0039_key_successor_waived"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "delivery_settings",
        sa.Column("for_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
    )
    op.create_index(
        "ix_delivery_settings_for_person_id", "delivery_settings", ["for_person_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_delivery_settings_for_person_id", table_name="delivery_settings")
    op.drop_column("delivery_settings", "for_person_id")
