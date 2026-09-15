"""E04-05: the family's order task names the medicine line it is for.

`task.medication_line_id`: the medicine line a task made on his yes to "Ask the family to
order." is for, tied to the line on the same profile. It is how one open order task a line a
day is found again, so a second yes that day answers with the task already on the list, and
how the family's list shows the chemical name and strength beside the task's words.

`task_errand` gains `order` and `confirm_subject` gains `order`: non-native enums with no
database constraint, so no schema change for them.

Follows main's head when this was written (0028_whatsapp_opt_in); B1 is taking 0029, so the
operator repoints `down_revision` at merge time if it lands first.

Revision ID: 0030_order_task
Revises: 0028_whatsapp_opt_in
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_order_task"
down_revision = "0028_whatsapp_opt_in"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task") as task:
        task.add_column(sa.Column("medication_line_id", sa.Uuid(), nullable=True))
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


def downgrade() -> None:
    op.drop_index("ix_task_medication_line_id", table_name="task")
    with op.batch_alter_table("task") as task:
        task.drop_constraint("fk_task_medication_line_profile", type_="foreignkey")
        task.drop_constraint("fk_task_medication_line_id_medication_line", type_="foreignkey")
        task.drop_column("medication_line_id")
