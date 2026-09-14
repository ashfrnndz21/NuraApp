"""The State service: recompute, read, and render from.

State is the choke point. Everything downstream — ranking, format, cadence, escalation — is
computed from a snapshot, and a snapshot is computed from the record. Three promises hold
that together:

**It recomputes on any new fact.** Ingestion calls `recompute` when it writes facts, naming
the fact as the trigger. That is the fast path, but it is not what makes the promise true:
`current_state` asks the record whether anything has landed since the snapshot was computed,
and recomputes before it answers if anything has. A fact written by a path that forgets to
call, or by another worker, or by a worker that died between the two writes, still cannot be
read past — which is the only version of "recomputes on any new fact" that survives more
than one process.

**Nothing renders without it.** `render_from_state` is the only way to write a row of a
table that carries `RenderedFromState`, and it stamps the snapshot on. A snapshot the record
has moved past is refused rather than quietly refreshed: the caller composed the card from
what that snapshot said, so it must compose it again.

**A narrower key sees a narrower State.** A snapshot is the record in miniature, so reading
one is reading the record, and each dimension is gated by the scope its facts came from. A
dimension a key does not cover is withheld — named as withheld, never silently emptied.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.audit.models import Action, Channel, Outcome
from app.audit.trail import record
from app.db import ProfileScoped, as_utc, utcnow
from app.errors import Refusal
from app.keys.context import KeyContext, OutOfScope
from app.keys.grants import list_keys
from app.keys.scopes import Scope
from app.memory.models import Appointment, AppointmentStatus, Episode, Event, EventKind, Fact
from app.memory.semantic import current_facts
from app.memory.working import open_episodes
from app.state.dimensions import AFTER_DISCHARGE_WINDOW, AFTER_VISIT_WINDOW, derive
from app.state.models import (
    FACT_TRIGGERS,
    Dimension,
    Posture,
    RenderedFromState,
    StateSnapshot,
    StateTrigger,
)

STATE_SCOPE = Scope.RECORDS
"""What reading or writing a snapshot costs: a snapshot is the record, folded into six."""

RECOMPUTE_SCOPES: frozenset[Scope] = frozenset({Scope.RECORDS, Scope.VISITS, Scope.FAMILY})
"""Every scope a full recompute reads from. A key without all three cannot compute a State.

It can still read the last one, marked stale. Recomputing is the owner's own context and the
chief's; a helper who writes a medicine leaves State behind the record until one of them, or
the profile's own worker, catches it up.
"""

DIMENSION_SCOPE: dict[Dimension, Scope] = {
    Dimension.CLINICAL: Scope.RECORDS,
    Dimension.FUNCTIONAL: Scope.RECORDS,
    Dimension.COGNITIVE: Scope.RECORDS,
    Dimension.PREFERENCE: Scope.NOTES,
    Dimension.SITUATIONAL: Scope.VISITS,
    Dimension.FAMILY: Scope.FAMILY,
}
"""Which key opens which dimension when a snapshot is read back.

