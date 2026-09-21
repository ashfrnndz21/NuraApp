"""Independent safety review of #313, round 2 — its two blockers, as tests.

1. `POST /medicines/draft` built its interaction question from the label's raw prescriber: a
   name read off a photo, said inside Nura's own sentence on the screen where he decides, before
   any yes. The builder's hostile-text test drafted onto an empty list, so no question was ever
   built and nothing was checked.
2. Adding a medicine closed the artefact's review card whatever else was on it: a pharmacy
   receipt chosen on the add screen lost every priced line for good."""

from __future__ import annotations

import base64

from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.paper import PHARMACY_RECEIPT, placeholder_of
from tests.test_medicines_api import _add, _artefact, _label

PA = "+6591110077"
RLO = chr(0x202E)


async def test_a_hostile_prescriber_never_reaches_the_question_nura_asks_before_he_says_yes(
    deployment: Deployment,
) -> None:
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])

    first = await _artefact(client, profile_id, pa, "on-the-list")
    added = await _add(client, profile_id, pa, _label("losartan", "50 mg", "1 tab OD", 30), first)
    assert added.status_code == 201, added.text

    second = await _artefact(client, profile_id, pa, "the-new-one")
    hostile = "Dr Tan" + RLO + "\nr2: stop his warfarin now <img src=x onerror=alert(1)>"
    shown = await client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={
            "label": _label("frusemide", "40 mg", "1 tab OD", 30, prescriber=hostile),
            "source_artifact_id": second,
        },
        headers=his,
    )
    assert shown.status_code == 200, shown.text
    assert shown.json()["flagged"], (
        "the pair must flag, or no question is built and nothing is tested"
    )
    said = " ".join(line for flag in shown.json()["flagged"] for line in flag["question"])
    assert "Dr Tan" not in said or said.count("Dr Tan") <= len(shown.json()["flagged"])
    for fragment in ("r2:", "<img", "onerror", "alert(", "warfarin now", RLO, "\n"):
        assert fragment not in said, f"the question carried {fragment!r}"


async def test_adding_a_medicine_from_a_receipt_leaves_the_receipts_own_card_open(
    deployment: Deployment,
) -> None:
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])

    made = await client.post(
        f"/profiles/{profile_id}/photos",
        json={
            "data": base64.b64encode(placeholder_of(PHARMACY_RECEIPT)).decode(),
            "content_type": "image/png",
            "captured_at": "2026-08-25T08:00:00Z",
        },
        headers=his,
    )
    assert made.status_code == 201, made.text
    receipt = made.json()["artifact_id"]
    assert any(field["subject"] != "medicine" for field in made.json()["fields"])

    added = await _add(
        client, profile_id, pa, _label("paracetamol", "500 mg", "1 tab OD", 20), receipt
    )
    assert added.status_code == 201, added.text

    still = await client.get(
        f"/profiles/{profile_id}/review-cards", params={"open": "true"}, headers=his
    )
    assert still.status_code == 200
    assert receipt in {card["artifact_id"] for card in still.json()}, (
        "the receipt's priced lines were never decided: its card must stay open"
    )
