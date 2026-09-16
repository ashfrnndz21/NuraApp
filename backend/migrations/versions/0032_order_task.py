"""E04-05: the family's order task names the medicine line it is for, and the day it opened.

`task.medication_line_id`: the medicine line a task made on his yes to "Ask the family to
order." is for, tied to the line on the same profile. `task.opened_on`: his wall-clock day
(`app.medicines.reorder._his_day`) when that task was made. Together they are how one open
order task a line a day is found again, so a second yes that day answers with the task
already on the list.

A partial unique index on `(profile_id, medication_line_id, opened_on)`, where
`errand = 'order'` and `done_at IS NULL`, is what actually enforces one open order task a
line a day (#166 review): `ask_to_order` checks then acts, and two yeses at the same moment
can each pass the check before either writes. `opened_on` is in the index, not just
`created_at` compared at query time, because a partial index's predicate must be immutable —
it cannot test "is this today" itself — so the day has to be a column two rows can actually
collide on. That also keeps the day-reset the check-then-act code always had: a task still
open from yesterday does not collide with today's, because their `opened_on` differ. The
index is what stops the second insert on the same day; `ask_to_order` catches the
`IntegrityError` and answers with the task the index let win.

`task_errand` gains `order` and `confirm_subject` gains `order`: non-native enums with no
database constraint, so no schema change for them.

Renumbered onto main's head at merge time (#166): main took 0029 and 0030
(`0030_whatsapp_receipts`) first, so this follows it as 0031, not 0028.

Revision ID: 0031_order_task
Revises: 0030_whatsapp_receipts
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_order_task"
down_revision = "0031_brief_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task") as task:
        task.add_column(sa.Column("medication_line_id", sa.Uuid(), nullable=True))
        task.add_column(sa.Column("opened_on", sa.Date(), nullable=True))
        task.create_foreign_key(
            "fk_task_medication_line_id_medication_line",
            "medication_line",
            ["medication_line_id"],
            ["id"],
        )
        task.create_foreign_key(
            "fk_task_medication_line_profile",
            "medication_line",
            ["profile_id", "medication_line_id"],
            ["profile_id", "id"],
        )
    op.create_index("ix_task_medication_line_id", "task", ["medication_line_id"])
    op.create_index(
        "uq_task_open_order_per_line_per_day",
        "task",
        ["profile_id", "medication_line_id", "opened_on"],
        unique=True,
        sqlite_where=sa.text("errand = 'order' AND done_at IS NULL"),
        postgresql_where=sa.text("errand = 'order' AND done_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_task_open_order_per_line_per_day", table_name="task")
    op.drop_index("ix_task_medication_line_id", table_name="task")
    with op.batch_alter_table("task") as task:
        task.drop_constraint("fk_task_medication_line_profile", type_="foreignkey")
        task.drop_constraint("fk_task_medication_line_id_medication_line", type_="foreignkey")
        task.drop_column("opened_on")
        task.drop_column("medication_line_id")
