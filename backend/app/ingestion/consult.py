"""Recording a visit (E02-05, E05-04): the notice, the bytes, the words, who said them, the card.

    Consent captured before recording; transcript searchable; clip playable at a timestamp.
    One tap to start with consent prompt; ends into post-visit.

The order is docs/trust/recording-consent.md's. `notice_for` is what the surface asks when
the Start button is tapped, before the microphone opens: it refuses a key that does not
change the visits (a viewer, a helper, a clinic key) before anything else, then asks the gate
(`may_record`: the RECORDING consent in force under the visits scope, the records scope held),
and only then hands back the notice in his language, to the doctor by name, with the printed
card and the words for a no. A room is never told "Nura will listen now" by a key that could
not keep what it hears.

`record_consult` is the upload, once Stop is tapped — nothing reaches the server before: the
gate again, the audio checked (a recorder's own container, a size and a length a visit has),
the bytes kept as a VOICE artefact declared `Recording.CONSULT` in the region's store (so
`store_artifact` asks the consent a third time, where the bytes land), then the region's
transcriber, the region's speaker separator, and E05's post-visit summary with each item's
place in the recording. The recording and what was heard are kept whatever the summary does:
a summary that is refused (a line that fails the verifier) is refused inside its own
savepoint and the card says so; the recording stays, as far as it went. The doctor's answer is
the first seconds of the artefact and nothing is ever trimmed from its start. A "no" from the
doctor or from him is the surface's: nothing is uploaded, nothing is kept (`when_no`).

`consult_clip` is the other half of E03-05: the stretch of a recording a summary line or an
answer cites. A webm or an mp4 cannot be cut at a byte offset into something a phone will
play without a demuxer, and Nura takes no new dependency for one, so the clip is honest about
it: the whole artefact, under the scope it was written under — the visits', where every
consult is kept (ADR 0004) — with the start and end the citation carries, which the phone plays as a media fragment (`#t=start,end`) and stops at the end
(docs/adr/0006-consult-recording-on-the-web.md).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.db import as_utc, nested_unit_of_work, utcnow
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.ingestion.models import ConsultRecording, ConsultSegment
from app.ingestion.objects import NoSuchObject, ObjectStore, sha256_of
from app.ingestion.speakers import Aligned, SegmentsDoNotFit, SpeakerSeparator, Unseparated, align
from app.ingestion.transcribe import Transcriber, Transcript
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import require_artifact_under, store_artifact
from app.memory.models import Artifact, ArtifactKind, Recording, SourceChannel
from app.reasoning.visits.guard import may_change_visits
from app.reasoning.visits.models import SummaryItem, VisitSummary
from app.reasoning.visits.questions import require_visit
from app.reasoning.visits.summary import (
    YOU,
    ConsultClips,
    Summariser,
    post_visit_summary,
    store_transcript,
    summary_items,
)
from app.regions import guard_region
from app.safety.recording import may_record, printed_notice, recording_notice, when_no

CONSULT = ConsultRecording.__tablename__

CONSULT_CONTENT_TYPES: Mapping[str, Callable[[bytes], bool]] = {
    "audio/webm": lambda data: data[:4] == b"\x1a\x45\xdf\xa3",
    "audio/ogg": lambda data: data[:4] == b"OggS",
    "audio/mp4": lambda data: data[4:8] == b"ftyp",
}
"""What a phone's recorder makes, and how its first bytes say so: opus in a webm from Chrome
and Android, opus in an ogg from Firefox, AAC in an mp4 from Safari on the iPhone."""

MAX_CONSULT_BYTES = 48 * 1024 * 1024
"""A long visit with room: opus at the recorder's 64 kbit/s is about 29 MB an hour."""

MAX_CONSULT_SECONDS = 90 * 60
"""Ninety minutes. A visit that runs longer is two recordings."""

MIN_CONSULT_SECONDS = 1.0

CLIP_SLACK_SECONDS = 0.5
"""A clip may end this much past the last thing heard: the recorder's own rounding."""


class NotAConsultRecording(Refusal):
    """The bytes offered were empty, of a kind a phone's recorder does not make, not what
    their type says, or said to be no length at all."""


class ConsultTooLong(Refusal):
    """A visit's recording is not this big, or this long."""


class NoSuchRecording(Refusal):
    """No consult recording of that artefact on this profile."""


class NotAClip(Refusal):
    """A clip starts before it ends, inside the recording."""


