"""The drug registry port's conformance suite (E00-06): what ANY adapter must answer.

`app.drugs.registry.DrugRegistry` is a port; `FixtureRegistry` is the one adapter this build
has, and a licensed NPRA/HSA feed — when a deployment has a licence for one — is a second
adapter behind the same port, chosen in `app.drugs.client`. `assert_registry_conforms` is the
suite either must pass: it names the shape and the invariants a caller (`app.medicines.service`,
`app.channels.api.medicines`) is entitled to rely on, so a licensed adapter drops in with no
change to a caller.

The suite takes its sample from the caller, not from the registry: a licensed feed may hold
tens of thousands of products with no way to enumerate "every generic", so nothing here calls
anything but the port's own three methods. A licensed adapter's own test file calls
`assert_registry_conforms` with a handful of generics and one interacting pair it knows its
sandbox holds; nothing here is specific to the fixture beyond the sample `test_the_fixture_
registry_conforms` passes it.

This is distinct from `tests/test_drugs.py`, which asserts the fixture's own data (its
products, its interaction pairs, its monographs) is what it says it is.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import pytest

from app.drugs.fixture import FixtureRegistry
from app.drugs.registry import (
    DrugMatch,
    DrugRegistry,
    LabelFields,
    ProductKind,
    Severity,
    UnknownDrug,
)

_ID = re.compile(r"^[a-z][a-z0-9_]*$")
"""The shape every id into `app.medicines.strings` must have: lower-case, underscored, never
a sentence — a caller looks these up in a dict and must never be handed prose to render raw."""

SEVERITY_ORDER = {
    Severity.MAJOR: 0,
    Severity.MODERATE: 1,
    Severity.MINOR: 2,
    Severity.DUPLICATE: 3,
}


def _assert_well_formed_match(match: DrugMatch, generic: str) -> None:
    assert match.registration_no and match.registration_no == match.registration_no.strip()
    assert match.brand
    assert match.generic == generic
    assert match.strength
    assert match.form
    assert match.drug_class
    assert isinstance(match.high_risk, bool)
    assert isinstance(match.product_kind, ProductKind)
    assert match.product_name
    assert match.licence_status
    assert match.active_ingredients and match.generic in match.active_ingredients


def _assert_well_formed_monograph(registry: DrugRegistry, generic: str) -> None:
    mono = registry.monograph(generic)
    assert mono.generic == generic
    for one in (mono.plain_name_id, mono.purpose_id, mono.food_rule_id, mono.missed_dose_rule_id):
        assert _ID.match(one), f"{generic}: {one!r} is not an id a caller can look up"
    for many in (mono.watch_out_ids, mono.avoid_ids):
        for one in many:
            assert _ID.match(one), f"{generic}: {one!r} is not an id a caller can look up"


def assert_registry_conforms(
    registry: DrugRegistry,
    *,
    sample_generics: Sequence[str],
    interacting_pair: tuple[str, str] | None = None,
) -> None:
    """The contract every `DrugRegistry` adapter must meet.

    `sample_generics` are generics the registry is known to hold (any product kind: a
    prescription medicine, a supplement, a TCM remedy — E04-03 requires all three answer the
    same way). `interacting_pair`, when given, is two of them the registry is known to flag
    together, so the severity-ordering and well-formedness checks on `interactions()` have
    something to check; without one, only the empty-input behaviour is asserted.
    """
    assert sample_generics, "a sample of nothing conforms to nothing useful"

    # identify(): every field on every match is populated and well-formed, whatever the
    # product's kind — a supplement or a TCM remedy answers exactly as a prescription
    # medicine does, never with a blank where a caller expects a value (E04-03).
    for generic in sample_generics:
        matches = registry.identify(LabelFields(generic=generic))
        assert matches, f"{generic} was sampled as known but identify() found nothing for it"
        for match in matches:
            _assert_well_formed_match(match, generic)

    # identify(): nothing is guessed. A registration number that does not exist, or a brand
    # this registry has never heard of, matches nothing — never a nearest guess.
    assert registry.identify(LabelFields(registration_no="ZZZ00000000Z")) == []
    assert registry.identify(LabelFields(brand="Not A Real Brand Name Ever")) == []
    assert registry.identify(LabelFields()) == []  # nothing named identifies nothing

    # identify(): a registration number is case-insensitive and, when it is on the register,
    # decides alone — the strongest key (module doc, `DrugRegistry.identify`).
    for generic in sample_generics[:3]:
        (one, *_rest) = registry.identify(LabelFields(generic=generic))
        by_number = registry.identify(LabelFields(registration_no=one.registration_no.lower()))
        assert one in by_number

    # interactions(): a single generic, or none, flags nothing — there is no pair to flag
    # with only one drug named (or zero).
    assert registry.interactions([]) == []
    assert registry.interactions([sample_generics[0]]) == []

    if interacting_pair is not None:
        a, b = interacting_pair
        found = registry.interactions([a, b])
        assert found, f"{interacting_pair} was given as a known pair but nothing was flagged"
        orders = [SEVERITY_ORDER[i.severity] for i in found]
        assert orders == sorted(orders), "interactions() must be worst severity first"
        for interaction in found:
            assert set(interaction.pair) <= {a, b}
            assert interaction.text_id and _ID.match(interaction.text_id)
        # An unrelated third generic never appears in a pair it was not asked about.
        unrelated = next((g for g in sample_generics if g not in (a, b)), None)
        if unrelated is not None:
            assert all(unrelated not in i.pair for i in registry.interactions([a, b, unrelated]))

    # monograph(): every generic the register can identify has one — a caller that shows a
    # story or an interaction question for a product it just identified must never be met
    # with `UnknownDrug`. Ids are ids, never prose (module doc, `Monograph`).
    for generic in sample_generics:
        _assert_well_formed_monograph(registry, generic)
    with pytest.raises(UnknownDrug):
        registry.monograph("a generic no register has ever held")


REGISTRY = FixtureRegistry.load()
SAMPLE = ["amlodipine", "warfarin", "ginkgo biloba", "danshen", "paracetamol", "metformin"]


def test_the_fixture_registry_conforms() -> None:
    assert_registry_conforms(REGISTRY, sample_generics=SAMPLE, interacting_pair=("warfarin", "aspirin"))
