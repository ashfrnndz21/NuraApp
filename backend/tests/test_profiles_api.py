"""E00-09 acceptance: the key context on every profile route.

    A caregiver key with scope [medicines, visits] cannot read notes over HTTP (403 with
    the refusal, no row detail); the owner can list the keys cut on his profile; no profile
    route is reachable without a key context.

The routes here are the ones checkpoint 2 walks: open a profile, cut a caregiver key, read
medicines with it, be refused on notes, and read the refusal back in the audit trail.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.identity.models import Person, Profile
from app.regions import Region
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591110001"
DAUGHTER = "+6591110002"
SON = "+6591110004"
PRIVATE = "I did not tell the children about the fall."


async def _pa_with_a_note(deployment: Deployment) -> tuple[dict[str, str], str]:
    """Pa registers, opens his graph and writes one private note."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment.client, pa["token"], language="ms")
    written = await deployment.client.post(
        f"/profiles/{profile_id}/notes", json={"text": PRIVATE}, headers=bearer(pa["token"])
    )
    assert written.status_code == 201, written.text
    return pa, profile_id


async def _caregiver_key(
    client: AsyncClient, owner_token: str, profile_id: str, holder_phone: str
) -> dict[str, object]:
    granted = await client.post(
        f"/profiles/{profile_id}/keys",
        json={
            "holder_phone_e164": holder_phone,
            "role": "caregiver",
            "scopes": ["medicines", "visits"],
            "window": "thirty_days",
            "basis": "owner_consent",
        },
        headers=bearer(owner_token),
    )
    assert granted.status_code == 201, granted.text
    key: dict[str, object] = granted.json()
    return key


# --- the acceptance line -----------------------------------------------------------------


async def test_a_caregiver_key_scoped_to_medicines_and_visits_cannot_read_notes(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa_with_a_note(deployment)
    daughter = await register_by_phone(deployment, DAUGHTER, "Daughter")
    key = await _caregiver_key(deployment.client, pa["token"], profile_id, DAUGHTER)
    assert key["holder_person_id"] == daughter["person_id"]
    assert key["scopes"] == ["medicines", "visits"]
    hers = bearer(daughter["token"])

    # The key opens the profile, and the medicines.
    summary = await deployment.client.get(f"/profiles/{profile_id}", headers=hers)
    assert summary.status_code == 200
    assert summary.json()["role"] == "caregiver"
    assert sorted(summary.json()["scopes"]) == ["medicines", "visits"]
    medicines = await deployment.client.get(f"/profiles/{profile_id}/medicines", headers=hers)
    assert medicines.status_code == 200
    assert medicines.json() == []

    # It does not open the notes: the refusal by name, and nothing of what was refused.
    refused = await deployment.client.get(f"/profiles/{profile_id}/notes", headers=hers)
    assert refused.status_code == 403
    assert refused.json() == {"refusal": "OutOfScope", "scope": "notes"}
    assert PRIVATE not in refused.text
    assert profile_id not in refused.text

    written = await deployment.client.post(
        f"/profiles/{profile_id}/notes", json={"text": "hers"}, headers=hers
    )
    assert written.status_code == 403
    assert written.json() == {"refusal": "OutOfScope", "scope": "notes"}

    # The owner reads his note, and the refusal in the trail beside it.
    his = bearer(pa["token"])
    notes = await deployment.client.get(f"/profiles/{profile_id}/notes", headers=his)
    assert [note["text"] for note in notes.json()] == [PRIVATE]

    trail = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)
    assert trail.status_code == 200
    refusals = [entry for entry in trail.json() if entry["outcome"] == "refused"]
    assert [
        (e["actor_person_id"], e["scope"], e["refused_because"], e["action"]) for e in refusals
    ] == [
        (daughter["person_id"], "notes", "OutOfScope", "write"),
        (daughter["person_id"], "notes", "OutOfScope", "read"),
    ]
    allowed = [e for e in trail.json() if e["outcome"] == "allowed" and e["scope"] == "medicines"]
    assert [(e["actor_person_id"], e["rows"]) for e in allowed] == [(daughter["person_id"], 0)]
    assert PRIVATE not in trail.text

    # The trail is the owner's: a caregiver key does not open it.
    theirs = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=hers)
    assert theirs.status_code == 403
    assert theirs.json() == {"refusal": "NotTheirsToRead"}


