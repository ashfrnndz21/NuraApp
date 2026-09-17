"""E02-01 and E02-07 at the service: a photo stored in its region, read into a review card
with a confidence per field, and turned into facts with provenance only on a person's yes.

Acceptance lines. E02-01: lab values are extracted with unit and date — the lipid panel comes
off the fixture with every unit and the date on the paper, and the facts carry both. E02-07:
fields below the threshold are shown dotted (`needs_confirm`), and a single tap saves — one
confirmation over the whole card writes every kept field as a fact.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Outcome
from app.audit.trail import read_audit
from app.db import ImmutableRow, as_utc
from app.drafts import ConfirmSubject
from app.identity.service import create_own_profile, register_person
from app.ingestion.extract import (
    DocumentKind,
    ExtractedField,
    Extraction,
    FixtureExtractor,
    Hints,
    NotAFieldCode,
    NotAValue,
)
from app.ingestion.models import CONFIDENCE_THRESHOLD, FieldState, ReviewCard, ReviewField
from app.ingestion.objects import LocalObjectStore, NoSuchObject, NotAStorageKey, photo_key
from app.ingestion.photos import NotAPhoto, PhotoTooLarge, store_photo
from app.ingestion.review import (
    AlreadyConfirmed,
    Decision,
    NoSuchReviewCard,
    NoSuchReviewField,
    NotADecision,
    NotEveryFieldDecided,
    card_fields,
    card_from,
    confirm_review_card,
    list_review_cards,
    require_review_card,
    review_draft_for,
    review_photo,
)
from app.keys.confirm import (
    Confirmation,
    NotAConfirmerHere,
    NotWhatWasConfirmed,
    confirm,
)
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.memory.models import Artifact, ArtifactKind, ConfidenceState, SourceChannel
from app.memory.semantic import current_facts
from app.regions import OutOfRegion, Region
from app.state.models import Dimension, StateTrigger
from app.state.service import current_state
from tests.paper import (
    BP_CUFF,
    CLINIC_SLIP,
    DISCHARGE_LETTER,
    GLUCOMETER,
    HANDWRITTEN_PRESCRIPTION,
    LIPID_PANEL,
    LIPID_PANEL_2025,
    PAPER,
    RECEIPT,
    WARFARIN_LABEL,
    fixture,
    papers,
    placeholder_of,
    placeholder_png,
)
from tests.support import OPENING_CONSENT, agree_to_family_sharing, refused_unit

SEPT_3 = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
SG = Region.SG


async def _pa(session: AsyncSession, phone: str = "+6591110001") -> KeyContext:
    pa = await register_person(session, region=SG, display_name="Pa", phone_e164=phone)
    profile = await create_own_profile(session, region=SG, owner=pa, consent=OPENING_CONSENT)
    return await resolve_key_context(session, region=SG, person_id=pa.id, profile_id=profile.id)


async def _let_in(
    session: AsyncSession, owner: KeyContext, *, scopes: set[Scope], phone: str = "+6591110002"
) -> KeyContext:
    holder = await register_person(session, region=SG, display_name="Mei", phone_e164=phone)
    await agree_to_family_sharing(session, owner, holder, role=KeyRole.CAREGIVER)
    await grant_key(session, context=owner, holder=holder, role=KeyRole.CAREGIVER, scopes=scopes)
    return await resolve_key_context(
        session, region=SG, person_id=holder.id, profile_id=owner.profile_id
    )


@pytest.fixture
def store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path, SG)


@pytest.fixture
def extractor() -> FixtureExtractor:
    return FixtureExtractor(PAPER)


async def _photo(
    session: AsyncSession, context: KeyContext, store: LocalObjectStore, label: str = LIPID_PANEL
) -> Artifact:
    return await store_photo(
        session,
        context=context,
        store=store,
        data=placeholder_png(label),
        content_type="image/png",
        captured_at=SEPT_3,
        source_channel=SourceChannel.APP,
    )


async def _card(
    session: AsyncSession,
    context: KeyContext,
    store: LocalObjectStore,
    extractor: FixtureExtractor,
    label: str = LIPID_PANEL,
) -> tuple[ReviewCard, list[ReviewField]]:
    photo = await _photo(session, context, store, label)
    card = await review_photo(
        session,
        context=context,
        artifact_id=photo.id,
        store=store,
        extractor=extractor,
        language="ms",
    )
    return card, list(await card_fields(session, context=context, card_id=card.id))


def _decide(
    fields: list[ReviewField],
    *,
    correct: dict[str, Any] | None = None,
    reject: set[str] = frozenset(),
) -> list[Decision]:
    """Confirm every field, except the attributes named: corrected to the value given, or
    rejected."""
    decided = []
    for field in fields:
        if correct and field.attribute in correct:
            decided.append(Decision(field.id, FieldState.CORRECTED, correct[field.attribute]))
        elif field.attribute in reject:
            decided.append(Decision(field.id, FieldState.REJECTED))
        else:
            decided.append(Decision(field.id, FieldState.CONFIRMED))
    return decided


async def _yes(
    session: AsyncSession, context: KeyContext, card: ReviewCard, decisions: list[Decision]
) -> uuid.UUID:
    draft = await review_draft_for(session, context=context, card_id=card.id, decisions=decisions)
    return (await confirm(session, context, draft)).id


def _refusals(trail: Any) -> set[tuple[Action, str, str]]:
    return {
        (entry.action, entry.target, entry.refused_because or "")
        for entry in trail
        if entry.outcome is Outcome.REFUSED
    }


# --- the fixtures themselves -------------------------------------------------------------


def test_every_paper_fixture_names_the_digest_of_its_placeholder() -> None:
    """The extractor answers by digest, so a fixture whose digest drifted is a page it would
    never recognise. Nine fixtures are here: the lipid panel and the warfarin label (E02-01),
    the clinic slip and the prescription by hand (E02-02), the hospital letter and the receipt
    as PDFs (E02-03), two machines' screens (E02-08), and the second lipid panel
    the lab trend reads (E09-01). The labelled answers beside them
    (`*.expected.json`) are the accuracy harness's and name no digest."""
    labels = papers()
    assert set(labels) == {
        LIPID_PANEL,
        WARFARIN_LABEL,
        CLINIC_SLIP,
        HANDWRITTEN_PRESCRIPTION,
        DISCHARGE_LETTER,
        RECEIPT,
        BP_CUFF,
        GLUCOMETER,
        LIPID_PANEL_2025,
    }
    for label in labels:
        paper = fixture(label)
        assert paper["placeholder"] == label
        assert paper["sha256"] == hashlib.sha256(placeholder_of(label)).hexdigest()
        assert "redacted" in paper["note"].lower()
    assert all("sha256" not in json.loads(p.read_text()) for p in PAPER.glob("*.expected.json"))


