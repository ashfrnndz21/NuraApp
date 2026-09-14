"""Storing what a person said: a voice note, or the words he typed, as an artefact.

The bytes go to the region's object store and one Artifact row names them — kind VOICE for a
recording, kind MESSAGE for typed words — exactly as a photo does (`app.ingestion.photos`).
The words themselves live only in the store: a fact about how he feels is a code that names
the artefact (`app.safety.symptoms`), and "logged in his words" is kept true by the bytes.
Keeping them rests on the agreement to hold the record, checked before a byte lands.

A voice note is the sender's own words — his, or his chief's or caregiver's about him — kept
like typed text on the consent to hold the record: `store_voice` declares it
`Recording.OWN_NOTE` (ADR 0003). The RECORDING consent is for recordings of other people's
voices, a consult, and nothing here makes one. The artefact row is written before the bytes,
so a refusal at the store leaves nothing in the object store.
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
from app.memory.models import Artifact, ArtifactKind, Recording, SourceChannel
from app.regions import guard_region

MAX_WORDS_BYTES = 2000
"""Typed words about how he feels: a few sentences, not a document."""

WORDS_CONTENT_TYPE = "text/plain; charset=utf-8"


class NoWords(Refusal):
    """The words offered were empty, or far more than a person types about how he feels."""


VOICE_CONTENT_TYPES = frozenset(
    {"audio/m4a", "audio/mp4", "audio/aac", "audio/mpeg", "audio/wav", "audio/webm", "audio/ogg"}
)
"""What a voice note may be. The app records AAC in an m4a; WhatsApp sends ogg."""

MAX_VOICE_BYTES = 5 * 1024 * 1024
"""Five megabytes: a minute of speech with room; not a recording of a whole visit (E05)."""


class NotAVoiceNote(Refusal):
    """The bytes offered as a voice note were empty, or of a kind that is not one."""


class VoiceNoteTooLong(Refusal):
    """A voice note about how he feels is not this big."""




def check_voice_note(data: bytes, content_type: str) -> str:
    """The content type, lower-cased, or a refusal: empty bytes, too many, or not audio."""
    kind = content_type.strip().lower().split(";", 1)[0]
    if kind not in VOICE_CONTENT_TYPES:
        raise NotAVoiceNote(f"{content_type} is not a voice note")
    if not data:
        raise NotAVoiceNote("the voice note was empty")
    if len(data) > MAX_VOICE_BYTES:
        raise VoiceNoteTooLong(f"a voice note is at most {MAX_VOICE_BYTES} bytes")
    return kind


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
    artifact = await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.VOICE,
        recording=Recording.OWN_NOTE,
        storage_key=key,
        content_type=kind,
        sha256=digest,
        captured_at=captured_at,
        source_channel=source_channel,
        region=store.region,
    )
    await store.put(key, data)
    return artifact


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
    artifact = await store_artifact(
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
    await store.put(key, data)
    return artifact
