"""#198: a "Taken" that arrives after the window has closed, and after the ladder has already
climbed, still lands on that dose — but it is recorded as late, carrying the reply's own time,
and the escalation it closes stays in the record. Whoever the ladder reached is told, once,
that it stood down; someone with no key to the medicines, never on the ladder, hears nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.db import as_utc
from app.delivery.triggers.engine import Report, run_due
from app.delivery.triggers.models import Ladder, TriggerType
from app.identity.service import register_person
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.medicines.models import DoseTaken
from app.regions import Region
from tests.delivery_support import PA, SITI, Home, home
from tests.support import agree_to_family_sharing

SGT = ZoneInfo("Asia/Singapore")
KIT = "+6595550061"


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    """A moment on Pa's wall clock in September 2026, as UTC. The 14th is a Monday."""
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT).astimezone(UTC)


async def _run(sg: AsyncSession, h: Home, clock: FrozenClock, when: datetime) -> Report:
    clock.set(when)
    return await run_due(sg, via=h.via, profile_id=h.owner.profile_id, at=when)


async def _escalate_to_the_roster(sg: AsyncSession, h: Home, clock: FrozenClock) -> None:
    """Breakfast's window closes at 08:30 with nothing tapped: Pa is asked, then Siti half an
    hour on, then Mei (on duty) half an hour after that — the same climb `test_ladder.py`
    exercises, taken as read here so the late-reply tests start from an escalation that has
    actually reached someone."""
    await _run(sg, h, clock, at(8, 31))
    await _run(sg, h, clock, at(9, 1))
    await _run(sg, h, clock, at(9, 31))


async def test_a_taken_inside_the_window_is_not_marked_late(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(7, 0))
    h = await home(sg, tmp_path)
    # Breakfast's window opens an hour before 07:30 and closes at 08:30; nothing has climbed.
    handled = await h.inbound(sg, PA, "Taken")
    assert handled.outcome == "taken"
    assert len(handled.replies) == 1  # no "written down late" line
    tap = (await sg.scalars(select(DoseTaken))).one()
    assert tap.late is False


async def test_a_late_taken_after_the_window_carries_the_replys_time_and_says_so(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await _escalate_to_the_roster(sg, h, clock)

    # Two and a half hours after the window closed, Siti finally answers.
    late_at = at(11, 0)
    clock.set(late_at)
    handled = await h.inbound(sg, SITI, "sudah beri")
    assert handled.outcome == "taken"

    tap = (await sg.scalars(select(DoseTaken))).one()
    assert tap.late is True
    assert as_utc(tap.taken_at) == late_at
    assert tap.by_person_id == h.siti.id

    # Said plainly, once, after the usual confirmation — never a scold, never twice. Siti's
    # thread is in Malay (`home`'s own setup).
    assert [r.text for r in handled.replies][-1] == "Ini ditulis lewat daripada biasa."


async def test_the_escalation_stays_visible_in_the_record_after_the_late_tap(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await _escalate_to_the_roster(sg, h, clock)

    clock.set(at(11, 0))
    await h.inbound(sg, SITI, "sudah beri")

    ladder = (await sg.scalars(select(Ladder))).one()
    # The climb it actually made is still there: Pa, then Siti, then the roster (Mei).
    assert [step["standing"] for step in ladder.rungs] == ["patient", "helper", "on_duty"]
    assert ladder.closed_because == "answered"
    assert ladder.acknowledged_by_person_id == h.siti.id
    assert ladder.closed_at is not None


async def test_whoever_was_told_is_told_it_resolved_and_someone_not_told_is_not(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    # Kit holds a key, but not to the medicines: never on this ladder, never reached.
    kit = await register_person(sg, region=Region.SG, display_name="Kit", phone_e164=KIT)
    await agree_to_family_sharing(sg, h.owner, kit, scopes={Scope.VISITS})
    await grant_key(sg, context=h.owner, holder=kit, role=KeyRole.CHIEF, scopes={Scope.VISITS})

    await _escalate_to_the_roster(sg, h, clock)
    assert h.sent_to(h.mei) != []  # Mei was reached, asked to check on Pa

    clock.set(at(11, 0))
    handled = await h.inbound(sg, SITI, "sudah beri")
    assert handled.outcome == "taken"

    # Mei was told he had not taken it; she is told, once, that it's resolved.
    resolved = [t for t in h.sent_to(h.mei) if "do not need to check again" in t]
    assert len(resolved) == 1
    assert resolved[0].splitlines() == [
        "Pa has taken Pa's blood pressure tablet with breakfast.",
        "You do not need to check again.",
    ]
    # Siti tapped it herself: she already knows, so she gets no stand-down notice.
    assert [t for t in h.sent_to(h.siti) if "do not need to check again" in t] == []
    # Pa is never told about himself.
    assert [t for t in h.sent_to(h.pa) if "do not need to check again" in t] == []
    # Kit was never on the ladder: nothing about the tablet reaches her at all.
    assert h.sent_to(kit) == []

    resolved_rows = [
        s.delivery
        for s in (await _run(sg, h, clock, at(11, 1))).sent
        if s.delivery.trigger_type is TriggerType.DOSE_RESOLVED
    ]
    # Nothing left to send a second time: the run right after finds it already done.
    assert resolved_rows == []
