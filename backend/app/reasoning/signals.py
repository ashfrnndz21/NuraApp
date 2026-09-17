"""What Nura uses (RE-05): the everyday series he can switch off, and the confirmed
preference fact each switch writes.

docs/recommendation-engine.md §3.6 ("Switch a signal off") and ADR 0016 decision 3. Each
switch is a Fact — `subject="signals"`, `attribute=<family>` — confirmed by him or his chief
("He sets the switches, or his chief does under the confirm rules that bind every preference
fact today", §3.6), folded by State into the preference dimension
(`app.state.dimensions.SUBJECT_DIMENSION`). Turning one off is immediate on the next run: the
pattern detector and the recommendation broker (RE-01 to RE-04, later stories) skip that
series once they read it there.

Food, sleep, steps and water are used unless he says otherwise. Search-topic use is the one
exception, opt-in only (owner decision D3): it stays off until he turns it on himself, because
what he has asked about is his alone (§3.5, §3.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited
from app.audit.models import Action
from app.db import utcnow
from app.drafts import FactDraft
from app.errors import Refusal
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, EventKind, Fact, SourceChannel
from app.memory.semantic import assert_fact, current_facts

SIGNALS = "signals"
"""The Fact `subject` every switch is recorded under
(`app.state.dimensions.SUBJECT_DIMENSION`); the attribute names the family."""


class SignalFamily(StrEnum):
    """A series of his own everyday facts the recommendation engine may read."""

    FOOD = "food"
    SLEEP = "sleep"
    STEPS = "steps"
    WATER = "water"
    SEARCH_TOPICS = "search_topics"


DEFAULT_ON: frozenset[SignalFamily] = frozenset(
    {SignalFamily.FOOD, SignalFamily.SLEEP, SignalFamily.STEPS, SignalFamily.WATER}
)
"""Every family but search topics is used until he says otherwise. Search-topic use starts
off (owner decision D3, docs/recommendation-engine.md D3): opt-in only."""

SETTERS: frozenset[KeyRole] = frozenset({KeyRole.CHIEF})
"""He sets the switches, or his chief does (§3.6) — no other role, whatever scope it holds.
The same shape as `app.routines.service.may_set_routine`, narrower by one role: this is his
own preference about his own record, not a day the household runs by."""


class NotTheirsToSetSignals(Refusal):
    """A key that reads what Nura uses is not a key to switch it: his own, or his chief's."""


@dataclass(frozen=True, slots=True)
class SignalUse:
    """One family, on or off, and the fact it rests on — or none, when it still stands at
    the default because he has never said."""

    family: SignalFamily
    on: bool
    fact_id: str | None


def signals_may_be_set(context: KeyContext) -> bool:
    """Whether this key may flip a switch: his own, or his chief's. A caregiver, a viewer, a
    helper and a clinic read the switches and never this — `SignalsOut.may_set` for the
    screen, so a caregiver's view can say the switches are read-only, whose they are."""
    return context.is_owner or context.role in SETTERS


def may_set_signals(context: KeyContext) -> None:
    if signals_may_be_set(context):
        return
    raise NotTheirsToSetSignals(f"a {context.role} key reads what Nura uses; it does not set it")


async def _current(session: AsyncSession, *, context: KeyContext) -> dict[str, Fact]:
    facts = await current_facts(session, context=context, subject=SIGNALS)
    return {fact.attribute: fact for fact in facts}


@audited(Action.READ, Scope.RECORDS, SIGNALS)
async def current_signal_use(
    session: AsyncSession, *, context: KeyContext
) -> tuple[SignalUse, ...]:
    """Every family, on or off, as he last set it or the default when he never has."""
    facts = await _current(session, context=context)
    out: list[SignalUse] = []
    for family in SignalFamily:
        fact = facts.get(family.value)
        if fact is None:
            out.append(SignalUse(family=family, on=family in DEFAULT_ON, fact_id=None))
        else:
            out.append(SignalUse(family=family, on=bool(fact.value), fact_id=str(fact.id)))
    return tuple(out)


@audited(Action.WRITE, Scope.RECORDS, SIGNALS)
async def set_signal_use(
    session: AsyncSession, *, context: KeyContext, family: SignalFamily, on: bool
) -> SignalUse:
    """Switch one family on or off, on his own yes or his chief's
    (`NotTheirsToSetSignals` for anyone else).

    Confirmed at the tap: the way "not for me" on a card confirms itself
    (`app.delivery.feed.engagement._decline_for_the_day`) — one screen, one switch, nothing
    shown first to say yes to twice. The write is on the trail either way, and State folds
    the fact into the preference dimension on its next recompute
    (`app.state.dimensions.SUBJECT_DIMENSION`).
    """
    may_set_signals(context)
    current = (await _current(session, context=context)).get(family.value)
    event = await record_event(
        session,
        context=context,
        kind=EventKind.SETTING,
        occurred_at=utcnow(),
        label=f"signal {family.value}: {'on' if on else 'off'}",
        source_channel=SourceChannel.APP,
    )
    draft = FactDraft(
        subject=SIGNALS,
        attribute=family.value,
        value=on,
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None if current is None else current.id,
    )
    yes = await confirm(session, context, draft)
    written = await assert_fact(
        session,
        context=context,
        subject=SIGNALS,
        attribute=family.value,
        value=on,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmation_id=yes.id,
        event_id=event.id,
        supersedes_id=None if current is None else current.id,
    )
    return SignalUse(family=family, on=on, fact_id=str(written.id))
