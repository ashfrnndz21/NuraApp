"""E02-06: scribble and voice notes on any event.

Acceptance line: the note attaches to the selected event and appears in recall — Ask (E03-05)
finds it, cited with the note and its event, for a key that opens the note. A voice note
is a VOICE artefact heard by the region's transcriber, its words kept by reference and never
a fact; it can be heard again. It is the writer's own words — his about himself, or a
caregiver's on his event — so it rests on the consent to hold the record, not on the
recording consent, which is for consults (ADR 0003). A scribble
is a small image with an optional label. A private note is the notes scope's, a shared one the
record's, and a key that does not open the notes does not see a private one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.channels.strings import COULD_NOT_HEAR
from app.ingestion.models import EventNote
from app.ingestion.objects import sha256_of
from app.ingestion.transcribe import FixtureTranscriber
from app.regions import OutOfRegion, Region
from tests.api import bearer, own_profile, register_by_phone
from tests.capture_support import agree_to_recording, b64, key_for, refusals, voice
from tests.conftest import Deployment
from tests.paper import PNG_SIGNATURE
from tests.voice_notes import AFTER_THE_WALK, MUMBLED, VOICE, placeholder_voice

PA = "+6591210001"
MEI = "+6591210002"
HEARD = "I took it after my walk. I felt fine, only a little tired."
SCRIBBLE = PNG_SIGNATURE + b"nura-scribble-placeholder: a drawn arrow and 'ask Dr Tan'\n"


async def _reading(deployment: Deployment) -> tuple[dict[str, str], str, str]:
    """Pa, his profile, and the event of a blood pressure he typed this morning."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 138, "diastolic": 84},
        headers=bearer(pa["token"]),
    )
    assert posted.status_code == 201, posted.text
    return pa, profile_id, posted.json()["event_id"]


def _notes(profile_id: str, event_id: str) -> str:
    return f"/profiles/{profile_id}/events/{event_id}/notes"


ASKED = "what did I say after my walk"


def _note_lines(answer: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        line for line in answer["lines"] if any(c["kind"] == "event_note" for c in line["cites"])
    ]


async def test_recall_finds_only_the_notes_a_key_opens_and_names_who_left_each(
    deployment: Deployment,
) -> None:
    """His private note is the notes scope's: his caregiver's key, which does not open the
    notes, does not recall it, and he does. Her own note on his moment is shared: he recalls
    it, told as hers."""
    pa, profile_id, event_id = await _reading(deployment)
    his = bearer(pa["token"])
    mei = await register_by_phone(deployment, MEI, "Mei")
    hers = bearer(mei["token"])
    await key_for(deployment, pa, profile_id, MEI, ["records", "readings", "ask"])
    mine = await deployment.client.post(
        _notes(profile_id, event_id), json=voice(AFTER_THE_WALK, private=True), headers=his
    )
    assert mine.status_code == 201, mine.text
    ask = {"question": ASKED, "mode": "text"}

    theirs = await deployment.client.post(f"/profiles/{profile_id}/ask", json=ask, headers=hers)
    assert theirs.status_code == 200, theirs.text
    assert _note_lines(theirs.json()) == []

    drawn = await deployment.client.post(
        _notes(profile_id, event_id),
        json={
            "kind": "scribble",
            "data": b64(SCRIBBLE),
            "content_type": "image/png",
            "captured_at": "2026-09-03T07:55:00Z",
            "label": "after the walk",
        },
        headers=hers,
    )
    assert drawn.status_code == 201, drawn.text
    answered = await deployment.client.post(f"/profiles/{profile_id}/ask", json=ask, headers=his)
    lines = _note_lines(answered.json())
    assert sorted(line["text"] for line in lines) == [
        "Mei left a note on Thursday 3 September.",
        "You left a note on Thursday 3 September.",
    ]
    noted = {c["id"] for line in lines for c in line["cites"] if c["kind"] == "event_note"}
    assert noted == {mine.json()["note_id"], drawn.json()["note_id"]}
    # Her key recalls her own shared note, and still not his private one.
    again = await deployment.client.post(f"/profiles/{profile_id}/ask", json=ask, headers=hers)
    assert [line["text"] for line in _note_lines(again.json())] == [
        "You left a note on Thursday 3 September."
    ]


