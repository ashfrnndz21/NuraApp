"""E11-06: the escalation ladder — Dad, the helper, the caregiver on duty, the chief.

A breakfast tablet with no Taken by the end of its window asks Pa, then Siti half an hour
later, then whoever the roster puts on duty (Mei) — so the third ask goes to the roster, not
to him — and stops the moment someone answers: Siti's "given" on WhatsApp writes the Taken tap
for that tablet and closes the ladder. A red flag skips his rung and goes straight to the
roster, at 22:30 as at noon, whatever the caps. Nobody without a key that covers it is asked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.delivery.triggers.engine import Report, run_due
from app.delivery.triggers.models import (
    Category,
    DeliveryChannel,
    DeliveryOutcome,
    Ladder,
    TriggerType,
)
from app.identity.service import register_person
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.medicines.models import DoseTaken
from app.memory.models import Event, SourceChannel
from app.regions import Region
from tests.delivery_support import PA, SITI, Home, home
from tests.support import agree_to_family_sharing

SGT = ZoneInfo("Asia/Singapore")


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    """A moment on Pa's wall clock in September 2026, as UTC. The 14th is a Monday."""
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT).astimezone(UTC)


async def _run(sg: AsyncSession, h: Home, clock: FrozenClock, when: datetime) -> Report:
    clock.set(when)
    return await run_due(sg, via=h.via, profile_id=h.owner.profile_id, at=when)


def _of(report: Report, kind: TriggerType) -> list[tuple[object, int | None, DeliveryOutcome]]:
    return [
        (sent.delivery.to_person_id, sent.delivery.rung, sent.delivery.outcome)
        for sent in report.sent
        if sent.delivery.trigger_type is kind
    ]


async def test_an_untapped_tablet_asks_pa_then_siti_then_the_roster_and_stops_at_given(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)

    # Breakfast at 07:30 (his routine, not yet set); the routine calls it due for an hour, so
    # the window closes at 08:30. Before that, nobody is asked.
    assert _of(await _run(sg, h, clock, at(8, 29)), TriggerType.DOSE) == []

    first = await _run(sg, h, clock, at(8, 31))
    assert _of(first, TriggerType.DOSE) == [(h.pa.id, 0, DeliveryOutcome.SENT)]
    asked = next(s.delivery for s in first.sent if s.delivery.trigger_type is TriggerType.DOSE)
    assert asked.template_name == "dose_reminder" and asked.via is DeliveryChannel.WHATSAPP
    assert asked.rule == "dose_window_closed_untapped" and asked.category is Category.REMINDER
    assert h.sent_to(h.pa)[-1].splitlines() == [
        "Pa, this is Nura.",
        "Have you had your blood pressure tablet with breakfast?",
        "When you have, reply Taken.",
    ]
    # Nothing twice: the same rung is not asked again.
    assert _of(await _run(sg, h, clock, at(8, 45)), TriggerType.DOSE) == []

    second = await _run(sg, h, clock, at(9, 1))
    assert _of(second, TriggerType.DOSE) == [(h.siti.id, 1, DeliveryOutcome.SENT)]
    assert h.sent_to(h.siti)[-1].splitlines() == [
        "Pa belum kata Sudah ambil untuk ubat tekanan darah Pa bersama sarapan.",
        "Tolong tengok Pa.",
        "Bila Pa sudah ambil, balas sudah beri.",
    ]

    # The third ask goes to the roster — whoever is on duty now — not to him.
    third = await _run(sg, h, clock, at(9, 31))
    assert _of(third, TriggerType.DOSE) == [(h.mei.id, 2, DeliveryOutcome.SENT)]
    rung = next(s.delivery for s in third.sent if s.delivery.trigger_type is TriggerType.DOSE)
    assert rung.standing == "on_duty" and rung.template_name == "dose_check"
    assert len([text for text in h.sent_to(h.pa) if "Have you had" in text]) == 1

    # Siti taps "given" on WhatsApp: the Taken tap is written for that tablet, the ladder stops.
    clock.set(at(9, 35))
    handled = await h.inbound(sg, SITI, "sudah beri")
    assert handled.outcome == "taken"
    assert handled.replies[0].text.splitlines() == [
        "Terima kasih, saya sudah tulis.",
        "Pa sudah ambil ubat tekanan darah Pa.",
    ]
    tap = (await sg.scalars(select(DoseTaken))).one()
    assert tap.by_person_id == h.siti.id and tap.anchor == "breakfast"
    assert tap.line_id == h.line.id
    moment = await sg.get(Event, tap.event_id)
    assert moment is not None and moment.source_channel is SourceChannel.WHATSAPP
    ladder = (await sg.scalars(select(Ladder))).one()
    assert ladder.closed_because == "answered" and ladder.acknowledged_by_person_id == h.siti.id
    assert [step["standing"] for step in ladder.rungs] == ["patient", "helper", "on_duty"]
    assert [step["after_minutes"] for step in ladder.rungs] == [0, 30, 60]
    assert _of(await _run(sg, h, clock, at(10, 5)), TriggerType.DOSE) == []


