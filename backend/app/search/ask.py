"""Ask: natural-language recall over his own record, with citations (E03-05).

Pa asks by voice, "what was my blood pressure", and hears one line; Mei asks in text, "what
did Dr Tan say", and reads a few. Either way the answer is made of the templates in
`app.delivery.timeline_strings` and the values of the facts it cites — nothing else — and
every such line names the ids it rests on: the fact and the event or artefact under it, the
visit and its provider, the medicine line and its label. When nothing on the record answers,
it says so — "Nura does not have that written down." — and names the doctor; it never
guesses. A question that would change treatment is answered with what is written down and a
question for the doctor. The boundary is last on every answer — `app.safety.boundary`'s line
for `Surface.RECALL` — because recall is an inferring surface (spec §10).

Recall is a reading of the record under the asker's key, and the asker must hold the ask
scope (`Scope.ASK`) to ask at all. Each part — visits, readings, medicines, the record — is
read under its own scope; a part the key does not reach is not read and is named as
withheld, a part the owner keeps "only me" among them. Which parts a question is about is the
retriever's to say (`app.search.retrieve.Retriever`): it sees the question and the candidates
this key could read, never the database, and writes no words.

The question itself is kept, by reference: the text goes to the region's object store as the
bytes of a MESSAGE artefact written under the ask scope, and the answer names that artefact.
No row holds the question's words. Every ask is on the trail, and so is every refusal.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import (
    audited_guard,
    audited_profile_read,
    audited_read,
    audited_write,
    person_display_name,
)
from app.audit.models import Action
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.delivery import timeline_strings as words
from app.drugs.registry import DrugRegistry, UnknownDrug
from app.errors import Refusal
from app.ingestion.models import ReviewCard
from app.ingestion.notes import NoteView, recallable_notes
from app.ingestion.objects import ObjectStore, sha256_of
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.models import MedicationLine
from app.medicines.strings import PLAIN_NAME
from app.memory.episodic import fact_cites_only_what_is_held_here, hears_consults, held_here
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    Artifact,
    ArtifactKind,
    Attachment,
    ConfidenceState,
    Fact,
    Provider,
    SourceChannel,
)
from app.memory.semantic import fact_is_under
from app.memory.spine import UPCOMING
from app.memory.timeline import language_for
from app.reasoning.visits.models import ItemState, SummaryItem, SummaryItemKind, VisitSummary
from app.regions import guard_region
from app.safety.boundary import Surface, boundary_lines
from app.search.retrieve import Candidate, Retriever

ASK_TARGET = "ask"
"""The trail's name for an ask: one line per question, naming the kept question."""

QUESTION_LENGTH = 300
TEXT_LINES = 5
"""The most cited lines a text answer gives; a voice answer gives the lines of one thing."""

BLOOD_PRESSURE = ("blood_pressure", "reading")

CHANGE_WORDS = frozenset(
    {
        "stop",
        "start",
        "change",
        "increase",
        "reduce",
        "double",
        "skip",
        "halve",
        "more",
        "less",
        "berhenti",
        "tukar",
        "tambah",
        "kurangkan",
    }
)
CHANGE_WORDS_ZH = ("停", "换", "加", "减")
MEDICINE_WORDS = frozenset(
    {"medicine", "medicines", "tablet", "tablets", "pill", "pills", "ubat", "药"}
)
VISIT_WORDS = frozenset({"visit", "visits", "appointment", "lawatan", "看医生", "预约"})
PAPER_WORDS = frozenset({"paper", "papers", "letter", "surat", "文件"})
NOTE_WORDS = frozenset(
    {"note", "notes", "voice note", "scribble", "nota", "nota suara", "笔记", "语音"}
)
"""What a question calls a note on one of his moments (E02-06), in every language."""
_NOTE_STOP = frozenset(
    {
        "what",
        "when",
        "where",
        "which",
        "that",
        "this",
        "these",
        "those",
        "with",
        "have",
        "from",
        "they",
        "them",
        "then",
        "there",
        "their",
        "were",
        "been",
        "just",
        "very",
        "some",
        "into",
        "also",
        "said",
        "will",
        "would",
        "could",
        "should",
        "does",
        "yang",
        "saya",
        "anda",
        "untuk",
        "dengan",
        "pada",
        "tidak",
        "sudah",
        "akan",
        "boleh",
        "bila",
        "mana",
        "siapa",
        "kenapa",
    }
)
"""The words heard in a note that say nothing on their own: a note is not about every
question that begins "what" or "when"."""
_GENERIC_WORDS = frozenset(
    {"test", "paper", "number", "filter", "your", "the", "ujian", "surat", "nombor", "blood"}
)
_LATIN_WORD = re.compile(r"[a-z]+")