def test_the_lipid_panel_reads_as_a_lab_report_with_units_and_the_date_on_the_paper() -> None:
    paper = fixture(LIPID_PANEL)
    assert paper["document_kind"] == "lab_report"
    assert paper["document_date"] == "2023-09-07"
    by_attribute = {field["attribute"]: field for field in paper["fields"]}
    assert {name: f["value"] for name, f in by_attribute.items()} == {
        "total_cholesterol": 230,
        "hdl": 73,
        "ldl": 152,
        "triglycerides": 64,  # the deliberate misread; the paper says 54
        "vldl": 10.78,
        "tc_hdl_ratio": 3.1,
        "non_hdl_cholesterol": 156.3,
    }
    assert by_attribute["triglycerides"]["paper_says"] == 54
    assert all(f["unit"] == "mg/dL" for n, f in by_attribute.items() if n != "tc_hdl_ratio")
    assert by_attribute["tc_hdl_ratio"]["unit"] is None


def test_the_label_reads_per_the_medications_module_section_2() -> None:
    paper = fixture(WARFARIN_LABEL)
    assert paper["document_kind"] == "medicine_label"
    attributes = [field["attribute"] for field in paper["fields"]]
    assert attributes == ["name", "strength", "dose", "quantity", "dispensed_at", "prescriber"]
    dose = next(field for field in paper["fields"] if field["attribute"] == "dose")
    assert dose["value"]["drug"] == "Warfarin"
    assert dose["value"]["as_printed"] == "1 biji sekali sehari waktu malam"
    assert dose["value"]["instruction"] == "1 tablet once a day at night"


