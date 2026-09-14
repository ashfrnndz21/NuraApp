"""E17 over HTTP: the cloud, a tap and its answer, the red-flag path, the nudge plan, the
metrics with no health content, and one route per path.

    GET  /profiles/{id}/feelings/cloud       POST /profiles/{id}/feelings
    POST /profiles/{id}/feelings/{tap}/answer
    GET  /profiles/{id}/feelings/notes       GET  /profiles/{id}/nudges/plan
    POST /profiles/{id}/nudges/plan          POST /profiles/{id}/nudges/{nudge}/response
    GET  /profiles/{id}/nudge-metrics        GET  /profiles/{id}/me-summary
"""

from __future__ import annotations

import re
from collections import Counter

from fastapi.routing import APIRoute

from app.safety.red_flags import Feeling
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591410001"
MEI = "+6591410002"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


async def test_a_tap_its_one_answer_and_the_note_in_malay(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="ms")
    his = bearer(pa["token"])
    cloud = await deployment.client.get(f"/profiles/{profile_id}/feelings/cloud", headers=his)
    assert cloud.status_code == 200, cloud.text
    assert (
        cloud.json()["language"] == "ms" and cloud.json()["words"][-1]["label"] == "Sihat hari ini"
    )
    assert all(word["reasons"] for word in cloud.json()["words"])

    tap = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "low"}, headers=his
    )
    assert tap.status_code == 201, tap.text
    assert tap.json()["red_flag"] is False and tap.json()["question"]["words"] == "Bila ia bermula?"
    answered = await deployment.client.post(
        f"/profiles/{profile_id}/feelings/{tap.json()['tap_id']}/answer",
        json={"answer": "today"},
        headers=his,
    )
    assert answered.status_code == 201, answered.text
    note = answered.json()["note"]
    assert note["lines"] == ["Beritahu doktor anda bahawa anda rasa sedih hari ini."]
    assert note["voice"][-2:] == ["Ini bukan nasihat doktor.", "Tanya doktor anda."]
    again = await deployment.client.post(
        f"/profiles/{profile_id}/feelings/{tap.json()['tap_id']}/answer",
        json={"answer": "yesterday"},
        headers=his,
    )
    assert again.status_code == 409 and again.json() == {"refusal": "AlreadyAnswered"}
    notes = await deployment.client.get(f"/profiles/{profile_id}/feelings/notes", headers=his)
    assert [n["note_id"] for n in notes.json()] == [note["note_id"]]


async def test_a_red_word_over_http_takes_the_red_flag_path_and_makes_no_note(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    felt = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "chest_tightness"}, headers=his
    )
    assert felt.status_code == 201, felt.text
    body = felt.json()
    assert body["red_flag"] is True and body["flag_id"] and body["opens"] == "not_feeling_well"
    assert body["question"] is None and body["lines"][-1] == "Nura does not decide what is wrong."
    notes = await deployment.client.get(f"/profiles/{profile_id}/feelings/notes", headers=his)
    assert notes.json() == []
    unknown = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "heart attack"}, headers=his
    )
    assert unknown.status_code == 422


async def test_the_metrics_say_counts_and_nothing_about_his_health(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    for word in ("dizzy", "fine"):
        await deployment.client.post(
            f"/profiles/{profile_id}/feelings", json={"word": word}, headers=his
        )
    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(deployment, pa, profile_id, MEI, ["medicines", "records", "family"], "daughter")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={
            "holder_phone_e164": MEI,
            "role": "caregiver",
            "scopes": ["medicines", "records", "family"],
        },
        headers=his,
    )
    assert granted.status_code == 201, granted.text
    theirs = await deployment.client.get(
        f"/profiles/{profile_id}/nudge-metrics", headers=bearer(mei["token"])
    )
    assert theirs.status_code == 403 and theirs.json() == {"refusal": "NotOwnerOrChief"}
    mine = await deployment.client.get(f"/profiles/{profile_id}/nudge-metrics", headers=his)
    assert mine.status_code == 200, mine.text
    week = mine.json()["weeks"][0]
    assert (week["taps"], week["fine_today"], week["fine_share"]) == (2, 1, 0.5)
    text = mine.text.lower()
    assert not UUID.search(text), "no ids leave"
    assert not any(feeling.value in text for feeling in Feeling if feeling is not Feeling.FINE)
    assert "dr " not in text and "tablet" not in text


async def test_the_nudge_plan_and_its_hand_over_over_http(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    plan = await deployment.client.get(f"/profiles/{profile_id}/nudges/plan", headers=his)
    assert plan.status_code == 200, plan.text
    assert plan.json()["drafts"][0]["kind"] == "presence"
    handed = await deployment.client.post(f"/profiles/{profile_id}/nudges/plan", headers=his)
    assert handed.status_code == 201, handed.text
    nudge_id = handed.json()["nudge"]["nudge_id"]
    answered = await deployment.client.post(
        f"/profiles/{profile_id}/nudges/{nudge_id}/response", json={"kind": "accepted"}, headers=his
    )
    assert answered.status_code == 201, answered.text
    nothing = await deployment.client.post(f"/profiles/{profile_id}/nudges/plan", headers=his)
    assert nothing.status_code == 409 and nothing.json() == {"refusal": "NothingToHandOver"}


def test_no_route_is_declared_twice(deployment: Deployment) -> None:
    """Two stories adding the same route (E03's visits and a copy of them, say) must not both
    stay registered after a merge: one path, one handler."""
    app = deployment.client._transport.app  # type: ignore[attr-defined]
    declared = Counter(
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    )
    assert [pair for pair, n in declared.items() if n > 1] == []
