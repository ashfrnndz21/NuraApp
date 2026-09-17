"""The Health tab, food intake and metric logging over HTTP (design-direction.md).

    Acceptance: the wire shapes for the ring, the metric rows, insights, the medication
    reminder, the food catalogue and a food log all serialise cleanly end to end.
"""

from __future__ import annotations

from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment


async def test_the_health_tab_over_http(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, "+6591310001", "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    client = deployment.client

    steps = await client.post(
        f"/profiles/{profile_id}/metrics/steps", json={"value": 1000}, headers=his
    )
    assert steps.status_code == 201, steps.text
    assert steps.json()["status"] == "logged" and steps.json()["value"] == 1000

    skipped = await client.post(
        f"/profiles/{profile_id}/metrics/water", json={"skipped": True}, headers=his
    )
    assert skipped.status_code == 201, skipped.text
    assert skipped.json()["status"] == "skipped" and skipped.json()["value"] is None

    bad = await client.post(
        f"/profiles/{profile_id}/metrics/heart_rate", json={"skipped": True}, headers=his
    )
    assert bad.status_code == 400 and bad.json()["refusal"] == "NotAWholeMetric"

    unknown = await client.post(
        f"/profiles/{profile_id}/metrics/blood_type", json={"value": 1}, headers=his
    )
    assert unknown.status_code == 404 and unknown.json()["refusal"] == "NoSuchMetric"

    overview = await client.get(f"/profiles/{profile_id}/health/overview", headers=his)
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["ring"]["kind"] == "doses" and body["ring"]["total"] == 0
    rows = {row["kind"]: row for row in body["metrics"]}
    assert set(rows) == {"steps", "heart_rate", "sleep", "water"}
    assert rows["steps"]["status"] == "logged" and rows["steps"]["value"] == 1000
    assert rows["water"]["status"] == "skipped" and rows["water"]["value"] is None
    assert rows["sleep"]["status"] == "not_logged"
    assert rows["heart_rate"]["range_known"] is False
    assert rows["heart_rate"]["range_words"]  # the honest "no usual range yet" line

    insights = await client.get(f"/profiles/{profile_id}/health/insights", headers=his)
    assert insights.status_code == 200
    kinds = {card["kind"] for card in insights.json()}
    assert "steps" in kinds  # a true card about the steps he wrote down

    reminder = await client.get(f"/profiles/{profile_id}/medication-reminder", headers=his)
    assert reminder.status_code == 200 and reminder.json() == []

    catalog = await client.get("/food-catalog", headers=his)
    assert catalog.status_code == 200 and len(catalog.json()) > 5
    catalog_id = catalog.json()[0]["id"]

    meal = await client.post(
        f"/profiles/{profile_id}/food",
        json={"meal": "breakfast", "catalog_id": catalog_id, "amount": "a bowl"},
        headers=his,
    )
    assert meal.status_code == 201, meal.text
    assert meal.json()["status"] == "logged" and meal.json()["catalog_id"] == catalog_id

    skipped_lunch = await client.post(
        f"/profiles/{profile_id}/food", json={"meal": "lunch", "skipped": True}, headers=his
    )
    assert skipped_lunch.status_code == 201
    assert skipped_lunch.json()["status"] == "skipped"

    contradiction = await client.post(
        f"/profiles/{profile_id}/food",
        json={"meal": "dinner", "skipped": True, "food": "rice"},
        headers=his,
    )
    assert contradiction.status_code == 400
    assert contradiction.json()["refusal"] == "NotAFoodEntry"

    logged = await client.get(f"/profiles/{profile_id}/food", headers=his)
    assert logged.status_code == 200
    by_meal = {row["meal"]: row["status"] for row in logged.json()}
    assert by_meal == {"breakfast": "logged", "lunch": "skipped"}


async def test_a_stranger_gets_no_key(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, "+6591310002", "Pa")
    profile_id = await own_profile(deployment, pa)
    stranger = await register_by_phone(deployment, "+6591310003", "Someone")
    refused = await deployment.client.get(
        f"/profiles/{profile_id}/health/overview", headers=bearer(stranger["token"])
    )
    assert refused.status_code == 403 and refused.json() == {"refusal": "NoKey"}
