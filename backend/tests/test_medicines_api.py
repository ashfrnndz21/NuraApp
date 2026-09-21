"""Medicines over HTTP: the routes checkpoint 6 walks, behind the same key-context dependency
as every other profile route.

    POST /profiles/{id}/photos                   a label photo, stored in the region (E02)
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
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient

from app.clock import FrozenClock
from app.db import utcnow
from app.keys.context import resolve_key_context
from app.memory.episodic import store_artifact
from app.memory.models import ArtifactKind, Recording, SourceChannel
from app.regions import Region
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.paper import PILL_PHOTO, placeholder_png

PA = "+6591110001"
MEI = "+6591110002"
ASH = "+6591110003"

PHOTO = base64.b64encode(b"\x89PNG\r\n\x1a\n a label photo the extractor does not know").decode()


async def _artefact(
    client: AsyncClient, profile_id: str, who: dict[str, str], salt: str = ""
) -> str:
    """A label photo through E02's photo route: an artefact of kind PHOTO, and a review card
    with nothing on it, since the extractor knows nothing about these bytes."""
    made = await client.post(
        f"/profiles/{profile_id}/photos",
        json={
            "data": base64.b64encode(base64.b64decode(PHOTO) + salt.encode()).decode(),
            "content_type": "image/png",
            "captured_at": "2026-09-03T08:00:00Z",
        },
        headers=bearer(who["token"]),
    )
    assert made.status_code == 201, made.text
    assert made.json()["document_kind"] == "unknown" and made.json()["fields"] == []
    artifact_id: str = made.json()["artifact_id"]
    return artifact_id


async def _not_a_photo(
    deployment: Deployment, profile_id: str, who: dict[str, str], kind: ArtifactKind
) -> str:
    """An artefact that is not a photo — a voice note, a PDF. No route makes one yet (POST
    /photos takes only photos), so it is written the way ingestion will write it, through
    `store_artifact` under the owner's context."""
    async with deployment.sessions() as session:
        context = await resolve_key_context(
            session,
            region=Region.SG,
            person_id=uuid.UUID(who["person_id"]),
            profile_id=uuid.UUID(profile_id),
        )
        digest = uuid.uuid4().hex + uuid.uuid4().hex
        artifact = await store_artifact(
            session,
            context=context,
            kind=kind,
            storage_key=f"sg/{profile_id}/{digest}",
            content_type="audio/mpeg" if kind is ArtifactKind.VOICE else "application/pdf",
            sha256=digest,
            captured_at=utcnow(),
            source_channel=SourceChannel.APP,
            region=Region.SG,
            # A voice note is someone's own words, kept on the record consent (ADR 0003).
            recording=Recording.OWN_NOTE if kind is ArtifactKind.VOICE else None,
        )
        await session.commit()
        return str(artifact.id)


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
    photo = await _artefact(client, profile_id, pa, "one")
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
    # And as voice notes (E04-06): each part said once, kept by its script's digest, then read.
    assert told["voice_parts"][0] == "purpose" and "if_forgotten" in told["voice_parts"]
    for part in told["voice_parts"]:
        where = f"/profiles/{profile_id}/medicines/{line_id}/story/voice"
        first = await client.get(where, params={"part": part}, headers=his)
        assert first.status_code == 200, (part, first.text)
        assert first.headers["content-type"] == "audio/wav"
        assert 0 < float(first.headers["x-duration-seconds"]) <= 30
        again = await client.get(where, params={"part": part}, headers=his)
        assert (first.headers["x-voice-cache"], again.headers["x-voice-cache"]) == ("miss", "hit")
        assert again.content == first.content
    unknown = await client.get(
        f"/profiles/{profile_id}/medicines/{line_id}/story/voice",
        params={"part": "price"},
        headers=his,
    )
    assert unknown.status_code == 422
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
    voice = await _not_a_photo(deployment, profile_id, pa, ArtifactKind.VOICE)
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
    label_photo = await _artefact(client, profile_id, pa, "two")
    saved = await _add(client, profile_id, pa, warfarin, label_photo)
    assert saved.status_code == 201, saved.text
    assert saved.json()["high_risk"] is True and saved.json()["generic"] == "warfarin"

    # Aspirin: screened before save, the flag names both drugs and reads as a question.
    aspirin = _label("aspirin", "100 mg", "1 tab OD", 30)
    aspirin_photo = await _artefact(client, profile_id, pa, "three")
    shown = await client.post(
        f"/profiles/{profile_id}/medicines/draft?language=en",
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
    new_pack = await _artefact(client, profile_id, pa, "four")
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
    await let_in(deployment, pa, profile_id, MEI, ["medicines"], "helper", role="helper")
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
        f"/profiles/{profile_id}/photos",
        json={"data": PHOTO, "content_type": "image/png", "captured_at": "2026-09-03T08:00:00Z"},
        headers=hers,
    )
    assert her_photo.status_code == 403  # records scope: a photo is a paper
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
    # A well-formed label the register has no product for is refused too — NotIdentified
    # answers "no product in this register matches", not "this label is malformed"; digoxin
    # is deliberately never in the fixture (tests/test_drugs.py::
    # test_a_monograph_is_rule_ids_not_prose relies on the same gap), so the case does not
    # depend on the fixture's coverage staying thin as it grows.
    unknown = await deployment.client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={"label": _label("digoxin", "0.125 mg", "1 tab OD"), "source_artifact_id": photo},
        headers=his,
    )
    assert unknown.status_code == 400 and unknown.json() == {"refusal": "NotIdentified"}
    # warfarin is high-risk and on file at more than one strength; a label that does not say
    # which gets its own refusal (#211), not the generic "could not find this medicine" —
    # the register did identify the drug, only the strength is undetermined.
    ambiguous = await deployment.client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={
            "label": _label("warfarin", None, "1 tab OD"),  # type: ignore[arg-type]
            "source_artifact_id": photo,
        },
        headers=his,
    )
    assert ambiguous.status_code == 400 and ambiguous.json() == {"refusal": "StrengthNotRead"}
    missing = await deployment.client.get(
        f"/profiles/{profile_id}/medicines/00000000-0000-0000-0000-000000000009/story", headers=his
    )
    assert missing.status_code == 404 and missing.json() == {"refusal": "NoSuchLine"}


