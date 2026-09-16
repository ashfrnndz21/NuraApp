"""E19-05: a red flag escalates in the thread and to the roster within a minute, with the
hospital on his insurance named — and never "call the doctor today" when the doctor is closed.

    Escalation within one minute with the panel hospital named.

Two tiers (`app.safety.red_flags.AMBULANCE_FLAGS`): chest pain, breathless at rest and the
signs of a stroke are the ambulance at any hour; the rest are the doctor today in his hours
and, out of them (the directory's hours, else 20:00 to 08:00), the emergency department of
the hospital marked as on his insurance, or the emergency number if it gets worse. The
matrix is tier × in or out of hours × a hospital marked or not; the hour never lowers a tier.

A fall while he is on a blood thinner (`ANTICOAGULANT_CLASSES`: warfarin, apixaban and the rest
the register classes with them) is the ambulance at any hour (`AMBULANCE_ON_A_THINNER`): a bleed
inside the head can come hours after a fall. Every path a flag is told by reads it — the
WhatsApp reply and the family's notice from the button, the symptom log and the feeling cloud.
Without a thinner, a fall keeps its rows exactly.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp.models import Direction, WhatsAppMessage
from app.channels.whatsapp.strings import RED_FLAG_STEPS
from app.clock import FrozenClock
from app.db import as_utc, utcnow
from app.delivery.triggers.models import Delivery, DeliveryChannel, DeliveryOutcome, Ladder
from app.drugs.registry import LabelFields
from app.errors import Refusal
from app.keys.scopes import KeyRole
from app.medicines.strings import say_date
from app.memory.models import Provider, ProviderKind
from app.memory.spine import add_provider
from app.reasoning.feelings.service import record_tap
from app.regions import Region
from app.safety.high_risk import HIGH_RISK_CLASSES
from app.safety.not_feeling_well import not_feeling_well
from app.safety.red_flags import (
    AMBULANCE_FLAGS,
    AMBULANCE_ON_A_THINNER,
    ANTICOAGULANT_CLASSES,
    RED_FLAGS,
    Feeling,
    Flag,
    Step,
    Urgency,
    detect,
    detect_all,
    escalation_for,
    is_after_hours,
    step_for,
    urgency_of,
)
from app.safety.symptom_log import log_symptom
from tests.delivery_support import PA, SITI, Home, home, via_for
from tests.feelings_support import STORE, TRANSCRIBER
from tests.safety_support import REGISTRY, apixaban, let_in, pa, transcriber_for, warfarin

SGT = ZoneInfo("Asia/Singapore")
STROKE_AND_CHEST = {
    Feeling.CHEST_TIGHTNESS,
    Feeling.BREATHLESS_AT_REST,
    Feeling.WORST_HEADACHE,
    Feeling.SUDDEN_BLURRING,
    Feeling.CONFUSION,
    Feeling.SHAKY_SWEATY,
}
"""The ambulance tier, written out: chest pain, breathless at rest, the signs of a stroke, and
shaky and sweaty on a sugar medicine (it acts in minutes)."""


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


def test_out_of_hours_is_the_directorys_hours_else_20_to_08_the_last_hour_included() -> None:
    assert not is_after_hours(time(8, 0), None, None)
    assert not is_after_hours(time(18, 59), None, None)
    # The last hour before closing: the clinic cannot see him "today" at 19:45.
    assert is_after_hours(time(19, 0), None, None)
    assert is_after_hours(time(20, 0), None, None)
    assert is_after_hours(time(7, 59), None, None)
    assert is_after_hours(time(16, 30), time(9, 0), time(17, 0))
    assert not is_after_hours(time(9, 0), time(9, 0), time(17, 0))
    # A clinic open from 18:00 to 02:00 is open at one in the morning, not at half past one.
    assert not is_after_hours(time(0, 30), time(18, 0), time(2, 0))
    assert is_after_hours(time(1, 30), time(18, 0), time(2, 0))
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
    step = escalation_for(Feeling.FALL, providers=[tan, glen, other], local=six_pm, emergency_number="995", anticoagulated=False, tiered=True)
    assert (step.step, step.after_hours, step.doctor, step.hospital) == (
        Step.HOSPITAL_NOW,
        True,
        "Dr Tan",
        "Gleneagles",
    )
    ten_am = datetime(2026, 9, 14, 10, 0, tzinfo=SGT)
    step = escalation_for(Feeling.FALL, providers=[tan, other], local=ten_am, emergency_number="995", anticoagulated=False, tiered=True)
    assert (step.step, step.hospital) == (Step.DOCTOR_TODAY, None)
    # A clinic marked by mistake is not a hospital on his insurance.
    marked_clinic = _listed("Bedok Clinic", ProviderKind.CLINIC, panel=True)
    step = escalation_for(Feeling.FALL, providers=[marked_clinic], local=six_pm, emergency_number="995", anticoagulated=False, tiered=True)
    assert step.step is Step.DOCTOR_TODAY  # the clinic keeps no hours: 08:00 to 20:00
    assert escalation_for(Feeling.CHEST_TIGHTNESS, providers=[tan, glen], local=ten_am, emergency_number="995", anticoagulated=False, tiered=True).step is Step.AMBULANCE


# --- on WhatsApp, end to end -----------------------------------------------------------------

AMBULANCE_IF_WORSE = "If it gets worse, call the ambulance now on 995."
REPLY_STEP: dict[Step, list[str]] = {
    Step.AMBULANCE: ["Call the ambulance now on 995."],
    Step.DOCTOR_TODAY: ["Call Dr Tan today.", AMBULANCE_IF_WORSE],
    Step.DOCTOR_TODAY_HOSPITAL: [
        "Call Dr Tan today.",
        "If it gets worse, go to Gleneagles now.",
        "Gleneagles is on your insurance.",
    ],
    Step.HOSPITAL_NOW: [
        "Go to the emergency department at Gleneagles now.",
        "Gleneagles is on your insurance.",
        "If you cannot get there safely, call the ambulance now on 995.",
    ],
    Step.NUMBER_IF_WORSE: [
        "Sit down and rest now.",
        AMBULANCE_IF_WORSE,
        "Call Dr Tan on Tuesday 15 September in the morning.",
    ],
}
"""What the thread says to do now, by step: the reply sits between "This one we do not wait
for." and "Mei knows now.", and ends "Nura does not decide what is wrong."."""

