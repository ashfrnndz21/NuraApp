"""Working memory: the episode that is going on now.

An episode is opened with a kind and a label and closed when it is over. At most one episode
of a kind is open at a time, so "the current illness" is always one row; events, facts and
appointments name it while it is open. Closing is the one change an episode takes.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import BodySystem, Episode, EpisodeKind, short_label


class EpisodeAlreadyOpen(Refusal):
    """One episode of a kind at a time. Close the one that is open first."""


class EpisodeAlreadyClosed(Refusal):
    """This episode is over; it is not closed twice."""


class NoSuchEpisode(Refusal):
    """No open episode by that id on this profile."""


@audited(Action.READ, Scope.RECORDS, Episode.__tablename__)
async def open_episodes(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: EpisodeKind | None = None,
) -> Sequence[Episode]:
    """What is going on now, oldest first."""
    where: list[ColumnElement[bool]] = [Episode.closed_at.is_(None)]
    if kind is not None:
        where.append(Episode.kind == kind)
    found = await audited_read(session, Episode, context, Scope.RECORDS, where=where)
    return sorted(found, key=lambda episode: as_utc(episode.opened_at))


@audited(Action.WRITE, Scope.RECORDS, Episode.__tablename__)
async def open_episode(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: EpisodeKind,
    label: str,
    opened_at: datetime | None = None,
    body_systems: Iterable[BodySystem] | None = None,
) -> Episode:
    """Start an episode, refused while one of the same kind is open. `body_systems` is
    never worked out here or anywhere else (#175): it is what the person naming the
    episode said it is about, or nothing — the body-systems map glows only on a real tag."""
    # Keeping an episode rests on the consent to hold the record (E00-02).
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.RECORDS,
    )
    named = short_label(label)
    if await open_episodes(session, context=context, kind=kind):
        raise EpisodeAlreadyOpen(f"an episode of kind {kind} is already open")
    return await audited_write(
        session,
        Episode,
        context,
        Scope.RECORDS,
        kind=kind,
        label=named,
        opened_at=opened_at or utcnow(),
        body_systems=sorted({system.value for system in body_systems or ()}),
    )


@audited(Action.READ, Scope.RECORDS, Episode.__tablename__)
async def require_open_episode(
    session: AsyncSession,
    *,
    context: KeyContext,
    episode_id: uuid.UUID,
) -> Episode:
    """The open episode by that id on this profile. Nothing attaches to a closed one."""
    found = await audited_read(
        session,
        Episode,
        context,
        Scope.RECORDS,
        where=(Episode.id == episode_id, Episode.closed_at.is_(None)),
    )
    if not found:
        raise NoSuchEpisode(f"no open episode {episode_id} on profile {context.profile_id}")
    return found[0]


@audited(Action.WRITE, Scope.RECORDS, Episode.__tablename__)
async def close_episode(
    session: AsyncSession,
    *,
    context: KeyContext,
    episode_id: uuid.UUID,
    closed_at: datetime | None = None,
) -> Episode:
    """End an episode. The row stays, so the timeline still shows it."""
    found = await audited_read(
        session, Episode, context, Scope.RECORDS, where=(Episode.id == episode_id,)
    )
    if not found:
        raise NoSuchEpisode(f"no episode {episode_id} on profile {context.profile_id}")
    episode = found[0]
    if episode.closed_at is not None:
        raise EpisodeAlreadyClosed(f"episode {episode_id} closed at {episode.closed_at}")
    episode.closed_at = closed_at or utcnow()
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.RECORDS,
        target=Episode.__tablename__,
        target_id=episode.id,
        rows=1,
    )
    return episode
