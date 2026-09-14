"""The safety routes over HTTP: what checkpoint 14 walks.

    GET  /profiles/{id}/emergency-card        JSON
    GET  /profiles/{id}/emergency-card.html   the printable page
    POST /profiles/{id}/not-feeling-well
    POST /profiles/{id}/symptoms
    GET  /profiles/{id}/symptoms?since=

The printable page has no external asset and carries the design-system tokens at the
contrast the patient mode demands; an emergency-only key reads the card; a stranger with no
key is refused; a key narrowed past EMERGENCY is refused and the refusal is in the trail.
"""

from __future__ import annotations

import base64
import html as html_module
import re

from app.channels.printable import BODY_PX, TOKENS
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.paper import placeholder_png
from tests.voice import CHEST_PAIN, CONTENT_TYPE, DIZZY, placeholder_voice

PA = "+6591110061"
MEI = "+6592220061"
LIN = "+6594440061"
KIT = "+6593330061"
ANA = "+6595550061"


def _contrast(fore: str, back: str) -> float:
    """WCAG contrast ratio of two hex colours."""

    def luminance(hex_colour: str) -> float:
        parts = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    light, dark = sorted((luminance(fore), luminance(back)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


async def _pa_with_the_water_pill(deployment: Deployment) -> tuple[dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    photo = await deployment.client.post(
        f"/profiles/{profile_id}/photos",
        json={
            "data": base64.b64encode(placeholder_png("label-e13")).decode(),
            "content_type": "image/png",
            "captured_at": "2026-09-03T07:00:00Z",
        },
        headers=his,
    )
    assert photo.status_code == 201, photo.text
    artifact_id = photo.json()["artifact_id"]
    label = {
        "generic": "frusemide",
        "strength": "40 mg",
        "dose_text": "1 tab OD morning",
        "quantity": 30,
        "prescriber": "Dr Tan",
        "source_kind": "retail",
    }
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "medicine", "label": label, "source_artifact_id": artifact_id},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    added = await deployment.client.post(
        f"/profiles/{profile_id}/medicines",
        json={
            "label": label,
            "source_artifact_id": artifact_id,
            "confirmation_id": minted.json()["confirmation_id"],
        },
        headers=his,
    )
    assert added.status_code == 201, added.text
    return pa, profile_id


async def _key(deployment: Deployment, owner, profile_id: str, phone: str, role: str, scopes=None):
    await let_in(deployment, owner, profile_id, phone, scopes or ["emergency", "medicines", "visits", "readings", "records", "family", "notes", "money", "ask", "send"])
    body = {"holder_phone_e164": phone, "role": role}
    if scopes is not None:
        body["scopes"] = scopes
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys", json=body, headers=bearer(owner["token"])
    )
    assert granted.status_code == 201, granted.text
    return granted.json()


async def test_the_emergency_card_and_the_printable_page(deployment: Deployment) -> None:
    pa, profile_id = await _pa_with_the_water_pill(deployment)
    mei = await register_by_phone(deployment, MEI, "Mei")
    await _key(deployment, pa, profile_id, MEI, "chief")
    his = bearer(pa["token"])

    card = await deployment.client.get(f"/profiles/{profile_id}/emergency-card", headers=his)
    assert card.status_code == 200, card.text
    body = card.json()
    assert body["name"] == "Pa" and body["emergency_number"] == "995"
    assert body["medicines"][0]["generic"] == "frusemide"
    assert body["medicines"][0]["strength"] == "40 mg"
    assert body["contacts"][0]["name"] == "Mei" and body["contacts"][0]["phone_e164"] == MEI
    texts = [line["text"] for line in body["lines"]]
    assert texts[0] == "This is Pa's emergency card."
    assert "Pa takes the water pill (frusemide)." in texts and "Call Mei first." in texts
    assert body["state_id"] and body["card_id"]

    page = await deployment.client.get(f"/profiles/{profile_id}/emergency-card.html", headers=his)
    assert page.status_code == 200, page.text
    assert page.headers["content-type"].startswith("text/html")
    html = html_module.unescape(page.text)
    # Self-contained: nothing fetched, nothing run.
    assert "http://" not in html and "https://" not in html
    assert "<script" not in html and "<link" not in html and "<img" not in html
    assert "@import" not in html and "url(" not in html
    # The tokens, inline, at the patient mode's size and contrast.
    assert TOKENS["ink"] in html and TOKENS["paper"] in html and TOKENS["mist"] in html
    assert f"font-size: {BODY_PX}px" in html and BODY_PX == 20
    assert _contrast(TOKENS["ink"], TOKENS["paper"]) >= 7
    assert _contrast(TOKENS["plum"], TOKENS["paper"]) >= 7
    assert "min-height: 56px" in html
    # The data a stranger needs, beside the sentences.
    assert "40 mg" in html and MEI in html and "tel:995" in html
    assert "Pa takes the water pill (frusemide)." in html
    assert "This card is not a doctor's advice." in html
    assert "The ambulance number is 995." in html

    # Mei with her chief key, and a Malay page.
    hers = await deployment.client.get(
        f"/profiles/{profile_id}/emergency-card.html?language=ms", headers=bearer(mei["token"])
    )
    assert hers.status_code == 200
    assert 'lang="ms"' in hers.text and "Ini kad kecemasan Pa." in hers.text


async def test_who_may_read_the_card(deployment: Deployment) -> None:
    pa, profile_id = await _pa_with_the_water_pill(deployment)
    await register_by_phone(deployment, MEI, "Mei")
    await _key(deployment, pa, profile_id, MEI, "chief")
    lin = await register_by_phone(deployment, LIN, "Lin")
    await _key(deployment, pa, profile_id, LIN, "emergency")
    kit = await register_by_phone(deployment, KIT, "Kit")
    ana = await register_by_phone(deployment, ANA, "Ana")
    await _key(deployment, pa, profile_id, ANA, "caregiver", ["medicines"])
    his = bearer(pa["token"])

    # Pa computes State by reading his card; Lin's emergency-only key then reads it.
    mine = await deployment.client.get(f"/profiles/{profile_id}/emergency-card", headers=his)
    assert mine.status_code == 200
    theirs = await deployment.client.get(
        f"/profiles/{profile_id}/emergency-card", headers=bearer(lin["token"])
    )
    assert theirs.status_code == 200, theirs.text
    assert theirs.json()["state_id"] == mine.json()["state_id"]
    assert theirs.json()["lines"] == mine.json()["lines"]

    # Kit holds no key: refused, in words that name nobody.
    stranger = await deployment.client.get(
        f"/profiles/{profile_id}/emergency-card", headers=bearer(kit["token"])
    )
    assert stranger.status_code == 403 and stranger.json() == {"refusal": "NoKey"}
    page = await deployment.client.get(
        f"/profiles/{profile_id}/emergency-card.html", headers=bearer(kit["token"])
    )
    assert page.status_code == 403
    no_key = await deployment.client.get(f"/profiles/{profile_id}/emergency-card.html")
    assert no_key.status_code == 401

    # Ana's key was narrowed past EMERGENCY: refused by scope, and the refusal is on the trail.
    narrow = await deployment.client.get(
        f"/profiles/{profile_id}/emergency-card", headers=bearer(ana["token"])
    )
    assert narrow.status_code == 403
    assert narrow.json() == {"refusal": "OutOfScope", "scope": "emergency"}
    audit = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)
    assert audit.status_code == 200
    refused = [
        row
        for row in audit.json()
        if row["outcome"] == "refused" and row["target"] == "emergency_card"
    ]
    assert refused and refused[0]["refused_because"] == "OutOfScope"


