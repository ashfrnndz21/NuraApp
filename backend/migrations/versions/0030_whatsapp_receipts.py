"""#158 and #162: each inbound WhatsApp message handled once, and "which tablet?".

- `whatsapp_receipt`: one inbound message by the provider's own id, never its words —
  whether it was handled, and how often handling it failed. A redelivery of a message
  handled already is skipped; one that failed is tried again. It names no profile: a message
  is received before anyone knows whose it is.
- `whatsapp_dose_question`: "which tablet?", asked when a "Taken" or "given" reply could be
  about more than one tablet at that moment; the doses it read out, in their order, and its
  one change, the answer. Tied to its thread on the same profile.

B1 takes 0029; this goes on main's head at the time it is pushed, and the operator repoints
`down_revision` if another story lands first.

Revision ID: 0030_whatsapp_receipts
Revises: 0028_whatsapp_opt_in
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_whatsapp_receipts"
down_revision = "0028_whatsapp_opt_in"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_receipt",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider_message_id", sa.String(length=128), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("provider_message_id", name="uq_whatsapp_receipt_provider_message"),
    )
    op.create_table(
        "whatsapp_dose_question",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("thread_id", sa.Uuid(), sa.ForeignKey("whatsapp_thread.id"), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("doses", sa.JSON(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_whatsapp_dose_question_profile_id_id"),
        sa.ForeignKeyConstraint(
            ["profile_id", "thread_id"],
            ["whatsapp_thread.profile_id", "whatsapp_thread.id"],
            name="fk_whatsapp_dose_question_thread_profile",
        ),
    )
    op.create_index(
        "ix_whatsapp_dose_question_profile_id", "whatsapp_dose_question", ["profile_id"]
    )
    op.create_index("ix_whatsapp_dose_question_thread_id", "whatsapp_dose_question", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_whatsapp_dose_question_thread_id", table_name="whatsapp_dose_question")
    op.drop_index("ix_whatsapp_dose_question_profile_id", table_name="whatsapp_dose_question")
    op.drop_table("whatsapp_dose_question")
    op.drop_table("whatsapp_receipt")
