"""#129: a consult recording sent in chunks as it is made, so a long visit survives a dropped
connection.

    Upload in chunks as it records (resumable, each chunk under the recording's consent and
    region), assemble server-side, and keep the rule that a 'no' or leaving before the doctor
    answers keeps nothing: nothing is stored until the doctor's yes. Tests: a dropped
    connection mid-visit resumes; a no discards chunks already sent.

Over HTTP, on the visit day's household (`tests.test_visit_day`), with the placeholder
recording the fixtures know (`tests.consult_audio`), cut into chunks.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm.attributes import set_committed_value

from app.clock import FrozenClock
from app.db import utcnow
from app.ingestion import chunks
from app.ingestion.chunks import ANSWER_WITHIN, FINISH_WITHIN, MAX_CHUNK_BYTES
from app.ingestion.models import ConsultUpload
from app.ingestion.s3 import ObjectStoreUnavailable
from app.regions import Region
from tests.api import bearer, let_in, register_by_phone
from tests.capture_support import agree_to_recording, refusals
from tests.conftest import Deployment, _serve
from tests.consult_audio import CONSULT, CONTENT_TYPE, DURATION_S, WEBM_MAGIC, placeholder_consult
from tests.test_upload_cap import CHUNK, Endless
from tests.test_visit_day import House, _kept, household

DATA = placeholder_consult(CONSULT)
STARTED = "2026-09-03T08:00:00+00:00"
KIT = "+6593990129"


def pieces(data: bytes, size: int = 10) -> list[bytes]:
    return [data[start : start + size] for start in range(0, len(data), size)]


async def _ok(response: Response, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


class Phone:
    """The phone at the visit: one upload, sent chunk by chunk, by the person holding it."""

    def __init__(self, house: House, who: dict[str, str]) -> None:
        self.house = house
        self.who = who
        self.client = house.deployment.client
        self.upload = ""

    @property
    def headers(self) -> dict[str, str]:
        return bearer(self.who["token"])

    def at(self, rest: str = "") -> str:
        return f"{self.house.visit}/recording/uploads/{self.upload}{rest}"

    async def open(self) -> dict[str, Any]:
        opened = await self.client.post(
            f"{self.house.visit}/recording/uploads",
            json={"content_type": CONTENT_TYPE, "started_at": STARTED},
            headers=self.headers,
        )
        body: dict[str, Any] = await _ok(opened, 201)
        self.upload = body["upload_id"]
        return body

    async def chunk(self, position: int, data: bytes | Endless) -> Response:
        return await self.client.put(
            self.at(f"/chunks/{position}"),
            content=data,
            headers={**self.headers, "Content-Type": "application/octet-stream"},
        )

    async def send(self, data: bytes, *, first: int = 0) -> None:
        for offset, piece in enumerate(pieces(data)):
            await _ok(await self.chunk(first + offset, piece))

    async def status(self) -> Response:
        return await self.client.get(self.at(), headers=self.headers)

    async def yes(self) -> Response:
        return await self.client.post(self.at("/yes"), headers=self.headers)

    async def finish(self) -> Response:
        return await self.client.post(
            self.at("/finish"), params={"duration_s": DURATION_S}, headers=self.headers
        )

    async def discard(self, because: str) -> Response:
        return await self.client.delete(self.at(), params={"because": because}, headers=self.headers)

    def staged(self) -> list[Path]:
        """The chunks waiting in the region's store for this upload."""
        where = self.house.deployment.objects.root / "consult-uploads" / self.house.profile_id / self.upload
        return sorted(where.iterdir()) if where.exists() else []

    async def cut_short(self, position: int, data: bytes) -> list[dict[str, Any]]:
        """Half of a chunk sent, then the connection drops: the server's body stops and its
        client is gone, the way a phone losing its signal looks to it."""
        app = self.client._transport.app  # type: ignore[attr-defined]
        path = self.at(f"/chunks/{position}")
        arriving: list[dict[str, Any]] = [
            {"type": "http.request", "body": data[: len(data) // 2], "more_body": True},
            {"type": "http.disconnect"},
        ]

        async def receive() -> dict[str, Any]:
            return arriving.pop(0) if arriving else {"type": "http.disconnect"}

        answered: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            answered.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "PUT",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"nura.test"),
                (b"authorization", f"Bearer {self.who['token']}".encode()),
                (b"content-type", b"application/octet-stream"),
                (b"content-length", str(len(data)).encode()),
            ],
            "client": ("127.0.0.1", 50000),
            "server": ("nura.test", 80),
        }
        await app(scope, receive, send)
        return answered