async def test_the_owner_lists_the_keys_cut_on_his_profile(deployment: Deployment) -> None:
    pa, profile_id = await _pa_with_a_note(deployment)
    daughter = await register_by_phone(deployment, DAUGHTER, "Daughter")
    son = await register_by_phone(deployment, SON, "Son")
    his = bearer(pa["token"])

    hers = await _caregiver_key(deployment.client, pa["token"], profile_id, DAUGHTER)
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_person_id": son["person_id"], "role": "chief", "basis": "owner_consent"},
        headers=his,
    )
    assert granted.status_code == 201
    chief = granted.json()
    assert chief["expires_at"] is None and hers["expires_at"] is not None

    listed = await deployment.client.get(f"/profiles/{profile_id}/keys", headers=his)
    assert listed.status_code == 200
    assert {(k["key_id"], k["holder_person_id"], k["role"]) for k in listed.json()} == {
        (hers["key_id"], daughter["person_id"], "caregiver"),
        (chief["key_id"], son["person_id"], "chief"),
    }
    # Every key names who cut it and rests on a basis.
    assert {k["granted_by_person_id"] for k in listed.json()} == {pa["person_id"]}
    assert {k["basis"] for k in listed.json()} == {"owner_consent"}

    # Holding a key is not the same as reading who else holds one.
    theirs = await deployment.client.get(
        f"/profiles/{profile_id}/keys", headers=bearer(daughter["token"])
    )
    assert theirs.status_code == 403
    assert theirs.json() == {"refusal": "OutOfScope", "scope": "family"}

    # The owner closes one, and it stays in the list as closed.
    revoked = await deployment.client.delete(
        f"/profiles/{profile_id}/keys/{hers['key_id']}", headers=his
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    gone = await deployment.client.get(
        f"/profiles/{profile_id}/medicines", headers=bearer(daughter["token"])
    )
    assert gone.status_code == 403
    assert gone.json() == {"refusal": "NoKey"}
    still_listed = await deployment.client.get(f"/profiles/{profile_id}/keys", headers=his)
    assert len(still_listed.json()) == 2

    missing = await deployment.client.delete(
        f"/profiles/{profile_id}/keys/{uuid.uuid4()}", headers=his
    )
    assert missing.status_code == 404
    assert missing.json() == {"refusal": "NoKeyToClose"}


PROFILE_ROUTES = (
    ("GET", "/profiles/{id}"),
    ("GET", "/profiles/{id}/keys"),
    ("POST", "/profiles/{id}/keys"),
    ("DELETE", "/profiles/{id}/keys/00000000-0000-0000-0000-000000000000"),
    ("GET", "/profiles/{id}/audit"),
    ("GET", "/profiles/{id}/notes"),
    ("POST", "/profiles/{id}/notes"),
    ("GET", "/profiles/{id}/medicines"),
)


@pytest.mark.parametrize(("method", "route"), PROFILE_ROUTES)
async def test_no_profile_route_is_reachable_without_a_key_context(
    deployment: Deployment, method: str, route: str
) -> None:
    pa, profile_id = await _pa_with_a_note(deployment)
    path = route.format(id=profile_id)

    # No token: no session, so nobody to resolve a key for.
    anonymous = await deployment.client.request(method, path)
    assert anonymous.status_code == 401
    assert anonymous.json() == {"refusal": "NoSession"}

    # A session, but no key on this profile. The body is one word.
    stranger = await register_by_phone(deployment, "+6591110099", "Someone")
    refused = await deployment.client.request(method, path, headers=bearer(stranger["token"]))
    assert refused.status_code == 403
    assert refused.json() == {"refusal": "NoKey"}
    assert PRIVATE not in refused.text

    # A profile that does not exist refuses in the same words, so none can be found by asking.
    nowhere = await deployment.client.request(
        method, route.format(id=uuid.uuid4()), headers=bearer(stranger["token"])
    )
    assert nowhere.status_code == 403
    assert nowhere.json() == {"refusal": "NoKey"}

    # And a reach with no key leaves no line in the owner's trail: there is no context to
    # write one under. It goes to the channel log instead.
    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", headers=bearer(pa["token"])
    )
    assert stranger["person_id"] not in {entry["actor_person_id"] for entry in trail.json()}