class Mode(StrEnum):
    VOICE = "voice"
    TEXT = "text"


class NotAQuestion(Refusal):
    """A question is one line of one to three hundred characters."""


@dataclass(frozen=True, slots=True)
class Cite:
    """One thing a line rests on, by kind and id. A cite of a consult recording carries the
    stretch of it the line is about, in seconds (E03-05)."""

    kind: str
    id: uuid.UUID
    start_s: float | None = None
    end_s: float | None = None


@dataclass(frozen=True, slots=True)
class ClipRef:
    """The stretch of a consult recording a line can play on a tap: which artefact, from when
    to when, and the doctor who said it, for the button's words."""

    artifact_id: uuid.UUID
    start_s: float
    end_s: float
    doctor: str


@dataclass(frozen=True, slots=True)
class AnswerLine:
    text: str
    cites: tuple[Cite, ...]
    clip: ClipRef | None = None


@dataclass(frozen=True, slots=True)
class Answer:
    question_artifact_id: uuid.UUID
    mode: Mode
    language: str
    lines: tuple[AnswerLine, ...]
    """The cited lines: each made of a template and the values of the facts it cites."""
    honest: tuple[str, ...]
    """What is said when the record does not answer, or when the question would change
    treatment: plain, and claiming nothing, so it cites nothing."""
    boundary: tuple[str, ...]
    withheld: tuple[Scope, ...]
    dropped: int

    @property
    def answered(self) -> bool:
        return bool(self.lines)

    @property
    def spoken(self) -> list[str]:
        """The whole answer as it is read or heard, the boundary last."""
        return [line.text for line in self.lines] + list(self.honest) + list(self.boundary)


STEP_KEYS = ("visits", "readings", "medicines", "records")
"""One step per part of the record `_corpus_stream` reads, in the order it reads them. Each
name is a key into `app.delivery.timeline_strings.ASK_STEPS` (and its `_THEIRS` twin), never
prose composed here — the step is real work that already happened by the time it is yielded,
and it is yielded only when the key's scope let that part be read at all (`_corpus_stream`
skips a withheld scope's work entirely, so a step for it is never produced)."""


@dataclass(frozen=True, slots=True)
class AskStep:
    """One real stage of building the answer, streamed as it finishes: which part of the
    record was just read. Never invented, never delayed — see `recall_stream`. `count` is how
    many things that part held (visits, readings, medicine lines, or facts-and-papers-and-notes
    together for records) — for a narrator to say something concrete
    (`app.search.narrate.NarratedStep`), never a row itself."""

    key: str
    count: int = 0


# --- the corpus: what this key may read, as candidates ---------------------------------------


@dataclass
class _Corpus:
    candidates: list[Candidate] = field(default_factory=list)
    facts: dict[uuid.UUID, Fact] = field(default_factory=dict)
    visits: dict[uuid.UUID, Appointment] = field(default_factory=dict)
    providers: dict[uuid.UUID, Provider] = field(default_factory=dict)
    medicines: dict[uuid.UUID, MedicationLine] = field(default_factory=dict)
    papers: dict[uuid.UUID, Artifact] = field(default_factory=dict)
    paper_kinds: dict[uuid.UUID, str] = field(default_factory=dict)
    hung: dict[uuid.UUID, list[Attachment]] = field(default_factory=dict)
    consults: dict[uuid.UUID, tuple[SummaryItem, VisitSummary]] = field(default_factory=dict)
    notes: dict[uuid.UUID, NoteView] = field(default_factory=dict)
    writers: dict[uuid.UUID, str] = field(default_factory=dict)
    """Who left each note, by name: "Mei left a note on Monday 14 September"."""
    clips_open: bool = False
    """Whether the key may hear the recording to play a clip: the patient and the family he
    let in (`app.memory.episodic.hears_consults`), the rule the artefact door keeps."""
    withheld: list[Scope] = field(default_factory=list)

    def withhold(self, scope: Scope) -> None:
        if scope not in self.withheld:
            self.withheld.append(scope)


