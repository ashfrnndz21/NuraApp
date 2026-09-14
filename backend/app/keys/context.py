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
from app.regions import Region, guard_region


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
        raise NoKey(person_id=person_id, profile_id=profile_id)
    guard_region(held_in=profile.region, asked_from=region)

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
    raise NoKey(person_id=person_id, profile_id=profile_id)