async def test_a_dose_from_a_pdf_is_not_a_label_photo_either(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    pdf = await _not_a_photo(deployment, profile_id, pa, ArtifactKind.PDF)
    refused = await _add(
        deployment.client,
        profile_id,
        pa,
        _label("insulin glargine", "100 units/ml", "10 units ON", 900),
        pdf,
    )
    assert refused.status_code == 400
    assert refused.json() == {"refusal": "HighRiskNeedsLabelPhoto", "drug_class": "insulin"}


async def test_a_tap_the_phone_held_offline_is_written_when_he_made_it_and_once(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """E00-08: *Taken* tapped with no network is held on the phone and sent when the network is
    back, with the moment he tapped. The backend writes it at that moment, writes it once
    however often it comes, and takes only today's."""
    clock.set(datetime(2026, 9, 14, 2, 0, tzinfo=UTC))  # 10:00 in Singapore
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    photo = await _artefact(client, profile_id, pa, "held")
    added = await _add(client, profile_id, pa, _label("amlodipine", "5 mg", "1 tab OD", 30), photo)
    assert added.status_code == 201, added.text
    route = f"/profiles/{profile_id}/medicines/{added.json()['line_id']}/taken"

    held = {"anchor": "breakfast", "taken_at": "2026-09-14T08:05:00+08:00"}
    first = await client.post(route, json=held, headers=his)
    assert first.status_code == 201, first.text
    assert first.json()["taken_at"].startswith("2026-09-14T00:05:00")
    # The answer was lost on the way back and the phone sends it again: one tap, written once.
    again = await client.post(route, json=held, headers=his)
    assert again.status_code == 201, again.text
    assert again.json()["dose_taken_id"] == first.json()["dose_taken_id"]
    assert again.json()["taken_at"] == first.json()["taken_at"]
    listed = await client.get(f"/profiles/{profile_id}/medicines?language=en", headers=his)
    assert listed.json()[0]["count"]["taken"] == 1
    slots = await client.get(f"/profiles/{profile_id}/medicines/today?language=en", headers=his)
    assert [(slot["anchor"], slot["taken"]) for slot in slots.json()] == [("breakfast", True)]

    # Yesterday's tap is not today's tablet, and a tap cannot be from later than now.
    for moment in ("2026-09-13T21:00:00+08:00", "2026-09-14T10:30:00+08:00"):
        refused = await client.post(
            route, json={"anchor": "breakfast", "taken_at": moment}, headers=his
        )
        assert refused.status_code == 400, moment
        assert refused.json() == {"refusal": "TapNotToday"}, moment
    # A phone's clock a minute ahead is still today's tap.
    ahead = await client.post(
        route, json={"anchor": "lunch", "taken_at": "2026-09-14T10:01:00+08:00"}, headers=his
    )
    assert ahead.status_code == 201, ahead.text
    assert ahead.json()["taken_at"].startswith("2026-09-14T02:01:00")
    # A moment with no zone is refused before anything is written.
    naive = await client.post(
        route, json={"anchor": "breakfast", "taken_at": "2026-09-14T08:05:00"}, headers=his
    )
    assert naive.status_code == 422


async def test_a_typed_medicine_keeps_its_own_artefact_and_the_list_says_so(
    deployment: Deployment,
) -> None:
    """POST /medicines/typed (redesign package 11, the "type it" entry point): the words he
    typed are kept as their own artefact, exactly the way a photo is, and once the medicine
    is added its source line says "you told Nura" — never "the label" — while a photo-backed
    line still says "the label" as it always has."""
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])

    kept = await client.post(
        f"/profiles/{profile_id}/medicines/typed",
        json={"text": "I take fish oil 1000 mg every morning", "captured_at": "2026-09-10T08:00:00Z"},
        headers=his,
    )
    assert kept.status_code == 201, kept.text
    typed_artifact = kept.json()["artifact_id"]
    assert uuid.UUID(typed_artifact)  # a real id, not an echo of the text

    typed_label = _label("fish oil", "1000 mg", "1 capsule OD", None)
    added_typed = await _add(client, profile_id, pa, typed_label, typed_artifact)
    assert added_typed.status_code == 201, added_typed.text

    photo = await _artefact(client, profile_id, pa, "label-source")
    added_photo = await _add(
        client, profile_id, pa, _label("amlodipine", "5 mg", "1 tab OD", 30), photo
    )
    assert added_photo.status_code == 201, added_photo.text

    listed = {
        r["generic"]: r
        for r in (await client.get(f"/profiles/{profile_id}/medicines?language=en", headers=his)).json()
    }
    assert listed["fish oil"]["source"].startswith("You typed this in on")
    assert listed["amlodipine"]["source"].startswith("This comes from the label you kept on")


