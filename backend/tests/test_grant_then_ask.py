"""E12 acceptance: add someone and grant access, and they can ask at once.

The owner's own rule, plainly: on the Family screen, the main user (the owner) can add and
grant access to a person, and the moment he does, that person can query the profile, its
context and its memory — over his own key, never anyone else's account.

This walks the whole path over HTTP, the way the app does it:

    Pa reads the words for exactly the parts and the role he is about to let Kit see
    (`POST /consents/sharing/preview`), agrees to them (`POST /consents/sharing`), and cuts
    the key that rests on that agreement (`POST /profiles/{id}/keys`) — the same two-step
    sequence the Family "Give someone a key" screen now sends (`web/src/screens/family/
    Keys.tsx`); calling the key route alone, with no sharing agreement in force, is
    `ConsentWithheld` (`test_profiles_api.py`).

    Kit registers on his own account after that — nothing about him existed before Pa named
    his number — and his very first `GET /doors` already lists Pa: no reload of anything, no
    second sign-in, no job to wait for, because a key context is resolved fresh from the
    database on every reach (`app.keys.context.resolve_key_context`).

    He asks a question over his own key and reads back an answer that cites Pa's own facts,
    in his own language, because the caller passes it explicitly, the way the Ask screen
    does (`nura.ask(..., language.value)`).

    Pa then narrows Kit's key: the very next ask no longer reaches what was taken out, and
    says so honestly, not by guessing — no caching, no delay.

    Pa closes the key: Kit's next `GET /doors` no longer lists Pa at all, and the next ask is
    refused outright, in the backend's own words, and on Pa's trail — nothing here needs a
    reload either, because closing a key is read at the door the same way granting one is.
"""

from __future__ import annotations

from app.delivery.timeline_strings import verified
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591170001"
KIT = "+6591170002"

KIT_PARTS = ["ask", "emergency", "medicines", "readings", "records", "send", "visits"]
"""The caregiver role's own preset (`ROLE_SCOPES[KeyRole.CAREGIVER]`), less `profile` — no
Family screen ever asks for that one by name (`PARTS` in `web/src/family/model.ts`); every
key opens it anyway, granted or narrowed. Caregiver already holds `ask`, so he is never
refused asking outright — a narrower part, asked about, is what is withheld instead."""

KIT_SCOPES = sorted([*KIT_PARTS, "profile"])
"""What the cut key actually opens (`KeyOut.scopes`), profile included."""


async def _trail(deployment: Deployment, token: str, profile_id: str) -> list[dict[str, object]]:
    trail = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=bearer(token))
    assert trail.status_code == 200, trail.text
    entries: list[dict[str, object]] = trail.json()
    return entries


async def _family_trail(deployment: Deployment, token: str, profile_id: str) -> str:
    """His trail as he reads it, every day's sentences joined into one string to search."""
    got = await deployment.client.get(f"/profiles/{profile_id}/trail", headers=bearer(token))
    assert got.status_code == 200, got.text
    return " ".join(
        sentence for day in got.json() for line in day["lines"] for sentence in line["sentences"]
    )


