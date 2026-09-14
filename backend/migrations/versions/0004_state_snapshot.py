"""E00-04: the State snapshot.

One row per recomputation: the six dimensions, the posture, what triggered it and the
snapshot it supersedes. `sequence` is unique within a profile, so the current State is the
highest one and two writers cannot both think they wrote it. A snapshot that says a fact
caused it must name the fact, in the table as well as in the service.

Revision ID: 0004_state
Revises: 0003_memory
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_state"
down_revision = "0003_memory"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


POSTURE = _enum("posture", "stable", "watch", "act")
STATE_TRIGGER = _enum(
    "state_trigger",
    "first",
    "new_fact",
    "new_event",
    "episode_change",
    "spine_change",
    "key_change",
    "time_passed",
)

_INDEXES = ("ix_state_snapshot_profile_id", "ix_state_snapshot_computed_at")


def upgrade() -> None:
    op.create_table(
        "state_snapshot",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posture", POSTURE, nullable=False),
        # Why the posture is what it is: the fact ids and episode ids that raised it.
        sa.Column("posture_because", sa.JSON(), nullable=False),
        sa.Column("trigger_kind", STATE_TRIGGER, nullable=False),
        sa.Column("trigger_fact_id", sa.Uuid(), sa.ForeignKey("fact.id"), nullable=True),
        sa.Column(
            "supersedes_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=True
        ),
        # The six dimensions, one column each, so the table names them all.
        sa.Column("clinical", sa.JSON(), nullable=False),
        sa.Column("functional", sa.JSON(), nullable=False),
        sa.Column("cognitive", sa.JSON(), nullable=False),
        sa.Column("situational", sa.JSON(), nullable=False),
        sa.Column("preference", sa.JSON(), nullable=False),
        sa.Column("family", sa.JSON(), nullable=False),
        # When a window in this snapshot closes: time alone is enough to make State recompute.
        sa.Column("stale_after", sa.DateTime(timezone=True), nullable=True),
        # The newest fact folded in, or null when none were: a snapshot that folded nothing
        # is behind the moment any fact exists at all.
        sa.Column("folded_through", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "sequence", name="uq_state_snapshot_sequence"),
        sa.CheckConstraint(
            "trigger_kind <> 'new_fact' OR trigger_fact_id IS NOT NULL",
            name="ck_state_trigger_names_its_fact",
        ),
    )
    op.create_index("ix_state_snapshot_profile_id", "state_snapshot", ["profile_id"])
    op.create_index("ix_state_snapshot_computed_at", "state_snapshot", ["computed_at"])


def downgrade() -> None:
    for index in _INDEXES:
        op.drop_index(index, table_name="state_snapshot")
    op.drop_table("state_snapshot")
