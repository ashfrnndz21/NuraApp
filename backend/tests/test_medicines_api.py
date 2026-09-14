"""Medicines over HTTP: the routes checkpoint 6 walks, behind the same key-context dependency
as every other profile route.

    POST /profiles/{id}/artefacts                a label photo, stored in the region
    POST /profiles/{id}/medicines/draft          what the label means, before the yes
    POST /profiles/{id}/confirmations            the yes, subject medicine
    POST /profiles/{id}/medicines                write it
    GET  /profiles/{id}/medicines                the list with count, reorder date and flags
    GET  /profiles/{id}/medicines/{line}/story   the story in his language
    POST /profiles/{id}/medicines/{line}/taken   his tap
    GET  /profiles/{id}/medicines/today          today's dose cards
    GET  /profiles/{id}/medicines/interactions   the flags as questions
    GET  /profiles/{id}/medicines/history        the change log
"""

from __future__ import annotations

import base64
from datetime import timedelta
from typing import Any

from httpx import ASGITransport, AsyncClient

from app.channels.api import Providers, create_app
from app.clock import FrozenClock
from app.db import make_session_factory
from app.drugs.fixture import FixtureRegistry
from app.identity.providers import LoggingCodeSender
from app.regions import Region
from app.settings import Settings
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment, _engine

PA = "+6591110001"
MEI = "+6591110002"
ASH = "+6591110003"

PHOTO = base64.b64encode(b"\xff\xd8\xff\xe0 a label photo, as bytes").decode()
VOICE = base64.b64encode(b"ID3 a voice note saying half a tablet").decode()


async def _artefact(
    client: AsyncClient, profile_id: str, who: dict[str, str], kind: str = "photo"
) -> str:
    made = await client.post(
        f"/profiles/{profile_id}/artefacts",
        json={
            "kind": kind,
            "content_type": "image/jpeg" if kind == "photo" else "audio/mpeg",
            "content_base64": PHOTO if kind == "photo" else VOICE,
        },
        headers=bearer(who["token"]),
    )
    assert made.status_code == 201, made.text
    artifact_id: str = made.json()["artifact_id"]
    return artifact_id


def _label(
    generic: str, strength: str, dose_text: str, quantity: int | None = 30, **more: Any
) -> dict[str, Any]:
    return {
        "generic": generic,
        "strength": strength,
        "dose_text": dose_text,
        "quantity": quantity,
        "prescriber": "Dr Tan",
        **more,
    }


async def _add(
    client: AsyncClient,
    profile_id: str,
    who: dict[str, str],
    label: dict[str, Any],
    artifact_id: str,
) -> Any:
    """Draft, say yes, write: the way the app's card does it. The response of the write."""
    his = bearer(who["token"])
    minted = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "medicine", "label": label, "source_artifact_id": artifact_id},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    return await client.post(
        f"/profiles/{profile_id}/medicines",
        json={
            "label": label,
            "source_artifact_id": artifact_id,
            "confirmation_id": minted.json()["confirmation_id"],
        },
        headers=his,
    )


