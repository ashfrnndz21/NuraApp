"""E11-06 over HTTP, for the web: the person a red flag's ladder reached sees it still open
and says "I'm on it", which stops it for everyone after them — the web twin of the WhatsApp
reply in checkpoint 20."""

from __future__ import annotations

from app.clock import FrozenClock
from app.consent.models import ConsentPurpose
from app.consent.texts import current_version
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.family_support import MONDAY

PA, MEI, KIT = "+6591117701", "+6592227702", "+6595557703"
EVERYTHING = [
    "medicines", "visits", "readings", "records", "notes", "money", "family", "emergency",
    "ask", "send",
]


async def test_the_person_a_flag_reached_says_im_on_it_and_the_ladder_stops(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa", "en")
    mei = await register_by_phone(deployment, MEI, "Mei", "en")
    kit = await register_by_phone(deployment, KIT, "Kit", "en")
    profile_id = await own_profile(deployment, pa, display_name="Pa", language="en")
    his = bearer(pa["token"])
    agreed = await client.post(
        f"/profiles/{profile_id}/consents/whatsapp",
        json={"wording_version": current_version(ConsentPurpose.WHATSAPP), "language": "en", "captured_via": "app"},
        headers=his,
    )
    assert agreed.status_code == 201, agreed.text
    await let_in(deployment, pa, profile_id, MEI, EVERYTHING, "daughter")
    await let_in(deployment, pa, profile_id, KIT, ["medicines"], "son", holder_display_name="Kit")
    for who, role in ((mei, "chief"), (kit, "caregiver")):
        cut = await client.post(
            f"/profiles/{profile_id}/keys",
            json={"holder_person_id": who["person_id"], "role": role},
            headers=his,
        )
        assert cut.status_code == 201, cut.text
    slot = await client.post(
        f"/profiles/{profile_id}/roster",
        json={"person_id": mei["person_id"], "role": "chief", "weekdays": list(range(7)), "from_time": "00:00:00", "to_time": "23:59:00"},
        headers=his,
    )
    assert slot.status_code == 201, slot.text

    # Nothing is climbing yet.
    assert (await client.get(f"/profiles/{profile_id}/ladders", headers=bearer(mei["token"]))).json() == []

    said = await client.post(f"/profiles/{profile_id}/not-feeling-well", json={"words": "chest pain"}, headers=his)
    assert said.status_code == 201, said.text

    open_ = await client.get(
        f"/profiles/{profile_id}/ladders", params={"language": "en"}, headers=bearer(mei["token"])
    )
    assert open_.status_code == 200, open_.text
    (ladder,) = open_.json()
    assert ladder["subject"] == "flag"
    assert ladder["lines"] == [
        "Nura asked you to check on Pa on Monday 14 September at 10 in the morning.",
        "Once you tap I'm on it, Nura asks nobody else.",
    ]
    # In Malay, for a reader who reads Malay.
    malay = await client.get(
        f"/profiles/{profile_id}/ladders", params={"language": "ms"}, headers=bearer(mei["token"])
    )
    assert malay.json()[0]["lines"][0] == "Nura minta anda tengok Pa pada Isnin 14 September, pukul 10 pagi."

    # Kit's key does not open the emergency card: the ladder is not his to see.
    kits = await client.get(f"/profiles/{profile_id}/ladders", headers=bearer(kit["token"]))
    assert kits.status_code == 403 and kits.json()["refusal"] == "OutOfScope"

    stopped = await client.post(
        f"/profiles/{profile_id}/ladders/{ladder['ladder_id']}/acknowledge",
        params={"language": "en"},
        headers=bearer(mei["token"]),
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["closed_because"] == "answered"
    assert stopped.json()["acknowledged_by_person_id"] == mei["person_id"]
    assert stopped.json()["lines"] == ["Nura asks nobody else now."]
    assert (await client.get(f"/profiles/{profile_id}/ladders", headers=bearer(mei["token"]))).json() == []