CLOSING = "Nura does not decide what is wrong."

NOTICE: dict[Step, list[str]] = {
    Step.AMBULANCE: [
        "Pa is not feeling well.",
        "Call Pa now.",
        "Ask Pa now if an ambulance is coming.",
        "If not, call the ambulance now on 995.",
    ],
    Step.DOCTOR_TODAY: ["Pa is not feeling well.", "Call Dr Tan today."],
    Step.DOCTOR_TODAY_HOSPITAL: ["Pa is not feeling well.", "Call Dr Tan today."],
    Step.HOSPITAL_NOW: [
        "Pa is not feeling well.",
        "Call Pa now.",
        "Help Pa get to the emergency department at Gleneagles now.",
        "If Pa cannot get there safely, call the ambulance now on 995.",
    ],
    Step.NUMBER_IF_WORSE: ["Pa is not feeling well.", "Call Pa now.", AMBULANCE_IF_WORSE],
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
        CLOSING,
    ]
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[step]]


BASE_APPROVED = (
    "morning_card",
    "visit_reminder",
    "reorder",
    "family_digest",
    "feeling_check_in",
    "red_flag_notice",
)
"""E19's six: the only templates a number has approved until the tiered notices, and their
neutral fallback, are submitted and approved too (#174)."""


async def test_outside_her_window_an_unapproved_tier_never_falls_to_call_the_doctor_today(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """A tier's own template not approved, and outside her window a reply cannot go at all: no
    WhatsApp goes to her rather than the wrong, lower-urgency words — an urgent alert is never
    downgraded (#174). The thread's reply to him — free text, inside his own window — still
    says the night's step; her family page's notice is written besides; and why WhatsApp did
    not go is on the trail."""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=True)
    number = dataclasses.replace(h.via.number, templates=BASE_APPROVED)
    live = dataclasses.replace(h, via=dataclasses.replace(h.via, number=number))
    clock.set(at(22, 30))
    handled = await live.inbound(sg, PA, "I fell in the bathroom")
    assert handled.replies[0].text.splitlines()[1] == "Go to the emergency department at Gleneagles now."
    assert live.sent_to(live.mei) == []
    sent = [
        row
        for row in (await sg.scalars(select(Delivery).where(Delivery.to_person_id == h.mei.id))).all()
        if row.trigger_type.value == "flag"
    ]
    phone = [
        row
        for row in sent
        if row.outcome is DeliveryOutcome.SENT and row.via is not DeliveryChannel.IN_APP
    ]
    assert phone == []
    no_channel = [row for row in sent if row.outcome is DeliveryOutcome.NO_CHANNEL]
    assert no_channel and any(
        any("whatsapp:" in reason for reason in row.passed_over) for row in no_channel
    )
    assert any(
        row.via is DeliveryChannel.IN_APP and row.outcome is DeliveryOutcome.SENT for row in sent
    )


async def test_outside_her_window_with_the_neutral_notice_approved_it_goes_not_the_tier(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """The tier's own template still not approved, but its neutral fallback is: that goes,
    states no action, and never says "call the doctor today" either."""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=True)
    number = dataclasses.replace(h.via.number, templates=(*BASE_APPROVED, "red_flag_notice_urgent"))
    live = dataclasses.replace(h, via=dataclasses.replace(h.via, number=number))
    clock.set(at(22, 30))
    await live.inbound(sg, PA, "I fell in the bathroom")
    assert live.sent_to(live.mei)[-1].splitlines() == [
        "This one we do not wait for.",
        "Pa is not feeling well.",
        "Open Nura now.",
    ]
    sent = (await sg.scalars(select(Delivery).where(Delivery.to_person_id == h.mei.id))).all()
    phone = [
        row
        for row in sent
        if row.outcome is DeliveryOutcome.SENT and row.via is not DeliveryChannel.IN_APP
    ]
    assert [row.template_name for row in phone] == ["red_flag_notice_urgent"]
    assert any(
        row.via is DeliveryChannel.IN_APP and row.outcome is DeliveryOutcome.SENT for row in sent
    )


