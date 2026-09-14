"""Episodic memory: storing what came in, and recording what happened.

An artefact is stored once and never changed; the bytes are already in the object store of
the profile's region when this is called, and this writes down where. An event is a moment
— a reading taken, a visit, a message — that may name the artefact it came from.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import utcnow
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import Artifact, ArtifactKind, Event, EventKind, SourceChannel, short_label
from app.memory.working import require_open_episode
from app.regions import Region, guard_region

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class NotADigest(Refusal):
    """The sha256 of an artefact is sixty-four hex characters. This was not one."""


class NoSuchArtifact(Refusal):
    """No artefact by that id on this profile."""


async def store_artifact(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: ArtifactKind,
    storage_key: str,
    content_type: str,
    sha256: str,
    captured_at: datetime,
    source_channel: SourceChannel,
    region: Region,
    now: datetime | None = None,
) -> Artifact:
    """Write down an artefact whose bytes are already at `storage_key` in `region`.

    The region must be the profile's own: health data never leaves it, and a reference to
    bytes held elsewhere would be exactly that.
    """
    guard_region(held_in=region, asked_from=context.region)
    # Keeping anything at all rests on the consent to hold the record (E00-02).
    await require_consent(
        session, context=context, purpose=ConsentPurpose.HOLD_HEALTH_RECORD, scope=Scope.RECORDS,
        now=now,
    )
    digest = sha256.strip().lower()
    if not _DIGEST.match(digest):
        raise NotADigest("sha256 is sixty-four hex characters")
    if not storage_key.strip():
        raise NoSuchArtifact("an artefact needs a storage key")
    return await audited_write(
        session,
        Artifact,
        context,
        Scope.RECORDS,
        now=now,
        kind=kind,
        storage_key=storage_key.strip(),
        content_type=content_type,
        sha256=digest,
        captured_at=captured_at,
        source_channel=source_channel,
        region=region,
        stored_at=now or utcnow(),
    )


async def require_artifact(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    now: datetime | None = None,
) -> Artifact:
    """The artefact by that id on this profile, or a refusal that says no more than that."""
    found = await audited_read(
        session,
        Artifact,
        context,
        Scope.RECORDS,
        where=(Artifact.id == artifact_id,),
        now=now,
    )
    if not found:
        raise NoSuchArtifact(f"no artefact {artifact_id} on profile {context.profile_id}")
    return found[0]


async def record_event(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: EventKind,
    occurred_at: datetime,
    label: str | None = None,
    artifact_id: uuid.UUID | None = None,
    episode_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> Event:
    """Record that something happened, naming the artefact and the episode it belongs to.

    `label` is a name for the moment, one short line. What was said or shown is in the
    artefact, and only there.
    """
    await require_consent(
        session, context=context, purpose=ConsentPurpose.HOLD_HEALTH_RECORD, scope=Scope.RECORDS,
        now=now,
    )
    named = short_label(label) if label is not None else None
    if artifact_id is not None:
        await require_artifact(session, context=context, artifact_id=artifact_id, now=now)
    if episode_id is not None:
        await require_open_episode(session, context=context, episode_id=episode_id, now=now)
    return await audited_write(
        session,
        Event,
        context,
        Scope.RECORDS,
        now=now,
        kind=kind,
        occurred_at=occurred_at,
        label=named,
        artifact_id=artifact_id,
        episode_id=episode_id,
        recorded_at=now or utcnow(),
    )


async def require_event(
    session: AsyncSession,
    *,
    context: KeyContext,
    event_id: uuid.UUID,
    now: datetime | None = None,
) -> Event:
    """The event by that id on this profile, or a refusal."""
    found = await audited_read(
        session, Event, context, Scope.RECORDS, where=(Event.id == event_id,), now=now
    )
    if not found:
        raise NoSuchEvent(f"no event {event_id} on profile {context.profile_id}")
    return found[0]


class NoSuchEvent(Refusal):
    """No event by that id on this profile."""