# --- the object store --------------------------------------------------------------------


async def test_the_local_store_is_pinned_to_its_region_and_content_addressed(
    tmp_path: Path,
) -> None:
    sg, my = LocalObjectStore(tmp_path, Region.SG), LocalObjectStore(tmp_path, Region.MY)
    key = photo_key(uuid.uuid4(), "a" * 64)
    await sg.put(key, b"bytes")
    assert await sg.get(key) == b"bytes"
    assert sg.path_of(key).is_relative_to(tmp_path / "SG")
    with pytest.raises(NoSuchObject):
        await my.get(key)
    with pytest.raises(NotAStorageKey):
        await sg.get("../escape")
    with pytest.raises(NotAStorageKey):
        await sg.put("", b"")


# --- storing the photo -------------------------------------------------------------------


async def test_a_photo_is_stored_in_the_profiles_region_and_the_row_holds_only_key_and_digest(
    sg: AsyncSession, store: LocalObjectStore
) -> None:
    owner = await _pa(sg)
    data = placeholder_png(LIPID_PANEL)
    photo = await _photo(sg, owner, store)
    assert photo.kind is ArtifactKind.PHOTO
    assert photo.region is Region.SG
    assert photo.sha256 == hashlib.sha256(data).hexdigest()
    assert photo.storage_key == photo_key(owner.profile_id, photo.sha256)
    assert photo.content_type == "image/png"
    assert as_utc(photo.captured_at) == SEPT_3
    assert await store.get(photo.storage_key) == data
    # Nothing of the page is on any column of the row.
    assert not any(
        isinstance(value, bytes) or (isinstance(value, str) and "placeholder" in value)
        for value in vars(photo).values()
    )
    trail = list(await read_audit(sg, context=owner))
    assert (Action.WRITE, Artifact.__tablename__) in {(e.action, e.target) for e in trail}


async def test_a_photo_is_refused_before_a_byte_lands_when_it_is_not_a_photo_or_too_big(
    sg: AsyncSession, store: LocalObjectStore, tmp_path: Path
) -> None:
    owner = await _pa(sg)

    async def attempt(data: bytes, content_type: str) -> None:
        await store_photo(
            sg,
            context=owner,
            store=store,
            data=data,
            content_type=content_type,
            captured_at=SEPT_3,
            source_channel=SourceChannel.APP,
        )

    with pytest.raises(NotAPhoto):
        await attempt(b"%PDF-1.4", "application/pdf")
    with pytest.raises(NotAPhoto):
        await attempt(b"", "image/png")
    with pytest.raises(PhotoTooLarge):
        await attempt(b"x" * (10 * 1024 * 1024 + 1), "image/jpeg")
    # Nothing landed in the store.
    assert not (tmp_path / "SG").exists()
    assert {r[2] for r in _refusals(await read_audit(sg, context=owner))} == {
        "NotAPhoto",
        "PhotoTooLarge",
    }


async def test_a_store_for_the_other_region_is_refused(sg: AsyncSession, tmp_path: Path) -> None:
    owner = await _pa(sg)
    with pytest.raises(OutOfRegion):
        await _photo(sg, owner, LocalObjectStore(tmp_path, Region.MY))
    assert not (tmp_path / "MY").exists()


async def test_a_key_without_the_record_cannot_store_a_photo(
    sg: AsyncSession, store: LocalObjectStore
) -> None:
    owner = await _pa(sg)
    helper = await _let_in(sg, owner, scopes={Scope.MEDICINES})
    with pytest.raises(OutOfScope):
        await _photo(sg, helper, store)
    assert (Action.WRITE, "artifact", "OutOfScope") in _refusals(
        await read_audit(sg, context=owner)
    )


