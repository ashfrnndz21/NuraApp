"""E19-03 acceptance, with E11-01: a full day without the app, by the scheduler.

    Dad can complete a full day without opening the app.

Pa's Monday on WhatsApp alone, driven the way a deployment drives it: the dev run's frozen
clock stood at each hour (`POST /dev/clock`) and the trigger engine run there
(`POST /dev/run-triggers`, the door onto `run_due` the region's scheduler calls every five
minutes). No service is called directly: everything he sends comes in through the signed
webhook, as the provider posts it, and the fixture provider carries everything out — no Meta
call.

At breakfast the engine sends the morning card and, his visit being tomorrow, the visit card;
he answers "Taken" and the tablet is written as his tap, so nothing asks him about it later;
at lunch he sends a voice note, heard in the region and kept as his own note; at his check-in
time, from his settings, the check-in goes, and his "OK" back is written down; in the evening
his chief gets the family notice, a count and never what was said, and the helper does not.
Each goes once. Nothing reaches him through the app.
"""

from __future__ import annotations

import itertools
import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.keys.scopes import Scope
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.trio_api_support import add_medicine

SGT = ZoneInfo("Asia/Singapore")
PA = "+6591110061"
MEI = "+6592220061"
SITI = "+6597770061"
EVERY_PART = [scope.value for scope in Scope if scope is not Scope.PROFILE]
HELPER = ["medicines", "emergency", "send"]
DAY = "2026-09-14"
_ids = itertools.count(1)


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT)


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
        await _ok(await self.client.post("/dev/clock", json={"at": at(hour, minute).isoformat()}))

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
            "timestamp": str(int(at(hour, minute).timestamp())),
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
        self.pa = await register_by_phone(self.deployment, PA, "Pa", language="en")
        self.profile_id = await own_profile(self.deployment, self.pa, language="en")
        his = bearer(self.pa["token"])
        self.mei = await register_by_phone(self.deployment, MEI, "Mei", language="en")
        await let_in(self.deployment, self.pa, self.profile_id, MEI, EVERY_PART, "daughter")
        await _ok(
            await self.client.post(
                f"/profiles/{self.profile_id}/keys",
                json={"holder_phone_e164": MEI, "role": "chief"},
                headers=his,
            ),
            201,
        )
        self.siti = await register_by_phone(self.deployment, SITI, "Siti", language="ms")
        await let_in(
            self.deployment, self.pa, self.profile_id, SITI, HELPER, "helper", holder_display_name="Siti"
        )
        await _ok(
            await self.client.post(
                f"/profiles/{self.profile_id}/keys",
                json={"holder_phone_e164": SITI, "role": "helper", "scopes": HELPER},
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
            "scheduled_at": at(10, day=15).isoformat(),
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


def _to(rows: list[dict[str, Any]], person: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {row["trigger_type"]: row for row in rows if row["to_person_id"] == person["person_id"]}


def _of(rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [row for row in rows if row["trigger_type"] == kind]


async def test_pa_completes_a_full_day_on_whatsapp_without_opening_the_app(
    deployment: Deployment,
) -> None:
    day = Day(deployment)
    await day.set_up()

    # 07:31, breakfast: the morning card, and the visit card for tomorrow — both on WhatsApp.
    breakfast = await day.run(7, 31)
    his = _to(breakfast, day.pa)
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
    visit = his["visit_tomorrow"]
    assert (visit["outcome"], visit["channel"], visit["template_name"]) == (
        "sent",
        "whatsapp",
        "visit_reminder",
    )
    assert "Dr Tan" in visit["text"] and "Tuesday 15 September" in visit["text"]
    assert not _of(breakfast, "check_in") and not _of(breakfast, "family_notice")

    # 07:40, "Taken": the tablet is written as his tap; the runs after do not ask about it.
    await day.says(PA, 7, 40, {"type": "text", "text": {"body": "Taken"}})
    assert day.said_to(PA)[-1][0] == "Thank you, I wrote it down."
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
        PA, 12, 30, {"type": "audio", "audio": {"id": "pa-voice-market", "mime_type": "audio/ogg; codecs=opus"}}
    )
    assert day.said_to(PA)[-1] == ["Nura kept your voice note."]

    # 18:00, his check-in time: the check-in, once, on WhatsApp.
    evening = await day.run(18)
    [asked] = _of(evening, "check_in")
    assert asked["to_person_id"] == day.pa["person_id"]
    assert (asked["outcome"], asked["channel"], asked["template_name"], asked["rule"]) == (
        "sent",
        "whatsapp",
        "feeling_check_in",
        "check_in_time_reached",
    )
    assert asked["why"] == {"check_in_at": "18:00"}
    assert asked["text"].splitlines() == [
        "Hello Pa, this is Nura.",
        "How are you feeling today?",
        "Answer OK, tired or pain.",
    ]
    assert not _of(await day.run(18, 5), "check_in")

    # 18:10, his one word back is written down, without a second yes.
    await day.says(PA, 18, 10, {"type": "text", "text": {"body": "ok"}})
    assert day.said_to(PA)[-1] == ["Thank you for telling me.", "I wrote it down."]
    felt = await _ok(
        await deployment.client.get(
            f"/profiles/{day.profile_id}/facts",
            params={"subject": "feeling"},
            headers=bearer(day.pa["token"]),
        )
    )
    assert [fact["attribute"] for fact in felt] == ["reported"]

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
    assert day.said_to(SITI) == []
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
        "check_in_time_reached",
        "evening_family_notice",
    } <= {row["rule"] for row in sent}
    # Morning card, visit card, the Taken reply, the voice note's, the check-in, its reply.
    assert len(day.said_to(PA)) >= 6

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
