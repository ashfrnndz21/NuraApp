"""E16-04, the story's acceptance line, end to end:

    Warfarin, insulin, digoxin, methotrexate, opioids cannot be saved from voice alone.

The rule itself is `app.safety.high_risk` (built and unit-tested by E02/E04 in
tests/test_high_risk.py); this file does not rebuild it. It walks every path that writes a
medicine fact on main today and shows that a high-risk dose whose provenance is not a label
photo is refused at the memory store, whichever path wrote it, and that the refusal is on
the trail:

- the review card (E02): the fact shape `medicine.dose {"drug": …}` resting on the card's
  artefact — refused from a PDF, a screenshot, a voice note or a message; saved from a photo;
  over HTTP, the only way to a card is `POST /photos`, which takes only photos;
- the medicines module (E04): the fact shape `medication.line:<generic> {"drug_class": …}` —
  refused at its own door over HTTP (`POST /medicines`, 400) and, if the door were skipped,
  at the store;
- the readings route (E00-04): cannot express a medicine at all — its subject is fixed;
- a WhatsApp message or a voice note (E19, not on main yet): the store refuses the fact
  shape it would write, from a MESSAGE event on the WhatsApp channel or a VOICE artefact.

Every class of the five is walked, from a voice note and from a photo.
"""

from __future__ import annotations

import base64
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.db import utcnow
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
    refuse_dose_without_label_photo,
)
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.paper import WARFARIN_LABEL, placeholder_png
from tests.support import OPENING_CONSENT, refused_unit

PA = "+6591110001"

ONE_OF_EACH: dict[str, str] = {
    "anticoagulant": "warfarin",
    "insulin": "insulin glargine",
    "cardiac_glycoside": "digoxin",
    "antimetabolite": "methotrexate",
    "opioid": "tramadol",
}
"""One generic from each of the five classes of docs/medications-module.md §9."""

NOT_A_LABEL_PHOTO = (ArtifactKind.VOICE, ArtifactKind.MESSAGE, ArtifactKind.PDF, ArtifactKind.SCREENSHOT)