ACTION_WORDS: dict[str, frozenset[str]] = {
    "weigh_every_morning": frozenset({"scale", "weigh", "weight", "timbang", "体重"}),
    "bp_every_morning": frozenset({"blood pressure", "tekanan darah", "血压"}),
    "bring_bp_book_next_time": frozenset({"blood pressure book", "book", "buku", "血压本"}),
    "no_food_after_midnight": frozenset({"eat", "food", "midnight", "makan", "吃"}),
    "water_is_ok": frozenset({"water", "air", "喝水"}),
    "lighter_dinners": frozenset({"dinner", "salt", "makan malam", "晚餐"}),
    "walk_every_day": frozenset({"walk", "berjalan", "走"}),
    "blood_test_on": frozenset({"blood test", "ujian darah", "验血"}),
    "medicines_unchanged_said": frozenset(MEDICINE_WORDS),
}
"""What a heard action is about, in the words a question would use for it, for recall."""
FOLLOW_UP_WORDS = frozenset({"see again", "next visit", "come back", "jumpa lagi", "再见"})


def _with_words(phrases: set[str]) -> frozenset[str]:
    """Each phrase, and each word of it that says something on its own ("cholesterol")."""
    found = {phrase.lower() for phrase in phrases if phrase}
    for phrase in list(found):
        for word in _LATIN_WORD.findall(phrase):
            if len(word) >= 4 and word not in _GENERIC_WORDS:
                found.add(word)
    return frozenset(found)


def _note_words(text: str) -> set[str]:
    """The words heard in a note that say something on their own ("walk", "tired")."""
    return {
        word
        for word in _LATIN_WORD.findall(text.lower())
        if len(word) >= 4 and word not in _GENERIC_WORDS and word not in _NOTE_STOP
    }


def _what_names(subject: str) -> set[str]:
    return {words.what_word(subject, lang) for lang in words.LANGUAGES} | {
        subject.replace("_", " ")
    }


def _plain_names(registry: DrugRegistry | None, generic: str) -> set[str]:
    names = {generic.lower()}
    if registry is None:
        return names
    try:
        plain_id = registry.monograph(generic).plain_name_id
    except UnknownDrug:
        return names
    for lang in words.LANGUAGES:
        name = PLAIN_NAME[lang].get(plain_id)
        if name:
            for prefix in ("your ", "the ", "您的"):
                name = name.removeprefix(prefix)
            names.add(name.removesuffix(" anda"))
    return names


def _plain_name(registry: DrugRegistry | None, generic: str, language: str) -> str:
    if registry is not None:
        try:
            return PLAIN_NAME[language][registry.monograph(generic).plain_name_id]
        except (UnknownDrug, KeyError):
            pass
    return words.what_word("medicine", language)


def _is_reading(fact: Fact) -> bool:
    value = fact.value
    return (
        (fact.subject, fact.attribute) == BLOOD_PRESSURE
        and isinstance(value, dict)
        and "systolic" in value
        and "diastolic" in value
    )