async def test_the_button_and_the_symptom_log_over_http(deployment: Deployment) -> None:
    pa, profile_id = await _pa_with_the_water_pill(deployment)
    mei = await register_by_phone(deployment, MEI, "Mei")
    await _key(deployment, pa, profile_id, MEI, "chief")
    his = bearer(pa["token"])

    tired = await deployment.client.post(
        f"/profiles/{profile_id}/not-feeling-well", json={"words": "tired today"}, headers=his
    )
    assert tired.status_code == 201, tired.text
    body = tired.json()
    assert body["kind"] == "missed_dose" and body["posture"] == "watch"
    assert body["lines"][0]["text"] == "Nura has no note that you took the water pill today."
    assert body["lines"][1]["text"] == "Ask Dr Tan before you take the water pill."
    assert body["check_in_at"] is not None and body["notified_person_ids"] == [mei["person_id"]]
    assert body["symptoms"] == ["tired"] and body["red_flags"] == []

    chest = await deployment.client.post(
        f"/profiles/{profile_id}/not-feeling-well",
        json={"audio": base64.b64encode(placeholder_voice(CHEST_PAIN)).decode(), "content_type": CONTENT_TYPE},
        headers=his,
    )
    assert chest.status_code == 201, chest.text
    body = chest.json()
    assert body["kind"] == "red_flag" and body["posture"] == "act" and body["flag_id"]
    assert [line["text"] for line in body["lines"]] == [
        "Mei knows already.",
        "Call the ambulance now on 995.",
        "After that, call Mei.",
    ]
    assert body["by_voice"] and body["transcript_confidence"] == 0.94

    both = await deployment.client.post(
        f"/profiles/{profile_id}/not-feeling-well",
        json={"words": "tired", "audio": "AAAA", "content_type": CONTENT_TYPE},
        headers=his,
    )
    assert both.status_code == 422

    dizzy = await deployment.client.post(
        f"/profiles/{profile_id}/symptoms",
        json={"audio": base64.b64encode(placeholder_voice(DIZZY)).decode(), "content_type": CONTENT_TYPE},
        headers=his,
    )
    assert dizzy.status_code == 201, dizzy.text
    entry = dizzy.json()["entry"]
    assert entry["symptoms"] == ["dizzy"] and entry["severity"] == 2
    assert entry["severity_words"] == "quite bad" and entry["duration"] == "this_morning"
    assert entry["lines"][0]["text"] == "Pa felt dizzy on Thursday 3 September."

    log = await deployment.client.get(
        f"/profiles/{profile_id}/symptoms?since=2026-09-01T00:00:00Z", headers=bearer(mei["token"])
    )
    assert log.status_code == 200, log.text
    texts = [line["text"] for line in log.json()["lines"]]
    assert "Pa felt dizzy on Thursday 3 September." in texts
    assert "It was quite bad." in texts and "It started this morning." in texts
    # The button's words are in the log too, as the codes they mapped to.
    assert "Pa felt tired on Thursday 3 September." in texts
    assert "Pa felt chest pain on Thursday 3 September." in texts

    empty = await deployment.client.get(
        f"/profiles/{profile_id}/symptoms?since=2026-09-04T00:00:00Z", headers=his
    )
    assert empty.json()["entries"] == []
    assert re.fullmatch(r"Nobody wrote anything down since \w+ \d+ September\.", empty.json()["lines"][0]["text"])
