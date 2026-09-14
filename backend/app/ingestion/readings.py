"""A reading off a machine's screen, as the event and facts `POST /readings` writes (E02-08).

A photo of a blood pressure machine, a glucometer or a scale is read into a review card like
any page: the numbers, the unit, the kind of machine and the time on its screen, each with
how sure the extractor is. On the person's yes the card is not written field by field: the
kept fields become one READING event at the time on the screen — or when the photo was taken,
if that time was rejected — and the facts of the reading resting on it, in the same shape a
typed reading takes (`app.channels.api.profiles.add_reading`): `blood_pressure.reading` as
`{"systolic", "diastolic"}` in mmHg, and beside it a pulse, a sugar or a weight. Both numbers
of a blood pressure, or neither: half a blood pressure is not a reading.

The kind of machine and the time shape the event; they are not facts of their own.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import Any

from app.drafts import DecidedField
from app.errors import Refusal

SYSTOLIC = ("blood_pressure", "systolic")
DIASTOLIC = ("blood_pressure", "diastolic")
TAKEN_AT = ("reading", "taken_at")
DEVICE_KIND = ("device", "kind")

BLOOD_PRESSURE_RANGE = {SYSTOLIC: (40, 300), DIASTOLIC: (20, 200)}
"""The same bounds a typed reading is held to (`app.channels.api.schemas.ReadingIn`)."""


@dataclass(frozen=True, slots=True)
class Measure:
    """One number off a screen and the fact it becomes."""

    subject: str
    key: str
    unit: str
    low: float
    high: float


SINGLE_MEASURES: Mapping[tuple[str, str], Measure] = {
    ("heart_rate", "pulse"): Measure("heart_rate", "pulse", "/min", 20, 250),
    ("blood_sugar", "glucose"): Measure("blood_sugar", "glucose", "mmol/L", 0.5, 50),
    ("weight", "kg"): Measure("weight", "kg", "kg", 1, 400),
}
"""The numbers a screen shows beside a blood pressure, or on their own."""

LABELS: Mapping[str, str] = {
    "blood_pressure": "blood pressure",
    "blood_sugar": "blood sugar",
    "weight": "weight",
    "heart_rate": "pulse",
}
"""The event's label, from the first thing measured; `POST /readings` says "blood pressure"."""

READING = "reading"
"""The attribute every reading fact is written under, as the typed reading's is."""


class NotAWholeReading(Refusal):
    """A reading off a screen is whole: both numbers of a blood pressure, numbers in range,
    and a time on the screen that is a time, and not later than now."""


@dataclass(frozen=True, slots=True)
class ReadingFact:
    subject: str
    attribute: str
    value: dict[str, Any]
    unit: str
    field_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True, slots=True)
class Reading:
    """What a machine-screen card writes: the moment on the screen (None: the photo's), the
    event's label, and the facts. No facts means every number was rejected: nothing to write."""

    taken_at: datetime | None
    label: str
    facts: tuple[ReadingFact, ...]


def _number(field: DecidedField, low: float, high: float) -> int | float:
    value = field.value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise NotAWholeReading(f"{field.subject}.{field.attribute} is a number")
    if not low <= value <= high:
        raise NotAWholeReading(f"{field.subject}.{field.attribute} is between {low} and {high}")
    return int(value) if float(value).is_integer() else float(value)


def _moment(field: DecidedField, tz: tzinfo) -> datetime:
    if not isinstance(field.value, str):
        raise NotAWholeReading("the time on the screen is a date and a time")
    try:
        moment = datetime.fromisoformat(field.value)
    except ValueError:
        raise NotAWholeReading("the time on the screen is a date and a time") from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tz)
    return moment.astimezone(UTC)


def reading_from(fields: Sequence[DecidedField], *, tz: tzinfo, now: datetime) -> Reading:
    """The reading the kept fields make, or a refusal saying what is not whole about it.
    `tz` is the patient's wall clock, which a machine's screen shows its time on."""
    kept = {(f.subject, f.attribute): f for f in fields if f.decision != "rejected"}
    facts: list[ReadingFact] = []
    systolic, diastolic = kept.get(SYSTOLIC), kept.get(DIASTOLIC)
    if (systolic is None) != (diastolic is None):
        raise NotAWholeReading("a blood pressure is both numbers, or neither")
    if systolic is not None and diastolic is not None:
        facts.append(
            ReadingFact(
                subject="blood_pressure",
                attribute=READING,
                value={
                    "systolic": _number(systolic, *BLOOD_PRESSURE_RANGE[SYSTOLIC]),
                    "diastolic": _number(diastolic, *BLOOD_PRESSURE_RANGE[DIASTOLIC]),
                },
                unit="mmHg",
                field_ids=(systolic.field_id, diastolic.field_id),
            )
        )
    for code, measure in SINGLE_MEASURES.items():
        field = kept.get(code)
        if field is not None:
            facts.append(
                ReadingFact(
                    subject=measure.subject,
                    attribute=READING,
                    value={measure.key: _number(field, measure.low, measure.high)},
                    unit=measure.unit,
                    field_ids=(field.field_id,),
                )
            )
    shown = kept.get(TAKEN_AT)
    taken_at = None if shown is None else _moment(shown, tz)
    if taken_at is not None and taken_at > now:
        raise NotAWholeReading("the time on the screen is later than now")
    label = LABELS.get(facts[0].subject, READING) if facts else READING
    return Reading(taken_at=taken_at, label=label, facts=tuple(facts))