async def _pa(session: AsyncSession) -> KeyContext:
    pa = await register_person(session, region=Region.SG, display_name="Pa", phone_e164=PA)
    profile = await create_own_profile(session, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


async def _artifact(session: AsyncSession, context: KeyContext, kind: ArtifactKind) -> Artifact:
    digest = uuid.uuid4().hex + uuid.uuid4().hex
    return await store_artifact(
        session,
        context=context,
        kind=kind,
        storage_key=f"sg/{context.profile_id}/{digest}",
        content_type="image/jpeg" if kind is ArtifactKind.PHOTO else "application/octet-stream",
        sha256=digest,
        captured_at=utcnow(),
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )


def _review_card_shape(drug: str) -> dict[str, Any]:
    """The value the review card writes for a `dose` field (`app.ingestion.review`)."""
    return {"subject": "medicine", "attribute": "dose", "value": {"drug": drug, "instruction": "1 tablet at night"}}


def _medicines_module_shape(generic: str, drug_class: str) -> dict[str, Any]:
    """The value the medicines module writes for a line (`app.medicines.service._line_value`),
    with the registry's class on it and the name only in the attribute."""
    return {
        "subject": "medication",
        "attribute": f"line:{generic}",
        "value": {"drug_class": drug_class, "high_risk": True, "strength": "5 mg", "dose": {"amount": 1}},
    }


def test_the_rule_is_on_the_store_once_with_every_channel_loaded(deployment: Deployment) -> None:
    """Building the app imports every module that writes facts; the hook is there exactly once,
    so no writer path can miss it and none runs it twice."""
    assert semantic.before_fact_write.count(refuse_dose_without_label_photo) == 1


@pytest.mark.parametrize("drug_class", sorted(HIGH_RISK_CLASSES))
async def test_each_class_is_refused_from_voice_alone_and_saved_from_a_label_photo(
    sg: AsyncSession, drug_class: str
) -> None:
    owner = await _pa(sg)
    voice = await _artifact(sg, owner, ArtifactKind.VOICE)
    for shape in (
        _review_card_shape(ONE_OF_EACH[drug_class]),
        _medicines_module_shape(ONE_OF_EACH[drug_class], drug_class),
    ):
        with pytest.raises(HighRiskNeedsLabelPhoto) as refused:
            await assert_fact(sg, context=owner, confidence=0.9, artifact_id=voice.id, **shape)
        assert refused.value.drug_class == drug_class
    assert list(await current_facts(sg, context=owner)) == []

    label = await _artifact(sg, owner, ArtifactKind.PHOTO)
    for shape in (
        _review_card_shape(ONE_OF_EACH[drug_class]),
        _medicines_module_shape(ONE_OF_EACH[drug_class], drug_class),
    ):
        await assert_fact(sg, context=owner, confidence=0.9, artifact_id=label.id, **shape)
    assert {f.artifact_id for f in await current_facts(sg, context=owner)} == {label.id}


@pytest.mark.parametrize("kind", NOT_A_LABEL_PHOTO)
async def test_the_review_card_shape_is_refused_from_anything_but_a_photo(
    sg: AsyncSession, kind: ArtifactKind
) -> None:
    owner = await _pa(sg)
    not_a_label = await _artifact(sg, owner, kind)
    async with refused_unit(sg, HighRiskNeedsLabelPhoto):
        await assert_fact(
            sg, context=owner, confidence=1.0, artifact_id=not_a_label.id, **_review_card_shape("Warfarin")
        )
    assert list(await current_facts(sg, context=owner, subject="medicine")) == []
    trail = await read_audit(sg, context=owner)
    assert any(
        e.outcome is Outcome.REFUSED
        and e.action is Action.WRITE
        and e.target == "fact"
        and e.refused_because == "HighRiskNeedsLabelPhoto"
        for e in trail
    )


async def test_a_whatsapp_message_or_a_voice_note_is_words_alone(sg: AsyncSession) -> None:
    """What the WhatsApp channel (E19) will write when it lands: a fact resting on a MESSAGE
    event on the WhatsApp channel, or on a VOICE artefact. Both are refused for insulin."""
    owner = await _pa(sg)
    said = await record_event(
        sg,
        context=owner,
        kind=EventKind.MESSAGE,
        occurred_at=utcnow(),
        source_channel=SourceChannel.WHATSAPP,
        label="the helper says ten units at night",
    )
    with pytest.raises(HighRiskNeedsLabelPhoto):
        await assert_fact(
            sg, context=owner, confidence=0.8, event_id=said.id, **_review_card_shape("insulin glargine")
        )
    voice = await _artifact(sg, owner, ArtifactKind.VOICE)
    with pytest.raises(HighRiskNeedsLabelPhoto):
        await assert_fact(
            sg, context=owner, confidence=0.8, artifact_id=voice.id, event_id=said.id, **_review_card_shape("Insulin")
        )
    assert list(await current_facts(sg, context=owner)) == []


# --- over HTTP: the routes that exist on main ---------------------------------------------


async def _voice_note(deployment: Deployment, profile_id: str, who: dict[str, str]) -> str:
    """No route makes a voice artefact yet, so it is written the way the recording surface
    will write it, under the owner's context."""
    async with deployment.sessions() as session:
        context = await resolve_key_context(
            session,
            region=Region.SG,
            person_id=uuid.UUID(who["person_id"]),
            profile_id=uuid.UUID(profile_id),
        )
        artifact = await _artifact(session, context, ArtifactKind.VOICE)
        await session.commit()
        return str(artifact.id)


async def _add_medicine(
    client: AsyncClient, profile_id: str, who: dict[str, str], label: dict[str, Any], artifact_id: str
) -> Any:
    his = bearer(who["token"])
    minted = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "medicine", "label": label, "source_artifact_id": artifact_id},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    return await client.post(
        f"/profiles/{profile_id}/medicines",
        json={"label": label, "source_artifact_id": artifact_id, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )


async def test_the_medicines_route_refuses_a_high_risk_dose_from_a_voice_note(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    voice = await _voice_note(deployment, profile_id, pa)
    label = {"generic": "warfarin", "strength": "3 mg", "dose_text": "1 tab ON", "quantity": 28, "prescriber": "Dr Tan"}
    refused = await _add_medicine(deployment.client, profile_id, pa, label, voice)
    assert refused.status_code == 400, refused.text
    assert refused.json() == {"refusal": "HighRiskNeedsLabelPhoto", "drug_class": "anticoagulant"}
    his = bearer(pa["token"])
    held = await deployment.client.get(f"/profiles/{profile_id}/medicines", headers=his)
    assert held.status_code == 200 and held.json() == []
    facts = await deployment.client.get(
        f"/profiles/{profile_id}/facts", params={"subject": "medication"}, headers=his
    )
    assert facts.json() == []


async def test_the_review_card_route_saves_a_warfarin_dose_only_because_it_came_from_a_photo(
    deployment: Deployment,
) -> None:
    """`POST /photos` is the only way to a review card and takes only a photo, so the card's
    facts always rest on a PHOTO artefact; the store's rule is the floor under that."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    made = await deployment.client.post(
        f"/profiles/{profile_id}/photos",
        json={
            "data": base64.b64encode(placeholder_png(WARFARIN_LABEL)).decode(),
            "content_type": "image/png",
            "captured_at": "2026-09-03T08:00:00Z",
        },
        headers=his,
    )
    assert made.status_code == 201, made.text
    card = made.json()
    assert card["high_risk_class"] == "anticoagulant"
    decisions = [{"field_id": f["field_id"], "decision": "confirmed"} for f in card["fields"]]
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "review_card", "card_id": card["card_id"], "decisions": decisions},
        headers=his,
    )
    confirmed = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        json={"decisions": decisions, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert confirmed.status_code == 200, confirmed.text
    dose = next(f for f in confirmed.json()["facts"] if f["attribute"] == "dose")
    assert dose["artifact_id"] == card["artifact_id"]
    # A voice note cannot be posted as a photo.
    not_a_photo = await deployment.client.post(
        f"/profiles/{profile_id}/photos",
        json={"data": base64.b64encode(b"ID3 a voice note").decode(), "content_type": "audio/mpeg", "captured_at": "2026-09-03T08:00:00Z"},
        headers=his,
    )
    assert not_a_photo.status_code in (400, 415, 422), not_a_photo.text


async def test_the_readings_route_cannot_express_a_medicine(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 138, "diastolic": 84, "subject": "medicine", "drug": "warfarin"},
        headers=his,
    )
    assert posted.status_code == 201, posted.text
    facts = (await deployment.client.get(f"/profiles/{profile_id}/facts", headers=his)).json()
    assert {f["subject"] for f in facts} == {"blood_pressure"}