async def _house(deployment: Deployment) -> House:
    house = await household(deployment)
    await agree_to_recording(deployment, house.pa, house.profile_id)
    return house


async def _row(deployment: Deployment, upload_id: str) -> ConsultUpload:
    async with deployment.sessions() as session:
        row = await session.get(ConsultUpload, uuid.UUID(upload_id))
        assert row is not None
        return row


# --- a dropped connection ------------------------------------------------------------------------


async def test_a_dropped_connection_mid_visit_resumes_from_where_the_server_got_to(
    deployment: Deployment,
) -> None:
    house = await _house(deployment)
    phone = Phone(house, house.mei)
    opened = await phone.open()
    assert opened["chunks"] == 0 and opened["open"] and not opened["doctor_said_yes"]
    assert opened["max_chunk_bytes"] == MAX_CHUNK_BYTES
    parts = pieces(DATA)
    # The notice and the doctor's answer are in the first chunks; then his yes.
    await phone.send(parts[0] + parts[1])
    assert (await _ok(await phone.yes()))["doctor_said_yes"] is True

    # The connection drops half way through the third chunk: nothing of it is kept.
    await phone.cut_short(2, parts[2])
    where = await _ok(await phone.status())
    assert (where["chunks"], where["received_bytes"], where["open"]) == (2, 20, True)
    assert len(phone.staged()) == 2
    assert "ChunkCutShort" in await refusals(deployment, house.pa, house.profile_id)

    # A chunk the server has, sent again the same because its answer was lost, changes
    # nothing; other bytes under its number, or a number past the next, are refused.
    assert (await _ok(await phone.chunk(1, parts[1])))["chunks"] == 2
    other = await phone.chunk(1, b"not the same")
    assert other.status_code == 409 and other.json() == {"refusal": "NotTheChunkSent"}
    ahead = await phone.chunk(4, parts[4])
    assert ahead.status_code == 409 and ahead.json() == {"refusal": "ChunkOutOfOrder"}

    # Back online: the phone sends from where the server says it got to, and Stops.
    await phone.send(DATA[where["received_bytes"] :], first=where["chunks"])
    kept = await _ok(await phone.finish(), 201)
    recording = kept["recording"]
    assert recording["heard"] is True and recording["duration_s"] == DURATION_S
    assert recording["recorded_by_person_id"] == house.mei["person_id"]
    assert kept["summary"] is not None and kept["summary_refused"] is None

    # Put together in the region into the one recording, and every chunk let go.
    recordings, voices = await _kept(house)
    assert len(recordings) == 1 and len(voices) == 1
    assert await deployment.objects.get(voices[0].storage_key) == DATA
    assert phone.staged() == []
    row = await _row(deployment, phone.upload)
    assert row.recording_id == recordings[0].id and row.finished_at is not None
    done = await _ok(await phone.status())
    assert done["open"] is False
    # Stop sent again, its answer lost: the same recording, nothing kept twice.
    again = await _ok(await phone.finish(), 201)
    assert again["recording"]["recording_id"] == recording["recording_id"]
    assert len((await _kept(house))[0]) == 1


# --- a no -----------------------------------------------------------------------------------------


