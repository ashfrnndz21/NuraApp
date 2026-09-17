"""Series readers for what the record already holds (RE-03, `docs/recommendation-engine.md`
§2.2): doses, readings, symptoms, cloud taps, appointments and engagement, as typed, dated
points with the ids they rest on. No judgement, no arithmetic across days — that is the
pattern detector's job (§2.3), not this module's.

One reader per input family, each reading under the caller's key, one scope at a time, the
way `app.reasoning.feelings.record.read_situation` does. What the key does not hold is left
out of the series and named in `SeriesSet.withheld` — never silently empty and never guessed.

`answered_days` is the correctness rule §2.7 sets: a day is "answered" when he said
something on it, even a "no". Every point already written is itself an answer, and
`answered_days` is simply the days a point falls on. A day nobody wrote anything down for is
not in the set, and a rule must not treat it as either side of a comparison.

RE-10 adds the six lifestyle and food readers: steps, sleep and water (`app.lifestyle.
metrics`) and the four meal slots (`app.lifestyle.food`). Heart rate needs no reader of its
own — `app.lifestyle.metrics.log_metric` writes it in the exact shape a typed blood-pressure
machine's pulse already takes (subject `heart_rate`, attribute `reading`), so the existing
`PULSE` reading series already reads it. A skip ("no water today", "did not walk") is a real
answer under §2.7, never a blank: a skipped cumulative metric is a point of value `0.0`
(a logged zero is exactly what "none" means for steps and water), and a skipped meal is a
point of value `False` — both land in `answered_days` the same as a logged one.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import as_utc, utcnow
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.lifestyle.food import Meal, food_log
from app.lifestyle.metrics import LogStatus, MetricKind, metric_series
from app.medicines.models import DoseTaken
from app.memory.episodic import fact_cites_only_what_is_held_here
from app.memory.models import Appointment, ConfidenceState, Event, EventKind, Fact
from app.reasoning.feelings.models import FeelingTap
from app.reasoning.feelings.record import local_date
from app.safety.not_feeling_well import REPORTED, SYMPTOM

WINDOW_DAYS = 28
"""The default window a series reads: the same default a `PatternRule` reads over (§2.3)."""

SYMPTOM_SCOPE = scope_for_subject(SYMPTOM)
"""RECORDS: the scope a symptom fact is held under, decided in `app.keys.scopes`."""


class SeriesKind(StrEnum):
    """The families this module reads."""

    BP_SYSTOLIC = "bp_systolic"
    BP_DIASTOLIC = "bp_diastolic"
    SUGAR = "sugar"
    WEIGHT = "weight"
    PULSE = "pulse"
    STEPS = "steps"
    SLEEP_MINUTES = "sleep_minutes"
    WATER_CUPS = "water_cups"
    MEAL_BREAKFAST = "meal_breakfast"
    MEAL_LUNCH = "meal_lunch"
    MEAL_DINNER = "meal_dinner"
    MEAL_SNACK = "meal_snack"
    DOSE_ON_TIME = "dose_on_time"
    SYMPTOM = "symptom"
    FEELING = "feeling"
    APPOINTMENT = "appointment"
    ENGAGEMENT = "engagement"


@dataclass(frozen=True, slots=True)
class Evidence:
    """One id a point rests on, and the scope it was read under. `kind` is the broker's own
    vocabulary (§2.4): fact, event, tap or appointment, here — never a row, never free text."""

    kind: str
    id: uuid.UUID
    scope: Scope


@dataclass(frozen=True, slots=True)
class Point:
    """One dated value. `day` is his local day (`REGION_TZ`), the unit every rule pairs on;
    `at` is the UTC moment it rests on. `ids` names every fact, event or tap id the value
    comes from — plural, because a blood pressure point rests on one fact but a symptom
    point's day can rest on several."""

    day: date
    at: datetime
    value: float | str | bool
    ids: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class Series:
    kind: SeriesKind
    scope: Scope
    points: tuple[Point, ...]
    answered_days: frozenset[date]


@dataclass(frozen=True, slots=True)
class SeriesSet:
    """Every series this key can read, for one window. `withheld` names the scopes a series
    was left out for — the key does not hold them — so a caller never mistakes "nothing
    here" for "nothing happened"."""

    series: dict[SeriesKind, Series] = field(default_factory=dict)
    withheld: tuple[Scope, ...] = ()

    def get(self, kind: SeriesKind) -> Series | None:
        return self.series.get(kind)


