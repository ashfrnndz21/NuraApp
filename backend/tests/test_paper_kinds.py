"""Lab reports, hospital and clinic letters, and insurance documents through the review card
(documents-lab-reports-and-insurance): the document kinds the model decides between, routed
into the existing review flow and never past it.

Acceptance lines this covers:
- A lab report's own vitals row, in a unit the app already knows, becomes a reading proposal
  on confirm; an ordinary lab row, one of its own metadata siblings, or a value in an unknown
  unit stays a plain paper fact.
- A lab report naming a red-flag word goes through the red-flag path before the card is even
  shown, exactly like typed free text.
- A letter's diagnosis line is kept as the clinician wrote it — a control word against the
  condition (`app.safety.emergency_card` docstring) — never rephrased.
- A policy or a claim document's fields become facts under Scope.MONEY, never RECORDS, and
  the review card never writes a Policy or an InsuranceClaim row directly.
- Every proposed field carries its artefact and its page.
- A pill photo and a pharmacy receipt both route through the review card the same way; a
  pill's guess never auto-confirms, matched against the registry or not; a pharmacy receipt's
  matched line becomes a cost entry the ledger sums; an unmatched line stays a plain paper
  fact; a receipt's item name naming a red-flag word is flagged before the card is shown, the
  same as a lab report's remark (#pill-receipt).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.drafts import FactDraft
from app.drugs.fixture import FixtureRegistry
from app.ingestion.extract import DocumentKind, FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.review import PILL_MAX_CONFIDENCE, card_fields, confirm_review_card, review_photo
from app.insurance.ledger import medicine_monthly_costs
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.memory.models import ConfidenceState
from app.memory.semantic import current_facts
from app.regions import Region
from app.safety.high_risk import HighRiskNeedsLabelPhoto, refuse_dose_without_label_photo
from app.safety.red_flags import FlagKind, open_flags
from tests.medicines_support import add, label
from tests.paper import (
    CLINIC_LETTER_HYPERTENSION,
    INSURANCE_CLAIM,
    INSURANCE_POLICY,
    LAB_REPORT_RED_FLAG,
    LAB_REPORT_VITALS,
    METABOLIC_PANEL,
    PAPER,
    PHARMACY_RECEIPT,
    PHARMACY_RECEIPT_RED_FLAG,
    PILL_PHOTO,
    WARFARIN_LABEL,
)
from tests.test_ingestion import _card, _decide, _pa, _photo, _yes  # test helpers

REGISTRY = FixtureRegistry.load()


@pytest.fixture
def store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path, Region.SG)


@pytest.fixture
def extractor() -> FixtureExtractor:
    return FixtureExtractor(PAPER)


async def _confirm(
    sg: AsyncSession, owner: KeyContext, store: LocalObjectStore, extractor: FixtureExtractor, label: str
):
    card, fields = await _card(sg, owner, store, extractor, label)
    decisions = _decide(fields)
    yes = await _yes(sg, owner, card, decisions)
    return await confirm_review_card(
        sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=yes
    )


async def _confirm_with_registry(
    sg: AsyncSession, owner: KeyContext, store: LocalObjectStore, extractor: FixtureExtractor, paper_label: str
):
    """`_confirm`, but matched against the licensed registry (`registry=REGISTRY`): what a
    pill photo's guess is matched against, and what turns a pharmacy receipt's matching item
    line into a cost entry besides its plain paper fact (#pill-receipt)."""
    card, fields = await _card_with_registry(sg, owner, store, extractor, paper_label)
    decisions = _decide(fields)
    yes = await _yes(sg, owner, card, decisions)
    return await confirm_review_card(
        sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=yes, registry=REGISTRY
    )


async def _card_with_registry(
    sg: AsyncSession, owner: KeyContext, store: LocalObjectStore, extractor: FixtureExtractor, paper_label: str
):
    """`_card`, but reading through the licensed registry — what a pill photo's guess is
    matched against at read time (#pill-receipt)."""
    photo = await _photo(sg, owner, store, paper_label)
    card = await review_photo(
        sg, context=owner, artifact_id=photo.id, store=store, extractor=extractor, language="en", registry=REGISTRY
    )
    fields = await card_fields(sg, context=owner, card_id=card.id)
    return card, fields


async def test_a_lab_reports_known_unit_becomes_a_reading_proposal_and_the_rest_stay_facts(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    card, decided, facts = await _confirm(sg, await _pa(sg), store, extractor, LAB_REPORT_VITALS)
    assert card.document_kind is DocumentKind.LAB_REPORT
    reading = next(f for f in decided if f.subject == "blood_sugar")
    reading_fact = next(fact for fact in facts if fact.id == reading.fact_id)
    assert reading_fact.subject == "blood_sugar"
    assert reading_fact.attribute == "reading"
    assert reading_fact.value == {"glucose": 5.6}
    assert reading_fact.unit == "mmol/L"
    assert reading_fact.event_id is not None
    # An ordinary lab row and a header field are plain facts. The fixture's `ldl_reference_
    # range` sibling (the legacy shape) is folded onto `ldl`'s own `range` and never reaches
    # the card as a line of its own (defect #3, `fold_legacy_reference_ranges`).
    ldl = next(f for f in decided if f.subject == "lipid_panel" and f.attribute == "ldl")
    ldl_fact = next(fact for fact in facts if fact.id == ldl.fact_id)
    assert ldl_fact.value == 140 and ldl_fact.unit == "mg/dL" and ldl_fact.event_id is None
    assert ldl.range == {"low": None, "high": 130.0, "text": "<130"}
    assert not any(f.attribute == "ldl_reference_range" for f in decided)
    facility = next(f for f in decided if f.subject == "lab_report")
    facility_fact = next(fact for fact in facts if fact.id == facility.fact_id)
    assert facility_fact.subject == "lab_report" and facility_fact.value == "Bukit Lab"


async def test_a_wider_metabolic_panel_carries_its_own_printed_ranges_and_the_other_escape_hatch(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    """The controlled vocabulary added for defect #1 (kidney_panel, blood_test, liver_panel)
    reaches the card under its own canonical codes; a result given its own `range` directly
    (not a legacy `_reference_range` sibling) keeps it exactly; a result with no printed range
    at all carries none; a line outside the vocabulary is `subject`/`attribute` "lipid_panel"/
    "other" with `label_on_paper` — the words a person would still recognise the line by."""
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor, METABOLIC_PANEL)
    assert card.document_kind is DocumentKind.LAB_REPORT
    by_key = {(f.subject, f.attribute): f for f in fields}

    creatinine = by_key[("kidney_panel", "creatinine")]
    assert creatinine.value == 95 and creatinine.unit == "umol/L"
    assert creatinine.range == {"low": 60.0, "high": 110.0, "text": "60 - 110"}

    egfr = by_key[("kidney_panel", "egfr")]
    assert egfr.range == {"low": 60.0, "high": None, "text": ">60"}

    potassium = by_key[("kidney_panel", "potassium")]
    assert potassium.range == {"low": 3.5, "high": 5.2, "text": "3.5 - 5.2"}

    hba1c = by_key[("blood_test", "hba1c")]
    assert hba1c.value == 5.4 and hba1c.range == {"low": None, "high": 5.7, "text": "<5.7"}

    alt = by_key[("liver_panel", "alt")]
    assert alt.value == 42 and alt.range is None  # no printed range at all: none invented

    other = by_key[("lipid_panel", "other")]
    assert other.value == "0.9" and other.label_on_paper == "Apo-B"


async def test_a_lab_report_naming_a_red_word_is_flagged_before_the_card_is_shown(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner, store, LAB_REPORT_RED_FLAG)
    card = await review_photo(
        sg, context=owner, artifact_id=photo.id, store=store, extractor=extractor, language="en"
    )
    # The flag is raised at review time, before any decision on the card's fields.
    flags = await open_flags(sg, context=owner)
    assert len(flags) == 1
    flag = flags[0]
    assert flag.code == "breathless"
    assert flag.kind is FlagKind.RED_FLAG
    assert flag.artifact_id == photo.id
    assert flag.appointment_id is None
    assert flag.payload["found_in"] == "lab_report.remark"
    assert card.document_kind is DocumentKind.LAB_REPORT  # the card still opens as usual


async def test_a_letters_diagnosis_line_is_kept_verbatim_as_a_control_word(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, decided, facts = await _confirm(sg, owner, store, extractor, CLINIC_LETTER_HYPERTENSION)
    assert card.document_kind is DocumentKind.CLINIC_SLIP
    condition = next(f for f in decided if f.subject == "hypertension")
    assert condition.attribute == "control"
    fact = next(fact for fact in facts if fact.id == condition.fact_id)
    assert fact.value == "Hypertension, well controlled on current medication"
    assert fact.event_id is not None  # the clinic slip's own VISIT event
    # Never rephrased: the fact holds the clinician's own words, read back exactly.
    held = list(await current_facts(sg, context=owner, subject="hypertension", at=fact.valid_from))
    assert held and held[0].value == fact.value


async def test_insurance_documents_route_to_money_scoped_facts_never_records(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    # The scope decision itself, guarded directly: a policy or a claim's fields must never
    # fall back to RECORDS, which a clinic key also holds (`app.insurance.policy`'s "the
    # scope decision, written down").
    assert scope_for_subject("insurance_policy") is Scope.MONEY
    assert scope_for_subject("insurance_claim") is Scope.MONEY

    owner = await _pa(sg)
    policy_card, policy_decided, policy_facts = await _confirm(
        sg, owner, store, extractor, INSURANCE_POLICY
    )
    assert policy_card.document_kind is DocumentKind.INSURANCE_POLICY
    insurer = next(f for f in policy_decided if f.attribute == "insurer")
    fact = next(fact for fact in policy_facts if fact.id == insurer.fact_id)
    assert fact.subject == "insurance_policy" and fact.value == "Great Eastern"
    assert fact.event_id is None  # a fact only — never a Policy row (`app.insurance.policy`)
    held = list(await current_facts(sg, context=owner, subject="insurance_policy", at=fact.valid_from))
    assert {f.attribute: f.value for f in held} == {
        "insurer": "Great Eastern",
        "policy_number": "GE-HS-12345",
        "plan": "Hospital Shield",
        "start_date": "2026-01-01",
    }

    claim_card, claim_decided, claim_facts = await _confirm(sg, owner, store, extractor, INSURANCE_CLAIM)
    assert claim_card.document_kind is DocumentKind.INSURANCE_CLAIM
    claim_number = next(f for f in claim_decided if f.attribute == "claim_number")
    claim_fact = next(fact for fact in claim_facts if fact.id == claim_number.fact_id)
    assert claim_fact.subject == "insurance_claim" and claim_fact.value == "CLM-98765"
    assert claim_fact.event_id is None


async def test_every_proposed_field_carries_its_artefact_and_its_page(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor, LAB_REPORT_VITALS)
    assert card.artifact_id is not None
    assert all(field.page == 1 for field in fields)  # every field of this fixture is page 1


async def test_a_lab_readings_fact_joins_the_same_trend_a_device_reading_would(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    """A lab-sourced reading is readable the same way any reading is: under READINGS, by
    subject, current."""
    owner = await _pa(sg)
    _, decided, facts = await _confirm(sg, owner, store, extractor, LAB_REPORT_VITALS)
    reading = next(f for f in decided if f.subject == "blood_sugar")
    fact = next(fact for fact in facts if fact.id == reading.fact_id)
    held = list(await current_facts(sg, context=owner, subject="blood_sugar", at=fact.valid_from))
    assert held and held[0].id == fact.id
    assert scope_for_subject("blood_sugar") is Scope.READINGS


# --- the pill-and-receipt story (#pill-receipt) -------------------------------------------


async def test_a_pill_photo_and_a_pharmacy_receipt_both_route_through_the_review_card(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    """Neither kind is a special route of its own: both are read into an ordinary review
    card, one field per statement on the page, exactly like a lab report or a label."""
    owner = await _pa(sg)
    pill_card, pill_fields = await _card(sg, owner, store, extractor, PILL_PHOTO)
    assert pill_card.document_kind is DocumentKind.PILL_PHOTO
    assert {f.subject for f in pill_fields} == {"pill", "medicine"}

    receipt_card, receipt_fields = await _card(sg, owner, store, extractor, PHARMACY_RECEIPT)
    assert receipt_card.document_kind is DocumentKind.PHARMACY_RECEIPT
    assert {f.subject for f in receipt_fields} == {"receipt", "item_1", "item_2"}


async def test_a_pill_photos_guess_never_auto_confirms_even_matched_against_the_registry(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    """The pill's guess (paracetamol 500 mg) matches a product in the licensed registry
    exactly — an ordinary label photo at that confidence would need no check — but a pill's
    identity is a guess from what it looks like, never a read: it is still held below the
    confirmation threshold, so `needs_confirm` is set either way. The raw `pill` fields
    (what was actually seen) are untouched by the cap."""
    owner = await _pa(sg)
    card, fields = await _card_with_registry(sg, owner, store, extractor, PILL_PHOTO)
    assert card.document_kind is DocumentKind.PILL_PHOTO
    medicine = [f for f in fields if f.subject == "medicine"]
    assert medicine, "the guess matched the registry and is still on the card"
    for field in medicine:
        assert field.confidence <= PILL_MAX_CONFIDENCE
        assert field.needs_confirm is True
    name = next(f for f in medicine if f.attribute == "name")
    strength = next(f for f in medicine if f.attribute == "strength")
    # Narrowed to the register's own canonical answer, not the model's free text — but only
    # ever offered as a proposal, never taken as read.
    assert name.value == "paracetamol"
    assert strength.value == "500 mg"
    # The pill's own fields (what was actually seen) pass through uncapped.
    colour = next(f for f in fields if f.subject == "pill" and f.attribute == "colour")
    assert colour.confidence == pytest.approx(0.92)


async def test_a_pharmacy_receipts_matched_line_sums_into_the_ledger_and_an_unmatched_line_stays_a_fact(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    """A line naming a medicine already on his list (Panadol, matched to paracetamol) becomes
    a cost entry the ledger sums, besides its own plain paper fact; a line naming something
    not on his list (a hand sanitiser) stays a plain paper fact only — never held back for
    that, and never silently taken as a medicine."""
    owner = await _pa(sg)
    await add(sg, owner, label("paracetamol", "500 mg"))

    card, decided, facts = await _confirm_with_registry(sg, owner, store, extractor, PHARMACY_RECEIPT)
    assert card.document_kind is DocumentKind.PHARMACY_RECEIPT

    # The matched line's own words are kept exactly as printed, same as any other kind.
    item1_name = next(f for f in decided if f.subject == "item_1" and f.attribute == "name")
    item1_fact = next(fact for fact in facts if fact.id == item1_name.fact_id)
    assert item1_fact.value == "Panadol"

    # And, besides that plain fact, a cost entry for the generic it matched, with the
    # quantity bought beside the price — what the monthly figure below is worked out from.
    cost_facts = [fact for fact in facts if fact.subject == "medicine_cost"]
    assert len(cost_facts) == 1
    assert cost_facts[0].attribute == "paracetamol"
    assert cost_facts[0].value == {"total_cents": 1300, "item": "Panadol", "quantity": 2}
    assert cost_facts[0].unit == "SGD"
    assert scope_for_subject("medicine_cost") is Scope.MEDICINES

    # The ledger works out a real month from what was bought and how much he actually takes
    # a day (1 tablet OD, `tests.medicines_support.label`'s default dose): 2 tablets bought,
    # 1 a day, is 2/30 of a month, so S$13 buys S$195 worth of month at that rate.
    costs = await medicine_monthly_costs(sg, context=owner, language="en")
    assert len(costs) == 1
    assert costs[0].generic == "paracetamol"
    assert costs[0].currency == "SGD"
    assert costs[0].monthly_cents == 19500
    assert costs[0].monthly_said == "S$195 a month"

    # The unmatched line (nothing on his list is a hand sanitiser) stays a plain fact only.
    item2_name = next(f for f in decided if f.subject == "item_2" and f.attribute == "name")
    item2_fact = next(fact for fact in facts if fact.id == item2_name.fact_id)
    assert item2_fact.value == "Hand sanitiser 250ml"
    assert not any(fact.attribute == "hand sanitiser" for fact in cost_facts)
    assert {fact.generic for fact in costs} == {"paracetamol"}  # never the hand sanitiser


async def test_a_pharmacy_receipt_naming_nothing_on_his_list_writes_no_cost_entry_at_all(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    """A receipt confirmed without a registry to match against (or against nobody's list)
    writes every line as a plain paper fact and no cost entry — never held back."""
    owner = await _pa(sg)
    card, decided, facts = await _confirm(sg, owner, store, extractor, PHARMACY_RECEIPT)  # no registry
    assert card.document_kind is DocumentKind.PHARMACY_RECEIPT
    assert not any(fact.subject == "medicine_cost" for fact in facts)
    item1_name = next(f for f in decided if f.subject == "item_1" and f.attribute == "name")
    assert next(fact for fact in facts if fact.id == item1_name.fact_id).value == "Panadol"


async def test_a_pharmacy_receipt_item_naming_a_red_word_is_flagged_before_the_card_is_shown(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    """The same red-flag path a lab report's remark goes through (`_red_flag_scan`), read off
    a receipt's item line instead: "whichever way it comes in, it comes here first"."""
    owner = await _pa(sg)
    photo = await _photo(sg, owner, store, PHARMACY_RECEIPT_RED_FLAG)
    card = await review_photo(
        sg, context=owner, artifact_id=photo.id, store=store, extractor=extractor, language="en"
    )
    flags = await open_flags(sg, context=owner)
    assert len(flags) == 1
    flag = flags[0]
    assert flag.code == "chest_pain"
    assert flag.kind is FlagKind.RED_FLAG
    assert flag.artifact_id == photo.id
    assert flag.appointment_id is None
    assert flag.payload["found_in"] == "item_1.name"
    assert card.document_kind is DocumentKind.PHARMACY_RECEIPT  # the card still opens as usual


async def test_a_pill_photos_review_card_never_grounds_a_high_risk_label_confirm(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    """A pill photo is stored as `ArtifactKind.PHOTO`, the very same storage kind a real label
    photo is — but its own review card says which it was (#pill-receipt clinical-safety
    review): a warfarin dose submitted with a pill photo's artefact as its source is refused
    exactly like no photo at all, never silently accepted because the storage kind alone
    matches (`app.safety.high_risk.is_pill_photo`, checked in both `app.medicines.service.
    plan` and the `before_fact_write` hook that is the floor under every writer). A real
    label photo, confirmed the same way, still passes."""
    owner = await _pa(sg)
    pill_photo = await _photo(sg, owner, store, PILL_PHOTO)
    pill_card = await review_photo(
        sg, context=owner, artifact_id=pill_photo.id, store=store, extractor=extractor, language="en"
    )
    assert pill_card.document_kind is DocumentKind.PILL_PHOTO
    with pytest.raises(HighRiskNeedsLabelPhoto):
        await add(sg, owner, label("warfarin", "3 mg", "1 tab ON"), pill_photo)

    # A real label photo, confirmed the same way (its own review card, not a bare artefact),
    # still passes: the rule tells a pill from a label, it does not refuse every photo.
    label_photo = await _photo(sg, owner, store, WARFARIN_LABEL)
    label_card = await review_photo(
        sg, context=owner, artifact_id=label_photo.id, store=store, extractor=extractor, language="en"
    )
    assert label_card.document_kind is DocumentKind.MEDICINE_LABEL
    done = await add(sg, owner, label("warfarin", "3 mg", "1 tab ON"), label_photo)
    assert done.line.generic == "warfarin"


async def test_the_before_fact_write_hook_itself_tells_a_pill_photo_from_a_label(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    """The floor under every writer (`app.safety.high_risk.refuse_dose_without_label_photo`)
    is what actually stops a high-risk dose, whichever module tries to write it — not only
    `app.medicines.service.plan`'s own earlier check, which is friendlier but not the only
    door (#pill-receipt clinical-safety review). A `medicine`/`strength` draft naming warfarin,
    resting on a pill photo's own artefact, is refused here directly; the same draft resting
    on a real label photo's artefact is not."""
    owner = await _pa(sg)
    pill_photo = await _photo(sg, owner, store, PILL_PHOTO)
    await review_photo(
        sg, context=owner, artifact_id=pill_photo.id, store=store, extractor=extractor, language="en"
    )
    draft = FactDraft(
        subject="medicine",
        attribute="strength",
        value="warfarin 5 mg",
        unit=None,
        confidence=0.9,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=pill_photo.id,
        event_id=None,
        episode_id=None,
        supersedes_id=None,
    )
    with pytest.raises(HighRiskNeedsLabelPhoto):
        await refuse_dose_without_label_photo(sg, owner, draft)

    label_photo = await _photo(sg, owner, store, WARFARIN_LABEL)
    await review_photo(
        sg, context=owner, artifact_id=label_photo.id, store=store, extractor=extractor, language="en"
    )
    on_label = replace(draft, artifact_id=label_photo.id)
    await refuse_dose_without_label_photo(sg, owner, on_label)  # does not raise