async def test_a_no_throws_away_every_chunk_already_sent_and_keeps_nothing(
    deployment: Deployment,
) -> None:
    house = await _house(deployment)
    phone = Phone(house, house.mei)
    await phone.open()
    await phone.send(DATA[:30])  # the notice, and the doctor's no, reach the server
    assert len(phone.staged()) == 3

    assert (await phone.discard("no")).status_code == 204
    assert phone.staged() == []
    assert (await _ok(await phone.status()))["open"] is False
    row = await _row(deployment, phone.upload)
    assert row.discarded_because == "no" and row.discarded_at is not None
    for late in (await phone.chunk(3, DATA[30:40]), await phone.yes(), await phone.finish()):
        assert late.status_code == 410 and late.json() == {"refusal": "UploadClosed"}
    assert await _kept(house) == ([], [])

    # The page left before he answered: the same.
    left = Phone(house, house.mei)
    await left.open()
    await left.send(DATA[:10])
    assert (await left.discard("left")).status_code == 204
    assert left.staged() == [] and (await _row(deployment, left.upload)).discarded_because == "left"

    # Stop before the doctor's yes keeps nothing either.
    early = Phone(house, house.mei)
    await early.open()
    await early.send(DATA)
    refused = await early.finish()
    assert refused.status_code == 409 and refused.json() == {"refusal": "NoYesFromTheDoctor"}
    assert await _kept(house) == ([], [])
    # The phone sends the whole instead of this one: thrown away, every chunk with it.
    assert (await early.discard("whole")).status_code == 204
    assert early.staged() == [] and (await _row(deployment, early.upload)).discarded_because == "whole"
    assert (await early.discard("maybe")).status_code == 422


async def test_a_chunk_that_lands_as_it_closes_is_let_go_too(deployment: Deployment) -> None:
    house = await _house(deployment)
    profile = uuid.UUID(house.profile_id)
    # Thrown away; then a chunk that was on its way lands: the phone's second DELETE lets it go.
    no = Phone(house, house.mei)
    await no.open()
    await no.send(DATA[:20])
    assert (await no.discard("no")).status_code == 204
    await deployment.objects.put(chunks.chunk_key(profile, uuid.UUID(no.upload), 2), DATA[20:30])
    assert len(no.staged()) == 1
    assert (await no.discard("no")).status_code == 204
    assert no.staged() == []
    # Put together; then a chunk lands late: the scheduler's next run lets it go.
    kept = Phone(house, house.mei)
    await kept.open()
    await kept.send(DATA)
    await _ok(await kept.yes())
    await _ok(await kept.finish(), 201)
    row = await _row(deployment, kept.upload)
    await deployment.objects.put(chunks.chunk_key(profile, uuid.UUID(kept.upload), row.chunks), b"late")
    assert len(kept.staged()) == 1
    await _ok(await deployment.client.post("/dev/run-triggers", json={"profile_id": house.profile_id}))
    assert kept.staged() == []


