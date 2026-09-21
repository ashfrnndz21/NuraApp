"""`ClaudeAnalyst` (`app.reasoning.analyst.claude_adapter`): the agent behind the `Analyst`
port, tested the way every other Claude-backed adapter here is
(`tests/test_claude_feed_adapters.py`, `tests/test_clipmaker.py`, `tests/test_ask_agent.py`) —
a mocked `anthropic` client, never a live call, no API key. `RuleAnalyst` does every real read;
these tests exercise only what happens to its candidates once Claude has chosen and rephrased
them: the same gate every rule candidate already passed
(`app.reasoning.analyst.pipeline.finalize`) applied a second time to the model's own words,
which have never been checked — the HIGH finding an independent clinical-safety review raised
against the first cut of this adapter, which built `Insight`s straight from the model's `text`
and never re-checked them at all."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.keys.scopes import Scope
from app.reasoning.analyst.claude_adapter import CHOICES_SCHEMA, ClaudeAnalyst
from app.reasoning.analyst.port import InsightKind, Report
from app.reasoning.analyst.rule import RuleAnalyst
from app.reasoning.visits.models import Memo, MemoKind, MemoSource
from tests.medicines_support import REGISTRY, label
from tests.medicines_support import add as add_medicine
from tests.safety_support import pa


@dataclass
class FakeMessage:
    content: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "end_turn"


class FakeMessages:
    def __init__(self, responses: Sequence[FakeMessage]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> FakeMessage:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeMessages.create called more times than responses queued")
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses: Sequence[FakeMessage]) -> None:
        self.messages = FakeMessages(responses)


def _text_block(payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": "text", "text": json.dumps(payload)}


async def _rule_report(session: AsyncSession, context, *, language: str = "en") -> Report:
    report: Report | None = None
    async for event in RuleAnalyst(registry=REGISTRY).report_stream(session, context=context, language=language):
        if isinstance(event, Report):
            report = event
    assert report is not None
    return report


def _section(report: Report, key: str):
    return next((s for s in report.sections if s.key == key), None)


async def _duplicate_report(session: AsyncSession) -> tuple[Report, object]:
    """A rule report holding one duplicate-therapy `MEDICINE` candidate, `ask_who` pharmacist —
    the shape the HIGH finding's own example (a model choice naming a diagnosis and telling
    him to stop a medicine) is checked against."""
    owner = await pa(session, phone="+6591150091")
    await add_medicine(session, owner, label("bisoprolol", "2.5 mg", "1 tab OD"))
    await add_medicine(session, owner, label("atenolol", "50 mg", "1 tab OD"))
    report = await _rule_report(session, owner)
    return report, owner


# --- the structured-output schema: the same lint every Claude-backed adapter carries ----------


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
    (`tests/test_ask_agent.py`, `tests/test_claude_feed_adapters.py`, `tests/test_clipmaker.py`):
    a property without a `type`, and `minimum`/`maximum` on a number, are both refused by the
    API's structured output. Every property carries a type; no numeric bounds ride in this
    schema."""
    for node in _every_schema(CHOICES_SCHEMA):
        if not (isinstance(node, dict) and "properties" in node):
            continue
        for name, prop in node["properties"].items():
            assert "type" in prop, name
            assert "minimum" not in prop and "maximum" not in prop, name


# --- the gate: every model choice is re-checked, never trusted just because it parsed ---------


async def test_a_blocked_medicine_choice_is_never_printed_and_files_a_doctor_question(
    sg: AsyncSession,
) -> None:
    """The HIGH finding's own example: a model choice that names a diagnosis and tells him to
    stop a medicine must never reach the report, whatever section it claims — it is rerouted
    as a real, filed question for the doctor (`app.reasoning.analyst.rule.ask_the_doctor`,
    #236), and only the rule's own safe line is ever shown in its place."""
    rule_report, owner = await _duplicate_report(sg)
    section = _section(rule_report, "medicines_and_supplements")
    assert section is not None
    duplicate = next(i for i in section.insights if i.kind is InsightKind.MEDICINE)

    blocked_text = "You have high blood pressure, stop the amlodipine."
    client = FakeClient(
        [
            FakeMessage(
                content=[
                    _text_block(
                        {
                            "insights": [
                                {
                                    "insight_id": duplicate.insight_id,
                                    "text": blocked_text,
                                    "why_plain": "why",
                                }
                            ]
                        }
                    )
                ]
            )
        ]
    )
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    report: Report | None = None
    async for event in analyst.report_stream(sg, context=owner, language="en"):
        if isinstance(event, Report):
            report = event
    assert report is not None

    # Never printed anywhere in the report, whatever section it landed in.
    for section in report.sections:
        for insight in section.insights:
            assert "amlodipine" not in insight.text.lower()
            assert "stop" not in insight.text.lower()
            assert blocked_text not in insight.text

    # A real question was filed for the doctor — the reroute, never a silent drop.
    memos = await audited_read(
        sg, Memo, owner, Scope.VISITS, where=(Memo.source == MemoSource.ANALYST,)
    )
    assert len(memos) == 1
    assert memos[0].kind is MemoKind.ASK