async def test_empty_or_too_long_typed_words_are_refused(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    empty = await deployment.client.post(
        f"/profiles/{profile_id}/medicines/typed", json={"text": "   "}, headers=his
    )
    assert empty.status_code in (400, 422), empty.text
    too_long = await deployment.client.post(
        f"/profiles/{profile_id}/medicines/typed", json={"text": "x" * 5000}, headers=his
    )
    assert too_long.status_code == 422, too_long.text


async def test_classify_over_http_answers_medicine_class_or_unknown(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])

    medicine = await deployment.client.get(
        f"/profiles/{profile_id}/medicines/classify", params={"name": "amlodipine"}, headers=his
    )
    assert medicine.status_code == 200
    assert medicine.json() == {
        "name_kind": "medicine",
        "candidates": [],
        "resolved_generic": "amlodipine",
    }

    # #10: a brand-only name still classifies as a medicine, and resolves to the register's
    # own generic — never the brand text itself, which `identify()` would never match against
    # a `LabelIn.generic`.
    brand = await deployment.client.get(
        f"/profiles/{profile_id}/medicines/classify", params={"name": "Norvasc"}, headers=his
    )
    assert brand.status_code == 200
    assert brand.json() == {
        "name_kind": "medicine",
        "candidates": [],
        "resolved_generic": "amlodipine",
    }

    family = await deployment.client.get(
        f"/profiles/{profile_id}/medicines/classify", params={"name": "STATIN"}, headers=his
    )
    assert family.status_code == 200
    assert family.json()["name_kind"] == "class"
    assert family.json()["resolved_generic"] is None
    assert {c["generic"] for c in family.json()["candidates"]} == {
        "atorvastatin",
        "simvastatin",
        "rosuvastatin",
    }

    unknown = await deployment.client.get(
        f"/profiles/{profile_id}/medicines/classify",
        params={"name": "not a real thing"},
        headers=his,
    )
    assert unknown.status_code == 200
    assert unknown.json() == {"name_kind": "unknown", "candidates": [], "resolved_generic": None}


