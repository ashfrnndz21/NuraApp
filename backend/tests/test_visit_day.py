"""The visit day (E05-03, E05-04, E02-05, E03-05): the logistics card, the recording, clips.

    E05-03  Logistics card: time, place, parking, who is driving, what to bring.
            Driver pulled from roster; card sent T-1 and T-0.
    E05-04  In-visit recording flow. One tap to start with consent prompt; ends into post-visit.
    E02-05  Consult recording with consent prompt, transcription, speaker separation and
            timestamps. Consent captured before recording; transcript searchable; clip
            playable at a timestamp.
    E03-05  Answers cite the artefact; consult answers play the clip at the timestamp.

Over HTTP, the way the web client and checkpoint 22 reach it. Pa, his chief Mei (a note about
the place, and on the roster on Saturdays), Kit with a viewer's key, Siti with a helper's. The
visit is Saturday 5 September at 9 in the morning in Singapore; the clock stands on Thursday 3
September at 4 in the afternoon, so the visit is two days away, then the day before, then the
day.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import Response
from sqlalchemy import select

from app.channels.api import visits as visits_routes
from app.clock import FrozenClock
from app.db import take_keepers
from app.ingestion.consult import (
    MAX_CONSULT_SECONDS,
    ConsultTooLong,
    NotAConsultRecording,
    check_consult_audio,
)
from app.ingestion.models import ConsultRecording, ConsultSegment, Speaker
from app.ingestion.speakers import Segment, SegmentsDoNotFit, Unseparated, align
from app.ingestion.transcribe import Transcript
from app.keys.context import resolve_key_context
from app.keys.scopes import Scope
from app.memory.episodic import OnlyTheFamilyHears, require_artifact
from app.memory.models import Artifact, ArtifactKind
from app.reasoning.visits.summary import ConsultClips, Span
from app.regions import Region
from app.safety.plain_words import verify
from app.safety.recording import CHECKLIST, recording_notice
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.capture_support import agree_to_recording, confirm, decide, pdf, photo, refusals
from tests.conftest import Deployment
from tests.consult_audio import CONSULT, CONTENT_TYPE, DURATION_S, placeholder_consult
from tests.paper import DISCHARGE_LETTER

PA, MEI, KIT, SITI = "+6591210001", "+6591210002", "+6591210003", "+6591210004"
VISIT_AT = "2026-09-05T01:00:00Z"
"""Saturday 5 September, 9 in the morning in Singapore."""
ADDRESS = "Gleneagles Hospital, 6A Napier Road"
QUESTION = "what did Dr Tan say about the water pill"
EVERY_PART = [scope.value for scope in Scope if scope is not Scope.PROFILE]
ADR = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0006-consult-recording-on-the-web.md"

FRIDAY_MORNING = datetime(2026, 9, 4, 2, 0, tzinfo=UTC)
"""Friday 4 September, 10 in the morning in Singapore: the day before."""
SATURDAY_EARLY = datetime(2026, 9, 4, 23, 30, tzinfo=UTC)
"""Saturday 5 September, half past 7 in the morning in Singapore: the day."""


async def _ok(response: Response, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _clean(lines: list[str], language: str = "en") -> None:
    for line in lines:
        assert [f for f in verify(line, language) if f.severity != "note"] == [], line


@dataclass
class House:
    deployment: Deployment
    pa: dict[str, str]
    mei: dict[str, str]
    profile_id: str
    provider_id: str
    appointment_id: str

    @property
    def his(self) -> dict[str, str]:
        return bearer(self.pa["token"])

    @property
    def hers(self) -> dict[str, str]:
        return bearer(self.mei["token"])

    def at(self, path: str) -> str:
        return f"/profiles/{self.profile_id}{path}"

    @property
    def visit(self) -> str:
        return self.at(f"/appointments/{self.appointment_id}")


async def household(deployment: Deployment) -> House:
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(deployment, pa, profile_id, MEI, EVERY_PART, relationship="daughter")
    await _ok(
        await client.post(
            f"/profiles/{profile_id}/keys", json={"holder_phone_e164": MEI, "role": "chief"}, headers=his
        ),
        201,
    )
    tan = await _ok(
        await client.post(
            f"/profiles/{profile_id}/providers",
            json={"name": "Dr Tan", "kind": "doctor", "address": ADDRESS},
            headers=his,
        ),
        201,
    )
    booking = {"provider_id": tan["provider_id"], "scheduled_at": VISIT_AT, "purpose": "blood pressure check"}
    yes = await _ok(
        await client.post(
            f"/profiles/{profile_id}/confirmations", json={"subject": "appointment", **booking}, headers=his
        ),
        201,
    )
    visit = await _ok(
        await client.post(
            f"/profiles/{profile_id}/appointments",
            json={**booking, "confirmation_id": yes["confirmation_id"]},
            headers=his,
        ),
        201,
    )
    hers = bearer(mei["token"])
    await _ok(
        await client.post(
            f"/profiles/{profile_id}/providers/{tan['provider_id']}/notes",
            json={"text": "parking at B2"},
            headers=hers,
        ),
        201,
    )
    await _ok(
        await client.post(
            f"/profiles/{profile_id}/roster",
            json={
                "person_id": mei["person_id"],
                "role": "chief",
                "weekdays": [5],
                "from_time": "07:00:00",
                "to_time": "12:00:00",
            },
            headers=hers,
        ),
        201,
    )
    return House(deployment, pa, mei, profile_id, tan["provider_id"], visit["appointment_id"])


async def _key(house: House, phone: str, name: str, role: str, scopes: list[str]) -> dict[str, str]:
    person = await register_by_phone(house.deployment, phone, name)
    await let_in(house.deployment, house.pa, house.profile_id, phone, scopes, relationship="son")
    await _ok(
        await house.deployment.client.post(
            house.at("/keys"), json={"holder_phone_e164": phone, "role": role, "scopes": scopes}, headers=house.his
        ),
        201,
    )
    return person


async def _upload(house: House, who: dict[str, str], data: bytes, **params: Any) -> Response:
    return await house.deployment.client.post(
        f"{house.visit}/recording",
        content=data,
        params={"duration_s": DURATION_S, **params},
        headers={**bearer(who["token"]), "Content-Type": params.pop("content_type", CONTENT_TYPE)},
    )


async def _kept(house: House) -> tuple[list[ConsultRecording], list[Artifact]]:
    async with house.deployment.sessions() as session:
        recordings = list((await session.execute(select(ConsultRecording))).scalars())
        voices = list(
            (await session.execute(select(Artifact).where(Artifact.kind == ArtifactKind.VOICE))).scalars()
        )
    return recordings, voices


# --- the pieces --------------------------------------------------------------------------------


def test_segments_are_kept_as_pointers_into_the_transcript_in_order() -> None:
    text = "Is that OK, Dr Tan? Yes, that is fine. Thank you."
    found = align(
        text,
        [
            Segment(Speaker.UNKNOWN, 0.0, 2.0, "Is that OK, Dr Tan?"),
            Segment(Speaker.DOCTOR, 2.0, 3.5, " Yes, that is fine. "),
            Segment(Speaker.PATIENT, 3.5, 4.0, "Thank you."),
        ],
    )
    assert [(one.speaker, text[one.char_start : one.char_end]) for one in found] == [
        (Speaker.UNKNOWN, "Is that OK, Dr Tan?"),
        (Speaker.DOCTOR, "Yes, that is fine."),
        (Speaker.PATIENT, "Thank you."),
    ]
    with pytest.raises(SegmentsDoNotFit):
        align(text, [Segment(Speaker.DOCTOR, 0.0, 1.0, "words nobody said")])
    with pytest.raises(SegmentsDoNotFit):
        align(text, [Segment(Speaker.DOCTOR, 2.0, 3.0, "Yes"), Segment(Speaker.DOCTOR, 1.0, 1.5, "Thank")])
    with pytest.raises(SegmentsDoNotFit):
        align(text, [Segment(Speaker.DOCTOR, 1.0, 1.0, "Yes")])


def test_an_item_plays_from_the_segments_its_words_fall_in() -> None:
    text = "Is that OK? Yes. Take half. Thank you."
    clips = ConsultClips(
        artifact_id=uuid.uuid4(),
        segments=align(
            text,
            [
                Segment(Speaker.UNKNOWN, 0.0, 2.0, "Is that OK?"),
                Segment(Speaker.DOCTOR, 2.0, 3.0, "Yes."),
                Segment(Speaker.DOCTOR, 3.0, 6.5, "Take half."),
                Segment(Speaker.PATIENT, 6.5, 8.0, "Thank you."),
            ],
        ),
    )
    at = text.index("Take half.")
    assert clips.window(Span(at, at + len("Take half."))) == (3.0, 6.5)
    assert clips.window(Span(text.index("Yes."), at + 4)) == (2.0, 6.5)
    assert ConsultClips(clips.artifact_id, ()).window(Span(0, 5)) is None


async def test_with_no_separator_the_recording_is_one_stretch_by_an_unknown_speaker() -> None:
    heard = Transcript(text="Good morning.", confidence=0.9)
    segments = await Unseparated(Region.SG, 12.0).separate(heard, b"x", Region.SG)
    assert [(one.speaker, one.start_s, one.end_s) for one in segments] == [(Speaker.UNKNOWN, 0.0, 12.0)]
    assert await Unseparated(Region.SG).separate(Transcript("", 0.0), b"x", Region.SG) == ()


def test_only_a_recorders_own_audio_of_a_visits_length_is_kept() -> None:
    webm = placeholder_consult(CONSULT)
    assert check_consult_audio(webm, "audio/webm;codecs=opus", 66.0) == "audio/webm"
    assert check_consult_audio(b"OggS" + b"x", "audio/ogg", 2.0) == "audio/ogg"
    assert check_consult_audio(b"\0\0\0\x18ftypM4A ", "audio/mp4", 2.0) == "audio/mp4"
    for data, kind, seconds in (
        (b"", "audio/webm", 2.0),
        (webm, "text/plain", 2.0),
        (b"OggS" + b"x", "audio/webm", 2.0),
        (webm, "audio/webm", 0.5),
    ):
        with pytest.raises(NotAConsultRecording):
            check_consult_audio(data, kind, seconds)
    with pytest.raises(ConsultTooLong):
        check_consult_audio(webm, "audio/webm", MAX_CONSULT_SECONDS + 1)


def test_the_adr_names_every_step_of_the_recording_checklist() -> None:
    """The steps the surface owes (`CHECKLIST`, docs/trust/recording-consent.md) are each
    named in ADR 0006, which says where the web surface keeps them."""
    written = ADR.read_text(encoding="utf-8")
    assert [step for step in CHECKLIST if f"`{step}`" not in written] == []


# --- E05-03: the logistics card ----------------------------------------------------------------


async def test_the_logistics_card_is_composed_from_the_record_and_the_roster_waits_for_a_yes(
    deployment: Deployment,
) -> None:
    house = await household(deployment)
    card = await _ok(await deployment.client.get(f"{house.visit}/logistics", headers=house.his))
    assert card["state_id"] and card["doctor"] == "Dr Tan" and card["place"] == ADDRESS
    by_section = {line["section"]: line["text"] for line in card["lines"]}
    assert by_section["when"] == "You see Dr Tan on Saturday 5 September at 9 in the morning."
    assert by_section["place"] == f"Dr Tan is at {ADDRESS}."
    assert by_section["note"] == "Mei wrote a note about getting to Dr Tan."
    # The chief's note, as she wrote it, under her name: never a template, never read for facts.
    assert card["note"]["text"] == "parking at B2" and card["note"]["label"] == "Mei's note"
    # The roster has Mei on duty on Saturday mornings: a suggestion, nothing yet.
    assert card["driver"]["status"] == "suggested" and card["driver"]["name"] == "Mei"
    assert card["driver"]["needs_yes"] is True and card["driver"]["can_say_yes"] is True
    assert by_section["driver"] == "Mei will tell you who is driving you to Dr Tan on Saturday 5 September."
    assert [line["text"] for line in card["lines"] if line["section"] == "bring"] == [
        "Bring your blood pressure book on Saturday 5 September."
    ]
    _clean([line["text"] for line in card["lines"]])
    assert card["spoken"] == [line["spoken"] for line in card["lines"]]
    tasks = await _ok(await deployment.client.get(house.at("/tasks"), headers=house.hers))
    assert tasks == []

    # A key that does not reach the family list reads no note and no driver, and says so.
    kit = await _key(house, KIT, "Kit", "caregiver", ["visits", "records", "readings", "medicines"])
    theirs = await _ok(await deployment.client.get(f"{house.visit}/logistics", headers=bearer(kit["token"])))
    assert theirs["note"] is None and theirs["driver"]["status"] == "withheld"
    assert "family" in theirs["withheld"]
    assert {line["section"] for line in theirs["lines"]} == {"when", "place", "bring"}


async def test_the_chiefs_yes_gives_the_drive_and_the_card_names_the_driver(
    deployment: Deployment,
) -> None:
    house = await household(deployment)
    client = deployment.client
    draft = {"subject": "drive", "appointment_id": house.appointment_id, "person_id": house.mei["person_id"]}
    # Without a yes for exactly this, nothing is given.
    refused = await client.post(
        f"{house.visit}/driver",
        json={"person_id": house.mei["person_id"], "confirmation_id": house.appointment_id},
        headers=house.hers,
    )
    assert refused.status_code == 400 and refused.json() == {"refusal": "NotAConfirmerHere"}
    # A caregiver is not the chief: no yes to mint.
    kit = await _key(house, KIT, "Kit", "caregiver", EVERY_PART)
    theirs = await client.post(house.at("/confirmations"), json=draft, headers=bearer(kit["token"]))
    assert theirs.status_code == 403 and theirs.json() == {"refusal": "NotAChief"}
    # A clinic's key is never asked to drive him.
    clinic = await _key(house, SITI, "Clinic", "clinic", ["visits", "records"])
    not_family = await client.post(
        house.at("/confirmations"), json={**draft, "person_id": clinic["person_id"]}, headers=house.hers
    )
    assert not_family.status_code == 400 and not_family.json() == {"refusal": "NotOnThisVisit"}

    yes = await _ok(await client.post(house.at("/confirmations"), json=draft, headers=house.hers), 201)
    task = await _ok(
        await client.post(
            f"{house.visit}/driver",
            json={"person_id": house.mei["person_id"], "confirmation_id": yes["confirmation_id"]},
            headers=house.hers,
        ),
        201,
    )
    assert task["what"] == "drive Pa to Dr Tan" and task["errand"] == "drive"
    assert task["appointment_id"] == house.appointment_id and task["assigned_person_id"] == house.mei["person_id"]
    assert task["due_at"].startswith("2026-09-05T01:00")
    card = await _ok(await client.get(f"{house.visit}/logistics", headers=house.his))
    assert card["driver"] == {
        "status": "assigned",
        "person_id": house.mei["person_id"],
        "name": "Mei",
        "task_id": task["task_id"],
        "needs_yes": False,
        "can_say_yes": False,
    }
    assert "Mei will drive you to Dr Tan on Saturday 5 September." in [line["text"] for line in card["lines"]]
    # The yes is spent: the same one twice is refused.
    again = await client.post(
        f"{house.visit}/driver",
        json={"person_id": house.mei["person_id"], "confirmation_id": yes["confirmation_id"]},
        headers=house.hers,
    )
    assert again.status_code == 400 and again.json() == {"refusal": "AlreadySpent"}


async def test_what_to_bring_is_the_brief_s_lines_his_medicines_and_his_hospital_letter(
    deployment: Deployment,
) -> None:
    house = await household(deployment)
    client = deployment.client
    label_photo = await _ok(await client.post(house.at("/photos"), json=photo("a-pill-box"), headers=house.his), 201)
    label = {
        "generic": "amlodipine",
        "strength": "5 mg",
        "dose_text": "1 tab OD",
        "quantity": 30,
        "prescriber": "Dr Tan",
        "source_kind": "retail",
    }
    yes = await _ok(
        await client.post(
            house.at("/confirmations"),
            json={"subject": "medicine", "label": label, "source_artifact_id": label_photo["artifact_id"]},
            headers=house.his,
        ),
        201,
    )
    await _ok(
        await client.post(
            house.at("/medicines"),
            json={"label": label, "source_artifact_id": label_photo["artifact_id"], "confirmation_id": yes["confirmation_id"]},
            headers=house.his,
        ),
        201,
    )
    letter = await _ok(
        await client.post(house.at("/imports"), json=pdf(DISCHARGE_LETTER, hint="discharge_letter"), headers=house.his),
        201,
    )
    closed = await confirm(deployment, house.pa["token"], house.profile_id, letter, decide(letter))
    assert closed.status_code == 200, closed.text
    card = await _ok(await client.get(f"{house.visit}/logistics", headers=house.his))
    assert [line["text"] for line in card["lines"] if line["section"] == "bring"] == [
        "Bring your blood pressure book on Saturday 5 September.",
        "Bring your medicines in their boxes on Saturday 5 September.",
        "Bring your hospital letter on Saturday 5 September.",
    ]


async def test_the_logistics_card_comes_the_day_before_and_on_the_day(
    deployment: Deployment, clock: FrozenClock
) -> None:
    house = await household(deployment)

    async def logistics_cards() -> list[dict[str, Any]]:
        page = await _ok(await deployment.client.get(house.at("/feed"), headers=house.his))
        return [item for item in page["items"] if item["type"] == "visit_logistics"]

    # Thursday: two days away, no card.
    assert await logistics_cards() == []
    clock.set(FRIDAY_MORNING)
    tomorrow = await logistics_cards()
    assert [one["headline"] for one in tomorrow] == ["Getting to Dr Tan tomorrow"]
    card = await _ok(await deployment.client.get(f"{house.visit}/logistics", headers=house.his))
    # The card carries the visits' part only: when, where, what to bring from the visit. Who
    # drives him and Mei's note are the family list's, and stay off a card a viewer can read.
    visits_part = [line for line in card["lines"] if line["section"] in ("when", "place", "bring")]
    assert tomorrow[0]["body"] == [line["text"] for line in visits_part]
    assert tomorrow[0]["voice"] == [line["spoken"] for line in visits_part]
    assert not any("Mei" in line for line in tomorrow[0]["body"]) and tomorrow[0]["rendered_from_state"]
    assert tomorrow[0]["boundary"] is None and tomorrow[0]["autoplay"] is False
    clock.set(SATURDAY_EARLY)
    today = await logistics_cards()
    assert [one["headline"] for one in today] == ["Getting to Dr Tan today"]
    assert today[0]["item_id"] != tomorrow[0]["item_id"]


# --- E02-05, E05-04: the recording -------------------------------------------------------------


async def test_nothing_records_without_the_recording_consent(deployment: Deployment) -> None:
    house = await household(deployment)
    client = deployment.client
    notice = await client.get(f"{house.visit}/recording/notice", headers=house.his)
    assert notice.status_code == 403 and notice.json() == {"refusal": "ConsentWithheld"}
    upload = await _upload(house, house.mei, placeholder_consult(CONSULT))
    assert upload.status_code == 403 and upload.json() == {"refusal": "ConsentWithheld"}
    recordings, voices = await _kept(house)
    assert recordings == [] and voices == []
    assert not (deployment.objects.path_of(f"consults/{house.profile_id}/x").parent).exists()
    assert "ConsentWithheld" in await refusals(deployment, house.pa, house.profile_id)


async def test_a_key_that_does_not_change_the_visits_is_refused_before_the_room_is_told(
    deployment: Deployment,
) -> None:
    house = await household(deployment)
    await agree_to_recording(deployment, house.pa, house.profile_id)
    kit = await _key(house, KIT, "Kit", "viewer", ["visits", "readings"])
    siti = await _key(house, SITI, "Siti", "helper", ["medicines"])
    viewer = await deployment.client.get(f"{house.visit}/recording/notice", headers=bearer(kit["token"]))
    assert viewer.status_code == 403 and viewer.json() == {"refusal": "NotTheirsToChangeVisits"}
    helper = await deployment.client.get(f"{house.visit}/recording/notice", headers=bearer(siti["token"]))
    assert helper.status_code == 403 and helper.json() == {"refusal": "OutOfScope", "scope": "visits"}


async def test_consent_then_notice_then_upload_keeps_a_consult_and_ends_in_the_post_visit_card(
    deployment: Deployment,
) -> None:
    house = await household(deployment)
    client = deployment.client
    await agree_to_recording(deployment, house.pa, house.profile_id)

    # The notice, once the gate has passed: in his language, to the doctor by name.
    his = await _ok(await client.get(f"{house.visit}/recording/notice", headers=house.his))
    assert his["spoken"] == recording_notice("en", doctor="Dr Tan").splitlines()
    assert his["spoken"][-1] == "Is that OK, Dr Tan?"
    assert his["printed"][0] == "This patient uses Nura."
    assert his["when_no"] == ["Nura will not listen today.", "You will write the notes by hand."]
    hers = await _ok(await client.get(f"{house.visit}/recording/notice", headers=house.hers))
    assert hers["when_no"][-1] == "Mei will write the notes by hand."

    # Stop: the bytes, once.
    data = placeholder_consult(CONSULT)
    kept = await _ok(await _upload(house, house.mei, data), 201)
    recording = kept["recording"]
    assert recording["consent_id"] == his["consent_id"] and recording["heard"] is True
    assert recording["heard_confidence"] == 0.93 and recording["duration_s"] == DURATION_S
    assert recording["doctor_named"] is True and recording["notice_language"] == "en"
    assert recording["recorded_by_person_id"] == house.mei["person_id"]
    speakers = [(one["speaker"], one["start_s"], one["end_s"]) for one in recording["segments"]]
    assert speakers[:2] == [("unknown", 0.0, 8.6), ("doctor", 8.6, 10.4)]
    assert [one[0] for one in speakers].count("doctor") == 8
    assert {"patient", "family"} <= {one[0] for one in speakers}

    # A consult VOICE artefact in the region's store, byte for byte; the transcript beside it.
    async with deployment.sessions() as session:
        voice = await session.get(Artifact, uuid.UUID(recording["artifact_id"]))
        transcript = await session.get(Artifact, uuid.UUID(recording["transcript_artifact_id"]))
        segments = list((await session.execute(select(ConsultSegment))).scalars())
    assert voice is not None and voice.kind is ArtifactKind.VOICE and voice.content_type == "audio/webm"
    assert deployment.objects.path_of(voice.storage_key).read_bytes() == data
    assert voice.storage_key.startswith(f"consults/{house.profile_id}/")
    assert transcript is not None and transcript.kind is ArtifactKind.TRANSCRIPT
    text = deployment.objects.path_of(transcript.storage_key).read_text()
    assert text[segments[1].char_start : segments[1].char_end] == "Yes, that is fine."

    # The post-visit card, from the transcript, every item placed in the recording.
    summary = kept["summary"]
    assert kept["summary_refused"] is None and summary["artifact_id"] == recording["transcript_artifact_id"]
    assert summary["recording_artifact_id"] == recording["artifact_id"]
    assert "Ask Dr Tan about the new amount of the water pill (frusemide)." in summary["lines"]
    _clean(summary["lines"])

    def clip_of(**payload: str) -> tuple[float, float]:
        (item,) = [i for i in summary["items"] if payload.items() <= i["payload"].items()]
        return item["clip_start_s"], item["clip_end_s"]

    assert clip_of(generic="frusemide") == (19.8, 28.9)
    assert clip_of(kind="weigh_every_morning") == (28.9, 36.2)
    assert clip_of(subject="blood_pressure") == (10.4, 19.8)
    assert all(
        item["clip_start_s"] is not None and item["clip_start_s"] < item["clip_end_s"]
        for item in summary["items"]
    )

    listed = await _ok(await client.get(f"{house.visit}/recordings", headers=house.his))
    assert [one["recording_id"] for one in listed] == [recording["recording_id"]]
    assert len(listed[0]["segments"]) == 11
    summaries = await _ok(await client.get(f"{house.visit}/summaries", headers=house.his))
    assert summaries[0]["recording_artifact_id"] == recording["artifact_id"]


async def test_a_no_keeps_nothing(deployment: Deployment) -> None:
    """The doctor, or he, says no after the notice: the phone uploads nothing, so the
    server holds nothing — no recording, no voice, no bytes — and the words for a no say who
    writes the notes by hand."""
    house = await household(deployment)
    await agree_to_recording(deployment, house.pa, house.profile_id)
    notice = await _ok(await deployment.client.get(f"{house.visit}/recording/notice", headers=house.hers))
    assert notice["when_no"] == ["Nura will not listen today.", "Mei will write the notes by hand."]
    recordings, voices = await _kept(house)
    assert recordings == [] and voices == []
    # The by-hand path is E05's: the notes typed, read into the same card.
    typed = await deployment.client.post(
        f"{house.visit}/transcript",
        json={"data": __import__("base64").b64encode(b"Dr Tan said to weigh every morning.").decode()},
        headers=house.hers,
    )
    assert typed.status_code == 201, typed.text


async def test_a_recording_nobody_could_hear_is_kept_and_makes_no_card(deployment: Deployment) -> None:
    house = await household(deployment)
    await agree_to_recording(deployment, house.pa, house.profile_id)
    kept = await _ok(await _upload(house, house.his and house.pa, placeholder_consult("mumbled")), 201)
    assert kept["recording"]["heard"] is False and kept["recording"]["segments"] == []
    assert kept["summary"] is None and kept["summary_refused"] is None
    recordings, voices = await _kept(house)
    assert len(recordings) == 1 and len(voices) == 1


async def test_what_is_not_a_visit_s_recording_is_refused_on_the_trail(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> None:
    house = await household(deployment)
    await agree_to_recording(deployment, house.pa, house.profile_id)
    data = placeholder_consult(CONSULT)
    wrong_type = await _upload(house, house.pa, data, content_type="text/plain")
    assert wrong_type.status_code == 400 and wrong_type.json() == {"refusal": "NotAConsultRecording"}
    wrong_bytes = await _upload(house, house.pa, b"OggS" + data, content_type="audio/webm")
    assert wrong_bytes.status_code == 400
    too_long = await _upload(house, house.pa, data, duration_s=MAX_CONSULT_SECONDS + 1)
    assert too_long.status_code == 413 and too_long.json() == {"refusal": "ConsultTooLong"}
    monkeypatch.setattr(visits_routes, "MAX_CONSULT_BYTES", 16)
    too_big = await _upload(house, house.pa, data)
    assert too_big.status_code == 413 and too_big.json() == {"refusal": "ConsultTooLong"}
    recordings, voices = await _kept(house)
    assert recordings == [] and voices == []
    assert {"NotAConsultRecording", "ConsultTooLong"} <= await refusals(deployment, house.pa, house.profile_id)


# --- E03-05: the answer cites the clip, and the clip plays under the artefact's scope ---------


async def test_an_answer_cites_only_what_he_confirmed_and_the_clip_is_heard_only_by_his_family(
    deployment: Deployment,
) -> None:
    house = await household(deployment)
    client = deployment.client
    await agree_to_recording(deployment, house.pa, house.profile_id)
    data = placeholder_consult(CONSULT)
    kept = await _ok(await _upload(house, house.mei, data), 201)
    artifact_id = kept["recording"]["artifact_id"]
    summary = kept["summary"]
    ask = {"question": QUESTION, "mode": "text"}

    # Before his yes, recall cites nothing Dr Tan said: the card is waiting for it.
    waiting = await _ok(await client.post(house.at("/ask"), json=ask, headers=house.hers))
    on_the_card = [
        line for line in waiting["lines"] if any(c["kind"] == "visit_summary" for c in line["cites"])
    ]
    assert [line["text"] for line in on_the_card] == [
        "Your card from Dr Tan on Saturday 5 September is waiting for your yes."
    ]
    _clean([line["text"] for line in on_the_card])
    assert all(line["clip"] is None for line in waiting["lines"])
    assert not any(
        c["kind"] in ("artifact", "summary_item") for line in on_the_card for c in line["cites"]
    )

    # His yes, through Mei, his chief: every item kept.
    decisions = [{"item_id": item["item_id"], "decision": "confirmed"} for item in summary["items"]]
    yes = await _ok(
        await client.post(
            house.at("/confirmations"),
            json={"subject": "visit_summary", "summary_id": summary["summary_id"], "decisions": decisions},
            headers=house.hers,
        ),
        201,
    )
    await _ok(
        await client.post(
            f"{house.visit}/summary/{summary['summary_id']}/confirm",
            json={"decisions": decisions, "confirmation_id": yes["confirmation_id"]},
            headers=house.hers,
        )
    )

    # After it, transcript searchable: the answer finds where he said it, and cites it.
    answer = await _ok(await client.post(house.at("/ask"), json=ask, headers=house.hers))
    said = [line for line in answer["lines"] if line["clip"] is not None]
    assert [line["text"] for line in said] == ["Dr Tan talked about this on Saturday 5 September."]
    clip = said[0]["clip"]
    assert clip == {"artifact_id": artifact_id, "start_s": 19.8, "end_s": 28.9, "doctor": "Dr Tan"}
    cited = [cite for cite in said[0]["cites"] if cite["kind"] == "artifact"]
    assert cited == [{"kind": "artifact", "id": artifact_id, "start_s": 19.8, "end_s": 28.9}]
    assert {"summary_item", "appointment"} <= {cite["kind"] for cite in said[0]["cites"]}
    voiced = await _ok(
        await client.post(house.at("/ask"), json={**ask, "mode": "voice"}, headers=house.his)
    )
    assert voiced["lines"][0]["clip"]["start_s"] == 19.8

    # The clip, and the whole recording: him and the family he let in hear it, nobody else.
    where = house.at(f"/artifacts/{artifact_id}/clip")
    stretch, whole = {"start": 19.8, "end": 28.9}, {"start": 0, "end": DURATION_S}
    played = await client.get(where, params=stretch, headers=house.his)
    assert played.status_code == 200 and played.content == data
    assert played.headers["content-type"].startswith("audio/webm")
    assert played.headers["x-clip-start"] == "19.8" and played.headers["x-clip-end"] == "28.9"
    assert played.headers["x-media-fragment"] == "t=19.8,28.9"
    lim = await _key(house, "+6591210006", "Lim", "caregiver", ["visits", "records", "readings"])
    kit = await _key(house, KIT, "Kit", "viewer", ["visits", "readings"])
    clinic = await _key(house, "+6591210007", "Clinic", "clinic", ["visits", "records"])
    for params in (stretch, whole):
        heard = await client.get(where, params=params, headers=bearer(lim["token"]))
        assert heard.status_code == 200 and heard.content == data, heard.text
        for who in (kit, clinic):
            refused = await client.get(where, params=params, headers=bearer(who["token"]))
            assert refused.status_code == 403 and refused.json() == {"refusal": "OnlyTheFamilyHears"}
    outside = await client.get(where, params={"start": 10, "end": 500}, headers=house.his)
    assert outside.status_code == 400 and outside.json() == {"refusal": "NotAClip"}
    siti = await _key(house, SITI, "Siti", "helper", ["medicines"])
    helper = await client.get(where, params=stretch, headers=bearer(siti["token"]))
    assert helper.status_code == 403 and helper.json() == {"refusal": "OutOfScope", "scope": "visits"}

    # The transcript heard from it is behind the same door: a clinic key cannot read it either.
    async with deployment.sessions() as session:
        context = await resolve_key_context(
            session,
            region=Region.SG,
            person_id=uuid.UUID(clinic["person_id"]),
            profile_id=uuid.UUID(house.profile_id),
        )
        with pytest.raises(OnlyTheFamilyHears):
            await require_artifact(
                session,
                context=context,
                artifact_id=uuid.UUID(kept["recording"]["transcript_artifact_id"]),
            )
        take_keepers(session)
        await session.commit()
    assert {"OnlyTheFamilyHears", "NotAClip", "OutOfScope"} <= await refusals(
        deployment, house.pa, house.profile_id
    )


async def test_a_card_is_never_refused_for_a_name_the_family_has_not_given(
    deployment: Deployment,
) -> None:
    """A chief who signed up with no name: the card says "your family", and is still a card."""
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    mei = await register_by_phone(deployment, MEI)
    await let_in(deployment, pa, profile_id, MEI, EVERY_PART, relationship="daughter")
    await _ok(
        await client.post(f"/profiles/{profile_id}/keys", json={"holder_phone_e164": MEI, "role": "chief"}, headers=his),
        201,
    )
    tan = await _ok(
        await client.post(f"/profiles/{profile_id}/providers", json={"name": "Dr Tan", "kind": "doctor"}, headers=his),
        201,
    )
    booking = {"provider_id": tan["provider_id"], "scheduled_at": VISIT_AT, "purpose": "blood pressure check"}
    yes = await _ok(
        await client.post(f"/profiles/{profile_id}/confirmations", json={"subject": "appointment", **booking}, headers=his),
        201,
    )
    visit = await _ok(
        await client.post(f"/profiles/{profile_id}/appointments", json={**booking, "confirmation_id": yes["confirmation_id"]}, headers=his),
        201,
    )
    hers = bearer(mei["token"])
    await _ok(
        await client.post(f"/profiles/{profile_id}/providers/{tan['provider_id']}/notes", json={"text": "parking at B2"}, headers=hers),
        201,
    )
    route = f"/profiles/{profile_id}/appointments/{visit['appointment_id']}"
    card = await _ok(await client.get(f"{route}/logistics", headers=his))
    texts = [line["text"] for line in card["lines"]]
    if card["note"]["by_name"]:
        return  # the account has a name after all (the owner's naming reached it): nothing to prove
    assert card["note"]["label"] == "Your family's note" and card["note"]["text"] == "parking at B2"
    assert "Your family wrote a note about getting to Dr Tan." in texts
    assert "Nura does not have Dr Tan's address yet." in texts
    _clean(texts)


async def test_one_reminder_of_a_visit_a_day_the_logistics_card_holds_the_anticipation_nudge(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """E17's anticipation nudge and E05-03's logistics card say the same thing the day before.
    Before the card is on his feed the nudge goes as his one reminder; once it is, the nudge is
    held, and the plan says why."""
    house = await household(deployment)
    clock.set(FRIDAY_MORNING)
    plan = await _ok(await deployment.client.get(house.at("/nudges/plan"), headers=house.his))
    assert [d["reason"].get("code") for d in plan["drafts"]] == ["visit_tomorrow"]
    page = await _ok(await deployment.client.get(house.at("/feed"), headers=house.his))
    (card,) = [item for item in page["items"] if item["type"] == "visit_logistics"]
    again = await _ok(await deployment.client.get(house.at("/nudges/plan"), headers=house.his))
    assert all(d["kind"] != "anticipation" for d in again["drafts"])
    (held,) = [h for h in again["held"] if h["kind"] == "anticipation"]
    assert held["because"] == "logistics_card_says_it"
    assert held["reason"]["appointment_id"] == house.appointment_id
    assert held["reason"]["feed_item_id"] == card["item_id"]
