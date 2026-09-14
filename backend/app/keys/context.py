"""The key context: who is asking, about whose profile, and what that covers.

Nothing reads profile data without one, and the only way to get one is to ask here. The
resolver is also where the region pin is checked, so an out-of-region read cannot be reached
by any route that goes through a context.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.keys.models import Key
from app.keys.privacy import only_me_scopes
from app.keys.scopes import ALL_SCOPES, KeyRole, Scope
from app.regions import Region, guard_region

unknown_reaches: Counter[uuid.UUID] = Counter()
"""How many times each account has reached for a profile it has never known. In memory, per
process: enough for a test and a first alarm; a channel replaces the hook with its own."""


def count_unknown_reach(person_id: uuid.UUID, profile_id: uuid.UUID) -> None:
    unknown_reaches[person_id] += 1


on_unknown_reach: Callable[[uuid.UUID, uuid.UUID], None] | None = count_unknown_reach
"""Called with (person_id, profile_id) each time an unknown account is refused in silence.

Accepted residual risk: a person the profile has never known — no key ever cut, not the
owner — is refused with `NoKey` and no line in the trail, because a line would let anyone
fill a victim's trail by repeating a known id, and because the same words for a missing
profile, a real one and one pinned elsewhere are what stop a profile being found or placed
by asking. The cost is that repeated reaching by an unknown account is invisible to the
owner from inside the trail. The channel wires a counter here — rate limits and alerts live
out of band, keyed on the account reaching, never written into the profile it reached for.
"""


class NoKey(Refusal):
    """This person holds nothing on this profile.

    A profile that does not exist, one the asker has never held a key to, and one pinned to
    another region all refuse in these same words to a person the profile does not know, so
    that no profile can be found, or placed, by asking for it. The one person a profile
    knows without a key or ownership is the one it was set up for, by his number, before
    he claims it (`Standing.CLAIMANT`).
    """

    def __init__(self, *, person_id: uuid.UUID, profile_id: uuid.UUID) -> None:
        super().__init__(f"person {person_id} holds no key on profile {profile_id}")
        self.person_id = person_id
        self.profile_id = profile_id


class OutOfScope(Refusal):
    """The key is good, but it does not cover this part of the record."""

    def __init__(self, *, scope: Scope, context: KeyContext) -> None:
        super().__init__(f"key does not cover {scope}")
        self.scope = scope
        self.context = context


class Standing(StrEnum):
    """On what footing the person reaches the profile.

    `OWNER`: the graph is his, and he needs no key. `HOLDER`: a key someone cut him on a
    graph that has an owner. `STEWARD`: the chief key he holds on a graph nobody owns yet,
    because he set it up for the patient (E01). `CLAIMANT`: the person the graph was set up
    for, reaching it by the number it was set up against, before he has said it is his: he
    sees whose graph it is and nothing else until he claims it. `NONE`: nothing resolved —
    the footing a refusal is written under.
    """

    OWNER = "owner"
    HOLDER = "holder"
    STEWARD = "steward"
    CLAIMANT = "claimant"
    NONE = "none"
    SYSTEM = "system"
    """Nura itself, acting for the profile — the delivery engine's run: the reach of the
    person it acts for (the owner, or the steward before a claim), and no person as the
    actor on the trail (`as_the_system`)."""


CLAIMANT_SCOPES = frozenset({Scope.PROFILE})
"""What the person a graph was set up for may see of it before he claims it: whose it is."""


@dataclass(frozen=True, slots=True)
class KeyContext:
    """The resolved answer to "may this person see this, and which parts"."""

    profile_id: uuid.UUID
    region: Region
    person_id: uuid.UUID
    scopes: frozenset[Scope]
    role: KeyRole | None = None
    key_id: uuid.UUID | None = None
    standing: Standing = Standing.OWNER

    @property
    def is_owner(self) -> bool:
        """The owner reads his own graph without a key, so there is no key to name. The
        person a graph was set up for reads it without a key too, and is not its owner yet."""
        return self.standing is Standing.OWNER

    @property
    def is_steward(self) -> bool:
        """Holding the graph for the patient until he claims it."""
        return self.standing is Standing.STEWARD

    @property
    def is_claimant(self) -> bool:
        """The patient, before he has said the graph set up for him is his."""
        return self.standing is Standing.CLAIMANT

    def allows(self, scope: Scope) -> bool:
        return scope in self.scopes

    def require(self, scope: Scope) -> None:
        """Raise unless this context covers the scope. Every read calls this, once."""
        if scope not in self.scopes:
            raise OutOfScope(scope=scope, context=self)


def as_the_system(context: KeyContext) -> KeyContext:
    """The same reach, held by Nura itself rather than by the person: what the delivery
    engine runs under, so its reads and writes are the system's on the trail (no actor, the
    system channel), never the patient's own. Only a resolved owner's or steward's context is
    turned into this, and only by the engine."""
    return replace(context, role=None, key_id=None, standing=Standing.SYSTEM)


async def profile_by_id(
    session: AsyncSession, *, region: Region, profile_id: uuid.UUID
) -> Profile | None:
    """The profile row, if it is here and pinned to this region; otherwise nothing.

    The one way to look at a profile row without a context, for the code that is about to
    make one — the resolver below, and a channel deciding whether a refused reach has a graph
    to be written into. Reading the row's contents for anyone goes through
    `app.audit.access.audited_profile_read`, with a context.
    """
    profile = await session.get(Profile, profile_id)
    if profile is None or profile.region is not region:
        return None
    return profile


async def owned_profile(
    session: AsyncSession, *, region: Region, owner_person_id: uuid.UUID
) -> Profile | None:
    """The profile this person owns, if he has opened one here. Region-filtered, like the above."""
    return await session.scalar(
        select(Profile).where(Profile.owner_person_id == owner_person_id, Profile.region == region)
    )


async def profile_for_number(
    session: AsyncSession, *, region: Region, phone_e164: str
) -> Profile | None:
    """The profile set up against this phone number here, owned or still stewarded, or None.

    Like `owned_profile`: a row lookup for the code about to make a context or refuse to,
    never a read of what the graph holds. One graph per number is the rule (E01).
    """
    return await session.scalar(
        select(Profile).where(Profile.patient_phone_e164 == phone_e164, Profile.region == region)
    )


async def resolve_key_context(
    session: AsyncSession,
    *,
    region: Region,
    person_id: uuid.UUID,
    profile_id: uuid.UUID,
    while_closing: bool = False,
) -> KeyContext:
    """Resolve what this person may see of this profile, in this region, at this moment.

    `region` is the region this deployment serves. A profile pinned elsewhere is refused
    even when its row is present, because a row in the wrong database is the thing we are
    guarding against.

    While the owner's closing of his account stands (#143), nobody opens the profile —
    every key, and the owner's own reads — and the refusal is `AccountClosing`, on the trail.
    `while_closing` is for the few that must: the closing's status and his undo, and the
    delivery engine, which still carries a red flag raised before the closing.
    """
    moment = utcnow()
    profile = await session.get(Profile, profile_id)
    if profile is None:
        unknown_reach(person_id, profile_id)
        raise NoKey(person_id=person_id, profile_id=profile_id)

    # Every key ever cut for this person on this profile, closed ones included. A person the
    # profile knows — its owner, or someone who held a key once — is told the real reason
    # and is written down when refused. A person it has never known gets NoKey and silence,
    # whether the profile is missing, here, or pinned elsewhere: no profile can be found, or
    # placed in a region, by asking for it, and no known id is a way to fill a trail.
    keys = list(
        await session.scalars(
            select(Key).where(Key.profile_id == profile_id, Key.holder_person_id == person_id)
        )
    )
    if profile.owner_person_id != person_id and not keys:
        if await is_claimant_of(session, profile=profile, person_id=person_id):
            # The graph was set up against his number and nobody owns it yet: he may see
            # whose it is, and claim it; the rest waits for his OK (`app.identity.doors`).
            guard_region(held_in=profile.region, asked_from=region)
            return KeyContext(
                profile_id=profile.id,
                region=profile.region,
                person_id=person_id,
                scopes=CLAIMANT_SCOPES,
                standing=Standing.CLAIMANT,
            )
        unknown_reach(person_id, profile_id)
        raise NoKey(person_id=person_id, profile_id=profile_id)

    # A caller the profile knows is told the real reason; but nothing about another region's
    # profile is written into this region's trail, so the line stays with the channel's log.
    guard_region(held_in=profile.region, asked_from=region)

    if not while_closing and await closing_since(session, profile_id=profile.id) is not None:
        closing = AccountClosing(f"profile {profile.id} is closing")
        await _record_refused(session, profile=profile, person_id=person_id, refusal=closing)
        raise closing

    if profile.owner_person_id == person_id:
        return KeyContext(
            profile_id=profile.id,
            region=profile.region,
            person_id=person_id,
            scopes=ALL_SCOPES,
        )

    for key in keys:
        if key.is_active(moment):
            # The parts the owner marked "only me" come out of every key here, at the
            # floor, whatever the key row says (E12-04): a mark made a second ago holds
            # against a key cut a year ago, and nothing above this can put them back.
            return KeyContext(
                profile_id=profile.id,
                region=profile.region,
                person_id=person_id,
                scopes=key.scopes_held - await only_me_scopes(session, profile_id=profile.id),
                role=key.role,
                key_id=key.id,
                # A key on a graph nobody owns is the steward's: he holds it for the patient.
                standing=(Standing.STEWARD if profile.owner_person_id is None else Standing.HOLDER),
            )
    # The revoked-helper case: she held a key once, it is closed, and she is reaching again.
    refused = NoKey(person_id=person_id, profile_id=profile_id)
    await _record_refused(session, profile=profile, person_id=person_id, refusal=refused)
    raise refused


class AccountClosing(Refusal):
    """Its owner closed this account (#143): nobody opens it while his papers wait to be
    deleted. His undo, and the closing's own status, are the only doors left open to him."""


async def closing_since(session: AsyncSession, *, profile_id: uuid.UUID) -> datetime | None:
    """When the owner closed this account, if that closing stands (not undone); else None."""
    from app.identity.closure_models import AccountClosure

    found: datetime | None = await session.scalar(
        select(AccountClosure.requested_at)
        .where(AccountClosure.profile_id == profile_id, AccountClosure.undone_at.is_(None))
        .limit(1)
    )
    return found


def unknown_reach(person_id: uuid.UUID, profile_id: uuid.UUID) -> None:
    """Count a reach by a person the profile has never known. No line is written; see
    `on_unknown_reach`. Public for the doors that refuse a stranger by a phone number."""
    if on_unknown_reach is not None:
        on_unknown_reach(person_id, profile_id)


async def is_claimant_of(session: AsyncSession, *, profile: Profile, person_id: uuid.UUID) -> bool:
    """Whether this person is the one the profile was set up for and has not claimed it yet:
    it has no owner, and his number is the number it was set up against."""
    if profile.owner_person_id is not None or profile.patient_phone_e164 is None:
        return False
    person = await session.get(Person, person_id)
    return person is not None and person.phone_e164 == profile.patient_phone_e164


async def holds_the_profile(
    session: AsyncSession, *, profile_id: uuid.UUID, person_id: uuid.UUID
) -> bool:
    """Whether this person could open this profile now — by the clock, not by any caller's
    account of the time: its owner, or a key on it that is live at this moment.

    A yes-or-no with no context resolved and no line written — for checking a person who
    is *named* in a request (the one whose confirm is being used) without ever acting as
    them. Only the person who reached is ever the actor on a line.
    """
    profile = await session.get(Profile, profile_id)
    if profile is None:
        return False
    if profile.owner_person_id == person_id:
        return True
    keys = await session.scalars(
        select(Key).where(Key.profile_id == profile_id, Key.holder_person_id == person_id)
    )
    moment = utcnow()
    if any(key.is_active(moment) for key in keys):
        return True
    return await is_claimant_of(session, profile=profile, person_id=person_id)


async def _record_refused(
    session: AsyncSession,
    *,
    profile: Profile,
    person_id: uuid.UUID,
    refusal: Refusal,
) -> None:
    """One refused line for a reach that resolved nothing, in the name of the refusal only.

    The context is the narrowest there is — no scopes, no key — because nothing was resolved.
    """
    # Local import: `app.audit.trail` imports this module for `KeyContext`, so importing it at
    # the top would be a cycle. The trail is the floor of the enforcement beside the keys, and
    # this is the one place the keys call up into it.
    from app.audit.models import Action, Outcome
    from app.audit.trail import record

    await record(
        session,
        context=KeyContext(
            profile_id=profile.id,
            region=profile.region,
            person_id=person_id,
            scopes=frozenset(),
            standing=Standing.NONE,
        ),
        action=Action.READ,
        # Resolving a key is a reach at the face of the graph, which every key opens.
        scope=Scope.PROFILE,
        target=profile.__tablename__,
        outcome=Outcome.REFUSED,
        refused_because=type(refusal).__name__,
    )
