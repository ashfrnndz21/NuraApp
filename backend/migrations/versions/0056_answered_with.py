"""FIX BEFORE MERGE, the independent safety review: a review card's answer to its own D-2
("whose paper is it") or D-4b (a likely duplicate) question used to write no audit line at
all on success — `answer_review_card_question` (`app.ingestion.review`) mutates the card and
flushes, but nothing calls `app.audit.trail.record` for it; `@audited` only writes a line on
a *refusal*. The trail is silent on the one decision this whole package exists to make safe:
whether "mine"/"someone else's" or "same paper"/"different" was said.

`audit_entry.answered_with`: one more `refused_because`-shaped column — a name from a closed
set, never free text, following the very discipline `AuditEntry`'s own module docstring
states ("It never says what the thing said"). `answer_review_card_question` now writes an
explicit `record(...)` line carrying the already-validated `value` here (`WHOSE_PAPER_ANSWERS`
`| DUPLICATE_PAPER_ANSWERS`, checked before this ever runs — `NotAnAnswer` otherwise) —
never the paper's own printed name, which was never on this table to begin with.

Reversible on SQLite (`batch_alter_table`), the same discipline every migration since
`0054_insurance_policy_essentials` keeps.

Revision ID: 0056_answered_with
Revises: 0055_whose_paper_and_duplicates
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056_answered_with"
down_revision = "0055_whose_paper_and_duplicates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("audit_entry") as batch:
        batch.add_column(sa.Column("answered_with", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("audit_entry") as batch:
        batch.drop_column("answered_with")