async def _corpus_stream(
    session: AsyncSession,
    context: KeyContext,
    registry: DrugRegistry | None,
    store: ObjectStore,
) -> AsyncIterator[AskStep | _Corpus]:
    """Build the corpus one part of the record at a time, in `STEP_KEYS` order, yielding an
    `AskStep` the moment each part's real read finishes — and finally the `_Corpus` itself, the
    last item. A part this key's scope does not open is never read, so its step is never
    yielded either: the caregiver-scoping rule holds by construction, not by a filter bolted
    on after (spec 'Conversation, waiting and thinking')."""
    corpus = _Corpus()
    # visits (+ what was heard at a recorded one, E03-05: the same scope opens both)
    if context.allows(Scope.VISITS):
        providers = await audited_read(session, Provider, context, Scope.VISITS)
        corpus.providers = {provider.id: provider for provider in providers}
        for visit in await audited_read(session, Appointment, context, Scope.VISITS):
            provider = corpus.providers.get(visit.provider_id)
            corpus.visits[visit.id] = visit
            names = set(VISIT_WORDS) | ({provider.name.lower()} if provider else set())
            corpus.candidates.append(
                Candidate("visit", visit.id, visit.scheduled_at, frozenset(names))
            )
        corpus.clips_open = hears_consults(context)
        await _consults(session, context, registry, corpus)
        yield AskStep("visits", count=len(corpus.visits))
    else:
        corpus.withhold(Scope.VISITS)
    # readings: current facts under the readings scope. A medicine is recalled from its line,
    # below, not from the facts under it.
    if context.allows(Scope.READINGS):
        for fact in await _facts_under(session, context, Scope.READINGS):
            corpus.facts[fact.id] = fact
            names = _what_names(fact.subject)
            if fact.attribute not in ("reading", "value", "systolic", "diastolic"):
                names.add(fact.attribute.replace("_", " "))
            kind = "reading" if _is_reading(fact) else "fact"
            corpus.candidates.append(Candidate(kind, fact.id, fact.valid_from, _with_words(names)))
        yield AskStep("readings", count=len(corpus.facts))
    else:
        corpus.withhold(Scope.READINGS)
    # medicines
    if context.allows(Scope.MEDICINES):
        lines = await audited_read(
            session,
            MedicationLine,
            context,
            Scope.MEDICINES,
            where=(MedicationLine.superseded_at.is_(None),),
        )
        for line in lines:
            corpus.medicines[line.id] = line
            names = _plain_names(registry, line.generic) | set(MEDICINE_WORDS)
            if line.brand:
                names.add(line.brand.lower())
            if line.prescriber:
                names.add(line.prescriber.lower())
            corpus.candidates.append(
                Candidate("medicine", line.id, line.started_at, frozenset(names))
            )
        yield AskStep("medicines", count=len(lines))
    else:
        corpus.withhold(Scope.MEDICINES)
    # records: facts under the record's catch-all scope, the papers hung with something on
    # them, and his and the family's notes on his moments (E02-06) — one part, one scope, one
    # step.
    if context.allows(Scope.RECORDS):
        _facts_before_records = len(corpus.facts)
        for fact in await _facts_under(session, context, Scope.RECORDS):
            corpus.facts[fact.id] = fact
            names = _what_names(fact.subject)
            if fact.attribute not in ("reading", "value", "systolic", "diastolic"):
                names.add(fact.attribute.replace("_", " "))
            kind = "reading" if _is_reading(fact) else "fact"
            corpus.candidates.append(Candidate(kind, fact.id, fact.valid_from, _with_words(names)))
        hung = await audited_read(session, Attachment, context, Scope.RECORDS)
        for each in hung:
            corpus.hung.setdefault(each.artifact_id, []).append(each)
        if corpus.hung:
            artifacts = await audited_read(
                session,
                Artifact,
                context,
                Scope.RECORDS,
                where=(Artifact.id.in_(list(corpus.hung)), held_here(context)),
            )
            corpus.papers = {artifact.id: artifact for artifact in artifacts}
            cards = await audited_read(
                session,
                ReviewCard,
                context,
                Scope.RECORDS,
                where=(ReviewCard.artifact_id.in_(list(corpus.papers)),),
            )
            corpus.paper_kinds = {card.artifact_id: card.document_kind.value for card in cards}
        for artifact in corpus.papers.values():
            names = set(PAPER_WORDS)
            names |= {
                words.paper_word(corpus.paper_kinds.get(artifact.id), lang)
                for lang in words.LANGUAGES
            }
            for fact in corpus.facts.values():
                if fact.artifact_id == artifact.id:
                    names |= _what_names(fact.subject)
            names |= {name.lower() for name in _providers_of(corpus, artifact.id)}
            corpus.candidates.append(
                Candidate("paper", artifact.id, artifact.captured_at, _with_words(names))
            )
        await _notes(session, context, store, corpus)
        records_count = (
            (len(corpus.facts) - _facts_before_records) + len(corpus.papers) + len(corpus.notes)
        )
        yield AskStep("records", count=records_count)
    else:
        corpus.withhold(Scope.RECORDS)
    yield corpus


async def _facts_under(
    session: AsyncSession, context: KeyContext, scope: Scope
) -> Sequence[Fact]:
    """The current facts held under one scope (readings, or the record's catch-all) — the
    read `_corpus_stream` does once per part, before it says that part was read."""
    return await audited_read(
        session,
        Fact,
        context,
        scope,
        where=(
            fact_is_under(scope),
            Fact.superseded_at.is_(None),
            Fact.confidence_state != ConfidenceState.DISPUTED,
            fact_cites_only_what_is_held_here(context, scope),
        ),
    )


