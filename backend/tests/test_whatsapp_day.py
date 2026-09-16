"""E19-03 acceptance, with E11-01: a full day without the app.

    Dad can complete a full day without opening the app.

Pa's Monday on WhatsApp alone, on the frozen clock, over the trigger engine (#121) and the
fixture provider — no Meta call. Before breakfast the reorder date is reached and Mei, on
duty, is asked to order more, once, capped the second time the same morning; at breakfast the
engine sends the morning card and, his visit being tomorrow, the visit card; he answers
"Taken" and the tablet is written as his tap, so nothing nags him about it later; at lunch he
sends a voice note, heard in the region and kept as his own note; at dinner a second tablet's
window closes untapped, Nura asks him, and his own voice — "sudah makan ubat" — writes the tap
the same door typing "Taken" would; in the evening the feeling check-in goes and his one word
back is written down; his chief gets the family notice, a count and never what was said; and
at night, inside the quiet hours, a red word goes straight to the roster — never quiet, never
capped, the same ladder a red flag climbs at noon. Nothing reaches him through the app, and at
the end of the day his record — the taps, the fact, the flag, the note — is exactly what the
app's own buttons would have written.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp.classifier import RuleClassifier
from app.channels.whatsapp.inbound import Handled, handle_inbound
from app.channels.whatsapp.outbound.level0 import run_family_notice, run_feeling_check_in
from app.channels.whatsapp.provider import DevInbound
from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.triggers.engine import Report, run_due
from app.delivery.triggers.models import (
    Delivery,
    DeliveryChannel,
    DeliveryOutcome,
    Ladder,
    TriggerType,
)
from app.delivery.triggers.rules import RULES
from app.medicines.models import DoseTaken
from app.medicines.service import proud_days
from app.memory.models import Fact
from app.safety.red_flags import Flag
from tests.delivery_support import MEI, PA, Home, home
from tests.medicines_support import add, label
from tests.visits import visit

SGT = ZoneInfo("Asia/Singapore")


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT).astimezone(UTC)


async def _run(sg: AsyncSession, h: Home, clock: FrozenClock, when: datetime) -> Report:
    clock.set(when)
    return await run_due(sg, via=h.via, profile_id=h.owner.profile_id, at=when)


def _to(report: Report, person_id: object) -> dict[TriggerType, Delivery]:
    return {
        sent.delivery.trigger_type: sent.delivery
        for sent in report.sent
        if sent.delivery.to_person_id == person_id
    }


def _to_him(report: Report, h: Home) -> dict[TriggerType, Delivery]:
    return _to(report, h.pa.id)


async def _voice(sg: AsyncSession, h: Home, media_id: str) -> Handled:
    message = DevInbound(from_e164=PA, media_id=media_id, content_type="audio/ogg; codecs=opus")
    return await handle_inbound(
        sg,
        settings=h.via.settings,
        providers=h.via.providers,
        number=h.via.number,
        classifier=RuleClassifier(),
        message=message.as_message(utcnow()),
    )


async def test_pa_completes_a_full_day_on_whatsapp_without_opening_the_app(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    # Two tablets left of the blood pressure tablet: the reorder date is today (E05-06).
    h = await home(sg, tmp_path, quantity=2)
    dinner = await add(sg, h.owner, label("atorvastatin", "20 mg", "1 tab daily with dinner"))
    assert dinner.line is not None
    await visit(sg, h.owner, when=at(10, day=15), doctor="Dr Tan")

    # 07:20, before breakfast: the reorder date reached, told to Mei, on duty — not to him;
    # his own visit-tomorrow reminder, not tied to breakfast, may go the same run.
    first = await _run(sg, h, clock, at(7, 20))
    reorder = _to(first, h.mei.id)[TriggerType.REORDER]
    assert reorder.outcome is DeliveryOutcome.SENT and reorder.via is DeliveryChannel.WHATSAPP
    assert reorder.rule == "reorder_date_reached"
    assert reorder.to_person_id == h.mei.id  # to whoever is on duty, never to him

    # 07:31, breakfast: the morning card, and, his visit being tomorrow, the visit card.
    second = await _run(sg, h, clock, at(7, 31))
    breakfast = {**_to_him(first, h), **_to_him(second, h)}
    morning = breakfast[TriggerType.MORNING]
    assert morning.outcome is DeliveryOutcome.SENT and morning.via is DeliveryChannel.WHATSAPP
    assert morning.template_name == "morning_card"
    reminder = breakfast[TriggerType.VISIT_TOMORROW]
    assert reminder.outcome is DeliveryOutcome.SENT and reminder.via is DeliveryChannel.WHATSAPP
    assert reminder.template_name == "visit_reminder"
    # The reorder rule is true again at breakfast and capped: once a day, said, never twice.
    capped = _to(second, h.mei.id).get(TriggerType.REORDER)
    if capped is not None:  # the same run that sends breakfast may also see the cap
        assert capped.outcome is DeliveryOutcome.CAPPED
    else:
        capped = _to(await _run(sg, h, clock, at(7, 35)), h.mei.id)[TriggerType.REORDER]
        assert capped.outcome is DeliveryOutcome.CAPPED
    said = h.sent_to(h.pa)
    assert any(
        text.splitlines()[:2]
        == ["Good morning, Pa, this is Nura.", "Today is Monday 14 September."]
        for text in said
    )
    assert any("Dr Tan" in text and "Tuesday 15 September" in text for text in said)

    # 07:40, "Taken": the breakfast tablet is written as his tap; later runs do not ask again.
    clock.set(at(7, 40))
    taken = await h.inbound(sg, PA, "Taken")
    assert taken.outcome == "taken"
    assert (await proud_days(sg, context=h.owner)).days == 1
    for hour in (10, 13):
        later = _to_him(await _run(sg, h, clock, at(hour)), h)
        assert not [
            row
            for kind, row in later.items()
            if kind in (TriggerType.DOSE, TriggerType.DOSES_UNTAPPED)
            and row.outcome is DeliveryOutcome.SENT
        ]

    # 12:30, a voice note: heard in the region, kept as his own note, and he is told so.
    clock.set(at(12, 30))
    noted = await _voice(sg, h, "pa-voice-market")
    assert noted.outcome == "voice_note" and noted.note_id is not None
    assert h.sent_to(h.pa)[-1] == "Nura kept your voice note."

    # 19:31, dinner's window closed with the statin untapped: he is asked, rung 0.
    dose_ask = _to_him(await _run(sg, h, clock, at(19, 31)), h)[TriggerType.DOSE]
    assert dose_ask.outcome is DeliveryOutcome.SENT and dose_ask.rung == 0
    assert dose_ask.rule == "dose_window_closed_untapped"

    # 19:35, he answers by voice, not by typing: "sudah makan ubat" writes the tap the same
    # door "Taken" typed does — heard and classified, never guessed at (E11-01).
    clock.set(at(19, 35))
    said_it = await _voice(sg, h, "pa-voice-taken")
    assert said_it.outcome == "taken" and said_it.note_id is None
    taps = (await sg.scalars(select(DoseTaken))).all()
    assert {t.line_id for t in taps} == {h.line.id, dinner.line.id}

    # 18:00 has already passed; the check-in still goes at its own time, once.
    clock.set(at(18))
    asked = await run_feeling_check_in(
        sg,
        settings=h.via.settings,
        providers=h.via.providers,
        number=h.via.number,
        profile_id=h.owner.profile_id,
    )
    assert asked.to_person_id == h.pa.id and asked.template_name == "feeling_check_in"
    answered = await h.inbound(sg, PA, "ok")
    assert answered.outcome == "check_in_answer" and answered.fact_id is not None

    # 20:00, the family notice to his chief: a count, never what was said.
    clock.set(at(20))
    [notice] = await run_family_notice(
        sg,
        settings=h.via.settings,
        providers=h.via.providers,
        number=h.via.number,
        profile_id=h.owner.profile_id,
    )
    assert notice.to_person_id == h.mei.id and notice.to_e164 == MEI
    assert notice.template_name == "family_digest"

    # 22:30, inside the quiet hours: a red word from him goes straight to the roster (Mei, on
    # duty), never quiet and never capped — the same ladder a red flag climbs at any hour.
    assert RULES[TriggerType.FLAG].quiet is False and RULES[TriggerType.FLAG].cap is None
    clock.set(at(22, 30))
    flagged = await h.inbound(sg, PA, "I fell in the bathroom")
    assert flagged.outcome == "red_flag" and flagged.flag_id is not None
    ladder = (await sg.scalars(select(Ladder).where(Ladder.flag_id == flagged.flag_id))).one()
    assert ladder.rungs[0]["standing"] == "on_duty" and ladder.rungs[0]["after_minutes"] == 0
    assert h.sent_to(h.mei)[-1].splitlines()[:2] == [
        "This one we do not wait for.",
        "Pa is not feeling well.",
    ]

    # The whole day: everything he read came on WhatsApp; nothing through the app. His record
    # — the taps, the fact, the flag, the note — is exactly what the app's own buttons, the
    # feeling word, and the emergency card would have written.
    assert h.push.sent == []
    assert len(h.sent_to(h.pa)) >= 8
    assert len((await sg.scalars(select(DoseTaken).where(DoseTaken.by_person_id == h.pa.id))).all()) == 2
    fact = (
        await sg.scalars(
            select(Fact).where(Fact.profile_id == h.owner.profile_id, Fact.subject == "feeling")
        )
    ).one()
    assert fact.value == "ok" or fact.value == "OK" or fact.value.lower() == "ok"
    flag = await sg.get(Flag, flagged.flag_id)
    assert flag is not None and flag.feeling.value == "fall"
