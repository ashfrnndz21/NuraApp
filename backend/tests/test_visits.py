"""The visit loop at the service (E05-01, E05-02, E05-05, E05-06).

Gaps from the record; the brief in the profile's language, every line through the verifier
and refused whole when one fails; questions from gaps, memos and flags with their sources,
editable with a person's yes, one card for him; the transcript as an artefact, the summary
card, and on the yes: memos, a planned visit, facts citing the transcript, a flag for the
medicine change — and never a change to a medicine; the memo card, consolidated.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.db import ImmutableRow, as_utc
from app.drafts import QuestionDraft
from app.ingestion.objects import LocalObjectStore
from app.keys.confirm import NotWhatWasConfirmed, confirm
from app.keys.context import OutOfScope, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.memory.models import (
    AppointmentStatus,
    Artifact,
    ArtifactKind,
    ConfidenceState,
)
from app.memory.semantic import assert_fact, current_facts, supersede_fact
from app.memory.spine import upcoming_appointments
from app.reasoning.visits import strings
from app.reasoning.visits.brief import brief_for, build_brief
from app.reasoning.visits.gaps import GapKind, find_gaps
from app.reasoning.visits.memos import consolidate_memos, current_memos, memo_card, write_memo
from app.reasoning.visits.models import (
    Brief,
    Flag,
    FlagKind,
    ItemState,
    Memo,
    MemoKind,
    MemoSource,
    Question,
    QuestionSource,
    SummaryItemKind,
    VisitSummary,
)
from app.reasoning.visits.questions import (
    CARD_SIZE,
    change_questions,
    patient_card,
    question_draft_for,
    questions_for,
)
from app.reasoning.visits.strings import NotPlainEnough, day_and_date
from app.reasoning.visits.summary import (
    AlreadyConfirmed,
    ChangeKind,
    Decision,
    FactHeard,
    FixtureSummariser,
    NotATranscript,
    Span,
    SummaryDraft,
    confirm_summary,
    post_visit_summary,
    reroute_medicine_facts,
    store_transcript,
    summary_draft_for,
    summary_items,
)
from app.regions import Region
from app.safety.plain_words import verify
from app.state.service import current_state
from tests.support import agree_to_family_sharing, refused_unit
from tests.visits import (
    RED_FLAG,
    ROUTINE,
    SEPT_3,
    VISIT_AT,
    VISITS,
    medicine,
    pa,
    reading,
    transcript,
    visit,
)


def _clean(lines: list[str], language: str) -> None:
    for line in lines:
        assert [f for f in verify(line, language) if f.severity != "note"] == [], line


# --- gaps -----------------------------------------------------------------------------------


async def test_gaps_are_structured_and_name_their_facts(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    context = await pa(sg)
    bp = await reading(sg, context)
    line = await medicine(sg, context, name="Furosemide")
    await medicine(sg, context, name="Amlodipine", purpose="blood pressure", digest="b" * 64)
    _provider, appointment = await visit(sg, context, purpose="visit")
    disputed = await supersede_fact(
        sg,
        context=context,
        fact_id=bp.id,
        value={"systolic": 130, "diastolic": 80},
        confidence=1.0,
        confidence_state=ConfidenceState.DISPUTED,
        confirmation_id=(
            await confirm(
                sg,
                context,
                __import__("tests.test_memory", fromlist=["_next"])
                ._next(bp, {"systolic": 130, "diastolic": 80})
                .__class__(
                    subject=bp.subject,
                    attribute=bp.attribute,
                    value={"systolic": 130, "diastolic": 80},
                    unit=bp.unit,
                    confidence=1.0,
                    confidence_state=ConfidenceState.DISPUTED,
                    artifact_id=bp.artifact_id,
                    event_id=bp.event_id,
                    episode_id=bp.episode_id,
                    supersedes_id=bp.id,
                ),
            )
        ).id,
    )
    clock.step(timedelta(days=20))

    gaps = await find_gaps(sg, context=context, appointment_id=appointment.id)
    kinds = {gap.kind: gap for gap in gaps}
    assert set(kinds) == {
        GapKind.READING_STALE,
        GapKind.MEDICINE_NO_PURPOSE,
        GapKind.OPEN_DISPUTE,
        GapKind.APPOINTMENT_NO_PURPOSE,
    }
    assert kinds[GapKind.READING_STALE].fact_ids == (bp.id,)
    assert kinds[GapKind.READING_STALE].since == SEPT_3
    no_purpose = kinds[GapKind.MEDICINE_NO_PURPOSE]
    assert no_purpose.medicine == "Furosemide"
    assert set(no_purpose.fact_ids) == {fact.id for fact in line}
    assert kinds[GapKind.OPEN_DISPUTE].fact_ids == (disputed.id, bp.id)
    assert kinds[GapKind.APPOINTMENT_NO_PURPOSE].subject == str(appointment.id)


async def test_an_expired_fact_with_nothing_current_is_a_gap(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    context = await pa(sg)
    photo = await __import__("tests.visits", fromlist=["label_photo"]).label_photo(sg, context)
    old = await assert_fact(
        sg,
        context=context,
        subject="lipid_panel",
        attribute="ldl",
        value=152,
        unit="mg/dL",
        confidence=0.9,
        artifact_id=photo.id,
        valid_from=SEPT_3 - timedelta(days=400),
        valid_to=SEPT_3 - timedelta(days=30),
    )
    gaps = await find_gaps(sg, context=context)
    assert [(gap.kind, gap.subject, gap.fact_ids) for gap in gaps] == [
        (GapKind.FACT_EXPIRED, "lipid_panel", (old.id,))
    ]
    # A fresh value closes the gap.
    await assert_fact(
        sg,
        context=context,
        subject="lipid_panel",
        attribute="ldl",
        value=120,
        unit="mg/dL",
        confidence=0.9,
        artifact_id=photo.id,
    )
    assert await find_gaps(sg, context=context) == []


# --- the brief ------------------------------------------------------------------------------


async def test_the_brief_is_in_malay_verified_and_names_its_state(sg: AsyncSession) -> None:
    context = await pa(sg, language="ms")
    await reading(sg, context)
    await medicine(sg, context)
    _provider, appointment = await visit(sg, context)

    brief = await build_brief(sg, context=context, appointment_id=appointment.id)
    texts = [line["text"] for line in brief.lines]
    _clean(texts, "ms")
    assert brief.language == "ms"
    assert texts[0] == "Anda berjumpa Dr Tan pada Khamis 10 September."
    assert texts[1] == "Lawatan ini tentang blood pressure check."
    sections = [line["section"] for line in brief.lines]
    assert sections[:2] == ["purpose", "purpose"]
    assert "changed" in sections and "questions" in sections and "bring" in sections
    changed = [line for line in brief.lines if line["section"] == "changed"]
    # The reading and the two medicine facts arrived since the first snapshot.
    assert {line["key"] for line in changed} == {"changed_readings", "changed_medicines"}
    assert all(line["sources"] for line in changed)
    asked = [line for line in brief.lines if line["section"] == "questions"]
    assert "Tanya Dr Tan untuk apa pil air." in [line["text"] for line in asked]
    assert brief.state_id == (await current_state(sg, context=context)).id
    assert brief.since_state_id is None  # no earlier visit: measured from nothing
    assert "Bawa buku tekanan darah anda." in texts and "Bawa ubat anda dalam kotaknya." in texts

    async with refused_unit(sg, ImmutableRow):
        brief.language = "en"
        await sg.flush()
    await sg.refresh(brief)
    assert brief.language == "ms"


async def test_the_brief_is_rebuilt_only_when_state_moved(sg: AsyncSession) -> None:
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    first = await brief_for(sg, context=context, appointment_id=appointment.id)
    again = await brief_for(sg, context=context, appointment_id=appointment.id)
    assert again.id == first.id
    await reading(sg, context)
    third = await brief_for(sg, context=context, appointment_id=appointment.id)
    assert third.id != first.id and third.state_id != first.state_id
    assert (await sg.scalar(select(Brief.id).where(Brief.id == first.id))) is not None


async def test_a_brief_with_one_line_that_fails_the_verifier_is_refused_whole(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deliberately bad template: a fragment (docs/plain-words.md rule 1). The brief is
    refused as NotPlainEnough, nothing is written, and the refusal is on the trail."""
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    bad = {
        **strings.TEMPLATES,
        "bring_bp_book": {"en": "Only the part for you.", "ms": "x", "zh": "x"},
    }
    monkeypatch.setattr(strings, "TEMPLATES", bad)
    async with refused_unit(sg, NotPlainEnough):
        await build_brief(sg, context=context, appointment_id=appointment.id)
    assert (await sg.scalars(select(Brief))).all() == []
    refused = [e for e in await read_audit(sg, context=context) if e.outcome is Outcome.REFUSED]
    assert {(e.refused_because, e.target) for e in refused} == {("NotPlainEnough", "brief")}