async def test_a_clean_text_with_a_blocked_why_plain_is_never_printed_and_files_a_doctor_question(
    sg: AsyncSession,
) -> None:
    """#303 review, B1a — the independent safety reviewer's own proof: `finalize` used to
    check only `candidate.text`; a model choice with a clean `text` and a `why_plain` naming
    a dose change ("Ask the doctor to double the dose today.") was printed as-is. `why_plain`
    now runs through the exact same gate `text` does — plain words and the conclusion-or-
    advice blocklist — and either failing either refuses the whole candidate, the same as a
    blocked `text` always has: rerouted as a real, filed question for the doctor for a
    medicine or supplement kind, its words — text OR why — never printed."""
    rule_report, owner = await _duplicate_report(sg)
    section = _section(rule_report, "medicines_and_supplements")
    assert section is not None
    duplicate = next(i for i in section.insights if i.kind is InsightKind.MEDICINE)

    clean_text = "2 of your medicines are written down under the same kind."
    blocked_why = "Ask the doctor to double the dose today."
    client = FakeClient(
        [
            FakeMessage(
                content=[
                    _text_block(
                        {
                            "insights": [
                                {
                                    "insight_id": duplicate.insight_id,
                                    "text": clean_text,
                                    "why_plain": blocked_why,
                                }
                            ]
                        }
                    )
                ]
            )
        ]
    )
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    report: Report | None = None
    async for event in analyst.report_stream(sg, context=owner, language="en"):
        if isinstance(event, Report):
            report = event
    assert report is not None

    # Never printed anywhere in the report, whatever section it landed in — neither the
    # clean text (it never stood alone: the whole candidate was refused) nor the why.
    for section in report.sections:
        for insight in section.insights:
            assert insight.text != clean_text
            assert blocked_why not in insight.why_plain
            assert "double the dose" not in insight.why_plain.lower()

    # A real question was filed for the doctor — the reroute, never a silent drop, never the
    # clean text shown with the dangerous why quietly missing.
    memos = await audited_read(
        sg, Memo, owner, Scope.VISITS, where=(Memo.source == MemoSource.ANALYST,)
    )
    assert len(memos) == 1
    assert memos[0].kind is MemoKind.ASK


async def test_a_safe_rephrase_is_kept_as_the_models_own_words(sg: AsyncSession) -> None:
    rule_report, owner = await _duplicate_report(sg)
    section = _section(rule_report, "medicines_and_supplements")
    assert section is not None
    duplicate = next(i for i in section.insights if i.kind is InsightKind.MEDICINE)

    safe_text = "2 of your medicines are written down under the same kind."
    client = FakeClient(
        [
            FakeMessage(
                content=[
                    _text_block(
                        {
                            "insights": [
                                {
                                    "insight_id": duplicate.insight_id,
                                    "text": safe_text,
                                    "why_plain": "This compares the kind written down for each medicine.",
                                }
                            ]
                        }
                    )
                ]
            )
        ]
    )
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    report: Report | None = None
    async for event in analyst.report_stream(sg, context=owner, language="en"):
        if isinstance(event, Report):
            report = event
    assert report is not None
    assert report.source == "claude"
    section = _section(report, "medicines_and_supplements")
    assert section is not None
    kept = next(i for i in section.insights if i.kind is InsightKind.MEDICINE)
    assert kept.text == safe_text
    # Never a new id, never new evidence — only text and why_plain changed.
    assert kept.insight_id == duplicate.insight_id
    assert kept.evidence == duplicate.evidence


async def test_a_choice_naming_an_id_off_the_candidate_list_is_dropped(sg: AsyncSession) -> None:
    _rule_report, owner = await _duplicate_report(sg)
    client = FakeClient(
        [
            FakeMessage(
                content=[
                    _text_block(
                        {"insights": [{"insight_id": "made:up", "text": "Invented.", "why_plain": "why"}]}
                    )
                ]
            )
        ]
    )
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    report: Report | None = None
    async for event in analyst.report_stream(sg, context=owner, language="en"):
        if isinstance(event, Report):
            report = event
    assert report is not None
    # No candidate was kept: the whole call falls back to the rule report, unchanged.
    assert report.source == "rule"


async def test_falls_back_to_the_rule_report_on_a_refusal_stop_reason(sg: AsyncSession) -> None:
    _rule_report, owner = await _duplicate_report(sg)
    client = FakeClient([FakeMessage(content=[], stop_reason="refusal")])
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    report: Report | None = None
    async for event in analyst.report_stream(sg, context=owner, language="en"):
        if isinstance(event, Report):
            report = event
    assert report is not None
    assert report.source == "rule"


async def test_falls_back_to_the_rule_report_when_cut_off_at_max_tokens(sg: AsyncSession) -> None:
    _rule_report, owner = await _duplicate_report(sg)
    client = FakeClient([FakeMessage(content=[], stop_reason="max_tokens")])
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    report: Report | None = None
    async for event in analyst.report_stream(sg, context=owner, language="en"):
        if isinstance(event, Report):
            report = event
    assert report is not None
    assert report.source == "rule"


async def test_falls_back_to_the_rule_report_when_the_reply_does_not_parse(sg: AsyncSession) -> None:
    _rule_report, owner = await _duplicate_report(sg)
    client = FakeClient([FakeMessage(content=[{"type": "text", "text": "not json"}])])
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    report: Report | None = None
    async for event in analyst.report_stream(sg, context=owner, language="en"):
        if isinstance(event, Report):
            report = event
    assert report is not None
    assert report.source == "rule"


async def test_the_call_asks_for_structured_output_with_a_bare_schema_key(sg: AsyncSession) -> None:
    """The SDK's `JSONOutputFormatParam` reads `schema`, not `json_schema` — the same shape
    every other Claude-backed adapter here already got right (`tests/test_clipmaker.py`)."""
    _rule_report, owner = await _duplicate_report(sg)
    client = FakeClient([FakeMessage(content=[], stop_reason="refusal")])
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    async for _event in analyst.report_stream(sg, context=owner, language="en"):
        pass
    call = client.messages.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "schema" in call["output_config"]["format"]
    assert "json_schema" not in call["output_config"]["format"]