async def _notes(
    session: AsyncSession, context: KeyContext, store: ObjectStore, corpus: _Corpus
) -> None:
    """His notes on his moments, and the family's on them (E02-06): one candidate per note,
    named by its label, the words heard in it and the words for a note. Only a note this key
    opens — a private one only under the notes scope — on an event it reads
    (`app.ingestion.notes.recallable_notes`); the words are read back from the region's store
    and only name the candidate, they are never said in the answer."""
    for view in await recallable_notes(session, context=context, store=store):
        note = view.note
        names = set(NOTE_WORDS)
        if note.label:
            names |= set(_with_words({note.label}))
        if view.transcript is not None:
            names |= _note_words(view.transcript.text)
        corpus.notes[note.id] = view
        writer = note.written_by_person_id
        if writer not in corpus.writers:
            corpus.writers[writer] = await writer_name(session, context, writer)
        corpus.candidates.append(Candidate("note", note.id, note.written_at, frozenset(names)))


async def writer_name(session: AsyncSession, context: KeyContext, person_id: uuid.UUID) -> str:
    """Who left a note, by name, as far as this key may know who is on the family list: the
    reader themself needs no name ("You"), the patient is named under the profile's own scope,
    and anyone else only under the family's (`person_display_name`). Otherwise empty, and the
    line says "Someone" (`timeline_strings`)."""
    if person_id == context.person_id:
        return ""
    profile = await audited_profile_read(session, context)
    if person_id == profile.owner_person_id or context.allows(Scope.FAMILY):
        return await person_display_name(session, context, person_id)
    return ""


async def _consults(
    session: AsyncSession, context: KeyContext, registry: DrugRegistry | None, corpus: _Corpus
) -> None:
    """What was said at a recorded visit, one candidate per thing heard that has a place in
    the recording (E03-05): named by what it was about — his name for the medicine, the words
    for the action — so "what did Dr Tan say about the water pill" finds where he said it.

    Only what he has confirmed is cited. Before the post-visit card has his yes, a thing heard
    is a `consult_waiting` candidate: the answer says the card is waiting for his yes and cites
    the card, never the recording's words; after it, a confirmed item is a `consult`, with its
    place in the recording, and a rejected one is nothing."""
    summaries = await audited_read(
        session,
        VisitSummary,
        context,
        Scope.VISITS,
        where=(VisitSummary.recording_artifact_id.is_not(None),),
    )
    if not summaries:
        return
    by_id = {summary.id: summary for summary in summaries}
    items = await audited_read(
        session,
        SummaryItem,
        context,
        Scope.VISITS,
        where=(
            SummaryItem.summary_id.in_(list(by_id)),
            SummaryItem.clip_start_s.is_not(None),
            SummaryItem.state != ItemState.REJECTED,
        ),
    )
    for item in items:
        summary = by_id[item.summary_id]
        visit = corpus.visits.get(summary.appointment_id)
        if visit is None:
            continue
        names: set[str] = set()
        payload = item.payload or {}
        if item.kind is SummaryItemKind.MEDICATION_CHANGE and payload.get("generic"):
            names |= _plain_names(registry, str(payload["generic"]))
        elif item.kind is SummaryItemKind.ACTION:
            names |= ACTION_WORDS.get(str(payload.get("kind")), frozenset())
        elif item.kind is SummaryItemKind.FACT_HEARD and payload.get("subject"):
            names |= _what_names(str(payload["subject"]))
        elif item.kind is SummaryItemKind.FOLLOW_UP:
            names |= FOLLOW_UP_WORDS
        if not names:
            continue
        if summary.confirmed_at is None:
            kind = "consult_waiting"
        elif item.state is ItemState.CONFIRMED:
            kind = "consult"
        else:
            continue
        corpus.consults[item.id] = (item, summary)
        corpus.candidates.append(Candidate(kind, item.id, visit.scheduled_at, _with_words(names)))


def _providers_of(corpus: _Corpus, artifact_id: uuid.UUID) -> set[str]:
    """The providers a paper is from: the one whose visit it hangs off, and the ones whose
    visits were part of the episode it hangs off."""
    names: set[str] = set()
    for each in corpus.hung.get(artifact_id, []):
        for visit in corpus.visits.values():
            if visit.id == each.appointment_id or (
                each.episode_id is not None and visit.episode_id == each.episode_id
            ):
                provider = corpus.providers.get(visit.provider_id)
                if provider is not None:
                    names.add(provider.name)
    return names


