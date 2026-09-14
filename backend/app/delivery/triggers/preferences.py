"""The settings a profile's deliveries follow, read and changed (E11-05, E11-10).

The owner and his chief change them; anyone holding a key reads them. The times of his day
are E10-01's routine (`app.routines`), read here and set there. A change is a new row, checked by
`rules.check_settings` — an alert cannot be given a cap or quiet hours — and the newest row
is in force. The log of what went out (`Delivery`) is the owner's and his chief's to read,
narrowed to the parts of the record their key covers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.audit.trail import NotTheirsToRead
from app.db import utcnow
from app.delivery.triggers.models import Delivery, DeliverySettings, TriggerType
from app.delivery.triggers.rules import Config, check_settings, config_of
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.routines.breakfast import breakfast_time
from app.routines.service import current_routine


def owner_or_chief(context: KeyContext) -> None:
    """The patient, the steward holding his graph, and the chief he named."""
    if context.is_owner or context.is_steward:
        return
    if context.role is not KeyRole.CHIEF:
        raise NotTheirsToRead(f"a {context.role} key does not change or read the deliveries")
    context.require(Scope.FAMILY)


async def current(
    session: AsyncSession, *, context: KeyContext
) -> tuple[Config, DeliverySettings | None]:
    rows = await audited_read(
        session,
        DeliverySettings,
        context,
        Scope.PROFILE,
        order_by=(DeliverySettings.set_at.desc(),),
        limit=1,
    )
    row = rows[0] if rows else None
    routine = await current_routine(session, context=context) if context.allows(Scope.MEDICINES) else None
    return config_of(row, routine, await breakfast_time(session, context=context)), row


async def daily_cap(session: AsyncSession, *, context: KeyContext, type: TriggerType) -> int | None:
    """How many of one type may reach him in a day: the delivery settings' cap, else the
    rule's; None is never capped. The one number the engine sends by, and the smart-nudge
    planner hands over by (`app.delivery.nudges.engine`): one cap on what reaches him."""
    rows = await audited_read(
        session,
        DeliverySettings,
        context,
        Scope.PROFILE,
        order_by=(DeliverySettings.set_at.desc(),),
        limit=1,
    )
    return config_of(rows[0] if rows else None).cap_for(type)


async def change(
    session: AsyncSession,
    *,
    context: KeyContext,
    skip_quiet_days: bool,
    quiet_from: time | None,
    quiet_until: time | None,
    channels: Mapping[str, Sequence[str]],
    caps: Mapping[str, int],
) -> DeliverySettings:
    owner_or_chief(context)
    kept_channels, kept_caps = check_settings(channels, caps)
    return await audited_write(
        session,
        DeliverySettings,
        context,
        Scope.FAMILY,
        skip_quiet_days=skip_quiet_days,
        quiet_from=None if quiet_from is None else quiet_from.replace(tzinfo=None),
        quiet_until=None if quiet_until is None else quiet_until.replace(tzinfo=None),
        channels=kept_channels,
        caps=kept_caps,
        set_by_person_id=context.person_id,
        set_at=utcnow(),
    )


async def log(
    session: AsyncSession, *, context: KeyContext, day: str | None = None
) -> list[Delivery]:
    """What went out, and what was held, newest first: the parts this key covers."""
    owner_or_chief(context)
    where = () if day is None else (Delivery.day == day,)
    rows = await audited_read(session, Delivery, context, Scope.FAMILY, where=where)
    return sorted(
        (row for row in rows if context.allows(row.scope)),
        key=lambda row: (row.recorded_at, str(row.id)),
        reverse=True,
    )
