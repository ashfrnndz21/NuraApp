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
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import utcnow
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.repository import scoped_references
from app.keys.scopes import ALL_SCOPES, Column, KeyRole, Scope, scope_for_subject
from app.memory.models import (
    Artifact,
    ArtifactKind,
    Event,
    EventKind,
    Fact,
    Recording,
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


def _names_an_artefact_held_here(
    column: Column, context: KeyContext, scope: Scope
) -> ColumnElement[bool]:
    """`column` names an artefact on this profile whose bytes are in this region, whatever
    scope that artefact was written under: where the bytes are, not whether this key may
    read them (`app.keys.repository.scoped_references`)."""
    return scoped_references(column, Artifact, context, scope, held_here(context))


def event_cites_only_what_is_held_here(context: KeyContext, scope: Scope) -> ColumnElement[bool]:
    """The events naming no artefact, or one held here. Part of every query returning events.

    `scope` is the scope the surrounding read runs under: the filter asks nothing more of the
    key than that read already did. It asks where the artefact is held, not whether this key
    may read it: an event the key may see is shown, and an artefact it may not is withheld
    by name (`withheld_provenance`).
    """
    return or_(
        Event.artifact_id.is_(None),
        _names_an_artefact_held_here(Event.artifact_id, context, scope),
    )


def fact_cites_only_what_is_held_here(context: KeyContext, scope: Scope) -> ColumnElement[bool]:
    """The facts whose provenance, followed all the way down, is held here.

    A fact names an artefact, or an event, or both; an event names an artefact. This follows
    the chain: the artefact the fact names is held here, and the event it names itself names
    nothing or something held here. Part of every query returning facts, so a cite always
    leads to an artefact that can be read, and nothing resting on bytes held elsewhere is
    served by any reader. Like the events', the filter asks where the provenance is held and
    not whether this key may follow it: a fact is shown under its own scope, and what it
    cites is withheld by name where the key does not hold that (`withheld_provenance`).
    """
    return and_(
        or_(
            Fact.artifact_id.is_(None),
            _names_an_artefact_held_here(Fact.artifact_id, context, scope),
        ),
        or_(
            Fact.event_id.is_(None),
            scoped_references(
                Fact.event_id,
                Event,
                context,
                scope,
                event_cites_only_what_is_held_here(context, scope),
            ),
        ),
    )


EVENT_SCOPES: dict[EventKind, Scope] = {
    EventKind.READING: Scope.READINGS,
    EventKind.DOSE_TAKEN: Scope.MEDICINES,
    EventKind.SUPPLY: Scope.MEDICINES,
}
"""The scope `record_event` writes an event under: the record's, except a reading taken and a
tablet taken, which are the readings' and the medicines' parts. A key that does not hold the
part — a part marked "only me" among them — does not see the moment either. The writers
outside `record_event` write under their own scope, which the row keeps (`RowScoped`): the
family's message under FAMILY (`app.channels.whatsapp.inbound`), the moment of a fall said on
WhatsApp under EMERGENCY (`app.safety.red_flags.record_the_moment`), a tablet tapped under
MEDICINES (`app.medicines.service.record_dose_taken`)."""


def scope_for_event(kind: EventKind) -> Scope:
    """The scope an event of this kind is written under by `record_event`."""
    return EVENT_SCOPES.get(kind, Scope.RECORDS)


RECORDED_KINDS: frozenset[ArtifactKind] = frozenset({ArtifactKind.VOICE, ArtifactKind.TRANSCRIPT})
"""The artefact kinds that are a recording of people talking: every writer of one declares
whose voices it carries (`Recording`), and a consult rests on the RECORDING consent as well as
the consent to hold the record (ADR 0003). A visit's transcript (E05) is one: the words of a
consult, stored with `Recording.CONSULT`."""


class RecordingNotDeclared(Refusal):
    """A voice is stored saying whose voices it carries — a consult, or someone's own note —
    and nothing else is. This writer did not say, or said it of something that is not a voice."""


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
    recording: Recording | None = None,
) -> Artifact:
    """Write down an artefact whose bytes are already at `storage_key` in `region`.

    The region must be the profile's own: health data never leaves it, and a reference to
    bytes held elsewhere would be exactly that. The refusal is in the trail like any other.

    `recording` is required for a voice (`RECORDED_KINDS`) and refused for anything else
    (`RecordingNotDeclared`): the writer says whose voices it carries (ADR 0003). A
    `Recording.CONSULT` — people other than the account holder, a visit — rests on the
    RECORDING consent under the visits scope; a `Recording.OWN_NOTE` — his own words, or a
    caregiver's on his event — rests on holding the record, like typed text.
    """
    guard_region(held_in=region, asked_from=context.region)
    # Keeping anything at all rests on the consent to hold the record (E00-02).
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.RECORDS,
    )
    # Every voice says whose voices it carries, and nothing else claims to be a recording.
    if (kind in RECORDED_KINDS) != (recording is not None):
        raise RecordingNotDeclared(
            f"a {kind} artefact declares a recording"
            if kind in RECORDED_KINDS
            else f"a {kind} artefact is not a recording"
        )
    # A recording of other people — a consult — rests on the consent to record (E16-02,
    # ADR 0003). Checked here, where the bytes enter, and not only at the surface's gate
    # (`app.safety.recording.may_record`), so that no writer — the app, WhatsApp, a
    # connector — can keep a consult without it. His own note needs only the record's.
    if recording is Recording.CONSULT:
        await require_consent(
            session,
            context=context,
            purpose=ConsentPurpose.RECORDING,
            scope=Scope.VISITS,
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
        # A consult is the visits' part — the scope its consent is asked under (ADR 0003) —
        # and is written there, so only a key holding the visits reads it (row scope).
        Scope.VISITS if recording is Recording.CONSULT else Scope.RECORDS,
        kind=kind,
        storage_key=storage_key.strip(),
        content_type=content_type,
        sha256=digest,
        captured_at=captured_at,
        source_channel=source_channel,
        region=region,
        stored_at=utcnow(),
    )


