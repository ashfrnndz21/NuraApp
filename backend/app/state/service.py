"""The State service: recompute, read, and render from.

State is the choke point. Everything downstream — ranking, format, cadence, escalation — is
computed from a snapshot, and a snapshot is computed from the record. Three promises hold
that together:

**It recomputes on any new fact.** `recompute_on_fact` is registered on the memory store's
`after_fact_write` hook, so the moment `assert_fact` (or a supersession) lands a fact, the
next snapshot is written in the same unit of work, naming that fact as its trigger. A
dispute is the one fact that does not move State: it is not a fact that holds (`ConfirmedFactStands`),
so the number it disputes stays current and the snapshot stays where it was. The hook is the
fast path, but it is not what makes the promise true: `current_state` compares the ids the
last snapshot was computed from with the ids that hold now, and recomputes before it answers
if they differ — so a fact written by a key too narrow to recompute, or an episode, a visit
or a key that changed with no hook of its own, still cannot be read past.

**Nothing renders without it.** `render_from_state` is the only way to write a row of a
table that carries `RenderedFromState`, and it stamps the snapshot on. A snapshot the record
has moved past is refused rather than quietly refreshed: the caller composed the card from
what that snapshot said, so it must compose it again.

**A narrower key sees a narrower State.** A snapshot is the record in miniature, so reading
one is reading the record: the door is `Scope.RECORDS`, and a key without it is refused and
written down. Past the door each dimension is gated by the scope its inputs came from, and
within a dimension each subject by the scope its facts sit under (`scope_for_subject`), so a
key to the readings and the record sees the blood pressure and not the medicines. What is
held back is named as withheld, never silently emptied.

Scope: a snapshot is derived data — the record folded — and is read and written under
`Scope.RECORDS` rather than a scope of its own. A dedicated `Scope.STATE` would have to be
added to every preset and would still have to be narrowed by what the key holds of the
record, so it would be a second name for the same thing. Recomputing reads the visits and
the keys as well, so it needs `RECOMPUTE_SCOPES`: the owner's context and a chief's.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action, Channel, Outcome
from app.audit.trail import record
from app.db import ProfileScoped, as_utc, utcnow
from app.errors import Refusal
from app.keys.context import KeyContext, OutOfScope
from app.keys.grants import list_keys
from app.keys.models import Key
from app.keys.scopes import Scope, scope_for_subject
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    ConfidenceState,
    Episode,
    Event,
    EventKind,
    Fact,
)
from app.memory.semantic import NoSuchFact, current_facts
from app.memory.working import open_episodes
from app.safety.boundary import Surface, is_boundary_line
from app.state.dimensions import AFTER_DISCHARGE_WINDOW, AFTER_VISIT_WINDOW, derive
from app.state.models import (
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

It can still read the last one, told that it could not check it against the record. A
helper who writes a medicine leaves State behind the record until the owner, or the chief he
named, reads it and catches it up.
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

STATE_TARGET = StateSnapshot.__tablename__


class NoState(Refusal):
    """Nothing renders without State, and this profile has none that this key can reach."""


class StaleState(Refusal):
    """The record has moved past this snapshot. Read State again and compose again."""


class TriggerWithoutItsFact(Refusal):
    """A recompute caused by a fact must name the fact."""


class FactWithoutItsTrigger(Refusal):
    """A fact is named only by a recompute that a fact caused."""


class NoBoundaryLine(Refusal):
    """A row of an inferring surface reached the store without the boundary line for it."""


class NotRenderable(Refusal):
    """This table is not something rendered to a person, so it has no State to record."""


@dataclass(frozen=True, slots=True)
class StateView:
    """A snapshot as one key may read it: the dimensions it covers, and the ones it does not.

    `stale` is False when the record was checked against the snapshot and nothing has moved,
    True when it has, and None when the key was too narrow to check.
    """

    id: uuid.UUID
    profile_id: uuid.UUID
    sequence: int
    computed_at: datetime
    posture: Posture
    trigger: StateTrigger
    trigger_fact_id: uuid.UUID | None
    supersedes_id: uuid.UUID | None
    stale_after: datetime | None
    stale: bool | None
    dimensions: Mapping[Dimension, Mapping[str, Any] | None]
    withheld: frozenset[Dimension]
    withheld_scopes: frozenset[Scope]

    def dimension(self, dimension: Dimension) -> Mapping[str, Any] | None:
        """One dimension, or None where the key does not cover it. See `withheld`."""
        return self.dimensions[dimension]


@dataclass(frozen=True, slots=True)
class Inputs:
    """Everything a snapshot is computed from, read under the key context at one moment."""

    at: datetime
    facts: Sequence[Fact]
    events: Sequence[Event]
    episodes: Sequence[Episode]
    appointments: Sequence[Appointment]
    keys: Sequence[Key]

    def fingerprint(self) -> dict[str, Any]:
        """The ids of the inputs, by kind. Same record, same fingerprint; nothing it says."""
        return {
            "facts": sorted(str(fact.id) for fact in self.facts),
            "events": sorted(str(event.id) for event in self.events),
            "episodes": sorted(str(episode.id) for episode in self.episodes),
            "appointments": sorted(
                [str(visit.id), visit.status.value] for visit in self.appointments
            ),
            "keys": sorted([str(key.id), key.is_active(self.at)] for key in self.keys),
        }


async def _inputs(session: AsyncSession, *, context: KeyContext) -> Inputs:
    """Read what State is computed from: the facts that hold, the open episodes, the recent
    discharges, the visits near enough to matter, and every key ever cut."""
    moment = utcnow()
    return Inputs(
        at=moment,
        facts=await current_facts(session, context=context, at=moment),
        events=await audited_read(
            session,
            Event,
            context,
            Scope.RECORDS,
            where=(
                Event.kind == EventKind.DISCHARGE,
                Event.occurred_at > moment - AFTER_DISCHARGE_WINDOW,
            ),
        ),
        episodes=await open_episodes(session, context=context),
        appointments=await audited_read(
            session,
            Appointment,
            context,
            Scope.VISITS,
            where=(
                Appointment.scheduled_at > moment - AFTER_VISIT_WINDOW,
                Appointment.status != AppointmentStatus.CANCELLED,
            ),
        ),
        keys=await list_keys(session, context=context),
    )


def _withheld_from(context: KeyContext) -> frozenset[Dimension]:
    return frozenset(
        dimension for dimension, scope in DIMENSION_SCOPE.items() if not context.allows(scope)
    )


def _narrowed(held: dict[str, Any], context: KeyContext) -> tuple[dict[str, Any], set[Scope]]:
    """One dimension with the subjects the key does not cover taken out, and which scopes those
    were under. A fact folded into State is still a fact: a key to the readings and the
    record sees the blood pressure, not the medicines."""
    facts: dict[str, Any] = held.get("facts", {})
    kept: dict[str, Any] = {}
    taken: set[Scope] = set()
    for subject, attributes in facts.items():
        scope = scope_for_subject(subject)
        if context.allows(scope):
            kept[subject] = attributes
        else:
            taken.add(scope)
    if not taken:
        return held, taken
    kept_ids = {entry["fact_id"] for attributes in kept.values() for entry in attributes.values()}
    return {
        **held,
        "facts": kept,
        "fact_ids": [one for one in held.get("fact_ids", []) if one in kept_ids],
    }, taken


def _view(snapshot: StateSnapshot, context: KeyContext, *, stale: bool | None) -> StateView:
    withheld = _withheld_from(context)
    dimensions: dict[Dimension, Mapping[str, Any] | None] = {}
    withheld_scopes: set[Scope] = {DIMENSION_SCOPE[dimension] for dimension in withheld}
    for dimension, held in snapshot.dimensions().items():
        if dimension in withheld:
            dimensions[dimension] = None
            continue
        narrowed, taken = _narrowed(held, context)
        dimensions[dimension] = narrowed
        withheld_scopes |= taken
    return StateView(
        id=snapshot.id,
        profile_id=snapshot.profile_id,
        sequence=snapshot.sequence,
        computed_at=as_utc(snapshot.computed_at),
        posture=snapshot.posture,
        trigger=snapshot.trigger,
        trigger_fact_id=snapshot.trigger_fact_id,
        supersedes_id=snapshot.supersedes_id,
        stale_after=None if snapshot.stale_after is None else as_utc(snapshot.stale_after),
        stale=stale,
        dimensions=dimensions,
        withheld=withheld,
        withheld_scopes=frozenset(withheld_scopes),
    )


async def latest_snapshot(session: AsyncSession, *, context: KeyContext) -> StateSnapshot | None:
    """The current snapshot for this profile, or None before the first one is computed."""
    found = await audited_read(
        session,
        StateSnapshot,
        context,
        STATE_SCOPE,
        order_by=(StateSnapshot.sequence.desc(),),
        limit=1,
    )
    return found[0] if found else None


def what_moved(
    snapshot: StateSnapshot, inputs: Inputs
) -> tuple[StateTrigger | None, uuid.UUID | None]:
    """What has happened to the record since this snapshot, or `(None, None)` if nothing has.

    The ids that hold now are compared with the ids the snapshot was computed from. Facts
    are asked about first and answered with the newest one that arrived, because a new fact
    is the ordinary reason State moves and the snapshot records which fact it was.
    """
    was: dict[str, Any] = snapshot.computed_from
    now = inputs.fingerprint()
    if was.get("facts") != now["facts"]:
        before = set(was.get("facts", []))
        arrived = [fact for fact in inputs.facts if str(fact.id) not in before]
        if arrived:
            newest = max(arrived, key=lambda fact: (as_utc(fact.asserted_at), str(fact.id)))
            return StateTrigger.NEW_FACT, newest.id
        # A fact stopped holding — its window closed — and nothing new arrived.
        return StateTrigger.TIME_PASSED, None
    if was.get("events") != now["events"]:
        return StateTrigger.NEW_EVENT, None
    if was.get("episodes") != now["episodes"]:
        return StateTrigger.EPISODE_CHANGE, None
    if was.get("appointments") != now["appointments"]:
        return StateTrigger.SPINE_CHANGE, None
    if was.get("keys") != now["keys"]:
        return StateTrigger.KEY_CHANGE, None
    if snapshot.stale_after is not None and as_utc(snapshot.stale_after) <= inputs.at:
        return StateTrigger.TIME_PASSED, None
    return None, None


async def _require_recompute_scopes(session: AsyncSession, *, context: KeyContext) -> None:
    """Refuse unless the key covers every scope a recompute reads, and write down what it
    reached for. Checked before anything is read: a key that covers some of them must not
    write a snapshot with the rest of the dimensions empty, because that snapshot would
    become the profile's State for everyone, and an empty dimension cannot be told from a
    quiet one."""
    for scope in sorted(RECOMPUTE_SCOPES):
        try:
            context.require(scope)
        except OutOfScope as refusal:
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=scope,
                target=STATE_TARGET,
                outcome=Outcome.REFUSED,
                refused_because=type(refusal).__name__,
            )
            refusal.written_down = True
            raise


async def _write_snapshot(
    session: AsyncSession,
    *,
    context: KeyContext,
    previous: StateSnapshot | None,
    inputs: Inputs,
    trigger: StateTrigger,
    fact_id: uuid.UUID | None,
) -> StateView:
    if trigger is StateTrigger.NEW_FACT and fact_id is None:
        raise TriggerWithoutItsFact("a recompute caused by a fact names the fact")
    if trigger is not StateTrigger.NEW_FACT and fact_id is not None:
        raise FactWithoutItsTrigger("a fact is named only by a recompute a fact caused")
    if fact_id is not None:
        named = await session.get(Fact, fact_id)
        if named is None or named.profile_id != context.profile_id:
            raise NoSuchFact("no such fact on this profile")

    derived = derive(
        facts=inputs.facts,
        events=inputs.events,
        episodes=inputs.episodes,
        appointments=inputs.appointments,
        keys=inputs.keys,
        now=inputs.at,
    )
    snapshot = await audited_write(
        session,
        StateSnapshot,
        context,
        STATE_SCOPE,
        sequence=1 if previous is None else previous.sequence + 1,
        computed_at=inputs.at,
        posture=derived.posture,
        trigger=trigger,
        trigger_fact_id=fact_id,
        supersedes_id=None if previous is None else previous.id,
        stale_after=derived.stale_after,
        computed_from=inputs.fingerprint(),
        clinical=derived.dimensions[Dimension.CLINICAL],
        functional=derived.dimensions[Dimension.FUNCTIONAL],
        cognitive=derived.dimensions[Dimension.COGNITIVE],
        situational=derived.dimensions[Dimension.SITUATIONAL],
        preference=derived.dimensions[Dimension.PREFERENCE],
        family=derived.dimensions[Dimension.FAMILY],
    )
    return _view(snapshot, context, stale=False)


@audited(Action.WRITE, STATE_SCOPE, STATE_TARGET)
async def recompute_state(
    session: AsyncSession,
    *,
    context: KeyContext,
    trigger: StateTrigger | None = None,
    fact_id: uuid.UUID | None = None,
) -> StateView:
    """Work the six dimensions out again, and write the snapshot that supersedes the last.

    The hook on the memory store calls this as a fact lands, with `StateTrigger.NEW_FACT`
    and the fact. Called on demand with no trigger it asks the record what moved and records
    that — or `ASKED`, when nothing has and the same facts were worked out again.
    """
    await _require_recompute_scopes(session, context=context)
    previous = await latest_snapshot(session, context=context)
    inputs = await _inputs(session, context=context)
    if trigger is None:
        if previous is None:
            trigger, fact_id = StateTrigger.FIRST, None
        else:
            moved, moved_by = what_moved(previous, inputs)
            trigger, fact_id = moved or StateTrigger.ASKED, moved_by
    return await _write_snapshot(
        session, context=context, previous=previous, inputs=inputs, trigger=trigger, fact_id=fact_id
    )


@audited(Action.READ, STATE_SCOPE, STATE_TARGET)
async def current_state(session: AsyncSession, *, context: KeyContext) -> StateView:
    """State as of now, recomputed first if the record has moved since it was last computed.

    A key that cannot recompute reads the last snapshot as it stands, told (`stale=None`)
    that it could not check the record against it; nothing may be rendered from that.
    """
    previous = await latest_snapshot(session, context=context)
    if not RECOMPUTE_SCOPES <= context.scopes:
        if previous is None:
            raise NoState("no state has been computed for this profile")
        return _view(previous, context, stale=None)
    inputs = await _inputs(session, context=context)
    if previous is None:
        return await _write_snapshot(
            session,
            context=context,
            previous=None,
            inputs=inputs,
            trigger=StateTrigger.FIRST,
            fact_id=None,
        )
    moved, moved_by = what_moved(previous, inputs)
    if moved is None:
        return _view(previous, context, stale=False)
    return await _write_snapshot(
        session, context=context, previous=previous, inputs=inputs, trigger=moved, fact_id=moved_by
    )


@audited(Action.READ, STATE_SCOPE, STATE_TARGET)
async def state_history(
    session: AsyncSession, *, context: KeyContext, limit: int = 50
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
    )
    return [_view(snapshot, context, stale=None) for snapshot in found]


async def render_from_state[Row: ProfileScoped](
    session: AsyncSession,
    model: type[Row],
    context: KeyContext,
    scope: Scope,
    /,
    *,
    state: StateView | None = None,
    channel: Channel = Channel.APP,
    surface: Surface | None = None,
    boundary: str | None = None,
    **values: Any,
) -> Row:
    """Write a card, a clip or a nudge, stamped with the State it was rendered from.

    Pass the `state` the content was composed from. If the record has moved past it the row
    is refused: what is on the card and what State said must be the same reading of the day.

    A row of an inferring surface names its `surface` and carries `boundary`, the line from
    `app.safety.boundary.boundary_line` for that surface; a row that names a surface without
    that line, or with some other text, is refused (`NoBoundaryLine`), and a row that names
    no surface carries none. The boundary is structure, like the State id: there is no way
    to write a brief or a learning card and forget its line.
    """
    if not issubclass(model, RenderedFromState):
        raise NotRenderable("this table does not record the state it was rendered from")
    if surface is not None and not is_boundary_line(surface, boundary):
        raise NoBoundaryLine(f"a {surface.value} row carries the boundary line for it")
    if surface is None and boundary is not None:
        raise NoBoundaryLine("a row that infers nothing names no surface and carries no line")
    rendered_from = state or await current_state(session, context=context)
    if state is not None:
        await _still_current(session, context=context, state=state)
    if rendered_from.stale is not False:
        raise StaleState("state is behind the record, or could not be checked against it")
    return await audited_write(
        session,
        model,
        context,
        scope,
        channel=channel,
        state_id=rendered_from.id,
        boundary=boundary,
        **values,
    )


async def _still_current(session: AsyncSession, *, context: KeyContext, state: StateView) -> None:
    if state.profile_id != context.profile_id:
        raise StaleState("that state belongs to another profile")
    latest = await current_state(session, context=context)
    if latest.id != state.id:
        raise StaleState("this state has been superseded")


# --- the hook on the memory store ---------------------------------------------------------


async def recompute_on_fact(session: AsyncSession, context: KeyContext, fact: Fact) -> None:
    """What makes "State recomputes on any new fact" true at the moment the fact lands.

    Registered on `app.memory.semantic.after_fact_write` by `app.state`. A dispute is not a
    fact that holds, so it does not move State. A writer whose key does not cover a recompute
    is refused at the door — written down, and the fact still lands — and State stays behind
    the record until a key that can recompute reads it (`current_state`).
    """
    if fact.confidence_state is ConfidenceState.DISPUTED:
        return
    try:
        await recompute_state(
            session, context=context, trigger=StateTrigger.NEW_FACT, fact_id=fact.id
        )
    except OutOfScope:
        return
