"""Health Analyst backend: the weekly report and the one new fact a rule needs to tell a
supplement apart from a prescription line for its own purposes.

`medication_line.category` is a plain string, nullable. This migration's own backfill gives
existing rows the same word `product_kind` already gives them ("prescription", "supplement"
or "tcm") where the register named one, and `None` where it did not, never a guess; the write
path (`app.medicines.service._one_product`) sets it the same way for every new line from here
on. It is a second word beside `product_kind` on purpose — `product_kind` is the register's
own classification of the product; `category` is the Analyst's own question, "is this
something to ask about the way a supplement is," which is about how the Analyst reads the
line, not about what the register matched. A future write path is free to diverge the two;
nothing here assumes they always agree.

`insight_report` is one row per Health Analyst report: the week it is for, the boundary line
it carried, and its sections and insights, kept as JSON the way `TrendCard.lines` and
`state_snapshot.computed_from` already keep composed, already-verified text. `@monotonic`
(`app.db.monotonic`) gives it `seq`, because `GET /profiles/{id}/insights` is a "latest wins"
read (`app.db.monotonic`'s own docstring, #192/#218): two reports written in the same request,
or under a frozen clock, must resolve to one winner, never an arbitrary one.

Revision ID: 0050_health_analyst
Revises: 0049_condition_answers
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0050_health_analyst"
down_revision = "0049_condition_answers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("medication_line") as batch:
        batch.add_column(sa.Column("category", sa.String(length=32), nullable=True))
    op.execute("UPDATE medication_line SET category = product_kind WHERE product_kind IS NOT NULL")

    op.create_table(
        "insight_report",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id", sa.Uuid(), sa.ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("week_of", sa.Date(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("boundary", sa.JSON(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("profile_id", "id", name="uq_insight_report_profile_id_id"),
    )
    op.create_index("ix_insight_report_profile_id", "insight_report", ["profile_id"])
    op.create_index("ix_insight_report_generated_at", "insight_report", ["generated_at"])
    op.create_index("ix_insight_report_seq", "insight_report", ["seq"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE SEQUENCE insight_report_seq_seq")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP SEQUENCE insight_report_seq_seq")
    op.drop_index("ix_insight_report_seq", table_name="insight_report")
    op.drop_index("ix_insight_report_generated_at", table_name="insight_report")
    op.drop_index("ix_insight_report_profile_id", table_name="insight_report")
    op.drop_table("insight_report")
    with op.batch_alter_table("medication_line") as batch:
        batch.drop_column("category")