async def test_pa_adds_kit_and_kit_asks_against_pas_record_at_once(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])

    # Real papers to ask about and cite back: two blood pressure readings, the app's own way
    # of writing one (`POST /readings`), the older one superseded in nothing — recall answers
    # from the newest.
    older = await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 146, "diastolic": 90, "taken_at": "2026-09-08T08:00:00+08:00"},
        headers=his,
    )
    assert older.status_code == 201, older.text
    newest = await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 138, "diastolic": 84, "taken_at": "2026-09-13T08:00:00+08:00"},
        headers=his,
    )
    assert newest.status_code == 201, newest.text
    newest_fact_id = newest.json()["fact_id"]

    # --- 1. Pa adds Kit by phone, chooses the parts, the role and the window, and reads the
    # backend's own words for exactly that, before he agrees ------------------------------

    ask_for = {
        "holder_phone_e164": KIT,
        "holder_display_name": "Kit",
        "scopes": KIT_PARTS,
        "relationship": "son",
        "language": "en",
    }
    previewed = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing/preview", json=ask_for, headers=his
    )
    assert previewed.status_code == 200, previewed.text
    words = previewed.json()
    assert "Kit" in words["lines"][0]
    for expected in (
        "your blood pressure book and your sugar numbers",
        "your visits to the doctor",
        "your papers",
        "your medicines",
        "your questions to Nura",
    ):
        assert any(expected in line for line in words["lines"]), (expected, words["lines"])

    agreed = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing",
        json={**ask_for, "captured_via": "app", "wording_version": words["wording_version"]},
        headers=his,
    )
    assert agreed.status_code == 201, agreed.text

    cut = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={
            "holder_phone_e164": KIT,
            "role": "caregiver",
            "scopes": KIT_PARTS,
            "window": "always",
        },
        headers=his,
    )
    assert cut.status_code == 201, cut.text
    key = cut.json()
    assert key["scopes"] == KIT_SCOPES

    granted = await deployment.client.get(f"/profiles/{profile_id}/grants", headers=his)
    assert granted.status_code == 200, granted.text
    [grant] = [g for g in granted.json() if g["holder_name"] == "Kit"]
    assert "Kit" in grant["lines"][0]

    # --- 2. Kit signs in on his own account, after being granted, in Malay, and his very
    # first look at the doors already has Pa in it: no reload, no second sign-in, no job. --

    kit = await register_by_phone(deployment, KIT, "Kit", language="ms")
    his_kit = bearer(kit["token"])
    doors = await deployment.client.get("/doors", headers=his_kit)
    assert doors.status_code == 200, doors.text
    assert doors.json()["own"] is None and doors.json()["stewarding"] == []
    [invited] = doors.json()["invited"]
    assert invited["profile_id"] == profile_id
    assert invited["display_name"] == "Pa"
    assert invited["role"] == "caregiver" and invited["standing"] == "holder"
    assert set(invited["scopes"]) == set(KIT_SCOPES)

    # --- 3. Kit asks against Pa's record: the answer cites Pa's own papers, in Kit's own
    # language, exactly as the Ask screen sends it (`nura.ask(..., language.value)`). ------

    asked_en = await deployment.client.post(
        f"/profiles/{profile_id}/ask",
        # Voice: the best thing, in one line (E03-05) — the newest reading, cited.
        json={"question": "what was my blood pressure", "mode": "voice", "language": "en"},
        headers=his_kit,
    )
    assert asked_en.status_code == 200, asked_en.text
    answer = asked_en.json()
    assert answer["answered"] is True and answer["language"] == "en"
    [line] = answer["lines"]
    assert "138" in line["text"] and "84" in line["text"]
    assert any(c["kind"] == "fact" and c["id"] == newest_fact_id for c in line["cites"])

    asked_ms = await deployment.client.post(
        f"/profiles/{profile_id}/ask",
        json={"question": "tekanan darah saya", "mode": "text", "language": "ms"},
        headers=his_kit,
    )
    assert asked_ms.status_code == 200, asked_ms.text
    in_malay = asked_ms.json()
    assert in_malay["answered"] is True and in_malay["language"] == "ms"
    for said in in_malay["spoken"]:
        assert verified(said, "ms"), said
    assert any(
        c["kind"] == "fact" and c["id"] == newest_fact_id
        for each in in_malay["lines"]
        for c in each["cites"]
    )

    # --- 4 & 5 (first half). Pa narrows Kit's key to take readings out. The very next ask no
    # longer reaches it — no caching — and says so honestly rather than guessing: a question
    # outside what Kit now holds is refused in the backend's own words. ---------------------

    narrower = [scope for scope in KIT_PARTS if scope != "readings"]
    yes = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "key_change", "key_id": key["key_id"], "scopes": narrower},
        headers=his,
    )
    assert yes.status_code == 201, yes.text
    narrowed = await deployment.client.put(
        f"/profiles/{profile_id}/keys/{key['key_id']}",
        json={"scopes": narrower, "confirmation_id": yes.json()["confirmation_id"]},
        headers=his,
    )
    assert narrowed.status_code == 200, narrowed.text
    assert "readings" not in narrowed.json()["scopes"]

    after_narrowing = await deployment.client.post(
        f"/profiles/{profile_id}/ask",
        json={"question": "what was my blood pressure", "mode": "text", "language": "en"},
        headers=his_kit,
    )
    assert after_narrowing.status_code == 200, after_narrowing.text
    withheld = after_narrowing.json()
    assert withheld["answered"] is False
    assert "readings" in withheld["withheld"]
    assert withheld["honest"], "a question the record cannot answer is said honestly, not guessed"

    # The ask itself — allowed, even though it found nothing outside his parts — is still on
    # Pa's trail: he can read that Kit asked.
    trail_words = await _family_trail(deployment, pa["token"], profile_id)
    assert "Kit" in trail_words

    # --- 5 (second half). Pa closes Kit's key outright: Kit's next look at the doors no
    # longer lists Pa at all, and the next ask is refused outright, on Pa's trail. ----------

    closed = await deployment.client.delete(
        f"/profiles/{profile_id}/keys/{key['key_id']}", headers=his
    )
    assert closed.status_code == 200, closed.text

    after_close = await deployment.client.get("/doors", headers=his_kit)
    assert after_close.status_code == 200, after_close.text
    assert after_close.json()["invited"] == [] and after_close.json()["own"] is None

    refused = await deployment.client.post(
        f"/profiles/{profile_id}/ask",
        json={"question": "what was my blood pressure", "mode": "text", "language": "en"},
        headers=his_kit,
    )
    assert refused.status_code == 403, refused.text
    assert refused.json() == {"refusal": "NoKey"}

    entries = await _trail(deployment, pa["token"], profile_id)
    assert any(
        e["actor_person_id"] == kit["person_id"] and e["refused_because"] == "NoKey"
        for e in entries
    )
    trail_after_close = await _family_trail(deployment, pa["token"], profile_id)
    assert "Kit" in trail_after_close and "closed" in trail_after_close


async def test_the_family_keys_screen_cannot_cut_a_key_without_first_letting_the_person_in(
    deployment: Deployment,
) -> None:
    """The exact bug this checkpoint step exists to catch: `web/src/screens/family/Keys.tsx`
    used to call `POST /profiles/{id}/keys` straight away, for a phone number nobody had ever
    let in. That is `ConsentWithheld` (`test_profiles_api.py`), every time, for anybody new —
    which is the only case that matters, since a household's first caregiver is always new."""
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    unagreed = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": KIT, "role": "caregiver", "scopes": KIT_PARTS},
        headers=bearer(pa["token"]),
    )
    assert unagreed.status_code == 403
    assert unagreed.json() == {"refusal": "ConsentWithheld"}
