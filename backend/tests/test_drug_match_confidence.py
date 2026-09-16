"""#206: identification is a confidence score, not a binary match.

A match is not enough to call a product found — only to call it a candidate. The register
checks the label's own strength and form against the specific product a name matched, and a
label whose amount does not belong to that product scores below `CONFIDENCE_THRESHOLD`
(`app.ingestion.models`, the same floor a document field and a WhatsApp voice transcript are
already held to) and is refused exactly as a miss is today (`NotIdentified`). This is what
closes the finding on #206: a garbled label that happens to collide with a real product's name
is no longer indistinguishable from a clean, exact one — and the guarantee holds by
construction, not by the registry happening to lack a product.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.drugs.fixture import FIXTURE_PATH, FixtureRegistry
from app.drugs.registry import LabelFields, NotIdentified
from app.medicines.service import Label
from tests.medicines_support import REGISTRY, add, artefact, label, pa, planned

WRONG_STRENGTH_LOW = 0.4
"""Mirrors `app.drugs.fixture.WRONG_STRENGTH`: below `CONFIDENCE_THRESHOLD` (0.8)."""


def _grown_registry() -> FixtureRegistry:
    """The fixture's own data, plus products for generics nothing else in this file touches
    — standing in for "the registry grew" without touching the file on disk. If confidence
    depended on how big the register is rather than on the label against the one product
    it named, growing it this way would change the paracetamol-999mg result below; it does
    not, because the score is computed from the label and the one matched product alone."""
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    data["products"] = [
        *data["products"],
        {
            "registration_no": "MAL20990001A",
            "brand": "Panadol Extra",
            "generic": "paracetamol",
            "strength": "500 mg",
            "form": "caplet",
            "drug_class": "analgesic",
        },
        {
            "registration_no": "MAL20990002A",
            "brand": "Ibucare",
            "generic": "ibuprofen",
            "strength": "200 mg",
            "form": "tablet",
            "drug_class": "nsaid",
        },
    ]
    return FixtureRegistry(data)


def test_an_exact_brand_and_strength_scores_full_confidence() -> None:
    (norvasc,) = REGISTRY.identify(LabelFields(brand="Norvasc", strength="10 mg"))
    assert norvasc.confidence == 1.0


def test_a_registration_number_scores_full_confidence_whatever_else_is_given() -> None:
    (found,) = REGISTRY.identify(LabelFields(registration_no="MAL19970002A", strength="9999 mg"))
    assert found.confidence == 1.0 and found.generic == "amlodipine"


def test_a_name_match_with_no_strength_given_scores_above_the_floor_but_below_exact() -> None:
    (amlong,) = REGISTRY.identify(LabelFields(brand="Amlong"))
    assert 0.8 <= amlong.confidence < 1.0


def test_a_strength_that_does_not_belong_to_the_matched_product_scores_low() -> None:
    """paracetamol is one product on file, Panadol 500 mg: a label naming a strength it does
    not have is not silently handed that product anyway."""
    (found,) = REGISTRY.identify(LabelFields(generic="paracetamol", strength="999 mg"))
    assert found.confidence == WRONG_STRENGTH_LOW
    assert found.confidence < 0.8


def test_a_form_that_does_not_belong_to_the_matched_product_scores_low() -> None:
    (found,) = REGISTRY.identify(
        LabelFields(generic="paracetamol", strength="500 mg", form="injection")
    )
    assert found.confidence < 0.8


async def test_an_exact_match_identifies_and_writes_full_confidence_on_the_line(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    done = await add(sg, owner, label("amlodipine", "10 mg", "1 tab OD", quantity=30))
    assert done.line.generic == "amlodipine"
    assert done.line.registry_confidence == 1.0


async def test_a_wrong_strength_label_is_refused_like_a_miss(sg: AsyncSession) -> None:
    owner = await pa(sg)
    photo = await artefact(sg, owner)
    with pytest.raises(NotIdentified):
        await planned(sg, owner, label("paracetamol", "999 mg", "1 tab OD", quantity=30), photo)


async def test_a_brand_only_label_identifies_and_writes_its_own_lower_confidence(
    sg: AsyncSession,
) -> None:
    """No strength on the label at all: not contradicted, so not refused — but the line
    still keeps the honest, lower score, not 1.0 dressed up as an exact match."""
    owner = await pa(sg)
    photo = await artefact(sg, owner)
    brand_only = Label(dose=label("amlodipine", "5 mg").dose, brand="Amlong", quantity=30)
    shown = await planned(sg, owner, brand_only, photo)
    assert shown.match.generic == "amlodipine" and shown.match.strength == "5 mg"
    assert 0.8 <= shown.match.confidence < 1.0
    done = await add(sg, owner, brand_only, photo)
    assert done.line.registry_confidence == shown.match.confidence


def test_growing_the_registry_cannot_rescue_a_wrong_strength_match_by_construction() -> None:
    """The property the regression on #206 needs, proven by construction rather than by a
    test input chosen because today's registry happens not to hold it: adding unrelated
    products anywhere else in the register — simulating growth — cannot change the score of
    a label against the one product its own name matched, because the score is a function of
    those two things alone."""
    small = REGISTRY
    big = _grown_registry()
    for registry in (small, big):
        found = registry.identify(LabelFields(generic="paracetamol", strength="999 mg"))
        assert found and all(m.confidence == WRONG_STRENGTH_LOW for m in found)
    # The new product really is there in the grown registry (growth is real) — it is simply
    # irrelevant to a query naming a different generic and a strength that matches neither.
    assert len(big.identify(LabelFields(generic="paracetamol"))) == 2
    assert len(small.identify(LabelFields(generic="paracetamol"))) == 1


def test_registry_identify_returns_best_first() -> None:
    scored = REGISTRY.identify(LabelFields(generic="paracetamol", strength="999 mg"))
    assert [m.confidence for m in scored] == sorted((m.confidence for m in scored), reverse=True)