@pytest.mark.parametrize("language", ("en", "ms", "zh"))
async def test_outside_her_window_the_ambulance_tier_never_falls_to_call_the_doctor_today(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, language: str
) -> None:
    """The ambulance tier is the one that must never be lowered at all: outside her window,
    with neither its own template nor the neutral one approved, nothing goes to her on
    WhatsApp — in English, Malay and Chinese alike, since the words never render at all."""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    h.mei.language = language
    await sg.flush()
    number = dataclasses.replace(h.via.number, templates=BASE_APPROVED)
    live = dataclasses.replace(h, via=dataclasses.replace(h.via, number=number))
    clock.set(at(15, 0))
    await live.inbound(sg, PA, "my chest is tight")
    assert live.sent_to(live.mei) == []
    sent = [
        row
        for row in (await sg.scalars(select(Delivery).where(Delivery.to_person_id == h.mei.id))).all()
        if row.trigger_type.value == "flag"
    ]
    assert not any(
        row.outcome is DeliveryOutcome.SENT and row.via is DeliveryChannel.WHATSAPP for row in sent
    )
    assert any(
        row.via is DeliveryChannel.IN_APP and row.outcome is DeliveryOutcome.SENT for row in sent
    )


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
    phone = [row for row in went if row.via is not DeliveryChannel.IN_APP]
    assert [row.to_person_id for row in phone] == [h.mei.id]
    # Whatever carried it, the notice on her family page is written besides (#162).
    assert [row.to_person_id for row in went if row.via is DeliveryChannel.IN_APP] == [h.mei.id]
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


# --- what the review found ------------------------------------------------------------------


