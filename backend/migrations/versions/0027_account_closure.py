"""Closing an account (#143): the closing that waits out its window, and its record.

`account_closure` is a row of the profile, tied to it like every other. `erasure_record` is not:
it outlives the profile it records, keeping the consent rows as they stood and the one line
that says the graph was erased (`docs/trust/pdpa-data-map.md` §4).

Revision ID: 0027_account_closure
Revises: 0026_relationship_codes
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_account_closure"
down_revision = "0026_relationship_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_closure",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_account_closure_profile_id_id"),
    )
    op.create_index("ix_account_closure_profile_id", "account_closure", ["profile_id"])
    op.create_table(
        "erasure_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column(
            "region", sa.Enum("SG", "MY", name="region", native_enum=False, length=32), nullable=False
        ),
        sa.Column("requested_by_person_id", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consents", sa.JSON(), nullable=False),
        sa.Column("removed", sa.JSON(), nullable=False),
    )
    op.create_index("ix_erasure_record_profile_id", "erasure_record", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_erasure_record_profile_id", table_name="erasure_record")
    op.drop_table("erasure_record")
    op.drop_index("ix_account_closure_profile_id", table_name="account_closure")
    op.drop_table("account_closure")
