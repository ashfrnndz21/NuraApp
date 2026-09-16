"""The moment of each anchor: when a dose is due now, and when its moment has passed (E04-02).

    Doses render as paper cards at breakfast, dinner, bed; tap records time.

An anchor is never a clock time (`app.medicines.dose.Anchor`); its window is the part of his
day that moment covers, and his day is his own: his breakfast from his settings (the one
breakfast time, `app.routines.breakfast`, read through `app.onboarding.settings.reach_of`),
lunch, dinner and bed from his routine (E10-01, `app.routines.service.day_of`), the defaults
until someone sets them. A tablet's window opens an hour before its anchor and closes where the
routine stops calling the anchor due (`app.routines.service.window_of`) — the same window the
ladder climbs from (E11). Moving breakfast to 08:15 moves the morning tablet's window, and its
Taken card, with it. The client shows a dose as the one thing to do only while its window is
open, and shows the story's missed-dose guidance once the window has closed — it never
composes either from the anchor alone.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from app.medicines.dose import Anchor

if TYPE_CHECKING:
    from app.routines.service import Day


def window_status(
    anchor: Anchor | str, now_local: datetime, taken: bool, day: Day
) -> tuple[bool, bool]:
    """`(due_now, missed)` for one anchor at one moment on his wall clock, on his day. A taken
    dose is neither."""
    if taken:
        return False, False
    # Imported here: the routine module reads the medicines, and the medicines read this.
    from app.routines.service import window_of

    assert now_local.tzinfo is not None  # a moment on his wall clock, never a bare time
    opens, closes = window_of(day, now_local.date(), Anchor(anchor).value, now_local.tzinfo)
    return opens <= now_local < closes, now_local >= closes
