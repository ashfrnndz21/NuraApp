"""Steps, heart rate, sleep, water and meals: what he logs about his day
(design-direction.md, "Metric rows he can log"; docs/recommendation-engine.md §2.7).

    Acceptance: a value, a unit, a time and provenance for each of the four metrics; a meal
    is one Fact per slot with `had: true | false`, never a missing entry for "no breakfast";
    three states throughout — logged, logged as none, not logged — never conflated; every new
    log is scoped by key like every other health fact.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.keys.context import OutOfScope
from app.keys.scopes import ROLE_SCOPES, KeyRole, Scope
from app.lifestyle.food import Meal, NotAFoodEntry, food_around, food_log, log_food, meal_status_on
from app.lifestyle.metrics import (
    LogStatus,
    MetricKind,
    NotAWholeMetric,
    log_metric,
    metric_row,
    metric_series,
)
from app.memory.models import ConfidenceState
from tests.conftest import FROZEN_AT
from tests.medicines_support import let_in, pa


async def test_a_metric_he_logs_has_a_value_a_unit_a_time_and_his_own_provenance(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    entry = await log_metric(sg, context=owner, kind=MetricKind.HEART_RATE, value=72)
    assert entry.value == 72
    assert entry.unit == "/min"
    assert entry.taken_at is not None
    assert entry.status is LogStatus.LOGGED
    # The fact behind it carries his own confirmed word, like a typed blood pressure.
    from app.memory.semantic import current_facts

    facts = await current_facts(sg, context=owner, subject="heart_rate")
    assert len(facts) == 1
    assert facts[0].confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
    assert facts[0].confidence == 1.0
    assert facts[0].confirmed_by_person_id is not None
    assert facts[0].event_id is not None


async def test_steps_and_water_add_up_through_the_day_heart_rate_and_sleep_are_the_latest(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await pa(sg)
    await log_metric(sg, context=owner, kind=MetricKind.STEPS, value=2000)
    await log_metric(sg, context=owner, kind=MetricKind.STEPS, value=1500)
    row = await metric_row(sg, context=owner, kind=MetricKind.STEPS)
    assert row.status is LogStatus.LOGGED
    assert row.value == 3500

    await log_metric(sg, context=owner, kind=MetricKind.HEART_RATE, value=68)
    clock.step(timedelta(hours=1))
    later = await log_metric(sg, context=owner, kind=MetricKind.HEART_RATE, value=75)
    row = await metric_row(sg, context=owner, kind=MetricKind.HEART_RATE)
    assert row.status is LogStatus.LOGGED
    assert row.value == 75
    assert row.last_logged_at == later.taken_at


async def test_a_skip_is_a_real_entry_distinct_from_nothing_logged(sg: AsyncSession) -> None:
    owner = await pa(sg)
    # Nobody has said anything about water yet.
    row = await metric_row(sg, context=owner, kind=MetricKind.WATER)
    assert row.status is LogStatus.NOT_LOGGED
    assert row.value is None

    # He says "none today" — a real answer, not a blank.
    skipped = await log_metric(sg, context=owner, kind=MetricKind.WATER, skipped=True)
    assert skipped.status is LogStatus.SKIPPED
    assert skipped.value is None
    row = await metric_row(sg, context=owner, kind=MetricKind.WATER)
    assert row.status is LogStatus.SKIPPED
    assert row.value is None

    # Heart rate has no meaningful "none": skipping it is refused, not guessed at.
    with pytest.raises(NotAWholeMetric):
        await log_metric(sg, context=owner, kind=MetricKind.HEART_RATE, skipped=True)
    with pytest.raises(NotAWholeMetric):
        await log_metric(sg, context=owner, kind=MetricKind.STEPS, value=10, skipped=True)


async def test_the_series_reader_is_a_cheap_windowed_read(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await pa(sg)
    first = await log_metric(sg, context=owner, kind=MetricKind.WATER, value=1)
    boundary = clock.now()
    clock.step(timedelta(hours=3))
    second = await log_metric(sg, context=owner, kind=MetricKind.WATER, value=1)
    narrowed = await metric_series(
        sg, context=owner, kind=MetricKind.WATER, since=boundary + timedelta(hours=1)
    )
    assert [e.fact_id for e in narrowed] == [second.fact_id]
    whole = await metric_series(sg, context=owner, kind=MetricKind.WATER)
    assert [e.fact_id for e in whole] == [first.fact_id, second.fact_id]


async def test_the_newest_entry_wins_on_a_tie_by_a_deterministic_tie_breaker(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    a = await log_metric(sg, context=owner, kind=MetricKind.HEART_RATE, value=60, taken_at=FROZEN_AT)
    b = await log_metric(sg, context=owner, kind=MetricKind.HEART_RATE, value=90, taken_at=FROZEN_AT)
    expected = max((a, b), key=lambda e: str(e.fact_id))
    row = await metric_row(sg, context=owner, kind=MetricKind.HEART_RATE)
    assert row.value == expected.value
    # Same inputs, same answer, run again — never arbitrary.
    row_again = await metric_row(sg, context=owner, kind=MetricKind.HEART_RATE)
    assert row_again.value == row.value


async def test_a_metric_is_refused_out_of_range_or_from_the_future(sg: AsyncSession) -> None:
    owner = await pa(sg)
    with pytest.raises(NotAWholeMetric):
        await log_metric(sg, context=owner, kind=MetricKind.HEART_RATE, value=400)
    with pytest.raises(NotAWholeMetric):
        await log_metric(
            sg, context=owner, kind=MetricKind.WATER, value=1, taken_at=FROZEN_AT + timedelta(days=1)
        )


async def test_a_key_without_readings_cannot_log_or_read_a_metric(sg: AsyncSession) -> None:
    owner = await pa(sg)
    # A helper's preset holds no readings scope, so it cannot be narrowed to include one.
    helper = await let_in(
        sg, owner, phone="+6597770004", name="Siti", role=KeyRole.HELPER, scopes={Scope.PROFILE, Scope.EMERGENCY}
    )
    with pytest.raises(OutOfScope):
        await log_metric(sg, context=helper, kind=MetricKind.STEPS, value=1000)
    with pytest.raises(OutOfScope):
        await metric_row(sg, context=helper, kind=MetricKind.STEPS)

    # A caregiver's preset holds both the record's door and the readings the fact sits
    # under, so she can log and read.
    caregiver = await let_in(
        sg, owner, phone="+6592220002", name="Mei", role=KeyRole.CAREGIVER, scopes=ROLE_SCOPES[KeyRole.CAREGIVER]
    )
    await log_metric(sg, context=caregiver, kind=MetricKind.STEPS, value=1000)
    row = await metric_row(sg, context=caregiver, kind=MetricKind.STEPS)
    assert row.value == 1000


# --- meals: docs/recommendation-engine.md §2.7 --------------------------------------------


async def test_a_meal_is_one_fact_per_slot_with_had_true_or_false(sg: AsyncSession) -> None:
    owner = await pa(sg)
    entry = await log_food(sg, context=owner, meal=Meal.BREAKFAST, food="nasi lemak", amount="a plate")
    assert entry.status is LogStatus.LOGGED
    assert entry.food == "nasi lemak"

    from app.memory.semantic import current_facts

    facts = await current_facts(sg, context=owner, subject="meal", attribute="breakfast")
    assert len(facts) == 1
    assert facts[0].value["had"] is True


async def test_no_breakfast_is_an_entry_not_a_missing_one(sg: AsyncSession) -> None:
    owner = await pa(sg)
    assert await meal_status_on(sg, context=owner, meal=Meal.BREAKFAST) is LogStatus.NOT_LOGGED
    skipped = await log_food(sg, context=owner, meal=Meal.BREAKFAST, skipped=True)
    assert skipped.status is LogStatus.SKIPPED
    assert skipped.food is None and skipped.catalog_id is None and skipped.amount is None

    from app.memory.semantic import current_facts

    facts = await current_facts(sg, context=owner, subject="meal", attribute="breakfast")
    assert facts[0].value["had"] is False
    assert await meal_status_on(sg, context=owner, meal=Meal.BREAKFAST) is LogStatus.SKIPPED

    with pytest.raises(NotAFoodEntry):
        await log_food(sg, context=owner, meal=Meal.LUNCH, skipped=True, food="rice")
    with pytest.raises(NotAFoodEntry):
        await log_food(sg, context=owner, meal=Meal.LUNCH)


async def test_food_around_finds_what_he_ate_near_a_moment(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await pa(sg)
    breakfast = await log_food(sg, context=owner, meal=Meal.BREAKFAST, food="porridge")
    clock.step(timedelta(hours=10))
    dinner_at = clock.now()
    await log_food(sg, context=owner, meal=Meal.DINNER, food="fish")
    near = await food_around(sg, context=owner, moment=FROZEN_AT, before=1, after=1)
    assert [e.fact_id for e in near] == [breakfast.fact_id]
    near_dinner = await food_around(sg, context=owner, moment=dinner_at, before=1, after=1)
    assert len(near_dinner) == 1 and near_dinner[0].food == "fish"


async def test_meals_sit_under_readings_the_owners_call(sg: AsyncSession) -> None:
    owner = await pa(sg)
    # A helper's preset holds no readings scope, so it cannot see whether he has eaten.
    helper_no_readings = await let_in(
        sg, owner, phone="+6597770004", name="Siti", role=KeyRole.HELPER, scopes={Scope.PROFILE}
    )
    with pytest.raises(OutOfScope):
        await food_log(sg, context=helper_no_readings)

    # Any key that does hold readings can — the owner's deliberate call, widened from the
    # design draft that would have kept meals under the general record instead.
    viewer_with_readings = await let_in(
        sg, owner, phone="+6595550003", name="Kit", role=KeyRole.VIEWER, scopes={Scope.PROFILE, Scope.READINGS}
    )
    await log_food(sg, context=owner, meal=Meal.LUNCH, food="chicken rice")
    found = await food_log(sg, context=viewer_with_readings)
    assert len(found) == 1
