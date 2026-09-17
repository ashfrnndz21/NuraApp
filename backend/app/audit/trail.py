"""Writing the trail, and reading it back.

`record` is the only writer. It is the one place in Nura that puts a row on a profile without
going through `app.keys.repository`, and it has to be: a reach that was refused must still be
written down, and the person who was refused holds nothing the scope check would let through.
It is the floor of the enforcement, beside the keys, not a caller of them.

`read_audit` is the other half of the promise. The trail belongs to the patient: he reads it,
and the chief he named reads it, and nobody else — a caregiver holding a key to the medicines
holds no key to the record of who else read them.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Channel, Outcome
from app.db import keep_on_refusal, utcnow
from app.errors import Refusal
from app.keys.context import KeyContext, OutOfScope, Standing
from app.keys.repository import scoped_select
from app.keys.scopes import KeyRole, Scope

AUDIT_TARGET = AuditEntry.__tablename__
"""Reading the trail is itself a reach into the graph, so it is written down like any other."""


class NotTheirsToRead(Refusal):
    """The trail is the patient's own. Only he and the chief he named may read it."""


async def record(
    session: AsyncSession,
    *,
    context: KeyContext,
    action: Action,
    scope: Scope,
    target: str,
    outcome: Outcome = Outcome.ALLOWED,
    channel: Channel = Channel.APP,
    rows: int = 0,
    target_id: uuid.UUID | None = None,
    refused_because: str | None = None,
    shared_with_person_id: uuid.UUID | None = None,
    shared_with_label: str | None = None,
) -> AuditEntry:
    """Write one line of the trail.

    The entry is pinned to the profile in the context, so a person with no context — nobody
    resolved a key for them — cannot put a line into a graph they hold nothing on.

    An ALLOWED line is written in the same transaction as the access it records, so a write
    that is rolled back leaves behind no claim that it happened. A REFUSED line is the
    opposite case: the refusal is an exception, the unit of work that carried it is rolled
    back, and the line must land anyway. So it is flushed now, and a keeper is registered
    (`app.db.keep_on_refusal`) that writes an equivalent line again once the channel has
    rolled the unit back — the reaching is seen whether or not anything else survived.
    """
    # Nura's own reach (the delivery engine) is written as the system's: no person as the
    # actor, the system channel, whatever door it came through (`keys.context.as_the_system`).
    system = context.standing is Standing.SYSTEM
    values: dict[str, Any] = {
        "profile_id": context.profile_id,
        "at": utcnow(),
        "actor_person_id": None if system else context.person_id,
        "actor_role": None if system else context.role,
        "key_id": None if system else context.key_id,
        "action": action,
        "scope": scope,
        "channel": Channel.SYSTEM if system else channel,
        "target": target,
        "target_id": target_id,
        "rows": rows,
        "outcome": outcome,
        "refused_because": refused_because,
        "shared_with_person_id": shared_with_person_id,
        "shared_with_label": shared_with_label,
    }
    entry = AuditEntry(**values)
    session.add(entry)
    await session.flush()
    if outcome is Outcome.REFUSED:

        async def keep(again: AsyncSession) -> None:
            again.add(AuditEntry(**values))
            await again.flush()

        keep_on_refusal(session, keep)
    return entry


def _may_read_the_trail(context: KeyContext) -> None:
    """The patient, and the chief he named. A key to a part of the record is not this key."""
    if context.is_owner:
        return
    if context.role is not KeyRole.CHIEF:
        raise NotTheirsToRead(f"a {context.role} key does not open the record of who read what")
    # A chief cut narrower than the family scope does not reach it either.
    context.require(Scope.FAMILY)


async def read_audit(
    session: AsyncSession,
    *,
    context: KeyContext,
    action: Action | None = None,
    scope: Scope | None = None,
    actor_person_id: uuid.UUID | None = None,
    since: datetime | None = None,
    limit: int = 200,
    channel: Channel = Channel.APP,
) -> Sequence[AuditEntry]:
    """Every access to this profile, newest first, narrowed by who, what, which part and when.

    A refused attempt to read the trail is written down too, so the patient sees the reaching
    as well as the reads.
    """
    try:
        _may_read_the_trail(context)
    except (OutOfScope, NotTheirsToRead) as refusal:
        await record(
            session,
            context=context,
            action=Action.READ,
            scope=Scope.FAMILY,
            target=AUDIT_TARGET,
            outcome=Outcome.REFUSED,
            refused_because=type(refusal).__name__,
            channel=channel,
        )
        raise

    statement = scoped_select(AuditEntry, context, Scope.FAMILY)
    if action is not None:
        statement = statement.where(AuditEntry.action == action)
    if scope is not None:
        statement = statement.where(AuditEntry.scope == scope)
    if actor_person_id is not None:
        statement = statement.where(AuditEntry.actor_person_id == actor_person_id)
    if since is not None:
        statement = statement.where(AuditEntry.at >= since)
    # `.seq` breaks a tie in `at` (two lines in one request, or any frozen clock —
    # #192/#218): the trail's whole point is telling him what happened in what order, so a
    # merely stable-but-arbitrary tiebreaker is not enough — it needs the real one.
    found = (
        await session.scalars(
            statement.order_by(AuditEntry.at.desc(), AuditEntry.seq.desc()).limit(limit)
        )
    ).all()

    # After the query, so that reading the trail never returns the line about reading it.
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=Scope.FAMILY,
        target=AUDIT_TARGET,
        rows=len(found),
        channel=channel,
    )
    return found
