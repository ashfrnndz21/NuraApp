"""`app.runtime.events` and `app.runtime.run` (ADR 0019 points 4-5 and 12;
`docs/design/NURA-BUILD-MASTER-SPEC.md` §5, §41-§42): the one event vocabulary, the one
serialiser, and `run_nura` wrapping the existing routes over `POST /profiles/{id}/runs`.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.runtime.events import EventBuilder, ToolResult, to_sse
from app.runtime.run import Engine, Intent, RunSubject, run_nura
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
    assert finished is not None
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
    event = builder.tool_call_result(
        tool_call_id="x", content=ToolResult(key="medicines", count=3)
    )
    assert set(event.data["content"]) == {"key", "count"}


def test_tool_call_result_refuses_free_text() -> None:
    """F3 (independent review of #331): before this, `content` accepted any mapping or a bare
    string, and nothing stopped a caller from putting a model's or an extractor's own sentence
    there — the reviewer's own example, "LDL 3.8 mmol/L, borderline high — consider a statin",
    passed through verbatim. `ToolResult` closes that: anything that is not one is a `TypeError`
    raised before the event is even built, let alone put on the wire."""
    builder = EventBuilder(intent="answer_question")
    with pytest.raises(TypeError):
        builder.tool_call_result(
            tool_call_id="x",
            content="LDL 3.8 mmol/L, borderline high — consider a statin",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        builder.tool_call_result(
            tool_call_id="x", content={"key": "medicines"}  # type: ignore[arg-type]
        )


def test_custom_refuses_an_unclosed_payload() -> None:
    """F3: `custom`'s `value` is one of `CustomPayload`'s three shapes, never an arbitrary
    mapping — the same discipline `tool_call_result` now holds."""
    builder = EventBuilder(intent="understand_paper")
    with pytest.raises(TypeError):
        builder.custom(name="card", value={"card_id": "1", "summary": "a free-text note"})  # type: ignore[arg-type]


# --- run_nura, unknown intent ---------------------------------------------------------------


async def test_run_nura_refuses_an_unknown_intent() -> None:
    """`run_nura` never lets `UnknownIntent` — or any other exception — past itself (§4;
    B1, B1-R1): it is caught by the same `try` every wrapped call's own failure is, and
    reported as the run's one terminal event, not raised to the caller."""
    events = [
        e
        async for e in run_nura(
            "not_a_real_intent",  # type: ignore[arg-type]
            RunSubject(profile_id=uuid.uuid4(), payload={}),
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
        )
    ]
    types = [e.envelope.type.value for e in events]
    assert types == ["RUN_STARTED", "RUN_ERROR"]
    assert events[-1].data["code"] == "unknown_intent"
    assert events[0].envelope.run_id == events[-1].envelope.run_id
    assert [e.envelope.seq for e in events] == [1, 2]


# --- fixture / live parity, at the port run_nura actually wraps -----------------------------


class _StubProviders:
    """Just enough of `app.channels.api.deps.Providers` for `_answer_question`: the real
    `retriever`/`object_store`/`drug_registry` `RuleBasedAsker` and `ClaudeAsker` both
    genuinely need (F2, independent review of #331: the previous version of this test
    compared a fake adapter with itself and ignored these), plus whichever `Asker` the test
    is proving."""

    def __init__(self, asker: object, *, retriever: object, object_store: object, drug_registry: object) -> None:
        self.asker = asker
        self.retriever = retriever
        self.object_store = object_store
        self.drug_registry = drug_registry


def _event_types(events: list[object]) -> list[str]:
    return [e.envelope.type.value for e in events]  # type: ignore[attr-defined]


def _collapse(types: list[str]) -> list[str]:
    return [t for t in types if t not in {"STATE_DELTA", "STATE_SNAPSHOT"}]


async def test_fixture_and_live_askers_produce_the_same_event_type_sequence(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """F2: the two real `Asker` adapters (`app.search.asker.RuleBasedAsker`,
    `app.llm.ask_agent.ClaudeAsker` — the model call stubbed with `FakeClient`, the same
    harness `tests/test_ask_agent.py` mocks the `anthropic` client with, never a live call)
    produce the same `run_nura` event-type sequence for the same question over the same
    seeded record. `ClaudeAsker` here genuinely calls a tool (`read_medicines`) and returns a
    real, plain-words-checked line citing it — not a client that falls back before ever
    naming a tool, which would prove nothing about the tool-call shape."""
    from app.ingestion.objects import LocalObjectStore
    from app.llm.ask_agent import ClaudeAsker
    from app.regions import Region
    from app.search.asker import RuleBasedAsker
    from app.search.retrieve import KeywordRetriever
    from tests.medicines_support import REGISTRY
    from tests.test_ask_agent import FakeClient, FakeSearcher, _final, _tool_call

    rec = await record(sg)
    subject = RunSubject(
        profile_id=rec.owner.profile_id,
        payload={"question": "what is my medicine", "mode": "text"},
    )
    store = LocalObjectStore(tmp_path, Region.SG)

    rule_engine = Engine(
        providers=_StubProviders(
            RuleBasedAsker(), retriever=KeywordRetriever(), object_store=store, drug_registry=REGISTRY
        ),  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
    )
    claude_client = FakeClient(
        [
            _tool_call("toolu_1", "read_medicines"),
            _final([{"text": "Your blood pressure tablet is on your list of medicines.", "cites": ["m1"]}]),
        ]
    )
    claude_engine = Engine(
        providers=_StubProviders(
            ClaudeAsker(claude_client, searcher=FakeSearcher()),
            retriever=KeywordRetriever(),
            object_store=store,
            drug_registry=REGISTRY,
        ),  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
    )

    events_rule = [e async for e in run_nura(Intent.ANSWER_QUESTION, subject, rec.owner, sg, rule_engine)]
    events_claude = [e async for e in run_nura(Intent.ANSWER_QUESTION, subject, rec.owner, sg, claude_engine)]

    shape_rule = _collapse(_event_types(events_rule))
    shape_claude = _collapse(_event_types(events_claude))
    assert "RUN_ERROR" not in shape_rule and "RUN_ERROR" not in shape_claude
    assert shape_rule[0] == "RUN_STARTED" and shape_claude[0] == "RUN_STARTED"
    assert shape_rule[-1] == "RUN_FINISHED" and shape_claude[-1] == "RUN_FINISHED"
    assert "TOOL_CALL_START" in shape_rule and "TOOL_CALL_START" in shape_claude
    assert "TEXT_MESSAGE_START" in shape_rule and "TEXT_MESSAGE_START" in shape_claude
    # Never the record itself: both adapters' TOOL_CALL_RESULT carries the same closed shape.
    for events in (events_rule, events_claude):
        for result in [e for e in events if e.envelope.type.value == "TOOL_CALL_RESULT"]:
            assert set(result.data["content"]) <= {"key", "count"}


class _AnalysisStubProviders:
    """Just enough of `Providers` for `_generate_analysis`: `drug_registry` is the only
    attribute it reads off `engine` before calling `analyst_for` — patched out below, so
    `engine.settings`'s own value is never actually consulted."""

    def __init__(self, drug_registry: object) -> None:
        self.drug_registry = drug_registry


async def test_rule_and_claude_analysts_produce_the_same_event_type_sequence_through_run_nura(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F2 (independent review of #331, round 3): `ClaudeAnalyst.report_stream` delegates
    every non-`Report` event to the `RuleAnalyst` it wraps, so comparing the two adapters
    directly — the previous version of this test — proves nothing about `report_stream`'s own
    Claude-specific branch, and never exercised `run_nura` at all. This drives **both**
    adapters through `run_nura(GENERATE_ANALYSIS)` itself (`app.reasoning.analyst.provider.
    analyst_for` monkeypatched, since it needs a live `Settings`/API key `_generate_analysis`
    is never given in a test), for three cases: `RuleAnalyst`, `ClaudeAnalyst` falling back on
    a refusal stop reason, and `ClaudeAnalyst` taking its genuine live path (a real
    choose-and-rephrase response, `stop_reason` `"end_turn"` — reusing `tests.
    test_analyst_claude`'s own duplicate-therapy fixture and payload shape). All three
    produce the same `run_nura` event-type sequence."""
    import app.reasoning.analyst.provider as analyst_provider
    from app.reasoning.analyst.claude_adapter import ClaudeAnalyst
    from app.reasoning.analyst.rule import RuleAnalyst
    from tests.medicines_support import REGISTRY
    from tests.test_analyst_claude import (
        FakeClient,
        FakeMessage,
        _duplicate_report,
        _section,
        _text_block,
    )

    rule_report, owner = await _duplicate_report(sg)
    section = _section(rule_report, "medicines_and_supplements")
    assert section is not None
    from app.reasoning.analyst.port import InsightKind

    duplicate = next(i for i in section.insights if i.kind is InsightKind.MEDICINE)
    subject = RunSubject(profile_id=owner.profile_id, payload={})
    engine = Engine(providers=_AnalysisStubProviders(REGISTRY), settings=object())  # type: ignore[arg-type]

    def _use(analyst: object) -> None:
        monkeypatch.setattr(analyst_provider, "analyst_for", lambda *_a, **_k: analyst)

    _use(RuleAnalyst(registry=REGISTRY))
    events_rule = [e async for e in run_nura(Intent.GENERATE_ANALYSIS, subject, owner, sg, engine)]

    _use(ClaudeAnalyst(client=FakeClient([FakeMessage(content=[], stop_reason="refusal")]), registry=REGISTRY))
    events_claude_fallback = [e async for e in run_nura(Intent.GENERATE_ANALYSIS, subject, owner, sg, engine)]

    live_client = FakeClient(
        [
            FakeMessage(
                content=[
                    _text_block(
                        {
                            "insights": [
                                {
                                    "insight_id": duplicate.insight_id,
                                    "text": "2 of your medicines are written down under the same kind.",
                                    "why_plain": "This compares the kind written down for each medicine.",
                                }
                            ]
                        }
                    )
                ]
            )
        ]
    )
    _use(ClaudeAnalyst(client=live_client, registry=REGISTRY))
    events_claude_live = [e async for e in run_nura(Intent.GENERATE_ANALYSIS, subject, owner, sg, engine)]

    shape_rule = _collapse(_event_types(events_rule))
    shape_fallback = _collapse(_event_types(events_claude_fallback))
    shape_live = _collapse(_event_types(events_claude_live))
    assert "RUN_ERROR" not in shape_rule + shape_fallback + shape_live
    assert shape_rule == shape_fallback == shape_live
    assert shape_rule[0] == "RUN_STARTED"
    assert shape_rule[-1] == "RUN_FINISHED"
    assert "TOOL_CALL_START" in shape_rule


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
    assert events[-1]["code"] == "refused"  # closed ErrorCode (round 3, fix 2), never a class name


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
    # `notice` is dropped (never sent as `null`) when the paper needed none — LIPID_PANEL is
    # a recognised health paper, so only `card_id` is on the wire here.
    assert set(cards[0]["value"]) <= {"card_id", "notice"}
    assert "card_id" in cards[0]["value"]



# --- B1: a run always terminates (independent review of #331) -------------------------------


class _RaisesAfterOneDelta:
    """An `Asker` whose stream raises partway through — proves a run never leaves an open
    `TEXT_MESSAGE_START` with no matching `END` when the underlying call breaks mid-answer
    (B1, reproduced case 1: "events stop after TEXT_MESSAGE_CONTENT")."""

    external_processor: str | None = None

    async def ask_stream(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        from app.search.asker import AnswerDelta

        yield AnswerDelta(text="Your blood pressure tablet is on your list.", cites=())
        raise ValueError("a live model's own stream broke mid-answer")
        yield  # pragma: no cover — makes this an async generator; never reached


class _NeverAnswers:
    """An `Asker` whose stream ends with no `Answer` at all — reproduces B1 case 2 (the bare
    `assert answer is not None` that used to crash the generator with `AssertionError`)."""

    external_processor: str | None = None

    async def ask_stream(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        return
        yield  # pragma: no cover


async def test_b1_a_broken_asker_stream_still_closes_the_text_message_and_ends_the_run(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    subject = RunSubject(
        profile_id=rec.owner.profile_id,
        payload={"question": "what is my medicine", "mode": "text"},
    )
    engine = Engine(
        providers=_StubProviders(
            _RaisesAfterOneDelta(), retriever=None, object_store=None, drug_registry=None
        ),  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
    )
    events = [e async for e in run_nura(Intent.ANSWER_QUESTION, subject, rec.owner, sg, engine)]
    types = [e.envelope.type.value for e in events]
    assert types[0] == "RUN_STARTED"
    # The message that was open when the stream broke is closed before the run ends — never
    # left dangling with no `TEXT_MESSAGE_END`.
    assert "TEXT_MESSAGE_START" in types
    assert types[types.index("TEXT_MESSAGE_START") + 1 :].count("TEXT_MESSAGE_END") >= 1
    assert types[-1] == "RUN_ERROR"
    assert "ValueError" not in events[-1].data["message"]
    assert [e.envelope.seq for e in events] == list(range(1, len(events) + 1))


async def test_b1_a_stream_with_no_final_answer_ends_as_run_error_not_a_crash(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    subject = RunSubject(
        profile_id=rec.owner.profile_id,
        payload={"question": "what is my medicine", "mode": "text"},
    )
    engine = Engine(
        providers=_StubProviders(_NeverAnswers(), retriever=None, object_store=None, drug_registry=None),  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
    )
    events = [e async for e in run_nura(Intent.ANSWER_QUESTION, subject, rec.owner, sg, engine)]
    types = [e.envelope.type.value for e in events]
    assert types == ["RUN_STARTED", "RUN_ERROR"]
    assert events[-1].data["message"] == "Nura could not finish that just now."
    assert events[-1].data["code"] == "internal"
    assert events[0].envelope.run_id == events[-1].envelope.run_id
    assert [e.envelope.seq for e in events] == [1, 2]


async def test_b1_a_payload_missing_a_required_field_ends_as_run_error_not_a_500(
    sg: AsyncSession,
) -> None:
    """B1, reproduced case 3: `{"mode": "text"}` with no `question` used to raise a pydantic
    `ValidationError` that escaped past `RUN_STARTED`, with no `RUN_ERROR` or `RUN_FINISHED`
    ever following it."""
    rec = await record(sg)
    subject = RunSubject(profile_id=rec.owner.profile_id, payload={"mode": "text"})
    engine = Engine(providers=None, settings=None)  # type: ignore[arg-type]
    events = [e async for e in run_nura(Intent.ANSWER_QUESTION, subject, rec.owner, sg, engine)]
    types = [e.envelope.type.value for e in events]
    assert types == ["RUN_STARTED", "RUN_ERROR"]
    message = events[-1].data["message"]
    assert "ValidationError" not in message and "question" not in message
    assert events[-1].data["code"] == "bad_request"


async def test_b1_prepare_visit_with_no_appointment_id_ends_as_run_error_not_a_keyerror(
    sg: AsyncSession,
) -> None:
    """B1, reproduced case 4: `payload={}` used to raise a bare `KeyError` inside the
    generator, which — because `except Refusal` never catches a `KeyError` — escaped past
    `RUN_STARTED` with no terminal event at all."""
    rec = await record(sg)
    subject = RunSubject(profile_id=rec.owner.profile_id, payload={})
    engine = Engine(providers=None, settings=None)  # type: ignore[arg-type]
    events = [e async for e in run_nura(Intent.PREPARE_VISIT, subject, rec.owner, sg, engine)]
    types = [e.envelope.type.value for e in events]
    assert types == ["RUN_STARTED", "RUN_ERROR"]
    assert "KeyError" not in events[-1].data["message"]
    assert events[-1].data["code"] == "bad_request"
    assert [e.envelope.seq for e in events] == [1, 2]


# --- B2: patient words on TOOL_CALL_START.stage and RUN_ERROR.message (independent review) ---

_ENGINE_WORDS = (
    "jobs_looking_today",
    "brief_for",
    "visits",
    "readings",
    "medicines",
    "records",
    "stored",
    "reading",
    "found",
    "red_flag_checked",
    "ready",
    "OutOfScope",
    "does not cover",
)


async def test_answer_question_stage_is_patient_words_on_an_ms_profile(
    deployment: Deployment,
) -> None:
    """B2: measured on an `ms` profile before this fix, `TOOL_CALL_START` carried the bare
    function/enum name (`"visits"`, `"readings"`, …) as `stage`. It must carry
    `ASK_STEPS["ms"][key]` instead — one of the catalogue's own Malay sentences, never the
    English key."""
    pa = await register_by_phone(deployment, PA, "Pa", language="ms")
    profile_id = await own_profile(deployment, pa, language="ms")
    his = bearer(pa["token"])

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/runs",
        json={
            "intent": "answer_question",
            "payload": {"question": "apa ubat saya", "mode": "text"},
        },
        headers=his,
    )
    assert streamed.status_code == 200
    starts = [e for e in _events(streamed.text) if e["type"] == "TOOL_CALL_START"]
    assert starts
    for event in starts:
        stage = str(event["stage"])
        assert stage not in _ENGINE_WORDS
        assert any(ord(ch) > 127 or ch.isalpha() for ch in stage)  # a real sentence, not a code
        assert stage.endswith((".", "?"))  # a whole sentence (plain-words rule 1)


async def test_generate_recommendations_stage_is_patient_words_not_the_function_name(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/runs",
        json={"intent": "generate_recommendations", "payload": {}},
        headers=bearer(pa["token"]),
    )
    assert streamed.status_code == 200
    (start,) = [e for e in _events(streamed.text) if e["type"] == "TOOL_CALL_START"]
    assert start["stage"] not in _ENGINE_WORDS
    assert start["tool_call_name"] == "jobs_looking_today"  # the machine name stays on its own field
    assert start["stage"] == "Checking today's finds."


async def test_a_caregiver_refusal_message_is_patient_words_not_engine_language(
    deployment: Deployment,
) -> None:
    """B2: `RUN_ERROR.message` measured `"key does not cover records"` — a `Refusal`'s own
    constructor text — before this fix. It must read from `_REFUSAL_WORDS` instead."""
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
        json={"intent": "answer_question", "payload": {"question": "what is my medicine", "mode": "text"}},
        headers=bearer(mei["token"]),
    )
    events = _events(streamed.text)
    message = str(events[-1]["message"])
    for engine_word in ("does not cover", "OutOfScope", "key", "scope"):
        assert engine_word not in message
    assert message == "The people looking after this cannot do that yet."
    assert events[-1]["code"] == "refused"


async def test_an_unknown_intent_over_http_is_a_well_formed_run_not_a_raw_422(
    deployment: Deployment,
) -> None:
    """Follow-up 3 (independent review of #331): `RunIn.intent` used to be typed `Intent`,
    so FastAPI's own request-body validation rejected an unrecognised intent with a raw 422
    body before the route ever ran — the one input on this route that never got a
    `RUN_STARTED`, let alone a calm `RUN_ERROR`."""
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/runs",
        json={"intent": "fly_to_the_moon", "payload": {}},
        headers=bearer(pa["token"]),
    )
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    events = _events(streamed.text)
    types = [e["type"] for e in events]
    assert types == ["RUN_STARTED", "RUN_ERROR"]
    assert events[-1]["message"] == "Nura does not know how to do that yet."
    assert events[-1]["code"] == "unknown_intent"
    assert events[0]["run_id"] == events[-1]["run_id"]
    assert [e["seq"] for e in events] == [1, 2]


# --- B1-R1: one EventBuilder per run, always (independent review of #331, round 3) -----------


async def test_b1_r1_p3_a_state_read_failure_before_the_handlers_own_try_keeps_one_builder(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P3: a `RuntimeError` reading State — `_state_before` only ever catches `Refusal` — used
    to escape a handler before its own `try` even started (each handler built its own
    `EventBuilder` and called `_state_before` before entering `try`), surfacing as `RUN_ERROR`
    under a **fresh** `run_id` with `seq` back at 1. `_state_before` now runs inside the
    handler's own `try`, using the one builder `run_nura` already yielded `RUN_STARTED` with."""
    import app.runtime.run as run_module

    async def _broken_current_state(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the database fell over")

    monkeypatch.setattr(run_module, "current_state", _broken_current_state)
    rec = await record(sg)
    subject = RunSubject(
        profile_id=rec.owner.profile_id,
        payload={"question": "what is my medicine", "mode": "text"},
    )
    engine = Engine(
        providers=_StubProviders(_NeverAnswers(), retriever=None, object_store=None, drug_registry=None),  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
    )
    events = [e async for e in run_nura(Intent.ANSWER_QUESTION, subject, rec.owner, sg, engine)]
    types = [e.envelope.type.value for e in events]
    assert types == ["RUN_STARTED", "RUN_ERROR"]
    assert events[0].envelope.run_id == events[-1].envelope.run_id
    assert [e.envelope.seq for e in events] == [1, 2]
    assert "RuntimeError" not in events[-1].data["message"]
    assert events[-1].data["code"] == "internal"


async def test_b1_r1_p2_nothing_after_run_finished_builds_a_second_terminal(
    sg: AsyncSession,
) -> None:
    """P2: `session_scope`'s own commit can fail on the way out of the `async with` in
    `app.channels.api.runs.start_run`'s `pump`, after `run_nura` already yielded
    `RUN_FINISHED` — reachable, not hypothetical (`app/channels/api/deps.py` commits there).
    Simulated directly: drain a real `run_nura` call to `RUN_FINISHED`, holding the same
    builder `pump` would hold, then call `run_error` on it again exactly as `pump`'s own
    `except` would on that later failure — it must build nothing, the same guarantee
    `test_runtime_events.py`'s own `EventBuilder` tests already pin, now proven through a real
    run."""
    from app.runtime.events import ErrorCode, EventBuilder

    rec = await record(sg)
    subject = RunSubject(profile_id=rec.owner.profile_id, payload={})
    engine = Engine(providers=None, settings=None)  # type: ignore[arg-type]
    builder = EventBuilder(intent=Intent.GENERATE_RECOMMENDATIONS.value)
    events = [
        e
        async for e in run_nura(
            Intent.GENERATE_RECOMMENDATIONS, subject, rec.owner, sg, engine, builder=builder
        )
    ]
    assert events[-1].envelope.type.value == "RUN_FINISHED"
    assert builder.terminated
    again = builder.run_error(message="should never reach the wire", code=ErrorCode.INTERNAL)
    assert again is None
    # The stream itself is unaffected: still exactly one terminal, still every seq unique.
    assert [e.envelope.seq for e in events] == list(range(1, len(events) + 1))


# --- round 3, fix 1: a broken tool call is always closed before RUN_ERROR --------------------


async def test_fix1_generate_recommendations_closes_the_open_tool_call_before_run_error(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gap `generate_recommendations`/`prepare_visit` have between `TOOL_CALL_START` and
    the real `await` that `TOOL_CALL_END`/`RESULT` depend on (round 3, fix 1: measured
    `RUN_STARTED, TOOL_CALL_START, RUN_ERROR` — one START, zero END, before this)."""

    async def _broken_jobs_looking_today(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("the search index is down")

    rec = await record(sg)
    subject = RunSubject(profile_id=rec.owner.profile_id, payload={})
    engine = Engine(providers=None, settings=None)  # type: ignore[arg-type]
    monkeypatch.setattr(
        "app.delivery.feed.search.jobs_looking_today", _broken_jobs_looking_today
    )
    events = [
        e
        async for e in run_nura(Intent.GENERATE_RECOMMENDATIONS, subject, rec.owner, sg, engine)
    ]
    types = [e.envelope.type.value for e in events]
    assert types[0] == "RUN_STARTED"
    assert types[-1] == "RUN_ERROR"
    starts = types.count("TOOL_CALL_START")
    ends = types.count("TOOL_CALL_END")
    assert starts == 1
    assert ends == 1, f"a TOOL_CALL_START was left with no matching END: {types}"
    end_event = events[types.index("TOOL_CALL_END")]
    assert end_event.data.get("error") is True


async def test_fix1_prepare_visit_closes_the_open_tool_call_before_run_error(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _broken_brief_for(*args: object, **kwargs: object) -> object:
        raise RuntimeError("the brief could not be built")

    rec = await record(sg)
    subject = RunSubject(profile_id=rec.owner.profile_id, payload={"appointment_id": str(uuid.uuid4())})
    engine = Engine(providers=None, settings=None)  # type: ignore[arg-type]
    monkeypatch.setattr("app.reasoning.visits.brief.brief_for", _broken_brief_for)
    events = [e async for e in run_nura(Intent.PREPARE_VISIT, subject, rec.owner, sg, engine)]
    types = [e.envelope.type.value for e in events]
    assert types[0] == "RUN_STARTED"
    assert types[-1] == "RUN_ERROR"
    assert types.count("TOOL_CALL_START") == types.count("TOOL_CALL_END") == 1
    end_event = events[types.index("TOOL_CALL_END")]
    assert end_event.data.get("error") is True


# --- round 3, fix 2: RUN_ERROR.code is a closed enum, never a class name ---------------------


def test_fix2_run_error_code_must_be_an_error_code() -> None:
    from app.runtime.events import ErrorCode

    builder = EventBuilder(intent="answer_question")
    with pytest.raises(TypeError):
        builder.run_error(message="x", code="RuntimeError")  # type: ignore[arg-type]
    event = builder.run_error(message="x", code=ErrorCode.INTERNAL)
    assert event is not None
    assert event.data["code"] == "internal"


async def test_fix2_an_arbitrary_exception_maps_to_internal(sg: AsyncSession) -> None:
    from app.runtime.run import _error_code

    assert _error_code(RuntimeError("anything")).value == "internal"
    assert _error_code(ZeroDivisionError()).value == "internal"


# --- round 3, fix 3: ToolResult/StepCustom fields are validated against closed sets -----------


def test_fix3_tool_result_key_rejects_free_text_even_as_the_right_type() -> None:
    """F3, round 3: `ToolResult.key` was typed `str`, so a value of the right *type* — not
    only the wrong type — could still carry free text. `ToolResult(key="LDL 3.8 mmol/L,
    borderline high — consider a statin")` is the reviewer's own example."""
    with pytest.raises(ValueError, match="closed step keys"):
        ToolResult(key="LDL 3.8 mmol/L, borderline high — consider a statin")
    # A real, closed key still works.
    assert ToolResult(key="medicines").key == "medicines"


def test_fix3_card_custom_notice_rejects_free_text() -> None:
    from app.runtime.events import CardCustom

    with pytest.raises(ValueError, match="closed Notice"):
        CardCustom(notice="this page is definitely not a health paper, trust me")


def test_fix3_report_custom_language_rejects_free_text() -> None:
    from app.runtime.events import ReportCustom

    with pytest.raises(ValueError, match="en/ms/zh"):
        ReportCustom(sections=3, language="klingon")


# --- round 3 review nit: open_tool_call_id must not be set before TOOL_CALL_START is yielded --


class _AsksWithABadStepKey:
    """An `Asker` whose step names a key `ASK_STEPS` does not have — reproduces the round 3
    review nit: `stage=ASK_STEPS[language][event.key]` raises while `_answer_question` is
    still building `tool_call_start`'s own arguments, before that call is ever yielded.
    Before the fix, `open_tool_call_id` was already set at that point (assigned before the
    `yield`, not after it), so the `except` closed a call that had never opened — measured
    `RUN_STARTED, TOOL_CALL_END, RUN_ERROR`, no `TOOL_CALL_START` at all."""

    external_processor: str | None = None

    async def ask_stream(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        from app.search.ask import AskStep

        yield AskStep(key="not_a_real_step_key", count=1)


async def test_round3_nit_a_failure_building_stage_never_closes_an_unopened_tool_call(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    subject = RunSubject(
        profile_id=rec.owner.profile_id,
        payload={"question": "what is my medicine", "mode": "text"},
    )
    engine = Engine(
        providers=_StubProviders(
            _AsksWithABadStepKey(), retriever=None, object_store=None, drug_registry=None
        ),  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
    )
    events = [e async for e in run_nura(Intent.ANSWER_QUESTION, subject, rec.owner, sg, engine)]
    types = [e.envelope.type.value for e in events]
    assert types == ["RUN_STARTED", "RUN_ERROR"]
    assert "TOOL_CALL_START" not in types
    assert "TOOL_CALL_END" not in types
    assert events[0].envelope.run_id == events[-1].envelope.run_id
    assert [e.envelope.seq for e in events] == [1, 2]
