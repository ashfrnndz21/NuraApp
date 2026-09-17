"""design-direction.md, Connect's "Upcoming Call": a call on the calendar with one family
member — who, when, the link the family gave (or none, and Nura rings his phone instead).

`scheduled_call` is a new table, on the family list's part like the roster and the tasks
(`app.family.models.ScheduledCall`). `with_person_id` is a plain foreign key to `person`, like
every other person reference on a family row (`document.added_by_person_id`,
`scheduled_push.composed_by_person_id`): a person is a global account, never profile-scoped,
so there is no `(profile_id, id)` pair on it to tie against. The row's one change is its
cancelling (`cancelled_at`).

No steps/heart-rate/sleep/water/food column changes ride with this: those five are Facts and
Events, in the shapes those tables already have, so no schema change for them, and
`docs/trust/pdpa-data-map.md` was regenerated for the one table this migration does add.

Revision ID: 0045_scheduled_call
Revises: 0044_consent_role_window
Create Date: 2026-09-17

Renumbered from 0040 at merge time (#235): main's chain moved to 0043_feeling_note_said
while this branch sat behind it, and this revision is pinned ahead of #225's
0044_consent_role_window, now merged to main and main's actual head.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045_scheduled_call"
down_revision = "0044_consent_role_window"
branch_labels = None
depends_on = None


def _profile_id() -> sa.Column[sa.Uuid]:
    return sa.Column(
        "profile_id", sa.Uuid(), sa.ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )


def _row_of_profile(table: str) -> sa.UniqueConstraint:
    return sa.UniqueConstraint("profile_id", "id", name=f"uq_{table}_profile_id_id")


def upgrade() -> None:
    op.create_table(
        "scheduled_call",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("with_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("call_link", sa.String(length=300), nullable=True),
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column("added_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        _row_of_profile("scheduled_call"),
    )
    op.create_index("ix_scheduled_call_profile_id", "scheduled_call", ["profile_id"])
    op.create_index("ix_scheduled_call_with_person_id", "scheduled_call", ["with_person_id"])
    op.create_index("ix_scheduled_call_scheduled_at", "scheduled_call", ["scheduled_at"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_call_scheduled_at", table_name="scheduled_call")
    op.drop_index("ix_scheduled_call_with_person_id", table_name="scheduled_call")
    op.drop_index("ix_scheduled_call_profile_id", table_name="scheduled_call")
    op.drop_table("scheduled_call")
