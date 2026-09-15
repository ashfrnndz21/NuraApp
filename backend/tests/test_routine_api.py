"""E10-01 over HTTP: the day set once by Mei on her yes, rendered to Pa and to her."""

from __future__ import annotations

from typing import Any

from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.trio_api_support import add_medicine, caregiver

PA = "+6591110001"
MEI = "+6591110002"
SITI = "+6591110003"
DAY: dict[str, Any] = {
    "anchors": {
        "wake": "06:30",
        "breakfast": "07:30",
        "lunch": "12:30",
        "dinner": "18:30",
        "bed": "22:00",
    },
    "reading_prompts": [["blood_pressure", "wake"]],
    "walks": ["dinner"],
    "morning_card_at": "07:00",
}


async def test_mei_sets_the_day_once_and_it_renders_to_pa_and_to_her(
    deployment: Deployment,
) -> None:
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa", "ms")
    profile_id = await own_profile(deployment, pa, display_name="Pa", language="ms")
    await add_medicine(
        deployment, pa["token"], profile_id, "amlodipine", "5 mg", "1 biji sekali sehari pagi"
    )
    mei = await register_by_phone(deployment, MEI, "Mei", "en")
    await caregiver(deployment, pa, profile_id, MEI, ["medicines", "visits", "readings"])
    route = f"/profiles/{profile_id}/routine"

    before = await client.get(route, headers=bearer(pa["token"]))
    assert before.status_code == 200, before.text
    assert before.json()["set"] is False and before.json()["persona"] == "patient"

    minted = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "routine", **DAY},
        headers=bearer(mei["token"]),
    )
    assert minted.status_code == 201, minted.text
    yes = minted.json()["confirmation_id"]
    other = {**DAY, "morning_card_at": "08:00", "confirmation_id": yes}
    wrong = await client.put(route, json=other, headers=bearer(mei["token"]))
    assert (wrong.status_code, wrong.json()) == (400, {"refusal": "NotWhatWasConfirmed"})
    done = await client.put(
        route, json={**DAY, "confirmation_id": yes}, headers=bearer(mei["token"])
    )
    assert done.status_code == 200, done.text
    assert done.json()["set"] is True and done.json()["persona"] == "caregiver"

    his = (await client.get(route, headers=bearer(pa["token"]))).json()
    assert his["lines"] == [
        "Nura hantar halaman Hari Ini anda pukul 7 pagi.",
        "Apabila anda bangun, periksa tekanan darah anda.",
        "Semasa sarapan, ambil 1 biji ubat tekanan darah anda.",
        "Semasa makan malam, pergi berjalan kaki.",
    ]
    hers = (await client.get(route, headers=bearer(mei["token"]))).json()
    rows = {row["anchor"]: row for row in hers["table"]}
    assert rows["breakfast"]["at"] == "07:30"
    assert [m["generic"] for m in rows["breakfast"]["medicines"]] == ["amlodipine"]
    assert rows["wake"]["readings"] == ["blood_pressure"] and rows["dinner"]["walk"] is True
    as_him = await client.get(
        route, params={"persona": "patient", "language": "en"}, headers=bearer(mei["token"])
    )
    assert as_him.json()["lines"][2] == "At breakfast, take 1 tablet of your blood pressure tablet."


async def test_the_helper_reads_the_day_and_cannot_set_it(deployment: Deployment) -> None:
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa", "en")
    profile_id = await own_profile(deployment, pa, display_name="Pa", language="en")
    siti = await register_by_phone(deployment, SITI, "Siti", "en")
    await caregiver(deployment, pa, profile_id, SITI, ["medicines"], role="helper")
    seen = await client.get(f"/profiles/{profile_id}/routine", headers=bearer(siti["token"]))
    assert seen.status_code == 200 and seen.json()["persona"] == "caregiver"
    refused = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "routine", **DAY, "reading_prompts": []},
        headers=bearer(siti["token"]),
    )
    assert (refused.status_code, refused.json()) == (403, {"refusal": "NotTheirsToSet"})
