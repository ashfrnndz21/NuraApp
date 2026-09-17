"""Photos the family shares in the thread (E12-02), and the story cards made of them (E21-05).

A photo is shared with a line of words, the way one is on WhatsApp: the words are a message
of the thread (`post_message`), and the photo hangs off it (`ThreadPhoto`). The bytes go to
the region's object store under a content-addressed key and one artefact names them, written
under the family scope (`app.memory.episodic.store_family_photo`): the family's, never one of
his papers, and nothing is read off it. A photo posted in the family's WhatsApp group lands
here the same way (#149, `app.channels.whatsapp.inbound._group_photo`), its `source_channel`
saying it came from there — still never on his feed by that alone (`on_his_feed=False`; only
the sharer's own yes does that, and nobody in the group was asked it).

The one who shares it says, then and there, whether it may also be one of his story cards
(`on_his_feed`) — their yes, not anyone else's — and may take it back later
(`take_back_photo`), which only they can do. From then on it is not shown to anyone: not in
the thread, not on his feed, not by its bytes. Everything here is under the family scope: a
key that does not read the family thread reads none of it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import utcnow
from app.errors import Refusal
from app.family.models import ThreadMessage, ThreadPhoto
from app.family.thread import post_message
from app.ingestion.objects import NoSuchObject, ObjectStore, check_key, sha256_of
from app.ingestion.photos import MAX_PHOTO_BYTES, PHOTO_CONTENT_TYPES, PhotoTooLarge
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import require_artifact_under, store_family_photo
from app.memory.models import SourceChannel
from app.regions import guard_region

PHOTO_TARGET = ThreadPhoto.__tablename__


class NotAPhoto(Refusal):
    """The bytes offered were empty, or of a kind that is not an image."""


class NoSuchPhoto(Refusal):
    """No photo by that id in this family's thread that is still shared."""


class NotTheirsToTakeBack(Refusal):
    """A shared photo is taken back by the one who shared it, and by nobody else."""


def family_photo_key(profile_id: uuid.UUID, digest: str) -> str:
    return check_key(f"family-photos/{profile_id}/{digest}")


def check_photo(data: bytes, content_type: str) -> str:
    kind = content_type.strip().lower().split(";", 1)[0].strip()
    if kind not in PHOTO_CONTENT_TYPES:
        raise NotAPhoto(f"{content_type} is not an image")
    if not data:
        raise NotAPhoto("the photo was empty")
    if len(data) > MAX_PHOTO_BYTES:
        # The same cap as any photo he keeps, read against as it arrives (`UploadCaps`).
        raise PhotoTooLarge(f"a photo is at most {MAX_PHOTO_BYTES} bytes")
    return kind


@audited(Action.WRITE, Scope.FAMILY, PHOTO_TARGET)
async def share_photo(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    data: bytes,
    content_type: str,
    caption: str,
    on_his_feed: bool,
    source_channel: SourceChannel = SourceChannel.APP,
) -> tuple[ThreadMessage, ThreadPhoto]:
    """Share one photo with the family, with the words it comes with, and the sharer's own
    yes or no to its being one of his story cards. The row first, then the bytes: a refusal
    leaves nothing in the store. `source_channel` is the app by default; a photo mirrored in
    from the family's WhatsApp group (#149) is WhatsApp's, for the same provenance every
    artefact carries."""
    guard_region(held_in=store.region, asked_from=context.region)
    kind = check_photo(data, content_type)
    message = await post_message(session, context=context, text=caption)
    digest = sha256_of(data)
    key = family_photo_key(context.profile_id, digest)
    artifact = await store_family_photo(
        session,
        context=context,
        storage_key=key,
        content_type=kind,
        sha256=digest,
        captured_at=utcnow(),
        region=store.region,
        source_channel=source_channel,
    )
    await store.put(key, data)
    photo = await audited_write(
        session,
        ThreadPhoto,
        context,
        Scope.FAMILY,
        message_id=message.id,
        artifact_id=artifact.id,
        author_person_id=context.person_id,
        on_his_feed=on_his_feed,
        posted_at=utcnow(),
    )
    return message, photo


