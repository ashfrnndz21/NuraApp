"""The dev run's clock over HTTP, for end-to-end runs.

    GET  /dev/clock    what the process's clock says, and whether it is frozen
    POST /dev/clock    {"at": "2026-09-14T22:30:00+08:00"} or {"step_seconds": 3600}

A dev run started with NURA_FROZEN_CLOCK stands still at that instant (`app.clock.install_frozen`)
so what the backend says about the hour — the dose windows, the quiet hours, "today" — is the
same whenever the suite runs; a test moves it here to cross the quiet hours or midnight on
purpose. Only on a declared dev run (NURA_DEV_CODE_SENDER=1): anywhere else there is no such
route (404), the same gate as the other dev doors. On a dev run whose clock is the real one,
the clock cannot be moved (409): nothing here turns the real clock into a frozen one.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app import clock
from app.channels.api.deps import settings_of
from app.clock import FrozenClock

router = APIRouter(tags=["dev"])

A_YEAR = 366 * 24 * 3600


class ClockIn(BaseModel):
    """Exactly one: the instant to stand at (with its offset), or seconds to step by."""

    at: datetime | None = None
    step_seconds: int | None = Field(default=None, ge=-A_YEAR, le=A_YEAR)


class ClockOut(BaseModel):
    now: datetime
    frozen: bool


def _dev_run(request: Request) -> None:
    if not settings_of(request).dev_code_sender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


def _out() -> ClockOut:
    return ClockOut(now=clock.now(), frozen=isinstance(clock.current(), FrozenClock))


@router.get("/dev/clock")
async def read_clock(request: Request) -> ClockOut:
    """What the clock says. Dev runs only."""
    _dev_run(request)
    return _out()


@router.post("/dev/clock")
async def move_clock(body: ClockIn, request: Request) -> ClockOut:
    """Stand the frozen clock at another instant, or step it. Dev runs with a frozen clock only."""
    _dev_run(request)
    running = clock.current()
    if not isinstance(running, FrozenClock):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="the clock is not frozen: start with NURA_FROZEN_CLOCK",
        )
    if (body.at is None) == (body.step_seconds is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="give exactly one of at, step_seconds",
        )
    if body.at is not None:
        if body.at.tzinfo is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="at needs an offset"
            )
        running.set(body.at)
    else:
        running.step(timedelta(seconds=body.step_seconds or 0))
    return _out()
