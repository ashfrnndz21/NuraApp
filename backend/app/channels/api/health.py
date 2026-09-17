"""The Health tab over HTTP (design-direction.md): the Health Overview ring and metric rows,
Health Insights, the Medication Reminder, and food intake logging.

    GET  /profiles/{id}/health/overview          the ring and the four metric rows
    POST /profiles/{id}/metrics/{kind}            log steps, heart rate, sleep or water
    GET  /profiles/{id}/metrics/{kind}            every entry logged for one metric
    GET  /profiles/{id}/health/insights          true cards built from his own records
    GET  /profiles/{id}/medication-reminder      his next doses, read from the existing logic
    GET  /food-catalog                            common foods, for a tap
    POST /profiles/{id}/food                     log a meal, or log it as skipped
    GET  /profiles/{id}/food                     what he has logged

Every route takes the key context like every other; steps, heart rate, sleep, water and meals
are all read and written under the readings scope (`app.keys.scopes._SUBJECT_SCOPES`), the
owner's call recorded there. The ring never shows an invented score (design-direction.md,
"The one rule that changes the substance, not the look"): it is doses taken this week by
default — the PR body says why.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, status
from pydantic import AwareDatetime

from app.audit.access import audited_profile_read
from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.health_schemas import (
    FoodCatalogItemOut,
    FoodEntryOut,
    FoodLogIn,
    HealthOverviewOut,
    InsightOut,
    MedicationReminderOut,
    MetricEntryOut,
    MetricLogIn,
    MetricRowOut,
    RingOut,
)
from app.channels.health_strings import (
    NO_USUAL_RANGE,
    food_catalog,
    meal_label,
    metric_label,
    metric_status_words,
    metric_value_words,
    ring_label,
    ring_words,
)
from app.errors import Refusal
from app.lifestyle.food import food_log, log_food
from app.lifestyle.metrics import LogStatus, MetricKind, MetricRow, log_metric, metric_series
from app.medicines.service import language_for, today
from app.medicines.strings import PLAIN_NAME
from app.reasoning.health_insights import health_insights
from app.reasoning.health_overview import HealthOverview, HeartRateRow, health_overview
from app.routines.service import his_day

router = APIRouter(prefix="/profiles", tags=["health"])

Language = Query(default=None, min_length=2, max_length=16)


class NoSuchMetric(Refusal):
    """No metric by that name. `steps`, `heart_rate`, `sleep`, `water` are the only ones."""


async def _voice(session: Db, context: Context) -> tuple[bool, str]:
    """Whether to speak of him in the third person (a caregiver reading), and his name for
    the slot — the caregiver-voice rule: a caregiver's screen never speaks in his voice."""
    if context.is_owner:
        return False, ""
    profile = await audited_profile_read(session, context)
    return True, profile.display_name


def _metric_kind(kind: str) -> MetricKind:
    try:
        return MetricKind(kind)
    except ValueError:
        raise NoSuchMetric(f"no metric named {kind!r}") from None


def _ring_out(overview: HealthOverview, *, language: str | None, theirs: bool, patient: str) -> RingOut:
    doses = overview.doses
    return RingOut(
        kind="doses",
        label=ring_label(language, theirs=theirs, patient=patient),
        words=ring_words(doses.taken, doses.total, language=language, theirs=theirs),
        value=doses.taken,
        total=doses.total,
        week_starts_on=doses.week_starts_on,
        as_of=doses.as_of,
    )


def _metric_row_out(
    kind: MetricKind,
    row: MetricRow,
    *,
    language: str | None,
    theirs: bool,
    patient: str,
    heart_rate: HeartRateRow | None,
) -> MetricRowOut:
    value_words = None
    if row.status is LogStatus.LOGGED and row.value is not None:
        value_words = metric_value_words(row.value, row.unit, language)
    status_words = ""
    if row.status is not LogStatus.LOGGED:
        status_words = metric_status_words(
            row.status.value, language=language, theirs=theirs, patient=patient
        )
    range_known = None
    range_words = None
    if kind is MetricKind.HEART_RATE:
        assert heart_rate is not None
        range_known = heart_rate.range_known
        if not range_known:
            lang = language if language in ("en", "ms", "zh") else "en"
            range_words = NO_USUAL_RANGE[lang]
    return MetricRowOut(
        kind=kind,
        label=metric_label(kind.value, language),
        status=row.status,
        value=row.value if row.status is LogStatus.LOGGED else None,
        value_words=value_words,
        unit=row.unit,
        last_logged_at=row.last_logged_at,
        status_words=status_words,
        range_known=range_known,
        range_words=range_words,
    )


