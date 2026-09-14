"""One breakfast time (E01, E10, E11): the moment his day's tablets, prompt and card share.

His settings say when he has breakfast (E01, `ProfileSettings.breakfast_time`); before he has
said, the routine's own breakfast anchor stands (E10); before either, 07:30 on his wall clock.
`breakfast_time` is the one place that is read: the routine's breakfast anchor
(`app.routines.service.day_of`), the first week's schedule (`app.onboarding.plan`) and the
morning card (`app.delivery.triggers`) all ask it, so the day's prompt and the morning card
always come at the same moment, and a change to his settings moves all three.

His settings are read through `app.onboarding.settings.reach_of`, the same row and the
same field `GET /profiles/{id}/settings` serves (the web's About you), under the face of the
graph every key opens — his breakfast time is how to reach him, not his health; the routine
under the medicines, where it is kept.
"""

from __future__ import annotations

import re
from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import as_utc
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.routines.models import Routine

DEFAULT = time(7, 30)
"""Breakfast before he or his routine has said: half past seven on his clock."""

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _clock(text: str | None) -> time | None:
    match = _HHMM.match(text or "")
    return None if match is None else time(int(match.group(1)), int(match.group(2)))


async def breakfast_time(session: AsyncSession, *, context: KeyContext) -> time:
    """His settings' breakfast, else the routine's breakfast anchor, else 07:30."""
    # Imported here: `app.onboarding` wires its plan at import, and the plan asks this module.
    from app.onboarding.settings import reach_of

    said = (await reach_of(session, context=context)).breakfast
    if said is not None:
        return said
    if context.allows(Scope.MEDICINES):
        days = await audited_read(
            session, Routine, context, Scope.MEDICINES, where=(Routine.superseded_at.is_(None),)
        )
        if days:
            anchor = _clock(max(days, key=lambda row: as_utc(row.set_at)).anchors.get("breakfast"))
            if anchor is not None:
                return anchor
    return DEFAULT
