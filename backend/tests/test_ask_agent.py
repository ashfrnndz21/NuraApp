"""`ClaudeAsker` (`app.llm.ask_agent`), Ask as an agent: the tool-use loop, one `AskStep` per
tool call that actually runs, a withheld scope's tool never offered, a cite outside this ask's
own tool results dropped, a diagnosis line dropped, the boundary always the catalogue's own,
a refusal falling back to the rule-based answer, caregiver voice, and the one
`EXTERNAL_MODEL_PROCESSOR` audit line an ask that reaches the model writes.

Every test here mocks the `anthropic` client (`FakeClient`) — the same rule
`tests/test_claude_feed_adapters.py` holds `ClaudeSearcher`/`ClaudeCompressor` to: deterministic
inputs, no network.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.channels.about_him import Reader
from app.delivery.feed.compress import Found
from app.delivery.timeline_strings import honest_lines
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.photos import store_photo
from app.ingestion.review import EXTERNAL_MODEL_PROCESSOR, review_photo
from app.keys.scopes import KeyRole, Scope
from app.llm.ask_agent import (
    Cite,
    ClaudeAsker,
    _answer_from_payload,
    _boundary_rewrite,
    _parse_answer,
    _starts_with_dangling_opener,
    _ToolLine,
    _tools_for,
)
from app.memory.models import SourceChannel
from app.regions import Region
from app.safety.boundary import Surface, boundary_lines
from app.search.ask import Answer, AskStep, Mode, recall
from app.search.asker import AnswerDelta
from app.search.retrieve import KeywordRetriever
from tests.medicines_support import REGISTRY, let_in
from tests.paper import LAB_REPORT_VITALS, PAPER, placeholder_png
from tests.timeline_support import record, trail


@dataclass
class FakeMessage:
    stop_reason: str
    content: list[dict[str, Any]] = field(default_factory=list)


class FakeMessages:
    def __init__(self, responses: list[FakeMessage]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> FakeMessage:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses: list[FakeMessage]) -> None:
        self.messages = FakeMessages(responses)


class FakeSearcher:
    """Never called in these tests: every scenario here answers from the record alone."""

    def search(self, kind: str, terms: Any, domains: Any) -> list[Found]:
        return []

    def find(self, words: Any, domains: Any, *, media: str | None = None) -> list[Found]:
        return []


def _final(lines: list[dict[str, Any]], boundary: str = "ignored") -> FakeMessage:
    payload = {"lines": lines, "boundary": boundary}
    return FakeMessage(
        stop_reason="end_turn", content=[{"type": "text", "text": json.dumps(payload)}]
    )


def _tool_call(tool_id: str, name: str, args: dict[str, Any] | None = None) -> FakeMessage:
    return FakeMessage(
        stop_reason="tool_use",
        content=[{"type": "tool_use", "id": tool_id, "name": name, "input": args or {}}],
    )


async def _drive(
    asker: ClaudeAsker, sg: AsyncSession, context: Any, question: str, tmp_path: Path
) -> tuple[list[str], list[str], Any]:
    steps: list[str] = []
    deltas: list[str] = []
    answer = None
    async for event in asker.ask_stream(
        sg,
        context=context,
        question=question,
        mode=Mode.TEXT,
        retriever=KeywordRetriever(),
        store=LocalObjectStore(tmp_path, Region.SG),
        registry=REGISTRY,
        language="en",
    ):
        if isinstance(event, AskStep):
            steps.append(event.key)
        elif isinstance(event, AnswerDelta):
            deltas.append(event.text)
        else:
            answer = event
    assert answer is not None
    return steps, deltas, answer


async def test_the_tool_use_loop_runs_two_rounds_one_step_per_call_that_ran(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_medicines"),
            _final(
                [
                    {
                        "text": "Your blood pressure tablet is on your list of medicines.",
                        # A short, stable id ("m1", the first — and here only — medicine
                        # this ask read) is what the model is actually asked to copy back,
                        # never the row's own uuid.
                        "cites": ["m1"],
                    }
                ]
            ),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    steps, deltas, answer = await _drive(asker, sg, rec.owner, "what is my medicine", tmp_path)

    assert len(client.messages.calls) == 2
    # One step for the one tool that actually ran — never one for readings, visits or records,
    # which the model never asked to look at.
    assert steps == ["medicines"]
    assert [line.text for line in answer.lines] == [
        "Your blood pressure tablet is on your list of medicines."
    ]
    assert deltas == ["Your blood pressure tablet is on your list of medicines."]
    # The boundary is always the catalogue's own line for the surface and language — never
    # whatever the model wrote (`_final`'s payload said "ignored").
    assert answer.boundary == boundary_lines(Surface.RECALL, "en", doctor=None)
    assert "ignored" not in " ".join(answer.boundary)


async def test_a_withheld_scope_offers_no_tool(sg: AsyncSession) -> None:
    rec = await record(sg)
    narrow = await let_in(
        sg,
        rec.owner,
        phone="+6588880002",
        name="Aminah",
        role=KeyRole.HELPER,
        scopes={Scope.PROFILE, Scope.ASK, Scope.VISITS, Scope.EMERGENCY},
    )
    tools = _tools_for(narrow)
    # Medicines, readings, records and feelings all rest on scopes this key does not hold: not
    # one of their tools is offered, so the model can never even name the withheld part.
    assert "read_medicines" not in tools
    assert "read_readings" not in tools
    assert "read_records" not in tools
    assert "read_feelings" not in tools
    assert "read_visits" in tools
    assert "search_online" in tools  # never scope-gated: not a read of his record


def test_a_cite_outside_this_asks_tool_results_is_dropped() -> None:
    good_id = uuid.uuid4()
    known = {
        f"fact:{good_id}": _ToolLine(
            token=f"fact:{good_id}",
            text=f"fact:{good_id}: blood pressure 138/84 on 2026-09-02",
            cite=Cite(kind="fact", id=good_id),
        )
    }
    payload = {
        "lines": [
            {
                "text": "Your blood pressure was 138 over 84 on Wednesday 2 September.",
                "cites": [f"fact:{good_id}"],
            },
            {
                "text": "Your blood pressure was 999 over 999 on Thursday 1 January.",
                "cites": [f"fact:{uuid.uuid4()}"],
            },
        ]
    }
    answer = _answer_from_payload(payload, known, "en", Reader(his=True), Mode.TEXT)
    assert answer is not None
    # The line whose only cite is not among this ask's own tool results is dropped; the one
    # whose cite is real survives.
    assert [line.text for line in answer.lines] == [
        "Your blood pressure was 138 over 84 on Wednesday 2 September."
    ]
    assert answer.dropped == 1


def test_a_cite_matches_a_known_id_case_insensitively() -> None:
    """Short ids (`m1`, not a uuid) are what the model is asked to copy back — but it may
    still change the case. A line should not be thrown away over that alone (defect: "the
    agent's answer reached the phone empty")."""
    medicine_id = uuid.uuid4()
    known = {
        "m1": _ToolLine(
            token="m1",
            text="m1: amlodipine 5 mg, started 2026-08-01",
            cite=Cite(kind="medication_line", id=medicine_id),
        )
    }
    payload = {
        "lines": [
            {
                "text": "Your blood pressure tablet is on your list of medicines.",
                "cites": ["M1"],
            }
        ]
    }
    answer = _answer_from_payload(payload, known, "en", Reader(his=True), Mode.TEXT)
    assert answer is not None
    assert [line.text for line in answer.lines] == [
        "Your blood pressure tablet is on your list of medicines."
    ]


def test_a_line_with_no_surviving_cite_at_all_yields_no_answer() -> None:
    payload = {
        "lines": [
            {
                "text": "Your blood pressure was 138 over 84 on Wednesday 2 September.",
                "cites": [f"fact:{uuid.uuid4()}"],
            }
        ]
    }
    assert _answer_from_payload(payload, {}, "en", Reader(his=True), Mode.TEXT) is None


def test_a_diagnosis_line_is_dropped() -> None:
    good_id = uuid.uuid4()
    known = {
        f"fact:{good_id}": _ToolLine(
            token=f"fact:{good_id}", text="", cite=Cite(kind="fact", id=good_id)
        )
    }
    payload = {
        "lines": [
            {"text": "Your blood pressure is high.", "cites": [f"fact:{good_id}"]},
        ]
    }
    # "high" is in the same conclusion-and-advice blocklist `ClaudeNarrator` holds a rephrase
    # to: a finding, not an opening, so nothing survives.
    assert _answer_from_payload(payload, known, "en", Reader(his=True), Mode.TEXT) is None


def test_caregiver_voice_drops_a_line_that_still_speaks_to_him() -> None:
    good_id = uuid.uuid4()
    known = {
        f"fact:{good_id}": _ToolLine(
            token=f"fact:{good_id}", text="", cite=Cite(kind="fact", id=good_id)
        )
    }
    # A free-form line, unlike the rule-based asker's own fixed templates, is not necessarily
    # one `Reader.says` has a registered third-person twin for.
    text = "Your notes say you have been feeling tired since Wednesday 2 September."
    payload = {"lines": [{"text": text, "cites": [f"fact:{good_id}"]}]}
    # The same line, from his own key, survives: it is only the caregiver's key that drops it.
    assert _answer_from_payload(payload, known, "en", Reader(his=True), Mode.TEXT) is not None

    caregiver = Reader(his=False, name="Pa", language="en")
    # A caregiver's line must never speak to him directly ("your"): `.says()` has no twin for
    # this free-form line, so it is dropped rather than shown as though she were him.
    assert _answer_from_payload(payload, known, "en", caregiver, Mode.TEXT) is None


async def test_a_refusal_falls_back_to_the_rule_based_answer(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    question = "what was my blood pressure"
    expected = await recall(
        sg,
        context=rec.owner,
        question=question,
        mode=Mode.TEXT,
        retriever=KeywordRetriever(),
        store=LocalObjectStore(tmp_path, Region.SG),
        registry=REGISTRY,
    )
    client = FakeClient([FakeMessage(stop_reason="refusal")])
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    steps, _deltas, answer = await _drive(asker, sg, rec.owner, question, tmp_path)

    assert steps == []  # no tool ever ran
    assert [line.text for line in answer.lines] == [line.text for line in expected.lines]
    assert answer.answered


async def test_the_external_model_processor_audit_line_is_written_once(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_medicines"),
            _final(
                [
                    {
                        "text": "Your blood pressure tablet is on your list of medicines.",
                        "cites": ["m1"],
                    }
                ]
            ),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    await _drive(asker, sg, rec.owner, "what is my medicine", tmp_path)

    entries = [
        entry
        for entry in await trail(sg, rec.owner)
        if entry.target == EXTERNAL_MODEL_PROCESSOR and entry.action == Action.SHARE
    ]
    assert len(entries) == 1
    assert entries[0].outcome is Outcome.ALLOWED
    assert entries[0].shared_with_label == "anthropic"


async def test_the_reported_empty_answer_now_survives_with_short_case_insensitive_ids(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """The live-run defect, reproduced: several real tool steps stream, and the final answer
    cites ids that do not match a tool result byte for byte (here, the model changed the
    case). Before the fix the cite was matched by an exact-case uuid string and the whole
    line was silently dropped — every line, every time, because the model was never going to
    retype a uuid correctly. Short, per-kind ids matched case-insensitively fix it: the
    answer now actually reaches the phone."""
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_visits"),
            _tool_call("toolu_2", "read_medicines"),
            _final(
                [
                    {
                        "text": "Your next visit with Dr Tan is written down.",
                        "cites": ["V1"],
                    },
                    {
                        "text": "Your blood pressure tablet is on your list of medicines.",
                        "cites": ["M1"],
                    },
                ]
            ),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    steps, _deltas, answer = await _drive(
        asker, sg, rec.owner, "what is written down about my visits and medicines", tmp_path
    )

    assert steps == ["visits", "medicines"]
    assert len(answer.lines) == 2
    assert answer.lines != ()


async def test_when_even_the_fallback_has_nothing_the_catalogue_honest_line_is_sent(
    sg: AsyncSession, tmp_path: Path, monkeypatch: Any
) -> None:
    """Belt and braces: if the rule-based fallback itself somehow came back with nothing to
    say (no lines, no honest line), the reader must never be left with only the boundary. This
    should not happen in practice (`honest_lines` always fills in "your doctor"), but the fix
    guarantees it by construction rather than by that one caller's good behaviour."""
    rec = await record(sg)
    client = FakeClient([FakeMessage(stop_reason="refusal")])
    asker = ClaudeAsker(client, searcher=FakeSearcher())

    async def _empty_recall(*_args: Any, **_kwargs: Any) -> Answer:
        return Answer(
            question_artifact_id=uuid.uuid4(),
            mode=Mode.TEXT,
            language="en",
            lines=(),
            honest=(),
            boundary=boundary_lines(Surface.RECALL, "en", doctor=None),
            withheld=(),
            dropped=0,
        )

    monkeypatch.setattr("app.llm.ask_agent.recall", _empty_recall)
    _steps, _deltas, answer = await _drive(
        asker, sg, rec.owner, "what was my blood pressure", tmp_path
    )

    assert answer.lines == ()
    assert list(answer.honest) == honest_lines("en", None)
    assert answer.boundary


# A line that fails rule 3 (`docs/plain-words.md`: short words, short lines) — over Ask's own
# twenty-word ceiling (`kind="ask"`, docs/plain-words.md "1a. Profiles"; the agent's answer is
# verified at that profile, not the fifteen-word `kind="line"` every other surface uses),
# otherwise clean.
_TOO_LONG_LINE = (
    "Nura will ask you to say yes again the next time you open the app on your phone at home tonight."
)
_SHORT_LINE = "Your blood pressure tablet is on your list of medicines."


async def test_a_line_that_fails_plain_words_is_repaired_and_then_shown(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """Defect: "the agent still returns an empty answer" — five lines dropped, no repair. The
    fix gives the model one more try, told the verifier's own problem and rewrite for the rule
    its line broke (never the line itself), before ever falling back."""
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_medicines"),
            _final([{"text": _TOO_LONG_LINE, "cites": ["m1"]}]),
            _final([{"text": _SHORT_LINE, "cites": ["m1"]}]),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    steps, _deltas, answer = await _drive(asker, sg, rec.owner, "what is my medicine", tmp_path)

    assert steps == ["medicines"]
    # Three calls: the tool-use round, the first (failing) final answer, and the one repair
    # round — never a second repair.
    assert len(client.messages.calls) == 3
    repair_messages = client.messages.calls[2]["messages"]
    repair_ask = repair_messages[-1]
    assert repair_ask["role"] == "user"
    # The verifier's own problem and rewrite for the rule are named; the line that broke it
    # is not.
    assert "21 words on one line" in repair_ask["content"]
    assert "cut it into two lines, one idea each" in repair_ask["content"]
    assert _TOO_LONG_LINE not in repair_ask["content"]
    assert [line.text for line in answer.lines] == [_SHORT_LINE]


async def test_when_the_repair_also_fails_the_catalogue_line_is_sent(
    sg: AsyncSession, tmp_path: Path, monkeypatch: Any
) -> None:
    """Defect, part two: when even the one repair round still fails plain words, the rule-based
    fallback must be used, and if it has nothing of its own to say, the catalogue's own "could
    not find this" line must still reach him."""
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_medicines"),
            _final([{"text": _TOO_LONG_LINE, "cites": ["m1"]}]),
            _final([{"text": _TOO_LONG_LINE, "cites": ["m1"]}]),
        ]
    )

    async def _honest_only_recall(*_args: Any, **_kwargs: Any) -> Answer:
        return Answer(
            question_artifact_id=uuid.uuid4(),
            mode=Mode.TEXT,
            language="en",
            lines=(),
            honest=tuple(honest_lines("en", None)),
            boundary=boundary_lines(Surface.RECALL, "en", doctor=None),
            withheld=(),
            dropped=0,
        )

    monkeypatch.setattr("app.llm.ask_agent.recall", _honest_only_recall)
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    _steps, _deltas, answer = await _drive(asker, sg, rec.owner, "what is my medicine", tmp_path)

    # One repair round only — never a second.
    assert len(client.messages.calls) == 3
    assert answer.lines == ()
    assert list(answer.honest) == honest_lines("en", None)
    assert answer.boundary


async def test_when_the_fallback_itself_fails_the_catalogue_line_is_still_sent(
    sg: AsyncSession, tmp_path: Path, monkeypatch: Any
) -> None:
    """The rule-based answer is supposed to always say something and never raise — but if it
    does, that must never be the one way he ends up hearing nothing at all."""
    rec = await record(sg)
    client = FakeClient([FakeMessage(stop_reason="refusal")])

    async def _broken_recall(*_args: Any, **_kwargs: Any) -> Answer:
        raise RuntimeError("the rule-based asker blew up")

    monkeypatch.setattr("app.llm.ask_agent.recall", _broken_recall)
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    _steps, _deltas, answer = await _drive(
        asker, sg, rec.owner, "what was my blood pressure", tmp_path
    )

    assert answer.lines == ()
    assert list(answer.honest) == honest_lines("en", None)
    assert answer.boundary


def _every_schema(node: object):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _every_schema(value)
    elif isinstance(node, list):
        for value in node:
            yield from _every_schema(value)


def test_the_structured_output_schema_is_one_the_api_accepts() -> None:
    """The same lint every Claude-backed structured-output adapter carries
    (`tests/test_claude_extractor.py`, `tests/test_claude_feed_adapters.py`,
    `tests/test_clipmaker.py`, `tests/test_narrator.py`): a property without a `type`, and
    `minimum`/`maximum` on a number, are both refused by the API's structured output (hit
    live on the owner's key, 2026-09-18, for the extractor and the feed adapters). Every
    property carries a type; no numeric bounds ride in this schema."""
    from app.llm.ask_agent import ANSWER_SCHEMA

    for node in _every_schema(ANSWER_SCHEMA):
        if not (isinstance(node, dict) and "properties" in node):
            continue
        for name, prop in node["properties"].items():
            assert "type" in prop, name
            assert "minimum" not in prop and "maximum" not in prop, name


# Rule 14 (`docs/plain-words.md`: the boundary — no line starts, stops or changes a medicine)
# on its own, nothing else wrong with the line: `test_plain_words.py` pins this string to rule
# 14 alone, the same way `_TOO_LONG_LINE` above is pinned to rule 3 alone.
_BOUNDARY_LINE = "Your doctor stopped the water pill on Monday."
_BOUNDARY_AND_TOO_LONG_LINE = (
    "Your doctor stopped the water pill on Monday and told the nurse to write it in your "
    "blood pressure book for next time."
)


def test_boundary_rewrite_turns_a_treatment_change_into_a_question_for_the_doctor() -> None:
    """The verifier's own rewrite for rule 14 ('a question for the doctor') built for real: no
    chemical name, no invented medicine — only the one `_MEDICINE_NOUNS` the offending line
    already named."""
    from app.safety.plain_words import verify

    rewritten = _boundary_rewrite(_BOUNDARY_LINE, "en")
    assert rewritten == "Ask your doctor about the water pill."
    assert not any(f.severity == "fail" for f in verify(rewritten, "en", "line"))


async def test_a_line_that_fails_only_rule_14_is_rewritten_not_dropped(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """Defect: every line the model wrote about a medicine was dropped outright, on both the
    first round and the one repair round, and the reader heard nothing (live evidence:
    ``dropped a line, reason=plain_words_failed, rules=[14]`` for every line, after the
    repair round too). The fix: a line whose only problem is rule 14 is rewritten into the
    catalogue's own question-for-the-doctor shape instead — it reaches him, and no repair
    round is even needed for it."""
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_medicines"),
            _final([{"text": _BOUNDARY_LINE, "cites": ["m1"]}]),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    steps, deltas, answer = await _drive(asker, sg, rec.owner, "what is my medicine", tmp_path)

    assert steps == ["medicines"]
    # One round only: the rewrite means the first answer already survives, no repair needed.
    assert len(client.messages.calls) == 2
    assert [line.text for line in answer.lines] == ["Ask your doctor about the water pill."]
    assert deltas == ["Ask your doctor about the water pill."]
    # The rewritten line still rests on the same cite the model actually gave it.
    assert answer.lines[0].cites


async def test_a_line_failing_rule_14_and_another_rule_is_still_dropped(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """The rewrite is only for a line whose one and only problem is rule 14 — never a patch
    over a line broken some other way too. This line fails rule 14 and rule 3 (over fifteen
    words) at once, so it is dropped, exactly as an ordinary plain-words failure is; the model
    gets one repair round, and when that also fails, the rule-based fallback answers instead."""
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_medicines"),
            _final([{"text": _BOUNDARY_AND_TOO_LONG_LINE, "cites": ["m1"]}]),
            _final([{"text": _BOUNDARY_AND_TOO_LONG_LINE, "cites": ["m1"]}]),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    steps, _deltas, answer = await _drive(asker, sg, rec.owner, "what is my medicine", tmp_path)

    assert steps == ["medicines"]
    # The repair round still ran (never rewritten, so the model got a real second try), and
    # still failed — the rule-based fallback answered instead, never nothing.
    assert len(client.messages.calls) == 3
    assert answer.answered
    assert _BOUNDARY_AND_TOO_LONG_LINE not in " ".join(line.text for line in answer.lines)


async def test_every_line_failing_rule_14_still_reaches_him_through_the_fallback(
    sg: AsyncSession, tmp_path: Path, monkeypatch: Any
) -> None:
    """Live evidence, reproduced and fixed: a client whose every line fails rule 14, on both
    rounds, and whose rewrite cannot save it either (paired with a second failing rule here,
    so the rewrite path is never taken) — even then, the reader must hear the rule-based
    fallback's own answer, never silence. Belt and braces on top of it: if the fallback itself
    had nothing to say, the catalogue's own honest line still reaches him."""
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_medicines"),
            _final([{"text": _BOUNDARY_AND_TOO_LONG_LINE, "cites": ["m1"]}]),
            _final([{"text": _BOUNDARY_AND_TOO_LONG_LINE, "cites": ["m1"]}]),
        ]
    )

    async def _honest_only_recall(*_args: Any, **_kwargs: Any) -> Answer:
        return Answer(
            question_artifact_id=uuid.uuid4(),
            mode=Mode.TEXT,
            language="en",
            lines=(),
            honest=tuple(honest_lines("en", None)),
            boundary=boundary_lines(Surface.RECALL, "en", doctor=None),
            withheld=(),
            dropped=0,
        )

    monkeypatch.setattr("app.llm.ask_agent.recall", _honest_only_recall)
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    _steps, _deltas, answer = await _drive(asker, sg, rec.owner, "what is my medicine", tmp_path)

    assert len(client.messages.calls) == 3
    assert answer.lines == ()
    assert list(answer.honest) == honest_lines("en", None)
    assert answer.boundary


# --- fix 1: an answer never loses its lead and keeps the rest ------------------------------
#
# Live evidence (the operator's own run): the model's lead sentence ("there is no blood test
# in your checked papers") broke plain-words rule 4 (a red word, "result"), was dropped, and a
# second sentence survived on its own — "What your papers DO hold are notes from your hospital
# stay, ending Thursday 20 August." — which dangles with no lead to answer back to. Rule 4's
# own word: `verify("There is no blood test result in your papers.", "en", "ask")` names
# `"result"` — the glossary's own red word for it (`GLOSSARY`, "result"/"results"/"panel"/
# "labs"/"lab" -> "your blood test / your kidney test / your sugar test") — never "blood test"
# itself, which is not red. The fix: `ask_agent.txt` now tells the model to say "written down"
# rather than "result", and a partial answer whose lead was dropped (or whose surviving line
# dangles) gets one whole-answer repair round before ever reaching him.

_BAD_LEAD = "There is no blood test result in your papers."  # rule 4 ("result") alone
_GOOD_TAIL = "Ask Dr Tan whether it is time for another one."
_GOOD_LEAD = "There is no newer blood test written down in your papers."
_DANGLING_TAIL = "However, your next visit with Dr Tan is written down."


def test_rule_4_is_tripped_by_result_never_by_blood_test_itself() -> None:
    """What exactly rule 4 flags in the live sentence, pinned so the fix's target never
    drifts: the red word is "result" (the glossary's own row for "result"/"results"/"panel"/
    "labs"/"lab"), and "blood test" alone is not red."""
    from app.safety.plain_words import verify

    findings = [f for f in verify(_BAD_LEAD, "en", "ask") if f.severity == "fail"]
    assert [f.rule for f in findings] == [4]
    assert '"result"' in findings[0].problem
    assert not any(
        f.severity == "fail"
        for f in verify("There is no blood test in your checked papers.", "en", "ask")
    )


async def test_a_dropped_lead_line_triggers_a_whole_answer_repair_round(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """Defect, reproduced: the lead sentence fails plain words and is dropped, a later
    sentence survives on its own — before the fix this partial answer was shown as-is (no
    repair was ever tried, because the old repair only fired when *every* line was dropped).
    The fix asks the model, in one extra round, to rewrite the whole answer so it stands
    alone; here it does, and the coherent answer is what reaches him."""
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_medicines"),
            _final([{"text": _BAD_LEAD, "cites": ["m1"]}, {"text": _GOOD_TAIL, "cites": ["m1"]}]),
            _final([{"text": _GOOD_LEAD, "cites": ["m1"]}]),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    steps, deltas, answer = await _drive(
        asker, sg, rec.owner, "when was my last blood test", tmp_path
    )

    assert steps == ["medicines"]
    # Three calls: the tool-use round, the first (incoherent) answer, and the one
    # whole-answer repair round — never a second.
    assert len(client.messages.calls) == 3
    repair_ask = client.messages.calls[2]["messages"][-1]
    assert repair_ask["role"] == "user"
    assert _BAD_LEAD in repair_ask["content"]  # his own words, sent back to him, never logged
    assert "rewrite" in repair_ask["content"].lower()
    assert [line.text for line in answer.lines] == [_GOOD_LEAD]
    assert deltas == [_GOOD_LEAD]
    assert _GOOD_TAIL not in " ".join(line.text for line in answer.lines)


async def test_when_the_whole_answer_repair_also_fails_the_fallback_answers_never_a_partial(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """Fix 1c: when the one whole-answer repair chance also comes back incoherent, the
    rule-based fallback answers instead — never the dangling partial, and never a second
    whole-answer repair round."""
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_medicines"),
            _final([{"text": _BAD_LEAD, "cites": ["m1"]}, {"text": _GOOD_TAIL, "cites": ["m1"]}]),
            _final([{"text": _BAD_LEAD, "cites": ["m1"]}, {"text": _GOOD_TAIL, "cites": ["m1"]}]),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    steps, deltas, answer = await _drive(
        asker, sg, rec.owner, "when was my last blood test", tmp_path
    )

    assert steps == ["medicines"]
    assert len(client.messages.calls) == 3
    # Never the partial: the tail line the model kept re-offering on its own never reaches him.
    assert _GOOD_TAIL not in " ".join(answer.spoken)
    # The rule-based fallback answered instead (the same clean ending a refusal falls back to).
    assert answer.answered or answer.honest
    # No sentence streamed for a partial that was never going to be shown.
    assert deltas == []


async def test_a_dangling_opener_on_a_surviving_non_lead_line_triggers_the_same_path(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """Fix 1d: the lead line survives fine — it is a *later* line, opening with "However" right
    after the line it answered back to was dropped, that dangles. Caught the same cheap way,
    and repaired the same way."""
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_medicines"),
            _final(
                [
                    {"text": _GOOD_LEAD, "cites": ["m1"]},
                    {"text": _BAD_LEAD, "cites": ["m1"]},  # dropped (rule 4)
                    {"text": _DANGLING_TAIL, "cites": ["m1"]},  # survives, but dangles
                ]
            ),
            _final(
                [
                    {"text": _GOOD_LEAD, "cites": ["m1"]},
                    {"text": "Your next visit with Dr Tan is written down.", "cites": ["m1"]},
                ]
            ),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    _steps, _deltas, answer = await _drive(
        asker, sg, rec.owner, "when was my last blood test", tmp_path
    )

    assert len(client.messages.calls) == 3
    assert [line.text for line in answer.lines] == [
        _GOOD_LEAD,
        "Your next visit with Dr Tan is written down.",
    ]
    assert not any(line.text.lower().startswith("however") for line in answer.lines)


def test_starts_with_dangling_opener_matches_the_live_defects_own_opener() -> None:
    assert _starts_with_dangling_opener(
        "What your papers do hold are notes from his hospital stay.", "en"
    )
    assert _starts_with_dangling_opener(_DANGLING_TAIL, "en")
    assert not _starts_with_dangling_opener(_GOOD_LEAD, "en")


# --- fix 3: invented elapsed phrases are caught, exactly like an uncited claim -------------


def test_a_line_using_the_elapsed_phrase_it_was_given_survives() -> None:
    good_id = uuid.uuid4()
    known = {
        f"fact:{good_id}": _ToolLine(
            token=f"fact:{good_id}", text="", cite=Cite(kind="fact", id=good_id)
        )
    }
    text = "Your last blood test was on Wednesday 21 January, about 20 months ago."
    payload = {"lines": [{"text": text, "cites": [f"fact:{good_id}"]}]}
    parsed = _parse_answer(
        payload,
        known,
        "en",
        Reader(his=True),
        Mode.TEXT,
        elapsed_given=frozenset({"about 20 months ago"}),
    )
    assert parsed.answer is not None
    assert [line.text for line in parsed.answer.lines] == [text]


def test_a_line_inventing_its_own_elapsed_phrase_is_dropped() -> None:
    """Fix 3: the model must never do its own date arithmetic — a line whose elapsed-shaped
    words do not match a phrase this ask actually handed it is dropped, exactly like an
    uncited claim (defect this guards: the model quietly "correcting" a given phrase, or
    computing one for a date it read with no elapsed phrase attached at all)."""
    good_id = uuid.uuid4()
    known = {
        f"fact:{good_id}": _ToolLine(
            token=f"fact:{good_id}", text="", cite=Cite(kind="fact", id=good_id)
        )
    }
    text = "Your last blood test was on Wednesday 21 January, about 2 years ago."
    payload = {"lines": [{"text": text, "cites": [f"fact:{good_id}"]}]}
    # This ask only ever gave the model "about 20 months ago" for this date — "about 2 years
    # ago" is the model's own arithmetic, never handed to it.
    parsed = _parse_answer(
        payload,
        known,
        "en",
        Reader(his=True),
        Mode.TEXT,
        elapsed_given=frozenset({"about 20 months ago"}),
    )
    assert parsed.answer is None


# --- fix 2: a paper waiting to be checked reaches the model, four fields only --------------

SEPT_18 = datetime(2026, 9, 18, 8, 0, tzinfo=UTC)


async def _open_review_card(sg: AsyncSession, context: Any, store: LocalObjectStore) -> uuid.UUID:
    photo = await store_photo(
        sg,
        context=context,
        store=store,
        data=placeholder_png(LAB_REPORT_VITALS),
        content_type="image/png",
        captured_at=SEPT_18,
        source_channel=SourceChannel.APP,
    )
    card = await review_photo(
        sg,
        context=context,
        artifact_id=photo.id,
        store=store,
        extractor=FixtureExtractor(PAPER),
        language="en",
    )
    return card.id


async def test_waiting_papers_reach_the_model_with_only_the_four_allowed_fields(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, Region.SG)
    card_id = await _open_review_card(sg, rec.owner, store)

    client = FakeClient(
        [
            _tool_call("toolu_1", "read_waiting_papers"),
            _final(
                [
                    {
                        "text": "A blood test dated Thursday 10 September is waiting for "
                        "you to check.",
                        "cites": ["r1"],
                    },
                    {"text": "Once you check it, I can answer from it.", "cites": ["r1"]},
                ]
            ),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    steps, _deltas, answer = await _drive(
        asker, sg, rec.owner, "when was my last blood test done", tmp_path
    )

    assert steps == ["waiting_papers"]
    tool_result = client.messages.calls[1]["messages"][-1]["content"][0]["content"]
    assert "Bukit Lab" in tool_result  # the facility: allowed
    assert "blood test" in tool_result  # the kind: allowed
    # Never an extracted value, unit or range from the fixture's own numbers.
    for leaked in ("5.6", "140", "<130", "glucose", "ldl", "mmol"):
        assert leaked not in tool_result
    assert str(card_id) not in tool_result  # the id given back is the short token, never a uuid
    assert answer.lines


async def test_a_key_without_records_scope_is_never_offered_the_waiting_papers_tool(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    narrow = await let_in(
        sg,
        rec.owner,
        phone="+6588880003",
        name="Aminah",
        role=KeyRole.HELPER,
        scopes={Scope.PROFILE, Scope.ASK, Scope.VISITS, Scope.EMERGENCY},
    )
    assert "read_waiting_papers" not in _tools_for(narrow)
