"""E12-09: LPA and consent document storage.

    Documents attached to the grant record.

A document is kept by reference, tagged, in the region; the list says what each backs; the
evidence a graph was set up on is the same artefact when its bytes arrive later.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.consent.models import ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import grant_consent
from app.family.common import NotAChief
from app.family.documents import NotADocument, add_document, documents
from app.family.models import DocumentTag
from app.identity.doors import Evidence, set_up_for_someone
from app.identity.service import register_person
from app.ingestion.objects import LocalObjectStore, sha256_of
from app.keys.context import resolve_key_context
from app.memory.models import ArtifactKind
from app.regions import OutOfRegion, Region
from tests.family_support import MONDAY, household
from tests.support import OPENING_CONSENT

LPA = b"%PDF-1.4\n% a lasting power of attorney, redacted placeholder\n"
CAPTURED = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


async def test_an_uploaded_pdf_is_kept_by_reference_tagged_and_in_the_region(
    sg: AsyncSession, clock: FrozenClock, tmp_path: Path
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    store = LocalObjectStore(tmp_path, Region.SG)
    row = await add_document(
        sg,
        context=mei,
        store=store,
        data=LPA,
        content_type="application/pdf",
        tag=DocumentTag.LPA,
        captured_at=CAPTURED,
    )
    listed = await documents(sg, context=mei)
    assert len(listed) == 1
    view = listed[0]
    assert view.artifact.id == row.artifact_id and view.artifact.kind is ArtifactKind.PDF
    assert view.artifact.sha256 == sha256_of(LPA) and view.artifact.region is Region.SG
    assert view.tag is DocumentTag.LPA and view.added_by_person_id == h.mei.id
    assert view.backs == []
    assert await store.get(view.artifact.storage_key) == LPA
    assert view.artifact.storage_key.startswith(f"documents/{h.profile.id}/")

    # Cited as the basis of a consent the chief gives for him: the list says what it backs.
    await grant_consent(
        sg,
        context=mei,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.APP,
        basis=ConsentBasis.LPA,
        language="en",
        basis_artifact_id=view.artifact.id,
    )
    backed = (await documents(sg, context=mei))[0]
    assert [(b.kind, b.basis, b.purpose, b.active) for b in backed.backs] == [
        ("consent", ConsentBasis.LPA, ConsentPurpose.RECORDING.value, True)
    ]


async def test_the_evidence_a_graph_was_set_up_on_is_the_same_document_when_its_bytes_arrive(
    sg: AsyncSession, clock: FrozenClock, tmp_path: Path
) -> None:
    clock.set(MONDAY)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6592220002")
    digest = sha256_of(LPA)
    profile, stewardship = await set_up_for_someone(
        sg,
        region=Region.SG,
        steward=mei,
        patient_phone_e164="+6591110001",
        display_name="Pa",
        language="ms",
        consent=OPENING_CONSENT,
        basis=ConsentBasis.LPA,
        relationship="daughter",
        evidence=Evidence(
            kind=ArtifactKind.PDF,
            storage_key=f"documents/{digest}",
            content_type="application/pdf",
            sha256=digest,
            captured_at=CAPTURED,
        ),
    )
    steward = await resolve_key_context(
        sg, region=Region.SG, person_id=mei.id, profile_id=profile.id
    )
    before = await documents(sg, context=steward)
    assert len(before) == 1 and before[0].tag is DocumentTag.LPA, "tagged from the basis"
    assert {(b.kind, b.basis) for b in before[0].backs} == {
        ("consent", ConsentBasis.LPA),
        ("stewardship", ConsentBasis.LPA),
    }
    assert before[0].added_by_person_id is None

    store = LocalObjectStore(tmp_path, Region.SG)
    row = await add_document(
        sg,
        context=steward,
        store=store,
        data=LPA,
        content_type="application/pdf",
        tag=DocumentTag.LPA,
        captured_at=CAPTURED,
    )
    after = await documents(sg, context=steward)
    assert len(after) == 1, "one paper, one artefact"
    assert row.artifact_id == before[0].artifact.id
    assert after[0].added_by_person_id == mei.id
    assert await store.get(f"documents/{digest}") == LPA
    assert any(b.kind == "stewardship" and b.id == stewardship.id for b in after[0].backs)


async def test_only_a_pdf_or_a_photo_only_a_chief_only_in_the_region(
    sg: AsyncSession, clock: FrozenClock, tmp_path: Path
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    store = LocalObjectStore(tmp_path, Region.SG)
    with pytest.raises(NotADocument):
        await add_document(
            sg,
            context=mei,
            store=store,
            data=b"hello",
            content_type="text/plain",
            tag=DocumentTag.CONSENT_FORM,
            captured_at=CAPTURED,
        )
    with pytest.raises(NotADocument):
        await add_document(
            sg,
            context=mei,
            store=store,
            data=b"",
            content_type="application/pdf",
            tag=DocumentTag.CONSENT_FORM,
            captured_at=CAPTURED,
        )
    kit = await h.ctx(sg, h.kit)
    with pytest.raises(NotAChief):
        await add_document(
            sg,
            context=kit,
            store=store,
            data=LPA,
            content_type="application/pdf",
            tag=DocumentTag.LPA,
            captured_at=CAPTURED,
        )
    with pytest.raises(NotAChief):
        await documents(sg, context=kit)
    with pytest.raises(OutOfRegion):
        await add_document(
            sg,
            context=mei,
            store=LocalObjectStore(tmp_path, Region.MY),
            data=LPA,
            content_type="application/pdf",
            tag=DocumentTag.LPA,
            captured_at=CAPTURED,
        )
    assert await documents(sg, context=mei) == []
    pa = await h.ctx(sg, h.pa)
    names = {
        e.refused_because for e in await read_audit(sg, context=pa) if e.outcome is Outcome.REFUSED
    }
    assert {"NotADocument", "NotAChief", "OutOfRegion"} <= names
