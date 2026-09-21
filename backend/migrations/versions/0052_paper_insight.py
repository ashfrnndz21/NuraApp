"""Paper-scoped insight (checkpoint 3, "What it means for you", `app.reasoning.analyst.paper`):
three nullable columns on `insight_report`, set only by a paper-scoped run, `NULL` on every
row the weekly job or `POST /profiles/{id}/insights/stream` writes.

`artifact_id` names the one confirmed paper the insight is about; `headline` and `looked_at`
carry the two things a paper-scoped insight says beside its questions that the weekly report
never did — a short line, and the plain labels of what was actually read (the paper, however
many medicines, the next visit if any), kept as JSON the same way `sections` already is,
composed and already-verified text, never a row.

Revision ID: 0052_paper_insight
Revises: 0051_health_analyst
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0052_paper_insight"
down_revision = "0051_health_analyst"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("insight_report") as batch:
        batch.add_column(sa.Column("artifact_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("headline", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("looked_at", sa.JSON(), nullable=True))
        batch.create_foreign_key(
            "fk_insight_report_artifact", "artifact", ["artifact_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_insight_report_artifact_profile",
            "artifact",
            ["profile_id", "artifact_id"],
            ["profile_id", "id"],
        )
    op.create_index(
        "ix_insight_report_artifact_id", "insight_report", ["artifact_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_insight_report_artifact_id", table_name="insight_report")
    with op.batch_alter_table("insight_report") as batch:
        batch.drop_constraint("fk_insight_report_artifact_profile", type_="foreignkey")
        batch.drop_constraint("fk_insight_report_artifact", type_="foreignkey")
        batch.drop_column("looked_at")
        batch.drop_column("headline")
        batch.drop_column("artifact_id")
