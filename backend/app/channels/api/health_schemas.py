"""The shapes on the wire for the Health tab (Health Overview, the metric rows, Health
Insights, the medication reminder), food intake, and their strings. Kept apart from `schemas`
so this story reads in one place."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.lifestyle.food import FoodEntry, Meal
from app.lifestyle.metrics import LogStatus, MetricEntry, MetricKind, MetricRow
from app.reasoning.health_insights import Insight

# --- the ring and the metric rows (Health Overview) -----------------------------------------


class RingOut(BaseModel):
    """The ring: a real figure of his own, never a score. `kind` says which figure — doses
    taken this week, or days he checked in — `words` is "12 of 14" already said his way, and
    `label` is the plain-words line underneath saying what the number is."""

    kind: Literal["doses", "check_ins"]
    label: str
    words: str
    value: int
    total: int | None
    """None for `check_ins`: a week has no fixed number of check-ins to check against."""
    week_starts_on: date
    as_of: date


class MetricRowOut(BaseModel):
    """One row: steps, heart rate, sleep or water. `status` is one of three — logged (a
    number), skipped (he said "none", a real answer), or not logged (nothing said yet); only
    `LOGGED` carries a `value`. `range_known` is set only for heart rate: whether a
    reference range exists to place it against at all (it does not, today) — never a made-up
    band."""

    kind: MetricKind
    label: str
    status: LogStatus
    value: float | None
    value_words: str | None
    unit: str
    last_logged_at: datetime | None
    status_words: str
    range_known: bool | None = None
    range_words: str | None = None


class HealthOverviewOut(BaseModel):
    ring: RingOut
    metrics: list[MetricRowOut]


# --- logging a metric --------------------------------------------------------------------


class MetricLogIn(BaseModel):
    """A number he logged, or — for steps and water, where "none" means something — a skip.
    Exactly one of `value` and `skipped=True`, never both, never neither."""

    value: float | None = Field(default=None, ge=0, le=100_000)
    skipped: bool = False
    taken_at: AwareDatetime | None = None
    episode_id: uuid.UUID | None = None


class MetricEntryOut(BaseModel):
    event_id: uuid.UUID
    fact_id: uuid.UUID
    kind: MetricKind
    status: LogStatus
    value: float | None
    unit: str
    taken_at: datetime

    @classmethod
    def of(cls, entry: MetricEntry) -> MetricEntryOut:
        return cls(
            event_id=entry.event_id,
            fact_id=entry.fact_id,
            kind=entry.kind,
            status=entry.status,
            value=entry.value,
            unit=entry.unit,
            taken_at=entry.taken_at,
        )


# --- Health Insights -------------------------------------------------------------------------


class InsightOut(BaseModel):
    kind: str
    headline: str
    detail: str

    @classmethod
    def of(cls, insight: Insight) -> InsightOut:
        return cls(kind=insight.kind, headline=insight.headline, detail=insight.detail)


# --- Medication Reminder -----------------------------------------------------------------


class MedicationReminderOut(BaseModel):
    """One of his next doses, read from his medicines and dose windows
    (`app.medicines.service.today`) — nothing here duplicates that logic."""

    line_id: uuid.UUID
    name: str
    instruction: str
    anchor: str
    time: str
    """His wall-clock time for this anchor today, "07:30" — a real time, not the anchor's
    name alone."""
    taken: bool


# --- food intake -------------------------------------------------------------------------


class FoodCatalogItemOut(BaseModel):
    id: str
    label: str


class FoodLogIn(BaseModel):
    """One thing he ate: a catalogue id, his own words, or both — or, `skipped=True`, "I did
    not have this meal", a real answer that names none of those."""

    meal: Meal
    catalog_id: str | None = None
    food: str | None = Field(default=None, min_length=1, max_length=80)
    amount: str | None = Field(default=None, min_length=1, max_length=80)
    skipped: bool = False
    eaten_at: AwareDatetime | None = None
    episode_id: uuid.UUID | None = None


class FoodEntryOut(BaseModel):
    event_id: uuid.UUID
    fact_id: uuid.UUID
    meal: Meal
    meal_label: str
    status: LogStatus
    catalog_id: str | None
    food: str | None
    amount: str | None
    eaten_at: datetime

    @classmethod
    def of(cls, entry: FoodEntry, *, meal_label: str) -> FoodEntryOut:
        return cls(
            event_id=entry.event_id,
            fact_id=entry.fact_id,
            meal=entry.meal,
            meal_label=meal_label,
            status=entry.status,
            catalog_id=entry.catalog_id,
            food=entry.food,
            amount=entry.amount,
            eaten_at=entry.eaten_at,
        )


__all__ = [
    "FoodCatalogItemOut",
    "FoodEntryOut",
    "FoodLogIn",
    "HealthOverviewOut",
    "InsightOut",
    "MedicationReminderOut",
    "MetricEntryOut",
    "MetricLogIn",
    "MetricRowOut",
    "RingOut",
]
