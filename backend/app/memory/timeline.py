"""The timeline (E03-01, E03-02): the spine of visits, the episodes, and what hangs off each.

Appointments are the spine: the last check-up, the last visit and the next visit, said in his
words at the top of the page. Under them, newest first, each visit with its provider and each
episode with the visits it spanned, and off each the papers that hang there (`Attachment`),
the events that name it and the facts resting on those — every one read under its own scope.
The spine is the visits' (`Scope.VISITS`, the door); an episode, an artefact and an event are
the record's; a fact is its subject's (`scope_for_subject`, through `fact_is_under`). A key
that does not cover a part sees the page without it and is told which parts were withheld, by
name — a part the owner marked "only me" among them, since the key context never holds one
(`app.keys.privacy`).

Nothing here is a finding. The page is the record arranged in time; the lines at the top say
when and with whom, and nothing about what it meant.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import ColumnElement, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read
from app.audit.models import Action
from app.db import as_utc, utcnow
from app.delivery import timeline_strings as words
from app.errors import Refusal
from app.ingestion.models import EventNote
from app.keys.context import KeyContext
from app.keys.repository import scoped_select
from app.keys.scopes import FACT_SCOPES, Scope
from app.memory.episodic import (
    event_cites_only_what_is_held_here,
    fact_cites_only_what_is_held_here,
    held_here,
    withheld_provenance,
)
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    Artifact,
    Attachment,
    ConfidenceState,
    Episode,
    Event,
    Fact,
    Provider,
)
from app.memory.semantic import fact_is_under
from app.memory.spine import UPCOMING
from app.memory.working import NoSuchEpisode

PAGE_SIZE = 20
MAX_PAGE = 50

CHECKUP_WORDS = (
    "check-up",
    "checkup",
    "check up",
    "review",
    "screening",
    "pemeriksaan",
    "检查",
    "体检",
)
"""A visit is a check-up when the purpose the person wrote down says so. A visit has no kind
of its own yet (the visit loop, E05, may give it one); until then the words decide."""


class NotACursor(Refusal):
    """A cursor is what the last page handed back, unchanged. This was not one."""


@dataclass(frozen=True, slots=True)
class Hanging:
    """What hangs off one visit or one episode, newest first."""

    artifacts: tuple[Artifact, ...] = ()
    events: tuple[Event, ...] = ()
    facts: tuple[Fact, ...] = ()
    notes: tuple[EventNote, ...] = ()
    """The voice notes and scribbles on those events (E02-06), by reference: the note's row,
    never its recording or its words."""
    withheld: Mapping[uuid.UUID, tuple[str, ...]] = field(default_factory=dict)
    """For an event or a fact here, what it cites that this key may not follow, by name —
    shown without its id (`app.memory.episodic.withheld_provenance`)."""


@dataclass(frozen=True, slots=True)
class TimelineItem:
    """One entry on the timeline: a visit with its provider, or an episode with its visits."""

    kind: str
    """`appointment` or `episode`."""
    id: uuid.UUID
    at: datetime
    hanging: Hanging
    appointment: Appointment | None = None
    provider: Provider | None = None
    episode: Episode | None = None
    visits: tuple[uuid.UUID, ...] = ()
    """For an episode, the visits that were part of it — the episode groups them."""


@dataclass(frozen=True, slots=True)
class Anchor:
    """One of the three anchors of the spine, and its line in his words."""

    key: str
    line: str
    appointment: Appointment | None = None
    provider: Provider | None = None


@dataclass(frozen=True, slots=True)
class TimelinePage:
    language: str
    header: tuple[Anchor, ...]
    items: tuple[TimelineItem, ...]
    next_cursor: str | None
    withheld: tuple[Scope, ...]


@dataclass(frozen=True, slots=True)
class EpisodeView:
    """One episode with everything hanging off it, and each visit that was part of it."""

    item: TimelineItem
    visits: tuple[TimelineItem, ...]
    withheld: tuple[Scope, ...]


def _newest[Row: (Artifact, Event, Fact)](rows: Iterable[Row]) -> list[Row]:
    def moment(row: Row) -> tuple[datetime, str]:
        if isinstance(row, Artifact):
            return (as_utc(row.captured_at), str(row.id))
        if isinstance(row, Event):
            return (as_utc(row.occurred_at), str(row.id))
        return (as_utc(row.valid_from), str(row.id))

    return sorted(rows, key=moment, reverse=True)


@dataclass
class Gathered:
    """The parts of the record the timeline is made of, as far as this key reaches."""

    appointments: list[Appointment] = field(default_factory=list)
    providers: dict[uuid.UUID, Provider] = field(default_factory=dict)
    episodes: list[Episode] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    artifacts: dict[uuid.UUID, Artifact] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    notes: list[EventNote] = field(default_factory=list)
    withheld: list[Scope] = field(default_factory=list)
    withheld_refs: dict[uuid.UUID, tuple[str, ...]] = field(default_factory=dict)
    """For each event and fact gathered, what it cites that this key may not follow."""

    def withhold(self, scope: Scope) -> None:
        if scope not in self.withheld:
            self.withheld.append(scope)

    def refs_withheld(self, rows: Iterable[Event | Fact]) -> dict[uuid.UUID, tuple[str, ...]]:
        return {row.id: self.withheld_refs[row.id] for row in rows if row.id in self.withheld_refs}

    def off_visit(self, appointment_id: uuid.UUID) -> Hanging:
        ids = {
            each.artifact_id
            for each in self.attachments
            if each.appointment_id == appointment_id and each.artifact_id in self.artifacts
        }
        facts = [f for f in self.facts if f.artifact_id in ids]
        return Hanging(
            artifacts=tuple(_newest(self.artifacts[i] for i in ids)),
            facts=tuple(_newest(facts)),
            withheld=self.refs_withheld(facts),
        )

    def off_episode(self, episode_id: uuid.UUID) -> Hanging:
        events = [event for event in self.events if event.episode_id == episode_id]
        ids = {each.artifact_id for each in self.attachments if each.episode_id == episode_id}
        ids |= {event.artifact_id for event in events if event.artifact_id is not None}
        named = {event.id for event in events}
        facts = [
            fact
            for fact in self.facts
            if fact.episode_id == episode_id or fact.artifact_id in ids or fact.event_id in named
        ]
        return Hanging(
            artifacts=tuple(_newest(self.artifacts[i] for i in ids if i in self.artifacts)),
            events=tuple(_newest(events)),
            facts=tuple(_newest(facts)),
            notes=tuple(
                sorted(
                    (note for note in self.notes if note.event_id in named),
                    key=lambda note: (as_utc(note.written_at), str(note.id)),
                )
            ),
            withheld=self.refs_withheld([*events, *facts]),
        )

    def visit_item(self, appointment: Appointment) -> TimelineItem:
        return TimelineItem(
            kind="appointment",
            id=appointment.id,
            at=appointment.scheduled_at,
            hanging=self.off_visit(appointment.id),
            appointment=appointment,
            provider=self.providers.get(appointment.provider_id),
        )

    def episode_item(self, episode: Episode) -> TimelineItem:
        return TimelineItem(
            kind="episode",
            id=episode.id,
            at=episode.opened_at,
            hanging=self.off_episode(episode.id),
            episode=episode,
            visits=tuple(
                visit.id
                for visit in sorted(
                    self.appointments, key=lambda a: as_utc(a.scheduled_at), reverse=True
                )
                if visit.episode_id == episode.id
            ),
        )

    def items(self) -> list[TimelineItem]:
        return [self.visit_item(a) for a in self.appointments] + [
            self.episode_item(e) for e in self.episodes
        ]


async def gather(session: AsyncSession, *, context: KeyContext) -> Gathered:
    """Read what the timeline is made of, one part at a time, each under its own scope.

    A part the key does not hold is not read at all and is named in `withheld`. Facts are
    read only where they hang — off an episode, off an artefact hung somewhere, off an
    event of an episode — so a fact standing on its own is not pulled in to be dropped.
    """
    found = Gathered()
    if context.allows(Scope.VISITS):
        found.appointments = list(await audited_read(session, Appointment, context, Scope.VISITS))
        providers = await audited_read(session, Provider, context, Scope.VISITS)
        found.providers = {provider.id: provider for provider in providers}
    else:
        found.withhold(Scope.VISITS)
    if context.allows(Scope.RECORDS):
        found.episodes = list(await audited_read(session, Episode, context, Scope.RECORDS))
        found.attachments = list(await audited_read(session, Attachment, context, Scope.RECORDS))
        found.events = list(
            await audited_read(
                session,
                Event,
                context,
                Scope.RECORDS,
                where=(
                    # A reading taken and a tablet taken are written under the readings' and
                    # the medicines' parts (`episodic.EVENT_SCOPES`), and the read returns
                    # only the parts this key holds (`scoped_select`).
                    Event.episode_id.is_not(None),
                    event_cites_only_what_is_held_here(context, Scope.RECORDS),
                ),
            )
        )
        wanted = {each.artifact_id for each in found.attachments}
        wanted |= {event.artifact_id for event in found.events if event.artifact_id is not None}
        if wanted:
            artifacts = await audited_read(
                session,
                Artifact,
                context,
                Scope.RECORDS,
                where=(Artifact.id.in_(sorted(wanted, key=str)), held_here(context)),
            )
            found.artifacts = {artifact.id: artifact for artifact in artifacts}
        if found.events:
            found.notes = await _notes_on(session, context, [e.id for e in found.events])
            if not context.allows(Scope.NOTES):
                found.withhold(Scope.NOTES)
    else:
        found.withhold(Scope.RECORDS)
    hangs: list[ColumnElement[bool]] = []
    if found.episodes:
        hangs.append(Fact.episode_id.in_([episode.id for episode in found.episodes]))
    if found.artifacts:
        hangs.append(Fact.artifact_id.in_(list(found.artifacts)))
    if found.events:
        hangs.append(Fact.event_id.in_([event.id for event in found.events]))
    for scope in FACT_SCOPES:
        if not context.allows(scope):
            found.withhold(scope)
            continue
        if not hangs:
            continue
        found.facts.extend(
            await audited_read(
                session,
                Fact,
                context,
                scope,
                where=(
                    fact_is_under(scope),
                    Fact.superseded_at.is_(None),
                    Fact.confidence_state != ConfidenceState.DISPUTED,
                    fact_cites_only_what_is_held_here(context, scope),
                    or_(*hangs),
                ),
            )
        )
    found.withheld_refs = await withheld_provenance(
        session, context=context, rows=[*found.events, *found.facts]
    )
    return found


async def _notes_on(
    session: AsyncSession, context: KeyContext, event_ids: list[uuid.UUID]
) -> list[EventNote]:
    """The notes on these events this key opens: the shared ones under the record's scope,
    the private ones under the notes scope when the key holds it (E02-06). Their rows only —
    whether there are words is `transcript_key`, and the words stay in the store."""
    held = (
        EventNote.event_id.in_(event_ids),
        EventNote.artifact_id.in_(
            scoped_select(Artifact, context, Scope.RECORDS)
            .with_only_columns(Artifact.id)
            .where(held_here(context))
        ),
    )
    found = list(
        await audited_read(
            session, EventNote, context, Scope.RECORDS, where=(*held, EventNote.private.is_(False))
        )
    )
    if context.allows(Scope.NOTES):
        found.extend(
            await audited_read(
                session, EventNote, context, Scope.NOTES, where=(*held, EventNote.private.is_(True))
            )
        )
    return found


def is_checkup(purpose: str) -> bool:
    low = purpose.lower()
    return any(word in low for word in CHECKUP_WORDS)


def _anchor(
    key: str,
    none_key: str,
    visit: Appointment | None,
    found: Gathered,
    context: KeyContext,
    language: str,
) -> Anchor:
    if visit is None:
        return Anchor(key=key, line=words.anchor_line(none_key, language))
    provider = found.providers.get(visit.provider_id)
    when = words.said_date(visit.scheduled_at, context.region, language)
    line = words.anchor_line(
        key, language, doctor=None if provider is None else provider.name, when=when
    )
    if not words.verified(line, language):
        # A name in the directory that the words cannot carry: say "your doctor" instead.
        line = words.anchor_line(key, language, when=when)
    return Anchor(key=key, line=line, appointment=visit, provider=provider)


def header(found: Gathered, context: KeyContext, language: str) -> tuple[Anchor, ...]:
    """The last check-up, the last visit and the next visit, by the clock."""
    now = utcnow()
    happened = sorted(
        (
            visit
            for visit in found.appointments
            if visit.status == AppointmentStatus.ATTENDED and as_utc(visit.scheduled_at) <= now
        ),
        key=lambda visit: as_utc(visit.scheduled_at),
    )
    checkups = [visit for visit in happened if is_checkup(visit.purpose)]
    coming = sorted(
        (
            visit
            for visit in found.appointments
            if visit.status in UPCOMING and as_utc(visit.scheduled_at) >= now
        ),
        key=lambda visit: as_utc(visit.scheduled_at),
    )
    return (
        _anchor(
            "last_checkup",
            "no_checkup",
            checkups[-1] if checkups else None,
            found,
            context,
            language,
        ),
        _anchor(
            "last_visit", "no_visit", happened[-1] if happened else None, found, context, language
        ),
        _anchor("next_visit", "no_next", coming[0] if coming else None, found, context, language),
    )


def _key(item: TimelineItem) -> tuple[datetime, str]:
    return (as_utc(item.at), str(item.id))


def cursor_of(item: TimelineItem) -> str:
    raw = f"{as_utc(item.at).isoformat()}|{item.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _after(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        moment, _, ident = raw.partition("|")
        return (as_utc(datetime.fromisoformat(moment)), str(uuid.UUID(ident)))
    except (binascii.Error, ValueError, UnicodeDecodeError) as bad:
        raise NotACursor("a cursor is what the last page handed back") from bad


async def language_for(session: AsyncSession, context: KeyContext, asked: str | None) -> str:
    """The words come in `asked`, or the profile's own language."""
    if asked is not None:
        return words.language_of(asked)
    return words.language_of((await audited_profile_read(session, context)).language)


