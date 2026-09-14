"""E02-02, E02-03, E02-06, E02-08: capture extras.

`review_card` gains `asked_as` — the kind of paper a page was offered as, by the person or by
the route (a machine's screen) — and `source`, where an imported PDF came from (portal, email,
share). Both are checked strings with no database constraint, like `document_kind`, whose new
values (handwritten_prescription, insurance_letter, device_screen, not_health) need no schema
change either. `review_field` gains `corrected_by_person_id`: who typed a field Nura could not
read, or corrected one, which may be someone other than the person who confirms the card.

`event_note` is new: a voice note or a scribble on one event, tied to the event and to its
artefact on the same profile the way provenance is tied (0005). The words heard in a voice
note are in the object store under `transcript_key`; no column holds them.

Follows E19's WhatsApp revision (0011_whatsapp), main's head when this story was built; the operator
repoints `down_revision` if another story lands first.

Revision ID: 0018_capture_extras
Revises: 0011_whatsapp
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_capture_extras"
down_revision = "0011_whatsapp"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


DOCUMENT_KIND = _enum(
    "document_kind",
    "lab_report",
    "medicine_label",
    "discharge_letter",
    "clinic_slip",
    "handwritten_prescription",
    "insurance_letter",
    "device_screen",
    "not_health",
    "unknown",
)
DOCUMENT_SOURCE = _enum("document_source", "portal", "email", "share")
NOTE_KIND = _enum("event_note_kind", "voice", "scribble")

_INDEXES = (
    ("ix_event_note_profile_id", "event_note", ["profile_id"]),
    ("ix_event_note_event_id", "event_note", ["event_id"]),
    ("ix_event_note_written_at", "event_note", ["written_at"]),
)


def upgrade() -> None:
    with op.batch_alter_table("review_card") as card:
        card.add_column(sa.Column("asked_as", DOCUMENT_KIND, nullable=True))
        card.add_column(sa.Column("source", DOCUMENT_SOURCE, nullable=True))
    with op.batch_alter_table("review_field") as field:
        field.add_column(sa.Column("corrected_by_person_id", sa.Uuid(), nullable=True))
        field.create_foreign_key(
            "fk_review_field_corrected_by_person", "person", ["corrected_by_person_id"], ["id"]
        )
    op.create_table(
        "event_note",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=False),
        sa.Column("kind", NOTE_KIND, nullable=False),
        sa.Column("private", sa.Boolean(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column("transcript_key", sa.String(length=512), nullable=True),
        sa.Column("transcript_sha256", sa.String(length=64), nullable=True),
        sa.Column("transcript_confidence", sa.Float(), nullable=True),
        sa.Column("transcript_language", sa.String(length=16), nullable=True),
        sa.Column(
            "written_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False
        ),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_event_note_profile_id_id"),
        sa.ForeignKeyConstraint(
            ["profile_id", "event_id"],
            ["event.profile_id", "event.id"],
            name="fk_event_note_event_profile",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "artifact_id"],
            ["artifact.profile_id", "artifact.id"],
            name="fk_event_note_artifact_profile",
        ),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table("event_note")
    with op.batch_alter_table("review_field") as field:
        field.drop_constraint("fk_review_field_corrected_by_person", type_="foreignkey")
        field.drop_column("corrected_by_person_id")
    with op.batch_alter_table("review_card") as card:
        card.drop_column("source")
        card.drop_column("asked_as")
