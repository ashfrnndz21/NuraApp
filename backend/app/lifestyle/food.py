"""Food intake: what he ate, roughly how much, when, and which meal.

Not logged anywhere in Nura before this. The owner's addition to scope: Nura is building
toward personalised recommendations that read his medicines, his readings, his routines and
what he ate together — a recommendation engine will correlate food with a medicine ("take
with food"; food interactions such as grapefruit, vitamin K with warfarin, potassium) — so
this module builds the record, in the shape the rest of the system already uses for a
provenanced fact, and makes it cheap to ask "what did he eat around this moment". It does not
judge, score or advise on what he ate: that is the engine's job, and anything clinical about
food goes through the review queue like everything else that reasons about him.

**The shape follows docs/recommendation-engine.md §2.7 exactly**, since RE-10 (the engine's
meal, steps, sleep, water and heart-rate series) reads this module's rows directly and cannot
start until they land:

1. Every entry is an Event (`EventKind.FOOD`), with a Fact resting on it. `occurred_at` is
   when the meal happened on his day, not when it was typed.
2. Meals are one Fact per meal slot: `subject="meal"`, `attribute` is the meal itself —
   `"breakfast" | "lunch" | "dinner" | "snack"` — never a fixed attribute with the meal
   folded into the value. The value holds what he said, plus `"had": true | false`.
   **"No breakfast" is an entry** (`had: false`), not a missing one.
3. Nothing is inferred at write time: no "healthy meal" flag, no score.

Three states, not two (the absence rule): a meal is **logged** (`had: true`, what he ate),
**logged as skipped** (`had: false` — "I did not have breakfast", a real one-tap answer), or
**not logged** at all, because no Fact for that meal that day exists yet. `LogStatus`
(`app.lifestyle.metrics`) is the same three states, reused here so both logs answer "logged,
skipped, or nothing said" the same way; `had` is the wire form §2.7 asks for, and `status` is
read back from it, never stored twice.

**Where this sits under a key's scope.** Meals are read and written under readings
(`Scope.READINGS`, `app.keys.scopes.scope_for_subject("meal")`), the owner's deliberate call
(2026-09-17, made after weighing it against keeping meals under the general record so a
helper could not see them): whoever checks on him day to day can see whether he has eaten, a
helper included. The scope lives in one place — `_SUBJECT_SCOPES` in `app.keys.scopes`, and
the matching event scope in `app.memory.episodic.EVENT_SCOPES` — so changing it, either way,
is those two lines and nothing in this file.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.health_strings import CATALOG_IDS
from app.db import as_utc, utcnow
from app.drafts import FactDraft
from app.errors import Refusal
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.lifestyle.metrics import LogStatus
from app.medicines.service import today_in
from app.memory.episodic import record_event
from app.memory.models import (
    LABEL_LENGTH,
    ConfidenceState,
    EventKind,
    Fact,
    SourceChannel,
    short_label,
)
from app.memory.semantic import assert_fact, current_facts
from app.regions import REGION_TZ

MEAL_SUBJECT = "meal"
AMOUNT_LENGTH = LABEL_LENGTH


class Meal(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class NotAFoodEntry(Refusal):
    """A food entry names what he ate — a catalogue item, his own words, or both — and is not
    later than now; a skipped entry (`had: false`) names none of those, and only those."""


@dataclass(frozen=True, slots=True)
class FoodEntry:
    event_id: uuid.UUID
    fact_id: uuid.UUID
    meal: Meal
    status: LogStatus
    catalog_id: str | None
    food: str | None
    amount: str | None
    eaten_at: datetime


def _value_of(fact: Fact) -> dict[str, object]:
    value = fact.value
    assert isinstance(value, dict)
    return value


async def log_food(
    session: AsyncSession,
    *,
    context: KeyContext,
    meal: Meal,
    catalog_id: str | None = None,
    food: str | None = None,
    amount: str | None = None,
    skipped: bool = False,
    eaten_at: datetime | None = None,
    episode_id: uuid.UUID | None = None,
) -> FoodEntry:
    """Write down one thing he ate — or a key-holder whose scope covers readings logged for
    him — the way a metric log is written: the event first, the fact naming it, one yes.

    Simple enough for a tap or two: a catalogue id from `app.channels.health_strings.
    food_catalog`, his own words, or both (free entry beside the catalogue, never one without
    the other's option). No calorie count and no gram weight are asked for or accepted.

    `skipped=True` — "I did not have breakfast" — is a real, one-tap answer for the meal
    (written as `had: false`, docs/recommendation-engine.md §2.7), not a blank: it takes no
    catalogue id, no food and no amount, and the reverse (any of those given with
    `skipped=True`) is refused rather than guessed at.
    """
    if skipped and (catalog_id is not None or food is not None or amount is not None):
        raise NotAFoodEntry("a skipped meal names nothing he ate")
    if not skipped:
        if catalog_id is not None and catalog_id not in CATALOG_IDS:
            raise NotAFoodEntry(f"no such food on the catalogue: {catalog_id!r}")
        if catalog_id is None and not (food and food.strip()):
            raise NotAFoodEntry("a food entry names what he ate, or is logged as skipped")
    when = eaten_at or utcnow()
    if when > utcnow():
        raise NotAFoodEntry("a meal is not later than now")
    named_food = short_label(food) if food else None
    named_amount = short_label(amount) if amount else None
    event = await record_event(
        session,
        context=context,
        kind=EventKind.FOOD,
        occurred_at=when,
        label=meal.value,
        source_channel=SourceChannel.APP,
        episode_id=episode_id,
    )
    value: dict[str, object] = {"had": not skipped}
    if not skipped:
        value.update({"catalog_id": catalog_id, "food": named_food, "amount": named_amount})
    draft = FactDraft(
        subject=MEAL_SUBJECT,
        attribute=meal.value,
        value=value,
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=episode_id,
        supersedes_id=None,
    )
    yes = await confirm(session, context, draft)
    fact = await assert_fact(
        session,
        context=context,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        unit=draft.unit,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        event_id=event.id,
        episode_id=episode_id,
        valid_from=when,
    )
    return _entry_of(fact)


def _entry_of(fact: Fact) -> FoodEntry:
    value = _value_of(fact)
    had = bool(value.get("had", True))
    return FoodEntry(
        event_id=fact.event_id or fact.id,
        fact_id=fact.id,
        meal=Meal(fact.attribute),
        status=LogStatus.LOGGED if had else LogStatus.SKIPPED,
        catalog_id=value.get("catalog_id"),
        food=value.get("food"),
        amount=value.get("amount"),
        eaten_at=as_utc(fact.valid_from),
    )


async def food_log(
    session: AsyncSession,
    *,
    context: KeyContext,
    meal: Meal | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[FoodEntry]:
    """What he has logged, oldest first, ties on the same moment broken by id — narrowed to
    one meal slot, or to `[since, until)`, when given: the range a correlation asks for
    ("what did he eat around this reading", "has he eaten before this dose")."""
    facts = await current_facts(
        session, context=context, subject=MEAL_SUBJECT, attribute=meal.value if meal else None
    )
    entries = [_entry_of(f) for f in facts]
    if since is not None:
        entries = [e for e in entries if e.eaten_at >= since]
    if until is not None:
        entries = [e for e in entries if e.eaten_at < until]
    return sorted(entries, key=lambda e: (e.eaten_at, str(e.fact_id)))


async def food_around(
    session: AsyncSession, *, context: KeyContext, moment: datetime, before: int, after: int
) -> list[FoodEntry]:
    """What he ate from `before` hours before `moment` to `after` hours after it — the shape
    a food-medicine or food-reading correlation reads ("has he eaten before this dose")."""
    return await food_log(
        session,
        context=context,
        since=moment - timedelta(hours=before),
        until=moment + timedelta(hours=after),
    )


async def meal_status_on(
    session: AsyncSession, *, context: KeyContext, meal: Meal, on: datetime | None = None
) -> LogStatus:
    """Logged, skipped, or nothing said, for one meal on his day (the day `on` falls on, his
    own if `on` is not given) — the cheap per-day series read a correlation like "compare his
    readings on days he had breakfast against days he skipped it" starts from
    (docs/recommendation-engine.md §2.7, "answered_days"). The newest entry for that meal that
    day wins, ties on the same moment broken by id, same as every other "latest" read here."""
    zone = REGION_TZ[context.region]
    day = (as_utc(on).astimezone(zone).date()) if on is not None else today_in(context)
    entries = await food_log(session, context=context, meal=meal)
    of_the_day = [e for e in entries if e.eaten_at.astimezone(zone).date() == day]
    if not of_the_day:
        return LogStatus.NOT_LOGGED
    newest = max(of_the_day, key=lambda e: (e.eaten_at, str(e.fact_id)))
    return newest.status


__all__ = [
    "AMOUNT_LENGTH",
    "MEAL_SUBJECT",
    "FoodEntry",
    "Meal",
    "NotAFoodEntry",
    "food_around",
    "food_log",
    "log_food",
    "meal_status_on",
]
