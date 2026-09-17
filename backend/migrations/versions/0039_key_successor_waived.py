"""#144: Pa's own word that a chief may leave with nobody named after her.

`key.successor_waived_at` and `key.successor_waived_by_person_id` are set only by
`app.keys.grants.waive_successor`, only on a live chief key, only by the owner — so a chief's
leave (`app.keys.grants.leave_key`) can close with no successor without the family being left
without a chief silently. None on every key this migration runs over; nobody has said this
about any of them yet.

Revision ID: 0039_key_successor_waived
Revises: 0038_dose_taken_late
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039_key_successor_waived"
down_revision = "0038_dose_taken_late"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("key") as batch:
        batch.add_column(sa.Column("successor_waived_at", sa.DateTime(timezone=True), nullable=True))
        # No FK constraint added here, the way 0022's `recording_artifact_id` was not: SQLite's
        # batch rewrite needs every added constraint named, and the model's own
        # `ForeignKey("person.id")` is enough for the ORM and for `tests/test_migration.py`'s
        # table-shape check, which is columns and types, not constraints.
        batch.add_column(sa.Column("successor_waived_by_person_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("key") as batch:
        batch.drop_column("successor_waived_by_person_id")
        batch.drop_column("successor_waived_at")
