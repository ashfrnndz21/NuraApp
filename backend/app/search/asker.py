"""The Asker port: what answers a question about his own record, streamed.

Until now `app.search.ask.recall_stream` was the only way to ask: a rule-based retriever reads
his record scope by scope and answers from templates. `RuleBasedAsker` is exactly that,
unchanged, behind a port — so a second asker can exist without recall_stream's caller (`POST
/{id}/ask/stream`, `app.channels.api.timeline`) changing at all. `app.llm.ask_agent.
ClaudeAsker` is the other one: it decides for itself what to look at, and its trace is the
model's own real tool calls, one `AskStep` per call, never a scripted or delayed one
(docs/design-direction.md "Conversation, waiting and thinking"). `asker_for`
(`app.search.asker_provider`) is the one place a deployment chooses between them.

Lives here, not beside `app.search.ask`, for the reason `app.search.narrate` gives for the
Narrator port: nothing under `app/search/` may import the SDK or reach the network
(`backend/CLAUDE.md`; `tests/test_recall.py::test_recall_calls_no_model`), so `ClaudeAsker`
lives beside `app/llm/client.py` instead.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.drugs.registry import DrugRegistry
from app.ingestion.objects import ObjectStore
from app.keys.context import KeyContext
from app.search.ask import Answer, AskStep, Cite, Mode, recall_stream
from app.search.conversation import ConversationMemory
from app.search.retrieve import Retriever


@dataclass(frozen=True, slots=True)
class AnswerDelta:
    """One sentence of the final answer, sent the moment it is safe to say — the wire's own
    `answer_sentence` event (`app.channels.api.timeline`). Never a step, never a fact off the
    record by itself: both askers only ever yield one after the whole answer's lines have
    already passed every check (`verified` at Ask's own profile, the conclusion-and-advice
    blocklist, the cite check) — each delta is one already-safe line's text and the exact
    cites it rests on, in the order it will appear, so a caller never has to reassemble cites
    from the final `Answer` alone while a sentence is still arriving. `ClaudeAsker` yields one
    per line of the model's own checked answer; `RuleBasedAsker` yields one per line of
    `recall_stream`'s own already-composed, already-verified answer — the contract is the
    same however the answer was built, so a caller (`web/src/screens/Ask.tsx`) never has to
    know which asker it is holding."""

    text: str
    cites: tuple[Cite, ...] = ()


class Asker(Protocol):
    """Answers a question about his own record, streamed: one `AskStep` per real read, in the
    order it happened, zero or more `AnswerDelta` for the finished answer's own text as it is
    sent, then the `Answer`, last — the same contract `recall_stream` already promises, so a
    caller (`POST /{id}/ask/stream`) never has to know which asker it is holding."""

    external_processor: str | None
    """Not None when every ask reaches a processor outside the region (`ClaudeAsker`, ADR
    0017): a caller writes the reach to the audit trail once per ask, the way `ClaudeNarrator`
    already does for narration. None for an asker that never reaches outside this deployment
    (`RuleBasedAsker`)."""

    def ask_stream(
        self,
        session: AsyncSession,
        *,
        context: KeyContext,
        question: str,
        mode: Mode,
        retriever: Retriever,
        store: ObjectStore,
        registry: DrugRegistry | None = None,
        language: str | None = None,
        history: ConversationMemory | None = None,
    ) -> AsyncIterator[AskStep | AnswerDelta | Answer]:
        """`recall_stream`'s own signature, so `asker_for`'s choice is a drop-in for the
        route that calls it. `history` is the conversation memory (W2,
        `app.search.conversation.memory_for`) for a follow-up on an existing thread — `None`
        for a first question, and unused by `RuleBasedAsker`, which never resolves a
        follow-up's "that" the way the agent asker can."""
        ...


class RuleBasedAsker:
    """Today's asker, and the default: `recall_stream`, behind the port. No call outside this
    deployment, so no reach to audit. Its answer has always arrived whole from
    `recall_stream` — the retriever picks every cited line before any of them is said — but
    the sentence-gated wire contract (`AnswerDelta` per line, then the `Answer`) still holds
    for it: the moment `recall_stream` yields its `Answer`, this replays each of its own
    lines, already composed and already past `words.verified` inside `recall_stream` itself,
    as its own `AnswerDelta`, in order, before yielding the `Answer` in turn — so the web
    client has exactly one code path for both askers, and the fixture asker used in
    screenshots and e2e specs (a `RuleBasedAsker` over seeded demo data) exercises the real
    contract too, not a stand-in for it."""

    external_processor: str | None = None

    async def ask_stream(
        self,
        session: AsyncSession,
        *,
        context: KeyContext,
        question: str,
        mode: Mode,
        retriever: Retriever,
        store: ObjectStore,
        registry: DrugRegistry | None = None,
        language: str | None = None,
        history: ConversationMemory | None = None,
    ) -> AsyncIterator[AskStep | AnswerDelta | Answer]:
        # `history` is never used to resolve a follow-up's "that" (the rule-based answer never
        # does that) — only its two clarify-specific signals (W2): whether the turn right
        # before this one on the same thread was itself a clarifying question (never two in a
        # row about the same thing), and a tap's own already-resolved referent, if this turn
        # carries one.
        skip_clarify = bool(history is not None and history.recent and history.recent[-1].was_clarify)
        focus = None if history is None else history.resolved_focus
        async for event in recall_stream(
            session,
            context=context,
            question=question,
            mode=mode,
            retriever=retriever,
            store=store,
            registry=registry,
            language=language,
            focus=focus,
            skip_clarify=skip_clarify,
        ):
            if isinstance(event, Answer):
                if event.clarify is not None:
                    yield AnswerDelta(text=event.clarify.question, cites=())
                for line in event.lines:
                    yield AnswerDelta(text=line.text, cites=line.cites)
            yield event


__all__ = ["AnswerDelta", "Asker", "RuleBasedAsker"]
