"""The clock. One per process, and never an argument.

Every timestamp Nura writes, and every check against time — a key's window, a confirm's ten
minutes — reads the clock here, never a `now` a caller passed in. A caller-supplied instant
was a way to rewind a revocation or mint a yes that never expires; there is no such argument
any more. Tests swap in a `FrozenClock` and step it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """The real clock, in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """A clock that stands still until it is moved. For tests."""

    def __init__(self, at: datetime) -> None:
        self._at = at if at.tzinfo is not None else at.replace(tzinfo=UTC)

    def now(self) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        self._at = at if at.tzinfo is not None else at.replace(tzinfo=UTC)

    def step(self, by: timedelta) -> datetime:
        self._at += by
        return self._at


_clock: Clock = SystemClock()


def now() -> datetime:
    """The moment, from the one clock this process has."""
    return _clock.now()


def set_clock(clock: Clock) -> None:
    global _clock
    _clock = clock


@contextmanager
def use_clock(clock: Clock) -> Iterator[Clock]:
    """Run with another clock, then put the one before back."""
    global _clock
    before = _clock
    _clock = clock
    try:
        yield clock
    finally:
        _clock = before