async def _shared(session: AsyncSession, context: KeyContext, photo_id: uuid.UUID) -> ThreadPhoto:
    found = await audited_read(
        session,
        ThreadPhoto,
        context,
        Scope.FAMILY,
        where=(ThreadPhoto.id == photo_id, ThreadPhoto.withdrawn_at.is_(None)),
    )
    if not found:
        raise NoSuchPhoto(f"no shared photo {photo_id} on profile {context.profile_id}")
    return found[0]


@audited(Action.WRITE, Scope.FAMILY, PHOTO_TARGET)
async def take_back_photo(
    session: AsyncSession, *, context: KeyContext, photo_id: uuid.UUID
) -> ThreadPhoto:
    """The sharer takes a photo back: from now it is shown to nobody, anywhere. Only the one
    who shared it may; anyone else is refused by name, on the trail."""
    photo = await _shared(session, context, photo_id)
    if photo.author_person_id != context.person_id:
        raise NotTheirsToTakeBack("a photo is taken back by the one who shared it")
    photo.withdrawn_at = utcnow()
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=PHOTO_TARGET,
        target_id=photo.id,
        rows=1,
    )
    return photo


@audited(Action.READ, Scope.FAMILY, PHOTO_TARGET)
async def photos_on(
    session: AsyncSession, *, context: KeyContext, message_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, ThreadPhoto]:
    """The photos still shared on these thread messages, by message."""
    if not message_ids:
        return {}
    found = await audited_read(
        session,
        ThreadPhoto,
        context,
        Scope.FAMILY,
        where=(
            ThreadPhoto.message_id.in_(sorted(set(message_ids), key=str)),
            ThreadPhoto.withdrawn_at.is_(None),
        ),
    )
    return {photo.message_id: photo for photo in found}


@audited(Action.READ, Scope.FAMILY, PHOTO_TARGET)
async def photos_for_his_feed(session: AsyncSession, *, context: KeyContext) -> list[ThreadPhoto]:
    """The photos the family shared with a yes to his story, still shared, oldest first."""
    found = await audited_read(
        session,
        ThreadPhoto,
        context,
        Scope.FAMILY,
        where=(ThreadPhoto.on_his_feed.is_(True), ThreadPhoto.withdrawn_at.is_(None)),
        order_by=(ThreadPhoto.posted_at.asc(),),
    )
    return list(found)


@audited(Action.READ, Scope.FAMILY, PHOTO_TARGET)
async def taken_back(
    session: AsyncSession, *, context: KeyContext, photo_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Of these photos, the ones their sharer has taken back: ids only."""
    if not photo_ids:
        return set()
    found = await audited_read(
        session,
        ThreadPhoto,
        context,
        Scope.FAMILY,
        where=(
            ThreadPhoto.id.in_(sorted(set(photo_ids), key=str)),
            ThreadPhoto.withdrawn_at.is_not(None),
        ),
    )
    return {photo.id for photo in found}


@audited(Action.READ, Scope.FAMILY, PHOTO_TARGET)
async def photo_content(
    session: AsyncSession, *, context: KeyContext, store: ObjectStore, photo_id: uuid.UUID
) -> tuple[bytes, str]:
    """The bytes of one photo still shared, and its content type, read through the family's
    door (`require_artifact_under`) from the region's store."""
    guard_region(held_in=store.region, asked_from=context.region)
    photo = await _shared(session, context, photo_id)
    artifact = await require_artifact_under(
        session, context=context, artifact_id=photo.artifact_id, scope=Scope.FAMILY
    )
    data = await store.get(artifact.storage_key)
    if sha256_of(data) != artifact.sha256:
        raise NoSuchObject("the bytes under that key are not the photo")
    return data, artifact.content_type


__all__ = [
    "MAX_PHOTO_BYTES",
    "NoSuchPhoto",
    "NotAPhoto",
    "NotTheirsToTakeBack",
    "photo_content",
    "photos_for_his_feed",
    "photos_on",
    "share_photo",
    "take_back_photo",
    "taken_back",
]
