"""Find: the words of a visit's recording, searched (E02-05).

    Consent captured before recording; transcript searchable; clip playable at a timestamp.

He or his family types a few words — "water pill" — and lands on the moment of a recorded
visit where they were said: the sentence as it was heard, which visit it was (the doctor and
the day, in his language), and the stretch of the recording to play, from the speakers the
separator heard (`ConsultSegment`). Three rules decide what is searched, and none of them is
the caller's to widen:

- Only a visit whose post-visit card he has confirmed. Until his yes, what was said is a card
  waiting for him, and its words are not searched — the rule recall keeps for what a visit
  said (`app.search.ask._consults`).
- Only for the family he let in. A visit's recording, and the transcript heard from it, are
  for the patient, his chief and his caregivers (`app.memory.episodic.hears_consults`, the
  artefact door's rule): a viewer, a clinic or a helper holding the visits is refused by
  name, on the trail, before anything is read; and the transcript itself is read only
  through that door (`require_artifact_under`), under the visits scope it was written under.
- Nothing is kept of the search. The words searched are not written anywhere; the trail says
  that a search was made and how many places it found.

The line above each sentence is a template (`app.delivery.timeline_strings`), verified; the
sentence is the room's words, quoted as heard and never rewritten. Nothing infers here, so
there is no boundary line; no model is called.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc
from app.delivery import timeline_strings as words
from app.errors import Refusal
from app.ingestion.models import ConsultRecording, ConsultSegment
from app.ingestion.objects import NoSuchObject, ObjectStore, sha256_of
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import OnlyTheFamilyHears, hears_consults, require_artifact_under
from app.memory.models import Appointment, Provider
from app.memory.timeline import language_for
from app.reasoning.visits.models import VisitSummary
from app.regions import guard_region
from app.search.ask import Cite, ClipRef

log = logging.getLogger("nura.search.transcripts")

TRANSCRIPT_SEARCH = "transcript_search"
"""The trail's name for a search of the visits' words: one line per search, and how many
places it found. Never the words searched."""

WORDS_LENGTH = 100
MOST = 10
"""The most places one search lands on: newest visit first, then in the order said."""

_SENTENCE = re.compile(r"[^.!?。！？]+[.!?。！？]*")
_LATIN = re.compile(r"[0-9a-z]+")
_CJK = re.compile(r"[㐀-䶿一-鿿]+")


class NotASearch(Refusal):
    """A search is a few words on one line, one to a hundred characters, naming at least one
    word."""


@dataclass(frozen=True, slots=True)
class Found:
    """One place the words were said: Nura's line saying which visit, in his language; the
    sentence as it was heard; who the separator heard say it; and the stretch to play."""

    appointment_id: uuid.UUID
    summary_id: uuid.UUID
    doctor: str
    line: str
    sentence: str
    heard_in: str | None
    speaker: str | None
    clip: ClipRef
    cites: tuple[Cite, ...]


@dataclass(frozen=True, slots=True)
class Search:
    language: str
    found: tuple[Found, ...]
    honest: tuple[str, ...]
    """When nothing was found: "Nura does not have that written down." and who to ask."""
    dropped: int
    """Lines that did not pass the plain-words verifier and were not said."""


def terms_of(searched: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The words a sentence must hold, each: whole Latin words, and runs of Chinese."""
    text = searched.strip()
    if not text or len(text) > WORDS_LENGTH or "\n" in text or "\r" in text:
        raise NotASearch(f"a search is one line of one to {WORDS_LENGTH} characters")
    low = text.lower()
    latin = tuple(dict.fromkeys(_LATIN.findall(low)))
    han = tuple(dict.fromkeys(_CJK.findall(low)))
    if not latin and not han:
        raise NotASearch("a search names at least one word")
    return latin, han


def sentences(text: str) -> Iterator[tuple[int, int, str]]:
    """Each sentence of a transcript, with where it starts and ends in it."""
    for match in _SENTENCE.finditer(text):
        raw = match.group(0)
        said = raw.strip()
        if not said:
            continue
        start = match.start() + (len(raw) - len(raw.lstrip()))
        yield start, start + len(said), said


def holds(sentence: str, latin: Sequence[str], han: Sequence[str]) -> bool:
    low = sentence.lower()
    present = set(_LATIN.findall(low))
    return all(word in present for word in latin) and all(run in low for run in han)


