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
from app.medicines.models import MedicationLine
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
from app.reasoning.visits.strings import (
    NotASlotValue,
    NotPlainEnough,
    day_and_date,
    purpose_code,
    spoken,
    time_of_day,
)
from app.reasoning.visits.summary import (
    UNKNOWN_DRUG,
    AlreadyConfirmed,
    ChangeHeard,
    Decision,
    FactHeard,
    FixtureSummariser,
    MedicationChangeHeard,
    NotATranscript,
    Span,
    SummaryDraft,
    SummaryHints,
    confirm_summary,
    names_a_drug,
    post_visit_summary,
    reroute_medicine_facts,
    store_transcript,
    summary_draft_for,
    summary_items,
)
from app.regions import Region
from app.safety.plain_words import verify
from app.state.service import current_state
from tests.medicines_support import REGISTRY
from tests.support import agree_to_family_sharing, refused_unit
from tests.visits import (
    RED_FLAG,
    ROUTINE,
    SEPT_3,
    VISIT_AT,
    VISITS,
    Unknown,
    agree_to_recording,
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
    line = (await medicine(sg, context, generic="frusemide", strength="40 mg")).line
    await medicine(sg, context, generic="amlodipine", strength="5 mg")
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

    # The register knows what amlodipine is for; it has no monograph for the water pill here.
    gaps = await find_gaps(
        sg, context=context, registry=Unknown("frusemide"), appointment_id=appointment.id
    )
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
    assert no_purpose.medicine == "frusemide" and no_purpose.line_id == line.id
    assert no_purpose.fact_ids == (line.fact_id,)
    assert set(no_purpose.source_ids()) == {str(line.fact_id), str(line.id)}
    # With the real monograph the purpose is known and the gap is gone.
    with_purpose = await find_gaps(sg, context=context, registry=REGISTRY)
    assert GapKind.MEDICINE_NO_PURPOSE not in {gap.kind for gap in with_purpose}
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
    gaps = await find_gaps(sg, context=context, registry=REGISTRY)
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
    assert await find_gaps(sg, context=context, registry=REGISTRY) == []


async def test_an_interaction_the_licensed_data_flagged_is_a_gap_naming_both_lines(
    sg: AsyncSession,
) -> None:
    context = await pa(sg, language="en")
    warfarin = (
        await medicine(sg, context, generic="warfarin", strength="3 mg", dose="1 tab ON")
    ).line
    done = await medicine(sg, context, generic="aspirin", strength="100 mg")
    [flag] = done.flags
    gaps = await find_gaps(sg, context=context, registry=REGISTRY)
    [gap] = [one for one in gaps if one.kind is GapKind.INTERACTION_FLAGGED]
    assert gap.flag_id == flag.id
    assert {gap.medicine, gap.other} == {"warfarin", "aspirin"}
    assert set(gap.fact_ids) == {warfarin.fact_id, done.line.fact_id}
    _provider, appointment = await visit(sg, context)
    found = await questions_for(
        sg, context=context, appointment_id=appointment.id, registry=REGISTRY
    )
    asked = [q for q in found if q.source_kind == GapKind.INTERACTION_FLAGGED.value]
    assert [q.text for q in asked] == [
        "Ask Dr Tan if the aspirin and the blood thinner tablet (warfarin) are OK together."
    ]
    assert str(flag.id) in asked[0].source_ids


# --- the brief ------------------------------------------------------------------------------


async def test_the_brief_is_in_malay_verified_and_names_its_state(sg: AsyncSession) -> None:
    context = await pa(sg, language="ms")
    await reading(sg, context)
    await medicine(sg, context, generic="warfarin", strength="3 mg", dose="1 tab ON")
    await medicine(sg, context, generic="aspirin", strength="100 mg")
    _provider, appointment = await visit(sg, context)

    brief = await build_brief(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
    texts = [line["text"] for line in brief.lines]
    _clean(texts, "ms")
    assert brief.language == "ms"
    assert texts[0] == "Anda berjumpa Dr Tan pada Khamis 10 September pukul 10 pagi."
    # The purpose label ("blood pressure check") never reaches him; its subject does (P5).
    assert texts[1] == "Lawatan ini untuk memeriksa tekanan darah anda."
    sections = [line["section"] for line in brief.lines]
    assert sections[:2] == ["purpose", "purpose"]
    assert "changed" in sections and "questions" in sections and "bring" in sections
    changed = [line for line in brief.lines if line["section"] == "changed"]
    # The reading and the medicine lines' facts arrived since the record began.
    assert {line["key"] for line in changed} == {"changed_readings", "changed_medicines"}
    assert all(line["sources"] for line in changed)
    asked = [line for line in brief.lines if line["section"] == "questions"]
    # The interaction E04's licensed data flagged, as a question, in his words for the two.
    assert "Tanya Dr Tan sama ada aspirin dan ubat cair darah boleh dimakan bersama." in [
        line["text"] for line in asked
    ]
    assert brief.state_id == (await current_state(sg, context=context)).id
    assert brief.since_state_id is None  # no earlier visit: measured from nothing
    assert "Bawa buku tekanan darah anda pada Khamis 10 September." in texts
    assert "Bawa ubat anda dalam kotaknya pada Khamis 10 September." in texts
    assert all(line["spoken"] for line in brief.lines)

    async with refused_unit(sg, ImmutableRow):
        brief.language = "en"
        await sg.flush()
    await sg.refresh(brief)
    assert brief.language == "ms"


async def test_the_brief_is_rebuilt_only_when_state_moved(sg: AsyncSession) -> None:
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    first = await brief_for(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
    again = await brief_for(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
    assert again.id == first.id
    await reading(sg, context)
    third = await brief_for(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
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
        await build_brief(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
    assert (await sg.scalars(select(Brief))).all() == []
    refused = [e for e in await read_audit(sg, context=context) if e.outcome is Outcome.REFUSED]
    assert {(e.refused_because, e.target) for e in refused} == {("NotPlainEnough", "brief")}


async def test_a_purpose_label_never_reaches_him_as_written(sg: AsyncSession) -> None:
    """A caregiver's label is mapped to a fixed subject in his words; one that maps to nothing
    is "your health". Free text never goes into a patient slot (P5)."""
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context, purpose="hypertension follow-up")
    brief = await build_brief(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
    assert brief.lines[1]["text"] == "This visit is about your blood pressure."
    _p, other = await visit(
        sg, context, purpose="Dr Lim's second opinion", when=VISIT_AT + timedelta(days=1)
    )
    brief = await build_brief(sg, context=context, appointment_id=other.id, registry=REGISTRY)
    assert brief.lines[1]["key"] == "visit_about_health"
    assert brief.lines[1]["text"] == "This visit is about your health."
    assert purpose_code("ujian gula") == "sugar" and purpose_code("眼科复诊") == "eyes"
    assert purpose_code("") is None and purpose_code("visit") is None


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
        await brief_for(sg, context=hers, appointment_id=appointment.id, registry=REGISTRY)
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
    line = (await medicine(sg, context, generic="frusemide", strength="40 mg")).line
    _provider, appointment = await visit(sg, context)
    await __import__("app.audit.access", fromlist=["audited_write"]).audited_write(
        sg,
        Flag,
        context,
        Scope.RECORDS,
        kind=FlagKind.MEDICINE_CHANGE_HEARD,
        code=ChangeHeard.DOSE.value,
        subject="frusemide",
        fact_ids=[str(line.fact_id)],
        payload={"generic": "frusemide", "change": "dose", "line_id": str(line.id)},
        raised_at=SEPT_3,
    )
    found = await questions_for(
        sg, context=context, appointment_id=appointment.id, registry=Unknown("frusemide")
    )
    by_text = {q.text: q for q in found}
    _clean(list(by_text), "en")
    dose = by_text["Ask Dr Tan about the new amount of the water pill (frusemide)."]
    assert dose.source is QuestionSource.FLAG and dose.priority == 1
    purpose = by_text["Ask Dr Tan what the water pill (frusemide) is for."]
    assert purpose.source is QuestionSource.GAP
    assert purpose.source_kind == GapKind.MEDICINE_NO_PURPOSE.value
    assert set(purpose.source_ids) == {str(line.fact_id), str(line.id)}
    assert found[0] is dose  # the medicine change first
    for text in by_text:
        assert not any(word in text.lower() for word in ("take ", "stop ", "start ", "half"))
    assert all(q.state_id for q in found)

    # Asking again with nothing moved writes nothing new.
    again = await questions_for(
        sg, context=context, appointment_id=appointment.id, registry=Unknown("frusemide")
    )
    assert [q.id for q in again] == [q.id for q in found]


async def test_a_person_adds_edits_and_removes_a_question_with_a_yes(sg: AsyncSession) -> None:
    context = await pa(sg, language="en")
    await medicine(sg, context)
    _provider, appointment = await visit(sg, context)
    registry = Unknown("frusemide")
    before = await questions_for(
        sg, context=context, appointment_id=appointment.id, registry=registry
    )
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
    current = await questions_for(
        sg, context=context, appointment_id=appointment.id, registry=registry
    )
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
    current = await questions_for(
        sg, context=context, appointment_id=appointment.id, registry=registry
    )
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
    await medicine(sg, context, generic="frusemide", strength="40 mg")
    await medicine(sg, context, generic="amlodipine", strength="5 mg")
    _provider, appointment = await visit(sg, context, purpose="visit")
    found = await questions_for(
        sg,
        context=context,
        appointment_id=appointment.id,
        registry=Unknown("frusemide", "amlodipine"),
    )
    assert len(found) >= 3
    card = await patient_card(sg, context=context, appointment_id=appointment.id)
    assert card[:CARD_SIZE] == [q.text for q in found[:CARD_SIZE]]
    assert card[-1] == "Nura simpan soalan-soalan ini untuk anda."
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
        slots={"doctor": "Dr Tan", "medicine": "the water pill (frusemide)"},
        source=MemoSource.CONVERSATION,
        appointment_id=appointment.id,
    )
    assert first.text == "Every evening, eat a lighter dinner." and first.state_id
    assert len(first.text) <= 80
    kept = await consolidate_memos(sg, context=context)
    assert [m.id for m in kept] == [second.id, asked.id]
    assert first.superseded_at is not None and second.superseded_at is None
    card = await memo_card(sg, context=context)
    assert card == [
        "Every evening, eat a lighter dinner.",
        "Ask Dr Tan about the new amount of the water pill (frusemide).",
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


def test_a_fact_heard_about_a_dose_is_rerouted_whatever_its_subject() -> None:
    """B4: the reroute keys on the attribute, not the subject, and on any drug name."""
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
            # A free subject code with a dose attribute: still a dose.
            FactHeard("warfarin", "dose", {"amount": "5 mg"}, "mg", Span(11, 15), 0.9),
            # An underscore hides nothing: "warfarin_level" names warfarin (review 2, #4).
            FactHeard("warfarin_level", "reading", 5, "mg", Span(15, 16), 0.9),
            # A fact whose value names a drug the register knows: never a fact.
            FactHeard("symptom", "reported", "dizzy since the amlodipine", None, Span(16, 20), 0.8),
            # A fact whose subject names a high-risk drug: never a fact.
            FactHeard("insulin", "note", "keeps it in the fridge", None, Span(21, 25), 0.8),
            FactHeard(
                "blood_pressure",
                "reading",
                {"systolic": 142, "diastolic": 88},
                "mmHg",
                Span(26, 30),
                0.8,
            ),
        )
    )
    rerouted = reroute_medicine_facts(draft, REGISTRY)
    assert [(c.drug, c.change) for c in rerouted.medication_changes] == [
        ("warfarin", ChangeHeard.DOSE),
        ("aspirin", ChangeHeard.STOP),
        ("warfarin", ChangeHeard.DOSE),
        ("warfarin_level", ChangeHeard.UNCLEAR),
        ("dizzy since the amlodipine", ChangeHeard.UNCLEAR),
        ("keeps it in the fridge", ChangeHeard.UNCLEAR),
    ]
    assert [f.subject for f in rerouted.facts_heard] == ["blood_pressure"]
    assert names_a_drug(REGISTRY, "symptom", {"note": "took Lasix"}) is True
    assert names_a_drug(REGISTRY, "amlodipine-level", 5) is True
    assert names_a_drug(REGISTRY, "sleep", "fine") is False
    assert names_a_drug(REGISTRY, "blood_pressure", {"systolic": 142}) is False


async def test_transcript_in_summary_card_out_memos_on_the_yes(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    context = await pa(sg, language="en")
    await reading(sg, context)
    water_pill = (await medicine(sg, context, generic="frusemide", strength="40 mg")).line
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
        registry=REGISTRY,
    )
    items = await summary_items(sg, context=context, summary_id=summary.id)
    lines = [str(line["text"]) for line in summary.lines]
    _clean(lines, "en")
    assert summary.red_flag is False and summary.is_open and summary.state_id
    assert lines[0] == "Dr Tan said this on Thursday 10 September."
    assert "Ask Dr Tan about the new amount of the water pill (frusemide)." in lines
    assert "You see Dr Tan again on Thursday 15 October at 10 in the morning." in lines
    assert "You will book it." in lines  # rule 7: no chief on this profile, so he does
    assert "Every morning, stand on the scale before breakfast." in lines
    assert "Eat nothing after 12 midnight on Sunday 27 September." in lines
    assert "Bring your blood pressure book on Thursday 15 October." in lines
    # The spoken twin drops the bracketed chemical name (P7).
    assert "Ask Dr Tan about the new amount of the water pill." in [
        str(line["spoken"]) for line in summary.lines
    ]
    assert "Dr Tan wrote down your blood pressure." in lines
    assert not any("full" in line or "half a" in line for line in lines)
    kinds = {item.kind for item in items}
    assert kinds == set(SummaryItemKind)
    change = next(item for item in items if item.kind is SummaryItemKind.MEDICATION_CHANGE)
    assert change.payload == {"generic": "frusemide", "change": "dose"}
    assert text[change.span["start"] : change.span["end"]].startswith("From Friday")
    assert all(item.state is ItemState.PROPOSED and item.confidence > 0 for item in items)

    # Nothing is a memo, a visit or a fact yet.
    assert await current_memos(sg, context=context) == []
    assert len(await upcoming_appointments(sg, context=context)) == 0
    lines_before = [
        (l.id, l.superseded_at) for l in (await sg.scalars(select(MedicationLine))).all()
    ]

    decisions = [Decision(item.id, ItemState.CONFIRMED) for item in items]
    draft = await summary_draft_for(sg, context=context, summary_id=summary.id, decisions=decisions)
    yes = await confirm(sg, context, draft)
    other = [Decision(item.id, ItemState.REJECTED) for item in items]
    async with refused_unit(sg, NotWhatWasConfirmed):
        await confirm_summary(
            sg,
            context=context,
            summary_id=summary.id,
            decisions=other,
            confirmation_id=yes.id,
            registry=REGISTRY,
        )
    outcome = await confirm_summary(
        sg,
        context=context,
        summary_id=summary.id,
        decisions=decisions,
        confirmation_id=yes.id,
        registry=REGISTRY,
    )

    # Follow-ups → a PLANNED visit, needing its own confirm to become CONFIRMED.
    [planned] = outcome.appointments
    assert planned.status is AppointmentStatus.PLANNED and planned.purpose == "blood pressure check"
    assert as_utc(planned.scheduled_at) == datetime(2026, 10, 15, 2, 0, tzinfo=UTC)
    assert planned.confirmed_by_person_id == context.person_id
    # Actions → memos filed against the next visit; the change → an ASK memo and a flag.
    memo_texts = {m.text for m in outcome.memos}
    assert "Every morning, stand on the scale before breakfast." in memo_texts
    assert "Ask Dr Tan about the new amount of the water pill (frusemide)." in memo_texts
    assert all(
        m.appointment_id == planned.id and m.source is MemoSource.VISIT for m in outcome.memos
    )
    [flag] = outcome.flags
    assert flag.kind is FlagKind.MEDICINE_CHANGE_HEARD and flag.subject == "frusemide"
    assert flag.artifact_id == artifact.id and flag.payload["ask_the_doctor"] is True
    # What E04's reconcile picks up: the generic, the kind of change, the line — no amount.
    assert flag.payload["generic"] == "frusemide" and flag.payload["change"] == "dose"
    assert flag.payload["line_id"] == str(water_pill.id) and flag.fact_ids == [
        str(water_pill.fact_id)
    ]
    assert "amount" not in flag.payload and "dose_text" not in flag.payload
    # Never a change to a medicine: the lines are as they were, none superseded, none new.
    lines_after = [
        (l.id, l.superseded_at) for l in (await sg.scalars(select(MedicationLine))).all()
    ]
    assert lines_after == lines_before == [(water_pill.id, None)]
    assert not any(
        f.artifact_id == artifact.id
        for f in await current_facts(sg, context=context, subject="medication")
    )
    # Facts heard → facts with the transcript as provenance, confirmed by him, valid from the visit.
    [heard] = outcome.facts
    assert heard.artifact_id == artifact.id and heard.subject == "blood_pressure"
    assert heard.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
    assert heard.confirmed_by_person_id == context.person_id
    assert as_utc(heard.valid_from) == VISIT_AT
    # Every item names what it became; the card is closed and takes no second yes.
    for item in outcome.items:
        assert item.state is ItemState.CONFIRMED
        if item.kind is not SummaryItemKind.FOLLOW_UP_WHO:  # the who-books line writes nothing
            assert any((item.memo_id, item.appointment_id, item.fact_id, item.flag_id))
    assert summary.confirmed_at is not None and summary.confirmed_by_person_id == context.person_id
    async with refused_unit(sg, AlreadyConfirmed):
        await summary_draft_for(sg, context=context, summary_id=summary.id, decisions=decisions)
    # The memo card, consolidated, in card order: what to do, then what to ask.
    card = await memo_card(sg, context=context)
    assert card[-1] == "Ask Dr Tan about the new amount of the water pill (frusemide)."
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
        registry=REGISTRY,
    )
    items = await summary_items(sg, context=context, summary_id=summary.id)
    decisions = [Decision(item.id, ItemState.REJECTED) for item in items]
    yes = await confirm(
        sg,
        context,
        await summary_draft_for(sg, context=context, summary_id=summary.id, decisions=decisions),
    )
    outcome = await confirm_summary(
        sg,
        context=context,
        summary_id=summary.id,
        decisions=decisions,
        confirmation_id=yes.id,
        registry=REGISTRY,
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
        registry=REGISTRY,
    )
    lines = [str(line["text"]) for line in summary.lines]
    _clean(lines, "en")
    assert summary.red_flag is True
    assert lines[0] == "Call Dr Tan today."
    # P1/F2: the card says what happened, on the line after the call — one doer, one act.
    assert lines[1] == "Tell Dr Tan about the chest pain today."
    assert "Dr Tan said your medicines stay the same." in lines
    assert not any(
        word in " ".join(lines).lower() for word in ("angina", "heart attack", "cardiac")
    )
    [flag] = (await sg.scalars(select(Flag))).all()
    assert flag.kind is FlagKind.RED_FLAG and flag.code == "chest_pain"
    assert flag.artifact_id == artifact.id and flag.appointment_id == appointment.id
    # The narrowest span: the word itself, in the raw transcript (B2, note).
    heard_at = transcript(RED_FLAG)[flag.payload["span"]["start"] : flag.payload["span"]["end"]]
    assert heard_at == "chest pain" and flag.payload["found_in"] == "transcript"
    assert flags_when_card_written == [1]
    # And the flag's write is on the trail beside the card's.
    trail = [e for e in await read_audit(sg, context=context) if e.action is Action.WRITE]
    assert {"flag", "visit_summary"} <= {e.target for e in trail}
    # And on the next visit's questions, first.
    _p, next_visit = await visit(sg, context, when=VISIT_AT + timedelta(days=30), doctor="Dr Tan")
    found = await questions_for(
        sg, context=context, appointment_id=next_visit.id, registry=REGISTRY
    )
    assert found[0].text == "Tell Dr Tan about the chest pain today." and found[0].priority == 0


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
            registry=REGISTRY,
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
        registry=REGISTRY,
    )
    assert await summary_items(sg, context=context, summary_id=summary.id) == []
    assert [str(line["text"]) for line in summary.lines] == [
        "Dr Tan said this on Thursday 10 September."
    ]
    rows = (await sg.scalars(select(VisitSummary))).all()
    assert len(rows) == 1 and (await sg.scalars(select(Artifact))).all()


def test_his_name_for_a_medicine_comes_from_the_licensed_monograph_first() -> None:
    from app.reasoning.visits.strings import medicine_words

    assert medicine_words("frusemide", "en", REGISTRY) == "the water pill (frusemide)"
    assert medicine_words("frusemide", "ms", REGISTRY) == "pil air"
    assert medicine_words("aspirin", "en", REGISTRY) == "the aspirin"
    assert medicine_words("warfarin", "zh", REGISTRY) == "薄血药"
    # Unknown to the register: the docs' glossary, then the name as it is.
    assert medicine_words("furosemide", "en", REGISTRY) == "the water pill (furosemide)"
    with pytest.raises(NotASlotValue):
        medicine_words("Xylocaine", "en", REGISTRY)  # B1: never printed as it is


def test_day_and_date_says_the_day_in_each_language() -> None:
    when = datetime(2026, 9, 14, 2, 0, tzinfo=UTC)
    assert day_and_date(when, "en", Region.SG) == "Monday 14 September"
    assert day_and_date(when, "ms", Region.MY) == "Isnin 14 September"
    assert day_and_date(when, "zh", Region.SG) == "9月14日星期一"
    assert time_of_day(when, "en", Region.SG) == "10 in the morning"
    assert time_of_day(when, "ms", Region.MY) == "10 pagi"
    assert time_of_day(when, "zh", Region.SG) == "上午10点"
    late = datetime(2026, 9, 14, 11, 30, tzinfo=UTC)
    assert time_of_day(late, "en", Region.SG) == "half past 7 in the evening"
    assert time_of_day(datetime(2026, 9, 14, 4, 0, tzinfo=UTC), "en", Region.SG) == "12 noon"
    assert time_of_day(late, "ms", Region.MY) == "7.30 malam"
    assert time_of_day(late, "zh", Region.SG) == "晚上7点半"
    # Late at night UTC is the next morning on his clock.
    assert (
        day_and_date(datetime(2026, 9, 14, 23, 0, tzinfo=UTC), "en", Region.SG)
        == "Tuesday 15 September"
    )


def test_every_template_passes_the_verifier_in_every_language_with_its_kind() -> None:
    """Action-shaped lines are checked as actions (rules 6 and 7), the rest as lines (P-A)."""
    from app.safety.plain_words import fill

    assert strings.kind_of("bring_bp_book") == "action" and strings.kind_of("visit_with") == "line"
    for key, by_language in strings.TEMPLATES.items():
        for language in strings.LANGUAGES:
            failures = [
                f
                for f in verify(
                    fill(by_language[language], language), language, strings.kind_of(key)
                )
                if f.severity != "note"
            ]
            assert failures == [], (key, language, failures)


def test_a_slot_takes_only_the_kind_of_thing_it_is_for() -> None:
    """Nothing free reaches a line: names are names, numbers are numbers (safety note)."""
    assert strings.render("walk_every_day", "en", minutes=20) == "Every day, walk for 20 minutes."
    with pytest.raises(NotASlotValue):
        strings.render("walk_every_day", "en", minutes="20; take two tablets")
    with pytest.raises(NotASlotValue):
        strings.render(
            "visit_with",
            "en",
            doctor="Dr Tan 91234567",
            day="Monday 14 September",
            time="10 in the morning",
        )
    with pytest.raises(NotASlotValue):
        strings.render("call_doctor_today", "en", doctor="Call 999 now. Dr Tan")
    with pytest.raises(NotASlotValue):
        strings.render("ask_medicine_purpose", "en", doctor="Dr Tan", medicine="")
    with pytest.raises(NotASlotValue):
        strings.render("call_doctor_today", "en", clinic="Dr Tan")
    assert spoken("Ask Dr Tan about the new amount of the water pill (frusemide).") == (
        "Ask Dr Tan about the new amount of the water pill."
    )


class _Says:
    """A summariser that answers whatever a test hands it, for any transcript."""

    def __init__(self, draft: SummaryDraft) -> None:
        self.draft = draft

    async def summarise(
        self, transcript_text: str, language: str, hints: SummaryHints
    ) -> SummaryDraft:
        return self.draft


async def test_a_drug_the_register_does_not_know_is_never_printed_or_written(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """B1: an unregistered drug name reaches neither his screen nor the reconcile."""
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    store = LocalObjectStore(tmp_path, Region.SG)
    clock.set(VISIT_AT + timedelta(hours=1))
    artifact = await store_transcript(
        sg, context=context, store=store, text="We will change the Xyzzymab.", captured_at=VISIT_AT
    )
    heard = SummaryDraft(
        medication_changes=(MedicationChangeHeard("Xyzzymab", ChangeHeard.DOSE, Span(19, 27), 0.9),)
    )
    summary = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=artifact.id,
        store=store,
        summariser=_Says(heard),
        registry=REGISTRY,
    )
    lines = [str(line["text"]) for line in summary.lines]
    assert "Ask Dr Tan about the change to your medicines." in lines
    assert not any("xyzzymab" in line.lower() for line in lines)
    [item] = await summary_items(sg, context=context, summary_id=summary.id)
    assert item.payload == {"generic": None, "change": "dose"}
    assert item.key == "ask_medicines_change"
    decisions = [Decision(item.id, ItemState.CONFIRMED)]
    yes = await confirm(
        sg,
        context,
        await summary_draft_for(sg, context=context, summary_id=summary.id, decisions=decisions),
    )
    outcome = await confirm_summary(
        sg,
        context=context,
        summary_id=summary.id,
        decisions=decisions,
        confirmation_id=yes.id,
        registry=REGISTRY,
    )
    [flag] = outcome.flags
    assert flag.subject == UNKNOWN_DRUG and flag.code == "dose"
    assert set(flag.payload) == {"span", "change"} and flag.fact_ids == []
    assert [m.text for m in outcome.memos] == ["Ask Dr Tan about the change to your medicines."]
    # A brand the register knows is named as its generic, in his words.
    heard = SummaryDraft(
        medication_changes=(MedicationChangeHeard("Lasix", ChangeHeard.DOSE, Span(0, 5), 0.9),)
    )
    other = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=artifact.id,
        store=store,
        summariser=_Says(heard),
        registry=REGISTRY,
    )
    assert "Ask Dr Tan about the new amount of the water pill (frusemide)." in [
        str(line["text"]) for line in other.lines
    ]


async def test_a_red_flag_word_in_the_transcript_is_found_when_the_summariser_omits_it(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """B2: the raw transcript is scanned, so a model that mislabels or drops the chest pain
    still escalates; and a word inside a fact's subject is found too."""
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    store = LocalObjectStore(tmp_path, Region.SG)
    clock.set(VISIT_AT + timedelta(hours=1))
    artifact = await store_transcript(
        sg, context=context, store=store, text=transcript(RED_FLAG), captured_at=VISIT_AT
    )
    summary = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=artifact.id,
        store=store,
        summariser=_Says(SummaryDraft.nothing()),
        registry=REGISTRY,
    )
    assert summary.red_flag is True
    assert [str(line["text"]) for line in summary.lines][:2] == [
        "Call Dr Tan today.",
        "Tell Dr Tan about the chest pain today.",
    ]
    [flag] = (await sg.scalars(select(Flag))).all()
    assert flag.payload["found_in"] == "transcript"
    span = flag.payload["span"]
    assert transcript(RED_FLAG)[span["start"] : span["end"]] == "chest pain"

    # A word the summariser put in a subject code, on a transcript that has none itself.
    plain = await store_transcript(
        sg,
        context=context,
        store=store,
        text="A quiet visit with nothing new.",
        captured_at=VISIT_AT,
    )
    heard = SummaryDraft(
        facts_heard=(FactHeard("black_stool", "reported", "twice", None, Span(0, 5), 0.8),)
    )
    second = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=plain.id,
        store=store,
        summariser=_Says(heard),
        registry=REGISTRY,
    )
    assert second.red_flag is True
    codes = {f.code: f.payload["found_in"] for f in (await sg.scalars(select(Flag))).all()}
    assert codes["black_stool"] == "fact"