`STATE_SCOPE` is the floor — nobody reads a snapshot at all without it — so a dimension
gated on `Scope.RECORDS` is open to everyone who got this far. The preference dimension is
what he has agreed to and what he has said no to, so it is gated where the private notes
are: a clinic key reaches the record, and does not reach what he declined.
"""


class NoState(Refusal):
    """Nothing renders without State, and this profile has none that this key can reach."""


class StaleState(Refusal):
    """The record has moved past this snapshot. Read State again and compose again."""


class TriggerWithoutItsFact(Refusal):
    """A recompute caused by a fact must name the fact."""


class NotRenderable(Refusal):
    """This table is not something rendered to a person, so it has no State to record."""


@dataclass(frozen=True, slots=True)
class StateView:
    """A snapshot as one key may read it: the dimensions it covers, and the ones it does not."""

    id: uuid.UUID
    profile_id: uuid.UUID
    sequence: int
    computed_at: datetime
    posture: Posture
    because: list[dict[str, Any]]
    trigger: StateTrigger
    trigger_fact_id: uuid.UUID | None
    supersedes_id: uuid.UUID | None
    stale_after: datetime | None
    stale: bool
    dimensions: Mapping[Dimension, Mapping[str, Any] | None]
    withheld: frozenset[Dimension]

    def dimension(self, dimension: Dimension) -> Mapping[str, Any] | None:
        """One dimension, or None where the key does not cover it. See `withheld`."""
        return self.dimensions[dimension]


def _withheld_from(context: KeyContext) -> frozenset[Dimension]:
    return frozenset(
        dimension for dimension, scope in DIMENSION_SCOPE.items() if not context.allows(scope)
    )


async def _write_down_what_was_withheld(
    session: AsyncSession,
    *,
    context: KeyContext,
    withheld: frozenset[Dimension],
    now: datetime | None,
) -> None:
    """One refused line per dimension held back, so the owner sees the reaching too.

    The reader is told which dimensions were withheld and the owner is told that they were
    reached for. Neither is told what they said.
    """
    for dimension in sorted(withheld):
        await record(
            session,
            context=context,
            action=Action.READ,
            scope=DIMENSION_SCOPE[dimension],
            target=f"{StateSnapshot.__tablename__}.{dimension.value}",
            outcome=Outcome.REFUSED,
            refused_because=OutOfScope.__name__,
            now=now,
        )


def _view(snapshot: StateSnapshot, context: KeyContext, *, stale: bool) -> StateView:
    withheld = _withheld_from(context)
    held = snapshot.dimensions()
    return StateView(
        id=snapshot.id,
        profile_id=snapshot.profile_id,
        sequence=snapshot.sequence,
        computed_at=as_utc(snapshot.computed_at),
        posture=snapshot.posture,
        because=list(snapshot.posture_because),
        trigger=snapshot.trigger_kind,
        trigger_fact_id=snapshot.trigger_fact_id,
        supersedes_id=snapshot.supersedes_id,
        stale_after=None if snapshot.stale_after is None else as_utc(snapshot.stale_after),
        stale=stale,
        dimensions={
            dimension: None if dimension in withheld else held[dimension]
            for dimension in Dimension
        },
        withheld=withheld,
    )


async def _seen(
    session: AsyncSession,
    snapshot: StateSnapshot,
    context: KeyContext,
    *,
    stale: bool,
    now: datetime | None,
) -> StateView:
    """A snapshot as this key reads it, with what it could not reach written down."""
    view = _view(snapshot, context, stale=stale)
    await _write_down_what_was_withheld(
        session, context=context, withheld=view.withheld, now=now
    )
    return view


async def latest_snapshot(
    session: AsyncSession, *, context: KeyContext, now: datetime | None = None
) -> StateSnapshot | None:
    """The current snapshot for this profile, or None before the first one is computed."""
    found = await audited_read(
        session,
        StateSnapshot,
        context,
        STATE_SCOPE,
        order_by=(StateSnapshot.sequence.desc(),),
        limit=1,
        now=now,
    )
    return found[0] if found else None


async def changed_since(
    session: AsyncSession,
    *,
    context: KeyContext,
    snapshot: StateSnapshot,
    now: datetime | None = None,
) -> tuple[StateTrigger | None, uuid.UUID | None]:
    """What has happened to the record since this snapshot, or `(None, None)` if nothing has.

    Facts are asked about first and answered with the newest one, because a new fact is the
    ordinary reason State moves and the snapshot records which fact it was.
    """
    moment = now or utcnow()
    since = as_utc(snapshot.computed_at)

    # A snapshot that folded facts in is behind anything asserted after it was computed. One
    # that folded none is behind the moment any fact exists at all — which is how a fact
    # asserted at the very instant of the first recompute is still caught.
    landed: ColumnElement[bool] = (
        Fact.asserted_at >= since
        if snapshot.folded_through is None
        else Fact.asserted_at > since
    )
    facts = await audited_read(
        session,
        Fact,
        context,
        Scope.RECORDS,
        where=(landed,),
        order_by=(Fact.asserted_at.desc(),),
        limit=1,
        now=now,
    )
    if facts:
        return StateTrigger.NEW_FACT, facts[0].id

    events = await audited_read(
        session,
        Event,
        context,
        Scope.RECORDS,
        where=(Event.recorded_at > since,),
        limit=1,
        now=now,
    )
    if events:
        return StateTrigger.NEW_EVENT, None

    episodes = await audited_read(
        session,
        Episode,
        context,
        Scope.RECORDS,
        where=(Episode.opened_at > since,),
        limit=1,
        now=now,
    )
    if episodes or await _closed_since(session, context=context, since=since, now=now):
        return StateTrigger.EPISODE_CHANGE, None

    appointments = await audited_read(
        session,
        Appointment,
        context,
        Scope.VISITS,
        # A visit is only detected as newly written down. An appointment row can still be
        # edited — cancelled, moved — and when E05 adds those it has to carry the moment it
        # last changed, or a cancelled visit will sit in State until its own window closes.
        where=(Appointment.booked_at > since,),
        limit=1,
        now=now,
    )
    if appointments:
        return StateTrigger.SPINE_CHANGE, None

    for key in await list_keys(session, context=context, now=now):
        cut_or_closed = [key.granted_at, key.revoked_at]
        if any(at is not None and as_utc(at) > since for at in cut_or_closed):
            return StateTrigger.KEY_CHANGE, None

    if snapshot.stale_after is not None and as_utc(snapshot.stale_after) <= moment:
        return StateTrigger.TIME_PASSED, None
    return None, None


async def _closed_since(
    session: AsyncSession, *, context: KeyContext, since: datetime, now: datetime | None
) -> bool:
    closed = await audited_read(
        session,
        Episode,
        context,
        Scope.RECORDS,
        where=(Episode.closed_at.is_not(None), Episode.closed_at > since),
        limit=1,
        now=now,
    )
    return bool(closed)


async def _require_all(
    session: AsyncSession,
    *,
    context: KeyContext,
    scopes: frozenset[Scope],
    now: datetime | None,
) -> None:
    """Refuse unless the key covers every scope named, and write down what it reached for."""
    for scope in sorted(scopes):
        try:
            context.require(scope)
        except OutOfScope as refusal:
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=scope,
                target=StateSnapshot.__tablename__,
                outcome=Outcome.REFUSED,
                refused_because=type(refusal).__name__,
                now=now,
            )
            raise


async def recompute(
    session: AsyncSession,
    *,
    context: KeyContext,
    trigger: StateTrigger | None = None,
    trigger_fact_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> StateView:
    """Work the six dimensions out again, and write the snapshot that supersedes the last.

    Ingestion calls this as it writes, passing `StateTrigger.NEW_FACT` and the fact. Called
    without a trigger it asks the record what moved, so a scheduled sweep records the truth
    rather than "schedule".

    Every scope a recompute reads is required up front, before anything is read at all. A
    key that covers some of them must not write a snapshot with the rest of the dimensions
    empty: that snapshot would become the profile's State for everyone, and an empty
    dimension is indistinguishable from a quiet one.
    """
    moment = now or utcnow()
    await _require_all(session, context=context, scopes=RECOMPUTE_SCOPES, now=now)
    previous = await latest_snapshot(session, context=context, now=now)
    if trigger is None:
        if previous is None:
            trigger, trigger_fact_id = StateTrigger.FIRST, None
        else:
            found, fact_id = await changed_since(
                session, context=context, snapshot=previous, now=now
            )
            trigger, trigger_fact_id = found or StateTrigger.TIME_PASSED, fact_id
    if trigger in FACT_TRIGGERS and trigger_fact_id is None:
        raise TriggerWithoutItsFact(f"a {trigger} recompute names the fact that caused it")

    facts = await current_facts(session, context=context, at=moment, now=now)
    episodes = await open_episodes(session, context=context, now=now)
    events = await audited_read(
        session,
        Event,
        context,
        Scope.RECORDS,
        where=(
            Event.kind == EventKind.DISCHARGE,
            Event.occurred_at > moment - AFTER_DISCHARGE_WINDOW,
        ),
        now=now,
    )
    appointments = await audited_read(
        session,
        Appointment,
        context,
        Scope.VISITS,
        where=(
            Appointment.scheduled_at > moment - AFTER_VISIT_WINDOW,
            Appointment.status != AppointmentStatus.CANCELLED,
        ),
        now=now,
    )
    keys = await list_keys(session, context=context, now=now)

    derived = derive(
        facts=facts,
        events=events,
        episodes=episodes,
        appointments=appointments,
        keys=keys,
        now=moment,
    )
    snapshot = await audited_write(
        session,
        StateSnapshot,
        context,
        STATE_SCOPE,
        now=now,
        sequence=1 if previous is None else previous.sequence + 1,
        computed_at=moment,
        posture=derived.posture,
        posture_because=derived.because,
        trigger_kind=trigger,
        trigger_fact_id=trigger_fact_id,
        supersedes_id=None if previous is None else previous.id,
        stale_after=derived.stale_after,
        folded_through=max((as_utc(fact.asserted_at) for fact in facts), default=None),
        clinical=derived.dimensions[Dimension.CLINICAL],
        functional=derived.dimensions[Dimension.FUNCTIONAL],
        cognitive=derived.dimensions[Dimension.COGNITIVE],
        situational=derived.dimensions[Dimension.SITUATIONAL],
        preference=derived.dimensions[Dimension.PREFERENCE],
        family=derived.dimensions[Dimension.FAMILY],
    )
    return await _seen(session, snapshot, context, stale=False, now=now)


async def current_state(
    session: AsyncSession, *, context: KeyContext, now: datetime | None = None
) -> StateView:
    """State as of now, recomputed first if anything has landed since it was last computed.

    A key that cannot recompute gets the last snapshot marked `stale` instead of a refusal,
    so a narrow reader is never left with nothing; nothing may be rendered from it.
    """
    snapshot = await latest_snapshot(session, context=context, now=now)
    try:
        if snapshot is None:
            return await recompute(session, context=context, now=now)
        trigger, fact_id = await changed_since(
            session, context=context, snapshot=snapshot, now=now
        )
        if trigger is None:
            return await _seen(session, snapshot, context, stale=False, now=now)
        return await recompute(
            session, context=context, trigger=trigger, trigger_fact_id=fact_id, now=now
        )
    except OutOfScope:
        # The door that refused it has already written the line. A key too narrow to
        # recompute still reads what was computed for the profile, and is told it is behind.
        if snapshot is None:
            raise
        return await _seen(session, snapshot, context, stale=True, now=now)


async def render_from_state[Row: ProfileScoped](
    session: AsyncSession,
    model: type[Row],
    context: KeyContext,
    scope: Scope,
    /,
    *,
    state: StateView | None = None,
    channel: Channel = Channel.APP,
    now: datetime | None = None,
    **values: Any,
) -> Row:
    """Write a card, a clip or a nudge, stamped with the State it was rendered from.

    Pass the `state` the content was composed from. If the record has moved past it the row
    is refused: what is on the card and what State said must be the same reading of the day.
    """
    if not issubclass(model, RenderedFromState):
        raise NotRenderable(f"{model.__name__} does not record the state it was rendered from")
    rendered_from = state or await current_state(session, context=context, now=now)
    if state is not None:
        await _still_current(session, context=context, state=state, now=now)
    if rendered_from.stale:
        raise StaleState("state is behind the record; recompute before rendering")
    return await audited_write(
        session,
        model,
        context,
        scope,
        channel=channel,
        now=now,
        state_id=rendered_from.id,
        **values,
    )


async def _still_current(
    session: AsyncSession, *, context: KeyContext, state: StateView, now: datetime | None
) -> None:
    if state.profile_id != context.profile_id:
        raise StaleState("that state belongs to another profile")
    latest = await latest_snapshot(session, context=context, now=now)
    if latest is None:
        raise NoState(f"no state computed for profile {context.profile_id}")
    if latest.id != state.id:
        raise StaleState(f"state {state.sequence} has been superseded by {latest.sequence}")
    trigger, _ = await changed_since(session, context=context, snapshot=latest, now=now)
    if trigger is not None:
        raise StaleState(f"the record has moved past this state: {trigger}")


async def state_history(
    session: AsyncSession,
    *,
    context: KeyContext,
    limit: int = 50,
    now: datetime | None = None,
) -> Sequence[StateView]:
    """The last snapshots, newest first: why the app said what it said, in order.

    Each is read as it was written, not as it stands against the record now; whether the
    newest one is still current is what `current_state` is for.
    """
    found = await audited_read(
        session,
        StateSnapshot,
        context,
        STATE_SCOPE,
        order_by=(StateSnapshot.sequence.desc(),),
        limit=limit,
        now=now,
    )
    await _write_down_what_was_withheld(
        session, context=context, withheld=_withheld_from(context), now=now
    )
    return [_view(snapshot, context, stale=False) for snapshot in found]
