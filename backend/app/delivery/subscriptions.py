"""The browsers a person asked to get reminders on (Web Push, ADR 0001).

A subscription is a row of the profile it reminds about, under the face of the graph every
key opens (`Scope.PROFILE`): the person, the login session it came from, the push service's
endpoint and the browser's two keys. The same browser subscribing again replaces the row
before; stopping reminders revokes it; a push service that answers 404 or 410 has forgotten
the endpoint, and so does Nura (`gone_at`). A push goes only to a subscription whose login
session still stands: signing out of a phone ends its reminders with it.
"""

from __future__ import annotations

import binascii
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.delivery.push import unb64url
from app.delivery.triggers.models import PushSubscription
from app.errors import Refusal
from app.identity.models import LoginSession
from app.keys.context import KeyContext
from app.keys.scopes import Scope

TARGET = PushSubscription.__tablename__


class NotAPushSubscription(Refusal):
    """A push subscription is an https endpoint and the browser's two keys, a P-256 point and
    a 16-byte secret. This was not one."""


def _check(endpoint: str, p256dh: str, auth: str) -> None:
    if not endpoint.startswith("https://"):
        raise NotAPushSubscription("a push service's endpoint is an https address")
    try:
        point, secret = unb64url(p256dh), unb64url(auth)
    except (binascii.Error, ValueError) as bad:
        raise NotAPushSubscription("the browser's keys are base64url") from bad
    if len(point) != 65 or point[0] != 4 or len(secret) != 16:
        raise NotAPushSubscription("the browser's keys are a P-256 point and 16 bytes")


async def _mine(
    session: AsyncSession, context: KeyContext, *, endpoint: str
) -> Sequence[PushSubscription]:
    return await audited_read(
        session,
        PushSubscription,
        context,
        Scope.PROFILE,
        where=(
            PushSubscription.person_id == context.person_id,
            PushSubscription.endpoint == endpoint,
            PushSubscription.revoked_at.is_(None),
        ),
    )


async def subscribe(
    session: AsyncSession,
    *,
    context: KeyContext,
    login_id: uuid.UUID,
    endpoint: str,
    p256dh: str,
    auth: str,
) -> PushSubscription:
    """Keep this browser for the caller's reminders about this profile."""
    _check(endpoint, p256dh, auth)
    for earlier in await _mine(session, context, endpoint=endpoint):
        earlier.revoked_at = utcnow()
    return await audited_write(
        session,
        PushSubscription,
        context,
        Scope.PROFILE,
        person_id=context.person_id,
        session_id=login_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
    )


async def unsubscribe(session: AsyncSession, *, context: KeyContext, endpoint: str) -> int:
    """Stop the caller's reminders on this browser; how many subscriptions that revoked."""
    rows = await _mine(session, context, endpoint=endpoint)
    moment = utcnow()
    for row in rows:
        row.revoked_at = moment
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.PROFILE,
        target=TARGET,
        target_id=None,
        rows=len(rows),
        channel=Channel.APP,
    )
    return len(rows)


async def live_for(
    session: AsyncSession, *, context: KeyContext, person_id: uuid.UUID
) -> list[PushSubscription]:
    """The person's subscriptions on this profile a push may go to: not revoked, not gone,
    and from a login session that still stands."""
    rows = await audited_read(
        session,
        PushSubscription,
        context,
        Scope.PROFILE,
        where=(
            PushSubscription.person_id == person_id,
            PushSubscription.revoked_at.is_(None),
            PushSubscription.gone_at.is_(None),
        ),
        channel=Channel.SYSTEM,
    )
    now = utcnow()
    live = []
    for row in rows:
        login = await session.get(LoginSession, row.session_id)
        if login is not None and login.revoked_at is None and as_utc(login.expires_at) > now:
            live.append(row)
    return live


async def forget_gone(session: AsyncSession, device: PushSubscription) -> None:
    """The push service no longer knows this endpoint: neither does Nura."""
    device.gone_at = utcnow()
    await session.flush()
