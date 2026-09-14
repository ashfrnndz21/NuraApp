"""Nudge and check-in metrics (E17-05): how the cloud and the nudges are used, in counts only.

For the owner and his chief, per week on his wall: how many times he tapped the cloud, how
many of those were "Fine today" and what share that is, and for each kind of nudge how many
were handed over, accepted, dismissed, seen and ignored, with the acceptance rate; and, now,
how many of each kind in a row went ignored and which kinds are resting after two
(docs/smart-nudges.md §5, "Measures").

No health content leaves: no word he tapped, no line a nudge said, no reason, no id. The
metrics are read from the tap and nudge tables through the audited reads, so every read is on
his trail, and the metrics read itself is one more line (`audited`). The counts stay in the
region with the rest of his record; nothing here is sent to an analytics vendor.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.delivery.nudges.engine import ignored_streak, resting_kinds
from app.delivery.nudges.models import Nudge, NudgeKind, NudgeResponse, ResponseKind
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.reasoning.feelings.models import FeelingTap
from app.regions import REGION_TZ
from app.safety.red_flags import Feeling

METRICS_TARGET = "nudge_metrics"
MAX_WEEKS = 12


class NotOwnerOrChief(Refusal):
    """The nudge metrics are for the owner and his chief."""


@dataclass(slots=True)
class KindCounts:
    handed_over: int = 0
    accepted: int = 0
    dismissed: int = 0
    seen: int = 0
    ignored: int = 0

    @property
    def acceptance(self) -> float | None:
        return None if not self.handed_over else round(self.accepted / self.handed_over, 2)


@dataclass(slots=True)
class Week:
    week: str
    starts_on: date
    taps: int = 0
    fine_today: int = 0
    nudges: dict[NudgeKind, KindCounts] = field(default_factory=dict)

    @property
    def fine_share(self) -> float | None:
        return None if not self.taps else round(self.fine_today / self.taps, 2)


@dataclass(frozen=True, slots=True)
class Metrics:
    weeks: tuple[Week, ...]
    ignored_streaks: dict[NudgeKind, int]
    resting: tuple[NudgeKind, ...]
    as_of: datetime


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _week_of(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def _counts(
    nudges: Sequence[Nudge], responses: Sequence[NudgeResponse], now: datetime
) -> dict[NudgeKind, KindCounts]:
    counts = {kind: KindCounts() for kind in NudgeKind}
    for nudge in nudges:
        kinds = {r.kind for r in responses if r.nudge_id == nudge.id}
        one = counts[nudge.kind]
        one.handed_over += 1
        one.accepted += ResponseKind.ACCEPTED in kinds
        one.dismissed += ResponseKind.DISMISSED in kinds
        one.seen += ResponseKind.SEEN in kinds
        one.ignored += not kinds and as_utc(nudge.expires_at) <= now
    return counts


@audited(Action.READ, Scope.PROFILE, METRICS_TARGET)
async def nudge_metrics(session: AsyncSession, *, context: KeyContext, weeks: int = 4) -> Metrics:
    """The last `weeks` weeks, newest first, in counts. The owner's or a chief's key only."""
    if not (context.is_owner or context.role is KeyRole.CHIEF):
        raise NotOwnerOrChief("the nudge metrics are for the owner and his chief")
    weeks = max(1, min(weeks, MAX_WEEKS))
    zone = REGION_TZ[context.region]
    now = utcnow()
    this_monday = _monday(now.astimezone(zone).date())
    mondays = [this_monday - timedelta(weeks=back) for back in range(weeks)]
    start = datetime.combine(mondays[-1], time(0), zone).astimezone(UTC)

    taps = await audited_read(
        session, FeelingTap, context, Scope.RECORDS, where=(FeelingTap.tapped_at >= start,)
    )
    nudges = await audited_read(session, Nudge, context, Scope.PROFILE)
    responses = (
        await audited_read(
            session,
            NudgeResponse,
            context,
            Scope.PROFILE,
            where=(NudgeResponse.nudge_id.in_([n.id for n in nudges]),),
        )
        if nudges
        else []
    )

    table = {monday: Week(week=_week_of(monday), starts_on=monday) for monday in mondays}
    for tap in taps:
        week = table.get(_monday(as_utc(tap.tapped_at).astimezone(zone).date()))
        if week is not None:
            week.taps += 1
            week.fine_today += tap.word is Feeling.FINE
    for monday, week in table.items():
        inside = [n for n in nudges if _monday(date.fromisoformat(n.day)) == monday]
        week.nudges = _counts(inside, responses, now)

    # The metrics read itself: one more line on his trail, beside the reads it was made from.
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=Scope.PROFILE,
        target=METRICS_TARGET,
        rows=len(mondays),
    )
    return Metrics(
        weeks=tuple(table[monday] for monday in mondays),
        ignored_streaks={kind: ignored_streak(kind, nudges, responses, now) for kind in NudgeKind},
        resting=tuple(sorted(resting_kinds(nudges, responses, now=now, until=now))),
        as_of=now,
    )
