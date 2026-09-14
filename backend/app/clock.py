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


def _in_utc(at: datetime) -> datetime:
    """The instant in UTC. Every timestamp Nura stores is UTC and a database may drop the
    offset (`db.as_utc` reads a bare one back as UTC), so the clock never answers in any other
    zone: 10:00 in Singapore given as `+08:00` is 02:00 UTC here, never a bare 10:00."""
    return at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)


class FrozenClock:
    """A clock that stands still until it is moved. For tests, and for a dev run's
    end-to-end suite (`install_frozen`). It answers in UTC whatever offset it was given."""

    def __init__(self, at: datetime) -> None:
        self._at = _in_utc(at)

    def now(self) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        self._at = _in_utc(at)

    def step(self, by: timedelta) -> datetime:
        self._at += by
        return self._at


class FrozenClockOutsideDev(RuntimeError):
    """A frozen clock asked for outside a declared dev run. Every key window, confirm, expiry
    and "today" would read a moment that is not now; the process refuses to start on it."""


def install_frozen(at: datetime | None, *, dev_run: bool) -> Clock:
    """The clock a process starts on: the real one, or — on a declared dev run given
    NURA_FROZEN_CLOCK — a `FrozenClock` standing at that instant, moved only by `POST
    /dev/clock`. End-to-end runs use it so what the backend says about the hour (the dose
    windows, the quiet hours, "today") does not drift with the hour the suite runs at."""
    if at is None:
        return _clock
    if not dev_run:
        raise FrozenClockOutsideDev(
            "NURA_FROZEN_CLOCK is for a declared dev run only (NURA_DEV_CODE_SENDER=1)"
        )
    if at.tzinfo is None:
        raise FrozenClockOutsideDev(
            "NURA_FROZEN_CLOCK needs an offset, as in 2026-09-14T10:00:00+08:00"
        )
    frozen = FrozenClock(at)
    set_clock(frozen)
    return frozen


_clock: Clock = SystemClock()


def now() -> datetime:
    """The moment, from the one clock this process has."""
    return _clock.now()


def current() -> Clock:
    """The clock in use. Tests reach the frozen one through this to move it from a helper."""
    return _clock


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