def check_consult_audio(data: bytes, content_type: str, duration_s: float) -> str:
    """The content type without its parameters, or a refusal."""
    kind = content_type.strip().lower().split(";", 1)[0]
    looks_right = CONSULT_CONTENT_TYPES.get(kind)
    if looks_right is None:
        raise NotAConsultRecording(f"{content_type} is not a recorder's audio")
    if not data:
        raise NotAConsultRecording("the recording was empty")
    if len(data) > MAX_CONSULT_BYTES:
        raise ConsultTooLong(f"a recording is at most {MAX_CONSULT_BYTES} bytes")
    if not looks_right(data):
        raise NotAConsultRecording(f"the bytes are not {kind}")
    if not duration_s >= MIN_CONSULT_SECONDS:
        raise NotAConsultRecording("a recording lasts at least a second")
    if duration_s > MAX_CONSULT_SECONDS:
        raise ConsultTooLong(f"a recording is at most {MAX_CONSULT_SECONDS} seconds")
    return kind


def consult_key(profile_id: uuid.UUID, digest: str) -> str:
    return f"consults/{profile_id}/{digest}"


# --- the notice: what the Start button asks first ---------------------------------------------


@dataclass(frozen=True, slots=True)
class Notice:
    """What the surface shows and speaks before the microphone opens, and the words for a no."""

    appointment_id: uuid.UUID
    doctor: str
    language: str
    spoken: tuple[str, ...]
    printed: tuple[str, ...]
    when_no: tuple[str, ...]
    consent_id: uuid.UUID


@audited(Action.READ, Scope.VISITS, CONSULT)
async def notice_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    writer: str | None,
) -> Notice:
    """The notice for this visit, in his language, to the doctor by name — or a refusal
    before anyone in the room is told anything.

    `writer` is the name of the person holding the phone, who writes the notes by hand on a
    no; None when it is the patient himself ("You will write the notes by hand.").
    """
    may_change_visits(context)
    check = await may_record(session, context)
    visit = await require_visit(session, context=context, appointment_id=appointment_id)
    lang = visit.language
    who = writer if writer else YOU[lang]
    return Notice(
        appointment_id=visit.appointment.id,
        doctor=visit.doctor,
        language=lang,
        spoken=tuple(recording_notice(lang, doctor=visit.doctor).splitlines()),
        printed=tuple(printed_notice(lang).splitlines()),
        when_no=tuple(when_no(lang, who=who).splitlines()),
        consent_id=check.consent_id,
    )


# --- the upload: what Stop sends ------------------------------------------------------------


@dataclass
class ConsultOutcome:
    """What one upload kept, and the card it ended in."""

    recording: ConsultRecording
    artifact: Artifact
    transcript: Artifact | None
    heard: Transcript | None
    segments: list[ConsultSegment] = field(default_factory=list)
    summary: VisitSummary | None = None
    items: Sequence[SummaryItem] = ()
    summary_refused: str | None = None
    """The refusal's name when the card could not be made; the recording is kept anyway."""


@audited(Action.WRITE, Scope.VISITS, CONSULT)
async def record_consult(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    data: bytes,
    content_type: str,
    duration_s: float,
    started_at: datetime | None,
    store: ObjectStore,
    transcriber: Transcriber,
    separator: SpeakerSeparator | None,
    summariser: Summariser,
    registry: DrugRegistry,
) -> ConsultOutcome:
    """Keep one recording of one visit, hear it, say who spoke when, and make the card."""
    may_change_visits(context)
    check = await may_record(session, context)
    guard_region(held_in=store.region, asked_from=context.region)
    guard_region(held_in=transcriber.region, asked_from=context.region)
    kind = check_consult_audio(data, content_type, duration_s)
    visit = await require_visit(
        session, context=context, appointment_id=appointment_id, registry=registry
    )
    began = as_utc(started_at) if started_at is not None else utcnow() - timedelta(seconds=duration_s)
    digest = sha256_of(data)
    key = consult_key(context.profile_id, digest)
    # The row first, then the bytes: a refusal where the bytes land leaves nothing in the
    # store. `store_artifact` asks the RECORDING consent again, for a consult, whoever writes.
    artifact = await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.VOICE,
        recording=Recording.CONSULT,
        storage_key=key,
        content_type=kind,
        sha256=digest,
        captured_at=began,
        source_channel=SourceChannel.APP,
        region=store.region,
    )
    await store.put(key, data)

    heard = await transcriber.transcribe(data, kind, visit.language, context.region)
    transcript: Artifact | None = None
    aligned: list[Aligned] = []
    if heard.heard:
        transcript = await store_transcript(
            session, context=context, store=store, text=heard.text, captured_at=began
        )
        who_spoke = separator if separator is not None else Unseparated(context.region, duration_s)
        guard_region(held_in=who_spoke.region, asked_from=context.region)
        try:
            aligned = align(heard.text, await who_spoke.separate(heard, data, context.region))
        except SegmentsDoNotFit:
            # Nothing is guessed: the recording and the words are kept, with no speakers.
            aligned = []

    recording = await audited_write(
        session,
        ConsultRecording,
        context,
        Scope.VISITS,
        appointment_id=visit.appointment.id,
        artifact_id=artifact.id,
        transcript_artifact_id=None if transcript is None else transcript.id,
        consent_id=check.consent_id,
        duration_s=float(duration_s),
        started_at=began,
        notice_language=visit.language,
        doctor_named=bool(visit.doctor.strip()),
        heard_confidence=heard.confidence if heard.heard else None,
        recorded_by_person_id=context.person_id,
        stored_at=utcnow(),
    )
    outcome = ConsultOutcome(
        recording=recording,
        artifact=artifact,
        transcript=transcript,
        heard=heard if heard.heard else None,
    )
    for position, one in enumerate(aligned):
        outcome.segments.append(
            await audited_write(
                session,
                ConsultSegment,
                context,
                Scope.VISITS,
                recording_id=recording.id,
                position=position,
                speaker=one.speaker,
                start_s=one.start_s,
                end_s=one.end_s,
                char_start=one.char_start,
                char_end=one.char_end,
            )
        )
    if transcript is None:
        return outcome

    # The card, in its own savepoint: a card refused is a card not made, and the recording,
    # the words and the speakers stand.
    try:
        async with nested_unit_of_work(session):
            outcome.summary = await post_visit_summary(
                session,
                context=context,
                appointment_id=visit.appointment.id,
                artifact_id=transcript.id,
                store=store,
                summariser=summariser,
                registry=registry,
                clips=ConsultClips(artifact.id, tuple(aligned)),
            )
            outcome.items = await summary_items(
                session, context=context, summary_id=outcome.summary.id
            )
    except Refusal as refusal:
        outcome.summary = None
        outcome.items = ()
        outcome.summary_refused = type(refusal).__name__
    return outcome


