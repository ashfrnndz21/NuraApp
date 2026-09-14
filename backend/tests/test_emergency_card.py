"""E13-01: the emergency card.

    Conditions, medicines, allergies, blood type, contacts, insurer in two languages; works
    with no data.

The card is gated by EMERGENCY (a key narrowed past it is refused and written down); it is
rendered from a State snapshot and the row names it; an emergency-only key reads it from the
last snapshot and is refused when the record has moved past it; every line is verified;
Singapore says 995 and Malaysia 999.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Outcome
from app.clock import FrozenClock
from app.db import utcnow
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import EventKind, ProviderKind, SourceChannel
from app.memory.spine import add_provider
from app.regions import Region
from app.safety.emergency_card import CARD_TARGET, emergency_card
from app.safety.models import CardFormat, EmergencyCard
from app.state.service import StaleState, current_state
from tests.safety_support import (
    REGISTRY,
    assert_plain,
    clinic,
    fact,
    let_in,
    pa,
    trail,
    water_pill,
)


async def _ready(session: AsyncSession, *, region: Region = Region.SG):
    """Pa with a condition, an allergy, a blood type, a birth year, the water pill, a
    doctor, a reading, and Mei as chief."""
    owner = await pa(session, region=region, phone="+6591110031" if region is Region.SG else "+60121110031")
    await fact(session, owner, subject="heart_failure", attribute="control", value="watch")
    await fact(session, owner, subject="penicillin", attribute="allergy", value="rash")
    await fact(session, owner, subject="blood_type", attribute="group", value="O+")
    await fact(session, owner, subject="person", attribute="birth_year", value=1952)
    await water_pill(session, owner)
    await clinic(session, owner)
    await record_event(
        session,
        context=owner,
        kind=EventKind.READING,
        occurred_at=utcnow(),
        label="blood pressure",
        source_channel=SourceChannel.APP,
    )
    mei = await let_in(
        session,
        owner,
        phone="+6592220031" if region is Region.SG else "+60122220031",
        name="Mei",
        role=KeyRole.CHIEF,
    )
    return owner, mei


_clean = assert_plain


async def test_the_card_holds_what_a_stranger_needs_and_every_line_is_verified(
    sg: AsyncSession,
) -> None:
    owner, _mei = await _ready(sg)
    card = await emergency_card(sg, context=owner, registry=REGISTRY)

    assert card.name == "Pa" and card.language == "en" and card.emergency_number == "995"
    assert card.age_band == "70 to 79"
    assert [c.words for c in card.conditions] == ["a weak heart"]
    assert [a.words for a in card.allergies] == ["Penicillin"]
    assert card.blood_type == "O+"
    medicine = card.medicines[0]
    assert (medicine.generic, medicine.strength, medicine.amount, medicine.when) == (
        "frusemide", "40 mg", "1 tablet", "every morning",
    )
    assert medicine.plain_name == "the water pill (frusemide)"
    assert card.contacts[0].name == "Mei" and card.contacts[0].phone_e164 == "+6592220031"
    assert card.clinic is not None and card.clinic.name == "Dr Tan"
    assert card.last_reading_at is not None
    texts = [line.text for line in card.lines]
    assert texts[0] == "This is Pa's emergency card."
    assert "Pa takes the water pill (frusemide)." in texts
    assert "Pa takes 1 tablet every morning." in texts
    assert "The ambulance number is 995." in texts
    assert "Pa's blood pressure was last written down on Thursday 3 September." in texts
    assert "Pa has a weak heart." in texts
    assert "Pa is allergic to Penicillin." in texts
    assert "Pa's blood type is O positive." in texts
    assert "Mei looks after Pa." in texts and "Call Mei first." in texts
    assert "Pa sees Dr Tan." in texts
    assert texts[-1] == "This card is not a doctor's advice."
    _clean(card.lines)
    # The number and the strength are data beside the lines, never in a sentence.
    assert not any("+65" in text or "40 mg" in text for text in texts)


async def test_the_card_is_rendered_from_state_and_the_row_names_it(sg: AsyncSession) -> None:
    owner, _ = await _ready(sg)
    card = await emergency_card(sg, context=owner, registry=REGISTRY, format=CardFormat.HTML)
    state = await current_state(sg, context=owner)
    assert card.state_id == state.id
    row = await sg.get(EmergencyCard, card.card_id)
    assert row is not None and row.state_id == state.id and row.format is CardFormat.HTML
    assert row.rendered_for_person_id == owner.person_id
    assert set(row.line_ids) >= {"ec.title", "ec.medicine", "ec.chief", "ec.boundary"}
    assert row.fact_ids and all(len(one) == 36 for one in row.fact_ids)


async def test_the_card_is_gated_by_emergency_and_a_refusal_is_written_down(
    sg: AsyncSession,
) -> None:
    owner, _ = await _ready(sg)
    narrow = await let_in(
        sg, owner, phone="+6593330031", name="Kit", role=KeyRole.CAREGIVER, scopes={Scope.MEDICINES}
    )
    assert Scope.EMERGENCY not in narrow.scopes
    with pytest.raises(OutOfScope):
        await emergency_card(sg, context=narrow, registry=REGISTRY)
    refused = [
        line
        for line in await trail(sg, owner.profile_id)
        if line.outcome is Outcome.REFUSED and line.target == CARD_TARGET
    ]
    assert refused and refused[-1].actor_person_id == narrow.person_id
    assert refused[-1].scope is Scope.EMERGENCY


async def test_an_emergency_only_key_reads_the_card_from_the_last_snapshot(
    sg: AsyncSession,
) -> None:
    owner, _ = await _ready(sg)
    mine = await emergency_card(sg, context=owner, registry=REGISTRY)
    lin = await let_in(sg, owner, phone="+6594440031", name="Lin", role=KeyRole.EMERGENCY)
    assert lin.scopes == {Scope.PROFILE, Scope.EMERGENCY}
    theirs = await emergency_card(sg, context=lin, registry=REGISTRY)
    assert theirs.state_id == mine.state_id
    assert [line.text for line in theirs.lines] == [line.text for line in mine.lines]
    assert theirs.contacts[0].phone_e164 == "+6592220031"
    # The chief's account was read for her name and number, and the trail says so: a READ
    # of `person` under EMERGENCY by Lin's key (ADR 0002).
    reads = [
        line
        for line in await trail(sg, owner.profile_id)
        if line.actor_person_id == lin.person_id and line.target == "person"
    ]
    assert reads and all(line.scope is Scope.EMERGENCY for line in reads)
    rows = (
        await sg.scalars(select(EmergencyCard).where(EmergencyCard.profile_id == owner.profile_id))
    ).all()
    assert {row.rendered_for_person_id for row in rows} == {owner.person_id, lin.person_id}


async def test_a_stale_card_is_refused_rather_than_shown(sg: AsyncSession) -> None:
    """A caregiver key writes a control word but cannot recompute State, so the last snapshot
    is behind the record. The emergency-only key is refused the card until a key that can
    recompute reads it; then both read the same, current, State."""
    owner, mei = await _ready(sg)
    await emergency_card(sg, context=owner, registry=REGISTRY)
    lin = await let_in(sg, owner, phone="+6594440032", name="Lin", role=KeyRole.EMERGENCY)
    caregiver = await let_in(sg, owner, phone="+6595550031", name="Ana", role=KeyRole.CAREGIVER)
    await fact(sg, caregiver, subject="diabetes", attribute="control", value="watch")

    with pytest.raises(StaleState):
        await emergency_card(sg, context=lin, registry=REGISTRY)

    fresh = await emergency_card(sg, context=mei, registry=REGISTRY)
    assert [c.code for c in fresh.conditions] == ["diabetes", "heart_failure"]
    again = await emergency_card(sg, context=lin, registry=REGISTRY)
    assert again.state_id == fresh.state_id
    assert "Pa has sugar sickness." in [line.text for line in again.lines]


async def test_malaysia_says_999_and_singapore_995(sg: AsyncSession, my: AsyncSession) -> None:
    here, _ = await _ready(sg)
    there, _ = await _ready(my, region=Region.MY)
    assert (await emergency_card(sg, context=here, registry=REGISTRY)).emergency_number == "995"
    assert (await emergency_card(my, context=there, registry=REGISTRY)).emergency_number == "999"


async def test_the_card_in_malay_and_chinese_is_verified_too(sg: AsyncSession) -> None:
    owner, _ = await _ready(sg)
    for language in ("ms", "zh"):
        card = await emergency_card(sg, context=owner, registry=REGISTRY, language=language)
        assert card.language == language
        assert_plain(card.lines, language)
    malay = await emergency_card(sg, context=owner, registry=REGISTRY, language="ms")
    # In Malay his name for it stands alone; the register's name is in the table beside it.
    assert "Pa makan pil air." in [line.text for line in malay.lines]


async def test_a_bare_profile_still_has_a_card(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591110039")
    card = await emergency_card(sg, context=owner, registry=REGISTRY)
    texts = [line.text for line in card.lines]
    assert "Nura has no note of a medicine for Pa." in texts
    assert "Nura has no note of a condition for Pa." in texts
    assert "No family number is written down yet." in texts
    assert "The ambulance number is 995." in texts
    assert card.medicines == [] and card.contacts == [] and card.age_band is None


async def test_a_clinic_is_a_place_he_goes_to_and_an_old_reading_is_not_the_last(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await pa(sg, phone="+6591110038")
    await add_provider(
        sg, context=owner, name="Bedok Clinic", kind=ProviderKind.CLINIC, region=Region.SG
    )
    long_ago = utcnow() - timedelta(days=400)
    await record_event(
        sg,
        context=owner,
        kind=EventKind.READING,
        occurred_at=long_ago,
        label="blood pressure",
        source_channel=SourceChannel.APP,
    )
    await record_event(
        sg,
        context=owner,
        kind=EventKind.READING,
        occurred_at=utcnow(),
        label="weight",
        source_channel=SourceChannel.APP,
    )
    card = await emergency_card(sg, context=owner, registry=REGISTRY)
    texts = [line.text for line in card.lines]
    assert "Pa goes to Bedok Clinic." in texts
    assert card.last_reading_at is None
    assert not any("blood pressure was last" in text for text in texts)
