"""The smart nudge engine (E17-03, E11-07): the day's nudges, worked out from how he is.

`plan_nudges` reads State and the record under the caller's key and makes a `NudgeDraft` for
each kind that has something true to say that day:

- **Anticipation**: a visit on the spine the next day — who, which day, and to bring his
  blood pressure book (or his tablets, when he keeps no blood pressure numbers).
- **Check-in**: the feeling question, at his check-in time, after a change he has not
  answered on the cloud since (a new medicine, the week after a discharge, a direction in his
  blood pressure), or a week after a note Nura said it would ask again about.
- **Pattern**: his morning tablets taken every day, or most days, this week.
- **Commitment**: something he said at a visit, quoted in his own words from the memo
  (E11-07; memos come from `handoff.commitment_sources`), and "How did it go today?".
- **Recognition**: the number that only goes up moved since it was last said.
- **Presence**: someone in his family wrote today; or, in a quiet week, that Nura is here.

Then the rules (docs/smart-nudges.md §1 and §4; E17-03), in this order, every one visible in
the plan's `held` rather than applied in silence:

1. **None on a day with a red flag.** A flag raised on that day of his holds every nudge.
2. **Never at night.** A nudge goes no earlier than his check-in time and never inside the
   quiet hours (21:00 to 07:00 on his wall, `app.delivery.feed.rank`); a plan made for today
   after the quiet hours begin has nothing left to send.
3. **One a day, by delivery's cap.** As many go as E11's cap on nudges allows that day
   (`caps.nudge` in the delivery settings, one unless the family sets it: `daily_cap`),
   less those already handed over; the rest are held, "one_a_day". The engine sends by the
   same cap (`app.delivery.triggers`), so one number says how many nudges reach him a day.
4. **A kind he ignored twice rests for a week.** Two of a kind handed over and never touched
   before they expired, and that kind is held for seven days from the second.
5. **Dismissals feed ranking.** Every "Not today" on a kind in the last week moves that kind
   down the day's order.
6. **One reminder of a visit a day.** On a day the visit's logistics card (E05-03) is already
   on his feed, the anticipation nudge would say it again: it is held, "logistics_card_says_it".

The order itself is State's (docs/smart-nudges.md §1): after a change, the check-in and the
pattern come first; in a steady week, recognition and presence do. A visit tomorrow comes
before either. No nudge scolds, counts what was not done, or sets a target: the templates
(`strings`) have no such line, and a commitment is his own words and nothing added.

`hand_over` writes the chosen draft down (`Nudge`, rendered from State) and gives it to
delivery (`handoff.deliveries`, E11's). Nothing here sends anything. `respond` writes down
what he did with one.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import (
    audited,
    audited_profile_read,
    audited_read,
    audited_write,
    person_display_name,
)
from app.audit.models import Action
from app.db import as_utc, utcnow
from app.delivery.feed.models import CapsClass, CardType, FeedItem
from app.delivery.feed.rank import QUIET_FROM, QUIET_UNTIL, in_quiet_hours
from app.delivery.nudges import strings as said
from app.delivery.nudges.handoff import (
    Commitment,
    Held,
    NudgeDraft,
    NudgePlan,
    commitment_sources,
    deliveries,
)
from app.delivery.nudges.models import Nudge, NudgeKind, NudgeResponse, ResponseKind
from app.delivery.strings import FEELINGS
from app.delivery.triggers.models import TriggerType
from app.delivery.triggers.preferences import daily_cap
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.family.models import ThreadMessage
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.models import DoseTaken
from app.medicines.service import proud_days
from app.medicines.strings import say_date
from app.memory.episodic import record_event
from app.memory.models import EventKind, SourceChannel
from app.onboarding.settings import clocks_said
from app.reasoning.feelings.cloud import lead_for, weigh
from app.reasoning.feelings.models import FeelingNote, NoteOutcome
from app.reasoning.feelings.record import Situation, read_situation
from app.reasoning.feelings.strings import language_of
from app.reasoning.feelings.words import CHANGES
from app.regions import REGION_TZ
from app.safety.boundary import YOUR_DOCTOR
from app.safety.plain_words import verify
from app.safety.red_flags import Flag
from app.state.models import Posture
from app.state.service import RECOMPUTE_SCOPES, render_from_state

NUDGE = Nudge.__tablename__

CHECK_IN_AT = time(10, 0)
"""His check-in time when he has not said one: after breakfast, well inside his day."""
MORNING_ANCHOR = "breakfast"
IGNORED_TO_REST = 2
REST = timedelta(days=7)
"""Two of a kind ignored, and that kind rests for a week (E17-03)."""
DISMISSAL_WINDOW = timedelta(days=7)
DISMISSAL_STEP = 15
"""How far one "Not today" moves a kind down the day's order."""
WATCH_AGAIN = timedelta(days=7)
"""A note that said "Nura will ask you again in a week" comes back as a check-in."""
CHANGE_WEEK = timedelta(days=7)
PATTERN_DAYS = 7
PATTERN_AT_LEAST = 5
HISTORY = timedelta(days=21)

