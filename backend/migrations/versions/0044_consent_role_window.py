"""#185: his yes binds the role and the window he agreed to, not only the person and the
parts. `consent.role` and `consent.window` record, for a `SHARE_WITH_PERSON` agreement, the
role (`app.keys.scopes.KeyRole`) and the window (`app.keys.scopes.KeyWindow`) the rendered
words named; nullable, since every other purpose — and every row written before this
migration — carries neither. `app.keys.grants.grant_key` refuses a key cut for a different
role, or for a window that would outlast this one, against `require_consent`'s read of these
two columns.

Repointed onto 0039 (#205), which landed on main first, so the directory keeps one head.

Revision ID: 0044_consent_role_window
Revises: 0039_feeling_question_marker
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_consent_role_window"
down_revision = "0043_feeling_note_said"
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
KEY_WINDOW = sa.Enum(
    "always",
    "one_day",
    "thirty_days",
    "seventy_two_hours",
    name="key_window",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    with op.batch_alter_table("consent") as batch:
        batch.add_column(sa.Column("role", KEY_ROLE, nullable=True))
        batch.add_column(sa.Column("window", KEY_WINDOW, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("consent") as batch:
        batch.drop_column("window")
        batch.drop_column("role")