async def test_a_hospital_named_by_its_initials_never_loses_the_flag(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """"SGH" is a hospital's name, not an abbreviation in his sentence: the words are checked
    with every name standing in as a plain name, and the flag, the ladder, the reply and the
    family's notice all go."""
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await add_provider(sg, context=h.owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG)
    await add_provider(sg, context=h.owner, name="SGH", kind=ProviderKind.HOSPITAL, region=Region.SG, panel=True)
    clock.set(at(22, 30))
    handled = await h.inbound(sg, PA, "I fell in the bathroom")
    assert handled.outcome == "red_flag" and handled.flag_id is not None
    assert await sg.get(Flag, handled.flag_id) is not None
    assert (await sg.scalars(select(Ladder).where(Ladder.flag_id == handled.flag_id))).one()
    said = handled.replies[0].text.splitlines()
    assert said[1:3] == ["Go to the emergency department at SGH now.", "SGH is on your insurance."]
    assert "Help Pa get to the emergency department at SGH now." in h.sent_to(h.mei)[-1].splitlines()


@pytest.mark.parametrize(
    "words",
    ("I fell and now I am confused", "Pa jatuh dan keliru", "他跌倒了，现在很糊涂", "confused after he fell"),
)
def test_a_fall_with_confusion_is_the_ambulance_in_every_language(words: str) -> None:
    assert detect(words) is Feeling.CONFUSION
    assert urgency_of(Feeling.CONFUSION) is Urgency.AMBULANCE


async def test_a_fall_with_confusion_in_his_hours_is_still_the_ambulance(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    clock.set(at(15))
    handled = await h.inbound(sg, PA, "I fell and now I am confused")
    assert handled.replies[0].text.splitlines()[1] == "Call the ambulance now on 995."


async def test_if_his_directory_cannot_be_read_the_step_is_the_ambulance(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing about the directory may weaken the step or keep the flag from the family."""

    async def refused(*_: object, **__: object) -> None:
        raise Refusal("the directory could not be read")

    monkeypatch.setattr("app.channels.whatsapp.inbound.escalation_now", refused)
    monkeypatch.setattr("app.delivery.triggers.ladder.escalation_now", refused)
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=True)
    clock.set(at(15))
    handled = await h.inbound(sg, PA, "I fell in the bathroom")
    assert handled.outcome == "red_flag"
    assert handled.replies[0].text.splitlines()[1] == "Call the ambulance now on 995."
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[Step.AMBULANCE]]


async def test_inside_her_window_the_tiered_notice_goes_as_free_text_until_meta_approves(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """On a number that carries only the approved templates, Mei wrote an hour ago: the night's
    notice goes to her as free text, the same words as the pending template; nobody gets
    "call your doctor today" at 22:30."""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=True)
    approved = tuple(
        name
        for name in h.via.number.templates
        if name in ("morning_card", "visit_reminder", "reorder", "family_digest", "feeling_check_in", "red_flag_notice")
    )
    number = dataclasses.replace(h.via.number, templates=approved)
    live = dataclasses.replace(h, via=dataclasses.replace(h.via, number=number))
    clock.set(at(21, 30))
    await live.inbound(sg, h.mei.phone_e164 or "", "thank you")
    clock.set(at(22, 30))
    await live.inbound(sg, PA, "I fell in the bathroom")
    sent = [
        row
        for row in (await sg.scalars(select(Delivery).where(Delivery.to_person_id == h.mei.id))).all()
        if row.outcome is DeliveryOutcome.SENT and row.trigger_type.value == "flag"
    ]
    # The free text carried it; the notice on her family page is written besides (#162).
    assert [row.template_name for row in sent if row.via is not DeliveryChannel.IN_APP] == [None]
    assert any(row.via is DeliveryChannel.IN_APP for row in sent)
    assert live.sent_to(live.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[Step.HOSPITAL_NOW]]


# --- the same step on his voice note (#146) --------------------------------------------------


async def test_his_voice_note_at_night_is_answered_with_the_hospital_on_his_insurance(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """A voice note in which he says he fell (#146 transcribes it, the flag first) goes through
    the same step as typed words: at 22:30, with Gleneagles marked, the emergency department,
    never "call your doctor today"."""
    from tests.whatsapp_support import PA as PA_NUMBER
    from tests.whatsapp_support import family

    clock.set(datetime(2026, 9, 3, 12, 0, tzinfo=UTC))
    home = await family(sg, tmp_path)
    await add_provider(sg, context=home.owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG)
    await add_provider(
        sg, context=home.owner, name="Gleneagles", kind=ProviderKind.HOSPITAL, region=Region.SG, panel=True
    )
    clock.set(datetime(2026, 9, 3, 22, 30, tzinfo=SGT).astimezone(UTC))
    flagged = await home.inbound(
        sg, PA_NUMBER, media_id="pa-voice-fell", content_type="audio/ogg; codecs=opus"
    )
    assert flagged.outcome == "red_flag" and flagged.flag_id is not None
    said = [line for reply in flagged.replies for line in reply.text.splitlines()]
    assert "Go to the emergency department at Gleneagles now." in said
    assert "If you cannot get there safely, call the ambulance now on 995." in said
    assert not any("today." in line and line.startswith("Call ") for line in said)
    assert said[-1] == CLOSING or CLOSING in said


# --- a fall on a blood thinner (the operator, 15 September 2026) ------------------------------

THINNERS = {"warfarin": warfarin, "apixaban": apixaban}
"""The two kinds of blood thinner a family here holds, from their label photos: the register
classes both as an anticoagulant."""

FELL = {"en": "I fell in the bathroom", "ms": "Saya jatuh di bilik air", "zh": "我在浴室跌倒了"}
OPENING = {"en": "This one we do not wait for.", "ms": "Yang ini kita tidak tunggu.", "zh": "这个我们不等。"}
MEI_KNOWS = {"en": "Mei knows now.", "ms": "Mei sudah tahu.", "zh": "Mei已经知道了。"}
CLOSINGS = {
    "en": CLOSING,
    "ms": "Nura tidak menentukan apa masalahnya.",
    "zh": "Nura 不判断您出了什么问题。",
}
AMBULANCE_NOW = {
    "en": "Call the ambulance now on 995.",
    "ms": "Hubungi ambulans sekarang di talian 995.",
    "zh": "现在就打995叫救护车。",
}
"""The ambulance step, word for word, in his three languages."""


def _step_lines(step: Step, language: str) -> list[str]:
    """Today's lines for a step, in his language: the catalogue's, with the directory's names."""
    if language == "en":
        return REPLY_STEP[step]
    return [
        line.format(
            doctor="Dr Tan", hospital="Gleneagles", emergency_number="995", day=say_date(date(2026, 9, 15), language)
        )
        for line in RED_FLAG_STEPS[step.value][language]
    ]


@pytest.mark.parametrize("feeling", sorted(RED_FLAGS))
@pytest.mark.parametrize("after_hours", (False, True))
@pytest.mark.parametrize("hospital", (False, True))
def test_on_a_blood_thinner_a_fall_is_the_ambulance_and_no_other_row_moves(
    feeling: Feeling, after_hours: bool, hospital: bool
) -> None:
    step = step_for(urgency_of(feeling, anticoagulated=True), after_hours=after_hours, hospital=hospital)
    assert step is (Step.AMBULANCE if feeling is Feeling.FALL else _expected(feeling, after_hours, hospital))
    # Off a thinner, the fall keeps its rows exactly.
    assert step_for(urgency_of(feeling), after_hours=after_hours, hospital=hospital) is _expected(
        feeling, after_hours, hospital
    )


def test_the_thinners_are_the_registers_class_and_never_a_list_of_names() -> None:
    """The rule reads the register's class, the one the label-photo rule guards; every blood
    thinner the register knows is in it, so no drug list is copied here."""
    assert AMBULANCE_ON_A_THINNER == {Feeling.FALL}
    assert AMBULANCE_ON_A_THINNER <= RED_FLAGS - AMBULANCE_FLAGS
    assert ANTICOAGULANT_CLASSES <= set(HIGH_RISK_CLASSES)
    known = {
        match.generic: match.drug_class
        for generic in HIGH_RISK_CLASSES["anticoagulant"]
        for match in REGISTRY.identify(LabelFields(generic=generic))
    }
    assert {"warfarin", "apixaban"} <= set(known)
    assert all(drug_class.lower() in ANTICOAGULANT_CLASSES for drug_class in known.values())


def test_the_step_on_a_thinner_is_the_ambulance_whatever_the_directory_says() -> None:
    tan = _listed("Dr Tan", ProviderKind.DOCTOR, hours=(time(9, 0), time(17, 0)))
    glen = _listed("Gleneagles", ProviderKind.HOSPITAL, panel=True, n=1)
    for local in (datetime(2026, 9, 14, 14, 0, tzinfo=SGT), datetime(2026, 9, 14, 22, 30, tzinfo=SGT)):
        for providers in ([], [tan], [tan, glen]):
            for number in ("995", "999"):
                step = escalation_for(
                    Feeling.FALL, providers=providers, local=local, emergency_number=number, anticoagulated=True, tiered=True
                )
                assert (step.step, step.urgency, step.anticoagulated, step.emergency_number) == (
                    Step.AMBULANCE,
                    Urgency.AMBULANCE,
                    True,
                    number,
                )


@pytest.mark.parametrize("thinner", sorted(THINNERS))
@pytest.mark.parametrize("language", ("en", "ms", "zh"))
@pytest.mark.parametrize(("hour", "minute"), ((14, 0), (22, 30)))
@pytest.mark.parametrize("hospital", (False, True))
async def test_a_fall_on_a_blood_thinner_is_the_ambulance_at_any_hour_in_every_language(
    sg: AsyncSession,
    tmp_path: Path,
    clock: FrozenClock,
    thinner: str,
    language: str,
    hour: int,
    minute: int,
    hospital: bool,
) -> None:
    """At 14:00 in his doctor's hours and at 22:30 out of them, with Gleneagles marked or not:
    never "rest now, call Dr Tan in the morning" — the ambulance now, and the family's
    ambulance notice."""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=hospital)
    await THINNERS[thinner](sg, h.owner)
    h.pa.language = language
    await sg.flush()
    clock.set(at(hour, minute))
    handled = await h.inbound(sg, PA, FELL[language])
    assert handled.outcome == "red_flag"
    assert handled.replies[0].text.splitlines() == [
        OPENING[language],
        AMBULANCE_NOW[language],
        MEI_KNOWS[language],
        CLOSINGS[language],
    ]
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[Step.AMBULANCE]]


@pytest.mark.parametrize("language", ("en", "ms", "zh"))
@pytest.mark.parametrize(("hour", "minute"), ((14, 0), (22, 30)))
@pytest.mark.parametrize("hospital", (False, True))
async def test_a_fall_with_no_blood_thinner_keeps_todays_rows_exactly(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, language: str, hour: int, minute: int, hospital: bool
) -> None:
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=hospital)
    h.pa.language = language
    await sg.flush()
    clock.set(at(hour, minute))
    handled = await h.inbound(sg, PA, FELL[language])
    step = _expected(Feeling.FALL, after_hours=hour >= 20, hospital=hospital)
    assert step is not Step.AMBULANCE
    assert handled.replies[0].text.splitlines() == [
        OPENING[language],
        *_step_lines(step, language),
        MEI_KNOWS[language],
        CLOSINGS[language],
    ]
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[step]]