async def test_his_own_taken_stops_the_ladder_before_anyone_else_is_asked(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await _run(sg, h, clock, at(8, 31))
    clock.set(at(8, 40))
    handled = await h.inbound(sg, PA, "Taken")
    assert handled.outcome == "taken"
    assert handled.replies[0].text.splitlines() == [
        "Thank you, I wrote it down.",
        "You took your blood pressure tablet with breakfast.",
        "Mei can see you took it.",
    ]
    assert (await sg.scalars(select(DoseTaken))).one().by_person_id == h.pa.id
    assert _of(await _run(sg, h, clock, at(9, 1)), TriggerType.DOSE) == []
    assert h.sent_to(h.siti) == []


async def test_nobody_whose_key_does_not_cover_the_medicines_is_on_the_ladder(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, roster=False)
    kit = await register_person(sg, region=Region.SG, display_name="Kit", phone_e164="+6595550061")
    await agree_to_family_sharing(sg, h.owner, kit, scopes={Scope.VISITS})
    await grant_key(sg, context=h.owner, holder=kit, role=KeyRole.CHIEF, scopes={Scope.VISITS})
    await _run(sg, h, clock, at(8, 31))
    ladder = (await sg.scalars(select(Ladder))).one()
    people = [step["person_id"] for step in ladder.rungs]
    assert str(kit.id) not in people
    # No roster: after the helper, the chief is the next rung.
    assert [step["standing"] for step in ladder.rungs] == ["patient", "helper", "chief"]


async def test_a_red_flag_at_night_goes_straight_to_the_roster_not_quiet_not_capped(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, quantity=2)
    # Mei had her reorder today; a second one the same day is held by the cap.
    morning = await _run(sg, h, clock, at(10))
    assert _of(morning, TriggerType.REORDER) == [(h.mei.id, None, DeliveryOutcome.SENT)]
    assert _of(await _run(sg, h, clock, at(10, 5)), TriggerType.REORDER) == [
        (h.mei.id, None, DeliveryOutcome.CAPPED)
    ]

    # 22:30, inside the quiet hours: Pa writes that he fell.
    clock.set(at(22, 30))
    handled = await h.inbound(sg, PA, "I fell in the bathroom")
    assert handled.outcome == "red_flag"
    assert handled.replies[0].text.splitlines() == [
        "This one we do not wait for.",
        "Call your doctor today.",
        "Mei knows now.",
    ]
    ladder = (await sg.scalars(select(Ladder).where(Ladder.flag_id.is_not(None)))).one()
    # His own rung is skipped (he is the one in trouble): on duty first, then the rest.
    assert [(step["standing"], step["after_minutes"]) for step in ladder.rungs] == [
        ("on_duty", 0),
        ("key_holder", 5),
    ]
    # He raised it himself: the notice says his name, not "Pa said Pa is not well."
    assert h.sent_to(h.mei)[-1].splitlines() == [
        "This one we do not wait for.",
        "Pa is not feeling well.",
        "Call your doctor today.",
    ]
    # Nobody answered: five minutes on, still at night, the next rung is asked.
    later = await _run(sg, h, clock, at(22, 36))
    assert _of(later, TriggerType.FLAG) == [(h.siti.id, 4, DeliveryOutcome.SENT)]
    flagged = next(s.delivery for s in later.sent if s.delivery.trigger_type is TriggerType.FLAG)
    assert flagged.category is Category.ALERT and flagged.rule == "red_flag_raised"
    # A reminder at the same hour is held for the quiet hours; the flag was not.
    assert all(
        s.delivery.outcome is not DeliveryOutcome.SENT
        for s in later.sent
        if s.delivery.trigger_type is not TriggerType.FLAG
    )


async def test_an_ok_from_someone_the_flag_reached_stops_the_ladder(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    clock.set(at(15))
    await h.inbound(sg, PA, "I fell")
    clock.set(at(15, 1))
    answered = await h.inbound(sg, "+6592220051", "OK")
    assert answered.outcome == "flag_acknowledged"
    assert answered.replies[0].text.splitlines() == [
        "Thank you, you have it now.",
        "I will not ask anyone else.",
    ]
    ladder = (await sg.scalars(select(Ladder).where(Ladder.flag_id.is_not(None)))).one()
    assert ladder.closed_because == "answered" and ladder.acknowledged_by_person_id == h.mei.id
    assert _of(await _run(sg, h, clock, at(15, 10)), TriggerType.FLAG) == []
    assert not any(text.startswith("This one we do not wait for.") for text in h.sent_to(h.siti))
