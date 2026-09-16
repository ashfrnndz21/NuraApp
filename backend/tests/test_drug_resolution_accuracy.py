"""Brand to generic resolution over a sample of 200 MY/SG products, above 95% (E00-06,
docs/parity.md's gap line for this story): a measure, not a claim."""

from __future__ import annotations

import pytest

from app.drugs.fixture import FixtureRegistry
from tests.drug_resolution_accuracy import measure, products

THRESHOLD = 0.95


def test_the_sample_is_at_least_200_my_sg_products() -> None:
    sample = products()
    assert len(sample) >= 200
    assert len({p["registration_no"] for p in sample}) == len(sample)  # every one is distinct
    assert len({p["generic"] for p in sample}) >= 40  # a real spread, not one drug padded out
    kinds = {p["product_kind"] for p in sample}
    assert kinds == {"prescription", "supplement", "tcm"}


def test_brand_to_generic_resolution_is_above_95_percent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = measure(FixtureRegistry.load())
    with capsys.disabled():
        print("\n" + report.render())
    assert report.sampled >= 200
    assert report.accuracy > THRESHOLD, report.render()