async def test_adding_a_medicine_by_photo_closes_the_cards_own_review_card(
    deployment: Deployment,
) -> None:
    """#9: the add-a-medicine screen runs its own confirm pipeline (`POST /medicines`), past
    the ordinary paper review card its photo made — never `confirm_review_card` itself. Left
    alone, that card stayed open forever, so `app.search.ask.waiting_papers` (and the ordinary
    papers screen) kept asking him to check a label he had already said yes to through the
    medicines screen. Writing the line must close its own card, and only its own — a second,
    unrelated open card must still show as waiting."""
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])

    photo = await _artefact(client, profile_id, pa, "closes-its-card")
    other_photo = await _artefact(client, profile_id, pa, "stays-open")

    before = await client.get(
        f"/profiles/{profile_id}/review-cards", params={"open": "true"}, headers=his
    )
    assert before.status_code == 200
    assert {c["artifact_id"] for c in before.json()} == {photo, other_photo}

    amlodipine = _label("amlodipine", "5 mg", "1 tab OD", 30)
    added = await _add(client, profile_id, pa, amlodipine, photo)
    assert added.status_code == 201, added.text

    after = await client.get(
        f"/profiles/{profile_id}/review-cards", params={"open": "true"}, headers=his
    )
    assert after.status_code == 200
    still_open = {c["artifact_id"] for c in after.json()}
    assert still_open == {other_photo}  # the medicine's own card closed; the other did not

    closed = await client.get(f"/profiles/{profile_id}/review-cards", headers=his)
    mine = next(c for c in closed.json() if c["artifact_id"] == photo)
    assert mine["confirmed_at"] is not None
    assert mine["confirmed_by_person_id"] is not None