# --- the extractor -----------------------------------------------------------------------


async def test_the_fixture_extractor_answers_by_digest_and_says_unknown_for_a_page_it_cannot_read(
    extractor: FixtureExtractor,
) -> None:
    hints = Hints(language="ms", region=SG)
    lipid = await extractor.extract(placeholder_png(LIPID_PANEL), "image/png", hints)
    assert lipid.document_kind is DocumentKind.LAB_REPORT
    assert lipid.document_date == date(2023, 9, 7)
    assert [f.attribute for f in lipid.fields] == [
        "total_cholesterol",
        "hdl",
        "ldl",
        "triglycerides",
        "vldl",
        "tc_hdl_ratio",
        "non_hdl_cholesterol",
    ]
    assert all(f.span is not None for f in lipid.fields)
    unknown = await extractor.extract(placeholder_png("some-other-page"), "image/png", hints)
    assert unknown == Extraction.nothing()


def test_a_field_is_checked_before_it_reaches_a_card() -> None:
    good = ExtractedField("lipid_panel", "ldl", 152, "mg/dL", 0.7)
    assert good.checked() == good
    with pytest.raises(NotAFieldCode):
        ExtractedField("Lipid Panel", "ldl", 152, None, 0.7).checked()
    with pytest.raises(NotAFieldCode):
        ExtractedField("lipid_panel", "ldl; drop table", 152, None, 0.7).checked()
    with pytest.raises(NotAValue):
        ExtractedField("letter", "text", "x" * 201, None, 0.7).checked()
    with pytest.raises(NotAValue):
        ExtractedField("lipid_panel", "ldl", None, None, 0.7).checked()
    with pytest.raises(NotAValue):
        ExtractedField("lipid_panel", "ldl", object(), None, 0.7).checked()


# --- the review card ---------------------------------------------------------------------


async def test_a_photo_becomes_a_review_card_with_a_confidence_per_field(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor)
    photo = await sg.get(Artifact, card.artifact_id)
    assert card.is_open and card.confirmed_by_person_id is None
    assert card.document_kind is DocumentKind.LAB_REPORT
    assert card.document_date == date(2023, 9, 7)
    assert card.high_risk_class is None
    assert photo is not None and photo.kind is ArtifactKind.PHOTO
    assert [f.position for f in fields] == list(range(7))
    assert all(f.state is FieldState.PROPOSED and f.fact_id is None for f in fields)
    by_attribute = {f.attribute: f for f in fields}
    assert by_attribute["total_cholesterol"].value == 230
    assert by_attribute["total_cholesterol"].unit == "mg/dL"
    assert by_attribute["total_cholesterol"].confidence == 0.97
    # E02-07: below the threshold, dotted.
    assert {f.attribute for f in fields if f.needs_confirm} == {"ldl", "triglycerides"}
    assert all(f.confidence < CONFIDENCE_THRESHOLD for f in fields if f.needs_confirm)
    assert by_attribute["ldl"].span == {"x0": 0.62, "y0": 0.40, "x1": 0.74, "y1": 0.425}
    # Nothing is a fact yet.
    assert list(await current_facts(sg, context=owner)) == []
    assert [c.id for c in await list_review_cards(sg, context=owner)] == [card.id]
    assert (await require_review_card(sg, context=owner, card_id=card.id)).id == card.id


async def test_a_page_the_extractor_cannot_read_is_an_open_card_with_no_fields(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor, label="a-blurry-page")
    assert card.document_kind is DocumentKind.UNKNOWN
    assert card.document_date is None
    assert fields == []