# --- the answer ----------------------------------------------------------------------------


def _doctor(corpus: _Corpus) -> str | None:
    """Who to ask: the provider of the next visit, else of the last one that happened."""
    now = utcnow()
    visits = sorted(corpus.visits.values(), key=lambda visit: as_utc(visit.scheduled_at))
    coming = [v for v in visits if v.status in UPCOMING and as_utc(v.scheduled_at) >= now]
    happened = [
        v
        for v in visits
        if v.status == AppointmentStatus.ATTENDED and as_utc(v.scheduled_at) <= now
    ]
    chosen = coming[0] if coming else (happened[-1] if happened else None)
    if chosen is None:
        return None
    provider = corpus.providers.get(chosen.provider_id)
    return None if provider is None else provider.name


def _cites_of_fact(fact: Fact) -> list[Cite]:
    cites = [Cite("fact", fact.id)]
    if fact.event_id is not None:
        cites.append(Cite("event", fact.event_id))
    if fact.artifact_id is not None:
        cites.append(Cite("artifact", fact.artifact_id))
    return cites


def _day(moment: datetime, context: KeyContext, language: str) -> str:
    return words.said_date(moment, context.region, language)


def _compose(
    hits: Sequence[Candidate],
    corpus: _Corpus,
    context: KeyContext,
    language: str,
    registry: DrugRegistry | None,
) -> list[list[AnswerLine]]:
    """The lines for each thing the question is about, one group per thing, from the
    templates and the cited values. A group is one line, or two where one would carry more
    numbers than a line may (a reading in Chinese: the day, then the numbers)."""
    now = utcnow()
    groups: list[list[AnswerLine]] = []
    papers_said: set[uuid.UUID] = set()
    visits_heard: set[uuid.UUID] = set()
    for hit in hits:
        if hit.kind == "reading":
            fact = corpus.facts[hit.ref]
            value: dict[str, Any] = fact.value
            cites = tuple(_cites_of_fact(fact))
            texts = words.reading_lines(
                language,
                date=_day(fact.valid_from, context, language),
                top_number=str(value["systolic"]),
                bottom_number=str(value["diastolic"]),
            )
            groups.append([AnswerLine(text, cites) for text in texts])
        elif hit.kind == "fact":
            fact = corpus.facts[hit.ref]
            source = fact.artifact_id or fact.event_id
            if source in papers_said:
                continue
            together = [
                f
                for f in corpus.facts.values()
                if source is not None and (f.artifact_id == source or f.event_id == source)
            ] or [fact]
            papers_said.add(source or fact.id)
            text = words.recall_line(
                "paper",
                language,
                what=words.what_word(fact.subject, language),
                date=_day(fact.valid_from, context, language),
            )
            fact_cites = [c for f in together for c in _cites_of_fact(f)]
            groups.append([AnswerLine(text, tuple(dict.fromkeys(fact_cites)))])
        elif hit.kind == "visit":
            visit = corpus.visits[hit.ref]
            provider = corpus.providers.get(visit.provider_id)
            doctor = "" if provider is None else provider.name
            when = _day(visit.scheduled_at, context, language)
            if visit.status == AppointmentStatus.ATTENDED and as_utc(visit.scheduled_at) <= now:
                key = "visit_past"
            elif visit.status in UPCOMING and as_utc(visit.scheduled_at) >= now:
                key = "visit_next"
            else:
                continue
            text = words.recall_line(key, language, doctor=doctor, date=when)
            visit_cites = (Cite("appointment", visit.id), Cite("provider", visit.provider_id))
            groups.append([AnswerLine(text, visit_cites)])
        elif hit.kind == "medicine":
            line = corpus.medicines[hit.ref]
            name = _plain_name(registry, line.generic, language)
            if line.prescriber:
                text = words.recall_line(
                    "medicine_from", language, doctor=line.prescriber, name=name
                )
            else:
                text = words.recall_line("medicine_listed", language, name=name)
            line_cites = [Cite("medication_line", line.id), Cite("fact", line.fact_id)]
            if line.source_artifact_id is not None:
                line_cites.append(Cite("artifact", line.source_artifact_id))
            if line.source_event_id is not None:
                line_cites.append(Cite("event", line.source_event_id))
            groups.append([AnswerLine(text, tuple(line_cites))])
        elif hit.kind == "consult":
            item, summary = corpus.consults[hit.ref]
            # One line per recorded visit: the best thing heard there that the question is
            # about, and the stretch of the recording where it was said.
            if summary.id in visits_heard:
                continue
            visits_heard.add(summary.id)
            visit = corpus.visits[summary.appointment_id]
            provider = corpus.providers.get(visit.provider_id)
            doctor = "" if provider is None else provider.name
            text = words.recall_line(
                "consult_said",
                language,
                doctor=doctor,
                date=_day(visit.scheduled_at, context, language),
            )
            consult_cites = [Cite("summary_item", item.id), Cite("appointment", visit.id)]
            clip: ClipRef | None = None
            if (
                corpus.clips_open
                and summary.recording_artifact_id is not None
                and item.clip_start_s is not None
                and item.clip_end_s is not None
            ):
                consult_cites.append(
                    Cite(
                        "artifact",
                        summary.recording_artifact_id,
                        item.clip_start_s,
                        item.clip_end_s,
                    )
                )
                clip = ClipRef(
                    summary.recording_artifact_id, item.clip_start_s, item.clip_end_s, doctor
                )
            groups.append([AnswerLine(text, tuple(consult_cites), clip)])
        elif hit.kind == "consult_waiting":
            _, summary = corpus.consults[hit.ref]
            if summary.id in visits_heard:
                continue
            visits_heard.add(summary.id)
            visit = corpus.visits[summary.appointment_id]
            provider = corpus.providers.get(visit.provider_id)
            text = words.recall_line(
                "consult_waiting",
                language,
                doctor="" if provider is None else provider.name,
                date=_day(visit.scheduled_at, context, language),
            )
            groups.append(
                [
                    AnswerLine(
                        text, (Cite("visit_summary", summary.id), Cite("appointment", visit.id))
                    )
                ]
            )
        elif hit.kind == "note":
            note = corpus.notes[hit.ref].note
            when = _day(note.written_at, context, language)
            text = (
                words.recall_line("note_yours", language, date=when)
                if note.written_by_person_id == context.person_id
                else words.recall_line(
                    "note_theirs",
                    language,
                    who=corpus.writers.get(note.written_by_person_id, ""),
                    date=when,
                )
            )
            note_cites = (
                Cite("event_note", note.id),
                Cite("event", note.event_id),
                Cite("artifact", note.artifact_id),
            )
            groups.append([AnswerLine(text, note_cites)])
        elif hit.kind == "paper":
            if hit.ref in papers_said:
                continue
            papers_said.add(hit.ref)
            artifact = corpus.papers[hit.ref]
            on_it = [f for f in corpus.facts.values() if f.artifact_id == artifact.id]
            what = (
                words.what_word(on_it[0].subject, language)
                if on_it
                else words.paper_word(corpus.paper_kinds.get(artifact.id), language)
            )
            moment = on_it[0].valid_from if on_it else artifact.captured_at
            text = words.recall_line(
                "paper", language, what=what, date=_day(moment, context, language)
            )
            paper_cites = [Cite("artifact", artifact.id)]
            paper_cites += [
                Cite("attachment", each.id) for each in corpus.hung.get(artifact.id, [])
            ]
            paper_cites += [Cite("fact", f.id) for f in on_it]
            groups.append([AnswerLine(text, tuple(paper_cites))])
    return groups


