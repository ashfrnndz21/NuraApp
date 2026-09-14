"""The calendar, as Nura reads it: a port with no way to write, and two readers behind it.

`CalendarSource` has one method, `events`, and nothing else: there is no call that could
add, change or delete an event in anyone's calendar (docs/read-only-connectors.md §2).
`FixtureCalendar` answers from events it was given; `IcsFileCalendar` reads an iCalendar file
a person uploaded (RFC 5545), in memory, with the standard library.

What is read off an event is its summary, when it starts, where, its UID and whether it was
cancelled — and nothing else. Attendees, the organiser, the description, alarms and
attachments are skipped by the parser and never reach a `CalendarEvent`, so no other
person's name can be kept by anything downstream (§2, "third parties stay out"). A
recurring event is read as its first occurrence.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.errors import Refusal
from app.fixtures import fixture

MAX_ICS_BYTES = 256 * 1024
"""A family's calendar export for a year is well under this; anything larger is refused."""

KEPT = frozenset({"SUMMARY", "DTSTART", "LOCATION", "UID", "STATUS"})
"""The only properties of an event that are read. Everything else is skipped unread."""


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """One event, as much of it as Nura reads: never who else is in it."""

    uid: str | None
    summary: str
    starts_at: datetime
    all_day: bool = False
    location: str | None = None
    cancelled: bool = False


class CalendarSource(Protocol):
    """A calendar Nura may read. Read-only by construction: this is the whole port."""

    async def events(self, *, since: datetime, until: datetime) -> Sequence[CalendarEvent]: ...


class NotACalendar(Refusal):
    """The file is not an iCalendar file this reader can read, or it is too large."""


@fixture
class FixtureCalendar:
    """A calendar that answers from the events it was given. For tests."""

    def __init__(self, events: Sequence[CalendarEvent]) -> None:
        self._events = tuple(events)

    async def events(self, *, since: datetime, until: datetime) -> Sequence[CalendarEvent]:
        return [e for e in self._events if since <= e.starts_at < until]


class IcsFileCalendar:
    """An uploaded .ics file, read in memory for the one request it came with and not kept.

    It is read when the scan asks for its events, inside the scan's audited door, so a file
    that is not a calendar is refused (`NotACalendar`) and the refusal is on the trail."""

    def __init__(self, data: bytes, *, zone: ZoneInfo) -> None:
        self._data = data
        self._zone = zone

    async def events(self, *, since: datetime, until: datetime) -> Sequence[CalendarEvent]:
        return [e for e in parse_ics(self._data, zone=self._zone) if since <= e.starts_at < until]


_DATE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_DATE_TIME = re.compile(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)$")


def _unescape(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append(" " if nxt in "nN" else nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return " ".join("".join(out).split())


def _split(line: str) -> tuple[str, dict[str, str], str] | None:
    """`NAME;PARAM=V;P2="a:b":value` → (NAME, params, value). A colon inside quotes is not the
    separator."""
    quoted = False
    for index, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ":" and not quoted:
            head, value = line[:index], line[index + 1 :]
            parts = head.split(";")
            params: dict[str, str] = {}
            for part in parts[1:]:
                key, _, val = part.partition("=")
                params[key.upper()] = val.strip('"')
            return parts[0].upper(), params, value
    return None


def _start(value: str, params: dict[str, str], zone: ZoneInfo) -> tuple[datetime, bool] | None:
    value = value.strip()
    day = _DATE.match(value)
    if day is not None or params.get("VALUE", "").upper() == "DATE":
        if day is None:
            return None
        on = date(int(day.group(1)), int(day.group(2)), int(day.group(3)))
        return datetime.combine(on, time.min, tzinfo=zone).astimezone(UTC), True
    moment = _DATE_TIME.match(value)
    if moment is None:
        return None
    y, mo, d, h, mi, s, utc = moment.groups()
    where = zone
    if utc:
        where = ZoneInfo("UTC")
    elif "TZID" in params:
        try:
            where = ZoneInfo(params["TZID"])
        except (ZoneInfoNotFoundError, ValueError):
            where = zone
    # A time with no zone is on the profile's wall clock; with TZID, on that zone's; with Z, UTC.
    local = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), tzinfo=where)
    return local.astimezone(UTC), False


def parse_ics(data: bytes, *, zone: ZoneInfo) -> list[CalendarEvent]:
    """The events in an iCalendar file: summary, start, location, UID, whether cancelled.

    Lines are unfolded (RFC 5545 §3.1); only properties directly on a VEVENT are read, so an
    alarm's own summary or description inside it is not; an event with no summary or no
    start it can read is skipped. A time with no zone is on the profile's wall clock (`zone`).
    """
    if len(data) > MAX_ICS_BYTES:
        raise NotACalendar(f"a calendar file is at most {MAX_ICS_BYTES} bytes")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as not_text:
        raise NotACalendar("a calendar file is UTF-8 text") from not_text
    unfolded = re.sub(r"\r?\n[ \t]", "", text)
    lines = [line for line in re.split(r"\r?\n", unfolded) if line]
    if not lines or lines[0].strip().upper() != "BEGIN:VCALENDAR":
        raise NotACalendar("a calendar file begins with BEGIN:VCALENDAR")
    events: list[CalendarEvent] = []
    stack: list[str] = []
    props: dict[str, tuple[dict[str, str], str]] = {}
    for line in lines:
        parsed = _split(line)
        if parsed is None:
            continue
        name, params, value = parsed
        if name == "BEGIN":
            stack.append(value.strip().upper())
            if stack[-1] == "VEVENT":
                props = {}
            continue
        if name == "END":
            ending = value.strip().upper()
            if stack and stack[-1] == ending:
                stack.pop()
            if ending == "VEVENT":
                event = _event(props, zone)
                if event is not None:
                    events.append(event)
            continue
        if stack and stack[-1] == "VEVENT" and name in KEPT and name not in props:
            props[name] = (params, value)
    return events


def _event(props: dict[str, tuple[dict[str, str], str]], zone: ZoneInfo) -> CalendarEvent | None:
    if "SUMMARY" not in props or "DTSTART" not in props:
        return None
    summary = _unescape(props["SUMMARY"][1])
    started = _start(props["DTSTART"][1], props["DTSTART"][0], zone)
    if not summary or started is None:
        return None
    location = _unescape(props["LOCATION"][1]) if "LOCATION" in props else None
    uid = props["UID"][1].strip() if "UID" in props else None
    status = props["STATUS"][1].strip().upper() if "STATUS" in props else ""
    return CalendarEvent(
        uid=uid or None,
        summary=summary,
        starts_at=started[0],
        all_day=started[1],
        location=location or None,
        cancelled=status == "CANCELLED",
    )
