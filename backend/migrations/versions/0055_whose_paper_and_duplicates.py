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

B4, the independent safety review: this index cannot simply be created on a database that
already has duplicate `(profile_id, sha256)` groups — `CREATE UNIQUE INDEX` fails outright,
and the owner's own database has nine (sizes 2, 2, 2, 2, 2, 2, 4, 5, 6). `_collapse_duplicate_
artifacts` runs first: within each group it keeps the earliest row (by `stored_at`, the id as
a stable tiebreak) as the survivor, re-points every other table's reference to a loser's id
onto the survivor's — `_ARTIFACT_REFERENCES` names every one of them, read from the models
that declare `ForeignKey("artifact.id")`, not guessed — and only then deletes the loser
`artifact` rows. Nothing that cites a loser is ever deleted before it is re-pointed: a
`fact.artifact_id` (a confirmed fact's own provenance), a `review_card.artifact_id`, an
`event.artifact_id` and every other reference move first, in the same unit of work as the
index. Raw SQL throughout, no ORM import: a migration outlives the models it was written
against.

**What happens to a collapsed group's review cards.** A `review_card` row is never deleted or
merged — only its `artifact_id` is re-pointed. If two duplicate uploads each already had their
own card before this migration (the failure mode this whole package closes), both cards
survive, now both naming the one surviving artifact — `app.ingestion.review.card_for_artifact`
already has to tolerate more than one card per artifact for an unrelated, pre-existing reason
(the same "at most one card" gap the audit's own follow-ups name), so this migration does not
newly break an invariant that already had exceptions; it is called out here so the reviewer
checks it, not because it is a new defect.

`review_card`: five nullable columns, `NULL` on every row written before this package.
`pending_question`/`question_payload`/`question_answer`/`question_answered_at`/
`question_answered_by_person_id` are the one mechanism both D-2 (identity mismatch) and D-4b
(a likely duplicate under a different digest) ask their question through — set at read time,
answered through `POST .../review-cards/{id}/answer`, checked by `confirm_review_card` before
anything is written. `discarded_at` is set when the answer keeps the paper out of the record
entirely ("someone else's", "yes, the same paper") — the card and its artifact are kept, nothing
about them is deleted, but the card can never be confirmed.

Reversible on SQLite (`batch_alter_table`), the same discipline `0054_insurance_policy_essentials`
already keeps. The collapse itself is not reversed on downgrade — there is no way back to rows
that were never wrong, only duplicated; downgrading only drops the index and the new columns.

Revision ID: 0055_whose_paper_and_duplicates
Revises: 0054_insurance_policy_essentials
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections import defaultdict

import sqlalchemy as sa
from alembic import op

revision = "0055_whose_paper_and_duplicates"
down_revision = "0054_insurance_policy_essentials"
branch_labels = None
depends_on = None


_ARTIFACT_REFERENCES: tuple[tuple[str, str], ...] = (
    ("medication_line", "source_artifact_id"),
    ("medication_supply", "artifact_id"),
    ("review_card", "artifact_id"),
    ("event_note", "artifact_id"),
    ("consult_recording", "artifact_id"),
    ("consult_recording", "transcript_artifact_id"),
    ("event", "artifact_id"),
    ("fact", "artifact_id"),
    ("attachment", "artifact_id"),
    ("thread_photo", "artifact_id"),
    ("document", "artifact_id"),
    ("insight_report", "artifact_id"),
    ("visit_summary", "artifact_id"),
    ("visit_summary", "recording_artifact_id"),
    ("consent", "basis_artifact_id"),
    ("biography_paper", "artifact_id"),
    ("whatsapp_message", "artifact_id"),
    ("turn", "question_artifact_id"),
    ("turn", "answer_artifact_id"),
    ("red_flag", "artifact_id"),
)
"""Every column in the schema that names an `artifact.id`, read off the models that declare
`ForeignKey("artifact.id")` (`grep -rn 'ForeignKey("artifact.id")' backend/app`) — kept as a
plain tuple, not imported from the models themselves, so this migration keeps working exactly
as written no matter how a later model changes. A column added here after this revision ships
needs its own migration to re-point the same way; that is true of any schema change and is not
special to this one."""


def _collapse_duplicate_artifacts() -> None:
    """Before the unique index can be created, no two rows may share `(profile_id, sha256)`.
    Groups that do are collapsed: the earliest row survives, every reference to a loser moves
    to the survivor, and only then is the loser deleted."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, profile_id, sha256, stored_at FROM artifact ORDER BY stored_at, id")
    ).fetchall()
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        groups[(row.profile_id, row.sha256)].append(row.id)
    duplicate_groups = {key: ids for key, ids in groups.items() if len(ids) > 1}
    if not duplicate_groups:
        return
    for ids in duplicate_groups.values():
        survivor, *losers = ids  # earliest first (the SELECT's own ORDER BY)
        for loser in losers:
            for table, column in _ARTIFACT_REFERENCES:
                bind.execute(
                    sa.text(f"UPDATE {table} SET {column} = :survivor WHERE {column} = :loser"),
                    {"survivor": survivor, "loser": loser},
                )
            bind.execute(sa.text("DELETE FROM artifact WHERE id = :loser"), {"loser": loser})


def upgrade() -> None:
    _collapse_duplicate_artifacts()
    with op.batch_alter_table("artifact") as batch:
        batch.create_index(
            "ix_artifact_profile_sha256", ["profile_id", "sha256"], unique=True
        )
    with op.batch_alter_table("review_card") as batch:
        batch.add_column(sa.Column("pending_question", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("question_payload", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("question_answer", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("question_answered_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("question_answered_by_person_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True))
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
