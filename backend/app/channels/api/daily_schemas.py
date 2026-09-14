"""The shapes on the wire for the lab trend (E09-01), the routine (E10-01) and the calendar
connector (E18-02). Kept apart from `schemas` so the three stories read in one place."""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.consent.models import ConsentChannel
from app.consent.service import RecordConsent
from app.db import as_utc
from app.drafts import ConfirmSubject
from app.ingestion.connectors.calendar import MAX_ICS_BYTES
from app.ingestion.connectors.models import AppointmentProposal, Connector, ConnectorSource
from app.memory.models import Appointment
from app.reasoning.ranges import Range
from app.reasoning.trends import Point, Trend
from app.routines.service import RoutineView

# --- the lab trend --------------------------------------------------------------------------


class RangeOut(BaseModel):
    """The range a result was placed against, in the analyte's own unit, and where it came
    from: the lab's printed range (`lab:<code>`) or a guideline table by source id."""

    lower: float | None
    upper: float | None
    unit: str
    source: str
    source_id: str
    lab: str | None
    min_age: int | None
    max_age: int | None
    sex: str | None

    @classmethod
    def of(cls, found: Range) -> RangeOut:
        return cls(
            lower=found.lower,
            upper=found.upper,
            unit=found.unit,
            source=found.source.value,
            source_id=found.source_id,
            lab=found.lab,
            min_age=found.min_age,
            max_age=found.max_age,
            sex=None if found.sex is None else found.sex.value,
        )


class TrendPointOut(BaseModel):
    """One confirmed result with its provenance and where it sits against its range."""

    fact_id: uuid.UUID
    artifact_id: uuid.UUID | None
    event_id: uuid.UUID | None
    confirmed_by_person_id: uuid.UUID | None
    value: float
    unit: str | None
    on: date
    lab: str | None
    band: str
    range: RangeOut | None
    no_range_because: str | None

    @classmethod
    def of(cls, point: Point) -> TrendPointOut:
        return cls(
            fact_id=point.fact_id,
            artifact_id=point.artifact_id,
            event_id=point.event_id,
            confirmed_by_person_id=point.confirmed_by_person_id,
            value=point.value,
            unit=point.unit,
            on=point.on,
            lab=point.lab,
            band=point.band.value,
            range=None if point.range is None else RangeOut.of(point.range),
            no_range_because=None
            if point.no_range_because is None
            else point.no_range_because.value,
        )


class TrendOut(BaseModel):
    """A trend for one analyte: the results oldest first, the direction over the last three,
    the lines he reads (ending on the boundary line), and the State and card it was
    rendered as. `birth_decade` is the decade his age band was read from, never the year."""

    analyte: str
    subject: str
    attribute: str
    unit: str
    language: str
    points: list[TrendPointOut]
    direction: str
    direction_since: date | None
    lines: list[str]
    boundary: str
    doctor: str | None
    birth_decade: int | None
    sex: str | None
    card_id: uuid.UUID
    state_id: uuid.UUID

    @classmethod
    def of(cls, trend: Trend) -> TrendOut:
        return cls(
            analyte=trend.analyte.id,
            subject=trend.analyte.subject,
            attribute=trend.analyte.attribute,
            unit=trend.analyte.unit,
            language=trend.language,
            points=[TrendPointOut.of(point) for point in trend.points],
            direction=trend.direction.value,
            direction_since=trend.direction_since,
            lines=list(trend.lines),
            boundary=trend.boundary,
            doctor=trend.doctor,
            birth_decade=trend.birth_decade,
            sex=None if trend.sex is None else trend.sex.value,
            card_id=trend.card.id,
            state_id=trend.card.state_id,
        )


# --- the routine ----------------------------------------------------------------------------


class RoutineDayIn(BaseModel):
    """A day: the five anchors at `HH:MM` on his clock, the readings he is prompted for at
    which anchor, the anchors after which he walks, and when his Today page comes."""

    anchors: dict[str, str]
    reading_prompts: list[tuple[str, str]] = Field(default_factory=list, max_length=15)
    walks: list[str] = Field(default_factory=list, max_length=5)
    morning_card_at: str = Field(min_length=5, max_length=5)


class RoutineIn(RoutineDayIn):
    """Set the day with the yes minted for exactly it (subject `routine`)."""

    confirmation_id: uuid.UUID


class RoutineConfirmIn(RoutineDayIn):
    """A yes to setting the day as shown. The draft is recomputed — the times checked, the
    routine it replaces named — so the yes binds to exactly what `PUT /routine` writes."""

    subject: Literal[ConfirmSubject.ROUTINE]