async def test_a_purpose_that_is_not_plain_refuses_the_brief(sg: AsyncSession) -> None:
    """The purpose label is rendered into a patient line, so a caregiver's jargon fails it."""
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context, purpose="BP review")
    with pytest.raises(NotPlainEnough) as refused:
        await build_brief(sg, context=context, appointment_id=appointment.id)
    assert "review" in refused.value.text


async def test_a_key_without_the_visits_cannot_read_the_brief(sg: AsyncSession) -> None:
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    mei = await __import__("app.identity.service", fromlist=["register_person"]).register_person(
        sg, region=Region.SG, display_name="Mei", phone_e164="+6592220002"
    )
    await agree_to_family_sharing(sg, context, mei, scopes={Scope.READINGS, Scope.RECORDS})
    await grant_key(
        sg,
        context=context,
        holder=mei,
        role=KeyRole.CAREGIVER,
        scopes={Scope.READINGS, Scope.RECORDS},
    )
    hers = await resolve_key_context(
        sg, region=Region.SG, person_id=mei.id, profile_id=context.profile_id
    )
    async with refused_unit(sg, OutOfScope):
        await brief_for(sg, context=hers, appointment_id=appointment.id)
    refused = [
        e
        for e in await read_audit(sg, context=context)
        if e.outcome is Outcome.REFUSED and e.actor_person_id == mei.id
    ]
    assert {(e.scope, e.target) for e in refused} == {(Scope.VISITS, "brief")}


