"""`app.runtime.events` and `app.runtime.run` (ADR 0019 points 4-5 and 12;
`docs/design/NURA-BUILD-MASTER-SPEC.md` §5, §41-§42): the one event vocabulary, the one
serialiser, and `run_nura` wrapping the existing routes over `POST /profiles/{id}/runs`.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.runtime.events import EventBuilder, to_sse
from app.runtime.run import Engine, Intent, RunSubject, UnknownIntent, run_nura
from app.search.ask import AskStep, Mode
from app.search.asker import AnswerDelta
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.capture_support import photo
from tests.conftest import Deployment
from tests.paper import LIPID_PANEL
from tests.timeline_support import record

PA = "+6591190001"
MEI = "+6591190002"


def _events(text: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in text.split("\n\n")
        if line.startswith("data: ")
    ]


# --- the serialiser, standalone -----------------------------------------------------------------


def test_every_event_carries_run_id_intent_and_a_monotonic_seq() -> None:
    builder = EventBuilder(intent="answer_question")
    started = builder.run_started()
    finished = builder.run_finished()
    assert started.envelope.run_id == finished.envelope.run_id
    assert started.envelope.intent == "answer_question"
    assert finished.envelope.seq == started.envelope.seq + 1


def test_to_sse_is_one_data_line_json_blank_line_after() -> None:
    event = EventBuilder(intent="answer_question").run_started()
    wire = to_sse(event)
    assert wire.endswith(b"\n\n")
    line = wire.decode().removeprefix("data: ").rstrip("\n")
    payload = json.loads(line)
    assert payload["type"] == "RUN_STARTED"
    assert payload["run_id"] == event.envelope.run_id


def test_tool_call_result_content_is_the_closed_summary_it_is_given() -> None:
    """The rule `run.py` documents at every call site: `content` is a short, closed summary —
    a count, a key — never a row and never free text off an extractor or a paper. This test
    pins the builder's own shape; the HTTP tests below prove `run.py`'s real call sites only
    ever pass `{"key", "count"}` for an Ask step."""
    builder = EventBuilder(intent="answer_question")
    event = builder.tool_call_result(tool_call_id="x", content={"key": "medicines", "count": 3})
    assert set(event.data["content"]) == {"key", "count"}


# --- run_nura, unknown intent ---------------------------------------------------------------


async def test_run_nura_refuses_an_unknown_intent() -> None:
    with pytest.raises(UnknownIntent):
        async for _ in run_nura(
            "not_a_real_intent",  # type: ignore[arg-type]
            RunSubject(profile_id=uuid.uuid4(), payload={}),
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
        ):
            pass


# --- fixture / live parity, at the port run_nura actually wraps -----------------------------


class _StubProviders:
    """Just enough of `app.channels.api.deps.Providers` for `_answer_question`: the fields it
    reads off `engine` before handing them, unused, to a fake `Asker` that ignores them."""

    def __init__(self, asker: object) -> None:
        self.asker = asker
        self.retriever = None
        self.object_store = None
        self.drug_registry = None


class _FixedStepsAsker:
    """A second `Asker` (`app.search.asker.Asker`), standing in for a live, model-backed one:
    a different source of steps (a fixed script instead of a keyword retriever), the same
    contract — one `AskStep` per real read, `AnswerDelta`s, then the `Answer`. Proves
    `run_nura` emits the same *shape* of events for two different adapters behind the same
    port (ADR 0019 point 12; master-spec §42) — the property that actually matters, since a
    byte-identical stream would be the wrong test: a live model's own words are its own."""

    external_processor: str | None = None

    def __init__(self, steps: list[AskStep], text: str, answer: object) -> None:
        self._steps = steps
        self._text = text
        self._answer = answer

    async def ask_stream(self, *args: object, **kwargs: object) -> AsyncIterator[object]:
        for step in self._steps:
            yield step
        yield AnswerDelta(text=self._text, cites=())
        yield self._answer


def _event_types(events: list[object]) -> list[str]:
    return [e.envelope.type.value for e in events]  # type: ignore[attr-defined]


