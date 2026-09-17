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
    assert found.withheld == (Scope.READINGS,)

    # A scope kit does hold still reads: the withheld reading series is not read as "nothing
    # happened" on the whole profile, only on the part the key does not cover.
    doses = found.get(SeriesKind.DOSE_ON_TIME)
    assert doses is not None
    assert len(doses.points) == 1
