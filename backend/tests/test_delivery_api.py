"""The delivery routes (E11-05, E11-06): the settings, the log, the ladder's "I have it", and
the dev-only engine run the checkpoint drives."""

from __future__ import annotations

from typing import Any

from app.clock import FrozenClock
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.test_feed_api import _caregiver_key

PA = "+6591119921"
MEI = "+6591119922"


async def test_the_settings_are_read_changed_and_an_alert_is_never_capped(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    now = await deployment.client.get(f"/profiles/{profile_id}/delivery-settings", headers=his)
    assert now.status_code == 200, now.text
    body = now.json()
    # The one breakfast time, not said yet: 07:30, the morning card and the breakfast tablet.
    assert body["breakfast_at"] == "07:30:00" and body["anchors"]["breakfast"] == "07:30:00"
    assert body["caps"]["flag"] is None
    assert body["channels"]["reorder"] == ["app_push", "whatsapp", "caregiver"]
    assert body["channels"]["flag"] == ["whatsapp", "app_push"]
    changed = await deployment.client.put(
        f"/profiles/{profile_id}/delivery-settings",
        json={
            "skip_quiet_days": True,
            "channels": {"reorder": ["whatsapp"]},
            "caps": {"reorder": 2},
        },
        headers=his,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["skip_quiet_days"] is True and changed.json()["caps"]["reorder"] == 2
    assert changed.json()["channels"]["reorder"] == ["whatsapp"]
    refused = await deployment.client.put(
        f"/profiles/{profile_id}/delivery-settings", json={"caps": {"flag": 5}}, headers=his
    )
    assert refused.status_code == 400 and refused.json()["refusal"] == "AlertsAreNeverHeld"
    # Nor its channels (#162): a red flag goes every way each person can be reached.
    routed = await deployment.client.put(
        f"/profiles/{profile_id}/delivery-settings",
        json={"channels": {"flag": ["caregiver"]}},
        headers=his,
    )
    assert routed.status_code == 400 and routed.json()["refusal"] == "AlertsGoEveryWay"
    after = await deployment.client.get(f"/profiles/{profile_id}/delivery-settings", headers=his)
    assert after.json()["channels"]["flag"] == ["whatsapp", "app_push"]


async def test_the_log_is_the_owners_and_his_chiefs_and_the_dev_run_fills_it(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    felt = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "fall"}, headers=his
    )
    assert felt.status_code == 201
    ran = await deployment.client.post("/dev/run-triggers", json={"profile_id": profile_id})
    assert ran.status_code == 200, ran.text
    assert ran.json()["day"] == "2026-09-03"
    log = await deployment.client.get(f"/profiles/{profile_id}/deliveries", headers=his)
    assert log.status_code == 200, log.text
    assert all(row["rule"] for row in log.json())
    mei = await register_by_phone(deployment, MEI, "Mei")
    await _caregiver_key(deployment, pa, profile_id, MEI, ["medicines", "emergency"])
    hers = await deployment.client.get(
        f"/profiles/{profile_id}/deliveries", headers=bearer(mei["token"])
    )
    assert hers.status_code == 403 and hers.json()["refusal"] == "NotTheirsToRead"


async def test_the_breakfast_he_saves_on_the_web_is_the_card_s_and_the_routine_s(
    deployment: Deployment,
) -> None:
    """#115's About you saves his breakfast through `PUT …/settings`; the morning card and the
    breakfast tablet read that same field (`GET …/settings`), not a time of their own."""
    pa = await register_by_phone(deployment, "+6591119923", "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    saved = await deployment.client.put(
        f"/profiles/{profile_id}/settings",
        json={"language": "en", "breakfast_time": "08:15"},
        headers=his,
    )
    assert saved.status_code == 200, saved.text
    shown = await deployment.client.get(f"/profiles/{profile_id}/settings", headers=his)
    assert shown.status_code == 200 and shown.json()["breakfast_time"][:5] == "08:15"
    delivery = await deployment.client.get(f"/profiles/{profile_id}/delivery-settings", headers=his)
    assert delivery.json()["breakfast_at"] == "08:15:00"
    assert delivery.json()["anchors"]["breakfast"] == "08:15:00"


async def test_one_reminder_of_a_visit_reaches_him_the_day_before(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """#128's logistics card, #119's anticipation nudge and E11's visit reminder all say the
    visit is tomorrow. One reaches him: the visit reminder, naming the card on his feed; the
    nudge handed over before the card was made is skipped, written down once, never sent."""
    from tests.test_visit_day import FRIDAY_MORNING, household

    house = await household(deployment)
    clock.set(FRIDAY_MORNING)  # 10:00 on Friday in Singapore, his check-in; the visit is Saturday
    agreed = await deployment.client.post(
        house.at("/consents/whatsapp"),
        json={"language": "en", "captured_via": "app"},
        headers=house.his,
    )
    assert agreed.status_code == 201, agreed.text
    handed = await deployment.client.post(house.at("/nudges/plan"), headers=house.his)
    assert handed.status_code == 201, handed.text
    page = await deployment.client.get(house.at("/feed"), headers=house.his)
    (card,) = [item for item in page.json()["items"] if item["type"] == "visit_logistics"]

    async def log() -> list[dict[str, Any]]:
        ran = await deployment.client.post(
            "/dev/run-triggers", json={"profile_id": house.profile_id}
        )
        assert ran.status_code == 200, ran.text
        rows = await deployment.client.get(
            house.at("/deliveries"), params={"day": "2026-09-04"}, headers=house.his
        )
        assert rows.status_code == 200, rows.text
        return [row for row in rows.json() if row["trigger_type"] in ("visit_tomorrow", "nudge")]

    first = await log()
    (reminder,) = [row for row in first if row["trigger_type"] == "visit_tomorrow"]
    assert reminder["outcome"] == "sent" and reminder["template_name"] == "visit_reminder"
    assert reminder["why"] == {
        "appointment_id": house.appointment_id,
        "feed_item_id": card["item_id"],
    }
    (nudge,) = [row for row in first if row["trigger_type"] == "nudge"]
    assert nudge["outcome"] == "skipped" and nudge["reason"] == "the visit reminder said it"
    assert await log() == first