CHANGED_WEEK: Mapping[NudgeKind, int] = {
    NudgeKind.ANTICIPATION: 100,
    NudgeKind.CHECK_IN: 90,
    NudgeKind.PATTERN: 80,
    NudgeKind.COMMITMENT: 70,
    NudgeKind.RECOGNITION: 60,
    NudgeKind.PRESENCE: 50,
}
STEADY_WEEK: Mapping[NudgeKind, int] = {
    NudgeKind.ANTICIPATION: 100,
    NudgeKind.RECOGNITION: 90,
    NudgeKind.PRESENCE: 80,
    NudgeKind.COMMITMENT: 70,
    NudgeKind.PATTERN: 60,
    NudgeKind.CHECK_IN: 50,
}
"""State ranks the kinds (docs/smart-nudges.md §1): after a change, check-in and pattern
first; in a steady week, presence and recognition first. A visit tomorrow leads both."""

SCOPE_OF: Mapping[NudgeKind, Scope] = {
    NudgeKind.ANTICIPATION: Scope.VISITS,
    NudgeKind.CHECK_IN: Scope.RECORDS,
    NudgeKind.PATTERN: Scope.MEDICINES,
    NudgeKind.COMMITMENT: Scope.VISITS,
    NudgeKind.RECOGNITION: Scope.MEDICINES,
    NudgeKind.PRESENCE: Scope.FAMILY,
}

PLAN_SCOPES: frozenset[Scope] = RECOMPUTE_SCOPES | {Scope.EMERGENCY}
"""A plan is rendered from State and must see the day's flags: the owner's key, or a chief's."""


class NotAPlanDay(Refusal):
    """A plan is for today or a day still to come."""


class NoSuchNudge(Refusal):
    """No nudge by that id on this profile that this key can see."""


class NothingToHandOver(Refusal):
    """The plan for that day has no nudge to hand over. Its `held` says why."""


def _local(moment: datetime, context: KeyContext) -> datetime:
    return as_utc(moment).astimezone(REGION_TZ[context.region])


def _at(day: date, clock: time, context: KeyContext) -> datetime:
    """That moment of that day on his wall, as UTC: every stored moment and every bound a
    query compares is UTC, as everywhere else in Nura (`app.db.utcnow`)."""
    return datetime.combine(day, clock, REGION_TZ[context.region]).astimezone(UTC)


def _ignored(nudge: Nudge, responses: Sequence[NudgeResponse], now: datetime) -> bool:
    """Handed over, stopped being worth sending, and nobody did anything with it."""
    return as_utc(nudge.expires_at) <= now and not any(r.nudge_id == nudge.id for r in responses)


