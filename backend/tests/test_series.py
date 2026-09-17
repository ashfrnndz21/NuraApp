"""RE-03: series readers for what the record already holds.

A golden profile — one dose tapped, one blood pressure, one symptom, one cloud tap, one
appointment and one feed card opened, each on its own day — read back through
`app.reasoning.patterns.series.read_series` and checked against exactly what was written.
Then the scope check: a key that does not hold READINGS gets no reading series at all, and
`SeriesSet.withheld` names READINGS so a caller never mistakes that for nothing having
happened.

The clock is frozen at Thursday 3 September 2026, 08:00 UTC on Pa's wall in Singapore
(`tests.conftest.FROZEN_AT`), and stepped a day at a time so each entry falls on a day of
its own.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.db import utcnow
from app.keys.context import KeyContext
from app.keys.scopes import ROLE_SCOPES, KeyRole, Scope
from app.lifestyle.food import Meal, log_food
from app.lifestyle.metrics import MetricKind, log_metric
from app.medicines.service import record_dose_taken
from app.memory.models import EventKind
from app.reasoning.feelings.record import local_date
from app.reasoning.feelings.service import record_tap
from app.reasoning.patterns.series import SeriesKind, read_series
from app.safety.red_flags import Feeling
from app.safety.symptom_log import Logged, log_symptom
from tests.family_support import household
from tests.feelings_support import (
    REGISTRY,
    STORE,
    TRANSCRIBER,
    VIA,
    blood_pressure,
    happened,
    new_medicine,
    visit_with,
)


async def _log_symptom(session: AsyncSession, owner: KeyContext, words: str) -> Logged:
    return await log_symptom(
        session,
        context=owner,
        store=STORE,
        transcriber=TRANSCRIBER,
        registry=REGISTRY,
        via=VIA,
        words=words,
    )


async def test_series_match_the_golden_profile(sg: AsyncSession, clock: FrozenClock) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)

    added = await new_medicine(sg, owner)
    dose_day = local_date(utcnow(), owner)
    dose = await record_dose_taken(sg, context=owner, line_id=added.line.id)

    clock.step(timedelta(days=1))
    reading_day = local_date(utcnow(), owner)
    reading = await blood_pressure(sg, owner, systolic=132, diastolic=84)

    clock.step(timedelta(days=1))
    symptom_day = local_date(utcnow(), owner)
    logged = await _log_symptom(sg, owner, "a bit of a cough")

    clock.step(timedelta(days=1))
    tap_day = local_date(utcnow(), owner)
    tapped = await record_tap(
        sg,
        context=owner,
        word=Feeling.FINE,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )

    clock.step(timedelta(days=1))
    visit_at = utcnow()
    visit_day = local_date(visit_at, owner)
    visit = await visit_with(sg, owner, at=visit_at)

    clock.step(timedelta(days=1))
    engaged_at = utcnow()
    engaged_day = local_date(engaged_at, owner)
    event = await happened(sg, owner, EventKind.ENGAGEMENT, engaged_at, "opened: read card")

    found = await read_series(sg, context=owner)

    systolic = found.get(SeriesKind.BP_SYSTOLIC)
    assert systolic is not None
    assert [(p.day, p.value) for p in systolic.points] == [(reading_day, 132.0)]
    assert (systolic.points[0].ids[0].kind, systolic.points[0].ids[0].id) == ("fact", reading.id)
    assert systolic.answered_days == {reading_day}

    diastolic = found.get(SeriesKind.BP_DIASTOLIC)
    assert diastolic is not None
    assert [(p.day, p.value) for p in diastolic.points] == [(reading_day, 84.0)]

    doses = found.get(SeriesKind.DOSE_ON_TIME)
    assert doses is not None
    assert [(p.day, p.value) for p in doses.points] == [(dose_day, True)]
    assert (doses.points[0].ids[0].kind, doses.points[0].ids[0].id) == ("event", dose.event_id)

    symptoms = found.get(SeriesKind.SYMPTOM)
    assert symptoms is not None
    assert [(p.day, p.value) for p in symptoms.points] == [
        (symptom_day, code.value) for code in logged.entry.symptoms
    ]
    assert symptoms.answered_days == {symptom_day}

    feelings = found.get(SeriesKind.FEELING)
    assert feelings is not None
    assert [(p.day, p.value) for p in feelings.points] == [(tap_day, Feeling.FINE.value)]
    assert feelings.points[0].ids[0].id == tapped.tap.id

    appointments = found.get(SeriesKind.APPOINTMENT)
    assert appointments is not None
    assert [(p.day, p.value) for p in appointments.points] == [(visit_day, visit.status.value)]

    engagement = found.get(SeriesKind.ENGAGEMENT)
    assert engagement is not None
    assert [(p.day, p.value) for p in engagement.points] == [(engaged_day, "opened: read card")]
    assert engagement.points[0].ids[0].id == event.id

    assert found.withheld == ()


async def test_lifestyle_and_food_series_match_what_was_logged(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """RE-10: steps, sleep, water and the four meal slots, plus heart rate reusing the
    existing PULSE reading series — read back through `read_series` and checked against
    exactly what was logged, a skip included as an answered day (§2.7)."""
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)

    steps_day = local_date(utcnow(), owner)
    await log_metric(sg, context=owner, kind=MetricKind.STEPS, value=4200)

    clock.step(timedelta(days=1))
    water_skip_day = local_date(utcnow(), owner)
    await log_metric(sg, context=owner, kind=MetricKind.WATER, skipped=True)

    clock.step(timedelta(days=1))
    sleep_day = local_date(utcnow(), owner)
    await log_metric(sg, context=owner, kind=MetricKind.SLEEP, value=420)

    clock.step(timedelta(days=1))
    pulse_day = local_date(utcnow(), owner)
    await log_metric(sg, context=owner, kind=MetricKind.HEART_RATE, value=72)

    clock.step(timedelta(days=1))
    breakfast_day = local_date(utcnow(), owner)
    await log_food(sg, context=owner, meal=Meal.BREAKFAST, skipped=True)

    clock.step(timedelta(days=1))
    lunch_day = local_date(utcnow(), owner)
    await log_food(sg, context=owner, meal=Meal.LUNCH, food="chicken rice")

    # `food_log`'s window is `[since, until)` (its own docstring): step past the last write
    # so `read_series`'s "now" does not land exactly on it and exclude it by that boundary.
    clock.step(timedelta(seconds=1))
    found = await read_series(sg, context=owner)

    steps = found.get(SeriesKind.STEPS)
    assert steps is not None
    assert [(p.day, p.value) for p in steps.points] == [(steps_day, 4200.0)]
    assert steps.answered_days == {steps_day}

    water = found.get(SeriesKind.WATER_CUPS)
    assert water is not None
    assert [(p.day, p.value) for p in water.points] == [(water_skip_day, 0.0)]
    assert water.answered_days == {water_skip_day}

    sleep = found.get(SeriesKind.SLEEP_MINUTES)
    assert sleep is not None
    assert [(p.day, p.value) for p in sleep.points] == [(sleep_day, 420.0)]

    # Heart rate needs no reader of its own: `log_metric` writes it in the same shape a
    # typed blood-pressure machine's pulse already takes, so the existing PULSE series
    # already picks it up.
    pulse = found.get(SeriesKind.PULSE)
    assert pulse is not None
    assert [(p.day, p.value) for p in pulse.points] == [(pulse_day, 72.0)]

    breakfast = found.get(SeriesKind.MEAL_BREAKFAST)
    assert breakfast is not None
    assert [(p.day, p.value) for p in breakfast.points] == [(breakfast_day, False)]
    assert breakfast.answered_days == {breakfast_day}

    lunch = found.get(SeriesKind.MEAL_LUNCH)
    assert lunch is not None
    assert [(p.day, p.value) for p in lunch.points] == [(lunch_day, True)]

    dinner = found.get(SeriesKind.MEAL_DINNER)
    assert dinner is not None and dinner.points == ()
    assert found.get(SeriesKind.MEAL_SNACK) is not None

    assert found.withheld == ()


async def test_a_key_without_readings_gets_no_reading_series_named_as_withheld(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    kit_scopes = (ROLE_SCOPES[KeyRole.CAREGIVER] | {Scope.FAMILY}) - {Scope.READINGS}
    home = await household(sg, kit_scopes=kit_scopes)
    owner = await home.ctx(sg, home.pa)
    kit = await home.ctx(sg, home.kit)
    assert not kit.allows(Scope.READINGS)

    added = await new_medicine(sg, owner)
    await blood_pressure(sg, owner, systolic=140, diastolic=88)
    await record_dose_taken(sg, context=owner, line_id=added.line.id)

    found = await read_series(sg, context=kit)

    assert found.get(SeriesKind.BP_SYSTOLIC) is None
    assert found.get(SeriesKind.BP_DIASTOLIC) is None
    assert found.get(SeriesKind.SUGAR) is None
    assert found.get(SeriesKind.WEIGHT) is None
    assert found.get(SeriesKind.PULSE) is None
    assert found.get(SeriesKind.STEPS) is None
    assert found.get(SeriesKind.SLEEP_MINUTES) is None
    assert found.get(SeriesKind.WATER_CUPS) is None
    assert found.get(SeriesKind.MEAL_BREAKFAST) is None
    assert found.withheld == (Scope.READINGS,)

    # A scope kit does hold still reads: the withheld reading series is not read as "nothing
    # happened" on the whole profile, only on the part the key does not cover.
    doses = found.get(SeriesKind.DOSE_ON_TIME)
    assert doses is not None
    assert len(doses.points) == 1
