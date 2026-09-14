"""The day and the hour, the way he says them, in his three languages.

"Thursday 7 September 2023" for a paper from another year, "Thursday 24 September" for a
visit this year, "10 in the morning" for an hour — never "10:00", never "the 7th" (plain
words, rule 5). The day and month names are the medicines module's, so the words are the
same everywhere he reads a date.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, time

from app.medicines.strings import DAY_NAMES, MONTH_NAMES, say_date

# @patient phrase
PART_OF_DAY: Mapping[str, tuple[str, str, str, str]] = {
    # (morning, afternoon, evening, night)
    "en": ("in the morning", "in the afternoon", "in the evening", "at night"),
    "ms": ("pagi", "petang", "malam", "malam"),
    "zh": ("上午", "下午", "晚上", "晚上"),
}


def say_day(day: date, language: str, *, with_year: bool = False) -> str:
    """'Thursday 7 September', or with the year for a day in another year."""
    if not with_year:
        return say_date(day, language)
    weekday = DAY_NAMES[language][day.weekday()]
    month = MONTH_NAMES[language][day.month - 1]
    if language == "zh":
        return f"{day.year}年{month}{day.day}日{weekday}"
    return f"{weekday} {day.day} {month} {day.year}"


def _part(hour: int) -> int:
    if hour < 12:
        return 0
    if hour < 17:
        return 1
    if hour < 21:
        return 2
    return 3


def say_clock(moment: time, language: str) -> str:
    """'7 in the morning', 'half past 7 in the morning', '7.15 in the evening'; in Malay
    'pukul 7 pagi', in Chinese '上午7点半'. Twelve-hour, digits, never a colon."""
    part = PART_OF_DAY[language][_part(moment.hour)]
    hour = moment.hour % 12 or 12
    if language == "zh":
        minutes = "" if moment.minute == 0 else ("半" if moment.minute == 30 else f"{moment.minute}分")
        return f"{part}{hour}点{minutes}"
    if language == "ms":
        clock = f"{hour}" if moment.minute == 0 else f"{hour}.{moment.minute:02d}"
        return f"pukul {clock} {part}"
    if moment.minute == 0:
        return f"{hour} {part}"
    if moment.minute == 30:
        return f"half past {hour} {part}"
    return f"{hour}.{moment.minute:02d} {part}"