def resting_kinds(
    nudges: Sequence[Nudge], responses: Sequence[NudgeResponse], *, now: datetime, until: datetime
) -> dict[NudgeKind, datetime]:
    """Each kind resting at `until`, and the moment its rest ends: its last two were ignored."""
    resting: dict[NudgeKind, datetime] = {}
    for kind in NudgeKind:
        mine = sorted(
            (n for n in nudges if n.kind is kind),
            key=lambda n: as_utc(n.handed_over_at),
            reverse=True,
        )[:IGNORED_TO_REST]
        if len(mine) == IGNORED_TO_REST and all(_ignored(n, responses, now) for n in mine):
            ends = as_utc(mine[0].expires_at) + REST
            if ends > until:
                resting[kind] = ends
    return resting


def ignored_streak(
    kind: NudgeKind, nudges: Sequence[Nudge], responses: Sequence[NudgeResponse], now: datetime
) -> int:
    """How many of the latest nudges of this kind, one after another, were ignored."""
    count = 0
    for nudge in sorted(
        (n for n in nudges if n.kind is kind), key=lambda n: as_utc(n.handed_over_at), reverse=True
    ):
        if not _ignored(nudge, responses, now):
            break
        count += 1
    return count


QUOTED_LINE = 1
"""In a commitment, the line that is his own words from the memo: verified where the memo was
written (E05) and quoted as it is here, never re-worded to pass again."""


def _verified(draft: NudgeDraft, code: str) -> bool:
    """Every line the templates wrote passes plain words; his quoted words are his."""
    ours = [
        line
        for index, line in enumerate(draft.lines)
        if not (draft.kind is NudgeKind.COMMITMENT and index == QUOTED_LINE)
    ]
    found = [
        f for line in (*ours, draft.why) for f in verify(line, code, "line") if f.severity == "fail"
    ]
    return not found


class _Planner:
    """One plan being made: the day, the record as read, what came before."""

    def __init__(
        self,
        *,
        context: KeyContext,
        situation: Situation,
        day: date,
        code: str,
        send_after: datetime,
        nudges: Sequence[Nudge],
    ) -> None:
        self.context = context
        self.situation = situation
        self.day = day
        self.code = code
        self.send_after = send_after
        self.expires_at = _at(day + timedelta(days=1), time(0), context)
        self.nudges = nudges
        assert situation.state is not None
        self.state_id = situation.state.id

    def draft(
        self,
        kind: NudgeKind,
        lines: Sequence[str],
        why: str,
        reason: dict[str, Any],
        *,
        key: str,
        memo_id: uuid.UUID | None = None,
    ) -> NudgeDraft:
        shown = tuple(line[:1].upper() + line[1:] for line in lines)
        return NudgeDraft(
            kind=kind,
            lines=shown,
            voice=shown,
            language=self.code,
            why=why,
            reason=reason,
            cap_class=CapsClass.ONE,
            scope=SCOPE_OF[kind],
            day=self.day,
            send_after=self.send_after,
            expires_at=self.expires_at,
            state_id=self.state_id,
            priority=0,
            dedupe_key=f"{kind.value}:{key}:{self.day.isoformat()}",
            memo_id=memo_id,
        )

    def last_of(self, kind: NudgeKind) -> Nudge | None:
        mine = [n for n in self.nudges if n.kind is kind]
        return max(mine, key=lambda n: as_utc(n.handed_over_at), default=None)


def changed_this_week(situation: Situation) -> tuple[bool, list[Any]]:
    """Whether State moved this week — a change behind the cloud, or a posture off steady."""
    week_ago = situation.now - CHANGE_WEEK
    changes = [
        reason
        for item in weigh(situation)
        for reason in item.reasons
        if reason.code in CHANGES and reason.since is not None and as_utc(reason.since) > week_ago
    ]
    posture = situation.state.posture if situation.state is not None else Posture.STABLE
    return bool(changes) or posture is not Posture.STABLE, changes