# --- questions ------------------------------------------------------------------------------


async def test_questions_carry_their_source_and_a_flag_becomes_a_question_not_advice(
    sg: AsyncSession,
) -> None:
    context = await pa(sg, language="en")
    line = await medicine(sg, context, name="Furosemide")
    _provider, appointment = await visit(sg, context)
    await __import__("app.audit.access", fromlist=["audited_write"]).audited_write(
        sg,
        Flag,
        context,
        Scope.RECORDS,
        kind=FlagKind.MEDICINE_CHANGE_HEARD,
        code=ChangeKind.DOSE.value,
        subject="furosemide",
        fact_ids=[],
        payload={"drug": "furosemide", "change": "dose"},
        raised_at=SEPT_3,
    )
    found = await questions_for(sg, context=context, appointment_id=appointment.id)
    by_text = {q.text: q for q in found}
    _clean(list(by_text), "en")
    dose = by_text["Ask Dr Tan about the new amount of the water pill (furosemide)."]
    assert dose.source is QuestionSource.FLAG and dose.priority == 1
    purpose = by_text["Ask Dr Tan what the water pill (furosemide) is for."]
    assert purpose.source is QuestionSource.GAP
    assert purpose.source_kind == GapKind.MEDICINE_NO_PURPOSE.value
    assert set(purpose.source_ids) == {str(fact.id) for fact in line}
    assert found[0] is dose  # the medicine change first
    for text in by_text:
        assert not any(word in text.lower() for word in ("take ", "stop ", "start ", "half"))
    assert all(q.state_id for q in found)

    # Asking again with nothing moved writes nothing new.
    again = await questions_for(sg, context=context, appointment_id=appointment.id)
    assert [q.id for q in again] == [q.id for q in found]


