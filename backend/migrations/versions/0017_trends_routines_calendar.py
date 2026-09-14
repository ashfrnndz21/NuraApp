"""E09-01, E10-01, E18-02: the lab trend's card, the day's routine, the calendar connector.

Four tables of profile data. `trend_card` is one lab trend as it was shown: the analyte, the
facts it drew, the direction, the lines, the State it was rendered from and the boundary
line it carried (`RenderedFromState`, tied to `state_snapshot(profile_id, id)`). `routine` is
one day as it was set — anchors, prompts, walks, the morning card — superseded, never edited.
`connector` is one read-only calendar on the profile, resting on its consent. And
`appointment_proposal` is one calendar event that looked like a visit, tied to its connector,
to the provider it named and to the appointment a person's yes booked from it.

`consent_purpose` gains `calendar` and `confirm_subject` gains `routine` and
`appointment_proposal`; both are non-native enums with no database constraint, so there is
no column change for them.

Follows E19's revision (0011_whatsapp), main's head when these stories were merged back; the operator
repoints `down_revision` if another story lands first.

Revision ID: 0017_trends_routines_calendar
Revises: 0011_whatsapp
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_trends_routines_calendar"
down_revision = "0011_whatsapp"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


DIRECTION = _enum("trend_direction", "up", "down", "steady", "mixed", "one", "none")
CONNECTOR_KIND = _enum("connector_kind", "calendar")
CONNECTOR_SOURCE = _enum("connector_source", "ics_file", "fixture")
MATCHED_BY = _enum("proposal_matched_by", "provider", "keyword")
PROVIDER_KIND = _enum("provider_kind", "doctor", "clinic", "hospital", "pharmacy", "lab", "other")
PROPOSAL_STATUS = _enum("proposal_status", "proposed", "accepted", "dismissed")


def _profile_id() -> sa.Column[sa.Uuid]:
    return sa.Column(
        "profile_id", sa.Uuid(), sa.ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )


def _row_of_profile(table: str) -> sa.UniqueConstraint:
    return sa.UniqueConstraint("profile_id", "id", name=f"uq_{table}_profile_id_id")


def _tied(table: str, column: str, referred: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["profile_id", column],
        [f"{referred}.profile_id", f"{referred}.id"],
        name=f"fk_{table}_{column.removesuffix('_id')}_profile",
    )


_INDEXES = (
    ("ix_trend_card_profile_id", "trend_card", ["profile_id"]),
    ("ix_trend_card_state_id", "trend_card", ["state_id"]),
    ("ix_routine_profile_id", "routine", ["profile_id"]),
    ("ix_connector_profile_id", "connector", ["profile_id"]),
    ("ix_appointment_proposal_profile_id", "appointment_proposal", ["profile_id"]),
    ("ix_appointment_proposal_connector_id", "appointment_proposal", ["connector_id"]),
    ("ix_appointment_proposal_starts_at", "appointment_proposal", ["starts_at"]),
)


def upgrade() -> None:
    op.create_table(
        "trend_card",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=False),
        sa.Column("boundary", sa.Text(), nullable=True),
        sa.Column("analyte", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("fact_ids", sa.JSON(), nullable=False),
        sa.Column("direction", DIRECTION, nullable=False),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column(
            "rendered_for_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False
        ),
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=False),
        _row_of_profile("trend_card"),
        _tied("trend_card", "state_id", "state_snapshot"),
    )
    op.create_table(
        "routine",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("anchors", sa.JSON(), nullable=False),
        sa.Column("reading_prompts", sa.JSON(), nullable=False),
        sa.Column("walks", sa.JSON(), nullable=False),
        sa.Column("morning_card_at", sa.String(length=5), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), sa.ForeignKey("routine.id"), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("set_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        _row_of_profile("routine"),
        _tied("routine", "supersedes_id", "routine"),
    )
    op.create_table(
        "connector",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("kind", CONNECTOR_KIND, nullable=False),
        sa.Column("source", CONNECTOR_SOURCE, nullable=False),
        sa.Column("consent_id", sa.Uuid(), sa.ForeignKey("consent.id"), nullable=False),
        sa.Column(
            "connected_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False
        ),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        _row_of_profile("connector"),
    )
    op.create_table(
        "appointment_proposal",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("connector_id", sa.Uuid(), sa.ForeignKey("connector.id"), nullable=False),
        sa.Column("event_digest", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("location", sa.String(length=80), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("matched_by", MATCHED_BY, nullable=False),
        sa.Column("keyword", sa.String(length=32), nullable=True),
        sa.Column("provider_id", sa.Uuid(), sa.ForeignKey("provider.id"), nullable=True),
        sa.Column("provider_name", sa.String(length=120), nullable=False),
        sa.Column("provider_kind", PROVIDER_KIND, nullable=False),
        sa.Column("status", PROPOSAL_STATUS, nullable=False),
        sa.Column("found_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=True),
        _row_of_profile("appointment_proposal"),
        _tied("appointment_proposal", "connector_id", "connector"),
        _tied("appointment_proposal", "provider_id", "provider"),
        _tied("appointment_proposal", "appointment_id", "appointment"),
        sa.UniqueConstraint("connector_id", "event_digest", name="uq_appointment_proposal_event"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table("appointment_proposal")
    op.drop_table("connector")
    op.drop_table("routine")
    op.drop_table("trend_card")
