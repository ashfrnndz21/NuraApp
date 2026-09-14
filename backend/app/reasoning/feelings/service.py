"""The door for the feelings: a tap on the cloud, its one answer, and the notes (E17-02).

**A red word goes first.** A tap on a red word — or a yes to the question that tells a red
variant apart — presses the not-feeling-well button for him, server-side (E13/E14,
`app.safety.not_feeling_well.not_feeling_well`, with his word as the words and the tapped red
word named so nothing is guessed back from them): the moment it was said
(`record_the_moment`, under the emergency scope, so any key holding that scope can start it),
the flag on it, kept so a later refusal cannot take it back (`write_flag_kept`), a notice to
everyone on his emergency list, and the ladder for delivery to walk (`roster_for`,
`Escalation`, kept) — before the cloud is read, before anything is ranked, before any note.
The button also sets the day's posture to act and renders its what-to-do card — the urgent
one, with the calls, "Nura does not decide what is wrong." last — and that card is what the
tap answers with; the client shows it. There is no note for a red word.

**Every other word asks one thing back.** The tap is a SYMPTOM event in his word and a
`FeelingTap` naming why the word was on the cloud; "Fine today" says thank you and asks
nothing. His answer is the tap's one change; the note it is read into is rendered from State
under the boundary line, or not written at all (`render_from_state`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import (
    audited,
    audited_profile_read,
    audited_read,
    audited_write,
)
from app.audit.models import Action
from app.audit.trail import record
from app.db import utcnow
from app.delivery.feed.items import NotPlainWords
from app.delivery.triggers.deliver import Via
from app.delivery.triggers.models import Ladder
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.ingestion.objects import ObjectStore
from app.ingestion.transcribe import Transcriber
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import record_event
from app.memory.models import EventKind, SourceChannel
from app.reasoning.feelings.cloud import weigh
from app.reasoning.feelings.inference import compose_note
from app.reasoning.feelings.models import FeelingNote, FeelingTap
from app.reasoning.feelings.record import local_date, read_situation
from app.reasoning.feelings.strings import ANSWER_WORDS, FINE_LINES, QUESTIONS, WORDS, language_of
from app.reasoning.feelings.words import (
    ANSWERS,
    Answer,
    FollowUp,
    follow_up_for,
    red_answer,
)
from app.safety.boundary import Surface
from app.safety.not_feeling_well import (
    QUITE_A_LOT,
    Line,
    WhatToDoNow,
    call_clinic_card,
    not_feeling_well,
)
from app.safety.red_flags import Feeling, Flag, is_red
from app.state.service import RECOMPUTE_SCOPES, render_from_state

TAP = FeelingTap.__tablename__
NOTE = FeelingNote.__tablename__
NOT_FEELING_WELL = "not_feeling_well"
"""The flow a red word opens (E13/E14): the client's, named here so it opens the same one."""


class NoSuchTap(Refusal):
    """No tap by that id on this profile."""


class AlreadyAnswered(Refusal):
    """A tap asks one thing, once. This one has its answer."""


class NotAnAnswer(Refusal):
    """That is not one of the answers this tap's question offered, or it asked nothing."""


@dataclass(frozen=True, slots=True)
class Question:
    follow_up: FollowUp
    words: str
    answers: tuple[tuple[Answer, str], ...]


@dataclass(frozen=True, slots=True)
class RedPath:
    """What a red word did: the flag, the ladder, how many on his list had a notice, and the
    not-feeling-well card's own reassurance and closing line."""

    flag: Flag
    escalation: Ladder | None
    """The ladder (E11-06, ADR 0005): the one record of who is told, and in what order."""
    notices: int
    lines: tuple[str, ...]
    card: WhatToDoNow
    opens: str = NOT_FEELING_WELL


@dataclass(frozen=True, slots=True)
class Tapped:
    tap: FeelingTap
    language: str
    question: Question | None
    lines: tuple[str, ...]
    red: RedPath | None


@dataclass(frozen=True, slots=True)
class Answered:
    tap: FeelingTap
    note: FeelingNote | None
    red: RedPath | None
    note_withheld_because: str | None = None
    clinic_card: tuple[Line, ...] = ()
    """The not-feeling-well table's middle row, when his answer is it — it began yesterday or
    before, it is more than yesterday, or a medicine started in the last fourteen days lists
    this word as a watch-out: call the clinic today (E13-02). Empty otherwise."""


A_DAY_OR_MORE_ANSWERS = frozenset({Answer.YESTERDAY, Answer.FEW_DAYS, Answer.WEEK_OR_MORE})
"""Answers to "since when" that are a day or more: the table's "lasting a day or more"."""