def _series(kind: SeriesKind, scope: Scope, points: Sequence[Point]) -> Series:
    ordered = tuple(sorted(points, key=lambda p: (p.at, p.value if isinstance(p.value, str) else "")))
    return Series(
        kind=kind,
        scope=scope,
        points=ordered,
        answered_days=frozenset(p.day for p in ordered),
    )


def _window(now: datetime | None, window_days: int) -> tuple[datetime, datetime]:
    moment = as_utc(now) if now is not None else utcnow()
    return moment - timedelta(days=window_days), moment


# --- readings ----------------------------------------------------------------------------

_READING_SERIES: tuple[tuple[SeriesKind, str, str], ...] = (
    (SeriesKind.BP_SYSTOLIC, "blood_pressure", "systolic"),
    (SeriesKind.BP_DIASTOLIC, "blood_pressure", "diastolic"),
    (SeriesKind.SUGAR, "blood_sugar", "glucose"),
    (SeriesKind.WEIGHT, "weight", "kg"),
    (SeriesKind.PULSE, "heart_rate", "pulse"),
)


async def _facts(
    session: AsyncSession,
    *,
    context: KeyContext,
    scope: Scope,
    subject: str,
    attribute: str,
    since: datetime,
    until: datetime,
) -> Sequence[Fact]:
    where: tuple[ColumnElement[bool], ...] = (
        Fact.subject == subject,
        Fact.attribute == attribute,
        Fact.superseded_at.is_(None),
        Fact.confidence_state != ConfidenceState.DISPUTED,
        Fact.valid_from >= since,
        Fact.valid_from <= until,
        fact_cites_only_what_is_held_here(context, scope),
    )
    return await audited_read(session, Fact, context, scope, where=where)


async def reading_series(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: SeriesKind,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
) -> Series:
    """One reading kind (systolic, diastolic, sugar, weight or pulse), under READINGS."""
    found = next((row for row in _READING_SERIES if row[0] is kind), None)
    if found is None:
        raise ValueError(f"{kind} is not a reading series")
    _, subject, value_key = found
    if not context.allows(Scope.READINGS):
        return _series(kind, Scope.READINGS, ())
    since, until = _window(now, window_days)
    facts = await _facts(
        session,
        context=context,
        scope=Scope.READINGS,
        subject=subject,
        attribute="reading",
        since=since,
        until=until,
    )
    points: list[Point] = []
    for fact in facts:
        value = fact.value if isinstance(fact.value, dict) else {}
        number = value.get(value_key)
        if isinstance(number, int | float) and not isinstance(number, bool):
            at = as_utc(fact.valid_from)
            points.append(
                Point(
                    day=local_date(at, context),
                    at=at,
                    value=float(number),
                    ids=(Evidence("fact", fact.id, Scope.READINGS),),
                )
            )
    return _series(kind, Scope.READINGS, points)


# --- lifestyle logs (RE-10, docs/recommendation-engine.md §2.7) --------------------------

_LOG_METRIC_SERIES: tuple[tuple[SeriesKind, MetricKind], ...] = (
    (SeriesKind.STEPS, MetricKind.STEPS),
    (SeriesKind.SLEEP_MINUTES, MetricKind.SLEEP),
    (SeriesKind.WATER_CUPS, MetricKind.WATER),
)
"""Heart rate is not here: `app.lifestyle.metrics.log_metric` writes it in the same shape a
typed blood-pressure machine's pulse already takes, so `reading_series(kind=PULSE)` already
reads it — a second reader over the same facts would double them, not add to them."""


async def lifestyle_metric_series(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: SeriesKind,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
) -> Series:
    """Steps, sleep or water, under READINGS: one point per entry he logged
    (`app.lifestyle.metrics.metric_series`). A skip is a point of value `0.0` — "no water
    today" is a logged zero, a real answer under §2.7 — so it lands in `answered_days` the
    same as a number does."""
    found = next((row for row in _LOG_METRIC_SERIES if row[0] is kind), None)
    if found is None:
        raise ValueError(f"{kind} is not a lifestyle metric series")
    _, metric_kind = found
    if not context.allows(Scope.READINGS):
        return _series(kind, Scope.READINGS, ())
    since, until = _window(now, window_days)
    entries = await metric_series(session, context=context, kind=metric_kind, since=since, until=until)
    points: list[Point] = []
    for entry in entries:
        value = 0.0 if entry.value is None else entry.value
        points.append(
            Point(
                day=local_date(entry.taken_at, context),
                at=entry.taken_at,
                value=value,
                ids=(Evidence("fact", entry.fact_id, Scope.READINGS),),
            )
        )
    return _series(kind, Scope.READINGS, points)


