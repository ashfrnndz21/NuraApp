"""Ask becomes a conversation (W2): the thread a question is kept on, and the memory of it.

`current_conversation` is the one continuing thread a person has with Nura about one profile
— started the first time he asks anything, reused across days, until `start_new_conversation`
closes it on his own "New conversation" (`POST /profiles/{id}/conversations`). A caregiver and
the patient himself never share a thread: `Conversation.person_id` is who asked, from the key
context, so a caregiver's thread stays hers, about him by name.

Three layers of memory, one module, never the whole record in a prompt:

1. **The record itself** — every fact the agent asker already reaches only through its own
   audited, scope-gated tools (`app.llm.ask_agent`). Nothing here reads it directly.
2. **Conversation memory** (`memory_for`) — the last `KEPT_VERBATIM` turns, verbatim, plus a
   running plain summary of everything older, written by `summarize_turn`: deterministic,
   rule-based, one line per folded turn ("he asked about X; Nura found Y"), never a model. A
   Claude-backed rewrite could replace `summarize_turn` behind the existing dev/demo gate
   (`app.llm.residency.allow_external_model`) later; nothing here calls one.
3. **Attention memory** — not built here. Opt-in only (`signals.search_topics`, decision D3),
   and out of this story's time box; a thread today keeps nothing past itself once closed.

Neither table holds a turn's words (`app.search.models`'s own docstring): a question was
already kept as a MESSAGE artefact before this story (`app.search.ask._keep_question`); the
answer becomes one the same way here (`_keep_answer`), and `memory_for` reads both back by
their `storage_key` to build the verbatim window and, once, to fold the oldest turn into the
summary.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.db import utcnow
from app.errors import Refusal
from app.ingestion.objects import ObjectStore, sha256_of
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import Artifact, ArtifactKind, SourceChannel
from app.search.ask import Answer
from app.search.models import Conversation, Turn


class NoSuchConversation(Refusal):
    """No conversation by that id on this profile, for this person — his own thread and a
    caregiver's are never the same row (the module docstring)."""

KEPT_VERBATIM = 6
"""The most recent turns kept word for word in `memory_for`; anything older is folded into
`Conversation.summary` instead (the brief: "the last 6 turns verbatim + a running plain
summary of earlier turns")."""

QUESTION_SNIPPET = 80


@dataclass(frozen=True, slots=True)
class TurnMemory:
    """One turn, verbatim, for the model's own context — never re-checked against a scope,
    since it is read back only for the same key that wrote it, on the same thread."""

    question: str
    answer_lines: tuple[str, ...]
    honest: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConversationMemory:
    """What `ClaudeAsker.ask_stream` is handed for a follow-up: the thread's id, its most
    recent turns verbatim, and the plain summary of everything older (`None` for a thread
    still inside its verbatim window)."""

    conversation_id: uuid.UUID
    recent: tuple[TurnMemory, ...]
    summary: str | None


async def current_conversation(session: AsyncSession, *, context: KeyContext) -> Conversation:
    """The person's own continuing thread on this profile: the newest one not yet closed, or
    a fresh one if he has never asked anything, or closed his last thread and not yet asked
    again. Tied by `seq` (#192/#218): "any latest query needs a deterministic tie-breaker"."""
    found = await audited_read(
        session,
        Conversation,
        context,
        Scope.ASK,
        where=(
            Conversation.person_id == context.person_id,
            Conversation.closed_at.is_(None),
        ),
        order_by=(Conversation.seq.desc(),),
        limit=1,
    )
    if found:
        return found[0]
    moment = utcnow()
    return await audited_write(
        session,
        Conversation,
        context,
        Scope.ASK,
        person_id=context.person_id,
        started_at=moment,
        last_turn_at=moment,
    )


