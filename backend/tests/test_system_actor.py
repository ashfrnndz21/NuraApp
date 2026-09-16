"""The delivery engine's reach is Nura's own, not the patient's (E11, the review of #121).

Its reads and writes are written with no person as the actor and on the system channel,
whatever door they came through; the table refuses a line with no actor on any other channel;
and the trail he reads folds the day's checks into one line in his words, which the chief can
open to see what was checked and how often.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Channel, Outcome
from app.audit.trail import record
from app.clock import FrozenClock
from app.delivery.triggers.engine import run_due
from app.family.trail import trail
from app.keys.context import as_the_system
from app.keys.scopes import Scope
from tests.delivery_support import home

SGT = ZoneInfo("Asia/Singapore")


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 14, hour, minute, tzinfo=SGT).astimezone(UTC)


async def test_the_engines_reach_is_the_systems_and_his_trail_folds_it(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    for when in (at(7, 1), at(8, 31), at(9, 1), at(9, 31)):
        clock.set(when)
        await run_due(sg, via=h.via, profile_id=h.owner.profile_id, at=when)

    systems = (
        await sg.scalars(
            select(AuditEntry).where(
                AuditEntry.profile_id == h.owner.profile_id, AuditEntry.actor_person_id.is_(None)
            )
        )
    ).all()
    assert systems and all(entry.channel is Channel.SYSTEM for entry in systems)
    assert all(entry.key_id is None and entry.actor_role is None for entry in systems)
    assert {entry.action for entry in systems} >= {Action.READ, Action.WRITE, Action.SHARE}

    days = await trail(sg, context=h.owner)
    [today] = [day for day in days if day.day == date(2026, 9, 14)]
    folded = [line for line in today.lines if line.sentences[0].startswith("On Monday")]
    assert [line.sentences for line in folded] == [
        ["On Monday 14 September, Nura checked your papers to remind you on time."]
    ]
    assert folded[0].who == "Nura" and folded[0].outcome is Outcome.ALLOWED
    assert folded[0].detail == []
    # What Nura sent is on his trail as Nura's, never as his own.
    assert any(line.who == "Nura" and line is not folded[0] for line in today.lines)

    # The chief can open the fold: each part it checked, and how often.
    mei = await h.ctx(sg, h.mei)
    [hers] = [day for day in await trail(sg, context=mei) if day.day == date(2026, 9, 14)]
    [opened] = [line for line in hers.lines if line.sentences[0].startswith("On Monday")]
    assert opened.detail and all(": " in part for part in opened.detail)


async def test_the_system_is_never_a_person_and_no_one_else_goes_without_a_name(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    line = await record(
        sg,
        context=as_the_system(h.owner),
        action=Action.READ,
        scope=Scope.PROFILE,
        target="profile",
        channel=Channel.APP,
    )
    assert line.actor_person_id is None and line.channel is Channel.SYSTEM
    with pytest.raises(IntegrityError):
        async with sg.begin_nested():
            sg.add(
                AuditEntry(
                    profile_id=h.owner.profile_id,
                    at=at(6, 1),
                    actor_person_id=None,
                    action=Action.READ,
                    scope=Scope.PROFILE,
                    channel=Channel.APP,
                    target="profile",
                    rows=0,
                    outcome=Outcome.ALLOWED,
                )
            )
            await sg.flush()
