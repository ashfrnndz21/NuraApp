"""The Health Overview ring and metric rows, Health Insights, and the Medication Reminder
(design-direction.md, Health tab).

    Acceptance: the ring shows a real figure he can check against what he did, never a
    score; a heart-rate row carries no band until a clinician-reviewed range exists;
    insights are true statements built from his own records; the reminder reuses the
    existing dose logic.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_write
from app.clock import FrozenClock
from app.db import utcnow
from app.drugs.fixture import FixtureRegistry
from app.keys.scopes import Scope
from app.lifestyle.metrics import MetricKind, log_metric
from app.medicines.service import record_dose_taken
from app.memory.episodic import record_event
from app.memory.models import EventKind, SourceChannel
from app.reasoning.feelings.models import FeelingTap
from app.reasoning.health_insights import health_insights
from app.reasoning.health_overview import (
    check_ins_this_week,
    doses_this_week,
    health_overview,
    medication_reminder,
    monday_of,
)
from app.reasoning.ranges import FixtureRanges
from app.safety.red_flags import Feeling
from tests.medicines_support import add, label, pa

REGISTRY = FixtureRegistry.load()
RANGES = FixtureRanges.load()


async def test_doses_this_week_is_scheduled_days_elapsed_never_a_future_day(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    added = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD"))  # one dose a day
    week = await doses_this_week(sg, context=owner)
    today = week.as_of
    monday = monday_of(today)
    elapsed = (today - monday).days + 1
    assert week.total == elapsed
    assert week.taken == 0

    await record_dose_taken(sg, context=owner, line_id=added.line.id)
    week_after = await doses_this_week(sg, context=owner)
    assert week_after.taken == 1
    assert week_after.total == elapsed  # taking it does not change how many were due


async def test_doses_this_week_is_zero_of_zero_with_no_active_medicine(sg: AsyncSession) -> None:
    owner = await pa(sg)
    week = await doses_this_week(sg, context=owner)
    assert week.taken == 0 and week.total == 0


async def test_heart_rate_carries_no_band_until_a_range_exists_for_it(sg: AsyncSession) -> None:
    owner = await pa(sg)
    overview = await health_overview(sg, context=owner, ranges=RANGES)
    assert overview.heart_rate.range_known is False
    assert RANGES.analyte("heart_rate") is None  # the honest reason: none in the table yet


async def test_check_ins_this_week_counts_distinct_days_not_taps(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await pa(sg)

    async def tap() -> None:
        event = await record_event(
            sg,
            context=owner,
            kind=EventKind.SYMPTOM,
            occurred_at=utcnow(),
            label="feeling",
            source_channel=SourceChannel.APP,
        )
        await audited_write(
            sg,
            FeelingTap,
            owner,
            Scope.RECORDS,
            event_id=event.id,
            word=Feeling.TIRED,
            red=False,
            by_person_id=owner.person_id,
            tapped_at=utcnow(),
        )

    await tap()
    await tap()  # two taps, same day
    found = await check_ins_this_week(sg, context=owner)
    assert found.days == 1
    clock.step(timedelta(days=1))
    await tap()
    found_after = await check_ins_this_week(sg, context=owner)
    assert found_after.days == 2


async def test_insights_are_true_statements_and_only_shown_when_there_is_something_to_say(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    # Nothing logged yet: no insights invented.
    assert await health_insights(sg, context=owner, language="en") == []

    added = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD"))
    await record_dose_taken(sg, context=owner, line_id=added.line.id)
    await log_metric(sg, context=owner, kind=MetricKind.STEPS, value=4200)
    cards = await health_insights(sg, context=owner, language="en")
    kinds = {card.kind for card in cards}
    assert "doses" in kinds and "steps" in kinds
    for card in cards:
        assert card.headline and card.detail
        # No invented judgement words in what Nura built from his own numbers.
        for banned in ("healthy", "unhealthy", "risk", "bad", "good job you must"):
            assert banned not in card.detail.lower()


async def test_medication_reminder_reuses_today_and_carries_a_real_time(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD"))
    lines = await medication_reminder(sg, context=owner, registry=REGISTRY, language="en")
    assert len(lines) == 1
    line = lines[0]
    assert line.anchor == "breakfast"
    assert ":" in line.time_of_day  # a real clock time, e.g. "07:30", not the anchor's name
    assert "amlodipine" in line.instruction.lower() or "blood pressure" in line.instruction.lower()
