"""E17-03 × E11, W7: the day's planned nudge is handed over at its planned time, and sent once.

The planner plans the day's nudge (#119) and delivery sends a handed-over nudge under the one
daily cap (#121). The delivery engine now hands it over itself at the planner's `send_after` —
his check-in time — never in the quiet hours his delivery settings keep and never on a day a
red flag was raised; the web handing it over too as he answers is the same nudge: one row, and
one send at most.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.delivery.nudges.engine import hand_over
from app.delivery.nudges.models import Nudge
from app.delivery.triggers.engine import Report, run_due
from app.delivery.triggers.models import Delivery, DeliveryOutcome, TriggerType
from app.delivery.triggers.preferences import change
from app.onboarding.settings import SettingsValues, save_settings
from tests.delivery_support import PA, Home, home
from tests.feelings_support import REGISTRY

SGT = ZoneInfo("Asia/Singapore")


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT).astimezone(UTC)


async def _run(sg: AsyncSession, h: Home, clock: FrozenClock, when: datetime) -> Report:
    clock.set(when)
    return await run_due(sg, via=h.via, profile_id=h.owner.profile_id, at=when)


def _sent_nudges(report: Report) -> list[Delivery]:
    return [
        s.delivery
        for s in report.sent
        if s.delivery.trigger_type is TriggerType.NUDGE and s.delivery.outcome is DeliveryOutcome.SENT
    ]


async def _nudges(sg: AsyncSession, h: Home) -> list[Nudge]:
    return list((await sg.scalars(select(Nudge).where(Nudge.profile_id == h.owner.profile_id))).all())


async def test_the_days_nudge_is_handed_over_at_its_time_and_sent_once(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    # Before his check-in time (10:00): nothing is handed over, nothing goes.
    assert _sent_nudges(await _run(sg, h, clock, at(9, 59))) == []
    assert await _nudges(sg, h) == []
    # At it: the schedule hands the day's nudge over, and delivery sends it.
    [sent] = _sent_nudges(await _run(sg, h, clock, at(10, 1)))
    [nudge] = await _nudges(sg, h)
    assert sent.template_name == "nudge" and sent.why["nudge_id"] == str(nudge.id)
    assert [one.template_name for one in h.whatsapp.sent].count("nudge") == 1
    # The web hands it over as he answers: the same nudge, one row.
    _plan, again = await hand_over(sg, context=h.owner, registry=REGISTRY)
    assert again.id == nudge.id and len(await _nudges(sg, h)) == 1
    # And it is not sent a second time.
    assert _sent_nudges(await _run(sg, h, clock, at(10, 6))) == []
    assert [one.template_name for one in h.whatsapp.sent].count("nudge") == 1


async def test_no_nudge_is_handed_over_on_a_red_flag_day(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    clock.set(at(9))
    handled = await h.inbound(sg, PA, "I fell in the bathroom")
    assert handled.outcome == "red_flag"
    assert _sent_nudges(await _run(sg, h, clock, at(10, 1))) == []
    assert await _nudges(sg, h) == []


async def test_no_nudge_is_handed_over_in_his_quiet_hours(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """His check-in time is 21:30 and his quiet hours begin at 21:00: the run at 21:35 is inside
    them, so nothing is handed over and nothing goes."""
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await save_settings(
        sg, context=h.owner, values=SettingsValues(language="en", checkin_time=time(21, 30))
    )
    await change(
        sg,
        context=h.owner,
        skip_quiet_days=False,
        quiet_from=time(21, 0),
        quiet_until=time(7, 0),
        channels={},
        caps={},
    )
    assert _sent_nudges(await _run(sg, h, clock, at(21, 35))) == []
    assert await _nudges(sg, h) == []
