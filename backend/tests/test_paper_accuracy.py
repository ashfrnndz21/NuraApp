"""The accuracy harness over the labelled test set (docs/build-plan.md §8, risk 1; E02-02).

Every paper fixture has its labelled answer beside it, every pair runs through the pipeline,
the per-field accuracy is printed, and on the fixtures themselves every field is either read
right or put in front of a person: 100%, with nothing silently wrong, dropped or invented.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.ingestion.extract import DocumentKind, ExtractedField, Extraction, FixtureExtractor, Hints
from tests.paper import CLINIC_SLIP, LIPID_PANEL, PAPER, expected, papers
from tests.paper_accuracy import Outcome, measure


def test_every_paper_has_its_labelled_answer() -> None:
    labelled = {path.name.removesuffix(".expected.json") for path in PAPER.glob("*.expected.json")}
    assert labelled == set(papers())
    for label in papers():
        answer = expected(label)
        assert answer["placeholder"] == label
        assert "sha256" not in answer
        assert all({"subject", "attribute", "value", "unit"} <= set(f) for f in answer["fields"])


async def test_every_labelled_paper_runs_through_the_pipeline_and_nothing_is_silently_wrong(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = await measure(FixtureExtractor(PAPER))
    with capsys.disabled():
        print("\n" + report.render())
    assert report.papers == len(papers())
    assert report.kinds_right == report.papers
    assert report.count(Outcome.WRONG) == 0
    assert report.count(Outcome.DROPPED) == 0
    assert report.count(Outcome.INVENTED) == 0
    assert report.safe_accuracy == 1.0
    # The two deliberate misreads are caught, not read: the lipid panel's triglycerides at low
    # confidence, and the clinic slip's frequency, which Nura could not read at all.
    caught = {(one.label, one.attribute) for one in report.scored if one.outcome is Outcome.CAUGHT}
    assert caught == {(LIPID_PANEL, "triglycerides"), (CLINIC_SLIP, "frequency")}
    assert report.read_accuracy < 1.0
    assert "100.0% read right or put in front of a person" in report.line()


class _Confident:
    """An extractor that reads the lipid panel's triglycerides wrong and sure of it."""

    def __init__(self) -> None:
        self._inner = FixtureExtractor(PAPER)

    async def extract(self, data: bytes, content_type: str, hints: Hints) -> Extraction:
        read = await self._inner.extract(data, content_type, hints)
        fields = tuple(
            replace(one, confidence=0.99) if one.attribute == "triglycerides" else one
            for one in read.fields
        )
        extra = (ExtractedField("lipid_panel", "made_up", 1, None, 0.99),)
        if read.document_kind is DocumentKind.LAB_REPORT:
            fields = fields + extra
        return replace(read, fields=fields)


async def test_the_harness_counts_a_silent_misread_and_an_invented_field() -> None:
    report = await measure(_Confident())
    assert report.count(Outcome.WRONG) == 1
    assert report.count(Outcome.INVENTED) == 1
    assert report.safe_accuracy < 1.0
