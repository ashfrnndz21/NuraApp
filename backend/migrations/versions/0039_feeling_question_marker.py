"""#205: an outbound WhatsApp message is marked when its words put the feeling question to
him, not named for the template that carried it.

`whatsapp_message.asks_feeling`: set at `send` from the rendered words themselves
(`app.reasoning.feelings.strings.asks_about_feeling`), true for the plain check-in template
and for the day's check-in nudge alike — and for anything later that asks the same question
the same way. `inbound._check_in_open` reads this column now, in place of a check against the
literal template name `feeling_check_in`, which is why his "OK" to the nudge's asking was
being told there was no question open for him: two different things asked him the same
question, and only one of their names was ever checked. Nullable at the model, non-null here
with a false default, so every row already in the table keeps meaning what it always did — no
feeling question was recorded against it before this column existed.

Revision ID: 0039_feeling_question_marker
Revises: 0036_drug_match_confidence
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039_feeling_question_marker"
down_revision = "0036_drug_match_confidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("whatsapp_message") as batch:
        batch.add_column(
            sa.Column("asks_feeling", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("whatsapp_message") as batch:
        batch.drop_column("asks_feeling")
