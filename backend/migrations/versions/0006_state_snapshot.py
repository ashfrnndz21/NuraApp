"""E00-04: the State snapshot.

One row per recomputation: the six dimensions, the posture, what triggered it, what it was
computed from, and the snapshot it supersedes. `sequence` is unique within a profile, so the
current State is the highest one and two writers cannot both think they wrote it. A snapshot
that says a fact caused it must name the fact, in the table as well as in the service, and
the fact and the snapshot it supersedes are tied to the same profile the way provenance is
(0005): `(profile_id, trigger_fact_id)` points at `fact(profile_id, id)`.

Revision ID: 0006_state_snapshot
Revises: 0005_memory_review
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_state_snapshot"
down_revision = "0005_memory_review"
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
    "asked",
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
        # The worst of the six dimensions' postures; each dimension carries its own, and why.
        sa.Column("posture", POSTURE, nullable=False),
        sa.Column("trigger", STATE_TRIGGER, nullable=False),
        sa.Column("trigger_fact_id", sa.Uuid(), sa.ForeignKey("fact.id"), nullable=True),
        sa.Column("supersedes_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=True),
        # The six dimensions, one column each, so the table names them all.
        sa.Column("clinical", sa.JSON(), nullable=False),
        sa.Column("functional", sa.JSON(), nullable=False),
        sa.Column("cognitive", sa.JSON(), nullable=False),
        sa.Column("situational", sa.JSON(), nullable=False),
        sa.Column("preference", sa.JSON(), nullable=False),
        sa.Column("family", sa.JSON(), nullable=False),
        # The ids this snapshot was computed from, by kind: how a read tells whether the
        # record has moved past it without comparing what it says.
        sa.Column("computed_from", sa.JSON(), nullable=False),
        # When a window in this snapshot closes: time alone is enough to make State recompute.
        sa.Column("stale_after", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "sequence", name="uq_state_snapshot_sequence"),
        sa.UniqueConstraint("profile_id", "id", name="uq_state_snapshot_profile_id_id"),
        sa.CheckConstraint(
            "trigger <> 'new_fact' OR trigger_fact_id IS NOT NULL",
            name="ck_state_trigger_names_its_fact",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "trigger_fact_id"],
            ["fact.profile_id", "fact.id"],
            name="fk_state_snapshot_trigger_fact_profile",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "supersedes_id"],
            ["state_snapshot.profile_id", "state_snapshot.id"],
            name="fk_state_snapshot_supersedes_profile",
        ),
    )
    op.create_index("ix_state_snapshot_profile_id", "state_snapshot", ["profile_id"])
    op.create_index("ix_state_snapshot_computed_at", "state_snapshot", ["computed_at"])


def downgrade() -> None:
    for index in _INDEXES:
        op.drop_index(index, table_name="state_snapshot")
    op.drop_table("state_snapshot")
