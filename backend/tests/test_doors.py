"""E01-01 acceptance: the three doors, proxy setup and the claim.

    Two people cannot create two profiles for one number; the claim converts the steward's
    key to a chief key and records consent — the patient's own agreement to keeping the
    record, and his agreement to let the steward in.

And around it: the steward reads everything but the private notes; the second setup is
refused in words that name nobody; the invited person lands with the key already cut; every
refusal with a graph to write under is on its trail; nothing here is reachable without a
session, and nothing on a profile without a key context (`test_profiles_api` walks the
profile routes, this file the doors).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select

from app.audit.models import AuditEntry
from app.identity.models import Person, Profile
from app.keys import context as keys_context
from tests.api import CONSENT, bearer, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591120001"
MEI = "+6591120002"
BROTHER = "+6591120003"
HELPER = "+6591120004"
STRANGER = "+6591120009"

PRIVATE = "I did not tell the children about the fall."
STEWARD_PARTS = [
    "ask",
    "emergency",
    "family",
    "medicines",
    "money",
    "readings",
    "records",
    "send",
    "visits",
]
"""Everything but the notes (and the face of the graph, which is every key's)."""


def _for_someone(phone: str, **changes: object) -> dict[str, object]:
    body: dict[str, object] = {
        "patient_phone_e164": phone,
        "display_name": "Pa",
        "language": "ms",
        "consent": CONSENT,
        "basis": "patient_asked",
        "relationship": "daughter",
    }
    body.update(changes)
    return body


async def _mei_sets_up_pa(deployment: Deployment) -> tuple[dict[str, str], str]:
    """Mei registers and sets up a graph for Pa by his number; she is its steward."""
    mei = await register_by_phone(deployment, MEI, "Mei")
    opened = await deployment.client.post(
        "/profiles/for-someone", json=_for_someone(PA), headers=bearer(mei["token"])
    )
    assert opened.status_code == 201, opened.text
    body = opened.json()
    assert body["standing"] == "steward" and body["role"] == "chief"
    assert body["display_name"] == "Pa" and body["language"] == "ms"
    assert body["scopes"] == sorted([*STEWARD_PARTS, "profile"])
    profile_id: str = body["profile_id"]
    return mei, profile_id


async def _pa_claims(
    deployment: Deployment, pa: dict[str, str], profile_id: str, language: str = "ms"
) -> dict[str, object]:
    """Pa mints his OK for what he was shown and claims the graph with it."""
    his = bearer(pa["token"])
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "claim", "language": language},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    assert minted.json()["subject"] == "claim"
    claimed = await deployment.client.post(
        f"/profiles/{profile_id}/claim",
        json={"confirmation_id": minted.json()["confirmation_id"], "language": language},
        headers=his,
    )
    assert claimed.status_code == 200, claimed.text
    body: dict[str, object] = claimed.json()
    return body


async def _trail(client: AsyncClient, token: str, profile_id: str) -> list[dict[str, object]]:
    trail = await client.get(f"/profiles/{profile_id}/audit", headers=bearer(token))
    assert trail.status_code == 200, trail.text
    entries: list[dict[str, object]] = trail.json()
    return entries


# --- the acceptance line: one graph per number -------------------------------------------


