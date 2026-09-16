"""E13-01: the insurer on the emergency card, and the card in two languages.

    Conditions, medicines, allergies, blood type, contacts, insurer in two languages; works
    with no data.

The insurer is typed by him or his chief, on the typer's own yes for exactly those words; the
name is said in a line, the policy reference is carried as data; an identity-card number is
refused. His language and English are on one card, line for line, in the JSON and on the
printable page. An emergency-only key reads it all, as before, and sets nothing.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.printable import emergency_card_html
from app.clock import FrozenClock
from app.insurance.insurer import (
    NotAPolicyReference,
    NotTheirsToSetInsurer,
    current_insurer,
    insurer_draft,
    set_insurer,
)
from app.keys.confirm import NotWhatWasConfirmed, confirm
from app.keys.scopes import KeyRole
from app.safety.emergency_card import emergency_card
from tests.safety_support import REGISTRY, assert_plain, clinic, let_in, pa, water_pill


async def _typed(session: AsyncSession, context, name: str | None, reference: str | None):
    yes = await confirm(session, context, insurer_draft(name, reference))
    return await set_insurer(
        session, context=context, name=name, policy_reference=reference, confirmation_id=yes.id
    )


async def test_the_insurer_is_typed_on_a_yes_said_in_a_line_and_carried_as_data(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591110071")
    await water_pill(sg, owner)
    await _typed(sg, owner, "Great Eastern", "GE-4471-0932")
    card = await emergency_card(sg, context=owner, registry=REGISTRY)
    assert card.insurer is not None
    assert (card.insurer.name, card.insurer.policy_reference) == ("Great Eastern", "GE-4471-0932")
    said = {line.id: line.text for line in card.lines}
    assert said["ec.insurer"] == "Pa's insurance is with Great Eastern."
    assert not any("GE-4471" in line.text for line in card.lines), "a reference is never said"
    assert card.english_lines == []  # an English card is already in English
    assert_plain(card.lines)


async def test_his_chief_may_type_it_and_the_newest_is_in_force(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await pa(sg, phone="+6591110072")
    mei = await let_in(sg, owner, phone="+6592220072", name="Mei", role=KeyRole.CHIEF)
    await _typed(sg, owner, "AIA", None)
    clock.step(timedelta(minutes=1))
    await _typed(sg, mei, "Prudential", "PRU 88 1234")
    held = await current_insurer(sg, context=owner)
    assert held is not None and (held.name, held.set_by_person_id) == ("Prudential", mei.person_id)
    # No name takes it off the card.
    clock.step(timedelta(minutes=1))
    await _typed(sg, owner, None, None)
    assert await current_insurer(sg, context=owner) is None
    card = await emergency_card(sg, context=owner, registry=REGISTRY)
    assert card.insurer is None and "ec.insurer" not in card.line_ids


async def test_an_emergency_only_key_reads_the_insurer_and_sets_nothing(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591110073", language="ms")
    await water_pill(sg, owner)
    await clinic(sg, owner)
    lin = await let_in(sg, owner, phone="+6594440073", name="Lin", role=KeyRole.EMERGENCY)
    await _typed(sg, owner, "Great Eastern", "GE-1")
    mine = await emergency_card(sg, context=owner, registry=REGISTRY)
    theirs = await emergency_card(sg, context=lin, registry=REGISTRY)
    # The lines are the same; the policy reference is his and his chief's to read in full, and
    # the last four for a key that holds only the emergency card.
    assert theirs.lines == mine.lines
    assert mine.insurer is not None and mine.insurer.policy_reference == "GE-1"
    assert theirs.insurer is not None and theirs.insurer.name == "Great Eastern"
    assert theirs.insurer.policy_reference == "••••GE1"
    assert theirs.english_lines == mine.english_lines and theirs.state_id == mine.state_id
    with pytest.raises(NotTheirsToSetInsurer):
        insurer_draft("AIA", None)  # the draft itself is anyone's to make…
        await set_insurer(sg, context=lin, name="AIA", policy_reference=None, confirmation_id=mine.card_id)


@pytest.mark.parametrize(
    "number",
    (
        "S1234567D",
        "t7654321a",
        "520101-14-5678",
        "520101145678",
        "520101 14 5678",
        "NRIC S1234567D",
        "S1234567D.",
    ),
)
def test_an_identity_card_number_is_refused_however_it_is_written(number: str) -> None:
    with pytest.raises(NotAPolicyReference):
        insurer_draft("AIA", number)
    with pytest.raises(NotAPolicyReference):
        insurer_draft(f"AIA {number}", "AIA-1")


def test_a_policy_reference_that_is_not_an_identity_card_is_kept() -> None:
    for reference in ("GE-4471-0932", "PRU 88 1234", "123456789012", "991399001234"):
        assert insurer_draft("AIA", reference).policy_reference == reference


async def test_a_yes_is_for_exactly_the_words(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591110074")
    yes = await confirm(sg, owner, insurer_draft("AIA", "AIA-1"))
    with pytest.raises(NotWhatWasConfirmed):
        await set_insurer(sg, context=owner, name="AIA", policy_reference="AIA-2", confirmation_id=yes.id)


async def test_his_language_and_english_are_on_one_card_and_one_page(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591110075", language="ms")
    await water_pill(sg, owner)
    await clinic(sg, owner)
    await _typed(sg, owner, "Great Eastern", "GE-77")
    card = await emergency_card(sg, context=owner, registry=REGISTRY)
    assert card.language == "ms"
    assert [line.id for line in card.english_lines] == [line.id for line in card.lines]
    english = {line.id: line.text for line in card.english_lines}
    malay = {line.id: line.text for line in card.lines}
    assert english["ec.title"] == "This is Pa's emergency card."
    assert malay["ec.insurer"] == "Pa ada insurans dengan Great Eastern."
    assert english["ec.insurer"] == "Pa's insurance is with Great Eastern."
    assert english["ec.medicine"] == "Pa takes the water pill (frusemide)."
    assert english["ec.ambulance"] == "The ambulance number is 995."
    assert_plain(card.lines, "ms")
    assert_plain(card.english_lines, "en")
    page = emergency_card_html(card)
    assert '<html lang="ms">' in page
    assert '<p class="twin" lang="en">Pa&#x27;s insurance is with Great Eastern.</p>' in page
    assert '<p class="twin" lang="en">This is Pa&#x27;s emergency card.</p>' in page
    assert page.count("GE-77") == 1 and "<script" not in page
    zh = await emergency_card(sg, context=owner, registry=REGISTRY, language="zh")
    assert zh.language == "zh" and [one.id for one in zh.english_lines] == [one.id for one in zh.lines]


async def test_a_name_in_capitals_is_said_as_it_is_written(sg: AsyncSession) -> None:
    """"AIA" is an insurer's name, not an abbreviation in his sentence: the line is on the card."""
    owner = await pa(sg, phone="+6591110076")
    await _typed(sg, owner, "AIA", "AIA-778")
    card = await emergency_card(sg, context=owner, registry=REGISTRY)
    assert {line.id: line.text for line in card.lines}["ec.insurer"] == "Pa's insurance is with AIA."