async def test_a_thinner_no_longer_in_force_does_not_raise_the_fall(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """A line superseded and not replaced is not on his list now: the night row, as without."""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    made = await warfarin(sg, h.owner)
    assert made.line is not None
    made.line.superseded_at = utcnow()
    await sg.flush()
    clock.set(at(22, 30))
    handled = await h.inbound(sg, PA, FELL["en"])
    assert handled.replies[0].text.splitlines()[1:4] == REPLY_STEP[Step.NUMBER_IF_WORSE]


async def test_the_helpers_word_reads_his_list_as_the_system(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """Siti's key does not open his medicines; she writes that he fell, at night, in Malay.
    The rule reads his list as the system and she is told the ambulance — naming no medicine."""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    await warfarin(sg, h.owner)
    clock.set(at(22, 30))
    handled = await h.inbound(sg, SITI, "Pa jatuh di bilik air")
    assert handled.outcome == "red_flag"
    assert handled.replies[0].text.splitlines()[1] == AMBULANCE_NOW["ms"]
    assert not any(word in handled.replies[0].text.lower() for word in ("warfarin", "marevan", "darah"))
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[Step.AMBULANCE]]


HELPER_SAYS = {"en": "Pa fell in the bathroom", "ms": "Pa jatuh di bilik air", "zh": "Pa在浴室跌倒了"}
ABOUT_HIM = {
    (False, "en"): [
        "Help Pa sit down and rest now.",
        AMBULANCE_IF_WORSE,
        "Call Dr Tan on Tuesday 15 September in the morning.",
    ],
    (True, "en"): [
        "Help Pa get to the emergency department at Gleneagles now.",
        "Gleneagles is on Pa's insurance.",
        "If Pa cannot get there safely, call the ambulance now on 995.",
    ],
    (False, "ms"): [
        "Bantu Pa duduk dan berehat sekarang.",
        "Kalau jadi lebih teruk, hubungi ambulans sekarang di talian 995.",
        "Telefon Dr Tan pada pagi Selasa 15 September.",
    ],
    (True, "ms"): [
        "Bantu Pa pergi ke jabatan kecemasan di Gleneagles sekarang.",
        "Gleneagles dilindungi insurans Pa.",
        "Kalau Pa tidak boleh pergi dengan selamat, hubungi ambulans sekarang di talian 995.",
    ],
    (False, "zh"): ["现在就帮Pa坐下休息。", "如果变得更严重，现在就打995叫救护车。", "9月15日星期二早上再打电话给Dr Tan。"],
    (True, "zh"): ["现在就帮Pa去Gleneagles的急诊部。", "Gleneagles在Pa的保险范围内。", "如果Pa不能安全地去那里，现在就打995叫救护车。"],
}
"""What the thread tells a sender who is not him, out of hours: who does the next thing is
her, and the hospital is on his insurance (plain words, rule 7)."""
CLOSING_ABOUT = {
    "en": "Nura does not decide what is wrong with Pa.",
    "ms": "Nura tidak menentukan apa masalah Pa.",
    "zh": "Nura 不判断Pa出了什么问题。",
}


@pytest.mark.parametrize("language", ("en", "ms", "zh"))
@pytest.mark.parametrize("hospital", (False, True))
async def test_the_helpers_word_is_answered_about_him_and_never_as_if_she_were_unwell(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, language: str, hospital: bool
) -> None:
    """Siti writes at 22:30 that Pa fell, with no blood thinner on his list: never "Sit down
    and rest now." or "on your insurance" to her — "Help Pa sit down and rest now.", "Gleneagles
    is on Pa's insurance." (B1 plain-words review). His own word keeps "you"."""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=hospital)
    h.siti.language = language
    await sg.flush()
    clock.set(at(22, 30))
    handled = await h.inbound(sg, SITI, HELPER_SAYS[language])
    assert handled.outcome == "red_flag"
    said = handled.replies[0].text.splitlines()
    assert said[0] == OPENING[language]
    assert said[1:4] == ABOUT_HIM[(hospital, language)]
    assert said[-1] == CLOSING_ABOUT[language]
    mine = await h.inbound(sg, PA, FELL["en"])
    assert mine.replies[0].text.splitlines()[1:4] == REPLY_STEP[
        Step.HOSPITAL_NOW if hospital else Step.NUMBER_IF_WORSE
    ]


