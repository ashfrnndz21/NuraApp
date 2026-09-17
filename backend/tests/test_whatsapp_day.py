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

A second version of the same acceptance line, `test_pa_completes_a_full_day_on_whatsapp_by_the_scheduler`,
walks the same day driven the way a deployment actually drives it: the dev run's frozen clock
stood at each hour (`POST /dev/clock`) and the trigger engine run there (`POST /dev/run-triggers`,
the door onto `run_due` the region's scheduler calls every five minutes), with everything he
sends coming in through the signed webhook, as the provider posts it — no service called
directly.
"""

from __future__ import annotations

import itertools
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
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
from app.keys.scopes import Scope
from app.medicines.models import DoseTaken
from app.medicines.service import proud_days
from app.memory.models import Fact
from app.safety.red_flags import Flag
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.delivery_support import MEI, PA, Home, home
from tests.medicines_support import add, label
from tests.trio_api_support import add_medicine
from tests.visits import visit

SGT = ZoneInfo("Asia/Singapore")

# The scheduler-driven test below registers its own household over HTTP rather than using the
# `home()` fixture, so it uses its own phone numbers to stay clear of the ones `delivery_support`
# hands the direct-call tests above.
SCHED_PA = "+6591110061"
SCHED_MEI = "+6592220061"
SCHED_SITI = "+6597770061"
EVERY_PART = [scope.value for scope in Scope if scope is not Scope.PROFILE]
HELPER = ["medicines", "emergency", "send"]
DAY = "2026-09-14"
_ids = itertools.count(1)


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT).astimezone(UTC)


def _sched_at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT)


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


async def test_a_taken_heard_too_unsurely_never_stops_the_ladder_from_asking(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """A false Taken closes the dose window and stops the escalation ladder before it ever
    runs — nobody asks him, nobody asks the helper, nobody tells his chief; a missed dose
    becomes invisible. So a voice note heard at 0.45 confidence that string-matches Taken
    ("Taken.", below `CONFIDENCE_THRESHOLD`) is never trusted to write the tap: the window
    stays open, and the ladder asks him at rung 0 exactly as it would with no reply at all."""
    clock.set(at(6))
    h = await home(sg, tmp_path)

    # 07:35, the window open: he is heard, but not surely enough — nothing is written.
    clock.set(at(7, 35))
    unsure = await _voice(sg, h, "pa-voice-taken-unsure")
    assert unsure.outcome == "voice_note" and unsure.note_id is not None
    assert not list(await sg.scalars(select(DoseTaken)))

    # 08:31, the window closed: the ladder asks him at rung 0, exactly as an untapped dose
    # always does — nothing about the low-confidence note held it back or answered for him.
    dose_ask = _to_him(await _run(sg, h, clock, at(8, 31)), h)[TriggerType.DOSE]
    assert dose_ask.outcome is DeliveryOutcome.SENT and dose_ask.rung == 0
    assert dose_ask.rule == "dose_window_closed_untapped"
    assert not list(await sg.scalars(select(DoseTaken)))


async def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


class Day:
    """Pa's household on one backend, and the three things a day is made of: the clock
    moved, the engine run, and a message sent to the number."""

    def __init__(self, deployment: Deployment) -> None:
        self.deployment = deployment
        self.client = deployment.client

    async def clock(self, hour: int, minute: int = 0) -> None:
        await _ok(await self.client.post("/dev/clock", json={"at": _sched_at(hour, minute).isoformat()}))

    async def run(self, hour: int, minute: int = 0) -> list[dict[str, Any]]:
        """The clock stood at this hour, then one engine run: the rows it wrote."""
        await self.clock(hour, minute)
        ran = await _ok(
            await self.client.post("/dev/run-triggers", json={"profile_id": self.profile_id})
        )
        assert ran["day"] == DAY
        rows: list[dict[str, Any]] = ran["deliveries"]
        return rows

    async def says(self, from_e164: str, hour: int, minute: int, message: dict[str, Any]) -> None:
        """A message to the number, posted by the provider to the signed webhook."""
        await self.clock(hour, minute)
        posted = {
            "from": from_e164.lstrip("+"),
            "id": f"wamid.day.{next(_ids)}",
            "timestamp": str(int(_sched_at(hour, minute).timestamp())),
            **message,
        }
        body = json.dumps(
            {
                "object": "whatsapp_business_account",
                "entry": [{"changes": [{"value": {"messages": [posted]}}]}],
            }
        ).encode()
        handled = await _ok(
            await self.client.post(
                "/whatsapp/webhook",
                content=body,
                headers={
                    "content-type": "application/json",
                    "X-Hub-Signature-256": self.deployment.whatsapp.sign(body),
                },
            )
        )
        assert handled == {"handled": 1}

    def said_to(self, phone: str) -> list[list[str]]:
        """Every WhatsApp message to this number, oldest first, as its lines."""
        return [one.text.splitlines() for one in self.deployment.whatsapp.sent if one.to_e164 == phone]

    async def set_up(self) -> None:
        """Pa, his own profile, WhatsApp agreed; Mei his chief; Siti the helper; his breakfast
        at half past seven and his check-in at six in the evening, from his settings; his blood
        pressure tablet from its label; Dr Tan tomorrow at 10. All over HTTP, at 06:00."""
        await self.clock(6)
        self.pa = await register_by_phone(self.deployment, SCHED_PA, "Pa", language="en")
        self.profile_id = await own_profile(self.deployment, self.pa, language="en")
        his = bearer(self.pa["token"])
        self.mei = await register_by_phone(self.deployment, SCHED_MEI, "Mei", language="en")
        await let_in(self.deployment, self.pa, self.profile_id, SCHED_MEI, EVERY_PART, "daughter", role="chief")
        await _ok(
            await self.client.post(
                f"/profiles/{self.profile_id}/keys",
                json={"holder_phone_e164": SCHED_MEI, "role": "chief"},
                headers=his,
            ),
            201,
        )
        self.siti = await register_by_phone(self.deployment, SCHED_SITI, "Siti", language="ms")
        await let_in(
            self.deployment,
            self.pa,
            self.profile_id,
            SCHED_SITI,
            HELPER,
            "helper",
            holder_display_name="Siti",
            role="helper",
        )
        await _ok(
            await self.client.post(
                f"/profiles/{self.profile_id}/keys",
                json={"holder_phone_e164": SCHED_SITI, "role": "helper", "scopes": HELPER},
                headers=his,
            ),
            201,
        )
        await _ok(
            await self.client.post(
                f"/profiles/{self.profile_id}/consents/whatsapp",
                json={"language": "en", "captured_via": "app"},
                headers=his,
            ),
            201,
        )
        settings = await _ok(
            await self.client.put(
                f"/profiles/{self.profile_id}/settings",
                json={"language": "en", "breakfast_time": "07:30", "checkin_time": "18:00"},
                headers=his,
            )
        )
        assert settings["checkin_time"] == "18:00"
        await add_medicine(self.deployment, self.pa["token"], self.profile_id, "amlodipine", "5 mg", "1 tab OM")
        tan = await _ok(
            await self.client.post(
                f"/profiles/{self.profile_id}/providers",
                json={"name": "Dr Tan", "kind": "doctor"},
                headers=his,
            ),
            201,
        )
        booking = {
            "provider_id": tan["provider_id"],
            "scheduled_at": _sched_at(10, day=15).isoformat(),
            "purpose": "blood pressure check",
        }
        yes = await _ok(
            await self.client.post(
                f"/profiles/{self.profile_id}/confirmations",
                json={"subject": "appointment", **booking},
                headers=his,
            ),
            201,
        )
        await _ok(
            await self.client.post(
                f"/profiles/{self.profile_id}/appointments",
                json={**booking, "confirmation_id": yes["confirmation_id"]},
                headers=his,
            ),
            201,
        )


def _rows_to(rows: list[dict[str, Any]], person: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {row["trigger_type"]: row for row in rows if row["to_person_id"] == person["person_id"]}


def _of(rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [row for row in rows if row["trigger_type"] == kind]


async def test_pa_completes_a_full_day_on_whatsapp_by_the_scheduler(
    deployment: Deployment,
) -> None:
    """The same E19-03/E11-01 day as above, but driven the way a deployment actually drives it:
    the dev run's frozen clock stood at each hour (`POST /dev/clock`) and the trigger engine run
    there (`POST /dev/run-triggers`, the door onto `run_due` the region's scheduler calls every
    five minutes). No service is called directly: everything he sends comes in through the
    signed webhook, as the provider posts it, and the fixture provider carries everything out —
    no Meta call.

    At breakfast the engine sends the morning card and, his visit being tomorrow, the visit
    card; he answers "Taken" and the tablet is written as his tap, so nothing asks him about it
    later; at lunch he sends a voice note, heard in the region and kept as his own note; at his
    check-in time, from his settings, his new tablet is still a change the day's smart nudge
    (W7) asks him about, so the plain check-in stands down for it; in the evening his chief gets
    the family notice, a count and never what was said, and the helper does not. Each goes once.
    Nothing reaches him through the app."""
    day = Day(deployment)
    await day.set_up()

    # 07:31, breakfast: the morning card, and the visit card for tomorrow — both on WhatsApp.
    breakfast = await day.run(7, 31)
    his = _rows_to(breakfast, day.pa)
    morning = his["morning"]
    assert (morning["outcome"], morning["channel"], morning["template_name"]) == (
        "sent",
        "whatsapp",
        "morning_card",
    )
    assert morning["text"].splitlines()[:2] == [
        "Good morning, Pa, this is Nura.",
        "Today is Monday 14 September.",
    ]
    visit_card = his["visit_tomorrow"]
    assert (visit_card["outcome"], visit_card["channel"], visit_card["template_name"]) == (
        "sent",
        "whatsapp",
        "visit_reminder",
    )
    assert "Dr Tan" in visit_card["text"] and "Tuesday 15 September" in visit_card["text"]
    assert not _of(breakfast, "check_in") and not _of(breakfast, "family_notice")

    # 07:40, "Taken": the tablet is written as his tap; the runs after do not ask about it.
    await day.says(SCHED_PA, 7, 40, {"type": "text", "text": {"body": "Taken"}})
    assert day.said_to(SCHED_PA)[-1][0] == "Thank you, I wrote it down."
    for hour in (10, 13):
        later = await day.run(hour)
        assert not [
            row
            for row in later
            if row["trigger_type"] in ("dose", "doses_untapped") and row["outcome"] == "sent"
        ]
        # His check-in time is six in the evening, from his settings: not yet.
        assert not _of(later, "check_in")

    # 12:30, a voice note: heard in the region, kept as his own note, and he is told so.
    await day.says(
        SCHED_PA,
        12,
        30,
        {"type": "audio", "audio": {"id": "pa-voice-market", "mime_type": "audio/ogg; codecs=opus"}},
    )
    assert day.said_to(SCHED_PA)[-1] == ["Nura kept your voice note."]

    # 18:00, his check-in time: his new tablet is a change the day's smart nudge (W7) already
    # asks him about, so the plain question stands down rather than asking him twice — once,
    # on WhatsApp, either way.
    evening = await day.run(18)
    [asked] = _of(evening, "check_in")
    assert asked["to_person_id"] == day.pa["person_id"]
    assert (asked["outcome"], asked["rule"]) == ("skipped", "check_in_time_reached")
    assert asked["why"] == {"check_in_at": "18:00"}
    [nudged] = _of(evening, "nudge")
    assert (nudged["outcome"], nudged["channel"], nudged["template_name"]) == (
        "sent",
        "whatsapp",
        "nudge",
    )
    assert nudged["text"].splitlines()[-1] == "How are you feeling today?"
    assert not _of(await day.run(18, 5), "check_in")

    # 18:10, his one word back: the nudge asked the same feeling question the plain check-in
    # would have (#205, fixed) — `_check_in_open` (inbound.py) now reads what he was actually
    # sent (`WhatsAppMessage.asks_feeling`), not which template's name carried it — so his
    # "OK" is read as his answer, the same as it would be to the plain check-in.
    await day.says(SCHED_PA, 18, 10, {"type": "text", "text": {"body": "ok"}})
    assert day.said_to(SCHED_PA)[-1] == ["Thank you for telling me.", "I wrote it down."]
    felt = await _ok(
        await deployment.client.get(
            f"/profiles/{day.profile_id}/facts",
            params={"subject": "feeling"},
            headers=bearer(day.pa["token"]),
        )
    )
    [feeling] = felt
    assert feeling["attribute"] == "reported" and feeling["value"] == "ok"

    # 20:00, the family notice to his chief: a count, never what was said. Not to the helper,
    # and not to him.
    notice_rows = _of(await day.run(20), "family_notice")
    [notice] = notice_rows
    assert notice["to_person_id"] == day.mei["person_id"] and notice["standing"] == "chief"
    assert (notice["outcome"], notice["channel"], notice["template_name"], notice["rule"]) == (
        "sent",
        "whatsapp",
        "family_digest",
        "evening_family_notice",
    )
    first, second = notice["text"].splitlines()
    assert re.fullmatch(r"Nura wrote down \d+ things about Pa this week\.", first)
    assert second == "You can read them in the app."
    assert notice["why"] == {"days": 7}  # the count is in her message only
    assert day.said_to(SCHED_SITI) == []
    assert not _of(await day.run(20, 5), "family_notice")

    # The whole day, as the delivery log keeps it: every message that reached anyone went on
    # WhatsApp, each rule named; nothing went through the app.
    logged = await _ok(
        await deployment.client.get(
            f"/profiles/{day.profile_id}/deliveries",
            params={"day": DAY},
            headers=bearer(day.pa["token"]),
        )
    )
    sent = [row for row in logged if row["outcome"] == "sent"]
    assert {row["channel"] for row in sent} == {"whatsapp"}
    assert {
        "breakfast_anchor_reached",
        "visit_tomorrow",
        "nudge_handed_over",
        "evening_family_notice",
    } <= {row["rule"] for row in sent}
    # Morning card, visit card, the Taken reply, the voice note's, the day's nudge, its reply.
    assert len(day.said_to(SCHED_PA)) >= 6

    # The family's own log and settings (E11-05, #137): Mei, his chief, reads both rules there,
    # and each is a kind of message whose channels and cap the family can change.
    hers = await _ok(
        await deployment.client.get(
            f"/profiles/{day.profile_id}/deliveries",
            params={"day": DAY},
            headers=bearer(day.mei["token"]),
        )
    )
    assert {"check_in_time_reached", "evening_family_notice"} <= {row["rule"] for row in hers}
    kinds = await _ok(
        await deployment.client.get(
            f"/profiles/{day.profile_id}/delivery-settings", headers=bearer(day.mei["token"])
        )
    )
    assert kinds["caps"]["check_in"] == 1 and kinds["caps"]["family_notice"] == 1
    assert kinds["channels"]["check_in"] == ["whatsapp", "app_push"]
    assert kinds["channels"]["family_notice"] == ["app_push", "whatsapp"]
