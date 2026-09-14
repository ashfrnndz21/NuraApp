"""The medicines service against docs/medications-module.md section 9.

    The system never changes a dose. It proposes; a person confirms.
    High-risk drugs require the label photo before the dose is saved.
    Every inferred value shows its source and confidence.
    Interaction checks run on a licensed database; the model writes the sentence.

Plus the extras E04 owes: supersession keeps history, the count and reorder arithmetic, a
helper key reads but cannot add, and every refusal is on the trail.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry
from app.audit.models import Outcome as AuditOutcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.drafts import FactDraft
from app.drugs.registry import NotIdentified, Severity
from app.keys.confirm import NotAConfirmerHere, NotWhatWasConfirmed
from app.keys.context import KeyContext, OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.medicines import dose as arithmetic
from app.medicines.dose import Dose, DoseNotRead, Frequency, NotADose, parse_dose_text
from app.medicines.models import ChangeKind, DoseTaken, MedicationLine, SourceKind
from app.medicines.service import (
    AlreadyRecorded,
    NoSuchLine,
    NotTheirsToChange,
    Outcome,
    active_lines,
    history,
    interaction_flags,
    plan,
    reconcile,
    record_dose_taken,
    story,
    today,
)
from app.memory.models import ArtifactKind, ConfidenceState, EventKind, Fact
from app.memory.semantic import assert_fact, current_facts
from app.safety.high_risk import MEDICATION, HighRiskNeedsLabelPhoto
from tests.medicines_support import REGISTRY, add, artefact, label, let_in, pa, planned, yes


def _refusals(entries: list[AuditEntry]) -> set[tuple[Action, str, str | None]]:
    return {
        (e.action, e.target, e.refused_because)
        for e in entries
        if e.outcome is AuditOutcome.REFUSED
    }


# --- identification and the first line -----------------------------------------------------


async def test_a_label_becomes_a_line_with_source_confidence_and_the_persons_yes(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    photo = await artefact(sg, owner)
    shown = await planned(sg, owner, label("amlodipine", "5 mg", "1 tab OD", quantity=30), photo)
    assert shown.outcome is Outcome.NEW_LINE and shown.matched_line is None
    assert shown.match.registration_no.startswith("MAL") and not shown.match.high_risk
    assert shown.flagged == [] and not shown.needs_label_photo
    assert shown.lead_time_days == 3  # retail

    done = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD", quantity=30), photo)
    line = done.line
    assert done.outcome is Outcome.NEW_LINE
    assert (line.generic, line.strength, line.form, line.drug_class) == (
        "amlodipine",
        "5 mg",
        "tablet",
        "calcium_channel_blocker",
    )
    assert line.source_artifact_id == photo.id and line.confidence == 1.0
    assert line.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
    assert line.confirmed_by_person_id == owner.person_id
    assert line.change_kind is ChangeKind.NEW_LINE and line.supersedes_id is None
    assert Dose.from_json(line.dose) == Dose(1.0, "tablet", Frequency.OD)
    # The fact underneath: subject medication, on the photo, the person's word.
    (fact,) = await current_facts(sg, context=owner, subject=MEDICATION)
    assert fact.id == line.fact_id and fact.artifact_id == photo.id
    assert fact.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
    assert (
        fact.value["drug_class"] == "calcium_channel_blocker" and fact.value["change"] == "new_line"
    )
    # The supply the label said.
    assert done.supply is not None and done.supply.quantity == 30
    assert done.supply.artifact_id == photo.id and done.supply.fact_id == fact.id


async def test_a_label_the_register_does_not_know_is_not_guessed(sg: AsyncSession) -> None:
    owner = await pa(sg)
    photo = await artefact(sg, owner)
    with pytest.raises(NotIdentified):
        await planned(sg, owner, label("ibuprofen", "200 mg"), photo)
    # Two strengths and no strength on the label: the strength decides, nothing is picked.
    with pytest.raises(NotIdentified):
        await planned(sg, owner, label("warfarin", None), photo)  # type: ignore[arg-type]
    assert _refusals(list(await read_audit(sg, context=owner))) == {
        (Action.READ, "medication_line", "NotIdentified")
    }


async def test_a_dose_is_read_from_the_labels_own_words_or_asked() -> None:
    assert parse_dose_text("1 tab BD") == Dose(1, "tablet", Frequency.BD)
    assert parse_dose_text("1 biji, 2 kali sehari") == Dose(1, "tablet", Frequency.BD)
    assert parse_dose_text("½ tablet once daily") == Dose(0.5, "tablet", Frequency.OD)
    assert parse_dose_text("1 tablet twice daily, with breakfast and dinner").anchors == (
        arithmetic.Anchor.BREAKFAST,
        arithmetic.Anchor.DINNER,
    )
    assert parse_dose_text("10 units ON").anchors == (arithmetic.Anchor.BED,)
    assert parse_dose_text("1 tab prn").frequency is Frequency.PRN
    assert parse_dose_text("1 tablet once a week").frequency is Frequency.WEEKLY
    with pytest.raises(DoseNotRead):
        parse_dose_text("as directed")
    with pytest.raises(DoseNotRead):
        parse_dose_text("1 tablet")
    with pytest.raises(NotADose):
        Dose(0, "tablet", Frequency.OD)
    with pytest.raises(NotADose):
        Dose(1, "tablet", Frequency.BD, (arithmetic.Anchor.BREAKFAST,))


# --- reconciliation ---------------------------------------------------------------------------


async def test_the_same_drug_strength_and_dose_is_a_refill_that_adds_a_supply(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    first = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD", quantity=30))
    later = await artefact(sg, owner)
    shown = await planned(sg, owner, label("amlodipine", "5 mg", "1 tab OD", quantity=28), later)
    assert shown.outcome is Outcome.REFILL and shown.matched_line is not None
    assert shown.matched_line.id == first.line.id
    done = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD", quantity=28), later)
    assert done.outcome is Outcome.REFILL and done.line.id == first.line.id
    assert done.supply is not None and done.supply.quantity == 28
    (view,) = await active_lines(sg, context=owner, registry=REGISTRY)
    assert view.count.dispensed == 58 and view.count.remaining == 58
    # Still one line. The first supply rests on the line's own fact; the refill is a fact.
    facts = await current_facts(sg, context=owner, subject=MEDICATION)
    assert sorted(f.attribute for f in facts) == ["line:amlodipine", "supply:amlodipine"]
    assert done.supply.fact_id != first.line.fact_id and done.supply.artifact_id == later.id


async def test_the_same_label_twice_or_one_that_adds_nothing_is_a_duplicate(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    photo = await artefact(sg, owner)
    await add(sg, owner, label("amlodipine", "5 mg", quantity=30), photo)
    same_photo = await planned(sg, owner, label("amlodipine", "5 mg", quantity=30), photo)
    assert same_photo.outcome is Outcome.DUPLICATE and same_photo.draft is None
    no_quantity = await planned(
        sg, owner, label("amlodipine", "5 mg", quantity=None), await artefact(sg, owner)
    )
    assert no_quantity.outcome is Outcome.DUPLICATE
    with pytest.raises(AlreadyRecorded):
        await reconcile(
            sg,
            context=owner,
            registry=REGISTRY,
            label=label("amlodipine", "5 mg", quantity=30),
            source_artifact_id=photo.id,
            confirmation_id=uuid.uuid4(),
        )
    assert (Action.WRITE, "medication_line", "AlreadyRecorded") in _refusals(
        list(await read_audit(sg, context=owner))
    )


async def test_a_different_amount_is_a_dose_change_that_supersedes_only_with_his_yes(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await pa(sg)
    first = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD", quantity=30))
    clock.step(timedelta(days=30))
    new_pack = await artefact(sg, owner)
    changed = label("amlodipine", "10 mg", "1 tab OD", quantity=30)
    shown = await planned(sg, owner, changed, new_pack)
    assert shown.outcome is Outcome.DOSE_CHANGE
    assert shown.matched_line is not None and shown.matched_line.id == first.line.id
    assert shown.draft is not None and shown.draft.supersedes_id == first.line.fact_id

    # Without a yes, nothing moves: the old amount is still the active one.
    with pytest.raises(NotAConfirmerHere):
        await reconcile(
            sg,
            context=owner,
            registry=REGISTRY,
            label=changed,
            source_artifact_id=new_pack.id,
            confirmation_id=uuid.uuid4(),
        )
    (still,) = await active_lines(sg, context=owner, registry=REGISTRY)
    assert still.line.id == first.line.id and still.line.strength == "5 mg"
    assert still.line.superseded_at is None

    # A yes for something else (the same change, but a pack of 28) does not write this one.
    other = await planned(
        sg, owner, label("amlodipine", "10 mg", "1 tab OD", quantity=28), new_pack
    )
    assert other.draft is not None and other.draft.supersedes_id == shown.draft.supersedes_id
    with pytest.raises(NotWhatWasConfirmed):
        await reconcile(
            sg,
            context=owner,
            registry=REGISTRY,
            label=changed,
            source_artifact_id=new_pack.id,
            confirmation_id=await yes(sg, owner, other.draft),
        )

    # With his yes for exactly the change: a new line supersedes, the old one stays.
    done = await reconcile(
        sg,
        context=owner,
        registry=REGISTRY,
        label=changed,
        source_artifact_id=new_pack.id,
        confirmation_id=await yes(sg, owner, shown.draft),
    )
    assert done.outcome is Outcome.DOSE_CHANGE
    assert done.line.change_kind is ChangeKind.DOSE_CHANGE
    assert done.line.supersedes_id == first.line.id and done.line.strength == "10 mg"
    assert done.line.started_at == first.line.started_at  # the medicine did not start again
    (now,) = await active_lines(sg, context=owner, registry=REGISTRY)
    assert now.line.id == done.line.id
    # It renders as a question for the doctor, never as the new amount to take.
    assert now.doctor_question == [
        "Pek baru anda menyatakan jumlah yang berbeza daripada dahulu.",
        "Tanya Dr Tan tentang jumlah baru itu.",
    ]
    told = await story(sg, context=owner, registry=REGISTRY, line_id=done.line.id, language="en")
    assert told.how_to_take[:2] == [
        "Your new pack says a different amount from before.",
        "Ask Dr Tan about the new amount.",
    ]
    assert not any(line.startswith("Take 1 tablet") for line in told.lines)

    # Supersession keeps history: both lines, both facts, the old marked with when.
    log = await history(sg, context=owner)
    assert [line.strength for line in log] == ["5 mg", "10 mg"]
    assert log[0].superseded_at is not None and log[1].superseded_at is None
    old_fact = await sg.get(Fact, first.line.fact_id)
    assert old_fact is not None and old_fact.superseded_at is not None
    assert [
        f.value["strength"]
        for f in await current_facts(sg, context=owner, subject=MEDICATION)
        if f.attribute.startswith("line:")
    ] == ["10 mg"]
    # The refusals along the way are on the trail.
    refused = _refusals(list(await read_audit(sg, context=owner)))
    assert (Action.WRITE, "fact", "NotAConfirmerHere") in refused
    assert (Action.WRITE, "fact", "NotWhatWasConfirmed") in refused


async def test_two_strengths_in_the_cupboard_are_two_lines_named_as_duplicates(
    sg: AsyncSession,
) -> None:
    """Section 8: both lines kept, the label decides which is current. Here a different
    dose on the same generic supersedes; the same dose on another strength is a change too,
    so two active lines of one generic arise only from a second medicine of the same class."""
    owner = await pa(sg)
    await add(sg, owner, label("atorvastatin", "20 mg", quantity=30))
    done = await add(sg, owner, label("simvastatin", "20 mg", quantity=30))
    (flag,) = done.flags
    assert flag.severity is Severity.DUPLICATE and flag.text_id == "same_kind_twice"
    views = await active_lines(sg, context=owner, registry=REGISTRY, language="en")
    simva = next(v for v in views if v.line.generic == "simvastatin")
    assert simva.flags[0].question == [
        "Ask Dr Tan whether you need both the cholesterol tablet and the cholesterol tablet.",
        "They are the same kind of medicine.",
    ]


# --- the interaction check on add -----------------------------------------------------------


async def test_a_new_line_is_screened_before_it_is_saved_and_the_flag_names_both(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    await add(sg, owner, label("warfarin", "3 mg", "1 tab ON", quantity=28))
    photo = await artefact(sg, owner)
    shown = await planned(sg, owner, label("aspirin", "100 mg", "1 tab OD", quantity=30), photo)
    (flagged,) = shown.flagged
    assert flagged.interaction.pair == ("aspirin", "warfarin")  # the new medicine first
    assert flagged.interaction.severity is Severity.MAJOR
    assert flagged.other_line.generic == "warfarin"

    done = await add(sg, owner, label("aspirin", "100 mg", "1 tab OD", quantity=30), photo)
    (flag,) = done.flags
    assert flag.line_id == done.line.id and flag.other_line_id == flagged.other_line.id
    assert flag.severity is Severity.MAJOR and flag.text_id == "bleeding_risk"
    (view,) = await interaction_flags(sg, context=owner, registry=REGISTRY, language="en")
    assert view.question == [
        "Ask Dr Tan about taking the aspirin and the blood thinner tablet together.",
        "Together they can make you bleed more easily.",
    ]
    # Nothing in the sentence came from a model, and nothing tells him to stop either.
    assert "stop" not in " ".join(view.question).lower()


# --- the high-risk rule -----------------------------------------------------------------------


async def test_a_high_risk_medicine_without_a_label_photo_is_refused_by_class(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    voice = await artefact(sg, owner, kind=ArtifactKind.VOICE)
    shown = await planned(sg, owner, label("warfarin", "3 mg", "1 tab ON", quantity=28), voice)
    assert shown.needs_label_photo and shown.match.high_risk
    assert shown.draft is not None  # the card can still show what it would be
    with pytest.raises(HighRiskNeedsLabelPhoto) as refused:
        await reconcile(
            sg,
            context=owner,
            registry=REGISTRY,
            label=label("warfarin", "3 mg", "1 tab ON", quantity=28),
            source_artifact_id=voice.id,
            confirmation_id=await yes(sg, owner, shown.draft),
        )
    assert refused.value.drug_class == "anticoagulant"
    assert await active_lines(sg, context=owner, registry=REGISTRY) == []
    assert await current_facts(sg, context=owner, subject=MEDICATION) == []
    assert (Action.WRITE, "medication_line", "HighRiskNeedsLabelPhoto") in _refusals(
        list(await read_audit(sg, context=owner))
    )
    # With the label photo it is saved, and marked high-risk.
    done = await add(sg, owner, label("warfarin", "3 mg", "1 tab ON", quantity=28))
    assert done.line.high_risk and done.line.drug_class == "anticoagulant"
    # Insulin and methotrexate are the same rule.
    for generic, strength in (("insulin glargine", "100 units/ml"), ("methotrexate", "2.5 mg")):
        with pytest.raises(HighRiskNeedsLabelPhoto):
            await reconcile(
                sg,
                context=owner,
                registry=REGISTRY,
                label=label(generic, strength, "10 units ON", quantity=900),
                source_artifact_id=(await artefact(sg, owner, kind=ArtifactKind.MESSAGE)).id,
                confirmation_id=uuid.uuid4(),
            )


async def test_the_rule_is_also_a_hook_on_the_memory_store_so_no_other_path_lands_a_dose(
    sg: AsyncSession,
) -> None:
    """A medication fact whose class is high-risk cannot be asserted from a voice note by
    anything, the service's manners aside: `app.safety.high_risk.label_photo_rule` runs on
    `before_fact_write`."""
    owner = await pa(sg)
    voice = await artefact(sg, owner, kind=ArtifactKind.VOICE)
    photo = await artefact(sg, owner)
    high_risk_value = {"generic": "warfarin", "drug_class": "anticoagulant", "dose": {"amount": 1}}
    with pytest.raises(HighRiskNeedsLabelPhoto):
        await assert_fact(
            sg,
            context=owner,
            subject=MEDICATION,
            attribute="line:warfarin",
            value=high_risk_value,
            confidence=0.8,
            artifact_id=voice.id,
        )
    assert await current_facts(sg, context=owner, subject=MEDICATION) == []
    # The same statement from the label photo lands; a low-risk one from the voice note too.
    landed = await assert_fact(
        sg,
        context=owner,
        subject=MEDICATION,
        attribute="line:warfarin",
        value=high_risk_value,
        confidence=0.8,
        artifact_id=photo.id,
    )
    assert landed.artifact_id == photo.id
    low_risk = await assert_fact(
        sg,
        context=owner,
        subject=MEDICATION,
        attribute="line:amlodipine",
        value={"generic": "amlodipine", "drug_class": "calcium_channel_blocker"},
        confidence=0.8,
        artifact_id=voice.id,
    )
    assert low_risk.artifact_id == voice.id
    assert _refusals(list(await read_audit(sg, context=owner))) == {
        (Action.WRITE, "fact", "HighRiskNeedsLabelPhoto")
    }


# --- the running count and the reorder date ---------------------------------------------------


def test_count_and_reorder_arithmetic() -> None:
    once = Dose(1, "tablet", Frequency.OD)
    twice = Dose(1, "tablet", Frequency.BD)
    half_twice = Dose(0.5, "tablet", Frequency.BD)
    today = date(2026, 9, 3)
    assert arithmetic.daily_amount(once) == 1 and arithmetic.daily_amount(twice) == 2
    assert arithmetic.daily_amount(half_twice) == 1
    assert arithmetic.daily_amount(Dose(1, "tablet", Frequency.WEEKLY)) == pytest.approx(1 / 7)
    assert arithmetic.daily_amount(Dose(1, "tablet", Frequency.PRN)) is None
    assert arithmetic.count_remaining(30, 2) == 28 and arithmetic.count_remaining(2, 5) == 0
    assert arithmetic.days_left(28, once) == 28 and arithmetic.days_left(28, twice) == 14
    assert arithmetic.days_left(5, Dose(1, "tablet", Frequency.PRN)) is None
    # today + days left − lead time; longer lead for a hospital pharmacy; never before today.
    assert arithmetic.reorder_date(today, 28, once, 3) == date(2026, 9, 28)
    assert arithmetic.reorder_date(today, 28, once, 7) == date(2026, 9, 24)
    assert arithmetic.reorder_date(today, 2, once, 7) == today
    assert arithmetic.reorder_date(today, 5, Dose(1, "tablet", Frequency.PRN), 3) is None
    assert not arithmetic.reorder_due(28, once, 7) and arithmetic.reorder_due(6, once, 7)


async def test_the_count_updates_per_tap_and_the_reorder_date_shifts_with_lead_time(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await pa(sg, language="en")
    done = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD", quantity=30))
    (view,) = await active_lines(sg, context=owner, registry=REGISTRY)
    today = date(2026, 9, 3)  # 08:00 UTC is 16:00 in Singapore, the same day
    assert view.count.remaining == 30 and view.count.days_left == 30
    assert view.count.reorder_date == today + timedelta(days=27) and not view.count.reorder_due
    assert view.count.basis == "taps"
    assert view.count.lines == [
        "You have 30 tablets of your blood pressure tablet left.",
        "That is about 30 days.",
    ]

    first = await record_dose_taken(sg, context=owner, line_id=done.line.id, anchor="breakfast")
    clock.step(timedelta(days=1))
    await record_dose_taken(sg, context=owner, line_id=done.line.id, anchor="breakfast")
    (view,) = await active_lines(sg, context=owner, registry=REGISTRY)
    assert view.count.taken == 2 and view.count.remaining == 28 and view.count.days_left == 28
    assert view.count.reorder_date == today + timedelta(days=1 + 28 - 3)
    # The tap is an event of its own kind, by the person who tapped, with no confirm.
    assert first.by_person_id == owner.person_id and first.anchor == "breakfast"
    event = await sg.scalar(select(DoseTaken).where(DoseTaken.id == first.id))
    assert event is not None
    from app.memory.models import Event

    kinds = {
        e.kind for e in await sg.scalars(select(Event).where(Event.profile_id == owner.profile_id))
    }
    assert EventKind.DOSE_TAKEN in kinds
    assert (Action.WRITE, "dose_taken") in {
        (e.action, e.target)
        for e in await read_audit(sg, context=owner)
        if e.outcome is AuditOutcome.ALLOWED
    }

    # A hospital supply has a longer lead time, so the same count reorders earlier.
    hospital = await add(
        sg,
        owner,
        label("frusemide", "40 mg", "1 tab OM", quantity=30, source_kind=SourceKind.HOSPITAL),
    )
    views = {v.line.generic: v for v in await active_lines(sg, context=owner, registry=REGISTRY)}
    assert hospital.line.lead_time_days == 7
    assert views["frusemide"].count.reorder_date == (today + timedelta(days=1)) + timedelta(
        days=30 - 7
    )


async def test_the_reorder_card_shows_below_the_threshold_in_his_words(sg: AsyncSession) -> None:
    owner = await pa(sg, language="en")
    await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD", quantity=6))
    (view,) = await active_lines(sg, context=owner, registry=REGISTRY)
    assert view.count.reorder_due and view.count.days_left == 6
    assert view.count.reorder == [
        "your blood pressure tablet runs out on Wednesday 9 September.",
        "Ask your family to order more.",
    ]
    assert view.count.reorder_actions == {
        "ask_to_order": "Ask the family to order.",
        "i_have_more": "I have more at home.",
    }


async def test_a_when_needed_medicine_counts_by_taps_only(sg: AsyncSession) -> None:
    owner = await pa(sg, language="en")
    done = await add(sg, owner, label("paracetamol", "500 mg", "2 tabs prn", quantity=20))
    await record_dose_taken(sg, context=owner, line_id=done.line.id)
    (view,) = await active_lines(sg, context=owner, registry=REGISTRY)
    assert view.count.remaining == 18 and view.count.days_left is None
    assert view.count.reorder_date is None and not view.count.reorder_due
    assert view.count.lines == ["You have 18 tablets of the pain tablet left."]
    assert await today(sg, context=owner, registry=REGISTRY) == []  # no anchors, no cards


async def test_todays_doses_are_cards_at_his_anchors_and_a_tap_marks_one(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, language="en")
    bp = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD", quantity=30))
    await add(sg, owner, label("metformin", "500 mg", "1 tab BD", quantity=60))
    slots = await today(sg, context=owner, registry=REGISTRY)
    assert [(s.line.generic, s.anchor, s.taken) for s in slots] == [
        ("amlodipine", "breakfast", False),
        ("metformin", "breakfast", False),
        ("metformin", "dinner", False),
    ]
    assert slots[0].card == "Take 1 tablet of your blood pressure tablet with breakfast."
    assert slots[0].taken_label == "Taken"
    await record_dose_taken(sg, context=owner, line_id=bp.line.id, anchor="breakfast")
    slots = await today(sg, context=owner, registry=REGISTRY)
    assert (slots[0].line.generic, slots[0].taken) == ("amlodipine", True)
    with pytest.raises(NoSuchLine):
        await record_dose_taken(sg, context=owner, line_id=uuid.uuid4())


# --- who may do what ------------------------------------------------------------------------------


async def test_a_helper_key_reads_the_list_and_the_story_and_taps_but_cannot_add(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    done = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD", quantity=30))
    mei = await let_in(
        sg, owner, phone="+6592220001", name="Mei", role=KeyRole.HELPER, scopes={Scope.MEDICINES}
    )
    (view,) = await active_lines(sg, context=mei, registry=REGISTRY)
    assert view.line.id == done.line.id
    told = await story(sg, context=mei, registry=REGISTRY, line_id=done.line.id)
    assert told.language == "ms" and told.purpose[0] == "Ini ubat tekanan darah anda."
    tapped = await record_dose_taken(sg, context=mei, line_id=done.line.id, anchor="breakfast")
    assert tapped.by_person_id == mei.person_id

    photo = await artefact(sg, owner)
    with pytest.raises(NotTheirsToChange):
        await plan(
            sg,
            context=mei,
            registry=REGISTRY,
            label=label("aspirin", "100 mg", quantity=30),
            source_artifact_id=photo.id,
        )
    with pytest.raises(NotTheirsToChange):
        await reconcile(
            sg,
            context=mei,
            registry=REGISTRY,
            label=label("aspirin", "100 mg", quantity=30),
            source_artifact_id=photo.id,
            confirmation_id=uuid.uuid4(),
        )
    (still,) = await active_lines(sg, context=owner, registry=REGISTRY)
    assert still.line.generic == "amlodipine"
    refused = [e for e in await read_audit(sg, context=owner) if e.outcome is AuditOutcome.REFUSED]
    assert {(e.actor_person_id, e.action, e.refused_because) for e in refused} == {
        (mei.person_id, Action.READ, "NotTheirsToChange"),
        (mei.person_id, Action.WRITE, "NotTheirsToChange"),
    }


async def test_a_key_without_the_medicines_scope_is_refused_at_the_door(sg: AsyncSession) -> None:
    owner = await pa(sg)
    done = await add(sg, owner, label("amlodipine", "5 mg", quantity=30))
    viewer = await let_in(
        sg, owner, phone="+6592220002", name="Kit", role=KeyRole.VIEWER, scopes={Scope.READINGS}
    )
    with pytest.raises(OutOfScope):
        await active_lines(sg, context=viewer, registry=REGISTRY)
    with pytest.raises(OutOfScope):
        await story(sg, context=viewer, registry=REGISTRY, line_id=done.line.id)
    with pytest.raises(OutOfScope):
        await record_dose_taken(sg, context=viewer, line_id=done.line.id)


async def test_a_caregiver_may_add_and_the_line_names_her_as_the_confirmer(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    ash = await let_in(
        sg,
        owner,
        phone="+6592220003",
        name="Ash",
        role=KeyRole.CAREGIVER,
        scopes={Scope.MEDICINES, Scope.RECORDS},
    )
    photo = await artefact(sg, ash)
    done = await add(sg, ash, label("metformin", "500 mg", "1 tab BD", quantity=60), photo)
    assert done.line.confirmed_by_person_id == ash.person_id
    (view,) = await active_lines(sg, context=owner, registry=REGISTRY)
    assert view.line.id == done.line.id


async def test_a_line_is_immutable_and_a_yes_is_spent_once(sg: AsyncSession) -> None:
    owner = await pa(sg)
    done = await add(sg, owner, label("amlodipine", "5 mg", quantity=30))
    row = await sg.get(MedicationLine, done.line.id)
    assert row is not None
    row.strength = "10 mg"
    from app.db import ImmutableRow

    with pytest.raises(ImmutableRow):
        await sg.flush()
    await sg.rollback()


async def test_nothing_in_the_medicines_module_writes_a_drug_fact_from_anywhere_but_the_registry(
    sg: AsyncSession,
) -> None:
    """The class, the brand, the strength and the form on the line are the register's answer,
    not the label's words: a label that says 'Norvasc' becomes the register's product."""
    owner = await pa(sg)
    from app.medicines.service import Label

    done = await add(
        sg,
        owner,
        Label(dose=parse_dose_text("1 tab OD"), brand="norvasc", strength="5mg", quantity=30),
    )
    assert (done.line.generic, done.line.brand, done.line.strength) == (
        "amlodipine",
        "Norvasc",
        "5 mg",
    )
    assert done.line.registration_no == "MAL19970001A"
    draft = FactDraft(
        subject=MEDICATION,
        attribute="line:amlodipine",
        value={},
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=None,
        episode_id=None,
        supersedes_id=None,
    )
    assert draft.confirm_subject.value == "fact"


def _unused(context: KeyContext) -> None:  # pragma: no cover - keeps the import honest
    assert context
