"""Cutting, listing and closing keys.

Binding does not share the account: it cuts a key per person with a role, a scope, a window
and a recorded basis. Only the owner or a chief may cut one, and nobody may cut a key wider
than the one they hold.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.errors import Refusal
from app.identity.models import Person
from app.keys.context import KeyContext
from app.keys.models import Key
from app.keys.repository import scoped_new, scoped_select
from app.keys.scopes import DEFAULT_WINDOW, ROLE_SCOPES, KeyRole, KeyWindow, Scope, window_ends_at


class NotTheirKeyToCut(Refusal):
    """Only the owner of the graph, or a chief he named, may bind someone to it."""


class NoKeyToClose(Refusal):
    """There is no such key on this profile."""


def _may_cut_keys(context: KeyContext) -> None:
    context.require(Scope.FAMILY)
    if not context.is_owner and context.role is not KeyRole.CHIEF:
        raise NotTheirKeyToCut(f"a {context.role} key cannot cut another key")


async def grant_key(
    session: AsyncSession,
    *,
    context: KeyContext,
    holder: Person,
    role: KeyRole,
    basis: str,
    scopes: Iterable[Scope] | None = None,
    window: KeyWindow | None = None,
    now: datetime | None = None,
) -> Key:
    """Cut a key for one person on the profile in the context.

    `scopes` narrows the role's preset; it can never widen past what the granter holds.
    `basis` is what the grant rests on — the owner's recorded consent, an LPA, a letter.
    Consent itself is recorded by the consent service (E00-02); this only names the basis.
    """
    _may_cut_keys(context)
    moment = now or utcnow()
    asked = frozenset(scopes) if scopes is not None else ROLE_SCOPES[role]
    granted = asked & context.scopes

    # One person holds one key on one profile: a new key replaces the one before it.
    for existing in await session.scalars(scoped_select(Key, context, Scope.FAMILY)):
        if existing.holder_person_id == holder.id and existing.is_active(moment):
            existing.revoked_at = moment

    key = scoped_new(
        Key,
        context,
        Scope.FAMILY,
        holder_person_id=holder.id,
        role=role,
        scopes=sorted(scope.value for scope in granted),
        basis=basis,
        granted_by_person_id=context.person_id,
        granted_at=moment,
        expires_at=window_ends_at(window or DEFAULT_WINDOW[role], moment),
    )
    session.add(key)
    await session.flush()
    return key


async def list_keys(session: AsyncSession, *, context: KeyContext) -> Sequence[Key]:
    """Every key ever cut on this profile, so the owner can read who holds what."""
    result = await session.scalars(scoped_select(Key, context, Scope.FAMILY))
    return result.all()


async def revoke_key(
    session: AsyncSession,
    *,
    context: KeyContext,
    key_id: uuid.UUID,
    now: datetime | None = None,
) -> Key:
    """Close a key. The row stays, so the owner can still read that it was held."""
    _may_cut_keys(context)
    key = await session.scalar(scoped_select(Key, context, Scope.FAMILY).where(Key.id == key_id))
    if key is None:
        raise NoKeyToClose(f"no key {key_id} on profile {context.profile_id}")
    if key.revoked_at is None:
        key.revoked_at = now or utcnow()
    await session.flush()
    return key
