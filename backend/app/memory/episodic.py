"""Episodic memory: storing what came in, and recording what happened.

An artefact is stored once and never changed; the bytes are already in the object store of
the profile's region when this is called, and this writes down where; reading it back asks
for the region again, in the query itself. An event is a moment — a reading taken, a visit, a
message — that names the artefact it came from, or says which channel it came in on and what
it was. Neither comes from nowhere.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, Select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.db import utcnow
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.repository import scoped_select
from app.keys.scopes import Scope
from app.memory.models import (
    Artifact,
    ArtifactKind,
    Event,
    EventKind,
    Fact,
    SourceChannel,
    short_label,
)
from app.memory.working import require_open_episode
from app.regions import Region, guard_region

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class NotADigest(Refusal):
    """The sha256 of an artefact is sixty-four hex characters. This was not one."""


class NoSuchArtifact(Refusal):
    """No artefact by that id on this profile."""


class SourceNotNamed(Refusal):
    """An event names its artefact, or says its channel and what it was. This did neither."""


class CameInAnotherWay(Refusal):
    """An event read from an artefact came in the way the artefact did, not some other way."""


def held_here(context: KeyContext) -> ColumnElement[bool]:
    """The artefacts this deployment may serve: the ones whose bytes are in its region.

    Part of every query that returns an artefact, so a row that entered out of band naming
    bytes held elsewhere is never read, by any reader.
    """
    return Artifact.region == context.region


def _artefacts_held_here(context: KeyContext) -> Select[tuple[uuid.UUID]]:
    return (
        scoped_select(Artifact, context, Scope.RECORDS)
        .with_only_columns(Artifact.id)
        .where(held_here(context))
    )


def event_cites_only_what_is_held_here(context: KeyContext) -> ColumnElement[bool]:
    """The events naming no artefact, or one held here. Part of every query returning events."""
    return or_(Event.artifact_id.is_(None), Event.artifact_id.in_(_artefacts_held_here(context)))


def fact_cites_only_what_is_held_here(context: KeyContext) -> ColumnElement[bool]:
    """The facts whose provenance, followed all the way down, is held here.

    A fact names an artefact, or an event, or both; an event names an artefact. This follows
    the chain: the artefact the fact names is held here, and the event it names itself names
    nothing or something held here. Part of every query returning facts, so a cite always
    leads to an artefact that can be read, and nothing resting on bytes held elsewhere is
    served by any reader.
    """
    events_here = (
        scoped_select(Event, context, Scope.RECORDS)
        .with_only_columns(Event.id)
        .where(event_cites_only_what_is_held_here(context))
    )
    return and_(
        or_(Fact.artifact_id.is_(None), Fact.artifact_id.in_(_artefacts_held_here(context))),
        or_(Fact.event_id.is_(None), Fact.event_id.in_(events_here)),
    )


@audited(Action.WRITE, Scope.RECORDS, Artifact.__tablename__)
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
    bytes held elsewhere would be exactly that. The refusal is in the trail like any other.
    """
    guard_region(held_in=region, asked_from=context.region)
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


@audited(Action.READ, Scope.RECORDS, Artifact.__tablename__)
async def require_artifact(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    now: datetime | None = None,
) -> Artifact:
    """The artefact by that id on this profile, in this region, or a refusal saying no more.

    The region is part of the query (`held_here`), not a check after it: a row that entered
    out of band naming bytes held elsewhere is never read. To this deployment such a row is
    not there, and the refusal is written down as that.
    """
    found = await audited_read(
        session,
        Artifact,
        context,
        Scope.RECORDS,
        where=(Artifact.id == artifact_id, held_here(context)),
        now=now,
    )
    if not found:
        raise NoSuchArtifact(f"no artefact {artifact_id} on profile {context.profile_id}")
    return found[0]


@audited(Action.WRITE, Scope.RECORDS, Event.__tablename__)
async def record_event(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: EventKind,
    occurred_at: datetime,
    label: str | None = None,
    artifact_id: uuid.UUID | None = None,
    source_channel: SourceChannel | None = None,
    episode_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> Event:
    """Record that something happened, naming the artefact and the episode it belongs to.

    An event comes from somewhere. With an artefact, the event came in the way the artefact
    did, and `source_channel` may only agree. Without one, `source_channel` and `label` are
    both required: which channel it came in on, and what it was. `label` is a name for the
    moment, one short line. What was said or shown is in the artefact, and only there.
    """
    named = short_label(label) if label is not None else None
    came_in_by = await _where_it_came_from(
        session,
        context=context,
        artifact_id=artifact_id,
        source_channel=source_channel,
        label=named,
        now=now,
    )
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
        source_channel=came_in_by,
        label=named,
        artifact_id=artifact_id,
        episode_id=episode_id,
        recorded_at=now or utcnow(),
    )


async def _where_it_came_from(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID | None,
    source_channel: SourceChannel | None,
    label: str | None,
    now: datetime | None,
) -> SourceChannel:
    """The channel an event came in on: the artefact's, or the one given beside a label."""
    if artifact_id is None:
        if source_channel is None or label is None:
            raise SourceNotNamed("an event names its artefact, or says its channel and label")
        return source_channel
    artifact = await require_artifact(session, context=context, artifact_id=artifact_id, now=now)
    if source_channel is not None and source_channel is not artifact.source_channel:
        raise CameInAnotherWay(
            f"the artefact came in by {artifact.source_channel}, not {source_channel}"
        )
    return artifact.source_channel


@audited(Action.READ, Scope.RECORDS, Event.__tablename__)
async def require_event(
    session: AsyncSession,
    *,
    context: KeyContext,
    event_id: uuid.UUID,
    now: datetime | None = None,
) -> Event:
    """The event by that id on this profile, citing nothing held elsewhere, or a refusal."""
    found = await audited_read(
        session,
        Event,
        context,
        Scope.RECORDS,
        where=(Event.id == event_id, event_cites_only_what_is_held_here(context)),
        now=now,
    )
    if not found:
        raise NoSuchEvent(f"no event {event_id} on profile {context.profile_id}")
    return found[0]


class NoSuchEvent(Refusal):
    """No event by that id on this profile."""