@router.get("/{profile_id}/health/overview")
async def overview(
    request: Request, context: Context, session: Db, language: str | None = Language
) -> HealthOverviewOut:
    """The Health Overview card: the ring (doses taken this week, "12 of 14") and the four
    metric rows (steps, heart rate, sleep, water) — what he logged, never a score."""
    found = await health_overview(
        session, context=context, ranges=providers_of(request).reference_ranges
    )
    theirs, patient = await _voice(session, context)
    ring = _ring_out(found, language=language, theirs=theirs, patient=patient)
    rows = [
        _metric_row_out(
            MetricKind.STEPS,
            found.steps,
            language=language,
            theirs=theirs,
            patient=patient,
            heart_rate=None,
        ),
        _metric_row_out(
            MetricKind.HEART_RATE,
            found.heart_rate.row,
            language=language,
            theirs=theirs,
            patient=patient,
            heart_rate=found.heart_rate,
        ),
        _metric_row_out(
            MetricKind.SLEEP,
            found.sleep,
            language=language,
            theirs=theirs,
            patient=patient,
            heart_rate=None,
        ),
        _metric_row_out(
            MetricKind.WATER,
            found.water,
            language=language,
            theirs=theirs,
            patient=patient,
            heart_rate=None,
        ),
    ]
    return HealthOverviewOut(ring=ring, metrics=rows)


@router.post("/{profile_id}/metrics/{kind}", status_code=status.HTTP_201_CREATED)
async def metric_log(kind: str, body: MetricLogIn, context: Context, session: Db) -> MetricEntryOut:
    """Log one number he — or a key-holder whose scope covers readings — entered, or, for
    steps and water, log it as skipped."""
    entry = await log_metric(
        session,
        context=context,
        kind=_metric_kind(kind),
        value=body.value,
        skipped=body.skipped,
        taken_at=body.taken_at,
        episode_id=body.episode_id,
    )
    return MetricEntryOut.of(entry)


@router.get("/{profile_id}/metrics/{kind}")
async def metric_log_history(
    kind: str,
    context: Context,
    session: Db,
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
) -> list[MetricEntryOut]:
    """Every entry logged for this metric, oldest first, narrowed to `[since, until)` when
    given — the series a chart or a correlation reads."""
    found = await metric_series(
        session, context=context, kind=_metric_kind(kind), since=since, until=until
    )
    return [MetricEntryOut.of(entry) for entry in found]


@router.get("/{profile_id}/health/insights")
async def insights(context: Context, session: Db, language: str | None = Language) -> list[InsightOut]:
    """Health Insights: true cards built from his own records — nothing speculative,
    nothing diagnostic."""
    theirs, patient = await _voice(session, context)
    found = await health_insights(session, context=context, language=language, patient=patient)
    return [InsightOut.of(card) for card in found]


@router.get("/{profile_id}/medication-reminder")
async def medication_reminder(
    request: Request, context: Context, session: Db, language: str | None = Language
) -> list[MedicationReminderOut]:
    """His next doses, from his existing medicines and dose windows
    (`app.medicines.service.today`) — the untaken ones, soonest anchor first."""
    lang = await language_for(session, context, language)
    registry = providers_of(request).drug_registry
    slots = await today(session, context=context, registry=registry, language=lang)
    day = await his_day(session, context=context)
    order = ("breakfast", "lunch", "dinner", "bed")
    untaken = sorted(
        (slot for slot in slots if not slot.taken),
        key=lambda slot: (order.index(slot.anchor), slot.line.generic),
    )
    return [
        MedicationReminderOut(
            line_id=slot.line.id,
            name=PLAIN_NAME[lang][registry.monograph(slot.line.generic).plain_name_id],
            instruction=slot.card,
            anchor=slot.anchor,
            time=day.anchors[slot.anchor].strftime("%H:%M"),
            taken=slot.taken,
        )
        for slot in untaken
    ]


@router.get("/food-catalog")
async def food_catalog_list(language: str | None = Language) -> list[FoodCatalogItemOut]:
    """Common foods in Singapore and Malaysia, for a tap instead of typing."""
    return [
        FoodCatalogItemOut(id=item_id, label=label)
        for item_id, label in food_catalog(language).items()
    ]


@router.post("/{profile_id}/food", status_code=status.HTTP_201_CREATED)
async def food_add(
    body: FoodLogIn, context: Context, session: Db, language: str | None = Language
) -> FoodEntryOut:
    """Log one meal: what he ate (a catalogue id, his own words, or both) and roughly how
    much — or, `skipped=True`, that he did not have it. A tap or two; no calories, no grams."""
    entry = await log_food(
        session,
        context=context,
        meal=body.meal,
        catalog_id=body.catalog_id,
        food=body.food,
        amount=body.amount,
        skipped=body.skipped,
        eaten_at=body.eaten_at,
        episode_id=body.episode_id,
    )
    return FoodEntryOut.of(entry, meal_label=meal_label(entry.meal.value, language))


@router.get("/{profile_id}/food")
async def food_list(
    context: Context,
    session: Db,
    language: str | None = Language,
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
) -> list[FoodEntryOut]:
    """What he has logged, oldest first — the window a correlation asks for."""
    found = await food_log(session, context=context, since=since, until=until)
    return [FoodEntryOut.of(entry, meal_label=meal_label(entry.meal.value, language)) for entry in found]


__all__ = ["router"]
