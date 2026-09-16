"""#198: a late "Taken" is stored as late, not merely inferred at read time.

`dose_taken.late` is a stored bool, worked out once when the tap is written
(`app.medicines.windows.is_late`) from the anchor and the moment the tap itself carries — the
reply's own time, not the backend's processing clock. False on every row written before this
migration: their `taken_at` and `anchor` are unchanged, so a caller that wants a verdict on an
old tap can still work it out from those two fields the old way; nothing here rewrites them.

Renumbered from 0036 to 0038 at merge time: 0036 and 0037 went to #209 and #202, landing
first (docs/adr/0014, this migration's own docstring elsewhere, still call it "0036" in prose
— the number changed, not the reasoning).

Revision ID: 0038_dose_taken_late
Revises: 0037_drug_registry_growth
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_dose_taken_late"
down_revision = "0037_drug_registry_growth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("dose_taken") as batch:
        batch.add_column(
            sa.Column("late", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("dose_taken") as batch:
        batch.drop_column("late")
