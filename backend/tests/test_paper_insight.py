"""Checkpoint 3, "What it means for you" (`docs/design/experience-blueprint.html`, scene
`insight`): the paper-scoped insight (`app.reasoning.analyst.paper`) and keeping its offered
questions on a visit (`app.reasoning.visits.questions.keep_paper_insight_questions`).

Mocked throughout — no live model call, no API key: `RuleAnalyst`'s own candidate machinery
(`app.reasoning.analyst.pipeline.finalize`, `app.reasoning.analyst.rule.ask_the_doctor`) is
reused unchanged, and the Claude path is exercised the same way
`tests/test_analyst_claude.py` exercises `ClaudeAnalyst`: a fake `anthropic` client.
"""

from __future__ import annotations

import ast
import inspect
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.delivery import analyst_strings as words
from app.drugs.fixture import FixtureRegistry
from app.ingestion.objects import LocalObjectStore
from app.keys.scopes import KeyRole, Scope
from app.reasoning.analyst.claude_adapter import ClaudeAnalyst, _rebuild
from app.reasoning.analyst.paper import (
    CANDIDATE_SECTION_KEY,
    NotAConfirmedPaper,
    ReadResult,
    build_insight,
    read_phase,
)
from app.reasoning.analyst.port import AskWho, InsightKind, Report, Section
from app.reasoning.visits.models import Memo, MemoKind, MemoSource
from app.reasoning.visits.questions import current_questions, keep_paper_insight_questions
from tests.conftest import Deployment
from tests.medicines_support import add as add_medicine
from tests.medicines_support import label
from tests.paper import LAB_REPORT_VITALS, LIPID_PANEL
from tests.safety_support import clinic, let_in, pa
from tests.test_ingestion import _card, _decide, _yes
from tests.timeline_support import book

REGISTRY = FixtureRegistry.load()


@pytest.fixture
def store(tmp_path: Path) -> LocalObjectStore:
    from app.regions import Region

    return LocalObjectStore(tmp_path, Region.SG)


@pytest.fixture
def extractor():
    from app.ingestion.extract import FixtureExtractor
    from tests.paper import PAPER

    return FixtureExtractor(PAPER)


async def _confirm_paper(session, context, store, extractor, paper_label=LAB_REPORT_VITALS):
    """A confirmed review card for one lab paper, the artifact it names — the shape
    `_confirmed_paper` (`app.reasoning.analyst.paper`) needs to run at all."""
    card, fields = await _card(session, context, store, extractor, paper_label)
    decisions = _decide(fields)
    yes = await _yes(session, context, card, decisions)
    from app.ingestion.review import confirm_review_card

    card, _decided, _facts = await confirm_review_card(
        session, context=context, card_id=card.id, decisions=decisions, confirmation_id=yes
    )
    return card


AFTER_THE_PAPER = datetime(2026, 9, 21, tzinfo=UTC)
"""After every paper fixture's own document date (10-13 September 2026) and after the
suite's frozen clock (3 September 2026, `tests/conftest.FROZEN_AT`): `current_facts` only
returns a fact whose `valid_from` has arrived by `now`, so a paper-scoped read needs its own
`now` past the paper's date, the same way `tests/timeline_support.book` books a visit ahead
of it rather than behind."""


async def _drain(session: AsyncSession, context, artifact_id, *, language: str = "en", registry=None) -> ReadResult:
    result: ReadResult | None = None
    async for event in read_phase(
        session,
        context=context,
        artifact_id=artifact_id,
        language=language,
        registry=registry,
        now=AFTER_THE_PAPER,
    ):
        if isinstance(event, ReadResult):
            result = event
    assert result is not None
    return result


# --- the happy path: an out-of-range value beside a related medicine -----------------------


