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
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.extract import DocumentKind, FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.review import confirm_review_card, review_photo
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.memory.semantic import current_facts
from app.regions import Region
from app.safety.red_flags import FlagKind, open_flags
from tests.paper import (
    CLINIC_LETTER_HYPERTENSION,
    INSURANCE_CLAIM,
    INSURANCE_POLICY,
    LAB_REPORT_RED_FLAG,
    LAB_REPORT_VITALS,
    PAPER,
)
from tests.test_ingestion import _card, _decide, _pa, _photo, _yes  # test helpers


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
    # An ordinary lab row, its own metadata sibling, and a header field are plain facts.
    ldl = next(f for f in decided if f.subject == "lipid_panel" and f.attribute == "ldl")
    ldl_fact = next(fact for fact in facts if fact.id == ldl.fact_id)
    assert ldl_fact.value == 140 and ldl_fact.unit == "mg/dL" and ldl_fact.event_id is None
    ref_range = next(f for f in decided if f.attribute == "ldl_reference_range")
    ref_fact = next(fact for fact in facts if fact.id == ref_range.fact_id)
    assert ref_fact.value == "<130" and ref_fact.event_id is None
    facility = next(f for f in decided if f.subject == "lab_report")
    facility_fact = next(fact for fact in facts if fact.id == facility.fact_id)
    assert facility_fact.subject == "lab_report" and facility_fact.value == "Bukit Lab"


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