async def test_a_voice_note_attaches_to_the_event_is_heard_again_and_is_never_a_fact(
    deployment: Deployment,
) -> None:
    pa, profile_id, event_id = await _reading(deployment)
    his = bearer(pa["token"])
    facts_before = (await deployment.client.get(f"/profiles/{profile_id}/facts", headers=his)).json()

    posted = await deployment.client.post(
        _notes(profile_id, event_id), json=voice(AFTER_THE_WALK, label="after my walk"), headers=his
    )
    assert posted.status_code == 201, posted.text
    note = posted.json()
    assert note["event_id"] == event_id and note["kind"] == "voice" and note["private"] is False
    assert note["label"] == "after my walk" and note["content_type"] == "audio/m4a"
    assert note["transcript"] == {"text": HEARD, "confidence": 0.91, "language": "en"}
    assert note["notice"] is None

    # Recall: asked about in his own words, the note is found and cited with its event.
    asked = await deployment.client.post(
        f"/profiles/{profile_id}/ask", json={"question": ASKED, "mode": "text"}, headers=his
    )
    assert asked.status_code == 200, asked.text
    found = _note_lines(asked.json())
    assert [line["text"] for line in found] == ["You left a note on Thursday 3 September."]
    cited = {(cite["kind"], cite["id"]) for cite in found[0]["cites"]}
    assert {("event_note", note["note_id"]), ("event", event_id)} <= cited
    assert "artifact" in {cite["kind"] for cite in found[0]["cites"]}
    assert HEARD not in asked.text  # the words name the note; the answer never says them
    # And on the event itself, with its words.
    listed = await deployment.client.get(_notes(profile_id, event_id), headers=his)
    assert listed.status_code == 200 and listed.json() == [note]
    # Hearable: the recording, as it was kept.
    heard = await deployment.client.get(
        f"{_notes(profile_id, event_id)}/{note['note_id']}/content", headers=his
    )
    assert heard.status_code == 200 and heard.content == placeholder_voice(AFTER_THE_WALK)
    assert heard.headers["content-type"].startswith("audio/m4a")

    # Not a fact: the facts are what they were, and no column holds the words.
    facts_after = (await deployment.client.get(f"/profiles/{profile_id}/facts", headers=his)).json()
    assert facts_after == facts_before
    assert "text" not in EventNote.__table__.c and HEARD not in str(facts_after)
    words = HEARD.encode("utf-8")
    assert deployment.objects.path_of(f"transcripts/{profile_id}/{sha256_of(words)}").read_bytes() == words
    audio = sha256_of(placeholder_voice(AFTER_THE_WALK))
    assert deployment.objects.path_of(f"voice/{profile_id}/{audio}").is_file()


async def test_his_own_voice_note_needs_no_recording_consent(deployment: Deployment) -> None:
    """ADR 0003: his note about himself is his record, on the consent to hold it. Nothing asks
    for the recording consent, and no refusal of it is written."""
    pa, profile_id, event_id = await _reading(deployment)
    his = bearer(pa["token"])
    posted = await deployment.client.post(_notes(profile_id, event_id), json=voice(AFTER_THE_WALK), headers=his)
    assert posted.status_code == 201, posted.text
    agreed = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=his)
    assert "recording" not in {c["purpose"] for c in agreed.json()}
    assert "ConsentWithheld" not in await refusals(deployment, pa, profile_id)


async def test_a_caregivers_voice_note_on_his_event_is_her_own_words(deployment: Deployment) -> None:
    pa, profile_id, event_id = await _reading(deployment)
    mei = await register_by_phone(deployment, MEI, "Mei")
    await key_for(deployment, pa, profile_id, MEI, ["records", "readings"])
    posted = await deployment.client.post(
        _notes(profile_id, event_id), json=voice(AFTER_THE_WALK), headers=bearer(mei["token"])
    )
    assert posted.status_code == 201, posted.text
    assert posted.json()["written_by_person_id"] == mei["person_id"]
    his = await deployment.client.get(_notes(profile_id, event_id), headers=bearer(pa["token"]))
    assert [n["note_id"] for n in his.json()] == [posted.json()["note_id"]]


async def test_the_owner_can_give_the_recording_consent_over_http(deployment: Deployment) -> None:
    """For consults (E02-05, E05): the route stays, owner-only, in today's words."""
    pa, profile_id, _ = await _reading(deployment)
    await agree_to_recording(deployment, pa, profile_id)
    agreed = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=bearer(pa["token"]))
    assert "recording" in {c["purpose"] for c in agreed.json()}
    stale = await deployment.client.post(
        f"/profiles/{profile_id}/consents/recording",
        json={"wording_version": "0", "language": "en", "captured_via": "app"},
        headers=bearer(pa["token"]),
    )
    assert stale.status_code == 400


async def test_a_voice_note_nothing_was_heard_in_is_kept_and_says_so(deployment: Deployment) -> None:
    pa, profile_id, event_id = await _reading(deployment)
    posted = await deployment.client.post(
        _notes(profile_id, event_id), json=voice(MUMBLED), headers=bearer(pa["token"])
    )
    assert posted.status_code == 201, posted.text
    note = posted.json()
    assert note["transcript"] is None and note["notice"] == list(COULD_NOT_HEAR)
    kept = await deployment.client.get(
        f"{_notes(profile_id, event_id)}/{note['note_id']}/content", headers=bearer(pa["token"])
    )
    assert kept.content == placeholder_voice(MUMBLED)


