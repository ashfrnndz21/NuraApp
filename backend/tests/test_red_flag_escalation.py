"""E19-05: a red flag escalates in the thread and to the roster within a minute, with the
hospital on his insurance named — and never "call the doctor today" when the doctor is closed.

    Escalation within one minute with the panel hospital named.

Two tiers (`app.safety.red_flags.AMBULANCE_FLAGS`): chest pain, breathless at rest and the
signs of a stroke are the ambulance at any hour; the rest are the doctor today in his hours
and, out of them (the directory's hours, else 20:00 to 08:00), the emergency department of
the hospital marked as on his insurance, or the emergency number if it gets worse. The
matrix is tier × in or out of hours × a hospital marked or not; the hour never lowers a tier.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp.models import Direction, WhatsAppMessage
from app.clock import FrozenClock
from app.db import as_utc
from app.delivery.triggers.models import Delivery, DeliveryOutcome, Ladder
from app.memory.models import Provider, ProviderKind
from app.memory.spine import add_provider
from app.regions import Region
from app.safety.red_flags import (
    AMBULANCE_FLAGS,
    RED_FLAGS,
    Feeling,
    Step,
    Urgency,
    escalation_for,
    is_after_hours,
    step_for,
    urgency_of,
)
from tests.delivery_support import PA, Home, home

SGT = ZoneInfo("Asia/Singapore")
STROKE_AND_CHEST = {
    Feeling.CHEST_TIGHTNESS,
    Feeling.BREATHLESS_AT_REST,
    Feeling.WORST_HEADACHE,
    Feeling.SUDDEN_BLURRING,
    Feeling.CONFUSION,
}


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT).astimezone(UTC)


def _expected(feeling: Feeling, after_hours: bool, hospital: bool) -> Step:
    if feeling in STROKE_AND_CHEST:
        return Step.AMBULANCE
    if after_hours:
        return Step.HOSPITAL_NOW if hospital else Step.NUMBER_IF_WORSE
    return Step.DOCTOR_TODAY_HOSPITAL if hospital else Step.DOCTOR_TODAY


@pytest.mark.parametrize("feeling", sorted(RED_FLAGS))
@pytest.mark.parametrize("after_hours", (False, True))
@pytest.mark.parametrize("hospital", (False, True))
def test_every_red_flag_by_the_hour_and_the_hospital(
    feeling: Feeling, after_hours: bool, hospital: bool
) -> None:
    step = step_for(urgency_of(feeling), after_hours=after_hours, hospital=hospital)
    assert step is _expected(feeling, after_hours, hospital)


def test_the_ambulance_tier_is_chest_pain_and_the_signs_of_a_stroke_and_is_never_lowered() -> None:
    assert AMBULANCE_FLAGS == STROKE_AND_CHEST and AMBULANCE_FLAGS < RED_FLAGS
    for feeling in AMBULANCE_FLAGS:
        assert urgency_of(feeling) is Urgency.AMBULANCE
        for late in (False, True):
            for hospital in (False, True):
                assert step_for(Urgency.AMBULANCE, after_hours=late, hospital=hospital) is Step.AMBULANCE


def test_out_of_hours_is_the_directorys_hours_else_20_to_08() -> None:
    assert not is_after_hours(time(8, 0), None, None)
    assert not is_after_hours(time(19, 59), None, None)
    assert is_after_hours(time(20, 0), None, None)
    assert is_after_hours(time(7, 59), None, None)
    assert is_after_hours(time(17, 30), time(9, 0), time(17, 0))
    assert not is_after_hours(time(9, 0), time(9, 0), time(17, 0))
    # A clinic open from 18:00 to 02:00 is open at one in the morning.
    assert not is_after_hours(time(1, 0), time(18, 0), time(2, 0))
    assert is_after_hours(time(3, 0), time(18, 0), time(2, 0))


def _listed(name: str, kind: ProviderKind, *, panel: bool = False, hours: tuple[time, time] | None = None, n: int = 0) -> Provider:
    return Provider(
        name=name,
        kind=kind,
        panel=panel,
        opens_at=None if hours is None else hours[0],
        closes_at=None if hours is None else hours[1],
        region=Region.SG,
        added_at=datetime(2026, 9, 1, tzinfo=UTC) + timedelta(minutes=n),
    )


def test_the_step_reads_the_doctors_hours_and_the_hospital_from_the_directory() -> None:
    tan = _listed("Dr Tan", ProviderKind.DOCTOR, hours=(time(9, 0), time(17, 0)))
    glen = _listed("Gleneagles", ProviderKind.HOSPITAL, panel=True, n=1)
    other = _listed("Changi General", ProviderKind.HOSPITAL, n=2)
    six_pm = datetime(2026, 9, 14, 18, 0, tzinfo=SGT)
    step = escalation_for(Feeling.FALL, providers=[tan, glen, other], local=six_pm, emergency_number="995")
    assert (step.step, step.after_hours, step.doctor, step.hospital) == (
        Step.HOSPITAL_NOW,
        True,
        "Dr Tan",
        "Gleneagles",
    )
    ten_am = datetime(2026, 9, 14, 10, 0, tzinfo=SGT)
    step = escalation_for(Feeling.FALL, providers=[tan, other], local=ten_am, emergency_number="995")
    assert (step.step, step.hospital) == (Step.DOCTOR_TODAY, None)
    # A clinic marked by mistake is not a hospital on his insurance.
    marked_clinic = _listed("Bedok Clinic", ProviderKind.CLINIC, panel=True)
    step = escalation_for(Feeling.FALL, providers=[marked_clinic], local=six_pm, emergency_number="995")
    assert step.step is Step.DOCTOR_TODAY  # the clinic keeps no hours: 08:00 to 20:00
    assert escalation_for(Feeling.CHEST_TIGHTNESS, providers=[tan, glen], local=ten_am, emergency_number="995").step is Step.AMBULANCE


# --- on WhatsApp, end to end -----------------------------------------------------------------

REPLY_STEP: dict[Step, list[str]] = {
    Step.AMBULANCE: ["Call the ambulance now on 995."],
    Step.DOCTOR_TODAY: ["Call Dr Tan today."],
    Step.DOCTOR_TODAY_HOSPITAL: ["Call Dr Tan today.", "If it gets worse, go to Gleneagles now."],
    Step.HOSPITAL_NOW: ["Go to the emergency department at Gleneagles now."],
    Step.NUMBER_IF_WORSE: ["If it gets worse, call 995 now."],
}
"""What the thread says to do now, by step: the reply sits between "This one we do not wait
for." and "Mei knows now."."""

