"""The licensed data port and the fixture that answers it (docs/medications-module.md §2, §9)."""

from __future__ import annotations

import pytest

from app.drugs.fixture import FixtureRegistry
from app.drugs.registry import LabelFields, Severity, UnknownDrug
from app.safety.high_risk import HIGH_RISK_CLASSES, is_high_risk
from tests.medicines_support import REGISTRY


def test_the_fixture_holds_a_dozen_common_drugs_with_local_registration_numbers() -> None:
    assert REGISTRY.generics >= {
        "amlodipine",
        "metformin",
        "atorvastatin",
        "warfarin",
        "insulin glargine",
        "aspirin",
        "losartan",
        "frusemide",
        "omeprazole",
        "gliclazide",
        "methotrexate",
        "paracetamol",
    }
    for match in REGISTRY.identify(LabelFields(generic="amlodipine")):
        assert match.registration_no.startswith("MAL")
    (marevan,) = REGISTRY.identify(LabelFields(brand="Marevan", strength="3 mg"))
    assert marevan.registration_no.startswith("SIN") and marevan.generic == "warfarin"


def test_the_registration_number_is_the_strongest_key() -> None:
    """A registration number alone identifies the product; brand and strength are the fallback."""
    (found,) = REGISTRY.identify(LabelFields(registration_no="mal19970002a"))
    assert (found.generic, found.strength, found.brand) == ("amlodipine", "10 mg", "Norvasc")
    # Brand and strength fall back to the same product.
    (again,) = REGISTRY.identify(LabelFields(brand="norvasc", strength="10mg"))
    assert again.registration_no == "MAL19970002A"
    # A local generic brand resolves to the same generic, not to a guess.
    (amlong,) = REGISTRY.identify(LabelFields(brand="Amlong"))
    assert (amlong.generic, amlong.strength) == ("amlodipine", "5 mg")


def test_a_brand_the_register_does_not_hold_matches_nothing() -> None:
    assert REGISTRY.identify(LabelFields(brand="Nurofen", strength="200 mg")) == []
    assert REGISTRY.identify(LabelFields(strength="5 mg")) == []


def test_a_generic_without_a_strength_returns_every_strength_so_nothing_is_guessed() -> None:
    strengths = {m.strength for m in REGISTRY.identify(LabelFields(generic="warfarin"))}
    assert strengths == {"1 mg", "3 mg"}


def test_high_risk_is_a_property_of_the_class_from_the_register() -> None:
    by_generic = {m.generic: m for m in REGISTRY.identify(LabelFields(generic="warfarin"))}
    assert by_generic["warfarin"].high_risk and by_generic["warfarin"].drug_class == "anticoagulant"
    (lantus,) = REGISTRY.identify(LabelFields(generic="insulin glargine"))
    assert lantus.high_risk and lantus.drug_class == "insulin"
    (trexan,) = REGISTRY.identify(LabelFields(generic="methotrexate"))
    assert trexan.high_risk
    for norvasc in REGISTRY.identify(LabelFields(generic="amlodipine", strength="5 mg")):
        assert not norvasc.high_risk
    assert {
        "anticoagulant",
        "insulin",
        "cardiac_glycoside",
        "antimetabolite",
        "opioid",
    } <= HIGH_RISK_CLASSES
    assert is_high_risk("Opioid") and not is_high_risk(None) and not is_high_risk("statin")


def test_interactions_come_from_the_data_worst_first_and_name_both_drugs() -> None:
    found = REGISTRY.interactions(["amlodipine", "warfarin", "aspirin", "paracetamol"])
    pairs = [(i.pair, i.severity, i.text_id) for i in found]
    assert pairs[0] == (("warfarin", "aspirin"), Severity.MAJOR, "bleeding_risk")
    assert (("warfarin", "paracetamol"), Severity.MODERATE, "bleeding_check") in pairs
    assert all("amlodipine" not in i.pair for i in found)
    assert REGISTRY.interactions(["amlodipine"]) == []


def test_two_of_the_same_kind_are_flagged_as_duplicate_therapy() -> None:
    (flag,) = REGISTRY.interactions(["atorvastatin", "simvastatin", "amlodipine"])
    assert flag.severity is Severity.DUPLICATE
    assert flag.pair == ("atorvastatin", "simvastatin") and flag.text_id == "same_kind_twice"
    # metformin (biguanide) and gliclazide (sulfonylurea) are different kinds: no duplicate.
    assert REGISTRY.interactions(["metformin", "gliclazide"]) == []
    # Two strengths of one generic are one generic: not a duplicate of itself.
    assert REGISTRY.interactions(["amlodipine", "amlodipine"]) == []


def test_a_monograph_is_rule_ids_not_prose() -> None:
    mono = REGISTRY.monograph("amlodipine")
    assert mono.purpose_id == "blood_pressure"
    assert mono.missed_dose_rule_id == "take_now_unless_next_is_near"
    assert "swollen_ankles" in mono.watch_out_ids and "grapefruit" in mono.avoid_ids
    for value in (
        mono.purpose_id,
        mono.food_rule_id,
        mono.missed_dose_rule_id,
        *mono.watch_out_ids,
    ):
        assert " " not in value and value == value.lower()
    with pytest.raises(UnknownDrug):
        REGISTRY.monograph("digoxin")


def test_the_registry_loads_from_the_fixture_file_and_nothing_else() -> None:
    fresh = FixtureRegistry.load()
    assert fresh.generics == REGISTRY.generics