async def test_the_whole_walk_a_label_becomes_a_line_with_a_story_a_count_and_flags(
    deployment: Deployment, clock: FrozenClock
) -> None:
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="ms")
    his = bearer(pa["token"])

    empty = await client.get(f"/profiles/{profile_id}/medicines", headers=his)
    assert empty.status_code == 200 and empty.json() == []

    # A label photo, then what the label would mean.
    photo = await _artefact(client, profile_id, pa)
    amlodipine = _label("amlodipine", "5 mg", "1 tab OD", 30)
    shown = await client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={"label": amlodipine, "source_artifact_id": photo},
        headers=his,
    )
    assert shown.status_code == 200, shown.text
    draft = shown.json()
    assert draft["outcome"] == "new_line" and draft["match"]["generic"] == "amlodipine"
    assert draft["match"]["registration_no"].startswith("MAL") and not draft["needs_label_photo"]
    assert draft["flagged"] == [] and draft["lead_time_days"] == 3

    # His yes, then the write.
    added = await _add(client, profile_id, pa, amlodipine, photo)
    assert added.status_code == 201, added.text
    line = added.json()
    assert line["outcome"] == "new_line" and line["change_kind"] == "new_line"
    assert line["supply"]["quantity"] == 30 and line["flags"] == []
    line_id = line["line_id"]

    # The same label twice adds nothing: there is no yes to mint for it, and no write.
    again = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "medicine", "label": amlodipine, "source_artifact_id": photo},
        headers=his,
    )
    assert again.status_code == 409 and again.json() == {"refusal": "AlreadyRecorded"}
    spent = await client.post(
        f"/profiles/{profile_id}/medicines",
        json={
            "label": amlodipine,
            "source_artifact_id": photo,
            "confirmation_id": "00000000-0000-0000-0000-000000000001",
        },
        headers=his,
    )
    assert spent.status_code == 409 and spent.json() == {"refusal": "AlreadyRecorded"}

    # The story in Malay — his language — and in English when asked.
    story = await client.get(f"/profiles/{profile_id}/medicines/{line_id}/story", headers=his)
    assert story.status_code == 200, story.text
    told = story.json()
    assert told["language"] == "ms"
    assert told["purpose"] == [
        "Ini ubat tekanan darah anda.",
        "Ia menjaga tekanan darah anda supaya tidak tinggi.",
    ]
    assert told["how_to_take"][0] == "Ambil 1 biji sekali sehari."
    assert told["boundary"][-1] == "Tanya Dr Tan atau ahli farmasi sebelum anda ubah apa-apa."
    assert told["generic"] == "amlodipine" and "amlodipine" not in " ".join(told["lines"])
    english = await client.get(
        f"/profiles/{profile_id}/medicines/{line_id}/story?language=en", headers=his
    )
    assert english.json()["purpose"][0] == "This is your blood pressure tablet."

    # Two taps: the count comes down, the reorder date is arithmetic.
    first = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/taken",
        json={"anchor": "breakfast"},
        headers=his,
    )
    assert first.status_code == 201, first.text
    assert first.json()["by_person_id"] == pa["person_id"] and first.json()["anchor"] == "breakfast"
    clock.step(timedelta(days=1))
    second = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/taken", json={}, headers=his
    )
    assert second.status_code == 201
    listed = await client.get(f"/profiles/{profile_id}/medicines?language=en", headers=his)
    assert listed.status_code == 200, listed.text
    (row,) = listed.json()
    assert row["line_id"] == line_id and row["name"] == "your blood pressure tablet"
    assert row["source_artifact_id"] == photo and row["confidence_state"] == "confirmed_by_person"
    count = row["count"]
    assert count["dispensed"] == 30 and count["taken"] == 2 and count["remaining"] == 28
    assert count["days_left"] == 28 and count["reorder_date"] == "2026-09-29"  # 4 Sept + 28 − 3
    assert not count["reorder_due"] and count["basis"] == "taps"
    assert count["lines"] == [
        "You have 28 tablets of your blood pressure tablet left.",
        "That is about 28 days.",
    ]

    # Warfarin from a voice note: refused by class, nothing written, the refusal on the trail.
    voice = await _artefact(client, profile_id, pa, kind="voice")
    warfarin = _label("warfarin", "3 mg", "1 tab ON", 28)
    told_first = await client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={"label": warfarin, "source_artifact_id": voice},
        headers=his,
    )
    assert (
        told_first.json()["needs_label_photo"] is True
        and told_first.json()["match"]["high_risk"] is True
    )
    refused = await _add(client, profile_id, pa, warfarin, voice)
    assert refused.status_code == 400, refused.text
    assert refused.json() == {"refusal": "HighRiskNeedsLabelPhoto", "drug_class": "anticoagulant"}
    assert len((await client.get(f"/profiles/{profile_id}/medicines", headers=his)).json()) == 1
    # From the label photo it is saved, and marked high-risk.
    label_photo = await _artefact(client, profile_id, pa)
    saved = await _add(client, profile_id, pa, warfarin, label_photo)
    assert saved.status_code == 201, saved.text
    assert saved.json()["high_risk"] is True and saved.json()["generic"] == "warfarin"

    # Aspirin: screened before save, the flag names both drugs and reads as a question.
    aspirin = _label("aspirin", "100 mg", "1 tab OD", 30)
    aspirin_photo = await _artefact(client, profile_id, pa)
    shown = await client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={"label": aspirin, "source_artifact_id": aspirin_photo},
        headers=his,
    )
    (flagged,) = shown.json()["flagged"]
    assert flagged["other_generic"] == "warfarin" and flagged["severity"] == "major"
    assert (
        flagged["question"][0]
        == "Ask Dr Tan about taking the aspirin and the blood thinner tablet together."
    )
    added = await _add(client, profile_id, pa, aspirin, aspirin_photo)
    assert added.status_code == 201, added.text
    (flag,) = added.json()["flags"]
    assert flag["severity"] == "major" and flag["text_id"] == "bleeding_risk"
    questions = await client.get(
        f"/profiles/{profile_id}/medicines/interactions?language=en", headers=his
    )
    assert questions.status_code == 200
    (question,) = questions.json()
    assert question["other_generic"] == "warfarin" and question["severity"] == "major"
    assert question["question"] == [
        "Ask Dr Tan about taking the aspirin and the blood thinner tablet together.",
        "Together they can make you bleed more easily.",
    ]

    # A dose change: 10 mg on the new pack. Nothing moves without his yes; with it, the old
    # line is superseded and kept, and the story asks the doctor.
    new_pack = await _artefact(client, profile_id, pa)
    ten = _label("amlodipine", "10 mg", "1 tab OD", 30)
    shown = await client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={"label": ten, "source_artifact_id": new_pack},
        headers=his,
    )
    assert shown.json()["outcome"] == "dose_change" and shown.json()["matched_line_id"] == line_id
    no_yes = await client.post(
        f"/profiles/{profile_id}/medicines",
        json={
            "label": ten,
            "source_artifact_id": new_pack,
            "confirmation_id": "00000000-0000-0000-0000-000000000001",
        },
        headers=his,
    )
    assert no_yes.status_code == 400 and no_yes.json() == {"refusal": "NotAConfirmerHere"}
    still = {
        r["generic"]: r
        for r in (await client.get(f"/profiles/{profile_id}/medicines", headers=his)).json()
    }
    assert still["amlodipine"]["strength"] == "5 mg" and still["amlodipine"]["line_id"] == line_id
    changed = await _add(client, profile_id, pa, ten, new_pack)
    assert changed.status_code == 201, changed.text
    assert changed.json()["outcome"] == "dose_change" and changed.json()["supersedes_id"] == line_id
    now = {
        r["generic"]: r
        for r in (
            await client.get(f"/profiles/{profile_id}/medicines?language=en", headers=his)
        ).json()
    }
    assert (
        now["amlodipine"]["strength"] == "10 mg"
        and now["amlodipine"]["change_kind"] == "dose_change"
    )
    assert now["amlodipine"]["doctor_question"] == [
        "Your new pack says a different amount from before.",
        "Ask Dr Tan about the new amount.",
    ]
    story = await client.get(
        f"/profiles/{profile_id}/medicines/{now['amlodipine']['line_id']}/story?language=en",
        headers=his,
    )
    assert story.json()["how_to_take"][:2] == story.json()["doctor_question"]
    assert not any(line.startswith("Take ") for line in story.json()["lines"])
    log = (await client.get(f"/profiles/{profile_id}/medicines/history", headers=his)).json()
    assert {(row["generic"], row["strength"], row["superseded_at"] is None) for row in log} == {
        ("amlodipine", "5 mg", False),
        ("warfarin", "3 mg", True),
        ("aspirin", "100 mg", True),
        ("amlodipine", "10 mg", True),
    }
    assert log[0]["strength"] == "5 mg"  # the first line written is first

    # Today's cards: one per anchor, the tap recorded.
    cards = (
        await client.get(f"/profiles/{profile_id}/medicines/today?language=en", headers=his)
    ).json()
    assert [(c["generic"], c["anchor"], c["taken"]) for c in cards] == [
        ("amlodipine", "breakfast", True),
        ("aspirin", "breakfast", False),
        ("warfarin", "bed", False),
    ]
    assert cards[2]["card"] == "Take 1 tablet of the blood thinner tablet before bed."
    assert cards[2]["taken_label"] == "Taken"

    # Mei, a helper with the medicines key: reads the list and the story, cannot add.
    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(deployment, pa, profile_id, MEI, ["medicines"], "helper")
    granted = await client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "helper", "scopes": ["medicines"]},
        headers=his,
    )
    assert granted.status_code == 201, granted.text
    hers = bearer(mei["token"])
    seen = await client.get(f"/profiles/{profile_id}/medicines", headers=hers)
    assert seen.status_code == 200 and len(seen.json()) == 3
    read = await client.get(
        f"/profiles/{profile_id}/medicines/{saved.json()['line_id']}/story", headers=hers
    )
    assert read.status_code == 200 and read.json()["language"] == "ms"
    her_photo = await client.post(
        f"/profiles/{profile_id}/artefacts",
        json={"kind": "photo", "content_type": "image/jpeg", "content_base64": PHOTO},
        headers=hers,
    )
    assert her_photo.status_code == 403  # records scope: an artefact is a paper
    her_draft = await client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={
            "label": _label("paracetamol", "500 mg", "2 tabs prn", 20),
            "source_artifact_id": photo,
        },
        headers=hers,
    )
    assert her_draft.status_code == 403 and her_draft.json() == {"refusal": "NotTheirsToChange"}
    her_yes = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={
            "subject": "medicine",
            "label": _label("paracetamol", "500 mg", "2 tabs prn", 20),
            "source_artifact_id": photo,
        },
        headers=hers,
    )
    assert her_yes.status_code == 403 and her_yes.json() == {"refusal": "NotTheirsToChange"}
    her_add = await client.post(
        f"/profiles/{profile_id}/medicines",
        json={
            "label": _label("paracetamol", "500 mg", "2 tabs prn", 20),
            "source_artifact_id": photo,
            "confirmation_id": "00000000-0000-0000-0000-000000000001",
        },
        headers=hers,
    )
    assert her_add.status_code == 403 and her_add.json() == {"refusal": "NotTheirsToChange"}
    assert len((await client.get(f"/profiles/{profile_id}/medicines", headers=his)).json()) == 3
    # She may tap Taken for him.
    given = await client.post(
        f"/profiles/{profile_id}/medicines/{saved.json()['line_id']}/taken",
        json={"anchor": "bed"},
        headers=hers,
    )
    assert given.status_code == 201 and given.json()["by_person_id"] == mei["person_id"]

    # Every refusal is on Pa's trail, by name, with no content. Every read is on it too,
    # so the trail is long; it is read per person, under the medicines scope, 500 at a time.
    trail: list[dict[str, Any]] = []
    for person in (pa, mei):
        page = await client.get(
            f"/profiles/{profile_id}/audit?actor_person_id={person['person_id']}"
            "&scope=medicines&limit=500",
            headers=his,
        )
        assert page.status_code == 200, page.text
        trail.extend(page.json())
    refused_names = {
        (row["actor_person_id"], row["action"], row["refused_because"])
        for row in trail
        if row["outcome"] == "refused"
    }
    assert (pa["person_id"], "write", "HighRiskNeedsLabelPhoto") in refused_names
    # The yes that could not be minted for the duplicate, and the write that was refused.
    assert (pa["person_id"], "read", "AlreadyRecorded") in refused_names
    assert (pa["person_id"], "write", "AlreadyRecorded") in refused_names
    assert (pa["person_id"], "write", "NotAConfirmerHere") in refused_names
    assert (mei["person_id"], "read", "NotTheirsToChange") in refused_names
    assert (mei["person_id"], "write", "NotTheirsToChange") in refused_names
    assert "warfarin" not in str(trail) and "amlodipine" not in str(trail)


