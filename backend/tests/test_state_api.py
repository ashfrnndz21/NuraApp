"""State over HTTP: the routes checkpoint 3 walks.

    POST /profiles/{id}/readings   a blood pressure typed in: one event, one fact resting on it
    GET  /profiles/{id}/state      the current snapshot as the caller's key reads it

Both sit behind the same key-context dependency as every other profile route.
"""

from __future__ import annotations

from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591110001"
DAUGHTER = "+6591110002"
HELPER = "+6591110003"


async def _key(
    deployment: Deployment, owner: dict[str, str], profile_id: str, phone: str, scopes: list[str]
) -> dict[str, object]:
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": phone, "role": "caregiver", "scopes": scopes},
        headers=bearer(owner["token"]),
    )
    assert granted.status_code == 201, granted.text
    key: dict[str, object] = granted.json()
    return key


async def test_a_reading_recomputes_state_and_the_snapshot_names_it(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="ms")
    his = bearer(pa["token"])

    first = await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)
    assert first.status_code == 200, first.text
    before = first.json()
    assert before["sequence"] == 1
    assert before["trigger"] == {"kind": "first", "fact_id": None}
    assert before["posture"] == "stable"
    assert before["stale"] is False
    assert set(before["dimensions"]) == {
        "clinical",
        "functional",
        "cognitive",
        "situational",
        "preference",
        "family",
    }
    assert before["withheld"] == {"dimensions": [], "scopes": []}

    posted = await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 138, "diastolic": 84},
        headers=his,
    )
    assert posted.status_code == 201, posted.text
    reading = posted.json()

    second = await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)
    after = second.json()
    assert after["state_id"] != before["state_id"]
    assert after["sequence"] == 2
    assert after["supersedes_id"] == before["state_id"]
    assert after["trigger"] == {"kind": "new_fact", "fact_id": reading["fact_id"]}
    entry = after["dimensions"]["clinical"]["facts"]["blood_pressure"]["reading"]
    assert entry["value"] == {"systolic": 138, "diastolic": 84}
    assert entry["unit"] == "mmHg"
    assert entry["event_id"] == reading["event_id"]
    assert entry["confidence_state"] == "confirmed_by_person"
    assert after["dimensions"]["clinical"]["fact_ids"] == [reading["fact_id"]]
    # A number State holds, not a number State reads.
    assert after["posture"] == "stable"

    # The same facts, read again: the same snapshot.
    third = await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)
    assert third.json()["state_id"] == after["state_id"]

    # A second reading supersedes it.
    again = await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 142, "diastolic": 88, "taken_at": "2026-09-03T07:00:00Z"},
        headers=his,
    )
    assert again.status_code == 201, again.text
    fourth = (await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)).json()
    assert fourth["sequence"] == 3
    assert fourth["supersedes_id"] == after["state_id"]
    assert fourth["trigger"]["fact_id"] == again.json()["fact_id"]
    assert len(fourth["dimensions"]["clinical"]["fact_ids"]) == 2


async def test_the_reading_must_be_a_reading(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    for body in ({}, {"systolic": 138}, {"systolic": 1380, "diastolic": 84}):
        refused = await deployment.client.post(
            f"/profiles/{profile_id}/readings", json=body, headers=bearer(pa["token"])
        )
        assert refused.status_code == 422, refused.text


async def test_a_key_to_the_record_reads_state_narrowed_and_one_without_is_refused(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    await deployment.client.post(
        f"/profiles/{profile_id}/readings", json={"systolic": 138, "diastolic": 84}, headers=his
    )
    await deployment.client.post(
        f"/profiles/{profile_id}/notes", json={"text": "private"}, headers=his
    )

    daughter = await register_by_phone(deployment, DAUGHTER, "Mei")
    await let_in(deployment, pa, profile_id, DAUGHTER, ["readings", "records"], "daughter")
    await _key(deployment, pa, profile_id, DAUGHTER, ["readings", "records"])
    hers = bearer(daughter["token"])

    seen = await deployment.client.get(f"/profiles/{profile_id}/state", headers=hers)
    assert seen.status_code == 200, seen.text
    state = seen.json()
    assert state["stale"] is None  # her key cannot check the record against it
    assert state["dimensions"]["clinical"]["facts"]["blood_pressure"]["reading"]["value"] == {
        "systolic": 138,
        "diastolic": 84,
    }
    assert state["dimensions"]["situational"] is None
    assert state["dimensions"]["preference"] is None
    assert state["dimensions"]["family"] is None
    assert state["withheld"] == {
        "dimensions": ["family", "preference", "situational"],
        "scopes": ["family", "notes", "visits"],
    }
    assert "private" not in seen.text

    notes = await deployment.client.get(f"/profiles/{profile_id}/notes", headers=hers)
    assert notes.status_code == 403
    assert notes.json() == {"refusal": "OutOfScope", "scope": "notes"}

    helper = await register_by_phone(deployment, HELPER, "Auntie")
    await let_in(deployment, pa, profile_id, HELPER, ["medicines"], "helper")
    await _key(deployment, pa, profile_id, HELPER, ["medicines"])
    refused = await deployment.client.get(
        f"/profiles/{profile_id}/state", headers=bearer(helper["token"])
    )
    assert refused.status_code == 403
    assert refused.json() == {"refusal": "OutOfScope", "scope": "records"}
    assert "138" not in refused.text

    trail = (await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)).json()
    reached = [
        (e["scope"], e["target"], e["refused_because"])
        for e in trail
        if e["outcome"] == "refused" and e["actor_person_id"] == helper["person_id"]
    ]
    assert reached == [("records", "state_snapshot", "OutOfScope")]


async def test_no_state_route_without_a_key_context(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    stranger = await register_by_phone(deployment, DAUGHTER, "Stranger")
    theirs = bearer(stranger["token"])
    assert (await deployment.client.get(f"/profiles/{profile_id}/state")).status_code == 401
    assert (
        await deployment.client.get(f"/profiles/{profile_id}/state", headers=theirs)
    ).status_code == 403
    assert (
        await deployment.client.post(
            f"/profiles/{profile_id}/readings",
            json={"systolic": 138, "diastolic": 84},
            headers=theirs,
        )
    ).status_code == 403
