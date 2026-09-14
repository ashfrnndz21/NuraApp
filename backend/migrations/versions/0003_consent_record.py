"""E00-02: the consent record.

One row per agreement: who gave it, for whom, to what, in which version of the words and
the words themselves, in which language, how it was captured, on what basis and what is
behind the basis, when, and when it was withdrawn. Rows are never edited or removed;
withdrawing marks one, new words add one. No column can hold health content.

It follows the memory stores because a proxy basis points at the artefact behind it.

Revision ID: 0003_consent
Revises: 0003_memory
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_consent"
down_revision = "0003_memory"
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
        # Set for a per-holder purpose (sharing): the person the agreement is about.
        sa.Column("holder_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        # For a per-holder purpose: the parts of the record the words let that person see.
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("text_version", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        # The words as read, copied at the moment of agreement.
        sa.Column("wording_text", sa.Text(), nullable=False),
        sa.Column("captured_via", CHANNEL, nullable=False),
        sa.Column("basis", BASIS, nullable=False),
        # What is behind a proxy basis: the document or recording, and who heard it.
        sa.Column("basis_artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=True),
        sa.Column("witness_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
    )
    op.create_index("ix_consent_profile_id", "consent", ["profile_id"])
    op.create_index("ix_consent_person_id", "consent", ["person_id"])
    op.create_index("ix_consent_holder_person_id", "consent", ["holder_person_id"])


def downgrade() -> None:
    op.drop_index("ix_consent_holder_person_id", table_name="consent")
    op.drop_index("ix_consent_person_id", table_name="consent")
    op.drop_index("ix_consent_profile_id", table_name="consent")
    op.drop_table("consent")