async def test_the_two_duplicate_outcomes_are_told_apart_by_matched_line_id(
    deployment: Deployment,
) -> None:
    """#11: `POST /medicines/draft` answers `outcome: "duplicate"` for two different reasons,
    and a caller must be able to tell them apart, or a screen that offers "yes, say how many"
    for one of them loops forever on the other.

    Case A — this exact photo already wrote this exact medicine (`_label_seen_before`):
    nothing is missing, there is no quantity that would ever change the answer, and
    `matched_line_id` is null, exactly as `Plan(Outcome.DUPLICATE, match, None, None, ...)`
    on the backend leaves it.

    Case B — an active line already matches on strength and dose, but this label gave no
    quantity to add as a refill: asking for one is the right next question, and
    `matched_line_id` names the line it would refill.
    """
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])

    # Case A: add it once for real, then draft the very same label from the very same photo.
    photo = await _artefact(client, profile_id, pa, "case-a")
    amlodipine = _label("amlodipine", "5 mg", "1 tab OD", 30)
    added = await _add(client, profile_id, pa, amlodipine, photo)
    assert added.status_code == 201, added.text

    replayed = await client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={"label": amlodipine, "source_artifact_id": photo},
        headers=his,
    )
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["outcome"] == "duplicate"
    assert replayed.json()["matched_line_id"] is None  # nothing "yes, say how many" could fix

    # Case B: a second, unrelated photo, same medicine and dose, no quantity this time.
    second_photo = await _artefact(client, profile_id, pa, "case-b")
    no_quantity = _label("amlodipine", "5 mg", "1 tab OD", quantity=None)
    missing_quantity = await client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={"label": no_quantity, "source_artifact_id": second_photo},
        headers=his,
    )
    assert missing_quantity.status_code == 200, missing_quantity.text
    assert missing_quantity.json()["outcome"] == "duplicate"
    assert missing_quantity.json()["matched_line_id"] is not None  # "how many" is the fix

    # Answering it — the same photo, now with a quantity — refills the very line it named.
    with_quantity = _label("amlodipine", "5 mg", "1 tab OD", quantity=30)
    now_a_refill = await client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={"label": with_quantity, "source_artifact_id": second_photo},
        headers=his,
    )
    assert now_a_refill.status_code == 200, now_a_refill.text
    assert now_a_refill.json()["outcome"] == "refill"
    assert now_a_refill.json()["matched_line_id"] == missing_quantity.json()["matched_line_id"]


