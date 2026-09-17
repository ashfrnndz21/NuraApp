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
from app.search.ask import Answer, AskStep, Mode, recall_stream
from app.search.retrieve import Retriever


@dataclass(frozen=True, slots=True)
class AnswerDelta:
    """One chunk of the final answer's own text, sent as it is put together. Never a step,
    never a fact off the record by itself — `ClaudeAsker` only ever yields one after the whole
    answer's lines have already passed every check (`verified`, the conclusion-and-advice
    blocklist, the cite check): each delta is one already-safe line's text, in the order it
    will appear. `RuleBasedAsker` never yields one; its answer has always arrived whole, as
    `recall_stream`'s own last item, and still does."""

    text: str


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
    ) -> AsyncIterator[AskStep | AnswerDelta | Answer]:
        """`recall_stream`'s own signature, so `asker_for`'s choice is a drop-in for the
        route that calls it."""
        ...


class RuleBasedAsker:
    """Today's asker, unchanged, and the default: `recall_stream`, behind the port. No call
    outside this deployment, so no reach to audit and no `AnswerDelta` — the answer arrives
    whole, exactly as it always has."""

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
    ) -> AsyncIterator[AskStep | AnswerDelta | Answer]:
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
            yield event


__all__ = ["AnswerDelta", "Asker", "RuleBasedAsker"]
