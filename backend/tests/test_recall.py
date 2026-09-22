"""E03-05 acceptance.

    Answers cite the artefact; consult answers play the clip at the timestamp.

Pa asks by voice and hears one line; Mei asks in text and reads a few. An answer is made only
of templates and the values of the facts it cites, every cited line naming ids that exist on
his profile — the artefact or the event under a fact, the visit and its provider, the medicine
line and its label. When nothing answers, it says so and names the doctor; a question that
would change treatment is a question for the doctor; the boundary is last, always. The
question is kept as a MESSAGE artefact by reference, the ask is on the trail, and a key without
the ask scope is refused and that is on the trail too. Parts the key does not reach — a part
the owner keeps "only me" among them — are withheld by name. Which parts a question is about
is the retriever's to say, behind its port: keywords by default, fixtures keyed by the sha256
of the question in the tests. No model is called.

The clip half of the acceptance waits for consult recordings with timestamps (E02-05): a
citation names the artefact, and the clip is played from it when there is one to play.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.delivery.timeline_strings import verified
from app.ingestion.extract import DocumentKind
from app.ingestion.models import FieldState, ReviewCard, ReviewField
from app.ingestion.objects import LocalObjectStore
from app.keys.context import KeyContext, OutOfScope
from app.keys.repository import scoped_new
from app.keys.scopes import ROLE_SCOPES, KeyRole, Scope
from app.medicines.models import MedicationLine
from app.memory.models import (
    Appointment,
    Artifact,
    ArtifactKind,
    Attachment,
    Event,
    Fact,
    Provider,
)
from app.memory.semantic import assert_fact
from app.regions import Region
from app.safety.boundary import Surface, boundary_lines
from app.search.ask import Answer, Mode, NotAQuestion, recall
from app.search.retrieve import (
    FixtureRetriever,
    KeywordRetriever,
    NotAFixture,
    Retriever,
    question_digest,
)
from tests.medicines_support import REGISTRY, let_in, pa
from tests.timeline_support import SITI_PHONE, again, artefact, keep_only_me, record, trail

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "recall"

TABLES = {
    "fact": Fact,
    "event": Event,
    "artifact": Artifact,
    "appointment": Appointment,
    "provider": Provider,
    "medication_line": MedicationLine,
    "attachment": Attachment,
}


async def ask(
    session: AsyncSession,
    context: KeyContext,
    question: str,
    tmp_path: Path,
    *,
    mode: Mode = Mode.TEXT,
    retriever: Retriever | None = None,
    language: str | None = None,
) -> Answer:
    return await recall(
        session,
        context=context,
        question=question,
        mode=mode,
        retriever=retriever or KeywordRetriever(),
        store=LocalObjectStore(tmp_path, Region.SG),
        registry=REGISTRY,
        language=language,
    )


async def every_cite_is_on_this_profile(
    session: AsyncSession, context: KeyContext, answer: Answer
) -> None:
    for line in answer.lines:
        assert line.cites, line.text
        for cite in line.cites:
            row = await session.get(TABLES[cite.kind], cite.id)
            assert row is not None and row.profile_id == context.profile_id, cite


async def test_pa_asks_by_voice_and_hears_one_cited_line_then_the_boundary(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    answer = await ask(sg, rec.owner, "what was my blood pressure", tmp_path, mode=Mode.VOICE)
    assert [line.text for line in answer.lines] == [
        "Your blood pressure on Wednesday 2 September was 138 over 84."
    ]
    newest = rec.readings[1]
    assert [(c.kind, c.id) for c in answer.lines[0].cites] == [
        ("fact", newest.id),
        ("event", newest.event_id),
    ]
    assert answer.honest == ()
    assert answer.boundary == boundary_lines(Surface.RECALL, "en", doctor="Dr Tan")
    assert answer.spoken[-3:] == [
        "Nura looked in your papers.",
        "This is not a doctor's advice.",
        "Ask Dr Tan.",
    ]


async def test_mei_asks_in_text_what_dr_tan_said_and_every_line_cites_what_it_rests_on(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    answer = await ask(sg, rec.mei, "what did Dr Tan say", tmp_path)
    texts = {line.text for line in answer.lines}
    assert texts == {
        "Your next visit is to Dr Tan on Thursday 10 September.",
        "You saw Dr Tan on Monday 24 August.",
        "Dr Tan gave you your blood pressure tablet.",
        "Your cholesterol test from Thursday 7 September is in your papers.",
    }
    await every_cite_is_on_this_profile(sg, rec.owner, answer)
    paper = next(line for line in answer.lines if "papers" in line.text)
    # The answer cites the artefact (E03-05), and the facts read off it.
    assert ("artifact", rec.paper.id) in [(c.kind, c.id) for c in paper.cites]
    assert {c.id for c in paper.cites if c.kind == "fact"} == {fact.id for fact in rec.lab}
    medicine = next(line for line in answer.lines if "tablet" in line.text)
    assert ("medication_line", rec.medicine.line.id) in [(c.kind, c.id) for c in medicine.cites]
    assert answer.spoken[-1] == "Ask Dr Tan."


async def test_a_question_nothing_answers_gets_the_honest_line_and_the_boundary(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    answer = await ask(sg, rec.owner, "do I have cancer", tmp_path)
    assert not answer.answered and answer.lines == ()
    assert answer.honest == ("Nura does not have that written down.", "Ask Dr Tan.")
    assert answer.spoken == [
        "Nura does not have that written down.",
        "Ask Dr Tan.",
        "Nura looked in your papers.",
        "This is not a doctor's advice.",
        "Ask Dr Tan.",
    ]


async def test_a_question_that_would_change_treatment_is_a_question_for_the_doctor(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    answer = await ask(sg, rec.owner, "should I stop my blood pressure tablet", tmp_path)
    assert answer.lines[0].text == "Dr Tan gave you your blood pressure tablet."
    assert answer.honest == ("Ask Dr Tan before you change any medicine.",)
    assert answer.spoken[-1] == "Ask Dr Tan."
    assert not any("stop" in line.lower() for line in answer.spoken)


async def test_the_question_is_kept_by_reference_and_the_ask_is_on_the_trail(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    question = "what was my blood pressure"
    answer = await ask(sg, rec.owner, question, tmp_path, mode=Mode.VOICE)
    kept = await sg.get(Artifact, answer.question_artifact_id)
    assert kept is not None and kept.kind is ArtifactKind.MESSAGE
    assert kept.storage_key.startswith(f"questions/{rec.owner.profile_id}/")
    store = LocalObjectStore(tmp_path, Region.SG)
    assert await store.get(kept.storage_key) == question.encode("utf-8")
    assert question not in {kept.storage_key, kept.content_type, kept.sha256}
    asked = [e for e in await trail(sg, rec.owner) if e.target == "ask"]
    assert [(e.action, e.scope, e.target_id, e.rows) for e in asked] == [
        (Action.READ, Scope.ASK, kept.id, 1)
    ]


async def test_a_key_without_the_ask_scope_is_refused_and_it_is_written_down(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    siti = await let_in(
        sg,
        rec.owner,
        phone=SITI_PHONE,
        name="Siti",
        role=KeyRole.HELPER,
        scopes=set(ROLE_SCOPES[KeyRole.HELPER]),
    )
    with pytest.raises(OutOfScope):
        await ask(sg, siti, "what was my blood pressure", tmp_path)
    refused = [
        e
        for e in await trail(sg, rec.owner)
        if e.outcome is Outcome.REFUSED and e.actor_person_id == siti.person_id
    ]
    assert [(e.target, e.scope, e.refused_because) for e in refused] == [
        ("ask", Scope.ASK, "OutOfScope")
    ]


async def test_a_part_the_owner_keeps_only_me_is_withheld_from_the_answer(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    await keep_only_me(sg, rec.owner, Scope.READINGS)
    mei = await again(sg, rec.mei)
    answer = await ask(sg, mei, "what was my blood pressure", tmp_path)
    assert answer.lines == () and Scope.READINGS in answer.withheld
    assert answer.honest[0] == "Nura does not have that written down."
    his = await ask(sg, rec.owner, "what was my blood pressure", tmp_path, mode=Mode.VOICE)
    assert his.answered


async def test_the_fixture_retriever_answers_by_the_sha256_of_the_question(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    fixtures = FixtureRetriever.load(FIXTURES)
    answer = await ask(sg, rec.mei, "What did Dr Tan say?", tmp_path, retriever=fixtures)
    assert "You saw Dr Tan on Monday 24 August." in {line.text for line in answer.lines}
    unknown = await ask(sg, rec.mei, "what did the nurse say", tmp_path, retriever=fixtures)
    assert not unknown.answered
    bad = tmp_path / "fixtures"
    bad.mkdir()
    (bad / "x.json").write_text(json.dumps({"question": "a", "sha256": "b" * 64, "names": []}))
    with pytest.raises(NotAFixture):
        FixtureRetriever.load(bad)
    assert question_digest("What did Dr Tan say?") == question_digest("what did dr tan say")


@pytest.mark.parametrize(
    ("language", "question"),
    [("ms", "tekanan darah saya"), ("zh", "我的血压"), ("en", "when did I see Dr Tan")],
)
async def test_every_line_passes_plain_words_in_his_language(
    sg: AsyncSession, tmp_path: Path, language: str, question: str
) -> None:
    rec = await record(sg, language=language)
    for asked in (question, "what did Dr Tan say", "do I have cancer"):
        answer = await ask(sg, rec.owner, asked, tmp_path)
        assert answer.language == language and answer.dropped == 0
        for line in answer.spoken:
            assert verified(line, language), line
        await every_cite_is_on_this_profile(sg, rec.owner, answer)
    heard = await ask(sg, rec.owner, question, tmp_path, mode=Mode.VOICE)
    # Voice says one thing: one line, or two where the day would crowd the numbers (Chinese).
    assert heard.answered and len({line.cites for line in heard.lines}) == 1
    assert len(heard.lines) == (2 if language == "zh" else 1)


def test_recall_calls_no_model() -> None:
    """The retriever is a port; nothing under app/search reaches a model or the network."""
    root = Path(__file__).resolve().parents[1] / "app" / "search"
    for path in root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for name in ("anthropic", "openai", "httpx", "requests", "urllib"):
            assert f"import {name}" not in source and f"from {name}" not in source, path


@pytest.mark.parametrize("question", ["   ", "x" * 301, "two\nlines"])
async def test_a_question_is_one_line_of_at_most_three_hundred_characters(
    sg: AsyncSession, tmp_path: Path, question: str
) -> None:
    rec = await record(sg)
    with pytest.raises(NotAQuestion):
        await ask(sg, rec.owner, question, tmp_path)
    assert [e.refused_because for e in await trail(sg, rec.owner) if e.target == "ask"] == [
        "NotAQuestion"
    ]


# --- D-1 (audit-2026-09-22.md §3.1/§5): a measured value has somewhere to live ---------------
#
# Before this fix the only catalogue template that could state a measured value was
# `READING`, blood-pressure-only (`timeline_strings.py:544-548`) — a lab value fell back to
# `RECALL["paper"]`, which never touches `fact.value` at all. The owner's own case, reproduced
# by the audit: "How is my cholesterol?" answered with no number; "Is it high?" answered "Nura
# does not have that written down." about a paper he had already confirmed. These fixtures
# prove the opposite now, on a value the rule-based asker itself composes — never a guideline
# table's opinion, only what the paper printed or did not (`app.search.printed_range`).

WHEN = datetime(2026, 1, 21, 2, 0, tzinfo=UTC)
"""10 in the morning, Singapore, Wednesday 21 January 2026 — the frozen instant these D-1
fixtures use throughout, so `say_date` always answers the same worded day."""


async def _lipid_fact(
    session: AsyncSession,
    context: KeyContext,
    *,
    attribute: str,
    value: float,
    printed_range: dict[str, float | str | None] | None = None,
) -> tuple[Fact, Artifact]:
    """A confirmed lab fact, dated `WHEN`, from its own paper — with the paper's own printed
    range on file only when `printed_range` says so (`ReviewField.range`, D-1(a)'s own source
    of truth, never a guideline table)."""
    paper = await artefact(session, context, kind=ArtifactKind.PHOTO, when=WHEN)
    fact = await assert_fact(
        session,
        context=context,
        subject="lipid_panel",
        attribute=attribute,
        value=value,
        unit="mg/dL",
        confidence=0.95,
        artifact_id=paper.id,
        valid_from=WHEN,
    )
    card = scoped_new(
        ReviewCard,
        context,
        Scope.RECORDS,
        artifact_id=paper.id,
        document_kind=DocumentKind.LAB_REPORT,
        document_date=WHEN.date(),
        confirmed_at=WHEN,
        confirmed_by_person_id=context.person_id,
    )
    session.add(card)
    await session.flush()
    field = scoped_new(
        ReviewField,
        context,
        Scope.RECORDS,
        card_id=card.id,
        position=0,
        subject="lipid_panel",
        attribute=attribute,
        value=value,
        unit="mg/dL",
        confidence=0.95,
        range=printed_range,
        state=FieldState.CONFIRMED,
        fact_id=fact.id,
        decided_at=WHEN,
    )
    session.add(field)
    await session.flush()
    return fact, paper


async def test_a_measured_value_with_no_printed_range_is_said_with_its_date_never_silenced(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """The owner's own reproduction, part one: a confirmed lipid panel with no printed range
    on the paper answers "How is my cholesterol?" with the number and the date, never the old
    silent `RECALL["paper"]` fallback ("…is in your papers.", no number). A fresh owner (`pa`,
    not the shared `record()` fixture) so this profile holds nothing else named "cholesterol"
    for the retriever to prefer instead."""
    owner = await pa(sg, language="en")
    fact, _paper = await _lipid_fact(sg, owner, attribute="total_cholesterol", value=122)
    answer = await ask(sg, owner, "How is my cholesterol?", tmp_path)
    # Plain words rule 12 (no unit he does not use): the bare number, exactly the shape the
    # app's own onboarding read-back already gets right for the same paper (audit finding (e)).
    assert [line.text for line in answer.lines] == [
        "Your cholesterol test was 122 on Wednesday 21 January.",
        "No range is printed on the paper.",
    ]
    assert {cite.kind for line in answer.lines for cite in line.cites} >= {"fact"}
    assert {cite.id for line in answer.lines for cite in line.cites if cite.kind == "fact"} == {
        fact.id
    }
    for line in answer.spoken:
        assert verified(line, "en"), line


@pytest.mark.parametrize(
    ("value", "printed_range", "band_line"),
    [
        (140, {"low": None, "high": 130, "text": "<130"}, "It is above the range printed on the paper."),
        (100, {"low": None, "high": 130, "text": "<130"}, "It is within the range printed on the paper."),
        (30, {"low": 40, "high": 130, "text": "40 - 130"}, "It is below the range printed on the paper."),
    ],
)
async def test_a_measured_value_against_its_printed_range_never_the_apps_own_judgement(
    sg: AsyncSession,
    tmp_path: Path,
    value: float,
    printed_range: dict[str, float | str | None],
    band_line: str,
) -> None:
    """The owner's own reproduction, part two: with a printed range on file, the answer says
    above/below/within exactly as the paper prints it — never a guideline table's opinion, and
    never the conclusion-language veto's word ("high"/"low"): D-3's finding for that veto stays
    for a line that uses the questioner's OWN word, not for one reporting the paper's own
    printed comparison in neutral words."""
    owner = await pa(sg, language="en")
    await _lipid_fact(sg, owner, attribute="ldl", value=value, printed_range=printed_range)
    answer = await ask(sg, owner, "Is my cholesterol high?", tmp_path)
    assert answer.lines, "never a silent fallback for a value with a printed range on file"
    assert answer.lines[-1].text == band_line
    for line in answer.spoken:
        assert verified(line, "en"), line
