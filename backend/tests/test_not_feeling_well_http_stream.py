"""`POST /profiles/{id}/not-feeling-well/stream` over HTTP: the wiring
`test_not_feeling_well_stream.py` does not reach (the route itself, the same card the plain
route gives). docs/design-direction.md "Conversation, waiting and thinking".
"""

from __future__ import annotations

import base64
import json

from tests.api import bearer, register_by_phone
from tests.conftest import Deployment
from tests.test_safety_api import MEI, _key, _pa_with_the_water_pill
from tests.voice import CHEST_PAIN, CONTENT_TYPE, placeholder_voice


def _events(text: str) -> list[dict[str, object]]:
    return [json.loads(line.removeprefix("data: ")) for line in text.split("\n\n") if line.startswith("data: ")]


async def test_a_quiet_day_streams_checking_then_the_checks_then_the_same_card(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa_with_the_water_pill(deployment)
    await register_by_phone(deployment, MEI, "Mei")
    await _key(deployment, pa, profile_id, MEI, "chief")
    his = bearer(pa["token"])

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/not-feeling-well/stream", json={"words": "tired today"}, headers=his
    )
    assert streamed.status_code == 200
    events = _events(streamed.text)
    assert [e["type"] for e in events] == ["step", "step", "step", "step", "step", "card"]
    assert [e["key"] for e in events[:-1]] == ["checking", "tablets", "medicines", "family", "ready"]
    card = events[-1]["card"]
    assert isinstance(card, dict)
    assert card["kind"] == "missed_dose" and card["posture"] == "watch"


async def test_a_red_flag_still_streams_only_after_the_family_was_already_told(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa_with_the_water_pill(deployment)
    await register_by_phone(deployment, MEI, "Mei")
    await _key(deployment, pa, profile_id, MEI, "chief")
    his = bearer(pa["token"])

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/not-feeling-well/stream",
        json={
            "audio": base64.b64encode(placeholder_voice(CHEST_PAIN)).decode(),
            "content_type": CONTENT_TYPE,
        },
        headers=his,
    )
    assert streamed.status_code == 200
    events = _events(streamed.text)
    # Never TABLETS or MEDICINES — `not_feeling_well` never made those checks for a red flag
    # (module docstring), and the trace never claims a check that did not run.
    assert [e["key"] for e in events if e["type"] == "step"] == ["checking", "family", "ready"]
    card = events[-1]["card"]
    assert isinstance(card, dict)
    assert card["kind"] == "red_flag" and card["flag_id"]
