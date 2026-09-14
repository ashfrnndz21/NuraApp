"""Pa's WhatsApp agreement is for messages to Pa (#143).

Stopping it must never cut his family's red-flag notices. After Pa stops WhatsApp, a red flag is
still carried to his family on their own channel, under the key his agreement to let them in
rests on, and nothing goes to Pa on WhatsApp. The send door asks his agreement only for a
message to him; anyone else must hold a key to his profile. A key holder's own yes to WhatsApp
is recorded going forward, and holds nothing back.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp.outbound.send import NotLetInHere, _may_message
from app.clock import FrozenClock
from app.consent.models import ConsentChannel, ConsentPurpose
from app.consent.service import NoConsent, revoke_consent
from app.delivery.triggers.models import Delivery, DeliveryChannel, DeliveryOutcome, Ladder
from app.identity.service import register_person
from app.regions import Region
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.delivery_support import MEI, PA, home
from tests.test_triggers import _run, at


async def test_after_pa_stops_whatsapp_a_red_flag_still_reaches_his_family_and_not_him(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """Pa stops WhatsApp. Mei writes "he fell": Siti is told on her WhatsApp at once, and
    by 09:06, with every rung run, not one message has gone to Pa's number."""
    clock.set(at(9))
    h = await home(sg, tmp_path)
    await revoke_consent(
        sg, context=h.owner, purpose=ConsentPurpose.WHATSAPP, captured_via=ConsentChannel.APP
    )
    handled = await h.inbound(sg, MEI, "he fell in the bathroom")
    assert handled.flag_id is not None
    await _run(sg, h, clock, at(9, 6))
    ladder = (await sg.scalars(select(Ladder).where(Ladder.flag_id == handled.flag_id))).one()
    rows = (await sg.scalars(select(Delivery).where(Delivery.ladder_id == ladder.id))).all()
    assert [(row.to_person_id, row.outcome, row.via, row.passed_over) for row in rows] == [
        (h.siti.id, DeliveryOutcome.SENT, DeliveryChannel.WHATSAPP, []),
    ]
    assert [one for one in h.whatsapp.sent if one.to_e164 == PA] == []


async def test_the_send_door_asks_his_agreement_only_for_him(
    sg: AsyncSession, tmp_path: Path
) -> None:
    h = await home(sg, tmp_path)
    await revoke_consent(
        sg, context=h.owner, purpose=ConsentPurpose.WHATSAPP, captured_via=ConsentChannel.APP
    )
    with pytest.raises(NoConsent):
        await _may_message(sg, context=h.owner, person=h.pa)
    await _may_message(sg, context=h.owner, person=h.mei)  # her key lets her be told
    stranger = await register_person(
        sg, region=Region.SG, display_name="Ann", phone_e164="+6598880051", language="en"
    )
    with pytest.raises(NotLetInHere):
        await _may_message(sg, context=h.owner, person=stranger)


async def test_a_key_holder_says_yes_or_no_to_whatsapp_for_herself(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, "+6591430101", "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    said = await deployment.client.post(
        f"/profiles/{profile_id}/whatsapp-opt-in", json={"yes": True}, headers=bearer(pa["token"])
    )
    assert said.status_code == 201, said.text
    assert said.json()["said_yes"] is True
    again = await deployment.client.post(
        f"/profiles/{profile_id}/whatsapp-opt-in", json={"yes": False}, headers=bearer(pa["token"])
    )
    assert again.status_code == 201 and again.json()["said_yes"] is False


async def test_a_push_opens_one_card_by_its_id_under_its_scope(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, "+6591430201", "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    reading = await deployment.client.post(
        f"/profiles/{profile_id}/readings", json={"systolic": 138, "diastolic": 84}, headers=his
    )
    assert reading.status_code == 201, reading.text
    page = (await deployment.client.get(f"/profiles/{profile_id}/feed", headers=his)).json()
    card = next(item for item in page["items"] if item["type"] == "reading")
    opened = await deployment.client.get(
        f"/profiles/{profile_id}/feed/{card['item_id']}", headers=his
    )
    assert opened.status_code == 200, opened.text
    assert (
        opened.json()["item_id"] == card["item_id"]
        and opened.json()["headline"] == card["headline"]
    )
    missing = await deployment.client.get(
        f"/profiles/{profile_id}/feed/{uuid.uuid4()}", headers=his
    )
    assert missing.status_code == 404
