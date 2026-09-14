"""E00-07: the audit entry.

One line per read, write and share of a profile's data, readable by the patient and the
chief he named. The table holds what was touched and never what it said, which is why there
is no column here for a body, a value or a note.

Revision ID: 0002_audit
Revises: 0001_accounts
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_audit"
down_revision = "0001_accounts"
branch_labels = None
depends_on = None

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
SCOPE = sa.Enum(
    "medicines",
    "visits",
    "readings",
    "records",
    "notes",
    "money",
    "family",
    "emergency",
    "ask",
    "send",
    name="scope",
    native_enum=False,
    length=32,
)
ACTION = sa.Enum("read", "write", "share", name="audit_action", native_enum=False, length=32)
OUTCOME = sa.Enum("allowed", "refused", name="audit_outcome", native_enum=False, length=32)
CHANNEL = sa.Enum(
    "app",
    "whatsapp",
    "share_link",
    "clinic",
    "system",
    name="audit_channel",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    op.create_table(
        "audit_entry",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        # Null for the owner: he reaches his own graph without a key, so there is none to name.
        sa.Column("actor_role", KEY_ROLE, nullable=True),
        sa.Column("key_id", sa.Uuid(), sa.ForeignKey("key.id"), nullable=True),
        sa.Column("action", ACTION, nullable=False),
        sa.Column("scope", SCOPE, nullable=False),
        sa.Column("channel", CHANNEL, nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("outcome", OUTCOME, nullable=False),
        sa.Column("refused_because", sa.String(length=64), nullable=True),
        sa.Column("shared_with_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("shared_with_label", sa.String(length=120), nullable=True),
    )
    op.create_index("ix_audit_entry_profile_id", "audit_entry", ["profile_id"])
    op.create_index("ix_audit_entry_at", "audit_entry", ["at"])
    op.create_index("ix_audit_entry_actor_person_id", "audit_entry", ["actor_person_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_entry_actor_person_id", table_name="audit_entry")
    op.drop_index("ix_audit_entry_at", table_name="audit_entry")
    op.drop_index("ix_audit_entry_profile_id", table_name="audit_entry")
    op.drop_table("audit_entry")