async def test_two_people_cannot_create_two_profiles_for_one_number(
    deployment: Deployment,
) -> None:
    mei, profile_id = await _mei_sets_up_pa(deployment)

    # Pa's son tries the same number. Refused by name, and the answer names nobody: not
    # Mei, not the graph, not whether Pa has claimed it.
    brother = await register_by_phone(deployment, BROTHER, "Brother")
    second = await deployment.client.post(
        "/profiles/for-someone",
        json=_for_someone(PA, display_name="Father", relationship="son"),
        headers=bearer(brother["token"]),
    )
    assert second.status_code == 409
    assert second.json() == {"refusal": "AlreadySetUp"}
    assert profile_id not in second.text and mei["person_id"] not in second.text

    # Mei trying again gets the very same words.
    again = await deployment.client.post(
        "/profiles/for-someone", json=_for_someone(PA), headers=bearer(mei["token"])
    )
    assert again.status_code == 409
    assert again.json() == second.json()

    # And after Pa claims it, the words are still the same: nothing says which case it is.
    pa = await register_by_phone(deployment, PA, "Pa")
    await _pa_claims(deployment, pa, profile_id)
    later = await deployment.client.post(
        "/profiles/for-someone",
        json=_for_someone(PA, relationship="son"),
        headers=bearer(brother["token"]),
    )
    assert later.status_code == 409
    assert later.json() == second.json()

    # One graph for the number, whatever anyone tried.
    async with deployment.sessions() as db:
        graphs = (await db.scalars(select(Profile).where(Profile.patient_phone_e164 == PA))).all()
    assert [str(graph.id) for graph in graphs] == [profile_id]

    # A stranger's try is counted, not written: a line would let anyone fill Pa's trail by
    # repeating his number (`app.keys.context.on_unknown_reach`). Mei's own retry is on it.
    trail = await _trail(deployment.client, pa["token"], profile_id)
    assert [e for e in trail if e["actor_person_id"] == brother["person_id"]] == []
    assert keys_context.unknown_reaches[uuid.UUID(brother["person_id"])] >= 2
    hers = [
        (e["action"], e["scope"], e["refused_because"])
        for e in trail
        if e["actor_person_id"] == mei["person_id"] and e["outcome"] == "refused"
    ]
    assert ("write", "profile", "AlreadySetUp") in hers


async def test_the_for_me_door_is_closed_on_a_number_someone_set_up_for(
    deployment: Deployment,
) -> None:
    """Pa registers to find a graph waiting: he claims it, he does not open a second one.
    And the other way round: a number that opened its own graph cannot be set up for."""
    _, _ = await _mei_sets_up_pa(deployment)
    pa = await register_by_phone(deployment, PA, "Pa")
    beside = await deployment.client.post(
        "/profiles/mine", json={"consent": CONSENT}, headers=bearer(pa["token"])
    )
    assert beside.status_code == 409
    assert beside.json() == {"refusal": "WaitingToBeClaimed"}

    brother = await register_by_phone(deployment, BROTHER, "Brother")
    await own_profile(deployment, brother)
    mei = await register_by_phone(deployment, MEI, "Mei")
    for_brother = await deployment.client.post(
        "/profiles/for-someone",
        json=_for_someone(BROTHER, display_name="Brother", relationship="sister"),
        headers=bearer(mei["token"]),
    )
    assert for_brother.status_code == 409
    assert for_brother.json() == {"refusal": "AlreadySetUp"}

    # Setting up for your own number is the for-me door, not this one.
    own = await deployment.client.post(
        "/profiles/for-someone", json=_for_someone(MEI), headers=bearer(mei["token"])
    )
    assert own.status_code == 400
    assert own.json() == {"refusal": "NotForYourself"}


# --- the acceptance line: the claim -------------------------------------------------------


