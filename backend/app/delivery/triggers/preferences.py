"""The settings a profile's deliveries follow, read and changed (E11-05, E11-10, #144).

The owner and his chief change the profile's own default; anyone holding a key reads it. A
change is a new row, checked by `rules.check_settings` — an alert cannot be given a cap or
quiet hours — and the newest row is in force.

Quiet hours and channels differ per person (#144): Mei's weekdays, Kit's weekends. A row's
`for_person_id` is None for the profile's default (E11-05, unchanged) or a recipient's own;
`current(..., mine=True)` and `change(..., mine=True)` are any key holder's own — no family
scope asked, the same self-service footing as leaving a key — and rest on the default until
they set one. `app.delivery.triggers.deliver.Run.config_for` is the engine's own reader; it
does not call here, so a row written here is read the same way there. The log of what went
out (`Delivery`) is the owner's and his chief's to read, narrowed to the parts of the record
their key covers.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import replace
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


async def _newest(
    session: AsyncSession, *, context: KeyContext, for_person_id: uuid.UUID | None
) -> DeliverySettings | None:
    rows = await audited_read(
        session,
        DeliverySettings,
        context,
        Scope.PROFILE,
        where=(DeliverySettings.for_person_id == for_person_id,),
        order_by=(DeliverySettings.set_at.desc(),),
        limit=1,
    )
    return rows[0] if rows else None


async def current(
    session: AsyncSession, *, context: KeyContext, mine: bool = False
) -> tuple[Config, DeliverySettings | None]:
    """The settings in force: the profile's default (`mine=False`, E11-05, unchanged), or
    the caller's own (`mine=True`, #144) — falling back to the default when they have set
    none of their own, so a row here is read the same way `Run.config_for` reads it. His
    day (the routine's own clock) is always the profile's, whichever settings are read."""
    default = await _newest(session, context=context, for_person_id=None)
    own = default
    if mine and not context.is_owner:
        theirs = await _newest(session, context=context, for_person_id=context.person_id)
        if theirs is not None:
            own = theirs
    routine = (
        await current_routine(session, context=context) if context.allows(Scope.MEDICINES) else None
    )
    breakfast = await breakfast_time(session, context=context)
    if own is default:
        return config_of(default, routine, breakfast), own
    return replace(config_of(own), day=config_of(default, routine, breakfast).day), own


async def daily_cap(
    session: AsyncSession,
    *,
    context: KeyContext,
    type: TriggerType,
    for_person_id: uuid.UUID | None = None,
) -> int | None:
    """How many of one type may reach this recipient in a day (#144): their own cap when
    they have set one, else the profile's default, else the rule's; None is never capped.
    The one number the engine sends by, and the smart-nudge planner hands over by
    (`app.delivery.nudges.engine`)."""
    row = await _newest(session, context=context, for_person_id=for_person_id)
    if row is None and for_person_id is not None:
        row = await _newest(session, context=context, for_person_id=None)
    return config_of(row).cap_for(type)


async def change(
    session: AsyncSession,
    *,
    context: KeyContext,
    skip_quiet_days: bool,
    quiet_from: time | None,
    quiet_until: time | None,
    channels: Mapping[str, Sequence[str]],
    caps: Mapping[str, int],
    mine: bool = False,
) -> DeliverySettings:
    """Change the profile's default (`mine=False`, owner or chief, under the family scope,
    unchanged) or the caller's own (`mine=True`, #144) — any key holder, the same
    self-service footing as leaving a key: nobody else's word is asked for a person's own
    quiet hours, so it is written under `Scope.PROFILE`, which every key holds, rather than
    the family scope a plain viewer or caregiver does not."""
    if mine:
        for_person_id = context.person_id
        scope = Scope.PROFILE
    else:
        owner_or_chief(context)
        for_person_id = None
        scope = Scope.FAMILY
    kept_channels, kept_caps = check_settings(channels, caps)
    return await audited_write(
        session,
        DeliverySettings,
        context,
        scope,
        for_person_id=for_person_id,
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
    """What went out, and what was held, newest first: the parts this key covers (`seen_by`)."""
    owner_or_chief(context)
    where = () if day is None else (Delivery.day == day,)
    rows = await audited_read(session, Delivery, context, Scope.FAMILY, where=where)
    return sorted(
        (row for row in rows if seen_by(row, context)),
        key=lambda row: (row.recorded_at, str(row.id)),
        reverse=True,
    )


def seen_by(row: Delivery, context: KeyContext) -> bool:
    """Whether this key sees this row of the log. Its scope, first. Then the evening family
    notice (E11-01) only to the chief it was for, and to him: a chief is told only on a day
    something her key opens was written down, so whether another was told says that a part of
    his record closed to her was written today. And a hold because a red flag is open only
    to a key that opens his emergency lines: the reason is itself a health fact."""
    # Imported here: the day's rules run the engine's delivery, which reads these settings.
    from app.delivery.triggers.day import A_FLAG_IS_OPEN

    if not context.allows(row.scope):
        return False
    if (
        row.trigger_type is TriggerType.FAMILY_NOTICE
        and not context.is_owner
        and row.to_person_id != context.person_id
    ):
        return False
    return row.reason != A_FLAG_IS_OPEN or context.allows(Scope.EMERGENCY)
