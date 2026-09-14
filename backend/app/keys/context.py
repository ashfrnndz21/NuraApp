"""The key context: who is asking, about whose profile, and what that covers.

Nothing reads profile data without one, and the only way to get one is to ask here. The
resolver is also where the region pin is checked, so an out-of-region read cannot be reached
by any route that goes through a context.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.errors import Refusal
from app.identity.models import Profile
from app.keys.models import Key
from app.keys.scopes import ALL_SCOPES, KeyRole, Scope
from app.regions import OutOfRegion, Region, guard_region


class NoKey(Refusal):
    """This person holds nothing on this profile.

    A profile that does not exist refuses in the same words as one the asker has no key to,
    so that no profile can be found by asking for it.
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
    now: datetime | None = None,
) -> KeyContext:
    """Resolve what this person may see of this profile, in this region, at this moment.

    `region` is the region this deployment serves. A profile pinned elsewhere is refused
    even when its row is present, because a row in the wrong database is the thing we are
    guarding against.
    """
    moment = now or utcnow()
    profile = await session.get(Profile, profile_id)
    if profile is None:
        # There is no profile to pin a line to, so a NoKey leaves nothing at this layer: a
        # stranger cannot put a line into a graph by asking for it, and neither can a guess at
        # an id that does not exist. The same words, the same silence, either way.
        raise NoKey(person_id=person_id, profile_id=profile_id)
    try:
        guard_region(held_in=profile.region, asked_from=region)
    except OutOfRegion:
        # The profile is known, so the refusal is written down against it. The context is the
        # narrowest one there is — no scopes, no key — because nothing was resolved.
        await _record_out_of_region(session, profile=profile, person_id=person_id, now=moment)
        raise

    if profile.owner_person_id == person_id:
        return KeyContext(
            profile_id=profile.id,
            region=profile.region,
            person_id=person_id,
            scopes=ALL_SCOPES,
        )

    keys = await session.scalars(
        select(Key).where(Key.profile_id == profile_id, Key.holder_person_id == person_id)
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
    # A person with no active key holds nothing to pin a line to, either. See NoKey above.
    raise NoKey(person_id=person_id, profile_id=profile_id)


async def _record_out_of_region(
    session: AsyncSession, *, profile: Profile, person_id: uuid.UUID, now: datetime
) -> None:
    """One refused line for a reach across the region pin, in the name of the refusal only."""
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
        refused_because=OutOfRegion.__name__,
        now=now,
    )