async def test_a_label_card_shows_the_high_risk_class_which_is_not_a_field_to_reject(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor, label=WARFARIN_LABEL)
    assert card.document_kind is DocumentKind.MEDICINE_LABEL
    assert card.high_risk_class == "anticoagulant"
    assert [f.attribute for f in fields] == [
        "name",
        "strength",
        "dose",
        "quantity",
        "dispensed_at",
        "prescriber",
    ]
    assert {f.attribute for f in fields if f.needs_confirm} == {"dose", "prescriber"}


async def test_a_card_and_its_fields_are_read_under_the_record_and_refused_without_it(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, _ = await _card(sg, owner, store, extractor)
    mei = await _let_in(sg, owner, scopes={Scope.RECORDS})
    assert [c.id for c in await list_review_cards(sg, context=mei)] == [card.id]
    assert len(await card_fields(sg, context=mei, card_id=card.id)) == 7
    helper = await _let_in(sg, owner, scopes={Scope.MEDICINES}, phone="+6591110003")
    with pytest.raises(OutOfScope):
        await list_review_cards(sg, context=helper)
    with pytest.raises(OutOfScope):
        await require_review_card(sg, context=helper, card_id=card.id)
    assert (Action.READ, "review_card", "OutOfScope") in _refusals(
        await read_audit(sg, context=owner)
    )


async def test_a_card_is_the_profiles_own(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    pa = await _pa(sg)
    card, _ = await _card(sg, pa, store, extractor)
    other = await _pa(sg, phone="+6591110009")
    with pytest.raises(NoSuchReviewCard):
        await require_review_card(sg, context=other, card_id=card.id)


async def test_a_card_field_is_not_edited_outside_the_review_service(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    _, fields = await _card(sg, owner, store, extractor)
    fields[0].state = FieldState.CONFIRMED
    with pytest.raises(ImmutableRow):
        await sg.flush()
    await sg.rollback()
    fields[0].value = 999
    with pytest.raises(ImmutableRow):
        await sg.flush()
    await sg.rollback()


# --- the confirm -------------------------------------------------------------------------


async def test_one_yes_over_the_card_writes_a_fact_per_kept_field_with_provenance(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    """E02-07: a single tap saves. E02-01: value, unit and date come through to the fact."""
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor)
    before = await current_state(sg, context=owner)
    decisions = _decide(fields, correct={"triglycerides": 54}, reject={"tc_hdl_ratio"})
    yes = await _yes(sg, owner, card, decisions)

    closed, decided, facts = await confirm_review_card(
        sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=yes
    )

    assert not closed.is_open
    assert closed.confirmed_by_person_id == owner.person_id
    assert as_utc(closed.confirmed_at) == SEPT_3
    by_attribute = {f.attribute: f for f in decided}
    assert by_attribute["triglycerides"].state is FieldState.CORRECTED
    assert by_attribute["triglycerides"].value == 64  # the proposal stays beside the correction
    assert by_attribute["triglycerides"].corrected_value == 54
    assert by_attribute["tc_hdl_ratio"].state is FieldState.REJECTED
    assert by_attribute["tc_hdl_ratio"].fact_id is None
    assert by_attribute["ldl"].state is FieldState.CONFIRMED
    assert all(f.decided_at is not None for f in decided)

    assert len(facts) == 6
    held = list(await current_facts(sg, context=owner, subject="lipid_panel"))
    assert {f.id for f in held} == {f.id for f in facts}
    assert {f.attribute: f.value for f in held} == {
        "total_cholesterol": 230,
        "hdl": 73,
        "ldl": 152,
        "triglycerides": 54,
        "vldl": 10.78,
        "non_hdl_cholesterol": 156.3,
    }
    for fact in held:
        assert fact.artifact_id == card.artifact_id
        assert fact.event_id is None
        assert fact.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
        assert fact.confirmed_by_person_id == owner.person_id
        assert fact.unit == "mg/dL"
        assert fact.confidence == 1.0
        # Valid from the day on the paper, on the patient's clock (Singapore, UTC+8).
        assert as_utc(fact.valid_from) == datetime(2023, 9, 6, 16, 0, tzinfo=UTC)
        assert fact.valid_to is None
        assert by_attribute[fact.attribute].fact_id == fact.id

    # State recomputed as each fact landed; the latest snapshot names the last one.
    after = await current_state(sg, context=owner)
    assert after.sequence == before.sequence + 6
    assert after.trigger is StateTrigger.NEW_FACT
    assert after.trigger_fact_id == facts[-1].id
    assert after.stale is False
    clinical = after.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert set(clinical["facts"]["lipid_panel"]) == {f.attribute for f in held}


async def test_the_yes_binds_to_the_decisions_as_shown(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor)
    shown = _decide(fields, correct={"triglycerides": 54})
    yes = await _yes(sg, owner, card, shown)
    changed = _decide(fields, correct={"triglycerides": 45})
    async with refused_unit(sg, NotWhatWasConfirmed):
        await confirm_review_card(
            sg, context=owner, card_id=card.id, decisions=changed, confirmation_id=yes
        )
    assert list(await current_facts(sg, context=owner)) == []
    assert (await require_review_card(sg, context=owner, card_id=card.id)).is_open
    # The yes was not spent by the refusal: the decisions as shown still go through.
    _, _, facts = await confirm_review_card(
        sg, context=owner, card_id=card.id, decisions=shown, confirmation_id=yes
    )
    assert len(facts) == 7
    assert (Action.WRITE, "review_card", "NotWhatWasConfirmed") in _refusals(
        await read_audit(sg, context=owner)
    )


async def test_every_field_needs_one_decision_and_a_correction_says_what_to(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor)
    all_but_one = _decide(fields)[:-1]
    with pytest.raises(NotEveryFieldDecided):
        await review_draft_for(sg, context=owner, card_id=card.id, decisions=all_but_one)
    twice = _decide(fields) + [Decision(fields[0].id, FieldState.CONFIRMED)]
    with pytest.raises(NotEveryFieldDecided):
        await review_draft_for(sg, context=owner, card_id=card.id, decisions=twice)
    stranger = _decide(fields)[:-1] + [Decision(uuid.uuid4(), FieldState.CONFIRMED)]
    with pytest.raises(NoSuchReviewField):
        await review_draft_for(sg, context=owner, card_id=card.id, decisions=stranger)
    without = _decide(fields)[:-1] + [Decision(fields[-1].id, FieldState.CORRECTED)]
    with pytest.raises(NotADecision):
        await review_draft_for(sg, context=owner, card_id=card.id, decisions=without)
    carrying = _decide(fields)[:-1] + [Decision(fields[-1].id, FieldState.REJECTED, 5)]
    with pytest.raises(NotADecision):
        await review_draft_for(sg, context=owner, card_id=card.id, decisions=carrying)
    proposed = _decide(fields)[:-1] + [Decision(fields[-1].id, FieldState.PROPOSED)]
    with pytest.raises(NotADecision):
        await review_draft_for(sg, context=owner, card_id=card.id, decisions=proposed)


async def test_a_card_is_confirmed_once(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor)
    decisions = _decide(fields)
    yes = await _yes(sg, owner, card, decisions)
    await confirm_review_card(
        sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=yes
    )
    with pytest.raises(AlreadyConfirmed):
        await review_draft_for(sg, context=owner, card_id=card.id, decisions=decisions)
    with pytest.raises(AlreadyConfirmed):
        await confirm_review_card(
            sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=yes
        )
    assert len(await current_facts(sg, context=owner, subject="lipid_panel")) == 7
    # The refusal is on the trail: raised while the card was being read for the draft.
    assert {r[1:] for r in _refusals(await read_audit(sg, context=owner))} == {
        ("review_card", "AlreadyConfirmed")
    }


async def test_a_yes_is_the_confirmers_own_and_for_a_review_card(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor)
    decisions = _decide(fields)
    yes = await _yes(sg, owner, card, decisions)
    minted = await sg.get(Confirmation, yes)
    assert minted is not None
    assert minted.subject is ConfirmSubject.REVIEW_CARD
    assert minted.subject_id == card.id
    assert minted.person_id == owner.person_id
    # Mei, holding the record, cannot spend Pa's yes.
    mei = await _let_in(sg, owner, scopes={Scope.RECORDS})
    with pytest.raises(NotAConfirmerHere):
        await confirm_review_card(
            sg, context=mei, card_id=card.id, decisions=decisions, confirmation_id=yes
        )
    # Nor spend a yes minted for something else: a yes for a fact is not a yes for a card.
    with pytest.raises(NotAConfirmerHere):
        await confirm_review_card(
            sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=uuid.uuid4()
        )


async def test_the_label_card_writes_medicine_facts_under_the_medicines_scope(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor, label=WARFARIN_LABEL)
    decisions = _decide(fields, reject={"prescriber"})
    yes = await _yes(sg, owner, card, decisions)
    _, _, facts = await confirm_review_card(
        sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=yes
    )
    assert {f.attribute for f in facts} == {"name", "strength", "dose", "quantity", "dispensed_at"}
    assert all(f.subject == "medicine" for f in facts)
    dose = next(f for f in facts if f.attribute == "dose")
    assert dose.value["drug"] == "Warfarin"
    assert dose.unit == "tablet"
    assert dose.artifact_id == card.artifact_id
    assert as_utc(dose.valid_from) == datetime(2024, 3, 11, 16, 0, tzinfo=UTC)
    # Under MEDICINES: a key to the record alone does not read them; one to medicines does.
    records_only = await _let_in(sg, owner, scopes={Scope.RECORDS})
    with pytest.raises(OutOfScope):
        await current_facts(sg, context=records_only, subject="medicine")
    medicines = await _let_in(sg, owner, scopes={Scope.MEDICINES}, phone="+6591110003")
    assert len(await current_facts(sg, context=medicines, subject="medicine")) == 5


async def test_a_key_to_the_record_alone_cannot_confirm_a_label(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    """The card is the record's; the facts it writes are each held under their own scope."""
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor, label=WARFARIN_LABEL)
    mei = await _let_in(sg, owner, scopes={Scope.RECORDS})
    decisions = _decide(fields)
    yes = await _yes(sg, mei, card, decisions)
    async with refused_unit(sg, OutOfScope):
        await confirm_review_card(
            sg, context=mei, card_id=card.id, decisions=decisions, confirmation_id=yes
        )
    assert (await require_review_card(sg, context=owner, card_id=card.id)).is_open
    assert list(await current_facts(sg, context=owner, subject="medicine")) == []


async def test_a_card_from_a_direct_extraction_still_checks_its_fields(
    sg: AsyncSession, store: LocalObjectStore
) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner, store)
    with pytest.raises(NotAValue):
        await card_from(
            sg,
            context=owner,
            artifact=photo,
            extraction=Extraction(
                DocumentKind.DISCHARGE_LETTER,
                (ExtractedField("letter", "body", "the whole letter " * 20, None, 0.9),),
            ),
        )


async def test_the_confirm_is_on_the_trail_as_writes_to_the_card_its_fields_and_the_facts(
    sg: AsyncSession, store: LocalObjectStore, extractor: FixtureExtractor
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(sg, owner, store, extractor)
    decisions = _decide(fields, reject={"vldl"})
    yes = await _yes(sg, owner, card, decisions)
    await confirm_review_card(
        sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=yes
    )
    trail: list[AuditEntry] = list(await read_audit(sg, context=owner, action=Action.WRITE))
    written = [(e.target, e.target_id) for e in trail if e.outcome is Outcome.ALLOWED]
    assert (ReviewCard.__tablename__, card.id) in written
    assert {tid for t, tid in written if t == ReviewField.__tablename__} >= {f.id for f in fields}
    assert sum(1 for t, _ in written if t == "fact") == 6
    # The card, its fields and every yes are the record's.
    assert {
        e.scope
        for e in trail
        if e.target in {ReviewCard.__tablename__, ReviewField.__tablename__, "confirmation"}
    } == {Scope.RECORDS}
