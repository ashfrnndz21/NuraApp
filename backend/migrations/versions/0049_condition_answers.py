"""w1-onboarding: `profile_settings.answers`, a tapped word's follow-up answer.

A handful of conditions.json's words now carry `ask` — the one follow-up question the mock
shows once that word is tapped ("On tablets for it" -> "For how long?"). His answer (the
option id he chose) is stored on the settings row the same way `conditions` already is, by
the word's code, and also written as a `condition_answer.<code>` fact
(`app.onboarding.settings`) so State folds it. One nullable-then-backfilled JSON column,
`{}` for every row already written (nobody had answered a question that did not exist yet).

Revision ID: 0049_condition_answers
Revises: 0048_provider_category
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049_condition_answers"
down_revision = "0048_provider_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("profile_settings") as batch:
        batch.add_column(sa.Column("answers", sa.JSON(), nullable=True))
    bind = op.get_bind()
    profile_settings = sa.table("profile_settings", sa.column("id"), sa.column("answers", sa.JSON()))
    bind.execute(sa.update(profile_settings).where(profile_settings.c.answers.is_(None)).values(answers={}))
    with op.batch_alter_table("profile_settings") as batch:
        batch.alter_column("answers", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("profile_settings") as batch:
        batch.drop_column("answers")
