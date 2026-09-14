"""The doors every service reaching profile data goes through.

`app.keys.repository` says who may touch a row. These three say the same thing and write down
that it happened, which is why services call these and not the repository directly: there is
then no way to read, write or share a person's data and leave no trace of it.

A refusal goes through the same door. The scope check is what raises, and the line is written
before the refusal is passed on, so the owner sees the reaching as well as the reads.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Channel, Outcome
from app.audit.trail import record
from app.consent.models import Consent
from app.db import ProfileScoped
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.keys.context import KeyContext, OutOfScope
from app.keys.models import Key
from app.keys.repository import scoped_new, scoped_select
from app.keys.scopes import Scope


async def audited_read[Row: ProfileScoped](
    session: AsyncSession,
    model: type[Row],
    context: KeyContext,
    scope: Scope,
    /,
    *,
    where: Sequence[ColumnElement[bool]] = (),
    channel: Channel = Channel.APP,
    now: datetime | None = None,
) -> Sequence[Row]:
    """Read one profile's rows, and write down that they were read.

    `where` narrows within the profile; it can never widen past it, because the profile
    filter and the scope check come from `scoped_select` in the same expression.
    """
    try:
        statement = scoped_select(model, context, scope).where(*where)
    except OutOfScope as refusal:
        await _refused(
            session, context, Action.READ, scope, model.__tablename__, refusal, channel, now
        )
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
        now=now,
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
    now: datetime | None = None,
    **values: Any,
) -> Row:
    """Add one row to this profile, and write down that it was added."""
    try:
        row = scoped_new(model, context, scope, **values)
    except OutOfScope as refusal:
        await _refused(
            session, context, Action.WRITE, scope, model.__tablename__, refusal, channel, now
        )
        raise
    session.add(row)
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=scope,
        target=model.__tablename__,
        target_id=getattr(row, "id", None),
        rows=1,
        channel=channel,
        now=now,
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
    now: datetime | None = None,
) -> AuditEntry:
    """Write down that a copy of something left, and to whom.

    Nobody shares what they cannot read, so the scope of the thing going out is checked here.
    Whether a channel may send at all is the channel's own check against `Scope.SEND`; this
    records the leaving, it does not open the door.
    """
    try:
        context.require(scope)
    except OutOfScope as refusal:
        await _refused(session, context, Action.SHARE, scope, target, refusal, channel, now)
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
        now=now,
    )


PROFILE_TARGET = Profile.__tablename__


async def audited_profile_read(
    session: AsyncSession,
    context: KeyContext,
    /,
    *,
    channel: Channel = Channel.APP,
    now: datetime | None = None,
) -> Profile:
    """Read the profile row itself — whose graph, its name and language — and write it down.

    The profile is not a row *of* the graph, it is the graph, so `scoped_select` cannot name
    it; this is the one read that reaches it, under `Scope.PROFILE`, which every key holds.
    """
    try:
        context.require(Scope.PROFILE)
    except OutOfScope as refusal:
        await _refused(
            session, context, Action.READ, Scope.PROFILE, PROFILE_TARGET, refusal, channel, now
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
        now=now,
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
    now: datetime | None = None,
) -> str:
    """The display name of someone on this profile: its owner, a holder of a key to it, or
    someone a consent on it names — the person let in, the person who agreed, the witness.

    A Person row is an account, not profile data, so `scoped_select` cannot reach it; this
    is the one read that does, and only for people the profile already names. Whether the
    person is on the profile is itself read through the doors, under `Scope.FAMILY`: the
    key table and the consent table are the family list, and a helper or a clinic holding
    a key to the medicines holds no key to who else is on the record.
    """
    profile = await audited_profile_read(session, context, channel=channel, now=now)
    if person_id != profile.owner_person_id:
        held = await audited_read(
            session,
            Key,
            context,
            Scope.FAMILY,
            where=(Key.holder_person_id == person_id,),
            channel=channel,
            now=now,
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
                now=now,
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
                now=now,
            )
            raise refusal
    person = await session.get(Person, person_id)
    assert person is not None  # a foreign key on the profile or a key names this row
    return person.display_name


async def _refused(
    session: AsyncSession,
    context: KeyContext,
    action: Action,
    scope: Scope,
    target: str,
    refusal: OutOfScope,
    channel: Channel,
    now: datetime | None,
) -> None:
    """One line for a reach that did not land. The name of the refusal, never what it held."""
    await record(
        session,
        context=context,
        action=action,
        scope=scope,
        target=target,
        outcome=Outcome.REFUSED,
        refused_because=type(refusal).__name__,
        channel=channel,
        now=now,
    )