_MEAL_SERIES: tuple[tuple[SeriesKind, Meal], ...] = (
    (SeriesKind.MEAL_BREAKFAST, Meal.BREAKFAST),
    (SeriesKind.MEAL_LUNCH, Meal.LUNCH),
    (SeriesKind.MEAL_DINNER, Meal.DINNER),
    (SeriesKind.MEAL_SNACK, Meal.SNACK),
)


async def meal_series(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: SeriesKind,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
) -> Series:
    """One meal slot, under READINGS (the owner's call, 2026-09-17: whoever checks on him day
    to day can see whether he has eaten). One point per entry logged for that slot
    (`app.lifestyle.food.food_log`), valued `True` when he had it, `False` when he said he did
    not — "no breakfast" is an entry, not a missing one (§2.7), so it counts as answered."""
    found = next((row for row in _MEAL_SERIES if row[0] is kind), None)
    if found is None:
        raise ValueError(f"{kind} is not a meal series")
    _, meal = found
    if not context.allows(Scope.READINGS):
        return _series(kind, Scope.READINGS, ())
    since, until = _window(now, window_days)
    entries = await food_log(session, context=context, meal=meal, since=since, until=until)
    points = [
        Point(
            day=local_date(entry.eaten_at, context),
            at=entry.eaten_at,
            value=entry.status is LogStatus.LOGGED,
            ids=(Evidence("fact", entry.fact_id, Scope.READINGS),),
        )
        for entry in entries
    ]
    return _series(kind, Scope.READINGS, points)


# --- doses -------------------------------------------------------------------------------


async def dose_series(
    session: AsyncSession,
    *,
    context: KeyContext,
    line_id: uuid.UUID | None = None,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
) -> Series:
    """Whether each dose tapped in the window landed on time: `True` on time, `False` late.
    Narrowed to one medicine line when `line_id` is given (`SeriesKind.DOSE_ON_TIME` is a
    per-line series, §2.2); every active line's taps otherwise."""
    if not context.allows(Scope.MEDICINES):
        return _series(SeriesKind.DOSE_ON_TIME, Scope.MEDICINES, ())
    since, until = _window(now, window_days)
    where: tuple[ColumnElement[bool], ...] = (
        DoseTaken.taken_at >= since,
        DoseTaken.taken_at <= until,
        *(() if line_id is None else (DoseTaken.line_id == line_id,)),
    )
    taken = await audited_read(session, DoseTaken, context, Scope.MEDICINES, where=where)
    points = [
        Point(
            day=local_date(as_utc(dose.taken_at), context),
            at=as_utc(dose.taken_at),
            value=not dose.late,
            ids=(Evidence("event", dose.event_id, Scope.MEDICINES),),
        )
        for dose in taken
    ]
    return _series(SeriesKind.DOSE_ON_TIME, Scope.MEDICINES, points)


# --- symptoms ------------------------------------------------------------------------------


async def symptom_series(
    session: AsyncSession,
    *,
    context: KeyContext,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
) -> Series:
    """One point per symptom code reported, under RECORDS — the symptom log's own scope
    (`app.safety.symptom_log`). A report with no code the tables know ("not well") is one
    point of its own, `"not_well"`."""
    if not context.allows(SYMPTOM_SCOPE):
        return _series(SeriesKind.SYMPTOM, SYMPTOM_SCOPE, ())
    since, until = _window(now, window_days)
    facts = await _facts(
        session,
        context=context,
        scope=SYMPTOM_SCOPE,
        subject=SYMPTOM,
        attribute=REPORTED,
        since=since,
        until=until,
    )
    points: list[Point] = []
    for fact in facts:
        value = fact.value if isinstance(fact.value, dict) else {}
        codes = [code for code in value.get("symptoms", []) if isinstance(code, str)]
        at = as_utc(fact.valid_from)
        day = local_date(at, context)
        evidence = (Evidence("fact", fact.id, SYMPTOM_SCOPE),)
        for code in codes or ["not_well"]:
            points.append(Point(day=day, at=at, value=code, ids=evidence))
    return _series(SeriesKind.SYMPTOM, SYMPTOM_SCOPE, points)


# --- cloud taps ----------------------------------------------------------------------------


async def feeling_series(
    session: AsyncSession,
    *,
    context: KeyContext,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
) -> Series:
    """His own taps on the feeling cloud, under RECORDS — the same scope
    `app.reasoning.feelings.record.read_situation` reads them under."""
    if not context.allows(Scope.RECORDS):
        return _series(SeriesKind.FEELING, Scope.RECORDS, ())
    since, until = _window(now, window_days)
    taps = await audited_read(
        session,
        FeelingTap,
        context,
        Scope.RECORDS,
        where=(FeelingTap.tapped_at >= since, FeelingTap.tapped_at <= until),
    )
    points = [
        Point(
            day=local_date(as_utc(tap.tapped_at), context),
            at=as_utc(tap.tapped_at),
            value=tap.word.value,
            ids=(Evidence("tap", tap.id, Scope.RECORDS),),
        )
        for tap in taps
    ]
    return _series(SeriesKind.FEELING, Scope.RECORDS, points)