async def test_no_transcript_is_kept_without_the_agreement_to_recording(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """B3: `store_transcript` requires RECORDING under the visits scope; the refusal is on
    the trail by name, and nothing is stored."""
    from app.consent.service import ConsentWithheld

    context = await pa(sg, language="en", recording=False)
    store = LocalObjectStore(tmp_path, Region.SG)
    async with refused_unit(sg, ConsentWithheld):
        await store_transcript(
            sg, context=context, store=store, text=transcript(ROUTINE), captured_at=SEPT_3
        )
    assert (await sg.scalars(select(Artifact))).all() == []
    refused = [e for e in await read_audit(sg, context=context) if e.outcome is Outcome.REFUSED]
    assert ("ConsentWithheld", Scope.VISITS) in {(e.refused_because, e.scope) for e in refused}
    await agree_to_recording(sg, context, language="en")
    kept = await store_transcript(
        sg, context=context, store=store, text=transcript(ROUTINE), captured_at=SEPT_3
    )
    assert kept.kind is ArtifactKind.TRANSCRIPT


async def test_a_follow_up_with_a_new_doctors_name_never_adds_a_provider(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """Safety note: nobody is added to his directory from a transcript; the visit is booked
    with the doctor he saw, and the name heard is kept on the item for the record."""
    from datetime import date

    from app.memory.spine import list_providers
    from app.reasoning.visits.summary import FollowUpHeard

    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    store = LocalObjectStore(tmp_path, Region.SG)
    clock.set(VISIT_AT + timedelta(hours=1))
    artifact = await store_transcript(
        sg, context=context, store=store, text="See Dr Nobody next month.", captured_at=VISIT_AT
    )
    heard = SummaryDraft(
        follow_ups=(
            FollowUpHeard(date(2026, 10, 15), "heart check", Span(0, 5), 0.9, provider="Dr Nobody"),
        )
    )
    summary = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=artifact.id,
        store=store,
        summariser=_Says(heard),
        registry=REGISTRY,
    )
    item, who = await summary_items(sg, context=context, summary_id=summary.id)
    assert item.payload["provider_heard"] == "Dr Nobody"
    assert who.kind is SummaryItemKind.FOLLOW_UP_WHO and who.text == "You will book it."
    decisions = [Decision(one.id, ItemState.CONFIRMED) for one in (item, who)]
    yes = await confirm(
        sg,
        context,
        await summary_draft_for(sg, context=context, summary_id=summary.id, decisions=decisions),
    )
    outcome = await confirm_summary(
        sg,
        context=context,
        summary_id=summary.id,
        decisions=decisions,
        confirmation_id=yes.id,
        registry=REGISTRY,
    )
    [planned] = outcome.appointments
    assert planned.provider_id == appointment.provider_id
    assert [p.name for p in await list_providers(sg, context=context)] == ["Dr Tan"]


async def test_an_action_carries_only_the_slots_its_kind_allows(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """Safety note: summariser slot values are constrained per template."""
    from app.reasoning.visits.summary import ActionHeard, ActionKind

    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    store = LocalObjectStore(tmp_path, Region.SG)
    clock.set(VISIT_AT + timedelta(hours=1))
    artifact = await store_transcript(
        sg, context=context, store=store, text="Walk a little every day.", captured_at=VISIT_AT
    )
    heard = SummaryDraft(
        actions=(
            ActionHeard(
                ActionKind.WALK_EVERY_DAY, {"minutes": 20, "doctor": "Dr Evil"}, Span(0, 5), 0.9
            ),
        )
    )
    summary = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=artifact.id,
        store=store,
        summariser=_Says(heard),
        registry=REGISTRY,
    )
    [item] = await summary_items(sg, context=context, summary_id=summary.id)
    assert item.text == "Every day, walk for 20 minutes."
    assert item.payload["slots"] == {"minutes": 20}
    too_long = SummaryDraft(
        actions=(ActionHeard(ActionKind.WALK_EVERY_DAY, {"minutes": 9000}, Span(0, 5), 0.9),)
    )
    async with refused_unit(sg, NotASlotValue):
        await post_visit_summary(
            sg,
            context=context,
            appointment_id=appointment.id,
            artifact_id=artifact.id,
            store=store,
            summariser=_Says(too_long),
            registry=REGISTRY,
        )


async def test_a_red_flag_outlives_a_refusal_later_in_the_same_request(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """Review 2, #5: the request is one savepoint. A red-flag word plus one item the loop
    will not render is a refusal — and the Flag row is still there afterwards, replayed
    like a refused audit line (`app.db.keep_on_refusal`)."""
    from app.reasoning.visits.summary import ActionHeard, ActionKind

    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    store = LocalObjectStore(tmp_path, Region.SG)
    clock.set(VISIT_AT + timedelta(hours=1))
    artifact = await store_transcript(
        sg, context=context, store=store, text=transcript(RED_FLAG), captured_at=VISIT_AT
    )
    unrenderable = SummaryDraft(
        actions=(ActionHeard(ActionKind.WALK_EVERY_DAY, {"minutes": 9000}, Span(0, 5), 0.9),)
    )
    async with refused_unit(sg, NotASlotValue):
        await post_visit_summary(
            sg,
            context=context,
            appointment_id=appointment.id,
            artifact_id=artifact.id,
            store=store,
            summariser=_Says(unrenderable),
            registry=REGISTRY,
        )
    assert (await sg.scalars(select(VisitSummary))).all() == []  # the card was rolled back
    [flag] = (await sg.scalars(select(Flag))).all()  # the flag was not
    assert flag.kind is FlagKind.RED_FLAG and flag.code == "chest_pain"
    assert flag.artifact_id == artifact.id and flag.appointment_id == appointment.id
    trail = await read_audit(sg, context=context)
    assert any(e.target == "flag" and e.action is Action.WRITE for e in trail)
    assert {e.refused_because for e in trail if e.outcome is Outcome.REFUSED} >= {"NotASlotValue"}


async def test_a_key_that_reads_the_visits_does_not_write_them(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """Review 2: a viewer's or a clinic's key holds the visits scope to read; a transcript,
    a summary, a question are writes, refused by name and on the trail (same footing as
    the medicines, `medicines.service.CHANGERS`)."""
    from app.reasoning.visits.guard import NotTheirsToChangeVisits

    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    clinic = await __import__("app.identity.service", fromlist=["register_person"]).register_person(
        sg, region=Region.SG, display_name="Clinic", phone_e164="+6592220009"
    )
    await agree_to_family_sharing(sg, context, clinic, scopes={Scope.VISITS, Scope.RECORDS})
    await grant_key(
        sg,
        context=context,
        holder=clinic,
        role=KeyRole.CLINIC,
        scopes={Scope.VISITS, Scope.RECORDS},
    )
    theirs = await resolve_key_context(
        sg, region=Region.SG, person_id=clinic.id, profile_id=context.profile_id
    )
    store = LocalObjectStore(tmp_path, Region.SG)
    async with refused_unit(sg, NotTheirsToChangeVisits):
        await store_transcript(
            sg, context=theirs, store=store, text=transcript(ROUTINE), captured_at=SEPT_3
        )
    async with refused_unit(sg, NotTheirsToChangeVisits):
        await change_questions(
            sg,
            context=theirs,
            appointment_id=appointment.id,
            confirmation_id=uuid.uuid4(),
            text="Is the water pill bad for my kidneys?",
        )
    async with refused_unit(sg, NotTheirsToChangeVisits):
        await questions_for(sg, context=theirs, appointment_id=appointment.id, registry=REGISTRY)
    # Reading is theirs.
    from app.reasoning.visits.questions import current_questions

    assert await current_questions(sg, context=theirs, appointment_id=appointment.id) == []
    refused = [
        e
        for e in await read_audit(sg, context=context)
        if e.outcome is Outcome.REFUSED and e.actor_person_id == clinic.id
    ]
    assert {e.refused_because for e in refused} == {"NotTheirsToChangeVisits"}


async def test_a_code_with_no_words_of_his_becomes_a_whole_line_never_the_code(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """Review 2, F7: a subject the tables do not know is never spoken as its code."""
    context = await pa(sg, language="en")
    _provider, appointment = await visit(sg, context)
    store = LocalObjectStore(tmp_path, Region.SG)
    clock.set(VISIT_AT + timedelta(hours=1))
    artifact = await store_transcript(
        sg, context=context, store=store, text="He sleeps badly.", captured_at=VISIT_AT
    )
    heard = SummaryDraft(
        facts_heard=(FactHeard("sleep", "quality", "poor", None, Span(0, 5), 0.8),)
    )
    summary = await post_visit_summary(
        sg,
        context=context,
        appointment_id=appointment.id,
        artifact_id=artifact.id,
        store=store,
        summariser=_Says(heard),
        registry=REGISTRY,
    )
    [item] = await summary_items(sg, context=context, summary_id=summary.id)
    assert (
        item.text == "Tell Dr Tan about how you feel today."
        and item.key == "tell_doctor_how_you_feel"
    )
    assert "sleep" not in " ".join(str(line["text"]) for line in summary.lines)
    # And a gap about an unknown subject asks what the visit is for, never "about egfr".
    photo = await __import__("tests.visits", fromlist=["label_photo"]).label_photo(sg, context)
    await assert_fact(
        sg,
        context=context,
        subject="egfr",
        attribute="value",
        value=61,
        confidence=0.9,
        artifact_id=photo.id,
        valid_from=SEPT_3 - timedelta(days=400),
        valid_to=SEPT_3 - timedelta(days=30),
    )
    found = await questions_for(
        sg, context=context, appointment_id=appointment.id, registry=REGISTRY
    )
    texts = [q.text for q in found if q.source_kind == GapKind.FACT_EXPIRED.value]
    assert texts == ["Ask Dr Tan what this visit is for."]
    with pytest.raises(NotASlotValue):
        strings.subject_words("egfr", "en")


def test_no_template_in_any_language_starts_stops_or_changes_a_medicine() -> None:
    """Review 2, check 3: the boundary as the verifier now reads it (rule 14), in en, ms and
    zh alike — a treatment verb beside a medicine noun fails unless the line asks."""
    from app.safety.plain_words import fill

    for key, by_language in strings.TEMPLATES.items():
        for language in strings.LANGUAGES:
            text = fill(by_language[language], language)
            assert [f for f in verify(text, language) if f.rule == 14] == [], (key, language, text)
    for text, language in (
        ("Stop the water pill from Friday.", "en"),
        ("From Friday, take more of the water pill.", "en"),
        ("Berhenti makan pil air mulai Jumaat.", "ms"),
        ("Anda perlu mula makan ubat baru.", "ms"),
        ("从星期五开始停吃去水药。", "zh"),
        ("这个药要多吃一片。", "zh"),
    ):
        assert [f.rule for f in verify(text, language)] == [14] or 14 in [
            f.rule for f in verify(text, language)
        ], text


__all__ = ["uuid"]