async def _anticipation(p: _Planner) -> NudgeDraft | None:
    visit = p.situation.next_visit
    if visit is None or _local(visit.at, p.context).date() != p.day + timedelta(days=1):
        return None
    table = said.LINES[p.code]
    bring = "anticipation_book" if p.situation.readings else "anticipation_tablets"
    lines = [
        table["anticipation"][0].format(
            doctor=visit.doctor or YOUR_DOCTOR[p.code],
            day=say_date(p.day + timedelta(days=1), p.code),
        ),
        *table[bring],
    ]
    reason = {"code": "visit_tomorrow", "appointment_id": str(visit.appointment_id)}
    return p.draft(
        NudgeKind.ANTICIPATION,
        lines,
        said.WHY[p.code]["anticipation"],
        reason,
        key=str(visit.appointment_id),
    )


async def _check_in(p: _Planner, session: AsyncSession, changes: list[Any]) -> NudgeDraft | None:
    last_tap = p.situation.last_tap_at
    newest = max((as_utc(c.since) for c in changes if c.since is not None), default=None)
    table = said.LINES[p.code]
    if newest is not None and (last_tap is None or newest > last_tap):
        lead = lead_for(weigh(p.situation), p.situation, p.context, p.code)
        lines = [*((lead,) if lead else ()), *table["check_in"]]
        change = max(changes, key=lambda c: as_utc(c.since or p.situation.now))
        reason = {"code": "state_change", "change": change.code.value, **change.ids}
        return p.draft(
            NudgeKind.CHECK_IN, lines, said.WHY[p.code]["check_in"], reason, key="change"
        )
    watched = await audited_read(
        session,
        FeelingNote,
        p.context,
        Scope.RECORDS,
        where=(
            FeelingNote.outcome == NoteOutcome.WATCH,
            FeelingNote.created_at <= p.situation.now - WATCH_AGAIN,
            FeelingNote.created_at > p.situation.now - WATCH_AGAIN * 2,
        ),
        order_by=(FeelingNote.created_at.desc(),),
    )
    for note in watched:
        if last_tap is not None and last_tap > as_utc(note.created_at) + WATCH_AGAIN:
            continue
        feeling = FEELINGS[p.code].get(note.word.value)
        if feeling is None:
            continue
        lines = [table["check_in_watched"][0].format(feeling=feeling), *table["check_in"]]
        reason = {"code": "watched", "note_id": str(note.id)}
        return p.draft(
            NudgeKind.CHECK_IN,
            lines,
            said.WHY[p.code]["check_in_watched"],
            reason,
            key=str(note.id),
        )
    return None


async def _pattern(p: _Planner, session: AsyncSession) -> NudgeDraft | None:
    if not p.context.allows(Scope.MEDICINES):
        return None
    start = _at(p.day - timedelta(days=PATTERN_DAYS), time(0), p.context)
    end = _at(p.day, time(0), p.context)
    taps = await audited_read(
        session,
        DoseTaken,
        p.context,
        Scope.MEDICINES,
        where=(
            DoseTaken.taken_at >= start,
            DoseTaken.taken_at < end,
            DoseTaken.anchor == MORNING_ANCHOR,
        ),
    )
    days = len({_local(tap.taken_at, p.context).date() for tap in taps})
    if days < PATTERN_AT_LEAST:
        return None
    table = said.LINES[p.code]
    lines = (
        table["pattern_every"]
        if days == PATTERN_DAYS
        else tuple(line.format(count=days) for line in table["pattern_some"])
    )
    reason = {"code": "morning_taken", "days": days, "of": PATTERN_DAYS}
    return p.draft(NudgeKind.PATTERN, lines, said.WHY[p.code]["pattern"], reason, key="mornings")


async def _recognition(p: _Planner, session: AsyncSession) -> NudgeDraft | None:
    if not p.context.allows(Scope.MEDICINES):
        return None
    counted = await proud_days(session, context=p.context)
    last = p.last_of(NudgeKind.RECOGNITION)
    was = int(last.reason.get("days", 0)) if last is not None else 0
    if counted.days < 1 or counted.days <= was:
        return None
    reason = {"code": "proud_moved", "days": counted.days, "was": was}
    lines = said.recognition_lines(counted.days, p.code)
    return p.draft(
        NudgeKind.RECOGNITION, lines, said.WHY[p.code]["recognition"], reason, key=str(counted.days)
    )