async def start_new_conversation(session: AsyncSession, *, context: KeyContext) -> Conversation:
    """His own "New conversation": close whichever thread is open now (if any) and start a
    fresh one. The closed thread's turns are untouched — only its own `closed_at` is set, so
    `current_conversation` never picks it up again."""
    open_now = await audited_read(
        session,
        Conversation,
        context,
        Scope.ASK,
        where=(
            Conversation.person_id == context.person_id,
            Conversation.closed_at.is_(None),
        ),
        order_by=(Conversation.seq.desc(),),
        limit=1,
    )
    moment = utcnow()
    if open_now:
        open_now[0].closed_at = moment
        await session.flush()
    return await audited_write(
        session,
        Conversation,
        context,
        Scope.ASK,
        person_id=context.person_id,
        started_at=moment,
        last_turn_at=moment,
    )


async def conversation_by_id(
    session: AsyncSession, *, context: KeyContext, conversation_id: uuid.UUID
) -> Conversation:
    """His thread, or a caregiver's — never the other's: a conversation belongs to whoever
    asked it into being (`Conversation.person_id`), so a caregiver reaching for a thread that
    is not hers, or that is not on this profile, is refused the same as one that never
    existed."""
    found = await audited_read(
        session, Conversation, context, Scope.ASK, where=(Conversation.id == conversation_id,)
    )
    if not found or found[0].person_id != context.person_id:
        raise NoSuchConversation(f"no conversation {conversation_id} for this key")
    return found[0]


async def turns_of(
    session: AsyncSession, *, context: KeyContext, conversation: Conversation
) -> list[Turn]:
    """Every turn on this thread, oldest first — the read a `GET .../conversations/{id}`
    shows as the thread."""
    found = await audited_read(
        session,
        Turn,
        context,
        Scope.ASK,
        where=(Turn.conversation_id == conversation.id,),
        order_by=(Turn.seq.asc(),),
    )
    return list(found)


async def _artifact_text(
    session: AsyncSession, *, context: KeyContext, store: ObjectStore, artifact_id: uuid.UUID
) -> str:
    found = await audited_read(
        session, Artifact, context, Scope.ASK, where=(Artifact.id == artifact_id,)
    )
    if not found:
        return ""
    return (await store.get(found[0].storage_key)).decode("utf-8")


async def _keep_answer(
    session: AsyncSession, *, context: KeyContext, store: ObjectStore, answer: Answer
) -> Artifact:
    """The answer's own lines, kept as a MESSAGE artefact by reference, the same way the
    question already is (`app.search.ask._keep_question`): no row holds the words."""
    payload = {
        "lines": [
            {"text": line.text, "cite_kinds": [cite.kind for cite in line.cites]}
            for line in answer.lines
        ],
        "honest": list(answer.honest),
    }
    data = json.dumps(payload).encode("utf-8")
    digest = sha256_of(data)
    key = f"answers/{context.profile_id}/{digest}"
    await store.put(key, data)
    moment = utcnow()
    return await audited_write(
        session,
        Artifact,
        context,
        Scope.ASK,
        kind=ArtifactKind.MESSAGE,
        storage_key=key,
        content_type="application/json",
        sha256=digest,
        captured_at=moment,
        source_channel=SourceChannel.APP,
        region=store.region,
        stored_at=moment,
    )


async def turn_view(
    session: AsyncSession, *, context: KeyContext, store: ObjectStore, turn: Turn
) -> tuple[str, list[str], list[str]]:
    """One turn's own words, read back from its two artefacts for `GET
    .../conversations/{id}`: the question, the answer's lines, and its honest lines (empty
    unless the turn was never answered)."""
    question_text = await _artifact_text(
        session, context=context, store=store, artifact_id=turn.question_artifact_id
    )
    if turn.answer_artifact_id is None:
        return question_text, [], []
    raw = await _artifact_text(
        session, context=context, store=store, artifact_id=turn.answer_artifact_id
    )
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {}
    lines = [entry.get("text", "") for entry in payload.get("lines", [])]
    honest = list(payload.get("honest", []))
    return question_text, lines, honest


