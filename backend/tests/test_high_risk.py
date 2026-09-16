"""The label-photo rule for a high-risk drug (E16-04), as a hook under the memory store.

    High-risk drugs (warfarin, insulin, digoxin, methotrexate, opioids) require the label
    photo before the dose is saved; a verbal report is not enough.

The rule lives in `app/safety/high_risk.py` and is registered on `before_fact_write` by
importing it, so it holds for every writer. No API route can express a medicine dose from
anything but a photo card, so the refusal is proven here, at the service.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, resolve_key_context
from app.memory import semantic
from app.memory.episodic import record_event, store_artifact
from app.memory.models import Artifact, ArtifactKind, EventKind, SourceChannel
from app.memory.semantic import assert_fact, current_facts
from app.regions import Region
from app.safety.high_risk import (
    HIGH_RISK_CLASSES,
    HighRiskNeedsLabelPhoto,
    high_risk_class,
    names_high_risk,
    refuse_dose_without_label_photo,
)
from tests.support import OPENING_CONSENT, refused_unit

SEPT_3 = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)


async def _pa(session: AsyncSession) -> KeyContext:
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    profile = await create_own_profile(session, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


async def _artifact(session: AsyncSession, context: KeyContext, kind: ArtifactKind) -> Artifact:
    return await store_artifact(
        session,
        context=context,
        kind=kind,
        storage_key=f"sg/{kind.value}",
        content_type="image/jpeg" if kind is ArtifactKind.PHOTO else "application/pdf",
        sha256="d" * 64,
        captured_at=SEPT_3,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )


async def _dose(
    session: AsyncSession,
    context: KeyContext,
    drug: str,
    *,
    artifact_id: object = None,
    event_id: object = None,
    subject: str = "medicine",
) -> None:
    await assert_fact(
        session,
        context=context,
        subject=subject,
        attribute="dose",
        value={"drug": drug, "instruction": "1 tablet once a day"},
        unit="tablet",
        confidence=0.9,
        artifact_id=artifact_id,  # type: ignore[arg-type]
        event_id=event_id,  # type: ignore[arg-type]
    )


def test_the_table_is_the_five_classes_of_the_medications_module() -> None:
    assert set(HIGH_RISK_CLASSES) == {
        "anticoagulant",
        "insulin",
        "cardiac_glycoside",
        "antimetabolite",
        "opioid",
    }
    assert high_risk_class("Warfarin") == "anticoagulant"
    assert high_risk_class("warfarin 5 mg tablet") == "anticoagulant"
    assert high_risk_class("Insulin Glargine (Lantus)") == "insulin"
    assert high_risk_class("DIGOXIN") == "cardiac_glycoside"
    assert high_risk_class("methotrexate") == "antimetabolite"
    assert high_risk_class("Tramadol 50 mg") == "opioid"
    assert high_risk_class("amlodipine") is None
    assert high_risk_class("") is None
    assert high_risk_class(None) is None
    # Whole words: a name that merely contains one is not it.
    assert high_risk_class("codeinex") is None
    assert names_high_risk("medicine", {"drug": "Warfarin", "instruction": "1 biji"}) == (
        "anticoagulant"
    )
    assert names_high_risk("medicine", 5) is None
    assert names_high_risk("medicine:digoxin", 0.125) == "cardiac_glycoside"


def test_the_rule_is_registered_on_the_memory_store() -> None:
    assert refuse_dose_without_label_photo in semantic.before_fact_write
    assert semantic.before_fact_write.count(refuse_dose_without_label_photo) == 1


async def test_a_high_risk_dose_from_a_message_alone_is_refused_and_written_down(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    told = await record_event(
        sg,
        context=owner,
        kind=EventKind.MESSAGE,
        occurred_at=SEPT_3,
        source_channel=SourceChannel.WHATSAPP,
        label="the helper says one at night",
    )
    async with refused_unit(sg, HighRiskNeedsLabelPhoto):
        await _dose(sg, owner, "Warfarin", event_id=told.id)
    assert list(await current_facts(sg, context=owner, subject="medicine")) == []
    trail = await read_audit(sg, context=owner)
    assert any(
        e.outcome is Outcome.REFUSED
        and e.action is Action.WRITE
        and e.target == "fact"
        and e.refused_because == "HighRiskNeedsLabelPhoto"
        for e in trail
    )


async def test_a_high_risk_dose_from_a_pdf_or_a_screenshot_is_refused_too(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    letter = await _artifact(sg, owner, ArtifactKind.PDF)
    with pytest.raises(HighRiskNeedsLabelPhoto):
        await _dose(sg, owner, "insulin glargine", artifact_id=letter.id)
    screen = await _artifact(sg, owner, ArtifactKind.SCREENSHOT)
    with pytest.raises(HighRiskNeedsLabelPhoto):
        await _dose(sg, owner, "digoxin", artifact_id=screen.id)
    assert list(await current_facts(sg, context=owner, subject="medicine")) == []


async def test_a_high_risk_dose_from_a_label_photo_is_saved(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    label = await _artifact(sg, owner, ArtifactKind.PHOTO)
    await _dose(sg, owner, "Warfarin", artifact_id=label.id)
    await _dose(sg, owner, "methotrexate", artifact_id=label.id, subject="medication")
    held = await current_facts(sg, context=owner)
    assert {f.value["drug"] for f in held} == {"Warfarin", "methotrexate"}
    assert all(f.artifact_id == label.id for f in held)


async def test_a_dose_of_any_other_drug_is_saved_from_words(sg: AsyncSession) -> None:
    """The rule is for the five classes. Amlodipine from a message is the store's business."""
    owner = await _pa(sg)
    told = await record_event(
        sg,
        context=owner,
        kind=EventKind.MESSAGE,
        occurred_at=SEPT_3,
        source_channel=SourceChannel.WHATSAPP,
        label="the helper says one in the morning",
    )
    await _dose(sg, owner, "Amlodipine", event_id=told.id)
    assert [
        f.value["drug"] for f in await current_facts(sg, context=owner, subject="medicine")
    ] == ["Amlodipine"]


