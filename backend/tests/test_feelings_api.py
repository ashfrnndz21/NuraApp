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
import uuid
from collections import Counter

from fastapi.routing import APIRoute

from app.keys.context import resolve_key_context
from app.keys.scopes import Scope
from app.memory.models import Event
from app.regions import Region
from app.safety.red_flags import Feeling
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.feelings_support import new_medicine

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
    assert note["lines"] == ["Beritahu doktor anda bahawa anda rasa sedih pada Khamis 3 September."]
    assert note["voice"][-2:] == ["Ini bukan nasihat doktor.", "Tanya doktor anda."]
    again = await deployment.client.post(
        f"/profiles/{profile_id}/feelings/{tap.json()['tap_id']}/answer",
        json={"answer": "yesterday"},
        headers=his,
    )
    assert again.status_code == 409 and again.json() == {"refusal": "AlreadyAnswered"}
    notes = await deployment.client.get(f"/profiles/{profile_id}/feelings/notes", headers=his)
    assert [n["note_id"] for n in notes.json()["notes"]] == [note["note_id"]]
    assert notes.json()["withheld"] == 0


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
    assert notes.json() == {"notes": [], "withheld": 0}
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
    await let_in(deployment, pa, profile_id, MEI, ["medicines", "records", "family"], "daughter", role="caregiver")
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
    # Handed over twice — the web as he answers, the schedule at its time (W7): the same nudge.
    again = await deployment.client.post(f"/profiles/{profile_id}/nudges/plan", headers=his)
    assert again.status_code == 201
    assert again.json()["nudge"]["nudge_id"] == handed.json()["nudge"]["nudge_id"]


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


async def test_a_tap_is_the_records_and_a_note_on_a_medicine_is_withheld_without_the_medicines(
    deployment: Deployment,
) -> None:
    """The tap's moment is written under the record's scope (ADR 0004: its `written_scope`), so
    a key without the record reads no cloud; a note resting on a medicine line is withheld, by
    count, from a key that holds the record and not the medicines."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    async with deployment.sessions() as session:
        owner = await resolve_key_context(
            session,
            region=Region.SG,
            person_id=uuid.UUID(pa["person_id"]),
            profile_id=uuid.UUID(profile_id),
        )
        await new_medicine(session, owner)
        await session.commit()
    tap = (
        await deployment.client.post(
            f"/profiles/{profile_id}/feelings", json={"word": "dizzy"}, headers=his
        )
    ).json()
    answered = await deployment.client.post(
        f"/profiles/{profile_id}/feelings/{tap['tap_id']}/answer",
        json={"answer": "yesterday"},
        headers=his,
    )
    assert answered.json()["note"]["reasons"][0]["code"] == "new_medicine"
    async with deployment.sessions() as session:
        moment = await session.get(Event, uuid.UUID(tap["event_id"]))
        assert moment is not None and moment.written_scope is Scope.RECORDS

    async def key(phone: str, parts: list[str]) -> dict[str, str]:
        holder = await register_by_phone(deployment, phone, "Kit")
        await let_in(deployment, pa, profile_id, phone, parts, "son", role="caregiver")
        cut = await deployment.client.post(
            f"/profiles/{profile_id}/keys",
            json={"holder_phone_e164": phone, "role": "caregiver", "scopes": parts},
            headers=his,
        )
        assert cut.status_code == 201, cut.text
        return bearer(holder["token"])

    medicines_only = await key("+6591410031", ["medicines"])
    refused = await deployment.client.get(
        f"/profiles/{profile_id}/feelings/cloud", headers=medicines_only
    )
    assert refused.status_code == 403
    record_only = await key("+6591410032", ["records", "readings"])
    withheld = (
        await deployment.client.get(f"/profiles/{profile_id}/feelings/notes", headers=record_only)
    ).json()
    assert withheld == {"notes": [], "withheld": 1}
    both = await key("+6591410033", ["records", "readings", "medicines"])
    shown = (
        await deployment.client.get(f"/profiles/{profile_id}/feelings/notes", headers=both)
    ).json()
    assert [n["note_id"] for n in shown["notes"]] == [answered.json()["note"]["note_id"]]


async def test_the_day_s_nudges_are_read_back_with_what_each_person_did(
    deployment: Deployment,
) -> None:
    """W7: a push carries no words, so the app reads the day's handed-over nudge — its lines,
    its why — and what the reader has done with it; he answers at the response route."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    empty = await deployment.client.get(f"/profiles/{profile_id}/nudges", headers=his)
    assert empty.status_code == 200, empty.text
    assert empty.json()["nudges"] == [] and empty.json()["withheld"] == 0

    handed = await deployment.client.post(f"/profiles/{profile_id}/nudges/plan", headers=his)
    assert handed.status_code == 201, handed.text
    nudge = handed.json()["nudge"]
    day = await deployment.client.get(f"/profiles/{profile_id}/nudges", headers=his)
    (shown,) = day.json()["nudges"]
    assert shown["nudge_id"] == nudge["nudge_id"] and shown["lines"] == nudge["lines"]
    assert shown["why"] == nudge["why"] and shown["voice"] and shown["responses"] == []
    assert day.json()["day"] == nudge["day"]

    answered = await deployment.client.post(
        f"/profiles/{profile_id}/nudges/{nudge['nudge_id']}/response",
        json={"kind": "accepted"},
        headers=his,
    )
    assert answered.status_code == 201, answered.text
    again = await deployment.client.get(f"/profiles/{profile_id}/nudges", headers=his)
    assert again.json()["nudges"][0]["responses"] == ["accepted"]

    # Each person's own answers: Mei, his chief, has done nothing with it.
    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(
        deployment,
        pa,
        profile_id,
        MEI,
        ["emergency", "medicines", "visits", "readings", "records", "family", "notes"],
        role="chief",
    )
    key = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "chief"},
        headers=his,
    )
    assert key.status_code == 201, key.text
    hers = await deployment.client.get(
        f"/profiles/{profile_id}/nudges", headers=bearer(mei["token"])
    )
    assert hers.json()["nudges"][0]["responses"] == []

    other = await deployment.client.get(
        f"/profiles/{profile_id}/nudges?day=2026-01-05", headers=his
    )
    assert other.json()["nudges"] == []


async def test_the_answer_that_makes_a_word_red_says_so(deployment: Deployment) -> None:
    """W7: the phone shows the red offline card if a red-making answer cannot be sent, so each
    answer says whether it makes the word red — a yes to the question that tells the red variant
    apart, and nothing else."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    breathless = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "breathless"}, headers=his
    )
    assert breathless.status_code == 201, breathless.text
    question = breathless.json()["question"]
    assert question["follow_up"] == "at_rest"
    assert {one["answer"]: one["red"] for one in question["answers"]} == {"yes": True, "no": False}
    low = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "low"}, headers=his
    )
    assert [one["red"] for one in low.json()["question"]["answers"]] == [False] * 4
