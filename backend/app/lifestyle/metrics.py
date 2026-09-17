"""Steps, heart rate, sleep and water: what he logs about his day.

design-direction.md, "Metric rows he can log": logging for steps, heart rate, sleep and water
entered by him (or a key-holder whose scope covers it), each with a value, a unit, a time, and
provenance saying he entered it. Each is a Fact of its own subject, resting on a READING
event, in the same shape and under the same scope a typed blood pressure takes
(`app.channels.api.profiles.add_reading`): CONFIRMED_BY_PERSON, confidence 1.0, provenance
that names who entered it and when.

Water and sleep are ordinary daily logs. Steps is too: what he counts through his day, a
running total, the way the water cups add up. Heart rate is a health reading, one number at a
moment, read back through the same reference-range port the lab trend uses
(`app.reasoning.ranges`) — the fixture table has no entry for it yet, so a heart-rate row
carries no band and no pill until a clinician-reviewed range is added: the honest answer is
"no range for this yet", never an invented one (docs/design-direction.md: "Do not invent
thresholds"). Nothing here invents a daily target either: Reference A's "Good" pill and
Reference B's "4,230/6,000" are read against a goal Nura has no basis to set, so a metric row
here is the number he logged, and only that.

Three states, not two (docs/recommendation-engine.md, RE-03 and the absence rule): a day is
**logged** (a number), **logged as none** — he says there is nothing to count, "I did not
drink water today" — or **not logged** at all. The engine that will read this needs to tell a
day he skipped from a day nobody asked him about; conflating them would make every pattern it
finds about those two kinds of day silently wrong. `LogStatus` carries the distinction through
the Fact (`"status"` in its value) and back out through `MetricRow`.

Automatic reading from a phone or watch is an external dependency (design-direction.md): not
built here. The seam is already in the model — `SourceChannel.DEVICE` — so a device connector
can write the same shape later without any reader of these facts changing.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import as_utc, utcnow
from app.drafts import FactDraft
from app.errors import Refusal
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.medicines.service import today_in
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, EventKind, Fact, SourceChannel
from app.memory.semantic import assert_fact, current_facts
from app.regions import REGION_TZ


class MetricKind(StrEnum):
    STEPS = "steps"
    HEART_RATE = "heart_rate"
    SLEEP = "sleep"
    WATER = "water"


class LogStatus(StrEnum):
    """The three states a day's entry can be in — never just two."""

    LOGGED = "logged"
    SKIPPED = "skipped"
    """He said there is nothing to count: no water today, no steps today. A real answer, not
    a blank — distinct from `NOT_LOGGED` so a reader downstream can tell them apart."""
    NOT_LOGGED = "not_logged"
    """Nobody has said anything about this metric for the day in question. The default when
    there is no row at all; never returned by a write, only by a read."""


@dataclass(frozen=True, slots=True)
class MetricSpec:
    subject: str
    value_key: str
    unit: str
    low: float
    high: float
    cumulative: bool
    """Whether a day's value is the sum of what he logged that day (steps, water — a running
    total, the way the water cups add up) or the latest single reading (heart rate, sleep)."""
    skippable: bool
    """Whether "none" is a meaningful answer for this metric (steps, water: yes — a day with
    no walking or no water is a real day; heart rate, sleep: no — there is no "I skipped my
    heart rate today", only "not measured", which is `NOT_LOGGED`, not a skip)."""


METRICS: Mapping[MetricKind, MetricSpec] = {
    MetricKind.STEPS: MetricSpec("steps", "count", "steps", 0, 100_000, True, True),
    # The same key and bounds a screen reading already uses (`app.ingestion.readings`), so a
    # typed pulse and a machine-screen pulse are the same fact either way.
    MetricKind.HEART_RATE: MetricSpec("heart_rate", "pulse", "/min", 20, 250, False, False),
    MetricKind.SLEEP: MetricSpec("sleep", "minutes", "min", 0, 1440, False, False),
    MetricKind.WATER: MetricSpec("water", "cups", "cups", 0, 40, True, True),
}

EVENT_LABEL: Mapping[MetricKind, str] = {
    MetricKind.STEPS: "steps",
    MetricKind.HEART_RATE: "pulse",
    MetricKind.SLEEP: "sleep",
    MetricKind.WATER: "water",
}


class NotAWholeMetric(Refusal):
    """A metric he logs is one number, in range, at a moment not later than now — or, where
    "none" means something for it, a skip and no number at all, never both."""


@dataclass(frozen=True, slots=True)
class MetricEntry:
    kind: MetricKind
    event_id: uuid.UUID
    fact_id: uuid.UUID
    status: LogStatus
    value: float | None
    unit: str
    taken_at: datetime


def _value_of(fact: Fact, spec: MetricSpec) -> tuple[LogStatus, float | None]:
    raw = fact.value
    assert isinstance(raw, dict)
    status = LogStatus(raw.get("status", LogStatus.LOGGED.value))
    if status is LogStatus.SKIPPED:
        return status, None
    return status, float(raw[spec.value_key])


