"""Today and this week on the patient's wall clock: what the caps count, what a card's day
and week are, and how a day is said ("Monday 14 September", docs/plain-words.md rule 5).

Apart from `compose` so the self-search (`search`), which compose calls, can name the day and
the week a card is made for without importing compose back.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.db import as_utc, utcnow
from app.delivery.strings import language_for
from app.keys.context import KeyContext
from app.regions import REGION_TZ

WEEKDAYS: Mapping[str, tuple[str, ...]] = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "ms": ("Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"),
    "zh": ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"),
}
MONTHS: Mapping[str, tuple[str, ...]] = {
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "ms": (
        "Januari",
        "Februari",
        "Mac",
        "April",
        "Mei",
        "Jun",
        "Julai",
        "Ogos",
        "September",
        "Oktober",
        "November",
        "Disember",
    ),
}


def plain_day(local: datetime, language: str) -> str:
    """ "Monday 14 September", the way docs/plain-words.md rule 5 says; never "the 14th"."""
    code = language_for(language)
    if code == "zh":
        return f"{local.month}月{local.day}日{WEEKDAYS['zh'][local.weekday()]}"
    return f"{WEEKDAYS[code][local.weekday()]} {local.day} {MONTHS[code][local.month - 1]}"


@dataclass(frozen=True, slots=True)
class Day:
    """Today on the patient's wall clock: the date the caps count, and when it ends."""

    tz: ZoneInfo
    now: datetime
    local: datetime

    @property
    def key(self) -> str:
        return self.local.date().isoformat()

    @property
    def week(self) -> str:
        year, week, _ = self.local.isocalendar()
        return f"{year}-W{week:02d}"

    @property
    def week_starts(self) -> date:
        """The Monday of this week, on his wall clock."""
        return self.local.date() - timedelta(days=self.local.weekday())

    @property
    def week_ends_at(self) -> datetime:
        """Midnight at the end of this Sunday, on his wall clock."""
        sunday_night = datetime.combine(self.week_starts + timedelta(days=7), time(0), self.tz)
        return sunday_night.astimezone(self.now.tzinfo)

    @property
    def starts_at(self) -> datetime:
        """Midnight at the start of today, on his wall clock."""
        return datetime.combine(self.local.date(), time(0), self.tz).astimezone(self.now.tzinfo)

    @property
    def week_starts_at(self) -> datetime:
        """Midnight at the start of this Monday, on his wall clock."""
        return datetime.combine(self.week_starts, time(0), self.tz).astimezone(self.now.tzinfo)

    @property
    def ends_at(self) -> datetime:
        midnight = datetime.combine(self.local.date() + timedelta(days=1), time(0), self.tz)
        return midnight.astimezone(self.now.tzinfo)

    def same_day(self, moment: datetime) -> bool:
        return as_utc(moment).astimezone(self.tz).date() == self.local.date()

    def plain(self, moment: datetime, language: str) -> str:
        return plain_day(as_utc(moment).astimezone(self.tz), language)


def today_for(context: KeyContext) -> Day:
    tz = REGION_TZ[context.region]
    now = utcnow()
    return Day(tz=tz, now=now, local=now.astimezone(tz))
