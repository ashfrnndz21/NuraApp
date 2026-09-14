"""E02-01, E02-07: the review card.

Two tables. `review_card` is one photo read into fields and waiting for — or closed by — a
person's yes: it names the artefact (tied to the same profile, as provenance is tied in
0005), the kind of paper and the date on it, the high-risk class of the drug it names where
the label rule applies, and who confirmed it and when. `review_field` is one proposed
statement on a card — subject, attribute, value, unit, the extractor's confidence and where
on the page it read it — with the person's decision (proposed, confirmed, corrected,
rejected), his correction beside the proposal it does not overwrite, and the fact the field
became (tied to the same profile). Facts are never edited; these rows are where editing
happens, once, before a fact exists.

`confirm_subject` gains `review_card`, a checked string with no database constraint, so no
schema change: the person's yes to a whole card.

Revision ID: 0008_ingestion
Revises: 0007_doors_and_stewardship
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_ingestion"
down_revision = "0007_doors_and_stewardship"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


DOCUMENT_KIND = _enum(
    "document_kind", "lab_report", "medicine_label", "discharge_letter", "clinic_slip", "unknown"
)
FIELD_STATE = _enum("review_field_state", "proposed", "confirmed", "corrected", "rejected")

_INDEXES = (
    ("ix_review_card_profile_id", "review_card", ["profile_id"]),
    ("ix_review_card_artifact_id", "review_card", ["artifact_id"]),
    ("ix_review_card_created_at", "review_card", ["created_at"]),
    ("ix_review_field_profile_id", "review_field", ["profile_id"]),
    ("ix_review_field_card_id", "review_field", ["card_id"]),
)


def upgrade() -> None:
    op.create_table(
        "review_card",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=False),
        sa.Column("document_kind", DOCUMENT_KIND, nullable=False),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("high_risk_class", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_review_card_profile_id_id"),
        sa.ForeignKeyConstraint(
            ["profile_id", "artifact_id"],
            ["artifact.profile_id", "artifact.id"],
            name="fk_review_card_artifact_profile",
        ),
    )
    op.create_table(
        "review_field",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("card_id", sa.Uuid(), sa.ForeignKey("review_card.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=64), nullable=False),
        sa.Column("attribute", sa.String(length=64), nullable=False),
        # What the extractor proposed; a correction goes beside it, never over it.
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("span", sa.JSON(), nullable=True),
        sa.Column("state", FIELD_STATE, nullable=False),
        sa.Column("corrected_value", sa.JSON(), nullable=True),
        sa.Column("fact_id", sa.Uuid(), sa.ForeignKey("fact.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_review_field_profile_id_id"),
        sa.ForeignKeyConstraint(
            ["profile_id", "card_id"],
            ["review_card.profile_id", "review_card.id"],
            name="fk_review_field_card_profile",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "fact_id"],
            ["fact.profile_id", "fact.id"],
            name="fk_review_field_fact_profile",
        ),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table("review_field")
    op.drop_table("review_card")