async def _language(session: AsyncSession, context: KeyContext, asked: str | None) -> str:
    if asked is not None:
        return language_of(asked)
    return language_of((await audited_profile_read(session, context)).language)


async def _red_path(
    session: AsyncSession,
    *,
    context: KeyContext,
    feeling: Feeling,
    code: str,
    store: ObjectStore,
    transcriber: Transcriber,
    registry: DrugRegistry,
    via: Via,
) -> tuple[uuid.UUID, RedPath]:
    """The not-feeling-well button, pressed with his word: E13's whole flow, server-side.

    His word is the words kept, and the flag is the word he tapped (`feeling`), not one
    heard back from it. The button writes the moment and the flag first and keeps them, tells
    everyone on his emergency list, writes the ladder, sets the day's posture, and renders the
    what-to-do card — the urgent one, "Nura does not decide what is wrong." last. The flag and
    the ladder are read back by the moment they rest on."""
    done = await not_feeling_well(
        session,
        context=context,
        store=store,
        transcriber=transcriber,
        registry=registry,
        via=via,
        words=WORDS[code][feeling],
        language=code,
        feeling=feeling,
    )
    assert done.event_id is not None  # the red path always writes the moment
    flags = await audited_read(
        session, Flag, context, Scope.EMERGENCY, where=(Flag.event_id == done.event_id,)
    )
    flag = flags[0]
    ladders = await audited_read(
        session, Ladder, context, Scope.EMERGENCY, where=(Ladder.flag_id == flag.id,)
    )
    return done.event_id, RedPath(
        flag=flag,
        escalation=ladders[0] if ladders else None,
        notices=len(done.notified_person_ids),
        lines=tuple(line.text for line in done.lines),
        card=done,
    )


async def record_tap(
    session: AsyncSession,
    *,
    context: KeyContext,
    word: Feeling,
    registry: DrugRegistry,
    store: ObjectStore,
    transcriber: Transcriber,
    via: Via,
    language: str | None = None,
) -> Tapped:
    """His tap on the cloud. A red word takes the red-flag path first and asks nothing."""
    moment = utcnow()
    if is_red(word):
        code = await _language(session, context, language)
        event_id, red = await _red_path(
            session,
            context=context,
            feeling=word,
            code=code,
            store=store,
            transcriber=transcriber,
            registry=registry,
            via=via,
        )
        tap = await audited_write(
            session,
            FeelingTap,
            context,
            Scope.EMERGENCY,
            event_id=event_id,
            word=word,
            red=True,
            flag_id=red.flag.id,
            follow_up=None,
            emphasised=False,
            reasons=[],
            cloud_state_id=None,
            by_person_id=context.person_id,
            tapped_at=moment,
        )
        return Tapped(tap=tap, language=code, question=None, lines=red.lines, red=red)

    event = await record_event(
        session,
        context=context,
        kind=EventKind.SYMPTOM,
        occurred_at=moment,
        label=word.value,
        source_channel=SourceChannel.APP,
    )
    code = await _language(session, context, language)
    situation = await read_situation(session, context=context, registry=registry)
    on_cloud = next((item for item in weigh(situation) if item.word is word), None)
    yesterday = local_date(moment, context).toordinal() - 1
    said_yesterday = any(
        said.word is word and local_date(said.at, context).toordinal() == yesterday
        for said in situation.said
    )
    follow_up = follow_up_for(word, said_yesterday=said_yesterday)
    tap = await audited_write(
        session,
        FeelingTap,
        context,
        Scope.RECORDS,
        event_id=event.id,
        word=word,
        red=False,
        flag_id=None,
        follow_up=follow_up,
        emphasised=bool(on_cloud and on_cloud.emphasised),
        reasons=[] if on_cloud is None else [reason.as_json() for reason in on_cloud.reasons],
        cloud_state_id=None if situation.state is None else situation.state.id,
        by_person_id=context.person_id,
        tapped_at=moment,
    )
    if follow_up is None:
        return Tapped(tap=tap, language=code, question=None, lines=FINE_LINES[code], red=None)
    question = Question(
        follow_up=follow_up,
        words=QUESTIONS[code][follow_up],
        answers=tuple((answer, ANSWER_WORDS[code][answer]) for answer in ANSWERS[follow_up]),
    )
    return Tapped(tap=tap, language=code, question=question, lines=(), red=None)


