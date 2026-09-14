"""The key context: who is asking, about whose profile, and what that covers.

Nothing reads profile data without one, and the only way to get one is to ask here. The
resolver is also where the region pin is checked, so an out-of-region read cannot be reached
by any route that goes through a context.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.errors import Refusal
from app.identity.models import Profile
from app.keys.models import Key
from app.keys.scopes import ALL_SCOPES, KeyRole, Scope
from app.regions import OutOfRegion, Region, guard_region

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
    that no profile can be found, or placed, by asking for it.
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


@dataclass(frozen=True, slots=True)
class KeyContext:
    """The resolved answer to "may this person see this, and which parts"."""

    profile_id: uuid.UUID
    region: Region
    person_id: uuid.UUID
    scopes: frozenset[Scope]
    role: KeyRole | None = None
    key_id: uuid.UUID | None = None

    @property
    def is_owner(self) -> bool:
        """The owner reads his own graph without a key, so there is no key to name."""
        return self.key_id is None

    def allows(self, scope: Scope) -> bool:
        return scope in self.scopes

    def require(self, scope: Scope) -> None:
        """Raise unless this context covers the scope. Every read calls this, once."""
        if scope not in self.scopes:
            raise OutOfScope(scope=scope, context=self)


async def resolve_key_context(
    session: AsyncSession,
    *,
    region: Region,
    person_id: uuid.UUID,
    profile_id: uuid.UUID,
) -> KeyContext:
    """Resolve what this person may see of this profile, in this region, at this moment.

    `region` is the region this deployment serves. A profile pinned elsewhere is refused
    even when its row is present, because a row in the wrong database is the thing we are
    guarding against.
    """
    moment = utcnow()
    profile = await session.get(Profile, profile_id)
    if profile is None:
        _unknown_reach(person_id, profile_id)
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
        _unknown_reach(person_id, profile_id)
        raise NoKey(person_id=person_id, profile_id=profile_id)

    try:
        guard_region(held_in=profile.region, asked_from=region)
    except OutOfRegion as refusal:
        await _record_refused(session, profile=profile, person_id=person_id, refusal=refusal)
        raise

    if profile.owner_person_id == person_id:
        return KeyContext(
            profile_id=profile.id,
            region=profile.region,
            person_id=person_id,
            scopes=ALL_SCOPES,
        )

    for key in keys:
        if key.is_active(moment):
            return KeyContext(
                profile_id=profile.id,
                region=profile.region,
                person_id=person_id,
                scopes=key.scopes_held,
                role=key.role,
                key_id=key.id,
            )
    # The revoked-helper case: she held a key once, it is closed, and she is reaching again.
    refused = NoKey(person_id=person_id, profile_id=profile_id)
    await _record_refused(session, profile=profile, person_id=person_id, refusal=refused)
    raise refused


def _unknown_reach(person_id: uuid.UUID, profile_id: uuid.UUID) -> None:
    if on_unknown_reach is not None:
        on_unknown_reach(person_id, profile_id)


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
    return any(key.is_active(moment) for key in keys)


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
        ),
        action=Action.READ,
        # Resolving a key is a reach at the whole graph; the family scope is where who holds
        # what is kept, so the refused line sits there.
        scope=Scope.FAMILY,
        target=profile.__tablename__,
        outcome=Outcome.REFUSED,
        refused_because=type(refusal).__name__,
    )