def _would_change_treatment(question: str, hits: Sequence[Candidate]) -> bool:
    low = question.lower()
    latin = set(_LATIN_WORD.findall(low))
    changing = bool(latin & CHANGE_WORDS) or any(word in low for word in CHANGE_WORDS_ZH)
    about_medicine = (
        bool(latin & MEDICINE_WORDS) or "药" in low or any(hit.kind == "medicine" for hit in hits)
    )
    return changing and about_medicine


async def _keep_question(
    session: AsyncSession, context: KeyContext, store: ObjectStore, text: str
) -> Artifact:
    """The question's words to the region's store; a MESSAGE artefact under the ask scope
    names them by key and digest. No row holds the words."""
    guard_region(held_in=store.region, asked_from=context.region)
    await require_consent(
        session, context=context, purpose=ConsentPurpose.HOLD_HEALTH_RECORD, scope=Scope.ASK
    )
    data = text.encode("utf-8")
    digest = sha256_of(data)
    key = f"questions/{context.profile_id}/{digest}"
    await store.put(key, data)
    moment = utcnow()
    return await audited_write(
        session,
        Artifact,
        context,
        Scope.ASK,
        kind=ArtifactKind.MESSAGE,
        storage_key=key,
        content_type="text/plain; charset=utf-8",
        sha256=digest,
        captured_at=moment,
        source_channel=SourceChannel.APP,
        region=store.region,
        stored_at=moment,
    )


