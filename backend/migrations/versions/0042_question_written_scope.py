"""RE-02 follow-up: `question.written_scope` (#120, the ADR 0004 decision 10 pattern).

A question generated from a feeling note (`QuestionSource.FEELING`) carries the note's own
words verbatim, and the note is the record's (`Scope.RECORDS`) — but every question was read
under `Scope.VISITS` alone, so a `VIEWER` key (`VISITS`, no `RECORDS`) read his feeling note
word for word through the questions list, the one place the brief's own narrowing of the same
words did not reach (found by review on PR #233).

`Question` joins `Artifact` and `Event` as a table whose rows are written under more than one
scope: `written_scope` is set by `app.keys.repository.scoped_new` from the scope of the write
(`app.reasoning.visits.questions._write`, `Scope.RECORDS` for a `QuestionSource.FEELING`
question, `Scope.VISITS` for every other source), and `scoped_select` — every read, including
`current_questions` and `patient_card` — narrows to a key that holds it.

Every row written before this column existed was written the one way `_write` always wrote
one until now: under the visits' own scope. `visits` is not a guess for the backfill; it is
what actually happened.

Revision ID: 0042_question_written_scope
Revises: 0041_feed_item_private_to
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042_question_written_scope"
down_revision = "0041_feed_item_private_to"
branch_labels = None
depends_on = None

SCOPE = sa.Enum(
    "medicines",
    "visits",
    "readings",
    "records",
    "notes",
    "money",
    "family",
    "emergency",
    "ask",
    "send",
    "profile",
    name="scope",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    with op.batch_alter_table("question") as batch:
        batch.add_column(sa.Column("written_scope", SCOPE, nullable=True))
    op.execute("UPDATE question SET written_scope = 'visits' WHERE written_scope IS NULL")
    with op.batch_alter_table("question") as batch:
        batch.alter_column("written_scope", existing_type=SCOPE, nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("question") as batch:
        batch.drop_column("written_scope")