async def _commitment(p: _Planner, session: AsyncSession) -> NudgeDraft | None:
    heard: list[Commitment] = []
    for source in commitment_sources:
        heard.extend(await source(session, context=p.context))
    # A memo is quoted once, ever: the feed already carries the memo card, and a nudge that
    # came back to the same words would be a reminder, not his own words said back once.
    quoted: set[uuid.UUID] = set()
    if heard:
        already = await audited_read(
            session,
            Nudge,
            p.context,
            Scope.PROFILE,
            where=(Nudge.memo_id.in_([c.memo_id for c in heard]),),
        )
        quoted = {n.memo_id for n in already if n.memo_id is not None}
    for commitment in sorted(heard, key=lambda c: as_utc(c.said_at), reverse=True):
        if commitment.memo_id in quoted or not commitment.words.strip():
            continue
        table = said.LINES[p.code]
        # His words, exactly as the memo holds them: nothing rephrased, nothing added.
        lines = [*table["commitment_said"], commitment.words.strip(), *table["commitment_ask"]]
        reason = {"code": "memo", "memo_id": str(commitment.memo_id)}
        return p.draft(
            NudgeKind.COMMITMENT,
            lines,
            said.WHY[p.code]["commitment"],
            reason,
            key=str(commitment.memo_id),
            memo_id=commitment.memo_id,
        )
    return None


async def _presence(p: _Planner, session: AsyncSession, *, steady: bool) -> NudgeDraft | None:
    table, whys = said.LINES[p.code], said.WHY[p.code]
    today = _local(p.situation.now, p.context).date()
    if p.day == today and p.context.allows(Scope.FAMILY):
        start = _at(today, time(0), p.context)
        posted = await audited_read(
            session,
            ThreadMessage,
            p.context,
            Scope.FAMILY,
            where=(ThreadMessage.posted_at >= start, ThreadMessage.text.is_not(None)),
            order_by=(ThreadMessage.posted_at.desc(),),
        )
        for message in posted:
            if message.author_person_id == p.context.person_id:
                continue
            name = await person_display_name(session, p.context, message.author_person_id)
            if not name:
                continue
            lines = [line.format(name=name) for line in table["presence_family"]]
            reason = {"code": "family_wrote", "message_id": str(message.id)}
            return p.draft(
                NudgeKind.PRESENCE,
                lines,
                whys["presence_family"].format(name=name),
                reason,
                key="family",
            )
    last = p.last_of(NudgeKind.PRESENCE)
    if steady and (last is None or as_utc(last.handed_over_at) <= p.situation.now - REST):
        reason = {"code": "quiet_week"}
        return p.draft(
            NudgeKind.PRESENCE, table["presence_here"], whys["presence_here"], reason, key="here"
        )
    return None


async def check_in_time(session: AsyncSession, *, context: KeyContext) -> time:
    """His check-in time from his settings (E01, `app.onboarding.settings`: `checkin_time`,
    written as the fact `setting.checkin_time`, "HH:MM" on his region's clock), or
    `CHECK_IN_AT`. A time inside the quiet hours is not one a nudge may go at: the default
    stands."""
    at = (await clocks_said(session, context=context)).checkin
    if at is None or not QUIET_UNTIL <= at < QUIET_FROM:
        return CHECK_IN_AT
    return at


def _send_after(
    day: date, today: date, now: datetime, context: KeyContext, at: time = CHECK_IN_AT
) -> datetime | None:
    """The earliest a nudge may go that day, or None when what is left of the day is night."""
    earliest = _at(day, at, context)
    if day == today:
        earliest = max(earliest, _local(now, context))
    local = _local(earliest, context)
    if in_quiet_hours(local):
        if local.time() >= QUIET_FROM:
            return None
        earliest = _at(day, QUIET_UNTIL, context)
    return earliest.astimezone(UTC)


