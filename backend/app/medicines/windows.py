"""The moment of each anchor: when a dose is due now, and when its moment has passed.

An anchor is never a clock time (`app.medicines.dose.Anchor`); the window is the part of his
day that moment covers, in the profile's region. The client shows a dose as the one thing to
do only while its window is open, and shows the story's missed-dose guidance once the window
has closed — it never composes either from the anchor alone.
"""

from __future__ import annotations

from datetime import datetime

from app.medicines.dose import Anchor

WINDOWS: dict[Anchor, tuple[int, int]] = {
    Anchor.BREAKFAST: (5, 11),
    Anchor.LUNCH: (11, 15),
    Anchor.DINNER: (16, 21),
    Anchor.BED: (20, 24),
}
"""Local hours, start inclusive and end exclusive: breakfast 5–11, lunch 11–15, dinner 16–21,
bed 20–24 (dinner and bed overlap for an hour: a late dinner is not yet a missed bed dose)."""


def window_status(anchor: Anchor | str, now_local: datetime, taken: bool) -> tuple[bool, bool]:
    """`(due_now, missed)` for one anchor at one local moment. A taken dose is neither."""
    if taken:
        return False, False
    start, end = WINDOWS[Anchor(anchor)]
    hour = now_local.hour
    return start <= hour < end, hour >= end