async def test_the_label_must_name_a_medicine_and_say_the_dose_one_way(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    photo = await _artefact(deployment.client, profile_id, pa)
    for label in (
        {"dose_text": "1 tab OD"},  # nothing names the medicine
        {"generic": "amlodipine", "strength": "5 mg"},  # no dose
        {
            "generic": "amlodipine",
            "dose_text": "1 tab OD",
            "dose": {"amount": 1, "unit": "tablet", "frequency": "od"},
        },
        {"generic": "amlodipine", "dose": {"amount": 0, "unit": "tablet", "frequency": "od"}},
    ):
        refused = await deployment.client.post(
            f"/profiles/{profile_id}/medicines/draft",
            json={"label": label, "source_artifact_id": photo},
            headers=his,
        )
        assert refused.status_code == 422, refused.text
    # Words the parser cannot read are asked, not guessed: a refusal, not a default regimen.
    unread = await deployment.client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={
            "label": {"generic": "amlodipine", "strength": "5 mg", "dose_text": "as directed"},
            "source_artifact_id": photo,
        },
        headers=his,
    )
    assert unread.status_code == 400 and unread.json() == {"refusal": "DoseNotRead"}
    unknown = await deployment.client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={"label": _label("ibuprofen", "200 mg", "1 tab BD"), "source_artifact_id": photo},
        headers=his,
    )
    assert unknown.status_code == 400 and unknown.json() == {"refusal": "NotIdentified"}
    missing = await deployment.client.get(
        f"/profiles/{profile_id}/medicines/00000000-0000-0000-0000-000000000009/story", headers=his
    )
    assert missing.status_code == 404 and missing.json() == {"refusal": "NoSuchLine"}


