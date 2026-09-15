"""#136: the WhatsApp webhook reads its body against a cap, as it arrives.

The webhook used to read its whole body before checking the signature. Now it reads through
`read_capped` (`app.channels.api.uploads`): a body declared past the cap is refused before a
byte is read, one that runs past it is refused at the first chunk over, both with a 413 and
before anything is parsed; the signature is checked over exactly the bytes read. A signed body
under the cap, sent in pieces, is handled exactly as before. A voice note's media is fetched
from the provider rather than uploaded, so that download is capped too.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp import inbound
from app.channels.whatsapp.api import WEBHOOK_BYTES
from app.channels.whatsapp.provider import FixtureProvider, MediaTooLarge
from app.ingestion.models import EventNote
from tests.conftest import WHATSAPP_FIXTURES, WHATSAPP_SECRET, Deployment
from tests.test_whatsapp_api import MEI, _cloud_api_text, _pa_on_whatsapp
from tests.whatsapp_support import PA, family

CHUNK = 64 * 1024
JSON = {"content-type": "application/json"}


class Endless:
    """A chunked body with no length that counts every byte the server takes from it, and
    gives up at `most` so a failing test ends."""

    def __init__(self, most: int) -> None:
        self.most, self.sent = most, 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        chunk = b'{"entry": ["'
        while self.sent < self.most:
            self.sent += len(chunk)
            yield chunk
            chunk = b"A" * CHUNK


async def _in_pieces(data: bytes, size: int) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


async def test_an_endless_body_is_refused_at_the_cap_before_it_is_parsed(
    deployment: Deployment,
) -> None:
    body = Endless(most=4 * WEBHOOK_BYTES)
    refused = await deployment.client.post(
        "/whatsapp/webhook",
        content=body,
        headers={**JSON, "X-Hub-Signature-256": "sha256=00"},
    )
    assert refused.status_code == 413 and refused.json() == {"refusal": "WebhookTooLarge"}
    # It stopped reading at the cap: at most one chunk past it, never the four times on offer.
    assert WEBHOOK_BYTES < body.sent <= WEBHOOK_BYTES + CHUNK
    assert deployment.whatsapp.sent == []


async def test_a_body_declared_past_the_cap_is_refused_before_a_byte_is_read(
    deployment: Deployment,
) -> None:
    refused = await deployment.client.post(
        "/whatsapp/webhook",
        content=b"{}",
        headers={**JSON, "Content-Length": str(WEBHOOK_BYTES + 1)},
    )
    assert refused.status_code == 413 and refused.json() == {"refusal": "WebhookTooLarge"}


async def test_a_signed_body_under_the_cap_in_pieces_is_handled_exactly_as_before(
    deployment: Deployment,
) -> None:
    await _pa_on_whatsapp(deployment)
    body = json.dumps(_cloud_api_text(MEI, "BP 150/90 this morning")).encode()
    forged = await deployment.client.post(
        "/whatsapp/webhook",
        content=_in_pieces(body, 17),
        headers={**JSON, "X-Hub-Signature-256": deployment.whatsapp.sign(body + b" ")},
    )
    assert forged.status_code == 403 and forged.json() == {"refusal": "NotAWebhook"}
    assert deployment.whatsapp.sent == []

    signed = await deployment.client.post(
        "/whatsapp/webhook",
        content=_in_pieces(body, 17),
        headers={**JSON, "X-Hub-Signature-256": deployment.whatsapp.sign(body)},
    )
    assert signed.status_code == 200 and signed.json() == {"handled": 1}
    [reply] = deployment.whatsapp.sent
    assert reply.to_e164 == MEI and reply.text.startswith("Did I get this right?")


async def test_a_signed_body_that_is_not_a_delivery_is_refused(deployment: Deployment) -> None:
    for body in (b"not json", b"[1, 2, 3]"):
        refused = await deployment.client.post(
            "/whatsapp/webhook",
            content=body,
            headers={**JSON, "X-Hub-Signature-256": deployment.whatsapp.sign(body)},
        )
        assert refused.status_code == 403 and refused.json() == {"refusal": "NotAWebhook"}


async def test_a_voice_notes_download_is_capped_and_past_it_nothing_is_heard_or_kept(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FixtureProvider(secret=WHATSAPP_SECRET, fixtures=WHATSAPP_FIXTURES)
    with pytest.raises(MediaTooLarge):
        await provider.fetch_media("pa-voice-market", max_bytes=10)
    assert (await provider.fetch_media("pa-voice-market", max_bytes=1024)).data

    home = await family(sg, tmp_path)
    monkeypatch.setattr(inbound, "VOICE_DOWNLOAD_BYTES", 10)
    handled = await home.inbound(sg, PA, media_id="pa-voice-market", content_type="audio/ogg")
    assert handled.outcome != "voice_note" and handled.note_id is None
    assert not list(
        await sg.scalars(select(EventNote).where(EventNote.profile_id == home.profile.id))
    )