async def test_a_person_adds_edits_and_removes_a_question_with_a_yes(sg: AsyncSession) -> None:
    context = await pa(sg, language="en")
    await medicine(sg, context)
    _provider, appointment = await visit(sg, context)
    before = await questions_for(sg, context=context, appointment_id=appointment.id)
    generated = before[0]

    text = "Is the water pill bad for my kidneys?"
    draft = await question_draft_for(
        sg,
        context=context,
        appointment_id=appointment.id,
        text=text,
        question_id=None,
        remove=False,
    )
    assert draft == QuestionDraft(appointment.id, text, "en", None, False)
    yes = await confirm(sg, context, draft)
    added = await change_questions(
        sg, context=context, appointment_id=appointment.id, confirmation_id=yes.id, text=text
    )
    assert added.source is QuestionSource.PERSON and added.added_by_person_id == context.person_id
    assert added.priority == 2

    # A yes for other words is refused.
    other = await confirm(
        sg,
        context,
        QuestionDraft(appointment.id, "Is the water pill too strong?", "en", None, False),
    )
    async with refused_unit(sg, NotWhatWasConfirmed):
        await change_questions(
            sg, context=context, appointment_id=appointment.id, confirmation_id=other.id, text=text
        )

    # An edit is a new row superseding the old.
    edit = "Is the water pill bad for my kidneys, Dr Tan?"
    yes = await confirm(sg, context, QuestionDraft(appointment.id, edit, "en", added.id, False))
    edited = await change_questions(
        sg,
        context=context,
        appointment_id=appointment.id,
        confirmation_id=yes.id,
        text=edit,
        question_id=added.id,
    )
    assert edited.supersedes_id == added.id and added.superseded_at is not None
    current = await questions_for(sg, context=context, appointment_id=appointment.id)
    assert edited.id in {q.id for q in current} and added.id not in {q.id for q in current}

    # A removal of a generated question is a tombstone, and it is not proposed again.
    yes = await confirm(sg, context, QuestionDraft(appointment.id, "", "en", generated.id, True))
    gone = await change_questions(
        sg,
        context=context,
        appointment_id=appointment.id,
        confirmation_id=yes.id,
        question_id=generated.id,
        remove=True,
    )
    assert gone.removed and gone.supersedes_id == generated.id
    current = await questions_for(sg, context=context, appointment_id=appointment.id)
    assert generated.id not in {q.id for q in current}
    assert generated.text not in {q.text for q in current}


async def test_a_fragment_typed_by_a_person_is_refused_by_the_verifier(sg: AsyncSession) -> None:
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    fragment = "Only the part for you."
    yes = await confirm(sg, context, QuestionDraft(appointment.id, fragment, "en", None, False))
    async with refused_unit(sg, NotPlainEnough):
        await change_questions(
            sg,
            context=context,
            appointment_id=appointment.id,
            confirmation_id=yes.id,
            text=fragment,
        )
    assert (await sg.scalars(select(Question).where(Question.text == fragment))).all() == []
    refused = [e for e in await read_audit(sg, context=context) if e.outcome is Outcome.REFUSED]
    assert {e.refused_because for e in refused} == {"NotPlainEnough"}


async def test_his_card_is_the_first_three_by_priority_and_one_screen(sg: AsyncSession) -> None:
    context = await pa(sg, language="ms")
    await reading(sg, context)
    await medicine(sg, context, name="Furosemide")
    await medicine(sg, context, name="Amlodipine", digest="b" * 64)
    _provider, appointment = await visit(sg, context, purpose="visit")
    found = await questions_for(sg, context=context, appointment_id=appointment.id)
    assert len(found) >= 3
    card = await patient_card(sg, context=context, appointment_id=appointment.id)
    assert card[:CARD_SIZE] == [q.text for q in found[:CARD_SIZE]]
    assert card[-1] == "Anda tidak perlu ingat semua ini."
    assert len(card) == CARD_SIZE + 1
    _clean(card, "ms")


# --- memos ----------------------------------------------------------------------------------