# --- appointments --------------------------------------------------------------------------


async def appointment_series(
    session: AsyncSession,
    *,
    context: KeyContext,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
) -> Series:
    """Visits on the spine, under VISITS: the status each was in, on the day it was for."""
    if not context.allows(Scope.VISITS):
        return _series(SeriesKind.APPOINTMENT, Scope.VISITS, ())
    since, until = _window(now, window_days)
    visits = await audited_read(
        session,
        Appointment,
        context,
        Scope.VISITS,
        where=(Appointment.scheduled_at >= since, Appointment.scheduled_at <= until),
    )
    points = [
        Point(
            day=local_date(as_utc(visit.scheduled_at), context),
            at=as_utc(visit.scheduled_at),
            value=visit.status.value,
            ids=(Evidence("appointment", visit.id, Scope.VISITS),),
        )
        for visit in visits
    ]
    return _series(SeriesKind.APPOINTMENT, Scope.VISITS, points)


# --- engagement ------------------------------------------------------------------------------


async def engagement_series(
    session: AsyncSession,
    *,
    context: KeyContext,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
) -> Series:
    """What he did with the feed, under RECORDS: one point per `ENGAGEMENT` event
    (`app.delivery.feed.engagement.record_engagement`), valued by what the label says —
    opened, played, dismissed, shared."""
    if not context.allows(Scope.RECORDS):
        return _series(SeriesKind.ENGAGEMENT, Scope.RECORDS, ())
    since, until = _window(now, window_days)
    events = await audited_read(
        session,
        Event,
        context,
        Scope.RECORDS,
        where=(
            Event.kind == EventKind.ENGAGEMENT,
            Event.occurred_at >= since,
            Event.occurred_at <= until,
        ),
    )
    points = [
        Point(
            day=local_date(as_utc(event.occurred_at), context),
            at=as_utc(event.occurred_at),
            value=event.label or "engaged",
            ids=(Evidence("event", event.id, Scope.RECORDS),),
        )
        for event in events
    ]
    return _series(SeriesKind.ENGAGEMENT, Scope.RECORDS, points)


# --- everything at once --------------------------------------------------------------------


async def read_series(
    session: AsyncSession,
    *,
    context: KeyContext,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
) -> SeriesSet:
    """Every series this key can read, for one window, in one call. A scope this key does
    not hold is left out and named in `withheld`, never silently empty."""
    series: dict[SeriesKind, Series] = {}
    withheld: list[Scope] = []

    if context.allows(Scope.READINGS):
        for kind, _, _ in _READING_SERIES:
            series[kind] = await reading_series(
                session, context=context, kind=kind, now=now, window_days=window_days
            )
        for kind, _ in _LOG_METRIC_SERIES:
            series[kind] = await lifestyle_metric_series(
                session, context=context, kind=kind, now=now, window_days=window_days
            )
        for kind, _ in _MEAL_SERIES:
            series[kind] = await meal_series(
                session, context=context, kind=kind, now=now, window_days=window_days
            )
    else:
        withheld.append(Scope.READINGS)

    if context.allows(Scope.MEDICINES):
        series[SeriesKind.DOSE_ON_TIME] = await dose_series(
            session, context=context, now=now, window_days=window_days
        )
    else:
        withheld.append(Scope.MEDICINES)

    if context.allows(Scope.VISITS):
        series[SeriesKind.APPOINTMENT] = await appointment_series(
            session, context=context, now=now, window_days=window_days
        )
    else:
        withheld.append(Scope.VISITS)

    # SYMPTOM, FEELING and ENGAGEMENT are all read under RECORDS (`scope_for_subject`,
    # `read_situation`, `scope_for_event`): one check, not three.
    if context.allows(Scope.RECORDS):
        series[SeriesKind.SYMPTOM] = await symptom_series(
            session, context=context, now=now, window_days=window_days
        )
        series[SeriesKind.FEELING] = await feeling_series(
            session, context=context, now=now, window_days=window_days
        )
        series[SeriesKind.ENGAGEMENT] = await engagement_series(
            session, context=context, now=now, window_days=window_days
        )
    else:
        withheld.append(Scope.RECORDS)

    return SeriesSet(series=series, withheld=tuple(withheld))
