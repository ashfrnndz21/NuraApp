"""E00-03: the memory stores and the spine.

Artifact and Event (episodic), Fact (semantic), Episode (working), Provider and Appointment
(the spine). Every table carries `profile_id`. The fact table refuses a row that names no
artefact and no event, and one whose confidence is outside nought to one.

This revision branches from 0002 beside the consent revision built in parallel; the two
heads are joined by a merge revision, not by making one depend on the other.

Revision ID: 0003_memory
Revises: 0002_audit
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_memory"
down_revision = "0002_audit"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


REGION = _enum("region", "SG", "MY")
ARTIFACT_KIND = _enum("artifact_kind", "photo", "pdf", "voice", "message", "reading", "screenshot")
SOURCE_CHANNEL = _enum("source_channel", "app", "whatsapp", "connector", "device", "clinic")
EVENT_KIND = _enum("event_kind", "reading", "visit", "message", "dose_taken", "symptom", "discharge")
CONFIDENCE_STATE = _enum("confidence_state", "extracted", "confirmed_by_person", "disputed")
EPISODE_KIND = _enum(
    "episode_kind", "illness", "admission", "recovery", "travel", "fasting", "other"
)
PROVIDER_KIND = _enum("provider_kind", "doctor", "clinic", "hospital", "pharmacy", "lab", "other")
APPOINTMENT_STATUS = _enum(
    "appointment_status", "planned", "confirmed", "attended", "not_attended", "cancelled"
)


_INDEXES = {
    "appointment": (
        "ix_appointment_scheduled_at",
        "ix_appointment_provider_id",
        "ix_appointment_profile_id",
    ),
    "provider": ("ix_provider_profile_id",),
    "fact": ("ix_fact_subject", "ix_fact_profile_id"),
    "event": ("ix_event_occurred_at", "ix_event_profile_id"),
    "episode": ("ix_episode_opened_at", "ix_episode_profile_id"),
    "artifact": ("ix_artifact_captured_at", "ix_artifact_profile_id"),
}


def _profile_id() -> sa.Column:
    return sa.Column(
        "profile_id", sa.Uuid(), sa.ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "artifact",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("kind", ARTIFACT_KIND, nullable=False),
        # A reference into the object store of the profile's region. Never the bytes.
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_channel", SOURCE_CHANNEL, nullable=False),
        sa.Column("region", REGION, nullable=False),
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifact_profile_id", "artifact", ["profile_id"])
    op.create_index("ix_artifact_captured_at", "artifact", ["captured_at"])

    op.create_table(
        "episode",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("kind", EPISODE_KIND, nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_episode_profile_id", "episode", ["profile_id"])
    op.create_index("ix_episode_opened_at", "episode", ["opened_at"])

    op.create_table(
        "event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("kind", EVENT_KIND, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        # A name for the moment, one short line. What was said is in the artefact.
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=True),
        sa.Column("episode_id", sa.Uuid(), sa.ForeignKey("episode.id"), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_event_profile_id", "event", ["profile_id"])
    op.create_index("ix_event_occurred_at", "event", ["occurred_at"])

    op.create_table(
        "fact",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("subject", sa.String(length=64), nullable=False),
        sa.Column("attribute", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_state", CONFIDENCE_STATE, nullable=False),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=True),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=True),
        sa.Column("episode_id", sa.Uuid(), sa.ForeignKey("episode.id"), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("asserted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), sa.ForeignKey("fact.id"), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        # Nothing infers without provenance: the table refuses a fact from nowhere.
        sa.CheckConstraint(
            "artifact_id IS NOT NULL OR event_id IS NOT NULL", name="ck_fact_has_provenance"
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_fact_confidence"),
    )
    op.create_index("ix_fact_profile_id", "fact", ["profile_id"])
    op.create_index("ix_fact_subject", "fact", ["subject"])

    op.create_table(
        "provider",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", PROVIDER_KIND, nullable=False),
        sa.Column("phone_e164", sa.String(length=20), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("region", REGION, nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_provider_profile_id", "provider", ["profile_id"])

    op.create_table(
        "appointment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("provider_id", sa.Uuid(), sa.ForeignKey("provider.id"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", APPOINTMENT_STATUS, nullable=False),
        sa.Column("purpose", sa.String(length=80), nullable=False),
        sa.Column("episode_id", sa.Uuid(), sa.ForeignKey("episode.id"), nullable=True),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_appointment_profile_id", "appointment", ["profile_id"])
    op.create_index("ix_appointment_provider_id", "appointment", ["provider_id"])
    op.create_index("ix_appointment_scheduled_at", "appointment", ["scheduled_at"])


def downgrade() -> None:
    for table in ("appointment", "provider", "fact", "event", "episode", "artifact"):
        for index in _INDEXES[table]:
            op.drop_index(index, table_name=table)
        op.drop_table(table)