CONSULT_HEARERS: frozenset[KeyRole] = frozenset({KeyRole.CHIEF, KeyRole.CAREGIVER})
"""Who hears a visit's recording besides the patient himself: the family he let in, his chief
and his caregivers. It is what the room was told ("Only you and the family you let in can
hear it") and what the printed card says ("The patient can let his family hear it too").
A viewer, a clinic, a helper or an emergency key reads the visit and its card, and not what
was said in the room, whatever scope it holds."""


class OnlyTheFamilyHears(Refusal):
    """A visit's recording, and the transcript heard from it, are for the patient and the
    family he let in — his chief and his caregivers. This key reads the visits; it does not
    hear what was said in the room."""


def is_consult(artifact: Artifact) -> bool:
    """Whether an artefact is a visit's recording or its transcript (`Recording.CONSULT`):
    a recorded kind, written under the visits scope — `store_artifact` writes a consult
    there and a person's own voice note under the record's or the notes'."""
    return artifact.kind in RECORDED_KINDS and artifact.written_scope is Scope.VISITS


def hears_consults(context: KeyContext) -> bool:
    """Whether this key may hear a visit's recording: the patient, or the family he let in."""
    return context.is_owner or context.role in CONSULT_HEARERS


def _heard_only_by_the_family(context: KeyContext, artifact: Artifact) -> Artifact:
    """The artefact door's one rule for a consult, whichever reader asks: every read of an
    artefact by id comes through `require_artifact` or `require_artifact_under`, so the clip,
    the transcript the post-visit card is read from and anything later all ask here. Refused
    in plain words, and on his trail by the door around the reader."""
    if is_consult(artifact) and not hears_consults(context):
        raise OnlyTheFamilyHears(f"a {context.role} key does not hear a visit's recording")
    return artifact


@audited(Action.READ, Scope.RECORDS, Artifact.__tablename__)
async def require_artifact(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
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
    )
    if not found:
        raise NoSuchArtifact(f"no artefact {artifact_id} on profile {context.profile_id}")
    return _heard_only_by_the_family(context, found[0])


@audited(Action.READ, lambda call: call["scope"], Artifact.__tablename__)
async def require_artifact_under(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    scope: Scope,
) -> Artifact:
    """The artefact by that id, read through the door of the scope it was written under, or a
    refusal saying no more. For a reader that knows which part an artefact is — a consult
    recording is the visits' (`store_artifact`, ADR 0003, ADR 0004) — so a key holding that
    part hears it and a key without it is refused at the door, on the trail. The row must
    also be written under `scope` (`scoped_select`) and held in this region (`held_here`)."""
    found = await audited_read(
        session,
        Artifact,
        context,
        scope,
        where=(Artifact.id == artifact_id, Artifact.written_scope == scope, held_here(context)),
    )
    if not found:
        raise NoSuchArtifact(f"no artefact {artifact_id} on profile {context.profile_id}")
    return _heard_only_by_the_family(context, found[0])


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
) -> Event:
    """Record that something happened, naming the artefact and the episode it belongs to.

    An event comes from somewhere. With an artefact, the event came in the way the artefact
    did, and `source_channel` may only agree. Without one, `source_channel` and `label` are
    both required: which channel it came in on, and what it was. `label` is a name for the
    moment, one short line. What was said or shown is in the artefact, and only there.

    The door is the record's; the row is written under its kind's part (`scope_for_event`),
    so a reading taken is the readings' and a key must hold that part to write or read it.
    """
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.RECORDS,
    )
    named = short_label(label) if label is not None else None
    came_in_by = await _where_it_came_from(
        session,
        context=context,
        artifact_id=artifact_id,
        source_channel=source_channel,
        label=named,
    )
    if episode_id is not None:
        await require_open_episode(session, context=context, episode_id=episode_id)
    return await audited_write(
        session,
        Event,
        context,
        scope_for_event(kind),
        kind=kind,
        occurred_at=occurred_at,
        source_channel=came_in_by,
        label=named,
        artifact_id=artifact_id,
        episode_id=episode_id,
        recorded_at=utcnow(),
    )