@audited(Action.READ, Scope.RECORDS, NUDGE)
async def _logistics_cards(
    session: AsyncSession, *, context: KeyContext, day: date
) -> dict[str, str]:
    """The visits whose logistics card (`CardType.VISIT_LOGISTICS`) is on his feed on `day`, by
    appointment id, to the card's id. Read under the visits scope, the card's own; a key that
    does not reach the visits sees no card, and holds nothing for one."""
    if not context.allows(Scope.VISITS):
        return {}
    cards = await audited_read(
        session,
        FeedItem,
        context,
        Scope.VISITS,
        where=(FeedItem.type == CardType.VISIT_LOGISTICS, FeedItem.day == day.isoformat()),
    )
    prefix = "logistics:"
    return {
        card.dedupe_key.removeprefix(prefix).rsplit(":", 1)[0]: str(card.id)
        for card in cards
        if card.dedupe_key.startswith(prefix)
    }


async def plan_nudges(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    day: date | None = None,
) -> NudgePlan:
    """The nudges for `day` (today by default) on his wall: at most one to go, the rest held
    with the reason. Nothing is written; `hand_over` writes the one that goes."""
    for scope in sorted(PLAN_SCOPES):
        context.require(scope)
    now = utcnow()
    today = _local(now, context).date()
    day = day or today
    if day < today:
        raise NotAPlanDay("a plan is for today or a day to come")
    code = language_of((await audited_profile_read(session, context)).language)
    day_start, day_end = _at(day, time(0), context), _at(day + timedelta(days=1), time(0), context)

    flags = await audited_read(
        session,
        Flag,
        context,
        Scope.EMERGENCY,
        where=(Flag.raised_at >= day_start, Flag.raised_at < day_end),
    )
    if any(flag.suppressed_because is None for flag in flags):
        return NudgePlan(day=day, drafts=(), held=(), none_because="red_flag")
    send_after = _send_after(
        day, today, now, context, await check_in_time(session, context=context)
    )
    if send_after is None:
        return NudgePlan(day=day, drafts=(), held=(), none_because="night")

    nudges = list(
        await audited_read(
            session, Nudge, context, Scope.PROFILE, where=(Nudge.handed_over_at > now - HISTORY,)
        )
    )
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
    situation = await read_situation(session, context=context, registry=registry)
    planner = _Planner(
        context=context,
        situation=situation,
        day=day,
        code=code,
        send_after=send_after,
        nudges=nudges,
    )
    changed, changes = changed_this_week(situation)
    order = CHANGED_WEEK if changed else STEADY_WEEK

    made: list[NudgeDraft] = []
    for built in (
        await _anticipation(planner),
        await _check_in(planner, session, changes),
        await _pattern(planner, session),
        await _commitment(planner, session),
        await _recognition(planner, session),
        await _presence(planner, session, steady=not changed),
    ):
        if built is not None:
            made.append(built)

    held: list[Held] = []
    # One reminder of a visit a day (E05-03): on a day the visit's logistics card is already
    # on his feed — who, which day, where, what to bring — the anticipation nudge would say it
    # again, so it is held, and says why. With no card made yet that day it goes as before.
    carded = await _logistics_cards(session, context=context, day=day)
    resting = resting_kinds(nudges, responses, now=now, until=send_after)
    dismissed: dict[NudgeKind, int] = {}
    by_id = {n.id: n for n in nudges}
    for response in responses:
        if response.kind is ResponseKind.DISMISSED and as_utc(response.at) > now - DISMISSAL_WINDOW:
            kind = by_id[response.nudge_id].kind
            dismissed[kind] = dismissed.get(kind, 0) + 1
    ranked: list[NudgeDraft] = []
    for draft in made:
        priority = order[draft.kind] - DISMISSAL_STEP * dismissed.get(draft.kind, 0)
        draft = replace(draft, priority=priority)
        if draft.kind is NudgeKind.ANTICIPATION and draft.reason.get("appointment_id") in carded:
            held.append(
                Held(
                    draft.kind,
                    "logistics_card_says_it",
                    priority,
                    {**draft.reason, "feed_item_id": carded[str(draft.reason["appointment_id"])]},
                )
            )
        elif draft.kind in resting:
            held.append(
                Held(
                    draft.kind,
                    "resting_after_two_ignored",
                    priority,
                    {"until": resting[draft.kind].isoformat()},
                )
            )
        elif not _verified(draft, code):
            held.append(Held(draft.kind, "not_plain_words", priority, dict(draft.reason)))
        else:
            ranked.append(draft)
    # A draft already handed over is not offered again: under a cap above one, the next goes.
    handed = {n.dedupe_key for n in nudges}
    ranked = [d for d in ranked if d.dedupe_key not in handed]
    ranked.sort(key=lambda d: (-d.priority, d.kind.value))
    already = [n for n in nudges if n.day == day.isoformat()]
    cap = await daily_cap(session, context=context, type=TriggerType.NUDGE)
    room = len(ranked) if cap is None else max(0, cap - len(already))
    going = tuple(ranked[:room])
    for draft in ranked[room:]:
        held.append(Held(draft.kind, "one_a_day", draft.priority, dict(draft.reason)))
    return NudgePlan(day=day, drafts=going, held=tuple(held))