def summarize_turn(question: str, answer_line_count: int, answered: bool) -> str:
    """One deterministic, rule-written line for a turn folded out of the verbatim window:
    "he asked about X; Nura found Y" — never a model (the module docstring)."""
    snippet = " ".join(question.split())[:QUESTION_SNIPPET]
    found = (
        f"Nura found {answer_line_count} line{'s' if answer_line_count != 1 else ''}"
        if answered
        else "Nura found nothing written down"
    )
    return f"He asked about {snippet}; {found}."


async def record_turn(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    conversation: Conversation,
    question_artifact_id: uuid.UUID,
    answer: Answer,
) -> Turn:
    """One turn, written onto a conversation: the answer kept as its own artefact, the turn
    row pointing at the two of them and nothing else, the conversation's own counters moved
    on, and the oldest turn outside the verbatim window folded into the summary if this turn
    pushed it out."""
    answer_artifact = (
        await _keep_answer(session, context=context, store=store, answer=answer)
        if answer.lines or answer.honest
        else None
    )
    turn = await audited_write(
        session,
        Turn,
        context,
        Scope.ASK,
        conversation_id=conversation.id,
        person_id=context.person_id,
        mode=answer.mode,
        language=answer.language,
        question_artifact_id=question_artifact_id,
        answer_artifact_id=None if answer_artifact is None else answer_artifact.id,
        answered=answer.answered,
        line_count=len(answer.lines),
    )
    moment = utcnow()
    conversation.turn_count += 1
    conversation.last_turn_at = moment
    await session.flush()

    if conversation.turn_count - conversation.summarized_through > KEPT_VERBATIM:
        older = await audited_read(
            session,
            Turn,
            context,
            Scope.ASK,
            where=(Turn.conversation_id == conversation.id,),
            order_by=(Turn.seq.asc(),),
            limit=conversation.summarized_through + 1,
        )
        if len(older) > conversation.summarized_through:
            to_fold = older[conversation.summarized_through]
            question_text = await _artifact_text(
                session, context=context, store=store, artifact_id=to_fold.question_artifact_id
            )
            line = summarize_turn(question_text, to_fold.line_count, to_fold.answered)
            conversation.summary = (
                f"{conversation.summary}\n{line}" if conversation.summary else line
            )
            conversation.summarized_through += 1
            await session.flush()

    return turn


async def memory_for(
    session: AsyncSession, *, context: KeyContext, store: ObjectStore, conversation: Conversation
) -> ConversationMemory:
    """The conversation memory `ClaudeAsker.ask_stream` is handed for a follow-up: the last
    `KEPT_VERBATIM` turns, verbatim, and the summary of everything older."""
    recent_rows = await audited_read(
        session,
        Turn,
        context,
        Scope.ASK,
        where=(Turn.conversation_id == conversation.id,),
        order_by=(Turn.seq.desc(),),
        limit=KEPT_VERBATIM,
    )
    recent: list[TurnMemory] = []
    for row in reversed(recent_rows):
        question_text = await _artifact_text(
            session, context=context, store=store, artifact_id=row.question_artifact_id
        )
        lines: tuple[str, ...] = ()
        honest: tuple[str, ...] = ()
        if row.answer_artifact_id is not None:
            raw = await _artifact_text(
                session, context=context, store=store, artifact_id=row.answer_artifact_id
            )
            try:
                payload = json.loads(raw) if raw else {}
            except ValueError:
                payload = {}
            lines = tuple(entry.get("text", "") for entry in payload.get("lines", []))
            honest = tuple(payload.get("honest", []))
        recent.append(TurnMemory(question=question_text, answer_lines=lines, honest=honest))
    return ConversationMemory(
        conversation_id=conversation.id, recent=tuple(recent), summary=conversation.summary
    )


__all__ = [
    "KEPT_VERBATIM",
    "ConversationMemory",
    "NoSuchConversation",
    "TurnMemory",
    "conversation_by_id",
    "current_conversation",
    "memory_for",
    "record_turn",
    "start_new_conversation",
    "summarize_turn",
    "turn_view",
    "turns_of",
]
