"""E02-03: PDF import from portals, email and shares.

Acceptance line: multi-page PDFs parsed into events with dates. A two-page hospital letter is
read page by page — every field says its page — and confirming it records the discharge on
the date on the letter, which every fact it writes names. A PDF that is not a health paper is
an open card with no fields that says so. What is not a PDF, or is too big, is refused before
a byte lands, and the refusal is on the trail. `/documents` stays the family's (E12-09).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.strings import NOT_A_HEALTH_PAPER
from app.ingestion.documents import MAX_PDF_BYTES, NotAPdf, PdfTooLarge, store_pdf
from app.ingestion.objects import LocalObjectStore, sha256_of
from app.memory.models import ArtifactKind
from app.regions import OutOfRegion, Region
from tests.api import bearer, own_profile, register_by_phone
from tests.capture_support import b64, confirm, decide, pdf, refusals
from tests.conftest import Deployment
from tests.paper import DISCHARGE_LETTER, RECEIPT, placeholder_pdf
from tests.test_ingestion import _pa

PA = "+6591190001"
WHEN = datetime(2026, 9, 1, tzinfo=UTC)


async def _pa_http(deployment: Deployment) -> tuple[dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, "Pa")
    return pa, await own_profile(deployment, pa, language="en")


async def test_a_two_page_hospital_letter_is_read_page_by_page_into_a_dated_event(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa_http(deployment)
    his = bearer(pa["token"])
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/imports",
        json=pdf(DISCHARGE_LETTER, source="portal", hint="discharge_letter"),
        headers=his,
    )
    assert posted.status_code == 201, posted.text
    card = posted.json()
    assert card["document_kind"] == "discharge_letter" and card["document_date"] == "2026-08-20"
    assert card["source"] == "portal" and card["asked_as"] == "discharge_letter"
    assert card["notice"] is None
    pages = [(f["attribute"], f["page"]) for f in card["fields"]]
    assert pages == [
        ("admitted_on", 1),
        ("discharged_on", 1),
        ("reason", 1),
        ("weight_at_discharge", 2),
        ("next_visit", 2),
        ("doctor", 2),
    ]
    assert all(f["span"]["page"] == f["page"] for f in card["fields"])
    # The bytes are a PDF artefact in the region's store, under the import key.
    digest = sha256_of(placeholder_pdf(DISCHARGE_LETTER))
    assert deployment.objects.path_of(f"imports/{profile_id}/{digest}").is_file()

    done = await confirm(deployment, pa["token"], profile_id, card, decide(card))
    assert done.status_code == 200, done.text
    result = done.json()
    assert len(result["facts"]) == 6 and result["event_id"] is not None
    for fact in result["facts"]:
        assert fact["artifact_id"] == card["artifact_id"]
        assert fact["event_id"] == result["event_id"]
        assert fact["valid_from"].startswith("2026-08-19T16:00:00")
        assert fact["confidence_state"] == "confirmed_by_person"
    by = {f["attribute"]: f for f in result["facts"]}
    assert by["weight_at_discharge"]["value"] == 68.5 and by["weight_at_discharge"]["unit"] == "kg"
    # The discharge is an event on the record: State reads it as the month after a discharge.
    state = await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)
    assert state.status_code == 200, state.text
    assert "after_discharge" in state.text


async def test_a_pdf_that_is_not_a_health_paper_is_an_open_card_that_says_so(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa_http(deployment)
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/imports",
        json=pdf(RECEIPT, source="email"),
        headers=bearer(pa["token"]),
    )
    assert posted.status_code == 201, posted.text
    card = posted.json()
    assert card["document_kind"] == "not_health" and card["fields"] == []
    assert card["confirmed_at"] is None and card["source"] == "email"
    assert card["notice"] == list(NOT_A_HEALTH_PAPER)
    assert card["notice"] == ["This does not look like a health paper."]
    facts = await deployment.client.get(
        f"/profiles/{profile_id}/facts", headers=bearer(pa["token"])
    )
    assert facts.json() == []


async def test_what_is_not_a_pdf_is_refused_before_a_byte_lands_and_is_on_the_trail(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa_http(deployment)
    his = bearer(pa["token"])
    as_photo = {**pdf(DISCHARGE_LETTER), "content_type": "image/png"}
    refused = await deployment.client.post(
        f"/profiles/{profile_id}/imports", json=as_photo, headers=his
    )
    assert refused.status_code == 400 and refused.json() == {"refusal": "NotAPdf"}
    pretending = {**pdf(DISCHARGE_LETTER), "data": b64(b"hello, not a pdf")}
    refused = await deployment.client.post(
        f"/profiles/{profile_id}/imports", json=pretending, headers=his
    )
    assert refused.status_code == 400 and refused.json() == {"refusal": "NotAPdf"}
    assert not list(deployment.objects.path_of(f"imports/{profile_id}/x").parent.parent.glob("*/*"))
    assert "NotAPdf" in await refusals(deployment, pa, profile_id)
    unknown_hint = {**pdf(DISCHARGE_LETTER), "document_kind": "device_screen"}
    assert (
        await deployment.client.post(
            f"/profiles/{profile_id}/imports", json=unknown_hint, headers=his
        )
    ).status_code == 422
    unknown_source = {**pdf(DISCHARGE_LETTER), "source": "fax"}
    assert (
        await deployment.client.post(
            f"/profiles/{profile_id}/imports", json=unknown_source, headers=his
        )
    ).status_code == 422


async def test_a_pdf_too_big_is_refused_and_one_for_another_region_never_lands(
    sg: AsyncSession, tmp_path: Path
) -> None:
    owner = await _pa(sg)
    here = LocalObjectStore(tmp_path, Region.SG)
    with pytest.raises(PdfTooLarge):
        await store_pdf(
            sg,
            context=owner,
            store=here,
            data=b"%PDF-1.4\n" + b"0" * MAX_PDF_BYTES,
            content_type="application/pdf",
            captured_at=WHEN,
        )
    with pytest.raises(NotAPdf):
        await store_pdf(
            sg,
            context=owner,
            store=here,
            data=b"",
            content_type="application/pdf",
            captured_at=WHEN,
        )
    across = LocalObjectStore(tmp_path, Region.MY)
    with pytest.raises(OutOfRegion):
        await store_pdf(
            sg,
            context=owner,
            store=across,
            data=placeholder_pdf(DISCHARGE_LETTER),
            content_type="application/pdf",
            captured_at=WHEN,
        )
    assert not any(tmp_path.rglob("*.partial")) and not (tmp_path / "MY").exists()
    kept = await store_pdf(
        sg,
        context=owner,
        store=here,
        data=placeholder_pdf(DISCHARGE_LETTER),
        content_type="application/pdf; charset=binary",
        captured_at=WHEN,
    )
    assert kept.kind is ArtifactKind.PDF and kept.content_type == "application/pdf"
    assert kept.storage_key.startswith(f"imports/{owner.profile_id}/")


async def test_the_familys_documents_route_is_left_as_it_was(deployment: Deployment) -> None:
    """E12-09 keeps `/documents` for a paper behind a basis; a PDF to be read is an import."""
    pa, profile_id = await _pa_http(deployment)
    listed = await deployment.client.get(
        f"/profiles/{profile_id}/documents", headers=bearer(pa["token"])
    )
    assert listed.status_code == 200 and listed.json() == []
