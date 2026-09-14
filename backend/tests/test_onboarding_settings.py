"""E01-03: the patient profile — conditions, language, functional and cognitive settings.

Acceptance: settings drive density mode and voice language immediately.

The word cloud is a fixed graph, named in his three languages, every name his words. A save
of the settings screen is the owner's or his chief's, supersedes the last save, writes as
facts only what changed — his yes on each — so State folds them into the cognitive,
functional and preference dimensions at once, and makes the language the profile's own, so
the next card the feed makes speaks it, voice-first. Every key reads how to talk to him; a
key to the record also reads his conditions and his doctor; only-me narrows that too.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from app.clock import FrozenClock
from app.onboarding import strings
from app.onboarding.conditions import graph
from app.onboarding.models import ProfileSettings
from app.onboarding.strings import LANGUAGES
from app.safety.plain_words import check_files, verify
from tests.api import let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.onboarding_support import (
    KIT,
    PA,
    SETTINGS,
    SITI,
    call,
    refused,
    stewarded,
)

IN_GRAPH_ORDER = [
    "high_blood_pressure",
    "cholesterol",
    "diabetes",
    "hospital_last_year",
    "blood_thinner",
]


async def test_the_word_cloud_is_public_and_named_in_his_language(deployment: Deployment) -> None:
    answer = await deployment.client.get("/onboarding/conditions", params={"language": "ms"})
    assert answer.status_code == 200, answer.text
    cloud = answer.json()
    assert cloud["language"] == "ms" and cloud["version"] == 1 and len(cloud["top"]) == 20
    by_code = {one["code"]: one for one in cloud["conditions"]}
    assert by_code["high_blood_pressure"]["name"] == "Darah tinggi"
    assert by_code["high_blood_pressure"]["weight"] == 3 and by_code["high_blood_pressure"]["top"]
    assert "weak_heart" in by_code["heart"]["related"]
    assert all(code in by_code for one in cloud["conditions"] for code in one["related"])
    assert set(cloud["top"]) == {code for code, one in by_code.items() if one["top"]}
    other = await deployment.client.get("/onboarding/conditions", params={"language": "ta"})
    assert other.json()["language"] == "en"


def test_every_condition_name_is_his_words() -> None:
    for condition in graph().conditions.values():
        for language in LANGUAGES:
            name = condition.name(language)
            failing = [f for f in verify(name, language, "phrase") if f.severity == "fail"]
            assert not failing, (condition.code, language, [str(f) for f in failing])


def test_every_onboarding_string_passes_plain_words() -> None:
    report = check_files([Path(strings.__file__)])
    assert report.strings > 250
    assert report.failures == [], [str(f) for f in report.failures]


async def test_settings_drive_density_and_voice_language_immediately(
    deployment: Deployment,
) -> None:
    """The acceptance line: the save lands in State, the profile and the next card at once."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = pa["token"]

    saved = await call(
        deployment, "PUT", f"/profiles/{profile_id}/settings", his, 200, json=SETTINGS
    )
    assert saved["settings_id"] and saved["set_by_person_id"] == pa["person_id"]
    assert saved["language"] == "ms" and saved["density"] == "simple"
    assert saved["voice_on"] is True and saved["large_text"] is True
    assert saved["conditions"] == IN_GRAPH_ORDER and saved["withheld"] == []
    assert (saved["doctor_name"], saved["breakfast_time"]) == ("Dr Tan", "07:30")

    profile = await call(deployment, "GET", f"/profiles/{profile_id}", his, 200)
    assert profile["language"] == "ms"

    state = await call(deployment, "GET", f"/profiles/{profile_id}/state", his, 200)
    cognitive = state["dimensions"]["cognitive"]
    assert cognitive["reading_language"] == "ms" and cognitive["spoken_language"] == "ms"
    assert cognitive["facts"]["format"]["density"]["value"] == "simple"
    assert cognitive["facts"]["format"]["preferred"]["value"] == "voice"
    assert cognitive["facts"]["memory_support"]["read_back"]["value"] is False
    functional = state["dimensions"]["functional"]["facts"]
    assert functional["vision"]["large_text"]["value"] is True
    assert functional["dexterity"]["big_targets"]["value"] is False
    preference = state["dimensions"]["preference"]["facts"]
    assert preference["nudges"]["breakfast_time"]["value"] == "07:30"
    assert preference["nudges"]["preferred_name"]["value"] == "Pa"
    clinical = state["dimensions"]["clinical"]
    assert clinical["facts"]["condition"]["diabetes"]["value"] is True
    assert clinical["facts"]["doctor"]["name"]["value"] == "Dr Tan"
    assert clinical["conditions"] == {} and state["posture"] == "stable"
    for entry in (cognitive["facts"]["format"]["preferred"], functional["vision"]["large_text"]):
        assert entry["confidence_state"] == "confirmed_by_person" and entry["event_id"]

    # The next card the feed makes is in Malay, and voice-first.
    await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/readings",
        his,
        201,
        json={"systolic": 138, "diastolic": 84},
    )
    feed = await call(deployment, "GET", f"/profiles/{profile_id}/feed", his, 200)
    mine = [item for item in feed["items"] if item["type"] in ("now", "reading")]
    assert mine and all(item["format"] == "voice_first" for item in mine)
    assert all(item["language"] == "ms" for item in mine)


