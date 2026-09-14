"""E00-01: person, profile and key.

The health graph is the profile; every table of profile data added after this one carries
`profile_id` with this foreign key, which is what makes the patient node its owner.

Revision ID: 0001_accounts
Revises:
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_accounts"
down_revision = None
branch_labels = None
depends_on = None

REGION = sa.Enum("SG", "MY", name="region", native_enum=False, length=32)
KEY_ROLE = sa.Enum(
    "chief",
    "caregiver",
    "viewer",
    "helper",
    "emergency",
    "clinic",
    name="key_role",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    op.create_table(
        "person",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("region", REGION, nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("phone_e164", sa.String(length=20), nullable=True, unique=True),
        sa.Column("email", sa.String(length=320), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "profile",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("region", REGION, nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        # Unique: a person owns at most one health graph, and it has exactly one owner.
        sa.Column("owner_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_person_id", name="uq_profile_owner_person_id"),
    )
    op.create_table(
        "key",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("holder_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("role", KEY_ROLE, nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("basis", sa.String(length=64), nullable=False),
        sa.Column("granted_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_key_profile_id", "key", ["profile_id"])
    op.create_index("ix_key_holder_person_id", "key", ["holder_person_id"])


def downgrade() -> None:
    op.drop_index("ix_key_holder_person_id", table_name="key")
    op.drop_index("ix_key_profile_id", table_name="key")
    op.drop_table("key")
    op.drop_table("profile")
    op.drop_table("person")
