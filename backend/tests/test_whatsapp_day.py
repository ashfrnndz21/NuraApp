"""E19-03 acceptance, with E11-01: a full day without the app.

    Dad can complete a full day without opening the app.

Pa's Monday on WhatsApp alone, on the frozen clock, over the trigger engine (#121) and the
fixture provider — no Meta call. At breakfast the engine sends the morning card and, his visit
being tomorrow, the visit card; he answers "Taken" and the tablet is written as his tap, so
nothing nags him about it later; at lunch he sends a voice note, heard in the region and kept
as his own note; in the evening the feeling check-in goes and his one word back is written
down; and his chief gets the family notice, a count and never what was said. Nothing reaches
him through the app.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp.classifier import RuleClassifier
from app.channels.whatsapp.inbound import Handled, handle_inbound
from app.channels.whatsapp.outbound.level0 import run_family_notice, run_feeling_check_in
from app.channels.whatsapp.provider import DevInbound
from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.triggers.engine import Report, run_due
from app.delivery.triggers.models import Delivery, DeliveryChannel, DeliveryOutcome, TriggerType
from app.medicines.service import proud_days
from tests.delivery_support import MEI, PA, Home, home
from tests.visits import visit

SGT = ZoneInfo("Asia/Singapore")


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT).astimezone(UTC)


async def _run(sg: AsyncSession, h: Home, clock: FrozenClock, when: datetime) -> Report:
    clock.set(when)
    return await run_due(sg, via=h.via, profile_id=h.owner.profile_id, at=when)


def _to_him(report: Report, h: Home) -> dict[TriggerType, Delivery]:
    return {
        sent.delivery.trigger_type: sent.delivery
        for sent in report.sent
        if sent.delivery.to_person_id == h.pa.id
    }


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
    h = await home(sg, tmp_path)
    await visit(sg, h.owner, when=at(10, day=15), doctor="Dr Tan")

    # 07:31, breakfast: the morning card, and the visit card for tomorrow — both on WhatsApp.
    breakfast = _to_him(await _run(sg, h, clock, at(7, 31)), h)
    morning = breakfast[TriggerType.MORNING]
    assert morning.outcome is DeliveryOutcome.SENT and morning.via is DeliveryChannel.WHATSAPP
    assert morning.template_name == "morning_card"
    reminder = breakfast[TriggerType.VISIT_TOMORROW]
    assert reminder.outcome is DeliveryOutcome.SENT and reminder.via is DeliveryChannel.WHATSAPP
    assert reminder.template_name == "visit_reminder"
    said = h.sent_to(h.pa)
    assert any(
        text.splitlines()[:2]
        == ["Good morning, Pa, this is Nura.", "Today is Monday 14 September."]
        for text in said
    )
    assert any("Dr Tan" in text and "Tuesday 15 September" in text for text in said)

    # 07:40, "Taken": the tablet is written as his tap; later runs do not ask him about it.
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

    # 18:00, the feeling check-in; one word back is written down without a second yes.
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

    # The whole day: everything he read came on WhatsApp; nothing through the app.
    assert h.push.sent == []
    assert len(h.sent_to(h.pa)) >= 6