async def test_memos_are_verified_consolidated_and_read_back_as_the_card(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    first = await write_memo(
        sg,
        context=context,
        kind=MemoKind.ACTION,
        key="lighter_dinners",
        slots={},
        source=MemoSource.CONVERSATION,
        appointment_id=appointment.id,
    )
    clock.step(timedelta(minutes=1))
    second = await write_memo(
        sg,
        context=context,
        kind=MemoKind.ACTION,
        key="lighter_dinners",
        slots={},
        source=MemoSource.CONVERSATION,
        appointment_id=appointment.id,
    )
    asked = await write_memo(
        sg,
        context=context,
        kind=MemoKind.ASK,
        key="ask_new_amount",
        slots={"doctor": "Dr Tan", "medicine": "the water pill (furosemide)"},
        source=MemoSource.CONVERSATION,
        appointment_id=appointment.id,
    )
    assert first.text == "Eat lighter dinners." and first.state_id and len(first.text) <= 80
    kept = await consolidate_memos(sg, context=context)
    assert [m.id for m in kept] == [second.id, asked.id]
    assert first.superseded_at is not None and second.superseded_at is None
    card = await memo_card(sg, context=context)
    assert card == [
        "Eat lighter dinners.",
        "Ask Dr Tan about the new amount of the water pill (furosemide).",
    ]
    _clean(card, "en")
    assert [
        m.id for m in await current_memos(sg, context=context, appointment_id=appointment.id)
    ] == [
        second.id,
        asked.id,
    ]
    async with refused_unit(sg, ImmutableRow):
        asked.text = "Something else."
        await sg.flush()
    await sg.refresh(asked)
    assert asked.text.startswith("Ask Dr Tan")


async def test_a_memo_from_a_template_that_is_not_plain_is_refused(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await pa(sg, language="en")
    bad = {**strings.TEMPLATES, "lighter_dinners": {"en": "Lighter dinners.", "ms": "x", "zh": "x"}}
    monkeypatch.setattr(strings, "TEMPLATES", bad)
    async with refused_unit(sg, NotPlainEnough):
        await write_memo(
            sg,
            context=context,
            kind=MemoKind.ACTION,
            key="lighter_dinners",
            slots={},
            source=MemoSource.CONVERSATION,
        )
    assert (await sg.scalars(select(Memo))).all() == []


# --- the post-visit summary -----------------------------------------------------------------


def test_the_fixtures_are_keyed_by_the_digest_of_their_transcript() -> None:
    import hashlib
    import json

    for path in sorted(VISITS.glob("*.json")):
        fixture = json.loads(path.read_text())
        assert fixture["sha256"] == hashlib.sha256(fixture["transcript"].encode()).hexdigest(), path
        for group in fixture["summary"].values():
            for item in group:
                span = item["span"]
                assert 0 <= span["start"] < span["end"] <= len(fixture["transcript"]), (path, item)


def test_a_fact_heard_about_a_dose_is_rerouted_as_a_question_never_a_fact() -> None:
    draft = SummaryDraft(
        facts_heard=(
            FactHeard(
                "medicine",
                "dose",
                {"drug": "warfarin", "instruction": "2 tablets"},
                "tablet",
                Span(0, 5),
                0.9,
            ),
            FactHeard("medicine", "stop", "aspirin", None, Span(6, 10), 0.8),
            FactHeard(
                "blood_pressure",
                "reading",
                {"systolic": 142, "diastolic": 88},
                "mmHg",
                Span(11, 20),
                0.8,
            ),
        )
    )
    rerouted = reroute_medicine_facts(draft)
    assert [(c.drug, c.change) for c in rerouted.medication_changes] == [
        ("warfarin", ChangeKind.DOSE),
        ("aspirin", ChangeKind.STOP),
    ]
    assert [f.subject for f in rerouted.facts_heard] == ["blood_pressure"]


async def test_transcript_in_summary_card_out_memos_on_the_yes(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    context = await pa(sg, language="en")
    await reading(sg, context)
    await medicine(sg, context, name="Furosemide")
    _provider, appointment = await visit(sg, context)
    store = LocalObjectStore(tmp_path, Region.SG)
    clock.set(VISIT_AT + timedelta(hours=1))

    text = transcript(ROUTINE)
    artifact = await store_transcript(
        sg, context=context, store=store, text=text, captured_at=VISIT_AT
    )
    assert artifact.kind is ArtifactKind.TRANSCRIPT
    assert (await store.get(artifact.storage_key)).decode() == text
    assert "water pill" not in artifact.storage_key and artifact.region is Region.SG

    summary = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=artifact.id,
        store=store,
        summariser=FixtureSummariser(VISITS),
    )
    items = await summary_items(sg, context=context, summary_id=summary.id)
    lines = [str(line["text"]) for line in summary.lines]
    _clean(lines, "en")
    assert summary.red_flag is False and summary.is_open and summary.state_id
    assert lines[0] == "Dr Tan said this on Thursday 10 September."
    assert "Ask Dr Tan about the new amount of the water pill (furosemide)." in lines
    assert "See Dr Tan again on Thursday 15 October." in lines
    assert "Every morning, stand on the scale before breakfast." in lines
    assert "Do not eat after 12 midnight on Sunday 27 September." in lines
    assert "Dr Tan wrote down your blood pressure." in lines
    assert not any("full" in line or "half" in line for line in lines)
    kinds = {item.kind for item in items}
    assert kinds == set(SummaryItemKind)
    change = next(item for item in items if item.kind is SummaryItemKind.MEDICATION_CHANGE)
    assert change.payload == {"drug": "furosemide", "change": "dose"}
    assert text[change.span["start"] : change.span["end"]].startswith("From Friday")
    assert all(item.state is ItemState.PROPOSED and item.confidence > 0 for item in items)

    # Nothing is a memo, a visit or a fact yet.
    assert await current_memos(sg, context=context) == []
    assert len(await upcoming_appointments(sg, context=context)) == 0
    medicines_before = await current_facts(sg, context=context, subject="medicine")

    decisions = [Decision(item.id, ItemState.CONFIRMED) for item in items]
    draft = await summary_draft_for(sg, context=context, summary_id=summary.id, decisions=decisions)
    yes = await confirm(sg, context, draft)
    other = [Decision(item.id, ItemState.REJECTED) for item in items]
    async with refused_unit(sg, NotWhatWasConfirmed):
        await confirm_summary(
            sg, context=context, summary_id=summary.id, decisions=other, confirmation_id=yes.id
        )
    outcome = await confirm_summary(
        sg, context=context, summary_id=summary.id, decisions=decisions, confirmation_id=yes.id
    )

    # Follow-ups → a PLANNED visit, needing its own confirm to become CONFIRMED.
    [planned] = outcome.appointments
    assert planned.status is AppointmentStatus.PLANNED and planned.purpose == "blood pressure check"
    assert as_utc(planned.scheduled_at) == datetime(2026, 10, 15, 2, 0, tzinfo=UTC)
    assert planned.confirmed_by_person_id == context.person_id
    # Actions → memos filed against the next visit; the change → an ASK memo and a flag.
    memo_texts = {m.text for m in outcome.memos}
    assert "Every morning, stand on the scale before breakfast." in memo_texts
    assert "Ask Dr Tan about the new amount of the water pill (furosemide)." in memo_texts
    assert all(
        m.appointment_id == planned.id and m.source is MemoSource.VISIT for m in outcome.memos
    )
    [flag] = outcome.flags
    assert flag.kind is FlagKind.MEDICINE_CHANGE_HEARD and flag.subject == "furosemide"
    assert flag.artifact_id == artifact.id and flag.payload["ask_the_doctor"] is True
    # Never a change to a medicine: the medicine facts are as they were.
    medicines_after = await current_facts(sg, context=context, subject="medicine")
    assert [f.id for f in medicines_after] == [f.id for f in medicines_before]
    assert not any(f.artifact_id == artifact.id for f in medicines_after)
    # Facts heard → facts with the transcript as provenance, confirmed by him, valid from the visit.
    [heard] = outcome.facts
    assert heard.artifact_id == artifact.id and heard.subject == "blood_pressure"
    assert heard.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
    assert heard.confirmed_by_person_id == context.person_id
    assert as_utc(heard.valid_from) == VISIT_AT
    # Every item names what it became; the card is closed and takes no second yes.
    for item in outcome.items:
        assert item.state is ItemState.CONFIRMED
        assert any((item.memo_id, item.appointment_id, item.fact_id, item.flag_id))
    assert summary.confirmed_at is not None and summary.confirmed_by_person_id == context.person_id
    async with refused_unit(sg, AlreadyConfirmed):
        await summary_draft_for(sg, context=context, summary_id=summary.id, decisions=decisions)
    # The memo card, consolidated, in card order: what to do, then what to ask.
    card = await memo_card(sg, context=context)
    assert card[-1] == "Ask Dr Tan about the new amount of the water pill (furosemide)."
    assert len(card) == len(outcome.memos)
    _clean(card, "en")


async def test_a_rejected_item_writes_nothing(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    store = LocalObjectStore(tmp_path, Region.SG)
    clock.set(VISIT_AT + timedelta(hours=1))
    artifact = await store_transcript(
        sg, context=context, store=store, text=transcript(ROUTINE), captured_at=VISIT_AT
    )
    summary = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=artifact.id,
        store=store,
        summariser=FixtureSummariser(VISITS),
    )
    items = await summary_items(sg, context=context, summary_id=summary.id)
    decisions = [Decision(item.id, ItemState.REJECTED) for item in items]
    yes = await confirm(
        sg,
        context,
        await summary_draft_for(sg, context=context, summary_id=summary.id, decisions=decisions),
    )
    outcome = await confirm_summary(
        sg, context=context, summary_id=summary.id, decisions=decisions, confirmation_id=yes.id
    )
    assert (
        not outcome.memos and not outcome.appointments and not outcome.facts and not outcome.flags
    )
    assert all(item.state is ItemState.REJECTED for item in outcome.items)
    assert (await sg.scalars(select(Flag))).all() == []


async def test_a_red_flag_word_writes_a_flag_first_and_the_card_says_call_today(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    store = LocalObjectStore(tmp_path, Region.SG)
    clock.set(VISIT_AT + timedelta(hours=1))
    artifact = await store_transcript(
        sg, context=context, store=store, text=transcript(RED_FLAG), captured_at=VISIT_AT
    )

    # The flag is a row before the card is composed: at the moment the card is written,
    # the flag is already there. Nothing ranks a card that does not exist yet.
    import app.reasoning.visits.summary as summary_module

    real_render = summary_module.render_from_state
    flags_when_card_written: list[int] = []

    async def render_after_the_flag(*args: object, **kwargs: object) -> object:
        flags_when_card_written.append(len((await sg.scalars(select(Flag))).all()))
        return await real_render(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(summary_module, "render_from_state", render_after_the_flag)
    summary = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=artifact.id,
        store=store,
        summariser=FixtureSummariser(VISITS),
    )
    lines = [str(line["text"]) for line in summary.lines]
    _clean(lines, "en")
    assert summary.red_flag is True
    assert lines[0] == "Call Dr Tan today."
    assert not any(
        word in " ".join(lines).lower() for word in ("angina", "heart attack", "cardiac")
    )
    [flag] = (await sg.scalars(select(Flag))).all()
    assert flag.kind is FlagKind.RED_FLAG and flag.code == "chest_pain"
    assert flag.artifact_id == artifact.id and flag.appointment_id == appointment.id
    heard_at = transcript(RED_FLAG)[flag.payload["span"]["start"] : flag.payload["span"]["end"]]
    assert heard_at.startswith("chest pain") and flag.payload["word"] == "chest pain"
    assert flags_when_card_written == [1]
    # And the flag's write is on the trail beside the card's.
    trail = [e for e in await read_audit(sg, context=context) if e.action is Action.WRITE]
    assert {"flag", "visit_summary"} <= {e.target for e in trail}
    # And on the next visit's questions, first.
    _p, next_visit = await visit(sg, context, when=VISIT_AT + timedelta(days=30), doctor="Dr Tan")
    found = await questions_for(sg, context=context, appointment_id=next_visit.id)
    assert found[0].text == "Tell Dr Tan about the chest pain." and found[0].priority == 0


async def test_a_photo_is_not_a_transcript_and_an_unknown_transcript_hears_nothing(
    sg: AsyncSession, tmp_path: Path
) -> None:
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    store = LocalObjectStore(tmp_path, Region.SG)
    photo = await __import__("tests.visits", fromlist=["label_photo"]).label_photo(sg, context)
    async with refused_unit(sg, NotATranscript):
        await post_visit_summary(
            sg,
            context=context,
            appointment_id=appointment.id,
            artifact_id=photo.id,
            store=store,
            summariser=FixtureSummariser(VISITS),
        )
    artifact = await store_transcript(
        sg,
        context=context,
        store=store,
        text="Something nobody has a fixture for.",
        captured_at=SEPT_3,
    )
    summary = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=artifact.id,
        store=store,
        summariser=FixtureSummariser(VISITS),
    )
    assert await summary_items(sg, context=context, summary_id=summary.id) == []
    assert [str(line["text"]) for line in summary.lines] == [
        "Dr Tan said this on Thursday 10 September."
    ]
    rows = (await sg.scalars(select(VisitSummary))).all()
    assert len(rows) == 1 and (await sg.scalars(select(Artifact))).all()


def test_day_and_date_says_the_day_in_each_language() -> None:
    when = datetime(2026, 9, 14, 2, 0, tzinfo=UTC)
    assert day_and_date(when, "en", Region.SG) == "Monday 14 September"
    assert day_and_date(when, "ms", Region.MY) == "Isnin 14 September"
    assert day_and_date(when, "zh", Region.SG) == "星期一 9月14日"
    # Late at night UTC is the next morning on his clock.
    assert (
        day_and_date(datetime(2026, 9, 14, 23, 0, tzinfo=UTC), "en", Region.SG)
        == "Tuesday 15 September"
    )


def test_every_template_passes_the_verifier_in_every_language() -> None:
    from app.safety.plain_words import fill

    for key, by_language in strings.TEMPLATES.items():
        for language in strings.LANGUAGES:
            failures = [
                f for f in verify(fill(by_language[language]), language) if f.severity != "note"
            ]
            assert failures == [], (key, language, failures)


__all__ = ["uuid"]
