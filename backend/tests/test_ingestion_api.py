"""Capture over HTTP: the routes checkpoint 5 walks.

    POST /profiles/{id}/photos                         a photo in, a review card out
    GET  /profiles/{id}/review-cards[/{card_id}]       the cards, under the record's scope
    POST /profiles/{id}/confirmations                  subject review_card: the yes
    POST /profiles/{id}/review-cards/{card_id}/confirm the facts, with provenance
    GET  /profiles/{id}/facts?subject=                 read them back

Every route sits behind the same key-context dependency as every other profile route.
"""

from __future__ import annotations

import base64
from typing import Any

from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.paper import LIPID_PANEL, WARFARIN_LABEL, placeholder_png

PA = "+6591110001"
MEI = "+6591110002"


def _photo(label: str) -> dict[str, str]:
    return {
        "data": base64.b64encode(placeholder_png(label)).decode(),
        "content_type": "image/png",
        "captured_at": "2026-09-03T08:00:00Z",
    }


def _decisions(card: dict[str, Any], **corrections: Any) -> list[dict[str, Any]]:
    decided = []
    for field in card["fields"]:
        if field["attribute"] in corrections:
            decided.append(
                {
                    "field_id": field["field_id"],
                    "decision": "corrected",
                    "corrected_value": corrections[field["attribute"]],
                }
            )
        else:
            decided.append({"field_id": field["field_id"], "decision": "confirmed"})
    return decided


async def _key(
    deployment: Deployment, owner: dict[str, str], profile_id: str, phone: str, scopes: list[str]
) -> None:
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": phone, "role": "caregiver", "scopes": scopes},
        headers=bearer(owner["token"]),
    )
    assert granted.status_code == 201, granted.text


async def test_a_photo_in_a_review_card_out_and_facts_on_the_yes(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="ms")
    his = bearer(pa["token"])

    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=_photo(LIPID_PANEL), headers=his
    )
    assert posted.status_code == 201, posted.text
    card = posted.json()
    assert card["document_kind"] == "lab_report"
    assert card["document_date"] == "2023-09-07"
    assert card["high_risk_class"] is None
    assert card["confirmed_at"] is None
    assert card["artifact_id"]
    fields = {f["attribute"]: f for f in card["fields"]}
    assert len(fields) == 7
    assert fields["ldl"]["value"] == 152 and fields["ldl"]["unit"] == "mg/dL"
    assert fields["ldl"]["needs_confirm"] is True and fields["ldl"]["confidence"] == 0.71
    assert fields["hdl"]["needs_confirm"] is False
    assert all(f["state"] == "proposed" and f["fact_id"] is None for f in fields.values())
    # The bytes went to the region's store, not into any answer.
    assert "placeholder" not in posted.text
    assert deployment.objects.path_of(f"photos/{profile_id}/" + _digest(LIPID_PANEL)).is_file()

    listed = await deployment.client.get(f"/profiles/{profile_id}/review-cards", headers=his)
    assert listed.status_code == 200
    assert [c["card_id"] for c in listed.json()] == [card["card_id"]]
    one = await deployment.client.get(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}", headers=his
    )
    assert one.status_code == 200 and one.json() == card

    # Nothing is a fact yet.
    none = await deployment.client.get(
        f"/profiles/{profile_id}/facts", params={"subject": "lipid_panel"}, headers=his
    )
    assert none.status_code == 200 and none.json() == []

    decisions = _decisions(card, triglycerides=54)
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "review_card", "card_id": card["card_id"], "decisions": decisions},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    assert minted.json()["subject"] == "review_card"

    confirmed = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        json={"decisions": decisions, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    assert result["card"]["confirmed_by_person_id"] == pa["person_id"]
    assert result["card"]["confirmed_at"] is not None
    states = {f["attribute"]: f["state"] for f in result["card"]["fields"]}
    assert states["triglycerides"] == "corrected"
    assert set(states.values()) == {"confirmed", "corrected"}
    assert len(result["facts"]) == 7
    by_attribute = {f["attribute"]: f for f in result["facts"]}
    assert by_attribute["triglycerides"]["value"] == 54
    for fact in result["facts"]:
        assert fact["subject"] == "lipid_panel"
        assert fact["artifact_id"] == card["artifact_id"]
        assert fact["confidence_state"] == "confirmed_by_person"
        assert fact["confirmed_by_person_id"] == pa["person_id"]
        assert fact["valid_from"].startswith("2023-09-06T16:00:00")

    read = await deployment.client.get(
        f"/profiles/{profile_id}/facts", params={"subject": "lipid_panel"}, headers=his
    )
    assert {f["fact_id"] for f in read.json()} == {f["fact_id"] for f in result["facts"]}

    state = await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)
    snapshot = state.json()
    assert snapshot["trigger"]["kind"] == "new_fact"
    assert snapshot["trigger"]["fact_id"] in {f["fact_id"] for f in result["facts"]}
    assert snapshot["dimensions"]["clinical"]["facts"]["lipid_panel"]["ldl"]["value"] == 152

    # Once. And the yes is spent.
    again = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        json={"decisions": decisions, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert again.status_code == 409 and again.json() == {"refusal": "AlreadyConfirmed"}


def _digest(label: str) -> str:
    import hashlib

    return hashlib.sha256(placeholder_png(label)).hexdigest()


async def test_the_yes_is_for_the_decisions_as_shown(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    card = (
        await deployment.client.post(
            f"/profiles/{profile_id}/photos", json=_photo(LIPID_PANEL), headers=his
        )
    ).json()
    shown = _decisions(card, triglycerides=54)
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "review_card", "card_id": card["card_id"], "decisions": shown},
        headers=his,
    )
    other = _decisions(card, triglycerides=45)
    refused = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        json={"decisions": other, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert refused.status_code == 400 and refused.json() == {"refusal": "NotWhatWasConfirmed"}
    still_open = await deployment.client.get(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}", headers=his
    )
    assert still_open.json()["confirmed_at"] is None
    facts = await deployment.client.get(f"/profiles/{profile_id}/facts", headers=his)
    assert facts.json() == []
    trail = (await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)).json()
    assert any(e["refused_because"] == "NotWhatWasConfirmed" for e in trail)