NOTICE: dict[Step, list[str]] = {
    Step.AMBULANCE: ["Pa is not well.", "Call Pa now.", "If Pa does not answer, call 995 now."],
    Step.DOCTOR_TODAY: ["Pa is not feeling well.", "Call Dr Tan today."],
    Step.DOCTOR_TODAY_HOSPITAL: ["Pa is not feeling well.", "Call Dr Tan today."],
    Step.HOSPITAL_NOW: [
        "Pa is not well.",
        "Call Pa now.",
        "Help Pa get to the emergency department at Gleneagles now.",
    ],
    Step.NUMBER_IF_WORSE: ["Pa is not well.", "Call Pa now.", "If it gets worse, call 995 now."],
}
"""What the chief on duty is sent, after "This one we do not wait for.": in his hours the
notice he raised himself names Dr Tan; out of them, or in the ambulance tier, the notice that
says so (pending Meta, sent on a dev run)."""


async def _home_with_a_directory(sg: AsyncSession, tmp_path: Path, clock: FrozenClock, *, hospital: bool) -> Home:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await add_provider(sg, context=h.owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG)
    if hospital:
        await add_provider(
            sg, context=h.owner, name="Gleneagles", kind=ProviderKind.HOSPITAL, region=Region.SG, panel=True
        )
    return h


@pytest.mark.parametrize(
    ("words", "feeling"),
    (("I fell in the bathroom", Feeling.FALL), ("my chest is tight", Feeling.CHEST_TIGHTNESS)),
)
@pytest.mark.parametrize("hour", (15, 22))
@pytest.mark.parametrize("hospital", (False, True))
async def test_the_thread_and_the_roster_are_told_what_to_do_now(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, words: str, feeling: Feeling, hour: int, hospital: bool
) -> None:
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=hospital)
    clock.set(at(hour, 30))
    handled = await h.inbound(sg, PA, words)
    assert handled.outcome == "red_flag"
    step = _expected(feeling, after_hours=hour >= 20, hospital=hospital)
    assert handled.replies[0].text.splitlines() == [
        "This one we do not wait for.",
        *REPLY_STEP[step],
        "Mei knows now.",
    ]
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[step]]


async def test_where_meta_has_not_approved_the_new_notices_the_approved_one_goes(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """A flag never waits on Meta: on a number that carries only the approved templates the
    approved notice goes at night too, and the thread's reply — free text, inside the window —
    already says the night's step."""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=True)
    approved = tuple(
        name
        for name in h.via.number.templates
        if name in ("morning_card", "visit_reminder", "reorder", "family_digest", "feeling_check_in", "red_flag_notice")
    )
    number = dataclasses.replace(h.via.number, templates=approved)
    live = dataclasses.replace(h, via=dataclasses.replace(h.via, number=number))
    clock.set(at(22, 30))
    handled = await live.inbound(sg, PA, "I fell in the bathroom")
    assert handled.replies[0].text.splitlines()[1] == "Go to the emergency department at Gleneagles now."
    assert live.sent_to(live.mei)[-1].splitlines()[0] == "This one we do not wait for."
    sent = (await sg.scalars(select(Delivery).where(Delivery.to_person_id == h.mei.id))).all()
    assert [row.template_name for row in sent if row.outcome is DeliveryOutcome.SENT] == ["red_flag_notice"]


async def test_the_escalation_goes_within_one_minute_of_the_red_word(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """The clock is frozen at the moment the words were written: the ladder starts then, its
    first step is due at once, and the message to the one on duty leaves inside the minute."""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=True)
    said_at = at(15, 0)
    clock.set(said_at)
    handled = await h.inbound(sg, PA, "I fell in the bathroom")
    ladder = (await sg.scalars(select(Ladder).where(Ladder.flag_id == handled.flag_id))).one()
    assert as_utc(ladder.started_at) == said_at
    first = [step for step in ladder.rungs if step["after_minutes"] == 0]
    assert [step["standing"] for step in first] == ["on_duty"]
    rows = (await sg.scalars(select(Delivery).where(Delivery.ladder_id == ladder.id))).all()
    went = [row for row in rows if row.outcome is DeliveryOutcome.SENT and row.rung == first[0]["rung"]]
    assert [row.to_person_id for row in went] == [h.mei.id]
    for row in went:
        assert as_utc(row.due_at) == said_at
        assert timedelta(0) <= as_utc(row.recorded_at) - said_at <= timedelta(minutes=1)
    messages = (
        await sg.scalars(
            select(WhatsAppMessage).where(
                WhatsAppMessage.person_id == h.mei.id, WhatsAppMessage.direction == Direction.OUTBOUND
            )
        )
    ).all()
    assert messages and all(as_utc(m.at) - said_at <= timedelta(minutes=1) for m in messages)
    # The hospital on his insurance is named in the escalation, in the thread.
    assert "If it gets worse, go to Gleneagles now." in handled.replies[0].text.splitlines()