async def test_a_store_that_fails_the_sweep_never_costs_the_run_what_it_sent(
    deployment: Deployment, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    house = await _house(deployment)
    phone = Phone(house, house.mei)
    await phone.open()
    await phone.send(DATA[:20])
    clock.step(ANSWER_WITHIN)

    async def refused(key: str) -> None:
        raise ObjectStoreUnavailable("the bucket refused a delete (503)")

    monkeypatch.setattr(deployment.objects, "delete", refused)
    ran = await deployment.client.post("/dev/run-triggers", json={"profile_id": house.profile_id})
    assert ran.status_code == 200, ran.text
    assert len(phone.staged()) == 2 and (await _row(deployment, phone.upload)).discarded_at is None
    monkeypatch.undo()
    await _ok(await deployment.client.post("/dev/run-triggers", json={"profile_id": house.profile_id}))
    assert phone.staged() == []
    assert (await _row(deployment, phone.upload)).discarded_because == "no_answer"


async def test_what_the_phone_could_not_throw_away_the_scheduler_does(
    deployment: Deployment, clock: FrozenClock
) -> None:
    house = await _house(deployment)
    unanswered = Phone(house, house.mei)
    await unanswered.open()
    await unanswered.send(DATA[:20])
    unfinished = Phone(house, house.mei)
    await unfinished.open()
    await unfinished.send(DATA[:20])
    await _ok(await unfinished.yes())

    async def scheduler() -> None:
        await _ok(await deployment.client.post("/dev/run-triggers", json={"profile_id": house.profile_id}))

    # A quarter of an hour with no answer from the doctor: taken as no answer at all. Before
    # the sweep reaches it, it takes nothing more.
    clock.step(ANSWER_WITHIN)
    lapsed = await unanswered.chunk(2, DATA[20:30])
    assert lapsed.status_code == 410 and lapsed.json() == {"refusal": "UploadClosed"}
    await scheduler()
    assert unanswered.staged() == []
    assert (await _row(deployment, unanswered.upload)).discarded_because == "no_answer"
    assert len(unfinished.staged()) == 2  # the doctor said yes to this one: it waits for Stop

    # A visit never finished, long after the longest visit: nothing kept that Stop did not say.
    clock.step(FINISH_WITHIN)
    await scheduler()
    assert unfinished.staged() == []
    assert (await _row(deployment, unfinished.upload)).discarded_because == "unfinished"
    assert await _kept(house) == ([], [])


async def test_closing_his_account_throws_away_every_chunk_already_sent(
    deployment: Deployment,
) -> None:
    """Closing the account (#143) throws away a recording still on its way in, with every
    chunk already sent, even one the doctor said yes to. Nothing more joins it, and a chunk
    that lands as it closes is let go by the scheduler's next run of the closing profile."""
    house = await _house(deployment)
    phone = Phone(house, house.mei)
    await phone.open()
    await phone.send(DATA[:30])
    await _ok(await phone.yes())
    assert len(phone.staged()) == 3

    his = bearer(house.pa["token"])
    base = f"/profiles/{house.profile_id}"
    yes = await _ok(
        await deployment.client.post(
            f"{base}/confirmations",
            json={"subject": "close_account", "language": "en"},
            headers=his,
        ),
        201,
    )
    closed = await deployment.client.post(
        f"{base}/closure",
        json={"confirmation_id": yes["confirmation_id"], "language": "en"},
        headers=his,
    )
    assert closed.status_code == 201, closed.text

    assert phone.staged() == []
    row = await _row(deployment, phone.upload)
    assert row.discarded_because == "closing" and row.discarded_at is not None
    # Nothing more joins it: the profile is closed to every key.
    late = await phone.chunk(3, DATA[30:40])
    assert late.status_code == 403 and late.json() == {"refusal": "AccountClosing"}
    assert (await phone.finish()).json() == {"refusal": "AccountClosing"}

    # A chunk that was on its way lands after the closing: the next run lets it go.
    profile = uuid.UUID(house.profile_id)
    await deployment.objects.put(chunks.chunk_key(profile, uuid.UUID(phone.upload), 3), b"late")
    assert len(phone.staged()) == 1
    await _ok(await deployment.client.post("/dev/run-triggers", json={"profile_id": house.profile_id}))
    assert phone.staged() == []
    assert await _kept(house) == ([], [])


async def test_a_stop_and_the_sweep_never_both_end_one_upload(deployment: Deployment) -> None:
    """The sweep, holding the row as it stood a moment before a Stop landed, cannot throw away
    what the Stop kept, and a second Stop cannot keep it again: an upload is ended in one
    statement that asks it is still open (`chunks._claim`)."""
    house = await _house(deployment)
    phone = Phone(house, house.mei)
    await phone.open()
    await phone.send(DATA)
    await _ok(await phone.yes())
    await _ok(await phone.finish(), 201)
    async with deployment.sessions() as session:
        row = await session.get(ConsultUpload, uuid.UUID(phone.upload))
        assert row is not None and row.recording_id is not None
        # As the sweep read it, before the Stop's answer.
        set_committed_value(row, "finished_at", None)
        set_committed_value(row, "recording_id", None)
        ended = await chunks._claim(
            session, row, discarded_at=utcnow(), discarded_because="no_answer"
        )
        assert not ended and row.discarded_at is None and row.recording_id is not None
        set_committed_value(row, "finished_at", None)
        assert not await chunks._claim(session, row, finished_at=utcnow())
    await _ok(await phone.finish(), 201)
    assert len((await _kept(house))[0]) == 1


# --- the cap --------------------------------------------------------------------------------------


async def test_a_chunk_over_the_cap_gets_a_413_and_nothing_of_it_is_kept(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> None:
    house = await _house(deployment)
    phone = Phone(house, house.mei)
    await phone.open()
    # Declared over the cap: refused before a byte is read.
    over = await phone.chunk(0, WEBM_MAGIC + b"A" * MAX_CHUNK_BYTES)
    assert over.status_code == 413 and over.json() == {"refusal": "ChunkTooLarge"}
    # No length declared: refused as it arrives, at most one network chunk past the cap.
    endless = Endless(WEBM_MAGIC, most=4 * MAX_CHUNK_BYTES)
    sent = await phone.chunk(0, endless)
    assert sent.status_code == 413 and sent.json() == {"refusal": "ChunkTooLarge"}
    assert MAX_CHUNK_BYTES < endless.sent <= MAX_CHUNK_BYTES + CHUNK
    assert phone.staged() == [] and (await _ok(await phone.status()))["chunks"] == 0
    assert "ChunkTooLarge" in await refusals(deployment, house.pa, house.profile_id)

    # A recording is at most so many chunks.
    monkeypatch.setattr(chunks, "MAX_CHUNKS", 1)
    many = await phone.chunk(1, DATA[:10])
    assert many.status_code == 413 and many.json() == {"refusal": "ConsultTooLong"}
    monkeypatch.setattr(chunks, "MAX_CHUNKS", 1000)
    # And the whole stays under a visit's cap, chunk by chunk.
    monkeypatch.setattr(chunks, "MAX_CONSULT_BYTES", 25)
    await phone.send(DATA[:20])
    whole = await phone.chunk(2, DATA[20:30])
    assert whole.status_code == 413 and whole.json() == {"refusal": "ConsultTooLong"}
    assert len(phone.staged()) == 2


# --- the same recording ---------------------------------------------------------------------------


async def test_the_assembled_recording_plays_the_same_clips_as_a_single_upload(
    deployment: Deployment,
) -> None:
    house = await _house(deployment)
    phone = Phone(house, house.mei)
    await phone.open()
    await phone.send(DATA, first=0)
    await _ok(await phone.yes())
    chunked = await _ok(await phone.finish(), 201)

    async for other in _serve(Region.SG):
        single_house = await _house(other)
        single = await _ok(
            await other.client.post(
                f"{single_house.visit}/recording",
                content=DATA,
                params={"duration_s": DURATION_S},
                headers={**bearer(single_house.mei["token"]), "Content-Type": CONTENT_TYPE},
            ),
            201,
        )
        single_clip = await other.client.get(
            single_house.at(f"/artifacts/{single['recording']['artifact_id']}/clip"),
            params={"start": 19.8, "end": 28.9},
            headers=single_house.his,
        )

    def stretches(kept: dict[str, Any]) -> list[tuple[str, float, float]]:
        return [(one["speaker"], one["start_s"], one["end_s"]) for one in kept["recording"]["segments"]]

    def clips(kept: dict[str, Any]) -> list[tuple[str, float | None, float | None]]:
        return [(item["text"], item["clip_start_s"], item["clip_end_s"]) for item in kept["summary"]["items"]]

    assert stretches(chunked) == stretches(single) and len(stretches(chunked)) == 11
    assert clips(chunked) == clips(single) and ("Ask Dr Tan about the new amount of the water pill (frusemide).", 19.8, 28.9) in clips(chunked)
    clip = await house.deployment.client.get(
        house.at(f"/artifacts/{chunked['recording']['artifact_id']}/clip"),
        params={"start": 19.8, "end": 28.9},
        headers=house.his,
    )
    assert clip.status_code == single_clip.status_code == 200
    assert clip.content == single_clip.content == DATA
    assert clip.headers["x-media-fragment"] == single_clip.headers["x-media-fragment"] == "t=19.8,28.9"


# --- who ------------------------------------------------------------------------------------------


async def test_only_the_phone_that_opened_it_sends_to_it_and_only_the_family_hears_it(
    deployment: Deployment,
) -> None:
    house = await _house(deployment)
    phone = Phone(house, house.mei)
    await phone.open()
    await phone.send(DATA)
    # Pa holds every part of his record, but this upload is Mei's phone's.
    his = Phone(house, house.pa)
    his.upload = phone.upload
    for call in (await his.status(), await his.chunk(5, b"x"), await his.yes(), await his.finish()):
        assert call.status_code == 403 and call.json() == {"refusal": "NotYourUpload"}
    await _ok(await phone.yes())
    kept = await _ok(await phone.finish(), 201)

    # Kit, a viewer who reads the visits: he cannot open one, and cannot hear what was kept.
    kit = await register_by_phone(deployment, KIT, "Kit")
    await let_in(deployment, house.pa, house.profile_id, KIT, ["visits"], relationship="son", holder_display_name="Kit")
    await _ok(
        await deployment.client.post(
            house.at("/keys"),
            json={"holder_phone_e164": KIT, "role": "viewer", "scopes": ["visits"]},
            headers=house.his,
        ),
        201,
    )
    viewer = Phone(house, kit)
    refused = await viewer.client.post(
        f"{house.visit}/recording/uploads",
        json={"content_type": CONTENT_TYPE, "started_at": STARTED},
        headers=viewer.headers,
    )
    assert refused.status_code == 403 and refused.json() == {"refusal": "NotTheirsToChangeVisits"}
    heard = await deployment.client.get(
        house.at(f"/artifacts/{kept['recording']['artifact_id']}/clip"),
        params={"start": 19.8, "end": 28.9},
        headers=bearer(kit["token"]),
    )
    assert heard.status_code == 403 and heard.json() == {"refusal": "OnlyTheFamilyHears"}


async def test_nothing_opens_without_the_recording_consent_or_in_a_container_a_phone_does_not_make(
    deployment: Deployment,
) -> None:
    house = await household(deployment)
    phone = Phone(house, house.mei)
    refused = await phone.client.post(
        f"{house.visit}/recording/uploads",
        json={"content_type": CONTENT_TYPE, "started_at": STARTED},
        headers=phone.headers,
    )
    assert refused.status_code == 403 and refused.json() == {"refusal": "ConsentWithheld"}
    await agree_to_recording(deployment, house.pa, house.profile_id)
    wrong = await phone.client.post(
        f"{house.visit}/recording/uploads",
        json={"content_type": "video/mp4", "started_at": STARTED},
        headers=phone.headers,
    )
    assert wrong.status_code == 400 and wrong.json() == {"refusal": "NotAConsultRecording"}
    naive = await phone.client.post(
        f"{house.visit}/recording/uploads",
        json={"content_type": CONTENT_TYPE, "started_at": "2026-09-03T08:00:00"},
        headers=phone.headers,
    )
    assert naive.status_code == 422
    # The first chunk is the recorder's own container, or nothing is kept.
    await phone.open()
    bad = await phone.chunk(0, b"not a webm at all")
    assert bad.status_code == 400 and bad.json() == {"refusal": "NotAConsultRecording"}
    assert phone.staged() == []
    async with deployment.sessions() as session:
        assert len((await session.execute(select(ConsultUpload))).scalars().all()) == 1
    assert timedelta(0) < ANSWER_WITHIN < FINISH_WITHIN