async def test_the_claim_converts_the_steward_to_a_chief_key_and_records_consent(
    deployment: Deployment,
) -> None:
    mei, profile_id = await _mei_sets_up_pa(deployment)
    hers = bearer(mei["token"])

    # Before the claim: the stewardship is open, on the basis Mei declared, and the keeping
    # of the record rests on her agreement for him.
    held = await deployment.client.get(f"/profiles/{profile_id}/stewardship", headers=hers)
    assert held.status_code == 200, held.text
    assert held.json()["steward_person_id"] == mei["person_id"]
    assert held.json()["steward_display_name"] == "Mei"
    assert held.json()["basis"] == "patient_asked" and held.json()["closed_at"] is None
    consents = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=hers)
    assert [(c["purpose"], c["basis"], c["person_id"]) for c in consents.json()] == [
        ("hold_health_record", "patient_asked", mei["person_id"])
    ]
    old_key_id = held.json()["key_id"]

    # Pa registers with the number the graph was set up against, and finds it waiting.
    pa = await register_by_phone(deployment, PA, "Pa", language="ms")
    his = bearer(pa["token"])
    waiting = await deployment.client.get("/profiles/mine/claimable", headers=his)
    assert waiting.status_code == 200, waiting.text
    [offer] = waiting.json()
    assert offer["profile_id"] == profile_id
    assert offer["set_up_by"] == "Mei" and offer["relationship"] == "daughter"
    assert offer["parts"] == STEWARD_PARTS
    assert offer["words_language"] == "ms"  # his own language, from registration
    # The words are Malay; who Mei is to him is as Mei wrote it, like any sharing consent.
    assert offer["sharing_words"].startswith("Anda membenarkan Mei, daughter, melihat")
    assert "- ubat anda" in offer["sharing_words"]
    assert "Singapura" in offer["hold_words"]
    # Until he says yes he sees whose graph it is and nothing more.
    face = await deployment.client.get(f"/profiles/{profile_id}", headers=his)
    assert face.status_code == 200 and face.json()["standing"] == "claimant"
    assert face.json()["scopes"] == ["profile"]
    early = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=his)
    assert early.status_code == 403 and early.json()["refusal"] == "OutOfScope"

    claimed = await _pa_claims(deployment, pa, profile_id)
    assert claimed["standing"] == "owner" and claimed["role"] is None
    assert "notes" in claimed["scopes"]

    # The graph is his: /me names it, and the for-me door is now the owner's.
    me = await deployment.client.get("/me", headers=his)
    assert me.json()["profile_id"] == profile_id

    # The consents he can read: the steward's proxy agreement withdrawn by him, his own
    # agreement to keeping the record in his words, and his agreement to let Mei in.
    consents = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=his)
    rows = consents.json()
    proxy = [c for c in rows if c["basis"] == "patient_asked"]
    assert len(proxy) == 1 and proxy[0]["revoked_by_person_id"] == pa["person_id"]
    own = [c for c in rows if c["purpose"] == "hold_health_record" and c["basis"] == "owner"]
    assert len(own) == 1 and own[0]["person_id"] == pa["person_id"]
    assert own[0]["language"] == "ms" and own[0]["revoked_at"] is None
    sharing = [c for c in rows if c["purpose"] == "share_with_family"]
    assert len(sharing) == 1
    assert sharing[0]["holder_person_id"] == mei["person_id"]
    assert sharing[0]["basis"] == "owner" and sharing[0]["person_id"] == pa["person_id"]
    assert sharing[0]["scopes"] == STEWARD_PARTS and sharing[0]["language"] == "ms"
    assert sharing[0]["wording_text"] == offer["sharing_words"]

    # Mei's key: the steward's is closed, and the chief key she holds now rests on that consent.
    keys = await deployment.client.get(f"/profiles/{profile_id}/keys", headers=his)
    by_id = {k["key_id"]: k for k in keys.json()}
    assert by_id[old_key_id]["revoked_at"] is not None and by_id[old_key_id]["consent_id"] is None
    [chief] = [k for k in keys.json() if k["revoked_at"] is None]
    assert chief["holder_person_id"] == mei["person_id"] and chief["role"] == "chief"
    assert chief["consent_id"] == sharing[0]["consent_id"]
    assert chief["granted_by_person_id"] == pa["person_id"] and chief["expires_at"] is None
    assert chief["scopes"] == sorted([*STEWARD_PARTS, "profile"])
    seen = await deployment.client.get(f"/profiles/{profile_id}", headers=hers)
    assert seen.json()["standing"] == "holder" and seen.json()["role"] == "chief"

    # The stewardship is closed, naming him.
    closed = await deployment.client.get(f"/profiles/{profile_id}/stewardship", headers=his)
    assert closed.json()["closed_at"] is not None
    assert closed.json()["claimed_by_person_id"] == pa["person_id"]

    # Every step is on the trail, in his name as owner: the transfer, the consents, the key.
    trail = await _trail(deployment.client, pa["token"], profile_id)
    his_writes = {
        (e["action"], e["scope"], e["target"])
        for e in trail
        if e["actor_person_id"] == pa["person_id"] and e["outcome"] == "allowed"
    }
    assert {
        ("write", "profile", "profile"),
        ("write", "family", "consent"),
        ("share", "family", "key"),
        ("write", "family", "key"),
        ("write", "family", "stewardship"),
        ("write", "profile", "confirmation"),
    } <= his_writes