async def recall_stream(
    session: AsyncSession,
    *,
    context: KeyContext,
    question: str,
    mode: Mode,
    retriever: Retriever,
    store: ObjectStore,
    registry: DrugRegistry | None = None,
    language: str | None = None,
) -> AsyncIterator[AskStep | Answer]:
    """Answer a question from his own record, with citations, the boundary last — streamed: an
    `AskStep` the moment each part of the record is actually read (`_corpus_stream`), then the
    `Answer`, the last item. The single source of truth for recall: `recall` (below) is this,
    drained. Nothing here is scripted or delayed for effect — a step is real work that already
    happened, and the answer is yielded the instant it is ready (spec 'Conversation, waiting
    and thinking').

    Voice gives the best thing, in one line (two where one line would carry too many numbers),
    and text up to five lines. Every cited line is a
    template filled with the values of what it cites and passes the plain-words verifier;
    a line that does not is not said. Nothing answered is "Nura does not have that written
    down", never a guess. The question is kept as a MESSAGE artefact and the ask is written
    to the trail, naming it.
    """
    async with audited_guard(session, context, Action.READ, Scope.ASK, ASK_TARGET):
        context.require(Scope.ASK)
        text = question.strip()
        if not text or len(text) > QUESTION_LENGTH or "\n" in text or "\r" in text:
            raise NotAQuestion(f"a question is one line of one to {QUESTION_LENGTH} characters")
        lang = await language_for(session, context, language)
        kept = await _keep_question(session, context, store, text)
        corpus: _Corpus | None = None
        async for item in _corpus_stream(session, context, registry, store):
            if isinstance(item, AskStep):
                yield item
            else:
                corpus = item
        assert corpus is not None
        hits = retriever.retrieve(text, corpus.candidates)
        doctor = _doctor(corpus)
        groups = _compose(hits, corpus, context, lang, registry)
        passing = [group for group in groups if all(words.verified(x.text, lang) for x in group)]
        dropped = sum(len(group) for group in groups) - sum(len(group) for group in passing)
        said: list[AnswerLine] = []
        for group in passing[:1] if mode is Mode.VOICE else passing:
            if said and len(said) + len(group) > TEXT_LINES:
                break
            said.extend(group)
        honest: list[str] = []
        if _would_change_treatment(text, hits):
            honest = words.reroute_lines(lang, doctor)
        elif not said:
            honest = words.honest_lines(lang, doctor)
        await record(
            session,
            context=context,
            action=Action.READ,
            scope=Scope.ASK,
            target=ASK_TARGET,
            target_id=kept.id,
            rows=len(said),
        )
        yield Answer(
            question_artifact_id=kept.id,
            mode=mode,
            language=lang,
            lines=tuple(said),
            honest=tuple(honest),
            boundary=boundary_lines(Surface.RECALL, lang, doctor=doctor),
            withheld=tuple(corpus.withheld),
            dropped=dropped,
        )


async def recall(
    session: AsyncSession,
    *,
    context: KeyContext,
    question: str,
    mode: Mode,
    retriever: Retriever,
    store: ObjectStore,
    registry: DrugRegistry | None = None,
    language: str | None = None,
) -> Answer:
    """`recall_stream`, drained: the answer alone, for a caller that does not stream (the
    existing `POST /profiles/{id}/ask` route, unchanged)."""
    result: Answer | None = None
    async for event in recall_stream(
        session,
        context=context,
        question=question,
        mode=mode,
        retriever=retriever,
        store=store,
        registry=registry,
        language=language,
    ):
        if isinstance(event, Answer):
            result = event
    assert result is not None
    return result


__all__ = [
    "ASK_TARGET",
    "STEP_KEYS",
    "Answer",
    "AnswerLine",
    "AskStep",
    "Cite",
    "ClipRef",
    "Mode",
    "NotAQuestion",
    "recall",
    "recall_stream",
    "writer_name",
]
