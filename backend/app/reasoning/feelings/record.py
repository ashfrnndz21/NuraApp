"""What the cloud, a tap's inference and the nudges read from the record, in one place.

One reader, `read_situation`, under the caller's key context, each part under its own scope
and only where the key covers it: State (the record's scope) for the open episodes and the
discharge; the medicine lines (medicines) with each one's licensed monograph rule ids from the
registry; his blood pressure numbers (readings); the visits on the spine (visits); and his
own taps on the cloud (the record's). What the key does not cover is left out, never guessed.

Nothing here judges anything. `rising` is arithmetic — the last three numbers, each higher
than the one before — and says a direction, never whether a number is high.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import as_utc, utcnow
from app.drugs.registry import DrugRegistry, UnknownDrug
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.models import LineStatus, MedicationLine
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    EpisodeKind,
    Event,
    EventKind,
    Provider,
)
from app.memory.semantic import current_facts
from app.memory.spine import upcoming_appointments
from app.reasoning.feelings.models import FeelingTap
from app.reasoning.feelings.words import (
    PAST_WORDS_WINDOW,
    TIMELINE_WINDOW,
    TREND_READINGS,
    TREND_WINDOW,
)
from app.regions import REGION_TZ
from app.safety.red_flags import Feeling
from app.state.models import Dimension
from app.state.service import StateView, current_state

BLOOD_PRESSURE = "blood_pressure"
READING = "reading"


@dataclass(frozen=True, slots=True)
class Line:
    """An active medicine line as the cloud reads it: which, since when, and what its licensed
    monograph says to watch out for, by rule id."""

    line_id: uuid.UUID
    generic: str
    plain_name_id: str | None
    started_at: datetime
    watch_out_ids: tuple[str, ...]
    prescriber: str | None


@dataclass(frozen=True, slots=True)
class Reading:
    fact_id: uuid.UUID
    taken_at: datetime
    systolic: int


@dataclass(frozen=True, slots=True)
class Said:
    """One of his own taps: the word, when, and the tap it was."""

    word: Feeling
    at: datetime
    tap_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class OpenEpisode:
    id: str
    kind: EpisodeKind
    since: datetime


@dataclass(frozen=True, slots=True)
class Visit:
    appointment_id: uuid.UUID
    at: datetime
    doctor: str | None


@dataclass(frozen=True, slots=True)
class Situation:
    """The record as the feelings read it, at one moment, under one key."""

    now: datetime
    state: StateView | None
    lines: tuple[Line, ...]
    readings: tuple[Reading, ...]
    episodes: tuple[OpenEpisode, ...]
    discharged_at: datetime | None
    said: tuple[Said, ...]
    last_tap_at: datetime | None
    next_visit: Visit | None
    recent_visit: tuple[uuid.UUID, datetime] | None
    """A visit this week, by the event (or the attended appointment) that says so."""


def rising(readings: Sequence[Reading], now: datetime) -> tuple[Reading, ...]:
    """The last `TREND_READINGS` blood pressure numbers inside `TREND_WINDOW`, if each is
    higher than the one before it; otherwise nothing. A direction, not a threshold."""
    recent = sorted(
        (r for r in readings if now - TREND_WINDOW <= as_utc(r.taken_at) <= now),
        key=lambda r: as_utc(r.taken_at),
    )
    last = recent[-TREND_READINGS:]
    if len(last) < TREND_READINGS:
        return ()
    if all(later.systolic > earlier.systolic for earlier, later in pairwise(last)):
        return tuple(last)
    return ()


def _moment(value: object) -> datetime | None:
    return as_utc(datetime.fromisoformat(value)) if isinstance(value, str) else None


async def _lines(
    session: AsyncSession, *, context: KeyContext, registry: DrugRegistry
) -> tuple[Line, ...]:
    found = await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(MedicationLine.superseded_at.is_(None), MedicationLine.status == LineStatus.ACTIVE),
    )
    lines: list[Line] = []
    watch: tuple[str, ...]
    plain: str | None
    for line in sorted(found, key=lambda one: (as_utc(one.started_at), one.generic)):
        try:
            monograph = registry.monograph(line.generic)
        except UnknownDrug:
            watch, plain = (), None
        else:
            watch, plain = monograph.watch_out_ids, monograph.plain_name_id
        lines.append(
            Line(
                line_id=line.id,
                generic=line.generic,
                plain_name_id=plain,
                started_at=as_utc(line.started_at),
                watch_out_ids=tuple(watch),
                prescriber=line.prescriber,
            )
        )
    return tuple(lines)


async def _readings(session: AsyncSession, *, context: KeyContext) -> tuple[Reading, ...]:
    facts = await current_facts(session, context=context, subject=BLOOD_PRESSURE, attribute=READING)
    found: list[Reading] = []
    for fact in facts:
        value = fact.value if isinstance(fact.value, dict) else {}
        systolic = value.get("systolic")
        if isinstance(systolic, int | float):
            found.append(Reading(fact.id, as_utc(fact.valid_from), int(systolic)))
    return tuple(found)


async def _said(session: AsyncSession, *, context: KeyContext, now: datetime) -> list[FeelingTap]:
    return list(
        await audited_read(
            session,
            FeelingTap,
            context,
            Scope.RECORDS,
            where=(FeelingTap.tapped_at > now - PAST_WORDS_WINDOW,),
            order_by=(FeelingTap.tapped_at.desc(),),
        )
    )


async def next_visit(session: AsyncSession, *, context: KeyContext) -> Visit | None:
    """The next visit on the spine and the doctor it is with, when the key covers visits."""
    if not context.allows(Scope.VISITS):
        return None
    coming = await upcoming_appointments(session, context=context, limit=1)
    if not coming:
        return None
    visit = coming[0]
    providers = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.id == visit.provider_id,)
    )
    return Visit(visit.id, as_utc(visit.scheduled_at), providers[0].name if providers else None)


async def _recent_visit(
    session: AsyncSession, *, context: KeyContext, now: datetime
) -> tuple[uuid.UUID, datetime] | None:
    events = await audited_read(
        session,
        Event,
        context,
        Scope.RECORDS,
        where=(
            Event.kind == EventKind.VISIT,
            Event.occurred_at > now - TIMELINE_WINDOW,
            Event.occurred_at <= now,
        ),
    )
    found = [(event.id, as_utc(event.occurred_at)) for event in events]
    if context.allows(Scope.VISITS):
        attended = await audited_read(
            session,
            Appointment,
            context,
            Scope.VISITS,
            where=(
                Appointment.status == AppointmentStatus.ATTENDED,
                Appointment.scheduled_at > now - TIMELINE_WINDOW,
                Appointment.scheduled_at <= now,
            ),
        )
        found.extend((visit.id, as_utc(visit.scheduled_at)) for visit in attended)
    return max(found, key=lambda one: one[1], default=None)


async def read_situation(
    session: AsyncSession, *, context: KeyContext, registry: DrugRegistry
) -> Situation:
    """Everything the feelings read, under this key, at this moment."""
    now = utcnow()
    state = await current_state(session, context=context)
    clinical = state.dimension(Dimension.CLINICAL) or {}
    episodes = tuple(
        OpenEpisode(
            str(e["id"]), EpisodeKind(e["kind"]), as_utc(datetime.fromisoformat(e["since"]))
        )
        for e in clinical.get("open_episodes", [])
        if isinstance(e, dict) and e.get("since")
    )
    taps = await _said(session, context=context, now=now)
    return Situation(
        now=now,
        state=state,
        lines=(
            await _lines(session, context=context, registry=registry)
            if context.allows(Scope.MEDICINES)
            else ()
        ),
        readings=(
            await _readings(session, context=context) if context.allows(Scope.READINGS) else ()
        ),
        episodes=episodes,
        discharged_at=_moment(clinical.get("discharged_at")),
        said=tuple(Said(tap.word, as_utc(tap.tapped_at), tap.id) for tap in taps),
        last_tap_at=as_utc(taps[0].tapped_at) if taps else None,
        next_visit=await next_visit(session, context=context),
        recent_visit=await _recent_visit(session, context=context, now=now),
    )


def local_date(moment: datetime, context: KeyContext) -> date:
    """The day on his wall a moment falls on."""
    return as_utc(moment).astimezone(REGION_TZ[context.region]).date()