async def test_only_the_person_the_graph_was_set_up_for_claims_it(
    deployment: Deployment,
) -> None:
    """The steward cannot claim, a stranger cannot reach, a yes for other words is not this
    yes, a yes is spent once, and once claimed there is nothing to claim."""
    mei, profile_id = await _mei_sets_up_pa(deployment)
    hers = bearer(mei["token"])

    # Mei, holding a chief key, cannot mint a claim for it nor claim it.
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "claim", "language": "en"},
        headers=hers,
    )
    assert minted.status_code == 201  # a yes she said, as herself: harmless, and audited
    by_mei = await deployment.client.post(
        f"/profiles/{profile_id}/claim",
        json={"confirmation_id": minted.json()["confirmation_id"], "language": "en"},
        headers=hers,
    )
    assert by_mei.status_code == 403
    assert by_mei.json() == {"refusal": "NotTheClaimant"}

    # A stranger holds nothing.
    stranger = await register_by_phone(deployment, STRANGER, "Someone")
    theirs = await deployment.client.post(
        f"/profiles/{profile_id}/claim",
        json={"confirmation_id": str(uuid.uuid4()), "language": "en"},
        headers=bearer(stranger["token"]),
    )
    assert theirs.status_code == 403 and theirs.json() == {"refusal": "NoKey"}
    assert (
        await deployment.client.get("/profiles/mine/claimable", headers=bearer(stranger["token"]))
    ).json() == []

    pa = await register_by_phone(deployment, PA, "Pa")
    his = bearer(pa["token"])
    # A yes minted for the words in one language is not a yes to them in another.
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "claim", "language": "en"},
        headers=his,
    )
    other_words = await deployment.client.post(
        f"/profiles/{profile_id}/claim",
        json={"confirmation_id": minted.json()["confirmation_id"], "language": "ms"},
        headers=his,
    )
    assert other_words.status_code == 400
    assert other_words.json() == {"refusal": "NotWhatWasConfirmed"}
    # Words Nura does not have cannot be agreed to.
    no_words = await deployment.client.get(
        "/profiles/mine/claimable", params={"language": "ta"}, headers=his
    )
    assert no_words.status_code == 400 and no_words.json() == {"refusal": "WordingNotOnFile"}

    # The right yes, once.
    await _pa_claims(deployment, pa, profile_id, language="en")
    twice = await deployment.client.post(
        f"/profiles/{profile_id}/claim",
        json={"confirmation_id": minted.json()["confirmation_id"], "language": "en"},
        headers=his,
    )
    assert twice.status_code == 403 and twice.json() == {"refusal": "NotTheClaimant"}
    assert (await deployment.client.get("/profiles/mine/claimable", headers=his)).json() == []

    # The refusals with a graph to write under are on Pa's trail.
    trail = await _trail(deployment.client, pa["token"], profile_id)
    refused = {
        (e["actor_person_id"], e["refused_because"]) for e in trail if e["outcome"] == "refused"
    }
    assert (mei["person_id"], "NotTheClaimant") in refused
    assert (pa["person_id"], "NotWhatWasConfirmed") in refused
    assert (pa["person_id"], "NotTheClaimant") in refused
    assert not any(e["actor_person_id"] == stranger["person_id"] for e in trail)


# --- what a steward may and may not do ---------------------------------------------------


