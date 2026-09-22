"""D-2 ("whose paper is it") and D-4 (duplicates), audit `docs/design/audit-2026-09-22.md`
§3.2/§5: a card files nothing until a mismatch or a likely duplicate is answered, and the
same bytes re-uploaded for a profile can never become a second artifact at all.

`artifact`: a unique index on `(profile_id, sha256)` (D-4a). Before this, every upload wrote
a fresh `Artifact` row regardless of digest — re-uploading the same bytes cost a second read,
a second model call and a second review card, silently (audit §1.6, §3.2: "the same policy
twice ... the same panel three times ... no warning"). The application now checks for an
existing artifact by digest before writing one (`app.ingestion.duplicates`) and the index is
the backstop: two concurrent uploads of the same bytes can now only ever produce one row,
whichever request the database serialises first.

`review_card`: five nullable columns, `NULL` on every row written before this package.
`pending_question`/`question_payload`/`question_answer`/`question_answered_at`/
`question_answered_by_person_id` are the one mechanism both D-2 (identity mismatch) and D-4b
(a likely duplicate under a different digest) ask their question through — set at read time,
answered through `POST .../review-cards/{id}/answer`, checked by `confirm_review_card` before
anything is written. `discarded_at` is set when the answer keeps the paper out of the record
entirely ("someone else's", "yes, the same paper") — the card and its artifact are kept, nothing
about them is deleted, but the card can never be confirmed.

Reversible on SQLite (`batch_alter_table`), the same discipline `0054_insurance_policy_essentials`
already keeps.

Revision ID: 0055_whose_paper_and_duplicates
Revises: 0054_insurance_policy_essentials
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0055_whose_paper_and_duplicates"
down_revision = "0054_insurance_policy_essentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("artifact") as batch:
        batch.create_index(
            "ix_artifact_profile_sha256", ["profile_id", "sha256"], unique=True
        )
    with op.batch_alter_table("review_card") as batch:
        batch.add_column(sa.Column("pending_question", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("question_payload", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("question_answer", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("question_answered_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("question_answered_by_person_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("discarded_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key(
            "fk_review_card_question_answered_by",
            "person",
            ["question_answered_by_person_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("review_card") as batch:
        batch.drop_constraint("fk_review_card_question_answered_by", type_="foreignkey")
        batch.drop_column("discarded_at")
        batch.drop_column("question_answered_by_person_id")
        batch.drop_column("question_answered_at")
        batch.drop_column("question_answer")
        batch.drop_column("question_payload")
        batch.drop_column("pending_question")
    with op.batch_alter_table("artifact") as batch:
        batch.drop_index("ix_artifact_profile_sha256")
