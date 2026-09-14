"""E00-03 acceptance.

    Every semantic fact links to at least one artefact and a confidence.

The first test is the Session 2 line from TASKS.md: a Fact without provenance is rejected.
The rest are the same clause read the other way: the provenance is a real artefact or event
on this profile, the confidence is a number between nought and one with a state, and recall
from a fact leads back to the thing it came from.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, resolve_key_context
from app.memory.episodic import record_event, store_artifact
from app.memory.models import (
    ArtifactKind,
    ConfidenceState,
    EventKind,
    Fact,
    SourceChannel,
)
from app.memory.semantic import NoProvenance, NoSuchProvenance, NotAConfidence, assert_fact
from app.regions import Region

MORNING = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
SHA = "a" * 64


async def _pa(session: AsyncSession) -> KeyContext:
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    profile = await create_own_profile(session, region=Region.SG, owner=pa)
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


async def test_a_fact_without_provenance_is_rejected(sg: AsyncSession) -> None:
    owner = await _pa(sg)

    with pytest.raises(NoProvenance):
        await assert_fact(
            sg,
            context=owner,
            subject="blood_pressure",
            attribute="systolic",
            value=138,
            unit="mmHg",
            confidence=0.9,
        )

    # The table refuses it too, so no path that skips the service can slip one in.
    sg.add(
        Fact(
            profile_id=owner.profile_id,
            subject="blood_pressure",
            attribute="systolic",
            value=138,
            confidence=0.9,
            confidence_state=ConfidenceState.EXTRACTED,
            valid_from=MORNING,
        )
    )
    with pytest.raises(IntegrityError):
        await sg.flush()
    await sg.rollback()


async def test_the_provenance_must_be_a_real_artefact_or_event_on_this_profile(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    with pytest.raises(NoSuchProvenance):
        await assert_fact(
            sg,
            context=owner,
            subject="blood_pressure",
            attribute="systolic",
            value=138,
            confidence=0.9,
            artifact_id=uuid.uuid4(),
        )
    with pytest.raises(NoSuchProvenance):
        await assert_fact(
            sg,
            context=owner,
            subject="blood_pressure",
            attribute="systolic",
            value=138,
            confidence=0.9,
            event_id=uuid.uuid4(),
        )


async def test_every_fact_carries_a_confidence_between_nought_and_one(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    photo = await store_artifact(
        sg,
        context=owner,
        kind=ArtifactKind.PHOTO,
        storage_key="sg/profiles/pa/2026-09-03/bp-book.jpg",
        content_type="image/jpeg",
        sha256=SHA,
        captured_at=MORNING,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )

    for out_of_range in (-0.1, 1.2):
        with pytest.raises(NotAConfidence):
            await assert_fact(
                sg,
                context=owner,
                subject="blood_pressure",
                attribute="systolic",
                value=138,
                confidence=out_of_range,
                artifact_id=photo.id,
            )

    fact = await assert_fact(
        sg,
        context=owner,
        subject="blood_pressure",
        attribute="systolic",
        value=138,
        unit="mmHg",
        confidence=0.8,
        artifact_id=photo.id,
    )
    assert fact.confidence == 0.8
    assert fact.confidence_state is ConfidenceState.EXTRACTED


async def test_a_fact_links_to_the_artefact_or_the_event_it_came_from(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    photo = await store_artifact(
        sg,
        context=owner,
        kind=ArtifactKind.PHOTO,
        storage_key="sg/profiles/pa/2026-09-03/bp-book.jpg",
        content_type="image/jpeg",
        sha256=SHA,
        captured_at=MORNING,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )
    reading = await record_event(
        sg,
        context=owner,
        kind=EventKind.READING,
        occurred_at=MORNING,
        label="blood pressure, morning",
        artifact_id=photo.id,
    )

    from_photo = await assert_fact(
        sg,
        context=owner,
        subject="blood_pressure",
        attribute="systolic",
        value=138,
        unit="mmHg",
        confidence=0.8,
        artifact_id=photo.id,
    )
    from_reading = await assert_fact(
        sg,
        context=owner,
        subject="blood_pressure",
        attribute="diastolic",
        value=84,
        unit="mmHg",
        confidence=0.8,
        event_id=reading.id,
    )

    # Recall returns the artefact: from either fact there is a path back to the photo.
    assert from_photo.artifact_id == photo.id
    assert from_reading.event_id == reading.id and reading.artifact_id == photo.id
    assert photo.storage_key.endswith("bp-book.jpg")
