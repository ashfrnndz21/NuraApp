"""E02, defect #3: "a reference range arrives as a separate field instead of belonging to its
result". `parse_printed_range` reads a printed range's bounds off its own text; the text
itself is always kept exactly as printed. `fold_legacy_reference_ranges` is the server-side
normaliser: a `<analyte>_reference_range` sibling field — the shape every extractor wrote
before a result carried its own `range` — folded onto the result it describes and dropped, so
an older answer, and the fixtures already written that way, keep working without a rewrite.
"""

from __future__ import annotations

import pytest

from app.ingestion.extract import (
    ExtractedField,
    PrintedRange,
    fold_legacy_reference_ranges,
    parse_printed_range,
)


@pytest.mark.parametrize(
    ("text", "low", "high"),
    [
        ("<150", None, 150.0),
        ("< 5.2", None, 5.2),
        (">1.0", 1.0, None),
        ("> 1.0", 1.0, None),
        ("3.9 - 6.0", 3.9, 6.0),
        ("3.9–6.0", 3.9, 6.0),
        ("3.9 to 6.0", 3.9, 6.0),
        ("Up to 40", None, 40.0),
        ("under 4.0", None, 4.0),
        ("or more 40", 40.0, None),
        ("Negative", None, None),
        ("", None, None),
        ("   ", None, None),
        ("3.5 - 5.2 mmol/L", 3.5, 5.2),
        ("<130 mg/dL", None, 130.0),
        (">40 mg/dL", 40.0, None),
    ],
)
def test_a_printed_range_parses_its_bounds_where_the_text_is_unambiguous(
    text: str, low: float | None, high: float | None
) -> None:
    parsed = parse_printed_range(text)
    assert parsed.low == low
    assert parsed.high == high


def test_the_text_is_always_kept_exactly_as_printed_bounds_or_not() -> None:
    for raw in ("3.9 - 6.0 mmol/L", "<150", "Negative", ""):
        assert parse_printed_range(raw).text == raw.strip()


def test_an_unparseable_range_keeps_its_text_with_both_bounds_null() -> None:
    parsed = parse_printed_range("Negative")
    assert parsed == PrintedRange(low=None, high=None, text="Negative")


def _field(subject: str, attribute: str, value: object, **rest: object) -> ExtractedField:
    return ExtractedField(
        subject=subject,
        attribute=attribute,
        value=value,
        unit=rest.get("unit"),  # type: ignore[arg-type]
        confidence=rest.get("confidence", 0.9),  # type: ignore[arg-type]
        range=rest.get("range"),  # type: ignore[arg-type]
    )


def test_a_legacy_reference_range_sibling_is_folded_onto_its_result_and_dropped() -> None:
    ldl = _field("lipid_panel", "ldl", 140, unit="mg/dL")
    sibling = _field("lipid_panel", "ldl_reference_range", "<130")
    facility = _field("lab_report", "facility", "Bukit Lab")

    folded = fold_legacy_reference_ranges([ldl, sibling, facility])

    assert [(f.subject, f.attribute) for f in folded] == [
        ("lipid_panel", "ldl"),
        ("lab_report", "facility"),
    ]
    result = folded[0]
    assert result.range == PrintedRange(low=None, high=130.0, text="<130")


def test_a_result_that_already_carries_its_own_range_is_left_alone() -> None:
    own_range = PrintedRange(low=None, high=100.0, text="<100")
    ldl = _field("lipid_panel", "ldl", 90, unit="mg/dL", range=own_range)
    sibling = _field("lipid_panel", "ldl_reference_range", "<130")

    folded = fold_legacy_reference_ranges([ldl, sibling])

    # Nothing is folded — the result already has its own range, given directly, which the
    # legacy sibling's text never overwrites — so the sibling is left exactly as it was too.
    assert [(f.subject, f.attribute) for f in folded] == [
        ("lipid_panel", "ldl"),
        ("lipid_panel", "ldl_reference_range"),
    ]
    assert folded[0].range == own_range


def test_a_sibling_with_no_result_to_fold_onto_passes_through_unchanged() -> None:
    orphan = _field("lipid_panel", "ldl_reference_range", "<130")

    folded = fold_legacy_reference_ranges([orphan])

    assert folded == (orphan,)


def test_a_sibling_whose_value_is_not_text_passes_through_unchanged() -> None:
    ldl = _field("lipid_panel", "ldl", 140, unit="mg/dL")
    sibling = _field("lipid_panel", "ldl_reference_range", 130)  # not a string: never folded

    folded = fold_legacy_reference_ranges([ldl, sibling])

    assert [(f.subject, f.attribute) for f in folded] == [
        ("lipid_panel", "ldl"),
        ("lipid_panel", "ldl_reference_range"),
    ]
    assert folded[0].range is None
