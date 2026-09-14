"""E00-02: the consent record.

One row per agreement: who gave it, to what, in which version of the words, in which
language, how it was captured, on what basis, when, and when it was withdrawn. Rows are
never edited or removed; withdrawing marks one, new words add one. No column can hold
health content.

Revision ID: 0003_consent
Revises: 0002_audit
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_consent"
down_revision = "0002_audit"
branch_labels = None
depends_on = None

PURPOSE = sa.Enum(
    "hold_health_record",
    "share_with_family",
    "recording",
    "whatsapp",
    name="consent_purpose",
    native_enum=False,
    length=32,
)
CHANNEL = sa.Enum(
    "app",
    "whatsapp",
    "paper",
    "verbal_witnessed",
    name="consent_channel",
    native_enum=False,
    length=32,
)
BASIS = sa.Enum(
    "owner",
    "lpa",
    "medical_letter",
    "verbal_recorded",
    name="consent_basis",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    op.create_table(
        "consent",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("purpose", PURPOSE, nullable=False),
        sa.Column("text_version", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("captured_via", CHANNEL, nullable=False),
        sa.Column("basis", BASIS, nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
    )
    op.create_index("ix_consent_profile_id", "consent", ["profile_id"])
    op.create_index("ix_consent_person_id", "consent", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_consent_person_id", table_name="consent")
    op.drop_index("ix_consent_profile_id", table_name="consent")
    op.drop_table("consent")