async def test_a_dose_from_a_pdf_is_not_a_label_photo_either(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    made = await deployment.client.post(
        f"/profiles/{profile_id}/artefacts",
        json={"kind": "pdf", "content_type": "application/pdf", "content_base64": PHOTO},
        headers=bearer(pa["token"]),
    )
    assert made.status_code == 201
    refused = await _add(
        deployment.client,
        profile_id,
        pa,
        _label("insulin glargine", "100 units/ml", "10 units ON", 900),
        made.json()["artifact_id"],
    )
    assert refused.status_code == 400 and refused.json() == {
        "refusal": "HighRiskNeedsLabelPhoto",
        "drug_class": "insulin",
    }


async def test_without_an_object_store_the_api_cannot_take_an_artefact() -> None:
    engine = await _engine()
    sender = LoggingCodeSender(reveal=True)
    app = create_app(
        Settings(region=Region.SG, database_url="sqlite+aiosqlite://", dev_code_sender=True),
        make_session_factory(engine),
        Providers(code_sender=sender, drug_registry=FixtureRegistry.load(), object_store=None),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://nura.test") as client:
        deployment = Deployment(
            region=Region.SG, client=client, sessions=make_session_factory(engine), sender=sender
        )
        pa = await register_by_phone(deployment, PA, "Pa")
        profile_id = await own_profile(deployment, pa)
        refused = await client.post(
            f"/profiles/{profile_id}/artefacts",
            json={"kind": "photo", "content_type": "image/jpeg", "content_base64": PHOTO},
            headers=bearer(pa["token"]),
        )
        assert refused.status_code == 503 and refused.json() == {"refusal": "NoObjectStore"}
        bad = await client.post(
            f"/profiles/{profile_id}/artefacts",
            json={"kind": "photo", "content_type": "image/jpeg", "content_base64": "not base64!!"},
            headers=bearer(pa["token"]),
        )
        assert bad.status_code == 503  # the store is checked first; nothing is decoded for nowhere
    await engine.dispose()