async def test_a_private_scribble_is_his_and_a_shared_voice_note_is_the_familys(
    deployment: Deployment,
) -> None:
    pa, profile_id, event_id = await _reading(deployment)
    his = bearer(pa["token"])
    mei = await register_by_phone(deployment, MEI, "Mei")
    await key_for(deployment, pa, profile_id, MEI, ["records", "readings"])

    shared = await deployment.client.post(
        _notes(profile_id, event_id), json=voice(AFTER_THE_WALK), headers=his
    )
    scribble = await deployment.client.post(
        _notes(profile_id, event_id),
        json={
            "kind": "scribble",
            "data": b64(SCRIBBLE),
            "content_type": "image/png",
            "captured_at": "2026-09-03T07:55:00Z",
            "private": True,
            "label": "ask Dr Tan about this",
        },
        headers=his,
    )
    assert scribble.status_code == 201, scribble.text
    drawn = scribble.json()
    assert drawn["kind"] == "scribble" and drawn["private"] is True and drawn["transcript"] is None
    assert drawn["notice"] is None

    his_view = await deployment.client.get(_notes(profile_id, event_id), headers=his)
    assert {n["note_id"] for n in his_view.json()} == {shared.json()["note_id"], drawn["note_id"]}
    hers = await deployment.client.get(_notes(profile_id, event_id), headers=bearer(mei["token"]))
    assert hers.status_code == 200
    assert [n["note_id"] for n in hers.json()] == [shared.json()["note_id"]]
    peek = await deployment.client.get(
        f"{_notes(profile_id, event_id)}/{drawn['note_id']}/content", headers=bearer(mei["token"])
    )
    assert peek.status_code == 404 and peek.json() == {"refusal": "NoSuchEventNote"}
    seen = await deployment.client.get(
        f"{_notes(profile_id, event_id)}/{drawn['note_id']}/content", headers=his
    )
    assert seen.content == SCRIBBLE
    # Mei cannot leave a private note: her key does not open the notes.
    hidden = await deployment.client.post(
        _notes(profile_id, event_id),
        json={"kind": "scribble", "data": b64(SCRIBBLE), "content_type": "image/png",
              "captured_at": "2026-09-03T08:00:00Z", "private": True},
        headers=bearer(mei["token"]),
    )
    assert hidden.status_code == 403 and hidden.json() == {"refusal": "OutOfScope", "scope": "notes"}


async def test_what_is_not_a_note_is_refused_and_on_the_trail(deployment: Deployment) -> None:
    pa, profile_id, event_id = await _reading(deployment)
    his = bearer(pa["token"])
    long_label = await deployment.client.post(
        _notes(profile_id, event_id), json=voice(AFTER_THE_WALK, label="x" * 81), headers=his
    )
    assert long_label.status_code == 400 and long_label.json() == {"refusal": "NotALabel"}
    not_sound = await deployment.client.post(
        _notes(profile_id, event_id), json=voice(AFTER_THE_WALK, content_type="image/png"), headers=his
    )
    assert not_sound.status_code == 400 and not_sound.json() == {"refusal": "NotAVoiceNote"}
    too_big = await deployment.client.post(
        _notes(profile_id, event_id),
        json={"kind": "scribble", "data": b64(PNG_SIGNATURE + b"0" * (1024 * 1024)),
              "content_type": "image/png", "captured_at": "2026-09-03T08:00:00Z"},
        headers=his,
    )
    assert too_big.status_code == 413 and too_big.json() == {"refusal": "NoteTooLarge"}
    nowhere = await deployment.client.post(
        _notes(profile_id, "00000000-0000-0000-0000-000000000001"), json=voice(AFTER_THE_WALK), headers=his
    )
    assert nowhere.status_code == 400 and nowhere.json() == {"refusal": "NoSuchEvent"}
    assert {"NotALabel", "NotAVoiceNote", "NoteTooLarge", "NoSuchEvent"} <= await refusals(
        deployment, pa, profile_id
    )
    assert (await deployment.client.get(_notes(profile_id, event_id), headers=his)).json() == []


async def test_the_transcriber_is_pinned_to_its_region() -> None:
    here = FixtureTranscriber(VOICE, Region.SG)
    heard = await here.transcribe(placeholder_voice(AFTER_THE_WALK), "audio/m4a", "en", Region.SG)
    assert heard.heard and heard.text == HEARD
    with pytest.raises(OutOfRegion):
        await here.transcribe(placeholder_voice(AFTER_THE_WALK), "audio/m4a", "en", Region.MY)
    assert not (await here.transcribe(b"never heard", "audio/m4a", "en", Region.SG)).heard
    assert Path(VOICE).is_dir()
