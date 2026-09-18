"""`GET /profiles/{id}/feed/jobs/status`: the feed's honest "Nura is looking for today's
reads" line (docs/design-direction.md, "Conversation, waiting and thinking"), bound to a
real read of whether a self-search is due today and has not yet run
(`app.delivery.feed.search.jobs_looking_today`) — the same rows and the same `due` rule
`GET /feed` already runs its learning supply through inline (`app.delivery.feed.compose.
_learning`), never a guess or a timer of its own.
"""

from __future__ import annotations

from datetime import timedelta

from app.clock import FrozenClock
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591220001"


async def _status(deployment: Deployment, profile_id: str, token: str) -> bool:
    answer = await deployment.client.get(
        f"/profiles/{profile_id}/feed/jobs/status", headers=bearer(token)
    )
    assert answer.status_code == 200, answer.text
    looking: bool = answer.json()["looking"]
    return looking


async def test_nothing_to_look_for_on_a_bare_profile(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    assert await _status(deployment, profile_id, pa["token"]) is False


async def test_a_job_just_made_has_already_run_today_so_nothing_is_still_looking(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    made = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs",
        json={"kind": "explainer", "terms": ["warfarin"]},
        headers=bearer(pa["token"]),
    )
    assert made.status_code == 201, made.text
    assert made.json()["status"] == "done"
    assert await _status(deployment, profile_id, pa["token"]) is False


async def test_a_daily_job_not_yet_run_today_is_still_looking(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    made = await deployment.client.post(
        f"/profiles/{profile_id}/search-jobs",
        json={"kind": "safety", "terms": ["warfarin"]},
        headers=bearer(pa["token"]),
    )
    assert made.status_code == 201, made.text
    assert await _status(deployment, profile_id, pa["token"]) is False
    # A new day: the daily job ran yesterday and has not run since, so today Nura is still
    # looking for today's reads — until the next `GET /feed` runs it inline and it is done.
    clock.set(clock.now() + timedelta(days=1))
    assert await _status(deployment, profile_id, pa["token"]) is True