async def test_a_save_supersedes_the_last_and_writes_only_what_changed(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = pa["token"]
    first = await call(
        deployment, "PUT", f"/profiles/{profile_id}/settings", his, 200, json=SETTINGS
    )
    before = await _facts(deployment, profile_id, his)
    second = await call(
        deployment,
        "PUT",
        f"/profiles/{profile_id}/settings",
        his,
        200,
        json={
            **SETTINGS,
            "density": "detailed",
            "conditions": [c for c in SETTINGS["conditions"] if c != "diabetes"],
        },
    )
    assert second["settings_id"] != first["settings_id"]
    assert "diabetes" not in second["conditions"] and second["density"] == "detailed"
    after = await _facts(deployment, profile_id, his)
    assert after[("condition", "diabetes")]["value"] is False
    assert after[("format", "density")]["value"] == "detailed"
    changed = {key for key in after if after[key]["fact_id"] != before.get(key, {}).get("fact_id")}
    assert changed == {("condition", "diabetes"), ("format", "density")}

    async with deployment.sessions() as session:
        old = await session.get(ProfileSettings, uuid.UUID(first["settings_id"]))
        new = await session.get(ProfileSettings, uuid.UUID(second["settings_id"]))
        assert old is not None and new is not None
        assert old.superseded_at is not None and new.superseded_at is None
        assert new.supersedes_id == old.id


async def test_voice_off_takes_back_only_a_voice_on_he_gave(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = pa["token"]
    path = f"/profiles/{profile_id}/settings"
    await call(deployment, "PUT", path, his, 200, json={"language": "en"})
    assert ("format", "preferred") not in await _facts(deployment, profile_id, his)
    await call(deployment, "PUT", path, his, 200, json={"language": "en", "voice_on": True})
    assert (await _facts(deployment, profile_id, his))[("format", "preferred")]["value"] == "voice"
    await call(deployment, "PUT", path, his, 200, json={"language": "en", "voice_on": False})
    off = (await _facts(deployment, profile_id, his))[("format", "preferred")]
    assert off["value"] == "text" and off["confidence_state"] == "confirmed_by_person"


async def test_his_word_on_text_stands_against_two_unopened_cards(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """The feed's own switch to voice (E21, spec §9) does not overturn a choice he made."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = pa["token"]
    path = f"/profiles/{profile_id}/settings"
    await call(deployment, "PUT", path, his, 200, json={"language": "en", "voice_on": True})
    await call(deployment, "PUT", path, his, 200, json={"language": "en", "voice_on": False})
    reading = {"systolic": 138, "diastolic": 84}
    await call(deployment, "POST", f"/profiles/{profile_id}/readings", his, 201, json=reading)
    day_one = await call(deployment, "GET", f"/profiles/{profile_id}/feed", his, 200)
    assert {item["format"] for item in day_one["items"]} == {"text"}
    clock.step(timedelta(days=1))
    await call(deployment, "POST", f"/profiles/{profile_id}/readings", his, 201, json=reading)
    day_two = await call(deployment, "GET", f"/profiles/{profile_id}/feed", his, 200)
    assert {item["format"] for item in day_two["items"]} == {"text"}
    assert (await _facts(deployment, profile_id, his))[("format", "preferred")]["value"] == "text"


async def test_what_each_key_reads_and_who_may_write(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    kit = await register_by_phone(deployment, KIT, "Kit")
    siti = await register_by_phone(deployment, SITI, "Siti")
    profile_id = await own_profile(deployment, pa, language="en")
    his = pa["token"]
    await let_in(deployment, pa, profile_id, KIT, ["records", "medicines", "visits"], "son")
    await let_in(deployment, pa, profile_id, SITI, ["medicines"], "helper")
    for phone, role, scopes in (
        (KIT, "caregiver", ["records", "medicines", "visits"]),
        (SITI, "helper", ["medicines"]),
    ):
        await call(
            deployment,
            "POST",
            f"/profiles/{profile_id}/keys",
            his,
            201,
            json={"holder_phone_e164": phone, "role": role, "scopes": scopes},
        )
    path = f"/profiles/{profile_id}/settings"
    await call(deployment, "PUT", path, his, 200, json=SETTINGS)

    # A caregiver holds the record: she reads it all.
    kits = await call(deployment, "GET", path, kit["token"], 200)
    assert kits["conditions"] == IN_GRAPH_ORDER and kits["doctor_name"] == "Dr Tan"
    assert kits["withheld"] == []
    # A helper reads how to talk to him and when; his conditions and his doctor are withheld.
    sitis = await call(deployment, "GET", path, siti["token"], 200)
    assert sitis["withheld"] == ["conditions", "doctor_name"]
    assert sitis["conditions"] is None and sitis["doctor_name"] is None
    assert (sitis["language"], sitis["voice_on"], sitis["large_text"]) == ("ms", True, True)
    assert (sitis["breakfast_time"], sitis["preferred_name"]) == ("07:30", "Pa")
    # Neither of them changes it.
    for token in (kit["token"], siti["token"]):
        await refused(deployment, "PUT", path, token, 403, "NotTheirsToSetUp", json=SETTINGS)

    # He marks his record "only me": the caregiver's read withholds them too.
    minted = await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/confirmations",
        his,
        201,
        json={"subject": "only_me", "scope": "records"},
    )
    await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/privacy",
        his,
        201,
        json={"scope": "records", "confirmation_id": minted["confirmation_id"]},
    )
    narrowed = await call(deployment, "GET", path, kit["token"], 200)
    assert narrowed["withheld"] == ["conditions", "doctor_name"] and narrowed["conditions"] is None

    trail = await call(
        deployment, "GET", f"/profiles/{profile_id}/audit", his, 200, params={"limit": 500}
    )
    refusals = {
        (e["actor_person_id"], e["refused_because"]) for e in trail if e["outcome"] == "refused"
    }
    assert {
        (kit["person_id"], "NotTheirsToSetUp"),
        (siti["person_id"], "NotTheirsToSetUp"),
    } <= refusals


async def test_a_steward_sets_him_up_and_nonsense_is_refused(deployment: Deployment) -> None:
    mei, profile_id = await stewarded(deployment)
    her = mei["token"]
    path = f"/profiles/{profile_id}/settings"
    fresh = await call(deployment, "GET", path, her, 200)
    assert fresh["settings_id"] is None and fresh["language"] == "ms" and fresh["set_at"] is None
    await refused(deployment, "PUT", path, her, 400, "NotALanguage", json={"language": "ta"})
    await refused(
        deployment,
        "PUT",
        path,
        her,
        400,
        "NotACondition",
        json={"language": "ms", "conditions": ["not_a_condition"]},
    )
    bad = await deployment.client.put(
        path,
        json={"language": "ms", "breakfast_time": "7.30"},
        headers={"Authorization": f"Bearer {her}"},
    )
    assert bad.status_code == 422
    saved = await call(deployment, "PUT", path, her, 200, json={**SETTINGS, "language": "en"})
    assert saved["set_by_person_id"] == mei["person_id"]
    assert (await call(deployment, "GET", f"/profiles/{profile_id}", her, 200))["language"] == "en"
    trail = await call(
        deployment, "GET", f"/profiles/{profile_id}/audit", her, 200, params={"limit": 500}
    )
    assert {"NotALanguage", "NotACondition"} <= {
        e["refused_because"] for e in trail if e["outcome"] == "refused"
    }


async def _facts(
    deployment: Deployment, profile_id: str, token: str
) -> dict[tuple[str, str], dict[str, Any]]:
    facts = await call(deployment, "GET", f"/profiles/{profile_id}/facts", token, 200)
    return {(f["subject"], f["attribute"]): f for f in facts}
