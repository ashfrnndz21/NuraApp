"""The ask bar's thinking trace (docs/design-direction.md, "Conversation, waiting and
'thinking'"): `recall_stream` yields one `AskStep` for each real part of the record it reads,
in the order it reads them, then the `Answer` — never an invented step, never an artificial
delay. `recall` (E03-05's existing surface) is `recall_stream`, drained, so the two can never
drift apart: this file only exercises the stream's own promises.
"""

from __future__ import annotations

import inspect
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

import app.search.ask as ask_module
from app.ingestion.objects import LocalObjectStore
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.regions import Region
from app.search.ask import STEP_KEYS, Answer, AskStep, Mode, recall, recall_stream
from app.search.retrieve import KeywordRetriever
from tests.medicines_support import REGISTRY, let_in
from tests.timeline_support import record


async def _steps(
    session: AsyncSession, context: KeyContext, question: str, tmp_path: Path
) -> tuple[list[str], Answer]:
    keys: list[str] = []
    answer: Answer | None = None
    async for event in recall_stream(
        session,
        context=context,
        question=question,
        mode=Mode.TEXT,
        retriever=KeywordRetriever(),
        store=LocalObjectStore(tmp_path, Region.SG),
        registry=REGISTRY,
    ):
        if isinstance(event, AskStep):
            keys.append(event.key)
        else:
            answer = event
    assert answer is not None
    return keys, answer


async def test_a_full_key_hears_one_step_per_part_in_the_order_they_are_read(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    keys, answer = await _steps(sg, rec.mei, "what was my blood pressure", tmp_path)
    # Every part opened to Mei's key is read, in `STEP_KEYS` order — never scrambled, never a
    # part skipped that her key opens.
    assert keys == list(STEP_KEYS)
    assert answer.answered


async def test_a_narrow_key_never_hears_a_step_for_a_part_its_scope_does_not_open(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    # A caregiver let in for medicines and nothing else on the record: her key opens no visit,
    # no reading, no paper — so the stream must never say Nura is checking one, not even to
    # name it as withheld. A step's existence is itself information (spec).
    narrow = await let_in(
        sg,
        rec.owner,
        phone="+6588880001",
        name="Aminah",
        role=KeyRole.HELPER,
        scopes={Scope.PROFILE, Scope.ASK, Scope.MEDICINES, Scope.EMERGENCY},
    )
    keys, answer = await _steps(sg, narrow, "what is my medicine", tmp_path)
    assert keys == ["medicines"]
    assert {Scope.VISITS, Scope.READINGS, Scope.RECORDS} <= set(answer.withheld)


async def test_the_stream_matches_recall_for_the_same_question(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    _, streamed = await _steps(sg, rec.owner, "what did Dr Tan say", tmp_path)
    direct = await recall(
        sg,
        context=rec.owner,
        question="what did Dr Tan say",
        mode=Mode.TEXT,
        retriever=KeywordRetriever(),
        store=LocalObjectStore(tmp_path, Region.SG),
        registry=REGISTRY,
    )
    assert [line.text for line in streamed.lines] == [line.text for line in direct.lines]
    assert streamed.boundary == direct.boundary


async def test_a_fast_answer_is_not_held_back(sg: AsyncSession, tmp_path: Path) -> None:
    """The honesty rule: the ask is rule-based and fast, so nothing here may hold the answer
    back to make a "thinking" animation look real. Draining the whole stream — every real
    step, then the answer — takes a small fraction of a second; there is no `sleep` anywhere
    on the path (`app/search/ask.py` is grepped for it directly, so a later change cannot
    quietly add one back)."""
    assert "sleep(" not in inspect.getsource(ask_module)

    rec = await record(sg)
    started = time.monotonic()
    await _steps(sg, rec.mei, "what was my blood pressure", tmp_path)
    assert time.monotonic() - started < 1.0