# --- reading them back -------------------------------------------------------------------------


@audited(Action.READ, Scope.VISITS, CONSULT)
async def recordings_for(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID
) -> list[tuple[ConsultRecording, list[ConsultSegment]]]:
    """Every recording of this visit, newest first, each with who spoke when."""
    found = await audited_read(
        session,
        ConsultRecording,
        context,
        Scope.VISITS,
        where=(ConsultRecording.appointment_id == appointment_id,),
    )
    if not found:
        return []
    segments = await audited_read(
        session,
        ConsultSegment,
        context,
        Scope.VISITS,
        where=(ConsultSegment.recording_id.in_([one.id for one in found]),),
    )
    by_recording: dict[uuid.UUID, list[ConsultSegment]] = {}
    for segment in sorted(segments, key=lambda one: one.position):
        by_recording.setdefault(segment.recording_id, []).append(segment)
    newest = sorted(found, key=lambda one: (as_utc(one.started_at), str(one.id)), reverse=True)
    return [(one, by_recording.get(one.id, [])) for one in newest]


@dataclass(frozen=True, slots=True)
class Clip:
    """The recording a citation points into, and the stretch of it to play."""

    artifact: Artifact
    data: bytes
    start_s: float
    end_s: float


@audited(Action.READ, Scope.VISITS, CONSULT)
async def consult_clip(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    artifact_id: uuid.UUID,
    start_s: float,
    end_s: float,
) -> Clip:
    """The stretch `start_s`–`end_s` of a consult recording, or a refusal.

    The recording is a visit's: its row and its bytes are the visits' part (`store_artifact`
    writes a consult there, ADR 0004), so the key must hold the visits scope to find it, and
    the artefact is read under the scope it was written under (`require_artifact_under`). The
    whole artefact comes back with the range: see the module note.
    """
    guard_region(held_in=store.region, asked_from=context.region)
    found = await audited_read(
        session,
        ConsultRecording,
        context,
        Scope.VISITS,
        where=(ConsultRecording.artifact_id == artifact_id,),
    )
    if not found:
        raise NoSuchRecording(f"no consult recording {artifact_id} on profile {context.profile_id}")
    recording = found[0]
    segments = await audited_read(
        session,
        ConsultSegment,
        context,
        Scope.VISITS,
        where=(ConsultSegment.recording_id == recording.id,),
    )
    longest = max([recording.duration_s, *(one.end_s for one in segments)])
    if not (0 <= start_s < end_s <= longest + CLIP_SLACK_SECONDS):
        raise NotAClip(f"a clip is inside the recording's {longest:.1f} seconds")
    artifact = await require_artifact_under(
        session, context=context, artifact_id=artifact_id, scope=Scope.VISITS
    )
    data = await store.get(artifact.storage_key)
    if sha256_of(data) != artifact.sha256:
        raise NoSuchObject("the bytes under that key are not the recording")
    return Clip(artifact=artifact, data=data, start_s=start_s, end_s=end_s)


__all__ = [
    "CONSULT_CONTENT_TYPES",
    "MAX_CONSULT_BYTES",
    "MAX_CONSULT_SECONDS",
    "Clip",
    "ConsultOutcome",
    "ConsultTooLong",
    "NoSuchRecording",
    "NotAClip",
    "NotAConsultRecording",
    "Notice",
    "check_consult_audio",
    "consult_clip",
    "notice_for",
    "record_consult",
    "recordings_for",
]