async def hand_over(
    session: AsyncSession, *, context: KeyContext, registry: DrugRegistry, day: date | None = None
) -> tuple[NudgePlan, Nudge]:
    """Plan the day, write down the one that goes, and give it to delivery. Sends nothing."""
    plan = await plan_nudges(session, context=context, registry=registry, day=day)
    if not plan.drafts:
        raise NothingToHandOver(plan.none_because or "nothing to hand over for that day")
    draft = plan.drafts[0]
    nudge = await render_from_state(
        session,
        Nudge,
        context,
        draft.scope,
        kind=draft.kind,
        scope=draft.scope,
        day=draft.day.isoformat(),
        language=draft.language,
        lines=list(draft.lines),
        voice=list(draft.voice),
        why=draft.why,
        reason=dict(draft.reason),
        cap_class=draft.cap_class,
        priority=draft.priority,
        send_after=draft.send_after,
        expires_at=draft.expires_at,
        dedupe_key=draft.dedupe_key,
        memo_id=draft.memo_id,
        handed_over_at=utcnow(),
        handed_over_by_person_id=context.person_id,
    )
    for delivery in deliveries:
        await delivery.take(session, context=context, nudge=nudge, draft=draft)
    return plan, nudge


@audited(Action.WRITE, Scope.PROFILE, NudgeResponse.__tablename__)
async def respond(
    session: AsyncSession, *, context: KeyContext, nudge_id: uuid.UUID, kind: ResponseKind
) -> NudgeResponse:
    """Write down what this person did with this nudge: an ENGAGEMENT event and a row."""
    found = await audited_read(
        session, Nudge, context, Scope.PROFILE, where=(Nudge.id == nudge_id,)
    )
    if not found:
        raise NoSuchNudge(f"no nudge {nudge_id} on profile {context.profile_id}")
    nudge = found[0]
    context.require(nudge.scope)
    moment = utcnow()
    event = await record_event(
        session,
        context=context,
        kind=EventKind.ENGAGEMENT,
        occurred_at=moment,
        label=f"{kind.value}: {nudge.kind.value} nudge",
        source_channel=SourceChannel.APP,
    )
    return await audited_write(
        session,
        NudgeResponse,
        context,
        Scope.PROFILE,
        nudge_id=nudge.id,
        person_id=context.person_id,
        kind=kind,
        event_id=event.id,
        at=moment,
    )
