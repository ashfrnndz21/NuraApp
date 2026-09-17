"""E03-03 acceptance.

    Every visit links to a provider; notes visible to chief only.

The directory is every doctor, clinic, hospital and pharmacy he has used, each with its
history — its visits, the papers from them or from the illnesses they were part of, the
medicines on its name. The chief's note about a place is one line, kept under the family
scope for the owner and his chief alone, and never about his health: a line naming a medicine
(by the licensed registry, the high-risk table or his own names for it) or a condition is
refused, and the refusal is on the trail. Nothing is kept of a refused line.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.family.common import NotAChief
from app.keys.context import OutOfScope
from app.keys.scopes import ROLE_SCOPES, KeyRole, Scope
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    HomeCareCategory,
    ProviderKind,
    ProviderNote,
)
from app.memory.providers import (
    NotAPlaceNote,
    NoteNamesHealth,
    chief_notes,
    directory,
    provider_history,
    write_chief_note,
)
from app.memory.spine import add_provider
from app.regions import Region
from app.safety.health_words import CONDITION, MEDICINE, names_health
from tests.medicines_support import REGISTRY, let_in
from tests.timeline_support import KIT_PHONE, record, refusals


async def test_every_visit_links_to_a_provider(sg: AsyncSession) -> None:
    rec = await record(sg)
    listed = await directory(sg, context=rec.owner)
    assert [(s.provider.name, s.visits) for s in listed] == [("Dr Tan", 2)]
    assert listed[0].last_visit is not None and listed[0].last_visit.id == rec.checkup.id
    assert listed[0].next_visit is not None and listed[0].next_visit.id == rec.next_visit.id
    # The table refuses a visit that names no provider, whatever the service did.
    sg.add(
        Appointment(
            profile_id=rec.owner.profile_id,
            scheduled_at=datetime(2026, 9, 20, tzinfo=UTC),
            status=AppointmentStatus.PLANNED,
            purpose="a visit with nobody",
            confirmed_by_person_id=rec.owner.person_id,
        )
    )
    with pytest.raises(IntegrityError):
        await sg.flush()
    await sg.rollback()


async def test_a_home_care_provider_carries_its_category(sg: AsyncSession) -> None:
    """Services' home-care grid (board-fidelity-round-2) reads the same directory as his
    doctors and clinics, told apart only by `category` — null for the existing kinds."""
    rec = await record(sg)
    nurse = await add_provider(
        sg,
        context=rec.owner,
        name="Home Nursing Co",
        kind=ProviderKind.OTHER,
        region=Region.SG,
        category=HomeCareCategory.NURSING,
    )
    assert nurse.category is HomeCareCategory.NURSING
    listed = {s.provider.name: s.provider.category for s in await directory(sg, context=rec.owner)}
    assert listed["Home Nursing Co"] is HomeCareCategory.NURSING
    assert listed["Dr Tan"] is None


async def test_a_providers_history_is_its_visits_the_papers_and_the_medicines_on_its_name(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    history = await provider_history(sg, context=rec.owner, provider_id=rec.tan.id)
    assert [visit.id for visit in history.visits] == [rec.next_visit.id, rec.checkup.id]
    # The lab paper hangs off the illness his next visit is part of.
    assert [(p.artifact.id, p.via, p.episode_id) for p in history.papers] == [
        (rec.paper.id, "episode", rec.episode.id)
    ]
    assert {fact.id for fact in history.papers[0].facts} == {fact.id for fact in rec.lab}
    assert [line.generic for line in history.medicines] == ["amlodipine"]
    assert history.withheld == ()


async def test_notes_are_the_chiefs_alone(sg: AsyncSession) -> None:
    rec = await record(sg)
    note = await write_chief_note(
        sg, context=rec.mei, provider_id=rec.tan.id, text="parking at B2", registry=REGISTRY
    )
    assert note.text == "parking at B2" and note.written_by_person_id == rec.mei.person_id
    for reader in (rec.mei, rec.owner):
        history = await provider_history(sg, context=reader, provider_id=rec.tan.id)
        assert [n.text for n in history.notes] == ["parking at B2"]
    # A caregiver's key does not open the family part: the notes are withheld, by name, and
    # reaching for them is refused and written down.
    kit = await let_in(
        sg,
        rec.owner,
        phone=KIT_PHONE,
        name="Kit",
        role=KeyRole.CAREGIVER,
        scopes=set(ROLE_SCOPES[KeyRole.CAREGIVER]),
    )
    history = await provider_history(sg, context=kit, provider_id=rec.tan.id)
    assert history.notes == () and Scope.FAMILY in history.withheld
    with pytest.raises(OutOfScope):
        await chief_notes(sg, context=kit, provider_id=rec.tan.id)


async def test_a_caregiver_given_the_family_part_is_still_not_a_chief(sg: AsyncSession) -> None:
    rec = await record(sg)
    kit = await let_in(
        sg,
        rec.owner,
        phone=KIT_PHONE,
        name="Kit",
        role=KeyRole.CAREGIVER,
        scopes=set(ROLE_SCOPES[KeyRole.CAREGIVER]) | {Scope.FAMILY},
    )
    with pytest.raises(NotAChief):
        await write_chief_note(sg, context=kit, provider_id=rec.tan.id, text="lift lobby B")
    history = await provider_history(sg, context=kit, provider_id=rec.tan.id)
    assert history.notes == () and Scope.FAMILY in history.withheld
    assert any(e.refused_because == "NotAChief" for e in await refusals(sg, rec.owner))


@pytest.mark.parametrize(
    "text",
    [
        "warfarin makes him sleepy, go early",
        "bring the Norvasc box",
        "ask about amlodipine at the counter",
        "the water pill is kept at home",
        "his diabetes clinic is on level 3",
        "he has cancer, be gentle",
        "klinik kencing manis di tingkat 3",
        "糖尿病复诊在三楼",
    ],
)
async def test_a_note_naming_a_medicine_or_a_condition_is_refused_and_written_down(
    sg: AsyncSession, text: str
) -> None:
    rec = await record(sg)
    with pytest.raises(NoteNamesHealth):
        await write_chief_note(
            sg, context=rec.mei, provider_id=rec.tan.id, text=text, registry=REGISTRY
        )
    assert (await sg.scalars(select(ProviderNote))).all() == []
    refused = [e for e in await refusals(sg, rec.owner) if e.refused_because == "NoteNamesHealth"]
    assert refused and refused[0].target == "provider_note" and refused[0].scope is Scope.FAMILY


@pytest.mark.parametrize("text", ["   ", "x" * 281, "two\nlines"])
async def test_a_note_is_one_line_of_at_most_280_characters(sg: AsyncSession, text: str) -> None:
    rec = await record(sg)
    with pytest.raises(NotAPlaceNote):
        await write_chief_note(sg, context=rec.mei, provider_id=rec.tan.id, text=text)


def test_the_health_words_check_finds_the_kind_and_never_the_word() -> None:
    assert names_health("parking at B2", REGISTRY) is None
    assert names_health("long waits, go early", REGISTRY) is None
    assert names_health("Level 3, lift lobby B", REGISTRY) is None
    assert names_health("the insulin fridge is broken") == MEDICINE
    assert names_health("Norvasc", REGISTRY) == MEDICINE
    assert names_health("Norvasc") is None  # the registry is what knows a brand
    assert names_health("his stroke clinic") == CONDITION
    assert names_health("高血压门诊") == CONDITION


async def test_a_note_on_a_provider_not_on_this_profile_is_refused(sg: AsyncSession) -> None:
    from app.memory.spine import NoSuchProvider

    rec = await record(sg)
    with pytest.raises(NoSuchProvider):
        await write_chief_note(sg, context=rec.mei, provider_id=uuid.uuid4(), text="parking at B2")
