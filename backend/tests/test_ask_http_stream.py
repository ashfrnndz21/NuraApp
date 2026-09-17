"""`POST /profiles/{id}/ask/stream` over HTTP: the wiring `test_ask_stream.py` does not reach
(the route itself, the caregiver-voice twin on a step's label, a red flag skipping the trace
entirely). docs/design-direction.md "Conversation, waiting and thinking".
"""

from __future__ import annotations

import json

from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591180001"
MEI = "+6591180002"


def _events(text: str) -> list[dict[str, object]]:
    return [json.loads(line.removeprefix("data: ")) for line in text.split("\n\n") if line.startswith("data: ")]


async def test_his_own_key_hears_the_steps_in_order_then_the_same_answer_ask_gives(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 138, "diastolic": 84, "taken_at": "2026-09-13T08:00:00+08:00"},
        headers=his,
    )

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/ask/stream",
        json={"question": "what was my blood pressure", "mode": "text"},
        headers=his,
    )
    assert streamed.status_code == 200
    events = _events(streamed.text)
    assert [e["type"] for e in events] == ["step", "step", "step", "step", "answer"]
    assert [e["key"] for e in events[:-1]] == ["visits", "readings", "medicines", "records"]
    assert events[1] == {"type": "step", "key": "readings", "label": "Looking at your blood pressure book.", "name": "blood pressure book"}

    plain = await deployment.client.post(
        f"/profiles/{profile_id}/ask",
        json={"question": "what was my blood pressure", "mode": "text"},
        headers=his,
    )
    assert events[-1]["answer"]["lines"] == plain.json()["lines"]


async def test_a_caregivers_step_names_him_not_her(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    await let_in(deployment, pa, profile_id, MEI, ["ask", "medicines"], holder_display_name="Mei", role="caregiver")
    mei = await register_by_phone(deployment, MEI, "Mei", language="en")
    cut = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": ["ask", "medicines"]},
        headers=bearer(pa["token"]),
    )
    assert cut.status_code == 201, cut.text

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/ask/stream",
        json={"question": "what is his medicine", "mode": "text"},
        headers=bearer(mei["token"]),
    )
    events = _events(streamed.text)
    # A narrow key: only the part it opens is ever streamed, never a step for visits,
    # readings or records — not even to say they were withheld (spec: a step's existence is
    # itself information).
    assert [e["key"] for e in events if e["type"] == "step"] == ["medicines"]
    step = next(e for e in events if e["type"] == "step")
    assert "Pa's" in str(step["label"]) and "your" not in str(step["label"])
    assert events[-1]["type"] == "answer"


async def test_a_red_flag_in_the_question_streams_no_step_at_all(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/ask/stream",
        json={"question": "chest pain and I can't breathe", "mode": "text"},
        headers=bearer(pa["token"]),
    )
    events = _events(streamed.text)
    assert [e["type"] for e in events] == ["answer"]
    assert events[0]["answer"]["red_flag"] is not None
