"""B1: the insurer on the emergency card; the panel hospital and a doctor's hours.

One table of profile data — `insurer`, who insures him, typed on a yes (E13-01): a history,
the newest row in force, tied to its profile like the delivery settings (0023). And three
columns on the directory's `provider` (E03-03, E19-05): whether a hospital is on his insurance
(`panel`), and when a doctor or clinic answers (`opens_at`, `closes_at`), which a red flag's
escalation reads. The new trigger type (`visit_brief`) and the new card kind (`call_clinic`)
are values of enums stored as checked strings: no DDL.

Revision ID: 0027_brief_safety
Revises: 0026_relationship_codes
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_brief_safety"
down_revision = "0026_relationship_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insurer",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("policy_reference", sa.String(length=40), nullable=True),
        sa.Column("set_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column(
            "confirmation_id", sa.Uuid(), sa.ForeignKey("confirmation.id"), nullable=False
        ),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_insurer_profile_id_id"),
    )
    op.create_index("ix_insurer_profile_id", "insurer", ["profile_id"])
    op.create_index("ix_insurer_set_at", "insurer", ["set_at"])
    with op.batch_alter_table("provider") as batch:
        batch.add_column(
            sa.Column("panel", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("opens_at", sa.Time(), nullable=True))
        batch.add_column(sa.Column("closes_at", sa.Time(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("provider") as batch:
        batch.drop_column("closes_at")
        batch.drop_column("opens_at")
        batch.drop_column("panel")
    op.drop_index("ix_insurer_set_at", table_name="insurer")
    op.drop_index("ix_insurer_profile_id", table_name="insurer")
    op.drop_table("insurer")
