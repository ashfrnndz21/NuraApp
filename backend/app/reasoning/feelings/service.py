"""The door for the feelings: a tap on the cloud, its one answer, and the notes (E17-02).

**A red word goes first.** A tap on a red word — or a yes to the question that tells a red
variant apart — takes the not-feeling-well button's own red-flag path (E13/E14,
`app.safety.not_feeling_well.escalate`), unchanged: the moment it was said
(`record_the_moment`, under the emergency scope, so any key holding that scope can start it),
the flag on it, kept so a later refusal cannot take it back (`write_flag_kept`), a notice to
everyone on his emergency list, and the ladder for delivery to walk (`roster_for`,
`Escalation`, kept) — before the cloud is read, before anything is ranked, before any note.
What the tap said is his word, so what the path is given to have "heard" is that word, sure,
and no artefact. There is no note for a red word: what comes back is the reassurance and
closing line of the urgent not-feeling-well card (`Surface.NOT_FEELING_WELL`, urgent) and the
flow to open, where the card with the calls is.

**Every other word asks one thing back.** The tap is a SYMPTOM event in his word and a
`FeelingTap` naming why the word was on the cloud; "Fine today" says thank you and asks
nothing. His answer is the tap's one change; the note it is read into is rendered from State
under the boundary line, or not written at all (`render_from_state`).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
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
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.ingestion.transcribe import Transcript
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
from app.safety.boundary import Surface, boundary_lines
from app.safety.not_feeling_well import Captured, family_of
from app.safety.not_feeling_well import escalate as escalate_red_flag
from app.safety.red_flags import Escalation, Feeling, Flag, is_red
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
    escalation: Escalation | None
    notices: int
    lines: tuple[str, ...]
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


async def _language(session: AsyncSession, context: KeyContext, asked: str | None) -> str:
    if asked is not None:
        return language_of(asked)
    return language_of((await audited_profile_read(session, context)).language)


async def _red_path(
    session: AsyncSession, *, context: KeyContext, feeling: Feeling, code: str
) -> tuple[uuid.UUID, RedPath]:
    """E13's red-flag path, as the button takes it: nothing is read or ranked before it."""
    profile = await audited_profile_read(session, context)
    family = await family_of(session, context=context, profile=profile)
    said = Captured(
        artifact=None,
        transcript=Transcript(text=WORDS[code][feeling], confidence=1.0, language=code),
        by_voice=False,
    )
    escalated = await escalate_red_flag(
        session, context=context, captured=said, feeling=feeling, family=family
    )
    told = None
    if not escalated.suppressed and family.chief is not None:
        told = family.chief.display_name or None
    lines = boundary_lines(
        Surface.NOT_FEELING_WELL, code, told=told, urgent=not escalated.suppressed
    )
    return escalated.event.id, RedPath(
        flag=escalated.flag,
        escalation=escalated.ladder,
        notices=len(escalated.notices),
        lines=lines,
    )


async def record_tap(
    session: AsyncSession,
    *,
    context: KeyContext,
    word: Feeling,
    registry: DrugRegistry,
    language: str | None = None,
) -> Tapped:
    """His tap on the cloud. A red word takes the red-flag path first and asks nothing."""
    moment = utcnow()
    if is_red(word):
        code = await _language(session, context, language)
        event_id, red = await _red_path(session, context=context, feeling=word, code=code)
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
        _, red = await _red_path(session, context=context, feeling=red_word, code=code)
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
    if not RECOMPUTE_SCOPES <= context.scopes:
        # A note is rendered from State, and this key cannot bring State up to the record.
        return Answered(tap=tap, note=None, red=None, note_withheld_because="no_state")
    note = await _render_note(
        session, context=context, tap=tap, answer=answer, registry=registry, code=code
    )
    return Answered(tap=tap, note=note, red=None)


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


@audited(Action.READ, Scope.RECORDS, NOTE)
async def recent_notes(
    session: AsyncSession, *, context: KeyContext, limit: int = 20
) -> Sequence[FeelingNote]:
    """The notes, newest first: what he said, read into things to tell the doctor."""
    return await audited_read(
        session,
        FeelingNote,
        context,
        Scope.RECORDS,
        order_by=(FeelingNote.created_at.desc(),),
        limit=limit,
    )