@pytest.mark.parametrize("path", ("button", "log", "cloud"))
@pytest.mark.parametrize("thinner", (None, "warfarin"))
async def test_the_button_the_log_and_the_cloud_tell_the_family_the_same_step(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, path: str, thinner: str | None
) -> None:
    """Pressed, written in the log, or tapped on the cloud at 22:30 with no hospital marked: his
    card says the ambulance as it always has, and the family's notice follows the tier — the
    ambulance on a thinner, the night notice without one. (The cloud's follow-up raises its
    red word through the same path as the tap.)"""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    if thinner is not None:
        await THINNERS[thinner](sg, h.owner)
    clock.set(at(22, 30))
    if path == "button":
        await not_feeling_well(
            sg, context=h.owner, store=STORE, transcriber=TRANSCRIBER, registry=REGISTRY, via=h.via,
            words=FELL["en"],
        )
    elif path == "log":
        await log_symptom(
            sg, context=h.owner, store=STORE, transcriber=TRANSCRIBER, registry=REGISTRY, via=h.via,
            words=FELL["en"],
        )
    else:
        await record_tap(
            sg, context=h.owner, word=Feeling.FALL, registry=REGISTRY, store=STORE,
            transcriber=TRANSCRIBER, via=h.via,
        )
    step = Step.AMBULANCE if thinner is not None else Step.NUMBER_IF_WORSE
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[step]]


async def test_in_malaysia_the_ambulance_is_999(my: AsyncSession, tmp_path: Path, clock: FrozenClock) -> None:
    """The region table gives the number: a fall on warfarin in Kuala Lumpur at 22:30 sends the
    family the ambulance notice on 999."""
    clock.set(datetime(2026, 9, 14, 6, 0, tzinfo=SGT).astimezone(UTC))
    owner = await pa(my, region=Region.MY, phone="+60121110077")
    await let_in(my, owner, phone="+60122220077", name="Mei", role=KeyRole.CHIEF)
    await warfarin(my, owner)
    via = via_for(Region.MY, tmp_path)
    clock.set(datetime(2026, 9, 14, 22, 30, tzinfo=SGT).astimezone(UTC))
    done = await not_feeling_well(
        my, context=owner, store=via.providers.object_store, transcriber=transcriber_for(Region.MY),
        registry=REGISTRY,
        via=via, words=FELL["en"],
    )
    assert "Call the ambulance now on 999." in [line.text for line in done.lines]
    whatsapp = via.providers.whatsapp
    sent = [one.text for one in whatsapp.sent if one.to_e164 == "+60122220077"]  # type: ignore[attr-defined]
    assert sent and sent[-1].splitlines() == [
        "This one we do not wait for.",
        "Pa is not feeling well.",
        "Call Pa now.",
        "Ask Pa now if an ambulance is coming.",
        "If not, call the ambulance now on 999.",
    ]


# --- what the clinical-safety re-check found ---------------------------------------------------

FELL_AND_SWOLLEN = {
    "en": "I fell and my leg is swollen on one side",
    "ms": "Saya jatuh dan kaki bengkak sebelah",
    "zh": "我跌倒了，一只脚肿了",
}


@pytest.mark.parametrize("language", sorted(FELL_AND_SWOLLEN))
def test_a_fall_with_another_same_day_flag_is_heard_as_the_fall(language: str) -> None:
    """Both are the same day off a thinner; on one, the fall is the ambulance — so the fall is
    the flag, and the thinner is never missed for the swelling said beside it."""
    assert detect(FELL_AND_SWOLLEN[language]) is Feeling.FALL
    assert detect("I fell and now I am confused") is Feeling.CONFUSION


@pytest.mark.parametrize("thinner", (None, "warfarin"))
async def test_a_fall_said_with_swelling_on_a_thinner_is_the_ambulance(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, thinner: str | None
) -> None:
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    if thinner is not None:
        await THINNERS[thinner](sg, h.owner)
    clock.set(at(22, 30))
    handled = await h.inbound(sg, PA, FELL_AND_SWOLLEN["en"])
    step = Step.AMBULANCE if thinner is not None else Step.NUMBER_IF_WORSE
    assert handled.replies[0].text.splitlines()[1:-2] == REPLY_STEP[step]
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[step]]


@pytest.mark.parametrize("language", ("ms", "zh"))
async def test_the_familys_ambulance_notice_is_in_her_language(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, language: str
) -> None:
    from app.channels.whatsapp.strings import RED_FLAG_NOTICE_TEXT

    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=True)
    await warfarin(sg, h.owner)
    h.mei.language = language
    await sg.flush()
    clock.set(at(22, 30))
    await h.inbound(sg, PA, FELL["en"])
    assert h.sent_to(h.mei)[-1].splitlines() == [
        line.format(name="Pa", emergency_number="995")
        for line in RED_FLAG_NOTICE_TEXT["red_flag_notice_ambulance_text"][language]
    ]