async def test_the_drug_may_be_named_in_the_subject(sg: AsyncSession) -> None:
    """E04 may write a dose under a per-drug subject; the rule reads the subject as well."""
    owner = await _pa(sg)
    told = await record_event(
        sg,
        context=owner,
        kind=EventKind.MESSAGE,
        occurred_at=SEPT_3,
        source_channel=SourceChannel.WHATSAPP,
        label="a voice note",
    )
    with pytest.raises(HighRiskNeedsLabelPhoto):
        await assert_fact(
            sg,
            context=owner,
            subject="medication",
            attribute="dose",
            value="warfarin, half a tablet",
            confidence=0.7,
            event_id=told.id,
        )


async def test_a_dose_is_a_dose_whatever_its_subject_code(sg: AsyncSession) -> None:
    """E05 review B4: `subject="warfarin", attribute="dose"` is guarded like `medicine.dose`.
    The rule keys on the attribute; the drug is read from the subject and the value."""
    context = await _pa(sg)
    told = await record_event(
        sg,
        context=context,
        kind=EventKind.MESSAGE,
        occurred_at=SEPT_3,
        label="voice note",
        source_channel=SourceChannel.WHATSAPP,
    )
    async with refused_unit(sg, HighRiskNeedsLabelPhoto):
        await assert_fact(
            sg,
            context=context,
            subject="warfarin",
            attribute="dose",
            value={"amount": "5 mg"},
            confidence=0.9,
            event_id=told.id,
        )
    async with refused_unit(sg, HighRiskNeedsLabelPhoto):
        await assert_fact(
            sg,
            context=context,
            subject="heart",
            attribute="amount",
            value="digoxin, one tablet",
            confidence=0.9,
            event_id=told.id,
        )
    assert await current_facts(sg, context=context) == []