class RoutineOut(BaseModel):
    """The day for one reader. The patient's `lines` are one per moment of his day, in his
    words; the caregiver's `table` is every moment with its time, medicines and prompts.
    `set` is False while the day is the default nobody has set yet."""

    routine_id: uuid.UUID | None
    set: bool
    set_by_person_id: uuid.UUID | None
    set_at: datetime | None
    supersedes_id: uuid.UUID | None
    anchors: dict[str, str]
    reading_prompts: list[list[str]] | None
    walks: list[str]
    morning_card_at: str
    persona: str
    language: str
    lines: list[str]
    table: list[dict[str, Any]]
    when_needed: list[dict[str, Any]]
    withheld: list[str]

    @classmethod
    def of(cls, view: RoutineView) -> RoutineOut:
        row = view.the.routine
        day = view.the.day
        withheld = sorted(scope.value for scope in view.the.withheld)
        return cls(
            routine_id=None if row is None else row.id,
            set=row is not None,
            set_by_person_id=None if row is None else row.set_by_person_id,
            set_at=None if row is None else as_utc(row.set_at),
            supersedes_id=None if row is None else row.supersedes_id,
            anchors=day.as_strings(),
            reading_prompts=None if withheld else [list(p) for p in day.reading_prompts],
            walks=list(day.walks),
            morning_card_at=day.morning_card_at.strftime("%H:%M"),
            persona=view.persona.value,
            language=view.language,
            lines=list(view.lines),
            table=list(view.table),
            when_needed=list(view.when_needed),
            withheld=withheld,
        )


# --- the calendar connector ---------------------------------------------------------------


class ConnectorConsentIn(BaseModel):
    """The owner agreeing to the calendar connector in the same step: which words, in which
    language, captured how. Stated, never inferred."""

    wording_version: str = Field(min_length=1, max_length=32, pattern=r"^[0-9A-Za-z._-]+$")
    language: str = Field(min_length=2, max_length=16)
    captured_via: ConsentChannel = ConsentChannel.APP

    def as_record(self) -> RecordConsent:
        return RecordConsent(
            text_version=self.wording_version,
            language=self.language,
            captured_via=self.captured_via,
        )


class ConnectIn(BaseModel):
    source: Literal[ConnectorSource.ICS_FILE] = ConnectorSource.ICS_FILE
    consent: ConnectorConsentIn | None = None


class ConnectorOut(BaseModel):
    connector_id: uuid.UUID
    kind: str
    source: str
    consent_id: uuid.UUID
    connected_by_person_id: uuid.UUID
    connected_at: datetime

    @classmethod
    def of(cls, row: Connector) -> ConnectorOut:
        return cls(
            connector_id=row.id,
            kind=row.kind.value,
            source=row.source.value,
            consent_id=row.consent_id,
            connected_by_person_id=row.connected_by_person_id,
            connected_at=as_utc(row.connected_at),
        )


class ScanIn(BaseModel):
    """An iCalendar file, base64. Read in memory for this request and not kept."""

    ics: str = Field(min_length=1, max_length=(MAX_ICS_BYTES * 4) // 3 + 8)

    @field_validator("ics")
    @classmethod
    def _base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as not_base64:
            raise ValueError("ics is the file's bytes in base64") from not_base64
        return value

    @property
    def data(self) -> bytes:
        return base64.b64decode(self.ics)


class ProposalOut(BaseModel):
    """A calendar event that looked like a visit: never a visit until a person says yes.
    `lines` is what he reads about it, in his language; empty once dismissed."""

    proposal_id: uuid.UUID
    connector_id: uuid.UUID
    title: str
    location: str | None
    starts_at: datetime
    all_day: bool
    matched_by: str
    keyword: str | None
    provider_id: uuid.UUID | None
    provider_name: str
    provider_kind: str
    status: str
    decided_at: datetime | None
    decided_by_person_id: uuid.UUID | None
    appointment_id: uuid.UUID | None
    lines: list[str]

    @classmethod
    def of(cls, row: AppointmentProposal, lines: list[str]) -> ProposalOut:
        return cls(
            proposal_id=row.id,
            connector_id=row.connector_id,
            title=row.title,
            location=row.location,
            starts_at=as_utc(row.starts_at),
            all_day=row.all_day,
            matched_by=row.matched_by.value,
            keyword=row.keyword,
            provider_id=row.provider_id,
            provider_name=row.provider_name,
            provider_kind=row.provider_kind.value,
            status=row.status.value,
            decided_at=None if row.decided_at is None else as_utc(row.decided_at),
            decided_by_person_id=row.decided_by_person_id,
            appointment_id=row.appointment_id,
            lines=lines,
        )


class ScanOut(BaseModel):
    """What one scan did. `dropped` counts events that were not visits; nothing of them was
    kept."""

    read: int
    proposed: list[ProposalOut]
    dropped: int
    already: int


class ProposalConfirmIn(BaseModel):
    """A yes to putting a proposed visit on the spine, as shown. The draft is recomputed from
    the proposal — provider, time, purpose — so the yes cannot name anything else."""

    subject: Literal[ConfirmSubject.PROPOSAL]
    proposal_id: uuid.UUID


class AcceptIn(BaseModel):
    confirmation_id: uuid.UUID


class AcceptedOut(BaseModel):
    proposal: ProposalOut
    appointment_id: uuid.UUID
    provider_id: uuid.UUID
    scheduled_at: datetime
    appointment_status: str

    @classmethod
    def of(cls, proposal: ProposalOut, appointment: Appointment) -> AcceptedOut:
        return cls(
            proposal=proposal,
            appointment_id=appointment.id,
            provider_id=appointment.provider_id,
            scheduled_at=as_utc(appointment.scheduled_at),
            appointment_status=appointment.status.value,
        )
