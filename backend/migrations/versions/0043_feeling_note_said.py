"""PR #233 review, finding 3a: `feeling_note.said` — what a tap's note said, by name.

`app.reasoning.visits.questions.question_from_feeling` used to read `note.lines[0]` to build
the question a feeling note becomes: the TELL line is index 0 today only because
`compose_note` (`app.reasoning.feelings.inference`) happens to build `shown` that way — an
invariant that lived in one function and was leaned on, unstated, by another, so a future
reordering of `compose_note` (leading with a reason instead of the TELL line, say) would
silently let a medicine-naming sentence reach a `Question` without its `DO_NOT_STOP` pair
(#157), with nothing to catch it.

`said` makes the guarantee structural: `compose_note` now returns it by name, `_write`
(`app.reasoning.feelings.service`) persists it by name, and `question_from_feeling` reads it
by name — `lines[0]` is still exactly this value (unchanged), but no reader has to know that.

Every row already written has `lines`, and its first line is exactly what `said` names (the
TELL line was always built first, and is not read positionally anywhere the invariant
depends on it — this migration is what stops that). The backfill is a plain copy, not a
guess.

Revision ID: 0043_feeling_note_said
Revises: 0042_question_written_scope
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_feeling_note_said"
down_revision = "0042_question_written_scope"
branch_labels = None
depends_on = None

LINE_LENGTH = 200


def upgrade() -> None:
    with op.batch_alter_table("feeling_note") as batch:
        batch.add_column(sa.Column("said", sa.String(length=LINE_LENGTH), nullable=True))
    bind = op.get_bind()
    feeling_note = sa.table(
        "feeling_note",
        sa.column("id"),
        sa.column("lines", sa.JSON()),
        sa.column("headline", sa.String(length=LINE_LENGTH)),
        sa.column("said", sa.String(length=LINE_LENGTH)),
    )
    for row in bind.execute(sa.select(feeling_note.c.id, feeling_note.c.lines, feeling_note.c.headline)):
        first = row.lines[0] if row.lines else row.headline
        bind.execute(
            sa.update(feeling_note).where(feeling_note.c.id == row.id).values(said=first)
        )
    with op.batch_alter_table("feeling_note") as batch:
        batch.alter_column("said", existing_type=sa.String(length=LINE_LENGTH), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("feeling_note") as batch:
        batch.drop_column("said")
