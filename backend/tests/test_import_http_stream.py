"""`POST /profiles/{id}/photos/stream` and `/imports/stream` over HTTP: the wiring
`test_import_stream.py` does not reach (the route itself, the caregiver-voice twin on a
step's label). docs/design-direction.md "Conversation, waiting and thinking".
"""

from __future__ import annotations

import base64
import json

from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.paper import LAB_REPORT_VITALS, placeholder_png

PA = "+6591190001"
MEI = "+6591190002"


def _events(text: str) -> list[dict[str, object]]:
    return [json.loads(line.removeprefix("data: ")) for line in text.split("\n\n") if line.startswith("data: ")]


async def test_his_own_key_hears_the_steps_then_the_same_card_the_plain_route_gives(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/photos/stream",
        json={
            "data": base64.b64encode(placeholder_png(LAB_REPORT_VITALS)).decode(),
            "content_type": "image/png",
            "captured_at": "2026-09-10T08:00:00Z",
        },
        headers=his,
    )
    assert streamed.status_code == 200
    events = _events(streamed.text)
    assert [e["type"] for e in events] == ["step", "step", "step", "step", "step", "card"]
    assert [e["key"] for e in events[:-1]] == ["stored", "reading", "found", "red_flag_checked", "ready"]
    found = events[2]
    assert "blood test" in str(found["label"])
    assert isinstance(found["label"], str) and found["label"].startswith("Nura found")

    plain = await deployment.client.post(
        f"/profiles/{profile_id}/photos",
        json={
            "data": base64.b64encode(placeholder_png(LAB_REPORT_VITALS)).decode(),
            "content_type": "image/png",
            "captured_at": "2026-09-10T08:00:00Z",
        },
        headers=his,
    )
    assert plain.status_code == 201
    card_event = events[-1]
    assert isinstance(card_event["card"], dict)
    assert card_event["card"]["document_kind"] == plain.json()["document_kind"]


async def test_a_caregivers_step_names_him_not_her(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    await let_in(deployment, pa, profile_id, MEI, ["records"], holder_display_name="Mei", role="caregiver")
    mei = await register_by_phone(deployment, MEI, "Mei", language="en")
    cut = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": ["records"]},
        headers=bearer(pa["token"]),
    )
    assert cut.status_code == 201, cut.text

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/photos/stream",
        json={
            "data": base64.b64encode(placeholder_png(LAB_REPORT_VITALS)).decode(),
            "content_type": "image/png",
            "captured_at": "2026-09-10T08:00:00Z",
        },
        headers=bearer(mei["token"]),
    )
    assert streamed.status_code == 200
    events = _events(streamed.text)
    stored = next(e for e in events if e["type"] == "step" and e["key"] == "stored")
    assert "Pa's" in str(stored["label"]) and "your" not in str(stored["label"])