async def test_an_out_of_range_value_beside_its_medicine_offers_a_question_citing_the_paper(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    owner = await pa(sg, phone="+6591160001")
    await add_medicine(sg, owner, label("atorvastatin", "20 mg", "1 tab OD"))
    card = await _confirm_paper(sg, owner, store, extractor)

    result = await _drain(sg, owner, card.artifact_id, registry=REGISTRY)

    assert result.questions, "an out-of-range LDL beside a statin should offer a question"
    offered = result.questions[0]
    assert offered.kind is InsightKind.MEDICINE
    assert offered.ask_who is AskWho.DOCTOR
    # Cites the paper (artifact id) and the medicine line, never a bare claim.
    kinds = {e.kind for e in offered.evidence}
    assert {"fact", "artifact", "medication_line"} <= kinds
    artifact_evidence = next(e for e in offered.evidence if e.kind == "artifact")
    assert artifact_evidence.id == str(card.artifact_id)
    # No dose, no verdict — a plain statement worth asking about, never advice.
    lowered = offered.text.lower()
    for word in ("dose", "should", "stop", "start", "change", "high", "low", "normal"):
        assert word not in lowered, offered.text
    # "Looked at" names the paper and the medicine actually read, never a fixed list.
    kinds_seen = {one.kind for one in result.looked_at}
    assert "artifact" in kinds_seen and "medicines" in kinds_seen
    assert not result.withheld


async def test_a_paper_with_no_printed_range_has_nothing_worth_asking(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    """`LIPID_PANEL` carries no `_reference_range` sibling on any of its rows: nothing to
    compare against, so nothing is worth asking — said honestly, never padded."""
    owner = await pa(sg, phone="+6591160002")
    card = await _confirm_paper(sg, owner, store, extractor, LIPID_PANEL)

    result = await _drain(sg, owner, card.artifact_id)
    assert result.questions == ()
    insight = build_insight(
        language="en",
        source="rule",
        questions=result.questions,
        looked_at=result.looked_at,
        withheld=result.withheld,
        now=datetime(2026, 9, 21, tzinfo=UTC),
    )
    assert insight.headline == words.PAPER_NOTHING_LINE["en"]


# --- refusals: an unconfirmed card, another profile's artifact -----------------------------


async def test_an_unconfirmed_card_is_refused(sg: AsyncSession, store: LocalObjectStore, extractor) -> None:
    owner = await pa(sg, phone="+6591160003")
    card, _fields = await _card(sg, owner, store, extractor, LAB_REPORT_VITALS)  # never confirmed

    with pytest.raises(NotAConfirmedPaper):
        await _drain(sg, owner, card.artifact_id)


async def test_another_profiles_artifact_is_refused(sg: AsyncSession, store: LocalObjectStore, extractor) -> None:
    owner = await pa(sg, phone="+6591160004")
    stranger = await pa(sg, phone="+6591160005")
    card = await _confirm_paper(sg, owner, store, extractor)

    with pytest.raises(NotAConfirmedPaper):
        await _drain(sg, stranger, card.artifact_id)


# --- a key without MEDICINES: withheld, named, never a dropped insight ---------------------


async def test_a_key_without_medicines_gets_the_insight_with_medicines_withheld_named(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    owner = await pa(sg, phone="+6591160006")
    await add_medicine(sg, owner, label("atorvastatin", "20 mg", "1 tab OD"))
    card = await _confirm_paper(sg, owner, store, extractor)

    viewer = await let_in(
        sg, owner, phone="+6591160007", name="Mei", role=KeyRole.VIEWER,
        scopes={Scope.RECORDS, Scope.VISITS},
    )

    result = await _drain(sg, viewer, card.artifact_id, registry=REGISTRY)
    assert "medicines_and_supplements" in result.withheld
    # The insight is not dropped: the out-of-range value is still worth asking about, just
    # never linked to a medicine this key cannot see.
    assert result.questions
    assert all(q.kind is not InsightKind.MEDICINE for q in result.questions)
    assert not any(e.kind == "medication_line" for q in result.questions for e in q.evidence)


# --- the reroute: a candidate that would change treatment is never printed -----------------


async def test_a_treatment_changing_candidate_is_rerouted_and_its_words_never_appear(
    sg: AsyncSession, store: LocalObjectStore, extractor, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocked = "Stop the atorvastatin now."
    monkeypatch.setitem(words.PAPER_VALUE_LINE, "en", blocked)

    owner = await pa(sg, phone="+6591160008")
    await add_medicine(sg, owner, label("atorvastatin", "20 mg", "1 tab OD"))
    card = await _confirm_paper(sg, owner, store, extractor)

    result = await _drain(sg, owner, card.artifact_id, registry=REGISTRY)

    assert result.questions
    for question in result.questions:
        assert blocked not in question.text
        assert "atorvastatin" not in question.text.lower()
        assert "stop" not in question.text.lower()
    assert any(q.text == words.ASK_THE_DOCTOR_LINE["en"] for q in result.questions)

    memos = await audited_read(sg, Memo, owner, Scope.VISITS)
    filed = [m for m in memos if m.source is MemoSource.ANALYST]
    assert len(filed) == 1
    assert filed[0].kind is MemoKind.ASK


# --- keep: idempotent, on the next visit ----------------------------------------------------


async def test_keep_is_idempotent_and_lands_on_the_next_visit(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    owner = await pa(sg, phone="+6591160009")
    await add_medicine(sg, owner, label("atorvastatin", "20 mg", "1 tab OD"))
    card = await _confirm_paper(sg, owner, store, extractor)
    result = await _drain(sg, owner, card.artifact_id, registry=REGISTRY)
    assert result.questions

    tan = await clinic(sg, owner)
    visit = await book(sg, owner, tan, datetime(2026, 10, 1, 10, 0, tzinfo=UTC), "check-up")

    first = await keep_paper_insight_questions(
        sg, context=owner, appointment_id=visit.id, artifact_id=card.artifact_id,
        insights=result.questions,
    )
    assert len(first) == len(result.questions)

    second = await keep_paper_insight_questions(
        sg, context=owner, appointment_id=visit.id, artifact_id=card.artifact_id,
        insights=result.questions,
    )
    assert second == []  # nothing new: keeping twice never duplicates

    current = await current_questions(sg, context=owner, appointment_id=visit.id)
    assert len([q for q in current if q.source_kind == "paper_insight"]) == len(result.questions)


# --- the Claude adapter path: a fake client, reusing the analyst's own machinery -----------


@dataclass
class FakeMessage:
    content: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "end_turn"


class FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


def _text_block(payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": "text", "text": json.dumps(payload)}


def _temp_report(result: ReadResult, *, language: str = "en") -> Report:
    return Report(
        report_id=str(uuid.uuid4()),
        generated_at=datetime(2026, 9, 21, tzinfo=UTC),
        week_of=datetime(2026, 9, 21, tzinfo=UTC).date(),
        language=language,
        source="rule",
        boundary=(),
        sections=(Section(CANDIDATE_SECTION_KEY, "", tuple(result.questions)),),
    )


async def test_the_claude_path_rephrases_and_a_thinking_block_before_the_answer_is_tolerated(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    owner = await pa(sg, phone="+6591160010")
    await add_medicine(sg, owner, label("atorvastatin", "20 mg", "1 tab OD"))
    card = await _confirm_paper(sg, owner, store, extractor)
    result = await _drain(sg, owner, card.artifact_id, registry=REGISTRY)
    assert result.questions
    report = _temp_report(result)
    offered = result.questions[0]

    safe_text = "This paper's cholesterol number is outside the range printed on it."
    client = FakeClient(
        [
            FakeMessage(
                content=[
                    {"type": "thinking", "thinking": "considering the candidate"},
                    _text_block(
                        {
                            "insights": [
                                {
                                    "insight_id": offered.insight_id,
                                    "text": safe_text,
                                    "why_plain": offered.why_plain,
                                }
                            ]
                        }
                    ),
                ]
            )
        ]
    )
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    raw = await analyst._ask_claude(report)
    assert raw is not None
    choices = json.loads(raw)
    from app.reasoning.analyst.claude_adapter import _parse_choices

    parsed = _parse_choices(json.dumps(choices))
    assert parsed is not None
    rebuilt = await _rebuild(report, parsed, session=sg, context=owner, language="en")
    section = next(s for s in rebuilt.sections if s.key == CANDIDATE_SECTION_KEY)
    assert section.insights[0].text == safe_text
    assert section.insights[0].insight_id == offered.insight_id


async def test_the_claude_path_falls_back_to_rule_questions_on_a_refusal(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    owner = await pa(sg, phone="+6591160011")
    await add_medicine(sg, owner, label("atorvastatin", "20 mg", "1 tab OD"))
    card = await _confirm_paper(sg, owner, store, extractor)
    result = await _drain(sg, owner, card.artifact_id, registry=REGISTRY)
    report = _temp_report(result)

    client = FakeClient([FakeMessage(content=[], stop_reason="refusal")])
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    raw = await analyst._ask_claude(report)
    assert raw is None  # the route's own fallback: keep the rule questions unchanged


# --- no transaction open while a model call is in flight (structural) ----------------------


def test_no_database_transaction_is_open_while_the_model_call_is_in_flight() -> None:
    """`app.channels.api.analyst._paper_events` must never hold a database transaction open
    across the model call: reads close in their own `session_scope`, the model call is made
    with none open, and the rebuild/save opens a second, fresh one. Asserted by structure —
    the source itself — since the route opens its own sessions from a live request, which a
    unit test cannot easily interrupt mid-flight (the same alternative
    `docs/design/redesign-brief.md`'s Health Analyst story allows)."""
    from app.channels.api import analyst as analyst_routes

    source = inspect.getsource(analyst_routes._paper_events)
    tree = ast.parse(source)
    func = tree.body[0]
    assert isinstance(func, ast.AsyncFunctionDef)

    # Every `async with session_scope(...)` block anywhere in the function (the first one
    # sits inside a `try:`, for the `Refusal` a read can raise) — never nested one inside the
    # other, so a database transaction from one is never still open during the other.
    session_blocks = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "session_scope"
            for item in node.items
        )
    ]
    assert len(session_blocks) == 2, "expected two separate session_scope blocks (reads, then write)"
    session_blocks.sort(key=lambda node: node.lineno)
    first, second = session_blocks
    assert first.end_lineno is not None and first.end_lineno < second.lineno, (
        "the two session_scope blocks must not be nested or overlapping"
    )

    def calls_ask_claude(node: ast.AST) -> bool:
        return any(isinstance(n, ast.Attribute) and n.attr == "_ask_claude" for n in ast.walk(node))

    # The model call must not appear inside either `session_scope` block...
    assert not calls_ask_claude(first)
    assert not calls_ask_claude(second)
    # ...only in the function body between them, with no session open at all.
    between = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Await)
        and isinstance(getattr(node, "lineno", None), int)
        and first.end_lineno < node.lineno < second.lineno
    ]
    assert any(calls_ask_claude(node) for node in between), "the model call must sit between the two units of work"


# --- the routes over HTTP: the event contract, and keep with no upcoming visit -------------


def _sse_events(text: str) -> list[dict[str, Any]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in text.split("\n\n")
        if line.startswith("data: ")
    ]


async def test_the_route_streams_steps_then_a_report_and_keep_files_a_standing_memo_with_no_visit(
    deployment: Deployment, store: LocalObjectStore, extractor
) -> None:
    from app.clock import current

    # Past every paper fixture's document date (`AFTER_THE_PAPER`'s own reasoning): moved
    # forward and restored, so this one HTTP-level test does not leave the frozen clock
    # somewhere another test does not expect.
    clock = current()
    before = clock.now()
    clock.set(AFTER_THE_PAPER)
    try:
        await _http_stream_and_keep(deployment, store, extractor)
    finally:
        clock.set(before)


async def _http_stream_and_keep(deployment: Deployment, store: LocalObjectStore, extractor) -> None:
    from app.keys.context import resolve_key_context
    from tests.api import bearer, own_profile, register_by_phone

    session = await register_by_phone(deployment, "+6591160012", "Pa", language="en")
    profile_id = await own_profile(deployment, session, language="en")
    his = bearer(session["token"])

    async with deployment.sessions() as raw:
        owner = await resolve_key_context(
            raw,
            region=deployment.region,
            person_id=uuid.UUID(session["person_id"]),
            profile_id=uuid.UUID(profile_id),
        )
        await add_medicine(raw, owner, label("atorvastatin", "20 mg", "1 tab OD"))
        card = await _confirm_paper(raw, owner, store, extractor)
        await raw.commit()

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/papers/{card.artifact_id}/insight/stream", headers=his
    )
    assert streamed.status_code == 200, streamed.text
    events = _sse_events(streamed.text)
    assert [e["type"] for e in events][:-1] == ["step"] * (len(events) - 1)
    assert events[-1]["type"] == "report"
    report = events[-1]["report"]
    assert set(report.keys()) >= {"report_id", "headline", "looked_at", "questions", "boundary"}
    assert report["questions"]

    kept = await deployment.client.post(
        f"/profiles/{profile_id}/papers/{card.artifact_id}/insight/keep", headers=his
    )
    assert kept.status_code == 201, kept.text
    assert kept.json()["filed"] == "unfiled"
    assert kept.json()["kept_count"] == len(report["questions"])


# --- range edge cases: decimals, a value exactly on a bound, compound text, precedence -----


def test_a_decimal_printed_range_parses() -> None:
    from app.reasoning.analyst.paper import _parse_printed_range

    assert _parse_printed_range("<0.1") == (None, 0.1)


def test_a_value_exactly_on_the_bound_is_not_flagged() -> None:
    from app.reasoning.analyst.paper import _band

    assert _band(130.0, (None, 130.0)) is None  # the bound itself is still "in"
    assert _band(129.99, (None, 130.0)) is None
    assert _band(130.01, (None, 130.0)) == "above"


def test_compound_or_sex_specific_range_text_says_nothing_rather_than_guess() -> None:
    from app.reasoning.analyst.paper import _parse_printed_range

    for text in ("M: 13.5-17.5, F: 12.0-15.5", "Normal", "See report", ""):
        assert _parse_printed_range(text) is None


def test_an_embedded_range_wins_over_a_conflicting_legacy_sibling() -> None:
    from app.reasoning.analyst.paper import _printed_range

    # The embedded shape says in-range (140 < 200); the legacy sibling, if it were read
    # instead, would say out-of-range (140 > 130). The embedded shape must win outright —
    # `_printed_range` never blends the two.
    assert _printed_range({"value": 140, "range": "<200"}, "<130") == (None, 200.0)


def test_the_confirm_flows_own_field_range_wins_over_a_conflicting_embedded_one() -> None:
    """`ReviewField.range` (defect #3, #292: `{"low", "high", "text"}`) is the range the
    confirm flow already parsed off the paper itself — it wins over both the embedded shape
    and the legacy sibling fact when it is present, even when they conflict with it."""
    from app.reasoning.analyst.paper import _printed_range

    # field_range says out-of-range (140 > 130); the embedded value and the legacy sibling,
    # if either were read instead, would both say in-range (140 < 200 / < 300).
    assert _printed_range(
        {"value": 140, "range": "<300"},
        "<300",
        field_range={"low": None, "high": 130.0, "text": "<130"},
    ) == (None, 130.0)


def test_field_range_falls_back_to_its_own_text_when_neither_bound_parsed() -> None:
    """A `field_range` whose `low`/`high` are both `null` — the extractor could not reduce a
    compound or unusual range to numbers — is not the end of it: its own `text` is tried
    here too, on the chance it is one of this module's own literal shapes after all."""
    from app.reasoning.analyst.paper import _printed_range

    assert _printed_range(
        140, None, field_range={"low": None, "high": None, "text": "<130"}
    ) == (None, 130.0)
    # ... and when even that does not parse (compound/sex-specific text), no bounds at all.
    assert (
        _printed_range(
            140, None, field_range={"low": None, "high": None, "text": "M: 0-130, F: 0-110"}
        )
        is None
    )


# --- a key with RECORDS but no VISITS: no visit in "looked at"; keep refuses cleanly -------


async def test_a_key_with_records_but_no_visits_never_names_a_visit_and_keep_refuses_cleanly(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    from app.errors import Refusal
    from app.memory.spine import upcoming_appointments

    owner = await pa(sg, phone="+6591160014")
    card = await _confirm_paper(sg, owner, store, extractor)

    # A caregiver, by role, may change the visits — but this one's own key was narrowed to
    # RECORDS alone, never granted VISITS.
    caregiver = await let_in(
        sg, owner, phone="+6591160015", name="Mei", role=KeyRole.CAREGIVER, scopes={Scope.RECORDS}
    )

    result = await _drain(sg, caregiver, card.artifact_id)
    assert not any(one.kind == "appointment" for one in result.looked_at)

    # "Behaves sanely": a real, existing Refusal (OutOfScope) — never a crash, never a leak.
    with pytest.raises(Refusal):
        await upcoming_appointments(sg, context=caregiver)


# --- a closing account is refused, on this story's own routes too --------------------------


async def test_a_closing_account_is_refused_on_the_paper_insight_routes(
    deployment: Deployment, store: LocalObjectStore, extractor
) -> None:
    from app.clock import current
    from app.keys.context import resolve_key_context
    from tests.api import bearer, own_profile, register_by_phone

    clock = current()
    before = clock.now()
    clock.set(AFTER_THE_PAPER)
    try:
        session = await register_by_phone(deployment, "+6591160016", "Pa", language="en")
        profile_id = await own_profile(deployment, session, language="en")
        his = bearer(session["token"])

        async with deployment.sessions() as raw:
            owner = await resolve_key_context(
                raw,
                region=deployment.region,
                person_id=uuid.UUID(session["person_id"]),
                profile_id=uuid.UUID(profile_id),
            )
            card = await _confirm_paper(raw, owner, store, extractor)
            await raw.commit()

        yes = await deployment.client.post(
            f"/profiles/{profile_id}/confirmations",
            json={"subject": "close_account", "language": "en"},
            headers=his,
        )
        assert yes.status_code == 201, yes.text
        closed = await deployment.client.post(
            f"/profiles/{profile_id}/closure",
            json={"confirmation_id": yes.json()["confirmation_id"], "language": "en"},
            headers=his,
        )
        assert closed.status_code == 201, closed.text

        streamed = await deployment.client.post(
            f"/profiles/{profile_id}/papers/{card.artifact_id}/insight/stream", headers=his
        )
        assert streamed.status_code == 403
        assert streamed.json() == {"refusal": "AccountClosing"}

        kept = await deployment.client.post(
            f"/profiles/{profile_id}/papers/{card.artifact_id}/insight/keep", headers=his
        )
        assert kept.status_code == 403
        assert kept.json() == {"refusal": "AccountClosing"}
    finally:
        clock.set(before)


# --- a caregiver reads the insight about the patient, by name, never "you"/"your" ----------


async def test_a_caregivers_key_reads_the_insight_about_the_patient_by_name(
    deployment: Deployment, store: LocalObjectStore, extractor
) -> None:
    from app.clock import current
    from app.keys.context import resolve_key_context
    from tests.api import bearer, let_in, own_profile, register_by_phone

    clock = current()
    before = clock.now()
    clock.set(AFTER_THE_PAPER)
    try:
        session = await register_by_phone(deployment, "+6591160017", "Pa", language="en")
        profile_id = await own_profile(deployment, session, language="en")
        his = bearer(session["token"])

        async with deployment.sessions() as raw:
            owner = await resolve_key_context(
                raw,
                region=deployment.region,
                person_id=uuid.UUID(session["person_id"]),
                profile_id=uuid.UUID(profile_id),
            )
            await add_medicine(raw, owner, label("atorvastatin", "20 mg", "1 tab OD"))
            card = await _confirm_paper(raw, owner, store, extractor)
            await raw.commit()

        scopes = ["records", "medicines", "visits"]
        her_session = await register_by_phone(deployment, "+6591160018", "Mei", language="en")
        hers = bearer(her_session["token"])
        await let_in(
            deployment, session, profile_id, "+6591160018", scopes, role="caregiver",
            holder_display_name="Mei",
        )
        granted = await deployment.client.post(
            f"/profiles/{profile_id}/keys",
            json={"holder_phone_e164": "+6591160018", "role": "caregiver", "scopes": scopes},
            headers=his,
        )
        assert granted.status_code == 201, granted.text

        streamed = await deployment.client.post(
            f"/profiles/{profile_id}/papers/{card.artifact_id}/insight/stream", headers=hers
        )
        assert streamed.status_code == 200, streamed.text
        events = _sse_events(streamed.text)
        report = events[-1]["report"]
        assert report["questions"], "the caregiver holds every scope this paper needs"
        text = json.dumps(report)
        assert "Pa" in text  # the patient by name
        assert " your " not in text.lower() and "\"you " not in text.lower()
    finally:
        clock.set(before)
