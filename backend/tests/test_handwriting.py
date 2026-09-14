"""E02-02: handwriting — clinic slips and prescriptions written by hand.

Acceptance line: drug, dose and frequency read from handwritten slips with confidence shown.
A field the recogniser could not read has no value and is never confirmed as read: the card
shows "Nura could not read this. Please type it.", someone types it — here the daughter,
before her father says yes — and the field names who did.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.strings import COULD_NOT_READ
from app.clock import FrozenClock
from app.ingestion.extract import (
    DocumentKind,
    ExtractedField,
    Extraction,
    FixtureExtractor,
    Hints,
    NotAValue,
)
from app.ingestion.objects import LocalObjectStore
from app.ingestion.photos import store_photo
from app.ingestion.review import card_fields, review_photo
from app.memory.models import SourceChannel
from app.regions import Region
from tests.api import bearer, own_profile, register_by_phone
from tests.capture_support import confirm, decide, key_for, mint, photo, refusals
from tests.conftest import Deployment
from tests.paper import CLINIC_SLIP, HANDWRITTEN_PRESCRIPTION, PAPER, placeholder_png
from tests.test_ingestion import _pa

PA = "+6591180001"
MEI = "+6591180002"
AFTER_THE_SLIP = datetime(2026, 9, 14, 4, 0, tzinfo=UTC)
TYPED = "once a day in the morning"


async def _family(deployment: Deployment, scopes: list[str] | None = None) -> tuple[dict[str, str], dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    mei = await register_by_phone(deployment, MEI, "Mei")
    await key_for(deployment, pa, profile_id, MEI, scopes or ["records", "readings"])
    return pa, mei, profile_id


async def _slip(deployment: Deployment, pa: dict[str, str], profile_id: str) -> dict[str, object]:
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos",
        json=photo(CLINIC_SLIP, hint="clinic_slip"),
        headers=bearer(pa["token"]),
    )
    assert posted.status_code == 201, posted.text
    card: dict[str, object] = posted.json()
    return card


def _field(card: dict[str, object], attribute: str) -> dict[str, object]:
    fields = card["fields"]
    assert isinstance(fields, list)
    return next(f for f in fields if f["attribute"] == attribute)


async def test_a_clinic_slip_is_read_with_confidence_and_asks_for_the_field_it_could_not_read(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(AFTER_THE_SLIP)
    pa, _, profile_id = await _family(deployment)
    card = await _slip(deployment, pa, profile_id)
    assert card["document_kind"] == "clinic_slip" and card["asked_as"] == "clinic_slip"
    assert card["document_date"] == "2026-09-10" and card["notice"] is None
    frequency = _field(card, "frequency")
    assert frequency["unreadable"] is True and frequency["value"] is None
    assert frequency["prompt"] == list(COULD_NOT_READ)
    assert frequency["prompt"] == ["Nura could not read this.", "Please type it."]
    assert frequency["needs_confirm"] is True and frequency["confidence"] == 0.12
    name = _field(card, "name")
    assert name["value"] == "Amlodipine" and name["confidence"] == 0.86
    assert name["unreadable"] is False and name["prompt"] is None
    dose = _field(card, "dose")
    assert dose["value"]["as_written"] == "1 tab" and dose["confidence"] == 0.81
    assert _field(card, "next_visit")["needs_confirm"] is True


async def test_a_handwritten_prescription_reads_drug_dose_and_frequency_with_confidence(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos",
        json=photo(HANDWRITTEN_PRESCRIPTION, hint="handwritten_prescription"),
        headers=bearer(pa["token"]),
    )
    assert posted.status_code == 201, posted.text
    card = posted.json()
    assert card["document_kind"] == "handwritten_prescription"
    read = {f["attribute"]: (f["value"], f["confidence"], f["needs_confirm"]) for f in card["fields"]}
    assert read["name"] == ("Metformin", 0.9, False)
    assert read["dose"][0]["instruction"] == "1 tablet" and read["dose"][1:] == (0.79, True)
    assert read["frequency"] == ("twice a day after meals", 0.76, True)
    assert all(f["prompt"] is None for f in card["fields"])


async def test_a_field_nura_could_not_read_is_never_confirmed_as_read(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(AFTER_THE_SLIP)
    pa, _, profile_id = await _family(deployment)
    card = await _slip(deployment, pa, profile_id)
    refused = await mint(deployment, pa["token"], profile_id, card, decide(card))
    assert refused.status_code == 400
    assert refused.json() == {"refusal": "UnreadableField"}
    assert "UnreadableField" in await refusals(deployment, pa, profile_id)
    # Rejecting it is always open: the rest of the slip is kept, the frequency writes nothing.
    done = await confirm(deployment, pa["token"], profile_id, card, decide(card, reject={"frequency"}))
    assert done.status_code == 200, done.text
    assert "frequency" not in {f["attribute"] for f in done.json()["facts"]}


async def test_mei_types_what_nura_could_not_read_and_pa_confirms_it(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(AFTER_THE_SLIP)
    pa, mei, profile_id = await _family(deployment)
    card = await _slip(deployment, pa, profile_id)
    frequency = _field(card, "frequency")
    typed = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/fields/{frequency['field_id']}/type",
        json={"value": TYPED},
        headers=bearer(mei["token"]),
    )
    assert typed.status_code == 200, typed.text
    now = _field(typed.json(), "frequency")
    assert now["corrected_value"] == TYPED and now["value"] is None
    assert now["corrected_by_person_id"] == mei["person_id"]
    assert now["state"] == "proposed" and now["prompt"] is None
    # Nothing is a fact until Pa says yes.
    none = await deployment.client.get(
        f"/profiles/{profile_id}/facts", params={"subject": "medicine"}, headers=bearer(pa["token"])
    )
    assert none.json() == []

    done = await confirm(deployment, pa["token"], profile_id, typed.json(), decide(typed.json()))
    assert done.status_code == 200, done.text
    result = done.json()
    field = _field(result["card"], "frequency")
    assert field["state"] == "corrected" and field["corrected_by_person_id"] == mei["person_id"]
    assert result["card"]["confirmed_by_person_id"] == pa["person_id"]
    facts = {f["attribute"]: f for f in result["facts"]}
    assert facts["frequency"]["value"] == TYPED
    assert facts["frequency"]["confirmed_by_person_id"] == pa["person_id"]
    assert facts["frequency"]["artifact_id"] == card["artifact_id"]
    # A clinic slip records a visit: the event on the date on the slip, which every fact names.
    assert result["event_id"] is not None
    assert {f["event_id"] for f in result["facts"]} == {result["event_id"]}
    assert all(f["valid_from"].startswith("2026-09-09T16:00:00") for f in result["facts"])

    # A closed card takes no more typing.
    again = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/fields/{frequency['field_id']}/type",
        json={"value": "twice a day"},
        headers=bearer(mei["token"]),
    )
    assert again.status_code == 409 and again.json() == {"refusal": "AlreadyConfirmed"}


async def test_the_yes_binds_to_the_value_typed_and_who_typed_it(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(AFTER_THE_SLIP)
    pa, mei, profile_id = await _family(deployment)
    card = await _slip(deployment, pa, profile_id)
    field_id = _field(card, "frequency")["field_id"]
    route = f"/profiles/{profile_id}/review-cards/{card['card_id']}/fields/{field_id}/type"
    first = await deployment.client.post(route, json={"value": TYPED}, headers=bearer(mei["token"]))
    decisions = decide(first.json())
    minted = await mint(deployment, pa["token"], profile_id, first.json(), decisions)
    assert minted.status_code == 201
    retyped = await deployment.client.post(
        route, json={"value": "twice a day"}, headers=bearer(mei["token"])
    )
    assert retyped.status_code == 200
    spent = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        json={"decisions": decisions, "confirmation_id": minted.json()["confirmation_id"]},
        headers=bearer(pa["token"]),
    )
    assert spent.status_code == 400 and spent.json() == {"refusal": "NotWhatWasConfirmed"}


async def test_a_correction_in_the_yes_names_the_confirmer(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(AFTER_THE_SLIP)
    pa, _, profile_id = await _family(deployment)
    card = await _slip(deployment, pa, profile_id)
    done = await confirm(
        deployment, pa["token"], profile_id, card, decide(card, correct={"frequency": TYPED})
    )
    assert done.status_code == 200, done.text
    field = _field(done.json()["card"], "frequency")
    assert field["state"] == "corrected" and field["corrected_by_person_id"] == pa["person_id"]


async def test_typing_needs_the_record_and_is_on_the_trail(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(AFTER_THE_SLIP)
    pa, mei, profile_id = await _family(deployment, scopes=["readings"])
    card = await _slip(deployment, pa, profile_id)
    field_id = _field(card, "frequency")["field_id"]
    refused = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/fields/{field_id}/type",
        json={"value": TYPED},
        headers=bearer(mei["token"]),
    )
    assert refused.status_code == 403 and refused.json()["refusal"] == "OutOfScope"
    assert "OutOfScope" in await refusals(deployment, pa, profile_id)
    blank = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/fields/{field_id}/type",
        json={"value": None},
        headers=bearer(pa["token"]),
    )
    assert blank.status_code == 422


class _Listening:
    """The fixture extractor, remembering the hints it was given."""

    def __init__(self) -> None:
        self.inner = FixtureExtractor(PAPER)
        self.heard: list[Hints] = []

    async def extract(self, data: bytes, content_type: str, hints: Hints) -> Extraction:
        self.heard.append(hints)
        return await self.inner.extract(data, content_type, hints)


async def test_the_kind_he_says_it_is_reaches_the_extractor_as_a_hint(
    sg: AsyncSession, tmp_path: Path
) -> None:
    owner = await _pa(sg)
    store = LocalObjectStore(tmp_path, Region.SG)
    listening = _Listening()
    stored = await store_photo(
        sg,
        context=owner,
        store=store,
        data=placeholder_png(CLINIC_SLIP),
        content_type="image/png",
        captured_at=AFTER_THE_SLIP,
        source_channel=SourceChannel.APP,
    )
    card = await review_photo(
        sg,
        context=owner,
        artifact_id=stored.id,
        store=store,
        extractor=listening,
        language="en",
        asked_as=DocumentKind.CLINIC_SLIP,
    )
    assert listening.heard == [Hints("en", Region.SG, DocumentKind.CLINIC_SLIP)]
    assert card.asked_as is DocumentKind.CLINIC_SLIP
    fields = await card_fields(sg, context=owner, card_id=card.id)
    assert [f.attribute for f in fields if f.unreadable] == ["frequency"]


def test_an_unreadable_field_carries_no_value() -> None:
    blank = ExtractedField("medicine", "frequency", None, None, 0.1, unreadable=True)
    assert blank.checked() == blank
    with pytest.raises(NotAValue):
        ExtractedField("medicine", "frequency", "OM", None, 0.1, unreadable=True).checked()
    with pytest.raises(NotAValue):
        ExtractedField("medicine", "frequency", None, None, 0.1).checked()