async def test_a_label_card_shows_the_high_risk_class_and_its_facts_sit_under_medicines(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    card = (
        await deployment.client.post(
            f"/profiles/{profile_id}/photos", json=_photo(WARFARIN_LABEL), headers=his
        )
    ).json()
    assert card["document_kind"] == "medicine_label"
    assert card["high_risk_class"] == "anticoagulant"
    decisions = _decisions(card)
    decisions[-1] = {"field_id": decisions[-1]["field_id"], "decision": "rejected"}
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "review_card", "card_id": card["card_id"], "decisions": decisions},
        headers=his,
    )
    confirmed = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        json={"decisions": decisions, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert confirmed.status_code == 200, confirmed.text
    facts = confirmed.json()["facts"]
    assert {f["attribute"] for f in facts} == {
        "name",
        "strength",
        "dose",
        "quantity",
        "dispensed_at",
    }
    dose = next(f for f in facts if f["attribute"] == "dose")
    assert dose["value"]["drug"] == "Warfarin" and dose["artifact_id"] == card["artifact_id"]
    # The label's facts read back under subject "medicine" (the medicines scope). The E04 list
    # at GET /medicines holds reconciled lines, which a card does not write yet.
    medicines = await deployment.client.get(
        f"/profiles/{profile_id}/facts", params={"subject": "medicine"}, headers=his
    )
    assert {m["attribute"] for m in medicines.json()} == {f["attribute"] for f in facts}
    # Under the medicines scope: Mei with a key to the record alone is refused them.
    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(deployment, pa, profile_id, MEI, ["records"])
    await _key(deployment, pa, profile_id, MEI, ["records"])
    hers = bearer(mei["token"])
    cards = await deployment.client.get(f"/profiles/{profile_id}/review-cards", headers=hers)
    assert cards.status_code == 200 and len(cards.json()) == 1
    refused = await deployment.client.get(
        f"/profiles/{profile_id}/facts", params={"subject": "medicine"}, headers=hers
    )
    assert refused.status_code == 403
    assert refused.json() == {"refusal": "OutOfScope", "scope": "medicines"}


async def test_a_key_without_the_record_sees_no_card(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    card = (
        await deployment.client.post(
            f"/profiles/{profile_id}/photos", json=_photo(LIPID_PANEL), headers=his
        )
    ).json()
    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(deployment, pa, profile_id, MEI, ["readings", "records"])
    await _key(deployment, pa, profile_id, MEI, ["readings"])
    hers = bearer(mei["token"])
    for path in ("/review-cards", f"/review-cards/{card['card_id']}"):
        refused = await deployment.client.get(f"/profiles/{profile_id}{path}", headers=hers)
        assert refused.status_code == 403, refused.text
        assert refused.json() == {"refusal": "OutOfScope", "scope": "records"}
        assert "230" not in refused.text
    upload = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=_photo(WARFARIN_LABEL), headers=hers
    )
    assert upload.status_code == 403 and upload.json()["scope"] == "records"
    await _key(deployment, pa, profile_id, MEI, ["readings", "records"])
    seen = await deployment.client.get(f"/profiles/{profile_id}/review-cards", headers=hers)
    assert seen.status_code == 200 and [c["card_id"] for c in seen.json()] == [card["card_id"]]
    trail = (await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)).json()
    assert any(
        e["outcome"] == "refused"
        and e["actor_person_id"] == mei["person_id"]
        and e["target"] == "review_card"
        for e in trail
    )


async def test_the_photo_must_be_a_photo(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    not_base64 = await deployment.client.post(
        f"/profiles/{profile_id}/photos",
        json={**_photo(LIPID_PANEL), "data": "not base64!"},
        headers=his,
    )
    assert not_base64.status_code == 422
    pdf = await deployment.client.post(
        f"/profiles/{profile_id}/photos",
        json={**_photo(LIPID_PANEL), "content_type": "application/pdf"},
        headers=his,
    )
    assert pdf.status_code == 400 and pdf.json() == {"refusal": "NotAPhoto"}
    missing = await deployment.client.get(
        f"/profiles/{profile_id}/review-cards/00000000-0000-0000-0000-000000000000", headers=his
    )
    assert missing.status_code == 404 and missing.json() == {"refusal": "NoSuchReviewCard"}
    unreadable = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=_photo("a-blurry-page"), headers=his
    )
    assert unreadable.status_code == 201
    assert unreadable.json()["document_kind"] == "unknown"
    assert unreadable.json()["fields"] == []