async def test_a_steward_reads_everything_but_the_private_notes(deployment: Deployment) -> None:
    mei, profile_id = await _mei_sets_up_pa(deployment)
    hers = bearer(mei["token"])

    # Not the notes: neither to read nor to write, and the refusal is on the trail.
    for method in ("GET", "POST"):
        refused = await deployment.client.request(
            method, f"/profiles/{profile_id}/notes", json={"text": "hers"}, headers=hers
        )
        assert refused.status_code == 403
        assert refused.json() == {"refusal": "OutOfScope", "scope": "notes"}

    # The rest of the graph, the trail and the consents, as a chief would while nobody owns it —
    # and the record can be written to: a reading rests on the agreement she gave for him.
    medicines = await deployment.client.get(f"/profiles/{profile_id}/medicines", headers=hers)
    assert medicines.status_code == 200 and medicines.json() == []
    reading = await deployment.client.post(
        f"/profiles/{profile_id}/readings", json={"systolic": 138, "diastolic": 84}, headers=hers
    )
    assert reading.status_code == 201, reading.text
    trail = await _trail(deployment.client, mei["token"], profile_id)
    refusals = [
        (e["action"], e["refused_because"])
        for e in trail
        if e["actor_person_id"] == mei["person_id"] and e["outcome"] == "refused"
    ]
    assert sorted(refusals) == [("read", "OutOfScope"), ("write", "OutOfScope")]

    # She cannot let anyone in on the owner's footing: that route agrees as the owner.
    helper_in = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing",
        json={
            "holder_phone_e164": HELPER,
            "scopes": ["medicines"],
            "language": "en",
            "captured_via": "app",
        },
        headers=hers,
    )
    assert helper_in.status_code == 403
    assert helper_in.json() == {"refusal": "NotTheirConsentToGive"}
    no_key = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": HELPER, "role": "helper"},
        headers=hers,
    )
    assert no_key.status_code == 403 and no_key.json() == {"refusal": "ConsentWithheld"}

    # After the claim she is his chief, on his consent, and the notes are still his alone.
    pa = await register_by_phone(deployment, PA, "Pa")
    await _pa_claims(deployment, pa, profile_id)
    written = await deployment.client.post(
        f"/profiles/{profile_id}/notes", json={"text": PRIVATE}, headers=bearer(pa["token"])
    )
    assert written.status_code == 201
    still = await deployment.client.get(f"/profiles/{profile_id}/notes", headers=hers)
    assert still.status_code == 403 and still.json()["scope"] == "notes"
    assert PRIVATE not in still.text
    medicines = await deployment.client.get(f"/profiles/{profile_id}/medicines", headers=hers)
    assert medicines.status_code == 200


async def test_a_documented_basis_keeps_the_document_and_a_spoken_one_is_not_a_door(
    deployment: Deployment,
) -> None:
    mei = await register_by_phone(deployment, MEI, "Mei")
    hers = bearer(mei["token"])

    # A lasting power of attorney without the paper is no basis; the shape refuses it.
    bare = await deployment.client.post(
        "/profiles/for-someone", json=_for_someone(PA, basis="lpa"), headers=hers
    )
    assert bare.status_code == 422
    spoken = await deployment.client.post(
        "/profiles/for-someone", json=_for_someone(PA, basis="verbal_recorded"), headers=hers
    )
    assert spoken.status_code == 400 and spoken.json() == {"refusal": "NoSuchWitness"}
    as_owner = await deployment.client.post(
        "/profiles/for-someone", json=_for_someone(PA, basis="owner"), headers=hers
    )
    assert as_owner.status_code == 403
    assert as_owner.json() == {"refusal": "NotTheirConsentToGive"}
    # Nothing was opened by any of those.
    async with deployment.sessions() as db:
        assert (await db.scalars(select(Profile))).all() == []
        assert (await db.scalars(select(AuditEntry))).all() == []

    evidence = {
        "kind": "pdf",
        "storage_key": "sg/lpa/pa.pdf",
        "content_type": "application/pdf",
        "sha256": "A" * 64,
        "captured_at": datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
    }
    opened = await deployment.client.post(
        "/profiles/for-someone",
        json=_for_someone(PA, basis="lpa", evidence=evidence),
        headers=hers,
    )
    assert opened.status_code == 201, opened.text
    profile_id = opened.json()["profile_id"]
    held = await deployment.client.get(f"/profiles/{profile_id}/stewardship", headers=hers)
    assert held.json()["basis"] == "lpa"
    consents = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=hers)
    [hold] = consents.json()
    assert hold["basis"] == "lpa" and hold["consent_id"] == held.json()["consent_id"]
    async with deployment.sessions() as db:
        from app.consent.models import Consent
        from app.memory.models import Artifact

        row = await db.get(Consent, uuid.UUID(hold["consent_id"]))
        assert row is not None and row.basis_artifact_id is not None
        paper = await db.get(Artifact, row.basis_artifact_id)
        assert paper is not None and str(paper.profile_id) == profile_id
        assert paper.sha256 == "a" * 64 and paper.storage_key == "sg/lpa/pa.pdf"