# --- the owner's own profile -------------------------------------------------------------


async def test_a_person_opens_one_profile_and_it_is_his(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    his = bearer(pa["token"])
    created = await deployment.client.post(
        "/profiles/mine", json={"display_name": "Pa", "language": "ms"}, headers=his
    )
    assert created.status_code == 201
    profile = created.json()
    assert profile["region"] == "SG" and profile["language"] == "ms"

    again = await deployment.client.post("/profiles/mine", json={}, headers=his)
    assert again.status_code == 409
    assert again.json() == {"refusal": "ProfileAlreadyOwned"}

    me = await deployment.client.get("/me", headers=his)
    assert me.json()["profile_id"] == profile["profile_id"]

    summary = await deployment.client.get(f"/profiles/{profile['profile_id']}", headers=his)
    assert summary.json()["role"] is None
    assert len(summary.json()["scopes"]) == 10

    assert (await deployment.client.post("/profiles/mine", json={})).status_code == 401


async def test_a_note_is_short_and_the_patients_own_words(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment.client, pa["token"])
    his = bearer(pa["token"])
    too_long = await deployment.client.post(
        f"/profiles/{profile_id}/notes", json={"text": "x" * 281}, headers=his
    )
    assert too_long.status_code == 422
    empty = await deployment.client.post(
        f"/profiles/{profile_id}/notes", json={"text": "   "}, headers=his
    )
    assert empty.status_code == 400
    assert empty.json() == {"refusal": "NotANote"}


async def test_a_key_needs_a_holder_and_only_the_owner_or_a_chief_cuts_one(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa_with_a_note(deployment)
    daughter = await register_by_phone(deployment, DAUGHTER, "Daughter")
    his = bearer(pa["token"])

    neither = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"role": "caregiver", "basis": "owner_consent"},
        headers=his,
    )
    assert neither.status_code == 422

    # Cutting a key for a number that has not registered yet reserves that number an account,
    # so the invite can land on it later. Whether the number was known is not answered.
    invited = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": "+6591110003", "role": "helper", "basis": "owner_consent"},
        headers=his,
    )
    assert invited.status_code == 201
    async with deployment.sessions() as db:
        siti = await db.scalar(select(Person).where(Person.phone_e164 == "+6591110003"))
    assert siti is not None and str(siti.id) == invited.json()["holder_person_id"]
    later = await register_by_phone(deployment, "+6591110003", "Siti")
    assert later["person_id"] == str(siti.id)

    # A caregiver may not cut a key.
    await _caregiver_key(deployment.client, pa["token"], profile_id, DAUGHTER)
    hers = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": SON, "role": "viewer", "basis": "owner_consent"},
        headers=bearer(daughter["token"]),
    )
    assert hers.status_code == 403
    assert hers.json() == {"refusal": "OutOfScope", "scope": "family"}


async def test_a_profile_pinned_elsewhere_is_out_of_region(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment.client, pa["token"])
    async with deployment.sessions() as db:
        profile = await db.get(Profile, uuid.UUID(profile_id))
        assert profile is not None
        profile.region = Region.MY
        await db.commit()
    refused = await deployment.client.get(
        f"/profiles/{profile_id}/notes", headers=bearer(pa["token"])
    )
    assert refused.status_code == 403
    assert refused.json() == {"refusal": "OutOfRegion"}
