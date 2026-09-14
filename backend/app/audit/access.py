"""The doors every service reaching profile data goes through.

`app.keys.repository` says who may touch a row. These three say the same thing and write down
that it happened, which is why services call these and not the repository directly: there is
then no way to read, write or share a person's data and leave no trace of it.

A refusal goes through the same door. The scope check is what raises, and the line is written
before the refusal is passed on, so the owner sees the reaching as well as the reads. The same
holds for any other refusal raised while the profile is known — the region pin, a rule about
what may replace what, a reach at a row on another profile: every service function stands
behind `audited`, one door for the whole call, so whatever it refuses leaves a line. A refusal
that has already been written down (`Refusal.written_down`) passes through the outer doors
without a second line.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any, cast

from sqlalchemy import Column, ColumnElement, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.visitors import iterate

from app.audit.models import Action, AuditEntry, Channel, Outcome
from app.audit.trail import record
from app.consent.models import Consent
from app.db import ProfileScoped
from app.errors import Refusal
from app.identity.models import Person, Profile, Stewardship
from app.keys.context import KeyContext, OutOfScope
from app.keys.models import Key
from app.keys.repository import scoped_new, scoped_select
from app.keys.scopes import Scope


class WidenedRead(Refusal):
    """A read that would have reached past the one table the scope check was made against."""


def _stays_on_one_table(table: str, order_by: Sequence[ColumnElement[Any]]) -> None:
    """Refuse an ordering that names a column of any table but the one being read."""
    for element in order_by:
        for part in iterate(element):
            if isinstance(part, Column) and part.table.name != table:
                raise WidenedRead(f"a read of {table} only orders by its own columns")


async def audited_read[Row: ProfileScoped](
    session: AsyncSession,
    model: type[Row],
    context: KeyContext,
    scope: Scope,
    /,
    *,
    where: Sequence[ColumnElement[bool]] = (),
    order_by: Sequence[ColumnElement[Any]] = (),
    limit: int | None = None,
    channel: Channel = Channel.APP,
) -> Sequence[Row]:
    """Read one profile's rows, and write down that they were read.

    `where` narrows within the profile; it can never widen past it, because the profile
    filter and the scope check come from `scoped_select` in the same expression. `order_by`
    and `limit` narrow further still — they can only bring back fewer rows than the profile
    filter already allows — and the line written down says how many actually came back.

    An `order_by` naming a column of another table would join that table in and let rows the
    key does not cover decide which row comes back, so the statement is checked for having
    stayed on the one table before it runs.
    """
    try:
        statement = scoped_select(model, context, scope).where(*where).order_by(*order_by)
        if limit is not None:
            statement = statement.limit(limit)
        _stays_on_one_table(model.__tablename__, order_by)
    except Refusal as refusal:
        await _refused(session, context, Action.READ, scope, model.__tablename__, refusal, channel)
        raise
    found = (await session.scalars(statement)).all()
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=scope,
        target=model.__tablename__,
        rows=len(found),
        channel=channel,
    )
    return found


async def audited_write[Row: ProfileScoped](
    session: AsyncSession,
    model: type[Row],
    context: KeyContext,
    scope: Scope,
    /,
    *,
    channel: Channel = Channel.APP,
    name_the_row: bool = True,
    **values: Any,
) -> Row:
    """Add one row to this profile, and write down that it was added.

    `name_the_row=False` keeps the new row's id off the line: for a row whose id is itself
    a thing to be used, a yes, and must not be readable from the trail.
    """
    try:
        row = scoped_new(model, context, scope, **values)
    except Refusal as refusal:
        await _refused(session, context, Action.WRITE, scope, model.__tablename__, refusal, channel)
        raise
    session.add(row)
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=scope,
        target=model.__tablename__,
        target_id=getattr(row, "id", None) if name_the_row else None,
        rows=1,
        channel=channel,
    )
    return row


async def record_share(
    session: AsyncSession,
    *,
    context: KeyContext,
    scope: Scope,
    target: str,
    channel: Channel,
    shared_with_person_id: uuid.UUID | None = None,
    shared_with_label: str | None = None,
    target_id: uuid.UUID | None = None,
) -> AuditEntry:
    """Write down that a copy of something left, and to whom.

    Nobody shares what they cannot read, so the scope of the thing going out is checked here.
    Whether a channel may send at all is the channel's own check against `Scope.SEND`; this
    records the leaving, it does not open the door.
    """
    try:
        context.require(scope)
    except Refusal as refusal:
        await _refused(session, context, Action.SHARE, scope, target, refusal, channel)
        raise
    return await record(
        session,
        context=context,
        action=Action.SHARE,
        scope=scope,
        target=target,
        target_id=target_id,
        rows=1,
        channel=channel,
        shared_with_person_id=shared_with_person_id,
        shared_with_label=shared_with_label,
    )


@asynccontextmanager
async def audited_guard(
    session: AsyncSession,
    context: KeyContext,
    action: Action,
    scope: Scope,
    target: str,
    /,
    *,
    channel: Channel = Channel.APP,
) -> AsyncIterator[None]:
    """Run a check that may refuse, and if it does, write the refusal down before passing it on.

    For the checks that fire before or after a row is reached — the region pin on an artefact,
    the rule that a person's word is not overwritten by a machine's — so that a refusal raised
    while the profile is known is as visible to the owner as a scope refusal is. The line
    carries the name of the refusal and nothing it held.
    """
    try:
        yield
    except Refusal as refusal:
        await _refused(session, context, action, scope, target, refusal, channel)
        raise


ScopeOf = Scope | Callable[[dict[str, Any]], Scope]
"""A door's scope: fixed, or worked out from the call's keywords (a fact's subject)."""


def audited[**P, R](
    action: Action, scope: ScopeOf, target: str, /
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """The door on a service function: one `audited_guard` around the whole call.

    The function takes the session first and `context` by keyword, as every service here
    does. The scope is checked at the door, before the body runs — so nothing in the body, a
    confirm being used least of all, happens for a caller the scope does not cover.
    Whatever the body then refuses — a reach at another profile's row, a rule, a format — is
    written down against the profile in the context before it is passed on.
    """

    def door(service: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(service)
        async def guarded(*args: P.args, **kwargs: P.kwargs) -> R:
            session = cast(AsyncSession, args[0])
            context = cast(KeyContext, kwargs["context"])
            required = scope if isinstance(scope, Scope) else scope(cast(dict[str, Any], kwargs))
            async with audited_guard(session, context, action, required, target):
                context.require(required)
                return await service(*args, **kwargs)

        return guarded

    return door


async def _refused(
    session: AsyncSession,
    context: KeyContext,
    action: Action,
    scope: Scope,
    target: str,
    refusal: Refusal,
    channel: Channel,
) -> None:
    """One line for a reach that did not land. The name of the refusal, never what it held."""
    if refusal.written_down:
        return
    refusal.written_down = True
    await record(
        session,
        context=context,
        action=action,
        scope=scope,
        target=target,
        outcome=Outcome.REFUSED,
        refused_because=type(refusal).__name__,
        channel=channel,
    )


PROFILE_TARGET = Profile.__tablename__


async def audited_profile_read(
    session: AsyncSession,
    context: KeyContext,
    /,
    *,
    channel: Channel = Channel.APP,
) -> Profile:
    """Read the profile row itself — whose graph, its name and language — and write it down.

    The profile is not a row *of* the graph, it is the graph, so `scoped_select` cannot name
    it; this is the one read that reaches it, under `Scope.PROFILE`, which every key holds.
    """
    try:
        context.require(Scope.PROFILE)
    except OutOfScope as refusal:
        await _refused(
            session, context, Action.READ, Scope.PROFILE, PROFILE_TARGET, refusal, channel
        )
        raise
    profile = await session.get(Profile, context.profile_id)
    assert profile is not None  # the context was resolved from this row
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=Scope.PROFILE,
        target=PROFILE_TARGET,
        target_id=profile.id,
        rows=1,
        channel=channel,
    )
    return profile


class NotOnThisProfile(Refusal):
    """Not the owner, not a key holder, not named by a consent here: no name to give."""


async def person_display_name(
    session: AsyncSession,
    context: KeyContext,
    person_id: uuid.UUID,
    /,
    *,
    channel: Channel = Channel.APP,
) -> str:
    """The display name of someone on this profile: its owner, the steward holding it for him
    until he claims it, a holder of a key to it, or someone a consent on it names — the
    person let in, the person who agreed, the witness.

    A Person row is an account, not profile data, so `scoped_select` cannot reach it; this
    is the one read that does, and only for people the profile already names. Whether the
    person is on the profile is itself read through the doors: the steward under
    `Scope.PROFILE`, because who holds the graph is part of whose graph it is, like the
    owner; everyone else under `Scope.FAMILY`, because the key table and the consent
    table are the family list, and a helper or a clinic holding a key to the medicines
    holds no key to who else is on the record.
    """
    profile = await audited_profile_read(session, context, channel=channel)
    stewarded_by = (
        await audited_read(
            session,
            Stewardship,
            context,
            Scope.PROFILE,
            where=(Stewardship.steward_person_id == person_id,),
            channel=channel,
        )
        if person_id != profile.owner_person_id
        else ()
    )
    if person_id != profile.owner_person_id and not stewarded_by:
        held = await audited_read(
            session,
            Key,
            context,
            Scope.FAMILY,
            where=(Key.holder_person_id == person_id,),
            channel=channel,
        )
        named_by_a_consent = (
            await audited_read(
                session,
                Consent,
                context,
                Scope.FAMILY,
                where=(
                    or_(
                        Consent.holder_person_id == person_id,
                        Consent.person_id == person_id,
                        Consent.witness_person_id == person_id,
                    ),
                ),
                channel=channel,
            )
            if not held
            else ()
        )
        if not held and not named_by_a_consent:
            refusal = NotOnThisProfile(f"person {person_id} is not on profile {profile.id}")
            await record(
                session,
                context=context,
                action=Action.READ,
                scope=Scope.FAMILY,
                target=Person.__tablename__,
                outcome=Outcome.REFUSED,
                refused_because=type(refusal).__name__,
                channel=channel,
            )
            raise refusal
    person = await session.get(Person, person_id)
    assert person is not None  # a foreign key on the profile or a key names this row
    return person.display_name
