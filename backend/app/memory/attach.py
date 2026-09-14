"""Hanging an artefact off an episode or a visit (E03-01, E03-02).

An artefact comes in on its own — a photo of a letter, a lab report — and the person who
knows what it belongs to says so: this paper is part of the chest infection, that letter is
from Thursday's visit. `attach_to_episode` and `attach_to_appointment` write that down on the
person's own yes (`app.drafts.AttachDraft`), the way a booking or a fact is written; the row
names who said so. `attach_from_ingestion` is the other way a paper joins an episode: the
review card's yes named an open episode as it was confirmed (`app.ingestion.review`), so the
card's photo hangs off it under that yes, marked as such.

Nothing here reads what the artefact says. The artefact is read under the record's scope, the
episode under the record's, the visit under the visits', and the attachment itself is a row of
the record.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.db import as_utc, utcnow
from app.drafts import AttachDraft
from app.errors import Refusal
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import require_artifact
from app.memory.models import Appointment, AttachedHow, Attachment
from app.memory.spine import NoSuchAppointment
from app.memory.working import require_open_episode

ATTACHMENT = Attachment.__tablename__


class AlreadyHangsThere(Refusal):
    """This artefact already hangs off that episode or that visit. Once is enough."""


async def require_appointment(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID
) -> Appointment:
    """The visit by that id on this profile, under the visits' scope, or a refusal."""
    found = await audited_read(
        session, Appointment, context, Scope.VISITS, where=(Appointment.id == appointment_id,)
    )
    if not found:
        raise NoSuchAppointment(f"no appointment {appointment_id} on profile {context.profile_id}")
    return found[0]


async def _hang(
    session: AsyncSession,
    *,
    context: KeyContext,
    draft: AttachDraft,
    how: AttachedHow,
    by_person_id: uuid.UUID,
) -> Attachment:
    """The write itself, after every check: the row, once, naming who and how."""
    already = await audited_read(
        session,
        Attachment,
        context,
        Scope.RECORDS,
        where=(
            Attachment.artifact_id == draft.artifact_id,
            Attachment.episode_id == draft.episode_id,
            Attachment.appointment_id == draft.appointment_id,
        ),
    )
    if already:
        raise AlreadyHangsThere(f"artefact {draft.artifact_id} already hangs there")
    return await audited_write(
        session,
        Attachment,
        context,
        Scope.RECORDS,
        artifact_id=draft.artifact_id,
        episode_id=draft.episode_id,
        appointment_id=draft.appointment_id,
        how=how,
        attached_by_person_id=by_person_id,
        attached_at=utcnow(),
    )


@audited(Action.WRITE, Scope.RECORDS, ATTACHMENT)
async def attach_to_episode(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    episode_id: uuid.UUID,
    confirmation_id: uuid.UUID,
) -> Attachment:
    """Hang an artefact off an open episode, on the person's yes for exactly that.

    The artefact must be on this profile and held here; the episode must be open — nothing
    attaches to a closed one. The yes is used last, once everything else has passed, so a
    refusal never spends it.
    """
    await require_artifact(session, context=context, artifact_id=artifact_id)
    await require_open_episode(session, context=context, episode_id=episode_id)
    draft = AttachDraft(artifact_id=artifact_id, episode_id=episode_id, appointment_id=None)
    yes = await consume_confirmation(session, context, confirmation_id, draft)
    return await _hang(
        session, context=context, draft=draft, how=AttachedHow.MANUAL, by_person_id=yes.person_id
    )


@audited(Action.WRITE, Scope.RECORDS, ATTACHMENT)
async def attach_to_appointment(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    appointment_id: uuid.UUID,
    confirmation_id: uuid.UUID,
) -> Attachment:
    """Hang an artefact off a visit on the spine — the letter from that visit, the lab slip
    it sent him for — on the person's yes for exactly that. Any visit, whatever its status:
    a letter arrives after the visit happened."""
    await require_artifact(session, context=context, artifact_id=artifact_id)
    await require_appointment(session, context=context, appointment_id=appointment_id)
    draft = AttachDraft(artifact_id=artifact_id, episode_id=None, appointment_id=appointment_id)
    yes = await consume_confirmation(session, context, confirmation_id, draft)
    return await _hang(
        session, context=context, draft=draft, how=AttachedHow.MANUAL, by_person_id=yes.person_id
    )


@audited(Action.WRITE, Scope.RECORDS, ATTACHMENT)
async def attach_from_ingestion(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    episode_id: uuid.UUID,
    by_person_id: uuid.UUID,
) -> Attachment:
    """The automatic way in: a review card confirmed into an open episode hangs its photo
    off that episode. The yes is the card's (`ReviewDraft.episode_id` is part of what was
    confirmed), already spent by the review service a moment ago; `by_person_id` is the
    person it named. Called by `app.ingestion.review` and by nothing on a surface."""
    await require_artifact(session, context=context, artifact_id=artifact_id)
    await require_open_episode(session, context=context, episode_id=episode_id)
    draft = AttachDraft(artifact_id=artifact_id, episode_id=episode_id, appointment_id=None)
    return await _hang(
        session, context=context, draft=draft, how=AttachedHow.INGESTION, by_person_id=by_person_id
    )


@audited(Action.READ, Scope.RECORDS, ATTACHMENT)
async def attachments(
    session: AsyncSession,
    *,
    context: KeyContext,
    episode_id: uuid.UUID | None = None,
    appointment_id: uuid.UUID | None = None,
    artifact_id: uuid.UUID | None = None,
) -> Sequence[Attachment]:
    """What hangs where, newest first, narrowed to one episode, one visit or one artefact."""
    where: list[ColumnElement[bool]] = []
    if episode_id is not None:
        where.append(Attachment.episode_id == episode_id)
    if appointment_id is not None:
        where.append(Attachment.appointment_id == appointment_id)
    if artifact_id is not None:
        where.append(Attachment.artifact_id == artifact_id)
    found = await audited_read(session, Attachment, context, Scope.RECORDS, where=where)
    return sorted(found, key=lambda row: (as_utc(row.attached_at), str(row.id)), reverse=True)
