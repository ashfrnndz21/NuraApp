"""A key holder's own answers at the key-accept step: WhatsApp, and the family's group (#143).

Revision ID: 0027_whatsapp_opt_in
Revises: 0026_account_closure
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_whatsapp_opt_in"
down_revision = "0026_account_closure"
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
        sa.Column("joins_group", sa.Boolean(), nullable=False),
        sa.Column("wording_version", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("said_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_whatsapp_opt_in_profile_id_id"),
    )
    op.create_index("ix_whatsapp_opt_in_profile_id", "whatsapp_opt_in", ["profile_id"])
    op.create_index("ix_whatsapp_opt_in_person_id", "whatsapp_opt_in", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_whatsapp_opt_in_person_id", table_name="whatsapp_opt_in")
    op.drop_index("ix_whatsapp_opt_in_profile_id", table_name="whatsapp_opt_in")
    op.drop_table("whatsapp_opt_in")