async def log_metric(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: MetricKind,
    value: float | None = None,
    skipped: bool = False,
    taken_at: datetime | None = None,
    episode_id: uuid.UUID | None = None,
) -> MetricEntry:
    """Write down one number he — or a key-holder whose scope covers readings — logged, the
    way a typed blood pressure is written: the event first, then the fact naming it, on the
    same yes, so nothing here can end with a fact that names no provenance.

    `skipped=True` writes "none" as a real entry (`LogStatus.SKIPPED`) for a metric where that
    means something (steps, water); it takes no `value`, and the reverse — a value with
    `skipped=True`, or neither — is refused rather than guessed at.
    """
    spec = METRICS[kind]
    if skipped and not spec.skippable:
        raise NotAWholeMetric(f"{spec.subject} has no meaningful 'none' to log")
    if skipped and value is not None:
        raise NotAWholeMetric("a skipped entry carries no number")
    if not skipped and value is None:
        raise NotAWholeMetric(f"{spec.subject} is a number, or a skip where a skip means something")
    when = taken_at or utcnow()
    now = utcnow()
    if when > now:
        raise NotAWholeMetric(f"{spec.subject} is not later than now")
    number: int | float | None = None
    if not skipped:
        assert value is not None
        if not spec.low <= value <= spec.high:
            raise NotAWholeMetric(f"{spec.subject} is between {spec.low} and {spec.high}")
        number = int(value) if float(value).is_integer() else float(value)
    event = await record_event(
        session,
        context=context,
        kind=EventKind.READING,
        occurred_at=when,
        label=EVENT_LABEL[kind],
        source_channel=SourceChannel.APP,
        episode_id=episode_id,
    )
    status = LogStatus.SKIPPED if skipped else LogStatus.LOGGED
    fact_value: dict[str, object] = {"status": status.value}
    if not skipped:
        fact_value[spec.value_key] = number
    draft = FactDraft(
        subject=spec.subject,
        attribute="reading",
        value=fact_value,
        unit=spec.unit,
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
    return MetricEntry(
        kind=kind,
        event_id=event.id,
        fact_id=fact.id,
        status=status,
        value=None if skipped else float(number),  # type: ignore[arg-type]
        unit=spec.unit,
        taken_at=when,
    )


def _newest(facts: Sequence[Fact]) -> Fact | None:
    """The most recently logged of these facts. Ties broken by id, never by time alone — a
    "latest" query with no tie-breaker is arbitrary on a tie."""
    if not facts:
        return None
    return max(facts, key=lambda f: (as_utc(f.valid_from), str(f.id)))


@dataclass(frozen=True, slots=True)
class MetricRow:
    """One metric row: what he logged, added up his way — a running total for the day for
    steps and water, the latest reading for heart rate and sleep — and when the last entry
    behind it landed. `status` is `NOT_LOGGED` when there is nothing at all for the day,
    `SKIPPED` when the day's only word on it is "none", and `LOGGED` with a number otherwise;
    `value` is set only when `status` is `LOGGED`."""

    kind: MetricKind
    status: LogStatus
    value: float | None
    unit: str
    last_logged_at: datetime | None


async def metric_row(
    session: AsyncSession, *, context: KeyContext, kind: MetricKind, on: date | None = None
) -> MetricRow:
    spec = METRICS[kind]
    facts = await current_facts(session, context=context, subject=spec.subject)
    if not facts:
        return MetricRow(kind=kind, status=LogStatus.NOT_LOGGED, value=None, unit=spec.unit, last_logged_at=None)
    if spec.cumulative:
        zone = REGION_TZ[context.region]
        day = on or today_in(context)
        of_the_day = [f for f in facts if as_utc(f.valid_from).astimezone(zone).date() == day]
        if not of_the_day:
            return MetricRow(kind=kind, status=LogStatus.NOT_LOGGED, value=None, unit=spec.unit, last_logged_at=None)
        numeric = [f for f in of_the_day if LogStatus(f.value.get("status", "logged")) is LogStatus.LOGGED]
        newest = _newest(of_the_day)
        assert newest is not None
        if numeric:
            total = sum(float(f.value[spec.value_key]) for f in numeric)
            return MetricRow(
                kind=kind, status=LogStatus.LOGGED, value=total, unit=spec.unit,
                last_logged_at=as_utc(newest.valid_from),
            )
        # Every entry today was a skip: a real "none", not a blank.
        return MetricRow(
            kind=kind, status=LogStatus.SKIPPED, value=None, unit=spec.unit,
            last_logged_at=as_utc(newest.valid_from),
        )
    newest = _newest(facts)
    assert newest is not None
    status, value = _value_of(newest, spec)
    return MetricRow(kind=kind, status=status, value=value, unit=spec.unit, last_logged_at=as_utc(newest.valid_from))


async def metric_series(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: MetricKind,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[MetricEntry]:
    """Every entry he has logged for this metric, oldest first, narrowed to `[since, until)`
    when given — the cheap windowed read the recommendation engine's series readers ask for
    (docs/recommendation-engine.md, RE-03): "his water over the last 7 days", "has he skipped
    steps this week". Ties on the same moment broken by id."""
    spec = METRICS[kind]
    facts = await current_facts(session, context=context, subject=spec.subject)
    ordered = sorted(facts, key=lambda f: (as_utc(f.valid_from), str(f.id)))
    entries = []
    for f in ordered:
        taken_at = as_utc(f.valid_from)
        if since is not None and taken_at < since:
            continue
        if until is not None and taken_at >= until:
            continue
        status, value = _value_of(f, spec)
        entries.append(
            MetricEntry(
                kind=kind,
                event_id=f.event_id or f.id,
                fact_id=f.id,
                status=status,
                value=value,
                unit=f.unit or spec.unit,
                taken_at=taken_at,
            )
        )
    return entries


async def metric_history(
    session: AsyncSession, *, context: KeyContext, kind: MetricKind
) -> list[MetricEntry]:
    """Every entry he has logged for this metric, oldest first. `metric_series` with no
    window."""
    return await metric_series(session, context=context, kind=kind)


__all__ = [
    "EVENT_LABEL",
    "METRICS",
    "LogStatus",
    "MetricEntry",
    "MetricKind",
    "MetricRow",
    "MetricSpec",
    "NotAWholeMetric",
    "log_metric",
    "metric_history",
    "metric_row",
    "metric_series",
]
