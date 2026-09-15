"""E11-02: today's top three, ordered alert, reminder, insight; every card explains itself."""

from __future__ import annotations

from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.test_feed_api import _caregiver_key, _reading

PA = "+6591119911"
MEI = "+6591119912"


async def test_the_top_three_are_an_alert_a_reminder_and_an_insight_each_with_its_why(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = pa["token"]
    await _reading(deployment, profile_id, his, 138, 84)
    quiet = await deployment.client.get(f"/profiles/{profile_id}/feed/today", headers=bearer(his))
    assert quiet.status_code == 200, quiet.text
    assert [item["category"] for item in quiet.json()["items"]] == [
        "reminder",
        "insight",
        "insight",
    ]

    felt = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "fall"}, headers=bearer(his)
    )
    assert felt.status_code == 201, felt.text
    today = await deployment.client.get(f"/profiles/{profile_id}/feed/today", headers=bearer(his))
    items = today.json()["items"]
    assert len(items) == 3
    assert [item["category"] for item in items] == ["alert", "reminder", "insight"]
    assert [item["type"] for item in items][:2] == ["flag", "now"]
    for item in items:
        assert item["why"]["plain"], item["type"]
        assert item["action"] and item["colour"] in {"stable", "watch", "act"}
        assert item["autoplay"] is False
    assert items[0]["action"] == "call"


async def test_the_caregiver_gets_her_own_top_three_and_every_card_explains_itself(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    await _reading(deployment, profile_id, pa["token"], 138, 84)
    mei = await register_by_phone(deployment, MEI, "Mei")
    await _caregiver_key(
        deployment, pa, profile_id, MEI, ["medicines", "visits", "readings", "records", "emergency"]
    )
    await deployment.client.get(f"/profiles/{profile_id}/feed", headers=bearer(pa["token"]))
    hers = await deployment.client.get(
        f"/profiles/{profile_id}/feed/today", headers=bearer(mei["token"])
    )
    assert hers.status_code == 200, hers.text
    body = hers.json()
    assert body["audience"] == "caregiver" and 0 < len(body["items"]) <= 3
    assert all(item["why"]["plain"] for item in body["items"])
