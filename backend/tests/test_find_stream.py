"""The feed's web and video search, streamed (docs/design-direction.md "Conversation, waiting
and thinking"): `POST /profiles/{id}/find/stream` says the allowlisted search is running
before it answers with the same results `POST /profiles/{id}/find` gives — one real step,
never an invented one, never a delay to make it look slower. Providers streams no step: a
directory read is over before there is anything to say is in progress.
"""

from __future__ import annotations

import json

from tests.api import bearer
from tests.conftest import Deployment
from tests.test_feed_formats import _pa


def _events(text: str) -> list[dict[str, object]]:
    return [json.loads(line.removeprefix("data: ")) for line in text.split("\n\n") if line.startswith("data: ")]


async def test_web_search_streams_one_step_then_the_same_results_find_gives(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/find/stream",
        json={"q": "blood pressure", "where": "web", "language": "en"},
        headers=bearer(pa["token"]),
    )
    assert streamed.status_code == 200
    events = _events(streamed.text)
    assert [e["type"] for e in events] == ["step", "results"]
    assert events[0]["key"] == "searching"
    assert events[0]["label"] == "Looking online."

    plain = await deployment.client.post(
        f"/profiles/{profile_id}/find",
        json={"q": "blood pressure", "where": "web", "language": "en"},
        headers=bearer(pa["token"]),
    )
    assert [r["title"] for r in events[1]["results"]] == [r["title"] for r in plain.json()["results"]]


async def test_videos_search_names_the_videos_step(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/find/stream",
        json={"q": "blood pressure", "where": "videos", "language": "en"},
        headers=bearer(pa["token"]),
    )
    events = _events(streamed.text)
    assert events[0] == {"type": "step", "key": "searching", "label": "Looking for videos."}


async def test_an_off_allowlist_filter_refuses_mid_stream_as_a_plain_event(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/find/stream",
        json={"q": "x", "where": "tiktok"},
        headers=bearer(pa["token"]),
    )
    assert streamed.status_code == 200  # the SSE headers are already on the wire
    events = _events(streamed.text)
    assert events == [{"type": "refusal", "status": 400, "refusal": "NotAFilter"}]
