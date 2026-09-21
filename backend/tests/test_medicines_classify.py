"""`app.medicines.classify` and its audited door (#302): a name alone is a medicine, a
family of medicines, or neither — decided by the licensed register, never by guessing at
the text. The owner's own case: a box that prints only "STATIN" asks which one it is."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.drugs.fixture import FixtureRegistry
from app.drugs.registry import LabelFields
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.medicines.classify import NameKind, classify_name
from app.medicines.service import classify
from tests.medicines_support import REGISTRY, let_in, pa

# --- the pure function, no session needed ---------------------------------------------------


def test_a_specific_product_classifies_as_a_medicine() -> None:
    assert classify_name(REGISTRY, "amlodipine") is NameKind.MEDICINE
    assert classify_name(REGISTRY, "Norvasc") is NameKind.MEDICINE  # a brand name too


def test_a_family_name_with_no_specific_product_classifies_as_a_class() -> None:
    assert classify_name(REGISTRY, "STATIN") is NameKind.CLASS
    assert classify_name(REGISTRY, "  statin  ") is NameKind.CLASS  # trimmed, case folded


def test_a_name_the_register_has_never_heard_of_is_unknown() -> None:
    assert classify_name(REGISTRY, "definitely not a real drug or class") is NameKind.UNKNOWN
    assert classify_name(REGISTRY, "") is NameKind.UNKNOWN
    assert classify_name(REGISTRY, None) is NameKind.UNKNOWN


def test_members_of_class_is_the_registers_own_filing_never_a_text_search() -> None:
    members = REGISTRY.members_of_class("STATIN")
    generics = {m.generic for m in members}
    assert generics == {"atorvastatin", "simvastatin", "rosuvastatin"}
    # One product per generic, even though rosuvastatin has five brands on file.
    assert len(members) == len(generics)
    # Ordered by generic name, so a caller offering these as choices is deterministic.
    assert [m.generic for m in members] == sorted(generics)
    # A word that merely resembles a class, but is not one the register files under, finds
    # nothing — this is filing, not search.
    assert REGISTRY.members_of_class("cholesterol") == []
    assert REGISTRY.members_of_class("") == []


def test_a_product_name_is_never_also_read_as_a_class() -> None:
    # "amlodipine" is a specific product's generic; it is not itself a drug_class value in
    # the fixture, so members_of_class must find nothing for it.
    assert REGISTRY.members_of_class("amlodipine") == []


def test_underscored_and_spaced_class_names_are_the_same_class() -> None:
    fixture = FixtureRegistry.load()
    members = fixture.identify(LabelFields(generic="amlodipine"))
    drug_class = members[0].drug_class  # "calcium_channel_blocker" on file
    spaced = drug_class.replace("_", " ")
    assert fixture.members_of_class(drug_class) == fixture.members_of_class(spaced.upper())


# --- the audited door -------------------------------------------------------------------


async def test_classify_is_read_only_and_scoped_like_its_neighbours(sg: AsyncSession) -> None:
    owner = await pa(sg)
    medicine = await classify(sg, context=owner, registry=REGISTRY, name="amlodipine")
    assert medicine.kind is NameKind.MEDICINE
    assert medicine.candidates == ()

    family = await classify(sg, context=owner, registry=REGISTRY, name="STATIN")
    assert family.kind is NameKind.CLASS
    assert {c.generic for c in family.candidates} == {"atorvastatin", "simvastatin", "rosuvastatin"}

    unknown = await classify(sg, context=owner, registry=REGISTRY, name="not a real thing")
    assert unknown.kind is NameKind.UNKNOWN
    assert unknown.candidates == ()


async def test_classify_is_refused_without_the_medicines_scope(sg: AsyncSession) -> None:
    owner = await pa(sg)
    # A readings-only key: it can read his blood-pressure readings, never the classifier.
    outsider = await let_in(
        sg, owner, phone="+6591110099", name="Kit", role=KeyRole.VIEWER, scopes={Scope.READINGS}
    )
    with pytest.raises(OutOfScope):
        await classify(sg, context=outsider, registry=REGISTRY, name="STATIN")