async def test_a_brand_only_name_no_longer_dead_ends_the_draft(deployment: Deployment) -> None:
    """#10: classify says a brand-only name ("Norvasc") is a known medicine, but `identify()`
    only ever matches `LabelIn.generic` against a product's own generic — so a caller that
    replays the classified name straight back as `generic` gets `NotIdentified` even though
    classify just said yes. The add path must settle on `resolved_generic` first."""
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])

    classified = await client.get(
        f"/profiles/{profile_id}/medicines/classify", params={"name": "Norvasc"}, headers=his
    )
    assert classified.status_code == 200
    resolved = classified.json()["resolved_generic"]
    assert resolved == "amlodipine"

    # The dead end, reproduced: sending the brand straight back as `generic` finds nothing.
    photo = await _artefact(client, profile_id, pa, "brand-dead-end")
    dead_end = await client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={"label": _label("Norvasc", "5 mg", "1 tab OD", 30), "source_artifact_id": photo},
        headers=his,
    )
    assert dead_end.status_code == 400, dead_end.text
    assert dead_end.json()["refusal"] == "NotIdentified"

    # Settled on the register's own generic first, exactly as the add screen now does: works.
    fixed = await client.post(
        f"/profiles/{profile_id}/medicines/draft",
        json={"label": _label(resolved, "5 mg", "1 tab OD", 30), "source_artifact_id": photo},
        headers=his,
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["match"]["generic"] == "amlodipine"


async def test_a_medicines_only_helper_key_is_told_the_real_source_kind_not_a_guess(
    deployment: Deployment,
) -> None:
    """BLOCKER 1, independent safety review #1's no-migration fix: a key that holds
    `Scope.MEDICINES` and not `Scope.RECORDS` used to be told nothing about a line's own
    artefact at all (`_artifact_kinds_for` answered `{}` outright), so `source_line` fell
    back to guessing "the label you kept" from the mere presence of a `source_artifact_id` —
    wrong for a typed entry, and never honest about a pill photo either. This fails
    behaviourally on the prior head: Mei's read of the typed line used to say "the label you
    kept" for a label that never existed, and of the pill photo the same.

    Three real source kinds, read by Mei — a helper key holding `medicines` alone, never
    `records` and never `family` — and the neutral fallback checked separately
    (`test_source_line_says_a_neutral_sentence_when_the_kind_cannot_be_read`, a pure
    function test: there is no way to make a real artefact "unreadable" through the API,
    since every line's own artefact is always on file)."""
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])

    # A label photo.
    photo = await _artefact(client, profile_id, pa, "medicines-only-label")
    label_added = await _add(client, profile_id, pa, _label("amlodipine", "5 mg", "1 tab OD", 30), photo)
    assert label_added.status_code == 201, label_added.text

    # A pill photo — a real one, so its review card genuinely reads `pill_photo`.
    pill_photo_made = await client.post(
        f"/profiles/{profile_id}/photos",
        json={
            "data": base64.b64encode(placeholder_png(PILL_PHOTO)).decode(),
            "content_type": "image/png",
            "captured_at": "2026-09-03T08:00:00Z",
        },
        headers=his,
    )
    assert pill_photo_made.status_code == 201, pill_photo_made.text
    assert pill_photo_made.json()["document_kind"] == "pill_photo"
    pill_photo_id = pill_photo_made.json()["artifact_id"]
    pill_added = await _add(
        client, profile_id, pa, _label("paracetamol", "500 mg", "1 tab prn", 20), pill_photo_id
    )
    assert pill_added.status_code == 201, pill_added.text

    # A typed entry, by Pa himself.
    typed = await client.post(
        f"/profiles/{profile_id}/medicines/typed",
        json={"text": "I take fish oil 1000 mg every morning", "captured_at": "2026-09-10T08:00:00Z"},
        headers=his,
    )
    assert typed.status_code == 201, typed.text
    typed_added = await _add(
        client, profile_id, pa, _label("fish oil", "1000 mg", "1 capsule OD", None), typed.json()["artifact_id"]
    )
    assert typed_added.status_code == 201, typed_added.text

    # Mei: a helper key, medicines only — never records, never family.
    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(deployment, pa, profile_id, MEI, ["medicines"], "helper", role="helper")
    granted = await client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "helper", "scopes": ["medicines"]},
        headers=his,
    )
    assert granted.status_code == 201, granted.text
    hers = bearer(mei["token"])

    listed = {
        r["generic"]: r
        for r in (await client.get(f"/profiles/{profile_id}/medicines?language=en", headers=hers)).json()
    }
    # Said about him by name on Mei's own key (`app.channels.about_him`), the same as every
    # other second-person line she reads: "the label Pa kept", never "you kept".
    assert listed["amlodipine"]["source"].startswith("This comes from the label Pa kept on")
    assert listed["paracetamol"]["source"].startswith("This comes from a photo of a tablet")
    assert "the label" not in listed["paracetamol"]["source"]
    # Pa typed it himself; Mei reads it with her own key, medicines-only — she still gets his
    # real name (`Scope.PROFILE`, which every key holds), never "the label you kept".
    assert listed["fish oil"]["source"].startswith("Pa typed this in on")
    assert "the label" not in listed["fish oil"]["source"]

    # Pa's own read, for comparison: he typed it himself, so it is "You", not his own name.
    his_own = {
        r["generic"]: r
        for r in (await client.get(f"/profiles/{profile_id}/medicines?language=en", headers=his)).json()
    }
    assert his_own["fish oil"]["source"].startswith("You typed this in on")


def test_source_line_says_a_neutral_sentence_when_the_kind_cannot_be_read() -> None:
    """BLOCKER 1: an artefact id is on the line but its own kind could not be read (a
    deleted artefact, or some future failure this has not seen yet) — `source_line` never
    falls back to "the label you kept" from the mere fact that a `source_artifact_id` is on
    file; a neutral sentence that claims nothing about where it came from instead."""
    from zoneinfo import ZoneInfo

    from app.medicines.models import MedicationLine
    from app.medicines.service import source_line

    line = MedicationLine(
        started_at=datetime(2026, 9, 19, 8, 0, tzinfo=UTC),
        source_artifact_id=uuid.uuid4(),
        confirmed_by_person_id=uuid.uuid4(),
    )
    text = source_line(line, ZoneInfo("Asia/Singapore"), "en", artifact_kind=None, is_pill_photo=False)
    assert text.startswith("Nura has this written down since")
    assert "label" not in text
    assert "pill" not in text.lower()
