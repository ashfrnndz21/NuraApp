"""The medicine tables: the line, what was dispensed, what was taken, what was flagged.

Every row is the profile's and is reached through `app.audit.access`. A line is immutable
with supersession, like the Fact it rests on: a dose change is a new line naming the old one,
and the old one stays with the moment it stopped being current. A supply and a taken dose are
moments and are never edited. A flag is what the licensed data said about two lines on the
day the second arrived.

No column here holds prose. `generic`, `brand`, `strength` and `form` are what the register
answered; `prescriber` is a name on the label, one short line; `dose` is a structured code
(`app.medicines.dose`), never a sentence.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.drugs.registry import Severity
from app.memory.models import LABEL_LENGTH, ConfidenceState


def _row_of_profile(table: str) -> UniqueConstraint:
    return UniqueConstraint("profile_id", "id", name=f"uq_{table}_profile_id_id")


def _tied_to_profile(table: str, column: str, referred: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["profile_id", column],
        [f"{referred}.profile_id", f"{referred}.id"],
        name=f"fk_{table}_{column.removesuffix('_id')}_profile",
    )


class LineStatus(StrEnum):
    ACTIVE = "active"
    HELD = "held"
    STOPPED = "stopped"


class ChangeKind(StrEnum):
    """Why this line was written: it is new, or a label showed a different amount from the
    line before it. A dose change is a question for the doctor, never advice."""

    NEW_LINE = "new_line"
    DOSE_CHANGE = "dose_change"


class SourceKind(StrEnum):
    """Where the medicine came from, which sets the lead time for reordering."""

    RETAIL = "retail"
    CLINIC = "clinic"
    HOSPITAL = "hospital"


LEAD_TIME_DAYS: dict[SourceKind, int] = {
    SourceKind.RETAIL: 3,
    SourceKind.CLINIC: 5,
    SourceKind.HOSPITAL: 7,
}
"""Days before the last tablet a reorder has to start, per source (module doc, section 2)."""

REORDER_THRESHOLD_DAYS = 7
"""The reorder card shows once fewer than this many days are left (module doc, section 3)."""


class MedicationLine(ProfileScoped, Base):
    """One medicine as the record holds it now: what, how strong, how much, from which label.

    `fact_id` is the `medication` fact this line is the typed view of — the fact carries the
    provenance, the confidence, the person's yes and the supersession; the line carries the
    same in columns a query can use. The one change a line takes is being superseded.
    """

    __tablename__ = "medication_line"
    __table_args__ = (
        _row_of_profile("medication_line"),
        _tied_to_profile("medication_line", "fact_id", "fact"),
        _tied_to_profile("medication_line", "source_artifact_id", "artifact"),
        _tied_to_profile("medication_line", "source_event_id", "event"),
        _tied_to_profile("medication_line", "supersedes_id", "medication_line"),
        CheckConstraint(
            "source_artifact_id IS NOT NULL OR source_event_id IS NOT NULL",
            name="ck_medication_line_has_source",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_medication_line_confidence"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fact.id"))
    generic: Mapped[str] = mapped_column(String(64), index=True)
    brand: Mapped[str | None] = mapped_column(String(80), default=None)
    strength: Mapped[str] = mapped_column(String(32))
    form: Mapped[str] = mapped_column(String(32))
    registration_no: Mapped[str | None] = mapped_column(String(32), default=None)
    drug_class: Mapped[str] = mapped_column(String(48))
    high_risk: Mapped[bool] = mapped_column(Boolean)
    dose: Mapped[dict[str, Any]] = mapped_column(JSON)
    prescriber: Mapped[str | None] = mapped_column(String(LABEL_LENGTH), default=None)
    source_kind: Mapped[SourceKind] = mapped_column(enum_column(SourceKind, "medicine_source_kind"))
    lead_time_days: Mapped[int] = mapped_column(Integer)
    reorder_threshold_days: Mapped[int] = mapped_column(Integer, default=REORDER_THRESHOLD_DAYS)
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifact.id"), default=None
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("event.id"), default=None)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_state: Mapped[ConfidenceState] = mapped_column(
        enum_column(ConfidenceState, "confidence_state")
    )
    status: Mapped[LineStatus] = mapped_column(enum_column(LineStatus, "medication_line_status"))
    change_kind: Mapped[ChangeKind] = mapped_column(
        enum_column(ChangeKind, "medication_change_kind")
    )
    started_at: Mapped[datetime] = mapped_column()
    stopped_at: Mapped[datetime | None] = mapped_column(default=None)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("medication_line.id"), default=None
    )
    superseded_at: Mapped[datetime | None] = mapped_column(default=None)
    confirmed_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    asserted_at: Mapped[datetime] = mapped_column(default=utcnow)


class Supply(ProfileScoped, Base):
    """What was dispensed for a line, when, from which label: the count starts here."""

    __tablename__ = "medication_supply"
    __table_args__ = (
        _row_of_profile("medication_supply"),
        _tied_to_profile("medication_supply", "line_id", "medication_line"),
        _tied_to_profile("medication_supply", "fact_id", "fact"),
        _tied_to_profile("medication_supply", "artifact_id", "artifact"),
        CheckConstraint("quantity > 0", name="ck_medication_supply_quantity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medication_line.id"), index=True)
    fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fact.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    dispensed_at: Mapped[datetime] = mapped_column()
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artifact.id"), default=None)
    confirmed_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    recorded_at: Mapped[datetime] = mapped_column(default=utcnow)


class DoseTaken(ProfileScoped, Base):
    """One tap: this line, taken now, by this person. Rests on a DOSE_TAKEN event.

    `late` is stored, not inferred at read time (#198): whether `taken_at` fell after the
    anchor's window had closed on his day, worked out once, when the tap is written
    (`app.medicines.windows.is_late`), from the anchor and the moment the tap itself carries
    — the reply's own time, never the backend's processing clock. A tap with no anchor is
    never late; there is no window to be late against. This says nothing about when the
    tablet left the blister, only when Nura was told: a late "Taken" is still a Taken."""

    __tablename__ = "dose_taken"
    __table_args__ = (
        _row_of_profile("dose_taken"),
        _tied_to_profile("dose_taken", "line_id", "medication_line"),
        _tied_to_profile("dose_taken", "event_id", "event"),
        CheckConstraint("amount > 0", name="ck_dose_taken_amount"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medication_line.id"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    anchor: Mapped[str | None] = mapped_column(String(16), default=None)
    amount: Mapped[float] = mapped_column(Float)
    taken_at: Mapped[datetime] = mapped_column(index=True)
    by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    late: Mapped[bool] = mapped_column(Boolean, default=False)


class InteractionFlag(ProfileScoped, Base):
    """What the licensed data said when a line was added: this line and that one, how much
    it matters, and which text. Rendered as a question for the doctor, never as advice."""

    __tablename__ = "interaction_flag"
    __table_args__ = (
        _row_of_profile("interaction_flag"),
        _tied_to_profile("interaction_flag", "line_id", "medication_line"),
        _tied_to_profile("interaction_flag", "other_line_id", "medication_line"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medication_line.id"), index=True)
    other_line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medication_line.id"))
    severity: Mapped[Severity] = mapped_column(enum_column(Severity, "interaction_severity"))
    text_id: Mapped[str] = mapped_column(String(64))
    flagged_at: Mapped[datetime] = mapped_column(default=utcnow)


frozen(MedicationLine, except_for=frozenset({"superseded_at"}))
frozen(Supply)
frozen(DoseTaken)
frozen(InteractionFlag)
