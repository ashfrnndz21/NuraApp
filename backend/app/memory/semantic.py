"""Semantic memory: facts with provenance and confidence, immutable with supersession.

Nothing infers without provenance. A fact is asserted from an artefact or an event on this
profile — never from nothing — with a confidence and a state, for a window of time. When it
turns out to be wrong, or a person confirms it, a new fact supersedes it: the old row stays,
marked with when it stopped being current, and the new one names it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import scope_for_subject
from app.memory.episodic import NoSuchArtifact, NoSuchEvent, require_artifact, require_event
from app.memory.models import ConfidenceState, Fact
from app.memory.working import require_open_episode


class NoProvenance(Refusal):
    """A fact says where it came from. This one named no artefact and no event."""


class NoSuchProvenance(Refusal):
    """The artefact or event a fact names must be on this profile. This one was not."""


class NotAConfidence(Refusal):
    """Confidence is a number from nought to one."""


class EmptyWindow(Refusal):
    """A fact cannot stop holding before it starts."""


class NoSuchFact(Refusal):
    """No fact by that id on this profile."""


class AlreadySuperseded(Refusal):
    """This fact has already been replaced. Supersede the one that replaced it."""


async def _check_provenance(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID | None,
    event_id: uuid.UUID | None,
    now: datetime | None,
) -> None:
    if artifact_id is None and event_id is None:
        raise NoProvenance("a fact names the artefact or the event it came from")
    try:
        if artifact_id is not None:
            await require_artifact(session, context=context, artifact_id=artifact_id, now=now)
        if event_id is not None:
            await require_event(session, context=context, event_id=event_id, now=now)
    except (NoSuchArtifact, NoSuchEvent) as missing:
        raise NoSuchProvenance(str(missing)) from missing


def _check_confidence(confidence: float) -> float:
    if not 0.0 <= confidence <= 1.0:
        raise NotAConfidence("confidence is a number from nought to one")
    return float(confidence)


def _check_window(valid_from: datetime, valid_to: datetime | None) -> None:
    if valid_to is not None and valid_to <= valid_from:
        raise EmptyWindow("valid_to must come after valid_from")


async def assert_fact(
    session: AsyncSession,
    *,
    context: KeyContext,
    subject: str,
    attribute: str,
    value: Any,
    confidence: float,
    unit: str | None = None,
    confidence_state: ConfidenceState = ConfidenceState.EXTRACTED,
    artifact_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    episode_id: uuid.UUID | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    supersedes_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> Fact:
    """Assert a fact about the profile from an artefact or an event on it.

    `valid_from` defaults to now; `valid_to` of None means it holds until superseded.
    """
    moment = now or utcnow()
    starts = valid_from or moment
    _check_window(starts, valid_to)
    sure = _check_confidence(confidence)
    await _check_provenance(
        session, context=context, artifact_id=artifact_id, event_id=event_id, now=now
    )
    if episode_id is not None:
        await require_open_episode(session, context=context, episode_id=episode_id, now=now)
    return await audited_write(
        session,
        Fact,
        context,
        scope_for_subject(subject),
        now=now,
        subject=subject,
        attribute=attribute,
        value=value,
        unit=unit,
        confidence=sure,
        confidence_state=confidence_state,
        artifact_id=artifact_id,
        event_id=event_id,
        episode_id=episode_id,
        valid_from=starts,
        valid_to=valid_to,
        asserted_at=moment,
        supersedes_id=supersedes_id,
    )


async def supersede_fact(
    session: AsyncSession,
    *,
    context: KeyContext,
    fact_id: uuid.UUID,
    value: Any,
    confidence: float,
    unit: str | None = None,
    confidence_state: ConfidenceState = ConfidenceState.EXTRACTED,
    artifact_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    now: datetime | None = None,
) -> Fact:
    """Replace a fact with a new one that names it. The old row stays.

    Subject and attribute are the old fact's: a supersession says the same thing better, it
    does not say something else. Provenance and unit are carried over unless new ones are
    given, so confirming a reading still links to the photo it was read from.
    """
    moment = now or utcnow()
    # The scope is the fact's own subject's, so the row is looked at first to learn it. The
    # audited read below is the one that checks the key and writes the line.
    row = await session.get(Fact, fact_id)
    if row is None or row.profile_id != context.profile_id:
        raise NoSuchFact(f"no fact {fact_id} on profile {context.profile_id}")
    found = await audited_read(
        session,
        Fact,
        context,
        scope_for_subject(row.subject),
        where=(Fact.id == fact_id,),
        now=now,
    )
    old = found[0]
    if old.superseded_at is not None:
        raise AlreadySuperseded(f"fact {fact_id} was superseded at {old.superseded_at}")

    carried = artifact_id is None and event_id is None
    new = await assert_fact(
        session,
        context=context,
        subject=old.subject,
        attribute=old.attribute,
        value=value,
        unit=unit if unit is not None else old.unit,
        confidence=confidence,
        confidence_state=confidence_state,
        artifact_id=old.artifact_id if carried else artifact_id,
        event_id=old.event_id if carried else event_id,
        episode_id=old.episode_id,
        valid_from=valid_from,
        valid_to=valid_to,
        supersedes_id=old.id,
        now=now,
    )
    old.superseded_at = moment
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=scope_for_subject(old.subject),
        target=Fact.__tablename__,
        target_id=old.id,
        rows=1,
        now=now,
    )
    return new


async def current_facts(
    session: AsyncSession,
    *,
    context: KeyContext,
    subject: str | None = None,
    attribute: str | None = None,
    at: datetime | None = None,
    now: datetime | None = None,
) -> Sequence[Fact]:
    """The facts that hold at `at` (default now): unsuperseded, inside their window.

    Passing `at` is how the timeline asks what was known on a day; the window is on the
    fact's own validity, so a fact asserted later about an earlier time is still found.

    The scope is the subject's, decided in `app.keys.scopes`: medicines under MEDICINES,
    readings under READINGS, the whole record — no subject named — under RECORDS.
    """
    moment = at or now or utcnow()
    where: list[ColumnElement[bool]] = [
        Fact.superseded_at.is_(None),
        Fact.valid_from <= moment,
        or_(Fact.valid_to.is_(None), Fact.valid_to > moment),
    ]
    if subject is not None:
        where.append(Fact.subject == subject)
    if attribute is not None:
        where.append(Fact.attribute == attribute)
    found = await audited_read(
        session, Fact, context, scope_for_subject(subject), where=where, now=now
    )
    return sorted(found, key=lambda fact: (fact.subject, fact.attribute, as_utc(fact.valid_from)))