# --- the third door ------------------------------------------------------------------------


async def test_the_invited_person_lands_with_the_key_already_cut(deployment: Deployment) -> None:
    """Pa lets his daughter in by her number before she has registered. When she proves the
    number, the key is hers, and the doors say so."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="ms")
    his = bearer(pa["token"])
    agreed = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing",
        json={
            "holder_phone_e164": MEI,
            "scopes": ["medicines", "visits"],
            "relationship": "daughter",
            "language": "en",
            "captured_via": "app",
        },
        headers=his,
    )
    assert agreed.status_code == 201, agreed.text
    cut = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": ["medicines", "visits"]},
        headers=his,
    )
    assert cut.status_code == 201, cut.text

    mei = await register_by_phone(deployment, MEI, "Mei")
    assert mei["person_id"] == cut.json()["holder_person_id"]
    doors = await deployment.client.get("/doors", headers=bearer(mei["token"]))
    assert doors.status_code == 200, doors.text
    assert doors.json()["own"] is None
    assert doors.json()["claimable"] == [] and doors.json()["stewarding"] == []
    [invited] = doors.json()["invited"]
    assert invited["profile_id"] == profile_id and invited["display_name"] == "Pa"
    assert invited["role"] == "caregiver" and invited["standing"] == "holder"
    assert invited["scopes"] == ["medicines", "profile", "visits"]
    # The name she gave at registration is the name the account carries now.
    async with deployment.sessions() as db:
        person = await db.get(Person, uuid.UUID(mei["person_id"]))
        assert person is not None and person.display_name == "Mei"

    # Pa's doors: his own graph, nothing else; Mei's reading of his face is on his trail.
    doors = await deployment.client.get("/doors", headers=his)
    assert doors.json()["own"]["profile_id"] == profile_id
    assert doors.json()["own"]["standing"] == "owner"
    assert doors.json()["invited"] == []
    trail = await _trail(deployment.client, pa["token"], profile_id)
    assert any(
        e["actor_person_id"] == mei["person_id"] and e["scope"] == "profile" and e["rows"] == 1
        for e in trail
    )


async def test_the_doors_say_which_apply(deployment: Deployment) -> None:
    mei, profile_id = await _mei_sets_up_pa(deployment)
    hers = bearer(mei["token"])
    doors = await deployment.client.get("/doors", headers=hers)
    assert doors.json()["own"] is None and doors.json()["invited"] == []
    [stewarding] = doors.json()["stewarding"]
    assert stewarding["profile_id"] == profile_id and stewarding["standing"] == "steward"

    mine = await own_profile(deployment, mei)
    doors = await deployment.client.get("/doors", headers=hers)
    assert doors.json()["own"]["profile_id"] == mine

    pa = await register_by_phone(deployment, PA, "Pa")
    doors = await deployment.client.get(
        "/doors", params={"language": "en"}, headers=bearer(pa["token"])
    )
    [offer] = doors.json()["claimable"]
    assert offer["profile_id"] == profile_id and offer["words_language"] == "en"
    assert "Mei, daughter" in offer["sharing_words"]
    await _pa_claims(deployment, pa, profile_id)
    doors = await deployment.client.get("/doors", headers=bearer(pa["token"]))
    assert doors.json()["own"]["profile_id"] == profile_id
    assert doors.json()["claimable"] == []
    doors = await deployment.client.get("/doors", headers=hers)
    assert doors.json()["stewarding"] == []
    [chief] = doors.json()["invited"]
    assert chief["profile_id"] == profile_id and chief["role"] == "chief"


async def test_nothing_here_is_reachable_without_a_session(deployment: Deployment) -> None:
    for method, path in (
        ("GET", "/doors"),
        ("POST", "/profiles/for-someone"),
        ("GET", "/profiles/mine/claimable"),
    ):
        anonymous = await deployment.client.request(method, path)
        assert anonymous.status_code == 401, path
        assert anonymous.json() == {"refusal": "NoSession"}