@audited(Action.READ, Scope.VISITS, Appointment.__tablename__)
async def timeline(
    session: AsyncSession,
    *,
    context: KeyContext,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: str | None = None,
    episode_id: uuid.UUID | None = None,
    limit: int = PAGE_SIZE,
    language: str | None = None,
) -> TimelinePage:
    """One page of the timeline, newest first, with the three anchors on top.

    `since` and `until` narrow by when the visit was or the episode began (`until` not
    included); `episode_id` narrows to one episode and the visits that were part of it
    (E03-02: the timeline filters by episode); `cursor` is the last page's `next_cursor`.
    """
    lang = await language_for(session, context, language)
    found = await gather(session, context=context)
    items = found.items()
    if episode_id is not None:
        context.require(Scope.RECORDS)
        if not any(episode.id == episode_id for episode in found.episodes):
            raise NoSuchEpisode(f"no episode {episode_id} on profile {context.profile_id}")
        items = [
            item
            for item in items
            if item.id == episode_id
            or (item.appointment is not None and item.appointment.episode_id == episode_id)
        ]
    if since is not None:
        items = [item for item in items if as_utc(item.at) >= as_utc(since)]
    if until is not None:
        items = [item for item in items if as_utc(item.at) < as_utc(until)]
    items.sort(key=_key, reverse=True)
    if cursor is not None:
        after = _after(cursor)
        items = [item for item in items if _key(item) < after]
    size = max(1, min(limit, MAX_PAGE))
    page = items[:size]
    return TimelinePage(
        language=lang,
        header=header(found, context, lang),
        items=tuple(page),
        next_cursor=cursor_of(page[-1]) if len(items) > size else None,
        withheld=tuple(found.withheld),
    )


@audited(Action.READ, Scope.RECORDS, Episode.__tablename__)
async def episode_view(
    session: AsyncSession, *, context: KeyContext, episode_id: uuid.UUID
) -> EpisodeView:
    """One episode, open or closed, with what hangs off it and each of its visits with what
    hangs off that. An episode groups events across visits (E03-02)."""
    found = await gather(session, context=context)
    episode = next((each for each in found.episodes if each.id == episode_id), None)
    if episode is None:
        raise NoSuchEpisode(f"no episode {episode_id} on profile {context.profile_id}")
    visits = sorted(
        (found.visit_item(visit) for visit in found.appointments if visit.episode_id == episode_id),
        key=_key,
        reverse=True,
    )
    return EpisodeView(
        item=found.episode_item(episode), visits=tuple(visits), withheld=tuple(found.withheld)
    )


__all__ = [
    "FACT_SCOPES",
    "Anchor",
    "EpisodeView",
    "Gathered",
    "Hanging",
    "NotACursor",
    "TimelineItem",
    "TimelinePage",
    "episode_view",
    "gather",
    "header",
    "is_checkup",
    "language_for",
    "timeline",
]
