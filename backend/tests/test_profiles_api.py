"""E00-09 acceptance: the key context on every profile route.

    A caregiver key with scope [medicines, visits] cannot read notes over HTTP (403 with
    the refusal, no row detail); the owner can list the keys cut on his profile; no profile
    route is reachable without a key context.

The routes here are the ones checkpoint 2 walks: open a profile, cut a caregiver key, read
medicines with it, be refused on notes, and read the refusal back in the audit trail.
"""

from __future__ import annotations

import logging
import uuid

import pytest
from sqlalchemy import select

from app.audit.models import AuditEntry
from app.identity.models import Person, Profile
from app.keys import context as keys_context
from app.keys.scopes import Scope
from app.regions import Region
from tests.api import CONSENT, bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591110001"
DAUGHTER = "+6591110002"
SON = "+6591110004"
PRIVATE = "I did not tell the children about the fall."
SCOPE_NAMES = tuple(scope.value for scope in Scope if scope is not Scope.PROFILE)


async def _pa_with_a_note(deployment: Deployment) -> tuple[dict[str, str], str]:
    """Pa registers, opens his graph and writes one private note."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="ms")
    written = await deployment.client.post(
        f"/profiles/{profile_id}/notes", json={"text": PRIVATE}, headers=bearer(pa["token"])
    )
    assert written.status_code == 201, written.text
    return pa, profile_id


async def _caregiver_key(
    deployment: Deployment, owner: dict[str, str], profile_id: str, holder_phone: str
) -> dict[str, object]:
    """Pa lets the number in to medicines and visits, then cuts a caregiver key on that."""
    await let_in(deployment, owner, profile_id, holder_phone, ["medicines", "visits"], "daughter", role="caregiver")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={
            "holder_phone_e164": holder_phone,
            "role": "caregiver",
            "scopes": ["medicines", "visits"],
            "window": "thirty_days",
        },
        headers=bearer(owner["token"]),
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
    key = await _caregiver_key(deployment, pa, profile_id, DAUGHTER)
    assert key["holder_person_id"] == daughter["person_id"]
    assert key["scopes"] == ["medicines", "profile", "visits"]
    hers = bearer(daughter["token"])

    # The key opens the profile, and the medicines.
    summary = await deployment.client.get(f"/profiles/{profile_id}", headers=hers)
    assert summary.status_code == 200
    assert summary.json()["role"] == "caregiver"
    assert sorted(summary.json()["scopes"]) == ["medicines", "profile", "visits"]
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
    # With the clock standing still no line is newer than another, so the order is not the point.
    assert sorted(
        (e["actor_person_id"], e["scope"], e["refused_because"], e["action"]) for e in refusals
    ) == sorted(
        [
            (daughter["person_id"], "notes", "OutOfScope", "write"),
            (daughter["person_id"], "notes", "OutOfScope", "read"),
        ]
    )
    allowed = [e for e in trail.json() if e["outcome"] == "allowed" and e["scope"] == "medicines"]
    assert [(e["actor_person_id"], e["rows"]) for e in allowed] == [(daughter["person_id"], 0)]
    assert PRIVATE not in trail.text

    # The trail is the owner's: a caregiver key does not open it.
    theirs = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=hers)
    assert theirs.status_code == 403
    assert theirs.json() == {"refusal": "NotTheirsToRead"}
    # Nor the record of who was let in.
    agreements = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=hers)
    assert agreements.status_code == 403
    assert agreements.json() == {"refusal": "OutOfScope", "scope": "family"}


async def test_the_owner_lists_the_keys_cut_on_his_profile(deployment: Deployment) -> None:
    pa, profile_id = await _pa_with_a_note(deployment)
    daughter = await register_by_phone(deployment, DAUGHTER, "Daughter")
    son = await register_by_phone(deployment, SON, "Son")
    his = bearer(pa["token"])

    hers = await _caregiver_key(deployment, pa, profile_id, DAUGHTER)
    await let_in(deployment, pa, profile_id, SON, list(SCOPE_NAMES), "son", role="chief")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_person_id": son["person_id"], "role": "chief"},
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
    # Every key names who cut it and the consent it rests on.
    assert {k["granted_by_person_id"] for k in listed.json()} == {pa["person_id"]}
    assert all(k["consent_id"] is not None for k in listed.json())

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

    before = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)
    missing = await deployment.client.delete(
        f"/profiles/{profile_id}/keys/{uuid.uuid4()}", headers=his
    )
    assert missing.status_code == 404
    assert missing.json() == {"refusal": "NoKeyToClose"}
    # The read that found nothing was rolled back with the refusal: the only new line is
    # the owner's own reading of the trail, above.
    after = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)
    assert len(after.json()) == len(before.json()) + 1


PROFILE_ROUTES = (
    ("GET", "/profiles/{id}"),
    ("GET", "/profiles/{id}/keys"),
    ("POST", "/profiles/{id}/keys"),
    ("DELETE", "/profiles/{id}/keys/00000000-0000-0000-0000-000000000000"),
    ("GET", "/profiles/{id}/audit"),
    ("GET", "/profiles/{id}/notes"),
    ("POST", "/profiles/{id}/notes"),
    ("GET", "/profiles/{id}/medicines"),
    ("POST", "/profiles/{id}/confirmations"),
    ("POST", "/profiles/{id}/claim"),
    ("GET", "/profiles/{id}/stewardship"),
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

    # A person the profile has never known leaves nothing in its trail: a line would let
    # anyone fill it by repeating a known id (`app.keys.context`). The reach is counted out
    # of band instead, for the channel to alarm on; the owner sees ex-key-holders, not
    # strangers (`test_an_ex_key_holders_reach_appears_in_the_owners_trail`).
    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", headers=bearer(pa["token"])
    )
    assert [e for e in trail.json() if e["actor_person_id"] == stranger["person_id"]] == []
    assert keys_context.unknown_reaches[uuid.UUID(stranger["person_id"])] >= 2
    assert PRIVATE not in trail.text

    # The profile that does not exist got no line anywhere: there is no graph to write under.
    async with deployment.sessions() as db:
        entries = (await db.scalars(select(AuditEntry))).all()
    assert {str(e.profile_id) for e in entries} == {profile_id}


# --- the owner's own profile -------------------------------------------------------------


async def test_the_for_me_door_records_the_agreement_it_was_given(
    deployment: Deployment,
) -> None:
    """Opening a profile is agreeing to Nura keeping it: the door takes today's words and
    records a HOLD_HEALTH_RECORD consent in the same transaction; stale words open nothing."""
    pa = await register_by_phone(deployment, PA, "Pa")
    his = bearer(pa["token"])

    unsigned = await deployment.client.post(
        "/profiles/mine", json={"display_name": "Pa"}, headers=his
    )
    assert unsigned.status_code == 422
    unknown = await deployment.client.post(
        "/profiles/mine",
        json={"consent": {**CONSENT, "captured_via": "telepathy"}},
        headers=his,
    )
    assert unknown.status_code == 422

    # Words that have moved on, or in a language Nura does not speak: refused, nothing opened.
    for stale in ({**CONSENT, "wording_version": "0"}, {**CONSENT, "language": "xx"}):
        refused = await deployment.client.post(
            "/profiles/mine", json={"consent": stale, "display_name": "Pa"}, headers=his
        )
        assert refused.status_code == 400
        assert refused.json()["refusal"] in {"NotTheCurrentWording", "WordingNotOnFile"}
    async with deployment.sessions() as db:
        assert (await db.scalars(select(Profile))).all() == []
        assert (await db.scalars(select(AuditEntry))).all() == []
    assert (await deployment.client.get("/me", headers=his)).json()["profile_id"] is None

    created = await deployment.client.post(
        "/profiles/mine",
        json={"consent": {**CONSENT, "language": "ms"}, "display_name": "Pa", "language": "ms"},
        headers=his,
    )
    assert created.status_code == 201
    profile_id = created.json()["profile_id"]

    again = await deployment.client.post("/profiles/mine", json={"consent": CONSENT}, headers=his)
    assert again.status_code == 409
    assert again.json() == {"refusal": "ProfileAlreadyOwned"}

    # The agreement is on the record, in the words he read, and the trail shows it written.
    consents = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=his)
    assert consents.status_code == 200
    [held] = consents.json()
    assert held["purpose"] == "hold_health_record"
    assert held["person_id"] == pa["person_id"]
    assert held["text_version"] == CONSENT["wording_version"]
    assert held["language"] == "ms" and held["captured_via"] == "app" and held["basis"] == "owner"
    assert held["wording_text"] and held["revoked_at"] is None

    trail = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)
    written = [(e["scope"], e["target"]) for e in trail.json() if e["action"] == "write"]
    assert ("profile", "profile") in written and ("family", "consent") in written

    assert (await deployment.client.post("/profiles/mine", json={})).status_code == 401


async def test_a_person_owns_one_profile_and_reads_its_face_through_the_trail(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    his = bearer(pa["token"])
    profile_id = await own_profile(deployment, pa, display_name="Pa", language="ms")

    me = await deployment.client.get("/me", headers=his)
    assert me.json()["profile_id"] == profile_id

    summary = await deployment.client.get(f"/profiles/{profile_id}", headers=his)
    assert summary.json()["region"] == "SG" and summary.json()["language"] == "ms"
    assert summary.json()["role"] is None
    assert "profile" in summary.json()["scopes"]
    assert len(summary.json()["scopes"]) == 11

    # Opening the graph was written down as a write to it; reading its face, as reads.
    trail = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)
    profile_lines = [(e["action"], e["outcome"]) for e in trail.json() if e["target"] == "profile"]
    assert sorted(profile_lines) == [("read", "allowed"), ("read", "allowed"), ("write", "allowed")]
    assert all(e["actor_person_id"] == pa["person_id"] for e in trail.json())


async def test_a_note_is_short_and_the_patients_own_words(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
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
        f"/profiles/{profile_id}/keys", json={"role": "caregiver"}, headers=his
    )
    assert neither.status_code == 422

    # No key without the owner's agreement to let that person in, by name.
    unagreed = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": "+6591110003", "role": "helper"},
        headers=his,
    )
    assert unagreed.status_code == 403
    assert unagreed.json() == {"refusal": "ConsentWithheld"}

    # Letting a number in that has not registered yet reserves that number an account, so
    # the invite can land on it later. Whether the number was known is not answered.
    await let_in(deployment, pa, profile_id, "+6591110003", ["medicines"], "helper", role="helper")
    invited = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": "+6591110003", "role": "helper"},
        headers=his,
    )
    assert invited.status_code == 201
    assert invited.json()["scopes"] == ["medicines", "profile"]
    async with deployment.sessions() as db:
        siti = await db.scalar(select(Person).where(Person.phone_e164 == "+6591110003"))
    assert siti is not None and str(siti.id) == invited.json()["holder_person_id"]
    later = await register_by_phone(deployment, "+6591110003", "Siti")
    assert later["person_id"] == str(siti.id)

    # A person pinned to another region is not a holder this deployment will name.
    async with deployment.sessions() as db:
        ash = Person(region=Region.MY, display_name="Ash", phone_e164="+60121110001")
        db.add(ash)
        await db.commit()
        ash_id = str(ash.id)
    elsewhere = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_person_id": ash_id, "role": "viewer"},
        headers=his,
    )
    nobody = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_person_id": str(uuid.uuid4()), "role": "viewer"},
        headers=his,
    )
    # In the same words as an id that is nobody's, so an account elsewhere cannot be probed.
    assert elsewhere.status_code == nobody.status_code == 403
    assert elsewhere.json() == nobody.json() == {"refusal": "NoSuchHolder"}

    # A caregiver may not cut a key.
    await _caregiver_key(deployment, pa, profile_id, DAUGHTER)
    hers = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": SON, "role": "viewer"},
        headers=bearer(daughter["token"]),
    )
    assert hers.status_code == 403
    assert hers.json() == {"refusal": "OutOfScope", "scope": "family"}


async def test_a_profile_pinned_elsewhere_is_out_of_region(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
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

    # And nothing about another region's profile was written into this region's trail.
    async with deployment.sessions() as db:
        entries = (await db.scalars(select(AuditEntry))).all()
    assert not any(e.refused_because == "OutOfRegion" for e in entries)


# --- the person whose key was closed ------------------------------------------------------


async def test_an_ex_key_holders_reach_appears_in_the_owners_trail(
    deployment: Deployment, caplog: pytest.LogCaptureFixture
) -> None:
    pa, profile_id = await _pa_with_a_note(deployment)
    daughter = await register_by_phone(deployment, DAUGHTER, "Daughter")
    key = await _caregiver_key(deployment, pa, profile_id, DAUGHTER)
    his = bearer(pa["token"])
    await deployment.client.delete(f"/profiles/{profile_id}/keys/{key['key_id']}", headers=his)

    with caplog.at_level(logging.INFO, logger="nura.channels.api"):
        for _ in range(2):
            refused = await deployment.client.get(
                f"/profiles/{profile_id}/medicines", headers=bearer(daughter["token"])
            )
            assert refused.status_code == 403
            assert refused.json() == {"refusal": "NoKey"}

    # The channel log names the reach by a handle and the route by its template: no ids.
    lines = [r.getMessage() for r in caplog.records if r.name == "nura.channels.api"]
    assert len(lines) == 2 and lines[0] == lines[1]
    assert "refusal=NoKey" in lines[0] and "route=GET /profiles/{profile_id}/medicines" in lines[0]
    assert profile_id not in lines[0] and daughter["person_id"] not in lines[0]

    trail = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)
    hers = [
        e
        for e in trail.json()
        if e["actor_person_id"] == daughter["person_id"] and e["outcome"] == "refused"
    ]
    assert [(e["scope"], e["refused_because"]) for e in hers] == [("profile", "NoKey")] * 2
    assert hers[0]["at"] >= hers[1]["at"]  # newest first


# --- what a refusal keeps, and what it does not -------------------------------------------


async def test_a_refused_request_keeps_its_audit_line_and_nothing_else_it_wrote(
    deployment: Deployment,
) -> None:
    """A caregiver tries to cut a key for a new number. Naming the holder reserves the number
    an account, then the grant is refused: the refusal stays in the trail and the account
    it would have left behind is gone with it."""
    pa, profile_id = await _pa_with_a_note(deployment)
    daughter = await register_by_phone(deployment, DAUGHTER, "Daughter")
    await _caregiver_key(deployment, pa, profile_id, DAUGHTER)

    refused = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": "+6591110003", "role": "helper"},
        headers=bearer(daughter["token"]),
    )
    assert refused.status_code == 403
    assert refused.json() == {"refusal": "OutOfScope", "scope": "family"}

    async with deployment.sessions() as db:
        assert await db.scalar(select(Person).where(Person.phone_e164 == "+6591110003")) is None

    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", headers=bearer(pa["token"])
    )
    hers = [e for e in trail.json() if e["outcome"] == "refused"]
    assert [
        (e["actor_person_id"], e["action"], e["scope"], e["refused_because"]) for e in hers
    ] == [(daughter["person_id"], "write", "family", "OutOfScope")]
