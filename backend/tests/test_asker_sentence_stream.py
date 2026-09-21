"""P1 (docs/design-direction.md "the answer streams sentence by sentence"): the `Asker` port's
one shared contract — `AskStep`s, then zero or more `AnswerDelta` (one per sentence of the
finished answer, text and cites together), then the `Answer` — holds for `RuleBasedAsker`
(`app.search.asker`) exactly as it does for `ClaudeAsker` (`backend/tests/test_ask_agent.py`),
so `POST /{id}/ask/stream` never has to know which asker answered. `RuleBasedAsker` never calls
a model; it only replays `recall_stream`'s own already-composed, already-verified lines as its
own `AnswerDelta`s.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.objects import LocalObjectStore
from app.regions import Region
from app.search.ask import Answer, Mode
from app.search.asker import AnswerDelta, RuleBasedAsker
from app.search.retrieve import KeywordRetriever
from tests.medicines_support import REGISTRY
from tests.timeline_support import record


async def test_rule_based_asker_streams_one_answer_delta_per_line_before_the_answer(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    asker = RuleBasedAsker()
    deltas: list[AnswerDelta] = []
    answer: Answer | None = None
    async for event in asker.ask_stream(
        sg,
        context=rec.owner,
        question="what was my blood pressure",
        mode=Mode.TEXT,
        retriever=KeywordRetriever(),
        store=LocalObjectStore(tmp_path, Region.SG),
        registry=REGISTRY,
        language="en",
    ):
        if isinstance(event, AnswerDelta):
            # A delta only ever follows every `AskStep`, and always before the `Answer` —
            # never interleaved with a step, and never after the final event.
            assert answer is None
            deltas.append(event)
        elif isinstance(event, Answer):
            answer = event

    assert answer is not None
    assert answer.answered
    # One delta per line of the finished answer, in the same order, text and cites both —
    # never a delta the final answer does not also carry, and never one dropped.
    assert [d.text for d in deltas] == [line.text for line in answer.lines]
    assert [d.cites for d in deltas] == [line.cites for line in answer.lines]


async def test_rule_based_asker_streams_no_deltas_when_nothing_answers(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """The honest "not written down" path: nothing to say yet, so nothing streams as a
    sentence — `answer.honest` carries the line instead, exactly as `recall_stream` always
    gave it."""
    rec = await record(sg)
    asker = RuleBasedAsker()
    deltas: list[AnswerDelta] = []
    answer: Answer | None = None
    async for event in asker.ask_stream(
        sg,
        context=rec.owner,
        question="do I have cancer",
        mode=Mode.TEXT,
        retriever=KeywordRetriever(),
        store=LocalObjectStore(tmp_path, Region.SG),
        registry=REGISTRY,
        language="en",
    ):
        if isinstance(event, AnswerDelta):
            deltas.append(event)
        elif isinstance(event, Answer):
            answer = event
    assert answer is not None
    assert not answer.answered
    assert deltas == []
    assert answer.honest