async def answer_tap(
    session: AsyncSession,
    *,
    context: KeyContext,
    tap_id: uuid.UUID,
    answer: Answer,
    registry: DrugRegistry,
    store: ObjectStore,
    transcriber: Transcriber,
    via: Via,
    language: str | None = None,
) -> Answered:
    """His one answer. A yes that makes the word red takes the red-flag path, and there is no
    note; anything else is read into a note rendered from State under the boundary line."""
    found = await audited_read(
        session, FeelingTap, context, Scope.RECORDS, where=(FeelingTap.id == tap_id,)
    )
    if not found:
        raise NoSuchTap(f"no tap {tap_id} on profile {context.profile_id}")
    tap = found[0]
    if tap.answer is not None:
        raise AlreadyAnswered("this tap has its answer")
    if tap.follow_up is None or answer not in ANSWERS[tap.follow_up]:
        raise NotAnAnswer(f"{answer} does not answer this tap")
    code = await _language(session, context, language)
    red_word = red_answer(tap.word, tap.follow_up, answer)
    red: RedPath | None = None
    if red_word is not None:
        _, red = await _red_path(
            session,
            context=context,
            feeling=red_word,
            code=code,
            store=store,
            transcriber=transcriber,
            registry=registry,
            via=via,
        )
        tap.flag_id = red.flag.id
    tap.answer = answer
    tap.answered_at = utcnow()
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.EMERGENCY if red is not None else Scope.RECORDS,
        target=TAP,
        target_id=tap.id,
        rows=1,
    )
    if red is not None:
        return Answered(tap=tap, note=None, red=red)
    # The table's middle row, by the button's own rule (E13-02): "more than yesterday" counts as
    # "quite a lot", "yesterday" or longer as "a day or more", and the tapped word is read
    # against a new medicine's monograph.
    clinic = await call_clinic_card(
        session,
        context=context,
        registry=registry,
        language=code,
        severity=QUITE_A_LOT if answer is Answer.MORE else None,
        lasting=answer in A_DAY_OR_MORE_ANSWERS,
        feelings=frozenset({tap.word}),
    )
    card = clinic or ()
    if not RECOMPUTE_SCOPES <= context.scopes:
        # A note is rendered from State, and this key cannot bring State up to the record.
        return Answered(
            tap=tap, note=None, red=None, note_withheld_because="no_state", clinic_card=card
        )
    note = await _render_note(
        session, context=context, tap=tap, answer=answer, registry=registry, code=code
    )
    return Answered(tap=tap, note=note, red=None, clinic_card=card)


async def _render_note(
    session: AsyncSession,
    *,
    context: KeyContext,
    tap: FeelingTap,
    answer: Answer,
    registry: DrugRegistry,
    code: str,
) -> FeelingNote:
    situation = await read_situation(session, context=context, registry=registry)
    composed = compose_note(tap.word, answer, situation, context, code)
    failing = composed.failures()
    if failing:
        raise NotPlainWords(failing)
    return await render_from_state(
        session,
        FeelingNote,
        context,
        Scope.RECORDS,
        state=situation.state,
        surface=Surface.FEELING_INFERENCE,
        boundary=composed.boundary,
        tap_id=tap.id,
        word=tap.word,
        answer=answer,
        language=composed.language,
        headline=composed.headline,
        lines=list(composed.lines),
        then=composed.then,
        voice=list(composed.voice),
        reasons=list(composed.reasons),
        outcome=composed.outcome,
        appointment_id=composed.appointment_id,
        created_at=utcnow(),
    )


REASON_SCOPES: dict[str, Scope] = {
    "new_medicine": Scope.MEDICINES,
    "reading_trend": Scope.READINGS,
}
"""The part of the record a note's reason rests on, where it is not the record's own: a medicine
line, his blood pressure facts. A note citing one is read only by a key holding that part
(ADR 0004: a row is read under the scope it rests on); the others are withheld by count."""


def note_scopes(note: FeelingNote) -> frozenset[Scope]:
    """Every part a note shows or cites: the record's, and each reason's own."""
    return frozenset(
        {Scope.RECORDS}
        | {REASON_SCOPES[r["code"]] for r in note.reasons if r.get("code") in REASON_SCOPES}
    )


@audited(Action.READ, Scope.RECORDS, NOTE)
async def recent_notes(
    session: AsyncSession, *, context: KeyContext, limit: int = 20
) -> tuple[list[FeelingNote], int]:
    """The notes this key may read, newest first, and how many were withheld because they
    rest on a part of the record the key does not hold. Never a silent gap."""
    found = await audited_read(
        session,
        FeelingNote,
        context,
        Scope.RECORDS,
        order_by=(FeelingNote.created_at.desc(),),
        limit=limit,
    )
    readable = [note for note in found if note_scopes(note) <= context.scopes]
    return readable, len(found) - len(readable)
