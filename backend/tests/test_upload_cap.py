"""Every upload is read against its cap as it arrives, never after (#133).

A body that does not say how long it is — chunked, no Content-Length — used to be read whole
before its size was checked. Each test here sends such a body and counts the bytes the server
took from it: over the cap, the server stops reading at the cap and answers the route's 413,
and nothing of the upload is kept; under it, what is stored is exactly what was sent.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import AsyncIterator
from typing import Any, get_args

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.channels.api import API_PREFIX
from app.channels.api import visits as visits_routes
from app.channels.api.refusals import status_of
from app.channels.api.uploads import cap_for
from app.ingestion.models import ConsultRecording
from app.memory.models import Artifact, ArtifactKind
from tests.api import bearer, own_profile, register_by_phone
from tests.capture_support import agree_to_recording, photo, refusals
from tests.conftest import Deployment
from tests.consult_audio import CONSULT, CONTENT_TYPE, DURATION_S, placeholder_consult
from tests.paper import CLINIC_SLIP
from tests.test_visit_day import household

PA = "+6591330001"
CHUNK = 64 * 1024
PREFIXES = ("", API_PREFIX)
JSON = {"Content-Type": "application/json"}
HEAD = b'{"content_type": "image/png", "captured_at": "2026-09-14T00:00:00Z", "data": "'


class Endless:
    """A chunked body with no length, which counts every byte the server takes from it and
    gives up at `most` so a failing test ends."""

    def __init__(self, head: bytes, most: int) -> None:
        self.head, self.most, self.sent = head, most, 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        chunk = self.head
        while self.sent < self.most:
            self.sent += len(chunk)
            yield chunk
            chunk = b"A" * CHUNK


async def _in_pieces(data: bytes, size: int) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


async def _pa(deployment: Deployment) -> tuple[dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, "Pa")
    return bearer(pa["token"]), await own_profile(deployment, pa, language="en")


async def _artifacts(deployment: Deployment) -> list[Artifact]:
    async with deployment.sessions() as session:
        return list((await session.execute(select(Artifact))).scalars())


# --- over the cap ------------------------------------------------------------------------------


@pytest.mark.parametrize("prefix", PREFIXES)
async def test_a_chunked_photo_over_the_cap_is_refused_before_it_is_held(
    deployment: Deployment, prefix: str
) -> None:
    his, profile_id = await _pa(deployment)
    path = f"{prefix}/profiles/{profile_id}/photos"
    cap = cap_for("POST", path, PREFIXES)
    assert cap is not None
    before = await _artifacts(deployment)
    body = Endless(HEAD, most=4 * cap.limit)
    refused = await deployment.client.post(path, content=body, headers={**his, **JSON})
    assert refused.status_code == 413 and refused.json() == {"refusal": "PhotoTooLarge"}
    # It stopped at the cap, at most one chunk past it, never the four times on offer.
    assert cap.limit < body.sent <= cap.limit + CHUNK
    assert await _artifacts(deployment) == before


async def test_a_body_declared_over_the_cap_is_refused_before_a_byte_is_read(
    deployment: Deployment,
) -> None:
    his, profile_id = await _pa(deployment)
    path = f"/profiles/{profile_id}/imports"
    cap = cap_for("POST", path)
    assert cap is not None
    body = Endless(HEAD, most=CHUNK)
    refused = await deployment.client.post(
        path, content=body, headers={**his, **JSON, "Content-Length": str(cap.limit + 1)}
    )
    assert refused.status_code == 413 and refused.json() == {"refusal": "PdfTooLarge"}
    assert body.sent == 0


async def test_a_chunked_recording_over_the_cap_is_refused_on_the_trail_and_nothing_kept(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> None:
    house = await household(deployment)
    await agree_to_recording(deployment, house.pa, house.profile_id)
    cap = 256 * 1024
    monkeypatch.setattr(visits_routes, "MAX_CONSULT_BYTES", cap)
    body = Endless(placeholder_consult(CONSULT), most=64 * 1024 * 1024)
    refused = await deployment.client.post(
        f"{house.visit}/recording",
        content=body,
        params={"duration_s": DURATION_S},
        headers={**bearer(house.pa["token"]), "Content-Type": CONTENT_TYPE},
    )
    assert refused.status_code == 413 and refused.json() == {"refusal": "ConsultTooLong"}
    assert cap < body.sent <= cap + CHUNK
    async with deployment.sessions() as session:
        assert (await session.execute(select(ConsultRecording))).scalars().all() == []
    assert [a for a in await _artifacts(deployment) if a.kind is ArtifactKind.VOICE] == []
    assert "ConsultTooLong" in await refusals(deployment, house.pa, house.profile_id)


# --- under the cap -----------------------------------------------------------------------------


async def test_a_chunked_photo_under_the_cap_is_stored_exactly(deployment: Deployment) -> None:
    his, profile_id = await _pa(deployment)
    sent: dict[str, Any] = photo(CLINIC_SLIP, hint="clinic_slip")
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos",
        content=_in_pieces(json.dumps(sent).encode(), 1000),
        headers={**his, **JSON},
    )
    assert posted.status_code == 201, posted.text
    (kept,) = [a for a in await _artifacts(deployment) if str(a.id) == posted.json()["artifact_id"]]
    assert await deployment.objects.get(kept.storage_key) == base64.b64decode(sent["data"])


async def test_a_chunked_recording_under_the_cap_is_stored_exactly(deployment: Deployment) -> None:
    house = await household(deployment)
    await agree_to_recording(deployment, house.pa, house.profile_id)
    data = placeholder_consult(CONSULT)
    posted = await deployment.client.post(
        f"{house.visit}/recording",
        content=_in_pieces(data, 7),
        params={"duration_s": DURATION_S},
        headers={**bearer(house.pa["token"]), "Content-Type": CONTENT_TYPE},
    )
    assert posted.status_code == 201, posted.text
    (voice,) = [a for a in await _artifacts(deployment) if a.kind is ArtifactKind.VOICE]
    assert await deployment.objects.get(voice.storage_key) == data


# --- every upload route ------------------------------------------------------------------------


def test_every_route_that_takes_bytes_in_json_is_capped_with_a_413(deployment: Deployment) -> None:
    """A route whose body carries bytes (a `data`, `audio` or `ics` field) must have a line in
    `JSON_UPLOADS`, under both mounts, answering with a refusal that is a 413."""
    app = deployment.client._transport.app  # type: ignore[attr-defined]
    found = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.body_field is None:
            continue
        # A body may be one of two models (a paper is a photo, or a card to attach).
        kinds = get_args(route.body_field.type_) or (route.body_field.type_,)
        fields = {name for kind in kinds for name in getattr(kind, "model_fields", {})}
        if not {"data", "audio", "ics"} & fields:
            continue
        sample = re.sub(r"\{[^}]+\}", "x", route.path)
        for method in route.methods:
            cap = cap_for(method, sample, PREFIXES)
            assert cap is not None, f"{method} {route.path} takes bytes and has no cap"
            assert status_of(cap.refused()) == 413, route.path
            found.append(sample)
    # Photos, screens, papers, imports, notes, documents, the two voices, transcripts, calendars,
    # and a photo shared with the family (E12-02, E21-05).
    assert len({re.sub(rf"^{API_PREFIX}", "", p) for p in found}) == 11