@audited(Action.READ, Scope.VISITS, TRANSCRIPT_SEARCH)
async def search_transcripts(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    searched: str,
    language: str | None = None,
) -> Search:
    """Every place in a confirmed visit's recording where these words were said, newest
    visit first, for the patient and the family he let in. See the module note."""
    latin, han = terms_of(searched)
    if not hears_consults(context):
        raise OnlyTheFamilyHears(f"a {context.role} key does not hear a visit's recording")
    guard_region(held_in=store.region, asked_from=context.region)
    lang = await language_for(session, context, language)
    confirmed = await audited_read(
        session,
        VisitSummary,
        context,
        Scope.VISITS,
        where=(
            VisitSummary.confirmed_at.is_not(None),
            VisitSummary.recording_artifact_id.is_not(None),
        ),
    )
    by_recording: dict[uuid.UUID, VisitSummary] = {}
    for summary in sorted(confirmed, key=lambda one: as_utc(one.created_at)):
        assert summary.recording_artifact_id is not None
        by_recording[summary.recording_artifact_id] = summary
    recordings = (
        await audited_read(
            session,
            ConsultRecording,
            context,
            Scope.VISITS,
            where=(
                ConsultRecording.artifact_id.in_(sorted(by_recording, key=str)),
                ConsultRecording.transcript_artifact_id.is_not(None),
            ),
        )
        if by_recording
        else []
    )
    visits: dict[uuid.UUID, Appointment] = {}
    providers: dict[uuid.UUID, Provider] = {}
    segments: dict[uuid.UUID, list[ConsultSegment]] = {}
    if recordings:
        visits = {
            visit.id: visit
            for visit in await audited_read(
                session,
                Appointment,
                context,
                Scope.VISITS,
                where=(Appointment.id.in_(sorted({r.appointment_id for r in recordings}, key=str)),),
            )
        }
        providers = {
            provider.id: provider
            for provider in await audited_read(
                session,
                Provider,
                context,
                Scope.VISITS,
                where=(
                    Provider.id.in_(sorted({v.provider_id for v in visits.values()}, key=str)),
                ),
            )
        }
        for segment in await audited_read(
            session,
            ConsultSegment,
            context,
            Scope.VISITS,
            where=(ConsultSegment.recording_id.in_([r.id for r in recordings]),),
        ):
            segments.setdefault(segment.recording_id, []).append(segment)

    found: list[Found] = []
    dropped = 0
    newest_first = sorted(
        (r for r in recordings if r.appointment_id in visits),
        key=lambda r: (as_utc(visits[r.appointment_id].scheduled_at), as_utc(r.started_at)),
        reverse=True,
    )
    for recording in newest_first:
        if len(found) >= MOST:
            break
        assert recording.transcript_artifact_id is not None
        # The one door for a consult's words: the visits' scope, the family's ears.
        transcript = await require_artifact_under(
            session,
            context=context,
            artifact_id=recording.transcript_artifact_id,
            scope=Scope.VISITS,
        )
        try:
            data = await store.get(transcript.storage_key)
        except NoSuchObject:
            log.warning("transcript search: the words of one recording are not in the store")
            continue
        if sha256_of(data) != transcript.sha256:
            log.warning("transcript search: the bytes of one transcript are not what was kept")
            continue
        text = data.decode("utf-8")
        visit = visits[recording.appointment_id]
        summary = by_recording[recording.artifact_id]
        provider = providers.get(visit.provider_id)
        doctor = "" if provider is None else provider.name
        line = words.recall_line(
            "transcript_said",
            lang,
            doctor=doctor,
            date=words.said_date(visit.scheduled_at, context.region, lang),
        )
        if not words.verified(line, lang):
            dropped += 1
            continue
        stretches = sorted(segments.get(recording.id, []), key=lambda one: one.position)
        for start, end, sentence in sentences(text):
            if not holds(sentence, latin, han):
                continue
            over = [s for s in stretches if s.char_start < end and s.char_end > start]
            if over:
                start_s = min(s.start_s for s in over)
                end_s = max(s.end_s for s in over)
                speaker: str | None = over[0].speaker.value
            else:
                # No speakers were heard: the whole recording, never a guessed moment in it.
                start_s, end_s, speaker = 0.0, float(recording.duration_s), None
            clip = ClipRef(recording.artifact_id, start_s, end_s, doctor)
            found.append(
                Found(
                    appointment_id=visit.id,
                    summary_id=summary.id,
                    doctor=doctor,
                    line=line,
                    sentence=sentence,
                    heard_in=recording.notice_language,
                    speaker=speaker,
                    clip=clip,
                    cites=(
                        Cite("visit_summary", summary.id),
                        Cite("appointment", visit.id),
                        Cite("artifact", transcript.id),
                        Cite("artifact", recording.artifact_id, start_s, end_s),
                    ),
                )
            )
            if len(found) >= MOST:
                break
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=Scope.VISITS,
        target=TRANSCRIPT_SEARCH,
        rows=len(found),
    )
    return Search(
        language=lang,
        found=tuple(found),
        honest=() if found else tuple(words.honest_lines(lang, None)),
        dropped=dropped,
    )


__all__ = [
    "MOST",
    "TRANSCRIPT_SEARCH",
    "Found",
    "NotASearch",
    "Search",
    "search_transcripts",
]