def test_a_code_is_read_as_words_before_the_drug_is_looked_for() -> None:
    """Review 2, #4: an underscore is a word character; a code is exactly where a drug hides."""
    from app.safety.high_risk import as_words

    assert as_words("warfarin_level") == "warfarin level"
    assert as_words("insulinGlargine.dose") == "insulin Glargine dose"
    assert high_risk_class("warfarin_level") == "anticoagulant"
    assert high_risk_class("digoxin-level") == "cardiac_glycoside"
    assert names_high_risk({"code": "methotrexate_weekly"}) == "antimetabolite"
    assert high_risk_class("paracetamol_level") is None


async def test_a_count_of_a_high_risk_medicine_rests_on_a_photo_under_the_store(
    sg: AsyncSession,
) -> None:
    """Review #140, note 3: `count:<generic>` (tablets found at home) is not a dose, but a
    typed count that is too high puts off a warfarin reorder. The rule under the store holds
    it to a photo as the medicines' door does, whoever writes it; any other count is free."""
    context = await _pa(sg)
    told = await record_event(
        sg,
        context=context,
        kind=EventKind.MESSAGE,
        occurred_at=SEPT_3,
        label="more at home",
        source_channel=SourceChannel.APP,
    )
    for value in (
        {"generic": "warfarin", "quantity": 14},
        {"generic": "rx-0001", "quantity": 14, "drug_class": "anticoagulant"},
        {"generic": "rx-0002", "quantity": 14, "high_risk": True},
    ):
        async with refused_unit(sg, HighRiskNeedsLabelPhoto):
            await assert_fact(
                sg,
                context=context,
                subject="medication",
                attribute=f"count:{value['generic']}",
                value=value,
                confidence=0.9,
                event_id=told.id,
            )
    pdf = await _artifact(sg, context, ArtifactKind.PDF)
    async with refused_unit(sg, HighRiskNeedsLabelPhoto):
        await assert_fact(
            sg,
            context=context,
            subject="medication",
            attribute="count:warfarin",
            value={"generic": "warfarin", "quantity": 14},
            confidence=0.9,
            artifact_id=pdf.id,
        )
    assert await current_facts(sg, context=context) == []

    photo = await _artifact(sg, context, ArtifactKind.PHOTO)
    await assert_fact(
        sg,
        context=context,
        subject="medication",
        attribute="count:warfarin",
        value={"generic": "warfarin", "quantity": 14},
        confidence=0.9,
        artifact_id=photo.id,
    )
    await assert_fact(
        sg,
        context=context,
        subject="medication",
        attribute="count:amlodipine",
        value={"generic": "amlodipine", "quantity": 20, "high_risk": False},
        confidence=0.9,
        event_id=told.id,
    )
    assert len(await current_facts(sg, context=context)) == 2


async def test_a_counts_own_attribute_names_the_drug_too(sg: AsyncSession) -> None:
    """#166 review: `count:<generic>` is where a count correction's drug name lives by
    construction — `app.medicines.reorder.found_more` also echoes `drug_class`/`high_risk`
    into the value, but the rule must not depend on a writer remembering to. A bare value
    with no `generic`, `drug_class` or `high_risk` key is still held to the photo, read off
    the attribute alone."""
    context = await _pa(sg)
    told = await record_event(
        sg,
        context=context,
        kind=EventKind.MESSAGE,
        occurred_at=SEPT_3,
        label="more at home",
        source_channel=SourceChannel.APP,
    )
    async with refused_unit(sg, HighRiskNeedsLabelPhoto):
        await assert_fact(
            sg,
            context=context,
            subject="medication",
            attribute="count:warfarin",
            value={"quantity": 14},
            confidence=0.9,
            event_id=told.id,
        )
    assert await current_facts(sg, context=context) == []

    photo = await _artifact(sg, context, ArtifactKind.PHOTO)
    await assert_fact(
        sg,
        context=context,
        subject="medication",
        attribute="count:warfarin",
        value={"quantity": 14},
        confidence=0.9,
        artifact_id=photo.id,
    )
    assert len(await current_facts(sg, context=context)) == 1
