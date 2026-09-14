"""E04: medicines — the line, the supply, the taken dose, the interaction flag.

Four tables of profile data, every row tied to its profile the way the memory tables are
(0005): `(profile_id, fact_id)` points at `fact(profile_id, id)`, a supply's line at
`medication_line(profile_id, id)`, and so on, so the database itself refuses a supply on
another profile's line. A line rests on a `medication` fact and names the artefact or the
event it came from, with the same check the fact table has. A line is immutable with
supersession (`supersedes_id`, `superseded_at`); a supply, a taken dose and a flag are
moments.

Follows E02's ingestion revision (0008), which itself follows 0007.

Revision ID: 0009_medicines
Revises: 0008_ingestion
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_medicines"
down_revision = "0008_ingestion"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


CONFIDENCE_STATE = _enum("confidence_state", "extracted", "confirmed_by_person", "disputed")
SOURCE_KIND = _enum("medicine_source_kind", "retail", "clinic", "hospital")
LINE_STATUS = _enum("medication_line_status", "active", "held", "stopped")
CHANGE_KIND = _enum("medication_change_kind", "new_line", "dose_change")
SEVERITY = _enum("interaction_severity", "major", "moderate", "minor", "duplicate")


def _profile_id() -> sa.Column[sa.Uuid]:
    return sa.Column(
        "profile_id", sa.Uuid(), sa.ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )


def _tied(table: str, column: str, referred: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["profile_id", column],
        [f"{referred}.profile_id", f"{referred}.id"],
        name=f"fk_{table}_{column.removesuffix('_id')}_profile",
    )


_INDEXES = (
    ("ix_medication_line_profile_id", "medication_line", ["profile_id"]),
    ("ix_medication_line_generic", "medication_line", ["generic"]),
    ("ix_medication_supply_profile_id", "medication_supply", ["profile_id"]),
    ("ix_medication_supply_line_id", "medication_supply", ["line_id"]),
    ("ix_dose_taken_profile_id", "dose_taken", ["profile_id"]),
    ("ix_dose_taken_line_id", "dose_taken", ["line_id"]),
    ("ix_dose_taken_taken_at", "dose_taken", ["taken_at"]),
    ("ix_interaction_flag_profile_id", "interaction_flag", ["profile_id"]),
    ("ix_interaction_flag_line_id", "interaction_flag", ["line_id"]),
)


def upgrade() -> None:
    op.create_table(
        "medication_line",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("fact_id", sa.Uuid(), sa.ForeignKey("fact.id"), nullable=False),
        sa.Column("generic", sa.String(length=64), nullable=False),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("strength", sa.String(length=32), nullable=False),
        sa.Column("form", sa.String(length=32), nullable=False),
        sa.Column("registration_no", sa.String(length=32), nullable=True),
        sa.Column("drug_class", sa.String(length=48), nullable=False),
        sa.Column("high_risk", sa.Boolean(), nullable=False),
        # A structured code — amount, unit, frequency, anchors — never a sentence.
        sa.Column("dose", sa.JSON(), nullable=False),
        sa.Column("prescriber", sa.String(length=80), nullable=True),
        sa.Column("source_kind", SOURCE_KIND, nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("reorder_threshold_days", sa.Integer(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=True),
        sa.Column("source_event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_state", CONFIDENCE_STATE, nullable=False),
        sa.Column("status", LINE_STATUS, nullable=False),
        sa.Column("change_kind", CHANGE_KIND, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_id", sa.Uuid(), sa.ForeignKey("medication_line.id"), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("asserted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_medication_line_profile_id_id"),
        sa.CheckConstraint(
            "source_artifact_id IS NOT NULL OR source_event_id IS NOT NULL",
            name="ck_medication_line_has_source",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_medication_line_confidence"
        ),
        _tied("medication_line", "fact_id", "fact"),
        _tied("medication_line", "source_artifact_id", "artifact"),
        _tied("medication_line", "source_event_id", "event"),
        _tied("medication_line", "supersedes_id", "medication_line"),
    )
    op.create_table(
        "medication_supply",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("line_id", sa.Uuid(), sa.ForeignKey("medication_line.id"), nullable=False),
        sa.Column("fact_id", sa.Uuid(), sa.ForeignKey("fact.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("dispensed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=True),
        sa.Column("confirmed_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_medication_supply_profile_id_id"),
        sa.CheckConstraint("quantity > 0", name="ck_medication_supply_quantity"),
        _tied("medication_supply", "line_id", "medication_line"),
        _tied("medication_supply", "fact_id", "fact"),
        _tied("medication_supply", "artifact_id", "artifact"),
    )
    op.create_table(
        "dose_taken",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("line_id", sa.Uuid(), sa.ForeignKey("medication_line.id"), nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("anchor", sa.String(length=16), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_dose_taken_profile_id_id"),
        sa.CheckConstraint("amount > 0", name="ck_dose_taken_amount"),
        _tied("dose_taken", "line_id", "medication_line"),
        _tied("dose_taken", "event_id", "event"),
    )
    op.create_table(
        "interaction_flag",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("line_id", sa.Uuid(), sa.ForeignKey("medication_line.id"), nullable=False),
        sa.Column("other_line_id", sa.Uuid(), sa.ForeignKey("medication_line.id"), nullable=False),
        sa.Column("severity", SEVERITY, nullable=False),
        sa.Column("text_id", sa.String(length=64), nullable=False),
        sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_interaction_flag_profile_id_id"),
        _tied("interaction_flag", "line_id", "medication_line"),
        _tied("interaction_flag", "other_line_id", "medication_line"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    for table in ("interaction_flag", "dose_taken", "medication_supply", "medication_line"):
        op.drop_table(table)