async def _where_it_came_from(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID | None,
    source_channel: SourceChannel | None,
    label: str | None,
) -> SourceChannel:
    """The channel an event came in on: the artefact's, or the one given beside a label."""
    if artifact_id is None:
        if source_channel is None or label is None:
            raise SourceNotNamed("an event names its artefact, or says its channel and label")
        return source_channel
    artifact = await require_artifact(session, context=context, artifact_id=artifact_id)
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
) -> Event:
    """The event by that id on this profile, citing nothing held elsewhere, or a refusal."""
    found = await audited_read(
        session,
        Event,
        context,
        Scope.RECORDS,
        where=(Event.id == event_id, event_cites_only_what_is_held_here(context, Scope.RECORDS)),
    )
    if not found:
        raise NoSuchEvent(f"no event {event_id} on profile {context.profile_id}")
    return found[0]


class NoSuchEvent(Refusal):
    """No event by that id on this profile."""


WITHHELD_ARTIFACT = "artifact"
WITHHELD_EVENT = "event"
"""The names a surface gives a reference it withholds: never the id, never a silent gap."""


Cited = tuple[uuid.UUID, Scope, uuid.UUID | None, uuid.UUID | None]
"""A row that cites provenance: its id, the scope it was read under, and the artefact and the
event it names (either may be None)."""


async def withheld_references(
    session: AsyncSession, *, context: KeyContext, cited: Sequence[Cited]
) -> dict[uuid.UUID, tuple[str, ...]]:
    """For each citing row, the references this key may not follow, by name — `"artifact"`,
    `"event"` — so a surface shows the row and says what it withheld: never the id of a row
    the key cannot see, and never a silent gap.

    A row is shown under its own scope; what it cites is shown under that row's own. Whether
    the key may follow a reference is asked the way any row is asked for, through the door,
    under the scope the citing row was read under: the artefacts and events that come back
    are the ones it may (`scoped_select` filters them by the scope each was written under).
    A key holding every scope follows every reference, and nothing is read to learn so.
    """
    if context.scopes >= ALL_SCOPES:
        return {}
    artifacts: dict[Scope, set[uuid.UUID]] = {}
    events: dict[Scope, set[uuid.UUID]] = {}
    for _, door, artifact_id, event_id in cited:
        if artifact_id is not None:
            artifacts.setdefault(door, set()).add(artifact_id)
        if event_id is not None:
            events.setdefault(door, set()).add(event_id)
    followed: set[uuid.UUID] = set()
    for door, ids in artifacts.items():
        if context.allows(door):
            found = await audited_read(
                session,
                Artifact,
                context,
                door,
                where=(Artifact.id.in_(sorted(ids, key=str)), held_here(context)),
            )
            followed |= {artifact.id for artifact in found}
    for door, ids in events.items():
        if context.allows(door):
            found_events = await audited_read(
                session, Event, context, door, where=(Event.id.in_(sorted(ids, key=str)),)
            )
            followed |= {event.id for event in found_events}
    withheld: dict[uuid.UUID, tuple[str, ...]] = {}
    for ident, _, artifact_id, event_id in cited:
        names: list[str] = []
        if artifact_id is not None and artifact_id not in followed:
            names.append(WITHHELD_ARTIFACT)
        if event_id is not None and event_id not in followed:
            names.append(WITHHELD_EVENT)
        if names:
            withheld[ident] = tuple(names)
    return withheld


async def withheld_provenance(
    session: AsyncSession, *, context: KeyContext, rows: Sequence[Fact | Event]
) -> dict[uuid.UUID, tuple[str, ...]]:
    """`withheld_references` for facts and events: a fact read under its subject's scope
    (`scope_for_subject`), naming an artefact and an event; an event read under the scope it
    was written under, naming an artefact."""
    return await withheld_references(
        session,
        context=context,
        cited=[
            (row.id, scope_for_subject(row.subject), row.artifact_id, row.event_id)
            if isinstance(row, Fact)
            else (row.id, row.written_scope, row.artifact_id, None)
            for row in rows
        ],
    )


async def row_is_there(
    session: AsyncSession, model: type[Artifact | Event], ident: uuid.UUID
) -> bool:
    """Whether a row this request wrote itself is still in its table: a yes or no, never the
    row. For the keepers that replay a write after a rollback (`app.db.keep_on_refusal`),
    which write the row again only if the rollback took it. Nothing a key asks for is read."""
    return await session.get(model, ident) is not None


async def artifact_kind_on_profile(
    session: AsyncSession, *, context: KeyContext, artifact_id: uuid.UUID
) -> ArtifactKind | None:
    """The kind of an artefact on this profile, or None: all a rule on a write needs to know
    of the artefact the write rests on (the label-photo rule, `app.safety.high_risk`),
    whatever scope it was written under. The kind only, never the row: the write read the
    artefact through the door a moment ago (`app.memory.semantic._check_provenance`)."""
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None or artifact.profile_id != context.profile_id:
        return None
    return artifact.kind