async def test_fixture_and_live_askers_produce_the_same_event_type_sequence(sg: AsyncSession) -> None:
    from app.search.ask import Answer

    rec = await record(sg)
    subject = RunSubject(
        profile_id=rec.owner.profile_id,
        payload={"question": "what is my medicine", "mode": "text"},
    )

    rule_asker = _FixedStepsAsker(
        [AskStep(key="medicines", count=1)],
        "His medicine is amlodipine.",
        Answer(
            question_artifact_id=uuid.uuid4(),
            mode=Mode.TEXT,
            language="en",
            lines=(),
            honest=("His medicine is amlodipine.",),
            boundary=(),
            withheld=(),
            dropped=0,
        ),
    )
    claude_asker = _FixedStepsAsker(
        [AskStep(key="medicines", count=1)],
        "He takes amlodipine for his blood pressure.",
        Answer(
            question_artifact_id=uuid.uuid4(),
            mode=Mode.TEXT,
            language="en",
            lines=(),
            honest=("He takes amlodipine for his blood pressure.",),
            boundary=(),
            withheld=(),
            dropped=0,
        ),
    )

    events_rule = [
        e
        async for e in run_nura(
            Intent.ANSWER_QUESTION,
            subject,
            rec.owner,
            sg,
            Engine(providers=_StubProviders(rule_asker), settings=None),  # type: ignore[arg-type]
        )
    ]
    events_claude = [
        e
        async for e in run_nura(
            Intent.ANSWER_QUESTION,
            subject,
            rec.owner,
            sg,
            Engine(providers=_StubProviders(claude_asker), settings=None),  # type: ignore[arg-type]
        )
    ]

    def _collapse(types: list[str]) -> list[str]:
        return [t for t in types if t not in {"STATE_DELTA", "STATE_SNAPSHOT"}]

    shape = _collapse(_event_types(events_rule))
    assert shape == _collapse(_event_types(events_claude))
    assert shape == [
        "RUN_STARTED",
        "TOOL_CALL_START",
        "TOOL_CALL_END",
        "TOOL_CALL_RESULT",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "RUN_FINISHED",
    ]
    # Never the record itself: both adapters' TOOL_CALL_RESULT carry the same closed shape.
    for events in (events_rule, events_claude):
        (result,) = [e for e in events if e.envelope.type.value == "TOOL_CALL_RESULT"]
        assert set(result.data["content"]) == {"key", "count"}


# --- the HTTP route -----------------------------------------------------------------------------


async def test_answer_question_over_http_matches_the_typed_vocabulary(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 138, "diastolic": 84, "taken_at": "2026-09-13T08:00:00+08:00"},
        headers=his,
    )

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/runs",
        json={
            "intent": "answer_question",
            "payload": {"question": "what was my blood pressure", "mode": "text"},
        },
        headers=his,
    )
    assert streamed.status_code == 200
    events = _events(streamed.text)
    types = [e["type"] for e in events]
    assert types[0] == "RUN_STARTED"
    assert "RUN_FINISHED" in types
    assert "RUN_ERROR" not in types
    # One TOOL_CALL_START/END/RESULT triple per real read of his record — never the record
    # itself: every RESULT's content is a closed {"key", "count"}, matching `AskStep` exactly.
    results = [e for e in events if e["type"] == "TOOL_CALL_RESULT"]
    assert results
    for result in results:
        assert set(result["content"]) == {"key", "count"}
    assert {e["run_id"] for e in events} == {events[0]["run_id"]}
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["intent"] == "answer_question" for e in events)


async def test_a_caregiver_without_ask_is_refused_as_run_error_not_500(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    await let_in(
        deployment, pa, profile_id, MEI, ["medicines"], holder_display_name="Mei", role="caregiver"
    )
    mei = await register_by_phone(deployment, MEI, "Mei", language="en")
    cut = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": ["medicines"]},
        headers=bearer(pa["token"]),
    )
    assert cut.status_code == 201, cut.text

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/runs",
        json={
            "intent": "answer_question",
            "payload": {"question": "what is my medicine", "mode": "text"},
        },
        headers=bearer(mei["token"]),
    )
    assert streamed.status_code == 200
    events = _events(streamed.text)
    assert events[0]["type"] == "RUN_STARTED"
    assert events[-1]["type"] == "RUN_ERROR"
    message = str(events[-1]["message"])
    assert "500" not in message and "OutOfScope" not in message


async def test_understand_paper_over_http_streams_tool_calls_then_a_card(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/runs",
        json={"intent": "understand_paper", "payload": {"kind": "photo", **photo(LIPID_PANEL)}},
        headers=his,
    )
    assert streamed.status_code == 200
    events = _events(streamed.text)
    types = [e["type"] for e in events]
    assert types[0] == "RUN_STARTED"
    assert "RUN_FINISHED" in types
    assert "RUN_ERROR" not in types
    cards = [e for e in events if e["type"] == "CUSTOM" and e["name"] == "card"]
    assert len(cards) == 1
    assert set(cards[0]["value"]) == {"card_id", "notice"}

