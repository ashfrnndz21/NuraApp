"""A person's own yes or no to Nura messaging them on WhatsApp about a profile (#143).

Revision ID: 0026_whatsapp_opt_in
Revises: 0025_account_closure
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_whatsapp_opt_in"
down_revision = "0025_account_closure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_opt_in",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("said_yes", sa.Boolean(), nullable=False),
        sa.Column("said_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_whatsapp_opt_in_profile_id_id"),
    )
    op.create_index("ix_whatsapp_opt_in_profile_id", "whatsapp_opt_in", ["profile_id"])
    op.create_index("ix_whatsapp_opt_in_person_id", "whatsapp_opt_in", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_whatsapp_opt_in_person_id", table_name="whatsapp_opt_in")
    op.drop_index("ix_whatsapp_opt_in_profile_id", table_name="whatsapp_opt_in")
    op.drop_table("whatsapp_opt_in")
