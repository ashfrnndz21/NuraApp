"""Storing a photo: bytes to the region's object store, one Artifact row naming them.

The store must be the profile's region's — checked before a byte is written, and again by
`store_artifact` when the row is written. Keeping the bytes rests on the agreement to hold
the record, so that is checked before they are written too: a photo of a page is health
data the moment it lands, referenced or not.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited
from app.audit.models import Action
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.errors import Refusal
from app.ingestion.objects import ObjectStore, photo_key, sha256_of
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import store_artifact
from app.memory.models import Artifact, ArtifactKind, SourceChannel
from app.regions import guard_region

PHOTO_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/heic", "image/webp"})
"""What a photo may be. A PDF is a different kind of artefact with its own story (E02)."""

MAX_PHOTO_BYTES = 10 * 1024 * 1024
"""Ten megabytes: a phone photo of a page, with room; not a video, not an archive."""


class NotAPhoto(Refusal):
    """The bytes offered as a photo were empty, or of a kind that is not a photo."""


class PhotoTooLarge(Refusal):
    """A photo of a page is not this big."""


@audited(Action.WRITE, Scope.RECORDS, Artifact.__tablename__)
async def store_photo(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    data: bytes,
    content_type: str,
    captured_at: datetime,
    source_channel: SourceChannel,
) -> Artifact:
    """Keep a photo: bytes in the region's store under a content-addressed key, and the
    Artifact row that names them by key and digest. Nothing of the page goes in the row."""
    guard_region(held_in=store.region, asked_from=context.region)
    kind = content_type.strip().lower()
    if kind not in PHOTO_CONTENT_TYPES:
        raise NotAPhoto(f"{content_type} is not a photo")
    if not data:
        raise NotAPhoto("the photo was empty")
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoTooLarge(f"a photo is at most {MAX_PHOTO_BYTES} bytes")
    # Before any byte lands: keeping it rests on the agreement to hold the record. The row
    # checks the same consent again on its way in; a refusal here leaves nothing behind.
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.RECORDS,
    )
    digest = sha256_of(data)
    key = photo_key(context.profile_id, digest)
    await store.put(key, data)
    return await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=key,
        content_type=kind,
        sha256=digest,
        captured_at=captured_at,
        source_channel=source_channel,
        region=store.region,
    )
