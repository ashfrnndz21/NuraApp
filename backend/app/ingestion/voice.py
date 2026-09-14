"""Storing what a person said: a voice note, or the words he typed, as an artefact.

The bytes go to the region's object store and one Artifact row names them — kind VOICE for a
recording, kind MESSAGE for typed words — exactly as a photo does (`app.ingestion.photos`).
The words themselves live only in the store: a fact about how he feels is a code that names
the artefact (`app.safety.symptoms`), and "logged in his words" is kept true by the bytes.
Keeping them rests on the agreement to hold the record, checked before a byte lands.

A voice note about how he feels is his own words on his own record: it is not a recording
of a consultation, so it is held under `HOLD_HEALTH_RECORD` and does not ask for the
`RECORDING` consent that a consult recording (E05) does.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited
from app.audit.models import Action
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.errors import Refusal
from app.ingestion.objects import ObjectStore, sha256_of
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import store_artifact
from app.memory.models import Artifact, ArtifactKind, SourceChannel
from app.regions import guard_region
from app.safety.transcribe import check_voice_note

MAX_WORDS_BYTES = 2000
"""Typed words about how he feels: a few sentences, not a document."""

WORDS_CONTENT_TYPE = "text/plain; charset=utf-8"


class NoWords(Refusal):
    """The words offered were empty, or far more than a person types about how he feels."""


def voice_key(profile_id: uuid.UUID, digest: str) -> str:
    return f"voice/{profile_id}/{digest}"


def words_key(profile_id: uuid.UUID, digest: str) -> str:
    return f"words/{profile_id}/{digest}"


@audited(Action.WRITE, Scope.RECORDS, Artifact.__tablename__)
async def store_voice(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    data: bytes,
    content_type: str,
    captured_at: datetime,
    source_channel: SourceChannel,
) -> Artifact:
    """Keep a voice note: bytes under a content-addressed key, one VOICE artefact naming them."""
    guard_region(held_in=store.region, asked_from=context.region)
    kind = check_voice_note(data, content_type)
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.RECORDS,
    )
    digest = sha256_of(data)
    key = voice_key(context.profile_id, digest)
    await store.put(key, data)
    return await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.VOICE,
        storage_key=key,
        content_type=kind,
        sha256=digest,
        captured_at=captured_at,
        source_channel=source_channel,
        region=store.region,
    )


@audited(Action.WRITE, Scope.RECORDS, Artifact.__tablename__)
async def store_words(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    text: str,
    captured_at: datetime,
    source_channel: SourceChannel,
) -> Artifact:
    """Keep the words a person typed: the text as bytes under a content-addressed key, one
    MESSAGE artefact naming them. No row holds the words."""
    guard_region(held_in=store.region, asked_from=context.region)
    said = text.strip()
    data = said.encode("utf-8")
    if not said:
        raise NoWords("no words were typed")
    if len(data) > MAX_WORDS_BYTES:
        raise NoWords(f"the words are at most {MAX_WORDS_BYTES} bytes")
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.RECORDS,
    )
    digest = sha256_of(data)
    key = words_key(context.profile_id, digest)
    await store.put(key, data)
    return await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.MESSAGE,
        storage_key=key,
        content_type=WORDS_CONTENT_TYPE,
        sha256=digest,
        captured_at=captured_at,
        source_channel=source_channel,
        region=store.region,
    )
