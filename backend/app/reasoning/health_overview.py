"""The Health Overview ring and metric rows (design-direction.md, Health tab).

The reference shows "Wellness Score 85 — Good": an invented grade. Nura does not decide what
is wrong, so the ring here holds a real figure of his own, one he can check against what he
did — never a score, never a percentage dressed as one. Two are built, because the doc asks
for either: **doses taken this week** ("12 of 14", `doses_this_week`) and **days he checked in
this week** (`check_ins_this_week`). `app.channels.api.health_tab` defaults the ring to doses and
recommends it — see the PR report for why.

The metric rows read `app.lifestyle.metrics` for what he has logged: a running total for the
day for steps and water, the latest reading for heart rate and sleep. Heart rate is looked up
against the reference-range port (`app.reasoning.ranges`) the lab trend uses; there is no
entry for it in the fixture table today, so `heart_rate_range` comes back `None` and the
caller says so honestly rather than inventing a band.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import as_utc
from app.drugs.registry import DrugRegistry
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.lifestyle.metrics import MetricKind, MetricRow, metric_row
from app.medicines.dose import Dose, Frequency
from app.medicines.models import DoseTaken, LineStatus, MedicationLine
from app.medicines.service import language_for, today, today_in
from app.medicines.strings import PLAIN_NAME
from app.reasoning.feelings.models import FeelingTap
from app.reasoning.ranges import ReferenceRanges
from app.regions import REGION_TZ
from app.routines.service import his_day

HEART_RATE_ANALYTE = "heart_rate"


def monday_of(day: date) -> date:
    """The Monday of the week `day` falls in — the same week boundary the nudge metrics use
    (`app.delivery.nudges.metrics._monday`), so "this week" means the same thing everywhere."""
    return day - timedelta(days=day.weekday())


class RingKind(StrEnum):
    DOSES = "doses"
    CHECK_INS = "check_ins"


@dataclass(frozen=True, slots=True)
class DoseWeek:
    """Doses taken this week against doses scheduled this week, for his active medicines,
    from Monday up to and including today — never a future day not yet due, so the number is
    always one he can check against what already happened."""

    taken: int
    total: int
    week_starts_on: date
    as_of: date


async def _active_lines(session: AsyncSession, *, context: KeyContext) -> list[MedicationLine]:
    where: list[ColumnElement[bool]] = [
        MedicationLine.superseded_at.is_(None),
        MedicationLine.status == LineStatus.ACTIVE,
    ]
    return list(await audited_read(session, MedicationLine, context, Scope.MEDICINES, where=where))


async def doses_this_week(session: AsyncSession, *, context: KeyContext) -> DoseWeek:
    today = today_in(context)
    monday = monday_of(today)
    elapsed = (today - monday).days + 1  # Monday itself counts as one elapsed day
    lines = await _active_lines(session, context=context)
    total = 0
    for line in lines:
        dose = Dose.from_json(line.dose)
        anchors = len(dose.scheduled_anchors)
        if anchors == 0:
            continue  # as-needed: no schedule to count against
        if dose.frequency is Frequency.WEEKLY:
            total += anchors  # one week, one due, however many days have started
        else:
            total += anchors * elapsed
    if not lines:
        return DoseWeek(taken=0, total=0, week_starts_on=monday, as_of=today)
    zone = REGION_TZ[context.region]
    line_ids = [line.id for line in lines]
    taken_rows = await audited_read(
        session,
        DoseTaken,
        context,
        Scope.MEDICINES,
        where=(DoseTaken.line_id.in_(line_ids),),
    )
    taken = sum(
        1
        for row in taken_rows
        if monday <= as_utc(row.taken_at).astimezone(zone).date() <= today
    )
    return DoseWeek(taken=min(taken, total) if total else taken, total=total, week_starts_on=monday, as_of=today)


@dataclass(frozen=True, slots=True)
class CheckInWeek:
    days: int
    week_starts_on: date
    as_of: date


async def check_ins_this_week(session: AsyncSession, *, context: KeyContext) -> CheckInWeek:
    today = today_in(context)
    monday = monday_of(today)
    zone = REGION_TZ[context.region]
    taps = await audited_read(session, FeelingTap, context, Scope.RECORDS, where=())
    days = {
        as_utc(tap.tapped_at).astimezone(zone).date()
        for tap in taps
        if monday <= as_utc(tap.tapped_at).astimezone(zone).date() <= today
    }
    return CheckInWeek(days=len(days), week_starts_on=monday, as_of=today)


@dataclass(frozen=True, slots=True)
class HeartRateRow:
    row: MetricRow
    range_known: bool
    """Whether a reference range exists for heart rate at all (`app.reasoning.ranges`). False
    today: the fixture table has no analyte for it, and no band or pill is invented."""


@dataclass(frozen=True, slots=True)
class HealthOverview:
    doses: DoseWeek
    check_ins: CheckInWeek
    steps: MetricRow
    heart_rate: HeartRateRow
    sleep: MetricRow
    water: MetricRow


async def health_overview(
    session: AsyncSession, *, context: KeyContext, ranges: ReferenceRanges
) -> HealthOverview:
    doses = await doses_this_week(session, context=context)
    check_ins = await check_ins_this_week(session, context=context)
    steps = await metric_row(session, context=context, kind=MetricKind.STEPS)
    heart_rate_row = await metric_row(session, context=context, kind=MetricKind.HEART_RATE)
    sleep = await metric_row(session, context=context, kind=MetricKind.SLEEP)
    water = await metric_row(session, context=context, kind=MetricKind.WATER)
    heart_rate = HeartRateRow(
        row=heart_rate_row, range_known=ranges.analyte(HEART_RATE_ANALYTE) is not None
    )
    return HealthOverview(
        doses=doses, check_ins=check_ins, steps=steps, heart_rate=heart_rate, sleep=sleep, water=water
    )


ANCHOR_ORDER = ("breakfast", "lunch", "dinner", "bed")


@dataclass(frozen=True, slots=True)
class MedicationReminderLine:
    """One of his next doses (design-direction.md, "Medication Reminder"): the medicine, the
    instruction as the existing dose card already says it, the moment of his day, and the
    real clock time for it — read from his medicines and dose windows
    (`app.medicines.service.today`, `app.routines.service.his_day`); nothing here duplicates
    that logic, only reads and sorts it."""

    line_id: uuid.UUID
    name: str
    instruction: str
    anchor: str
    time_of_day: str


async def medication_reminder(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    language: str | None = None,
) -> list[MedicationReminderLine]:
    """His next doses, untaken ones only, soonest anchor first — the existing dose cards
    (`today`), sorted and with a real clock time attached."""
    lang = await language_for(session, context, language)
    slots = await today(session, context=context, registry=registry, language=lang)
    day = await his_day(session, context=context)
    untaken = sorted(
        (slot for slot in slots if not slot.taken),
        key=lambda slot: (ANCHOR_ORDER.index(slot.anchor), slot.line.generic),
    )
    return [
        MedicationReminderLine(
            line_id=slot.line.id,
            name=PLAIN_NAME[lang][registry.monograph(slot.line.generic).plain_name_id],
            instruction=slot.card,
            anchor=slot.anchor,
            time_of_day=day.anchors[slot.anchor].strftime("%H:%M"),
        )
        for slot in untaken
    ]


__all__ = [
    "ANCHOR_ORDER",
    "CheckInWeek",
    "DoseWeek",
    "HealthOverview",
    "HeartRateRow",
    "MedicationReminderLine",
    "RingKind",
    "check_ins_this_week",
    "doses_this_week",
    "health_overview",
    "medication_reminder",
    "monday_of",
]