async def test_inside_her_window_the_ambulance_notice_goes_as_free_text_until_meta_approves(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """A number carrying only the approved templates, as a deployment's does until Meta
    approves the tiered notices: Mei wrote an hour ago, so the ambulance notice goes to her as
    free text. (Outside her window, with neither the tier's template nor its neutral fallback
    approved, no WhatsApp goes at all rather than a lower-urgency notice — #174, resolving
    ADR 0010's open question.)"""
    from app.channels.whatsapp.templates import TEMPLATES

    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    await warfarin(sg, h.owner)
    approved = tuple(name for name in h.via.number.templates if TEMPLATES[name].approved)
    assert "red_flag_notice_ambulance" not in approved
    number = dataclasses.replace(h.via.number, templates=approved)
    live = dataclasses.replace(h, via=dataclasses.replace(h.via, number=number))
    clock.set(at(21, 30))
    await live.inbound(sg, h.mei.phone_e164 or "", "thank you")
    clock.set(at(22, 30))
    handled = await live.inbound(sg, PA, FELL["en"])
    assert handled.replies[0].text.splitlines()[1] == "Call the ambulance now on 995."
    sent = [
        row
        for row in (await sg.scalars(select(Delivery).where(Delivery.to_person_id == h.mei.id))).all()
        if row.outcome is DeliveryOutcome.SENT and row.trigger_type.value == "flag"
    ]
    # The free text carried it; the notice on her family page is written besides (#162).
    assert [row.template_name for row in sent if row.via is not DeliveryChannel.IN_APP] == [None]
    assert any(row.via is DeliveryChannel.IN_APP for row in sent)
    assert live.sent_to(live.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[Step.AMBULANCE]]


async def test_the_system_read_of_his_list_is_on_the_trail_in_the_helpers_name(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    from app.audit.models import Action, Channel
    from app.keys.scopes import Scope
    from tests.safety_support import trail

    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    await warfarin(sg, h.owner)
    clock.set(at(22, 30))
    await h.inbound(sg, SITI, "Pa jatuh di bilik air")
    reads = [
        line
        for line in await trail(sg, h.owner.profile_id)
        if line.target == "medication_line" and line.action is Action.READ and line.channel is Channel.SYSTEM
    ]
    assert reads and {line.scope for line in reads} == {Scope.MEDICINES}
    assert h.siti.id in {line.actor_person_id for line in reads}


async def test_if_his_list_cannot_be_read_a_fall_is_the_ambulance(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any failure reading his list errs towards the ambulance, in its own savepoint: the
    flag, the ladder and the reply all still go."""

    async def broken(*_: object, **__: object) -> bool:
        raise RuntimeError("the medicines table could not be read")

    monkeypatch.setattr("app.safety.red_flags.on_a_blood_thinner", broken)
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=True)
    clock.set(at(15))
    handled = await h.inbound(sg, PA, FELL["en"])
    assert handled.outcome == "red_flag" and handled.flag_id is not None
    assert handled.replies[0].text.splitlines()[1] == "Call the ambulance now on 995."
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[Step.AMBULANCE]]


@pytest.mark.parametrize(
    ("drug_class", "generic"),
    (
        ("vitamin_k_antagonist", "warfarin"),
        ("vitamin_k_antagonist", "warfarin sodium"),
        ("direct_thrombin_inhibitor", "dabigatran etexilate"),
        ("ANTICOAGULANT", "warfarin sodium"),
    ),
)
async def test_a_thinner_is_known_by_its_class_in_any_case_or_by_its_name(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, drug_class: str, generic: str
) -> None:
    """A register that files warfarin under another code still raises the fall by its name;
    one that writes the class in capitals still raises it by the class."""
    from app.medicines.models import MedicationLine

    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    made = await warfarin(sg, h.owner)
    assert made.line is not None
    await sg.execute(
        MedicationLine.__table__.update()
        .where(MedicationLine.__table__.c.id == made.line.id)
        .values(drug_class=drug_class, generic=generic)
    )
    sg.expire_all()
    clock.set(at(22, 30))
    handled = await h.inbound(sg, PA, FELL["en"])
    assert handled.replies[0].text.splitlines()[1] == "Call the ambulance now on 995."


async def test_his_voice_note_on_a_thinner_is_the_ambulance_not_the_hospital(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """The voice note that says he fell (#146), at 22:30 with Gleneagles marked: on warfarin,
    the ambulance — the same step as typed words."""
    from tests.whatsapp_support import PA as PA_NUMBER
    from tests.whatsapp_support import family

    clock.set(datetime(2026, 9, 3, 12, 0, tzinfo=UTC))
    home = await family(sg, tmp_path)
    await add_provider(sg, context=home.owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG)
    await add_provider(
        sg, context=home.owner, name="Gleneagles", kind=ProviderKind.HOSPITAL, region=Region.SG, panel=True
    )
    await warfarin(sg, home.owner)
    clock.set(datetime(2026, 9, 3, 22, 30, tzinfo=SGT).astimezone(UTC))
    flagged = await home.inbound(sg, PA_NUMBER, media_id="pa-voice-fell", content_type="audio/ogg; codecs=opus")
    assert flagged.outcome == "red_flag"
    said = [line for reply in flagged.replies for line in reply.text.splitlines()]
    assert "Call the ambulance now on 995." in said
    assert not any("emergency department" in line or "morning" in line for line in said)


FELL_AND_SHAKY = {
    "en": "I fell, I am shaky and sweaty",
    "ms": "Saya jatuh, menggigil dan berpeluh",
    "zh": "我跌倒了，手抖出汗",
}
"""A fall said with shaky-and-sweaty: the ambulance tier's flag is first, but with no sugar
condition or sugar medicine on the record it is held back."""


@pytest.mark.parametrize("language", sorted(FELL_AND_SHAKY))
async def test_a_fall_said_with_a_held_back_flag_is_still_raised_as_the_fall(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, language: str
) -> None:
    """Never "I wrote it down. If it gets worse, call Dr Tan today." with nobody told: the
    fall is raised, and on a thinner it is the ambulance."""
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    await warfarin(sg, h.owner)
    h.pa.language = language
    await sg.flush()
    clock.set(at(22, 30))
    handled = await h.inbound(sg, PA, FELL_AND_SHAKY[language])
    assert handled.outcome == "red_flag" and handled.flag_id is not None
    flag = await sg.get(Flag, handled.flag_id)
    assert flag is not None and flag.feeling is Feeling.FALL and flag.suppressed_because is None
    assert handled.replies[0].text.splitlines()[1] == AMBULANCE_NOW[language]
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[Step.AMBULANCE]]


async def test_on_a_sugar_medicine_shaky_and_sweaty_stays_the_flag(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """With the fact on the record, the more urgent flag is not held back, and it is raised."""
    from tests.safety_support import gliclazide

    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    await gliclazide(sg, h.owner)
    clock.set(at(15))
    handled = await h.inbound(sg, PA, FELL_AND_SHAKY["en"])
    flag = await sg.get(Flag, handled.flag_id)
    assert flag is not None and flag.feeling is Feeling.SHAKY_SWEATY and flag.suppressed_because is None
    assert handled.replies[0].text.splitlines()[1] == "Call the ambulance now on 995."


@pytest.mark.parametrize("path", ("button", "log"))
async def test_the_button_and_the_log_raise_the_fall_said_with_a_held_back_flag(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, path: str
) -> None:
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=False)
    await warfarin(sg, h.owner)
    clock.set(at(22, 30))
    service = not_feeling_well if path == "button" else log_symptom
    done = await service(
        sg, context=h.owner, store=STORE, transcriber=TRANSCRIBER, registry=REGISTRY, via=h.via,
        words=FELL_AND_SHAKY["en"],
    )
    assert done.flag_id is not None
    flag = await sg.get(Flag, done.flag_id)
    assert flag is not None and flag.feeling is Feeling.FALL
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[Step.AMBULANCE]]


def test_falling_asleep_is_not_a_fall() -> None:
    """On a thinner a fall is the ambulance: "I cannot fall asleep" must not be one. A fall
    said beside it still is."""
    assert detect("I cannot fall asleep") is None
    assert detect("he keeps falling asleep in the chair") is None
    assert detect("I fell asleep and fell out of bed") is Feeling.FALL
    assert detect_all("my chest is tight and I fell") == [Feeling.CHEST_TIGHTNESS, Feeling.FALL]


async def test_a_real_database_error_reading_his_list_is_the_ambulance(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read fails in the database itself: its savepoint is rolled back, the request's
    transaction goes on, and the flag, the ladder, the reply and the notice all go."""
    from sqlalchemy import text

    async def broken(session: AsyncSession, **_: object) -> bool:
        await session.execute(text("SELECT * FROM no_such_table"))
        return False

    monkeypatch.setattr("app.safety.red_flags.on_a_blood_thinner", broken)
    h = await _home_with_a_directory(sg, tmp_path, clock, hospital=True)
    clock.set(at(22, 30))
    handled = await h.inbound(sg, PA, FELL["en"])
    assert handled.outcome == "red_flag" and handled.flag_id is not None
    assert await sg.get(Flag, handled.flag_id) is not None
    assert (await sg.scalars(select(Ladder).where(Ladder.flag_id == handled.flag_id))).one()
    assert handled.replies[0].text.splitlines()[1] == "Call the ambulance now on 995."
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[Step.AMBULANCE]]



# --- until a clinician signs the tiers (the B1 review) -----------------------------------------


@pytest.mark.parametrize("feeling", sorted(RED_FLAGS))
@pytest.mark.parametrize("after_hours", (False, True))
@pytest.mark.parametrize("hospital", (False, True))
def test_until_the_tiers_are_signed_off_every_red_flag_is_the_ambulance(
    feeling: Feeling, after_hours: bool, hospital: bool
) -> None:
    """`Settings.red_flag_tiers` unset: the one door gives the ambulance for every red flag,
    whatever the hour, the directory or his list — no level-of-care step of Nura's own."""
    tan = _listed("Dr Tan", ProviderKind.DOCTOR, hours=(time(9, 0), time(17, 0)))
    glen = _listed("Gleneagles", ProviderKind.HOSPITAL, panel=True, n=1)
    local = datetime(2026, 9, 14, 22 if after_hours else 10, 30, tzinfo=SGT)
    step = escalation_for(
        feeling,
        providers=[tan, glen] if hospital else [tan],
        local=local,
        emergency_number="995",
        anticoagulated=False,
        tiered=False,
    )
    assert (step.step, step.tiered) == (Step.AMBULANCE, False)


def _untiered(h: Home) -> Home:
    """The same home on a build whose tiers are not signed off."""
    settings = dataclasses.replace(h.via.settings, red_flag_tiers=False)
    return dataclasses.replace(h, via=dataclasses.replace(h.via, settings=settings))


@pytest.mark.parametrize("words", ("I fell in the bathroom", "my left leg is swollen", "my chest is tight"))
@pytest.mark.parametrize("hour", (15, 22))
@pytest.mark.parametrize("hospital", (False, True))
async def test_a_build_without_the_sign_off_never_says_today_the_hospital_or_the_morning(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, words: str, hour: int, hospital: bool
) -> None:
    h = _untiered(await _home_with_a_directory(sg, tmp_path, clock, hospital=hospital))
    clock.set(at(hour, 30))
    handled = await h.inbound(sg, PA, words)
    assert handled.outcome == "red_flag"
    said = handled.replies[0].text.splitlines()
    assert said[1] == "Call the ambulance now on 995."
    for line in said:
        for never in ("today", "emergency department", "morning", "Sit down", "insurance"):
            assert never not in line, line
    assert h.sent_to(h.mei)[-1].splitlines() == ["This one we do not wait for.", *NOTICE[Step.AMBULANCE]]
