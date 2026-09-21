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
        # Unambiguous: the whole string is one range, with at most a plain unit after it.
        ("<150", None, 150.0),
        ("< 5.2", None, 5.2),
        ("≤5.2", None, 5.2),  # "≤5.2"
        (">1.0", 1.0, None),
        ("> 1.0", 1.0, None),
        ("≥1.0", 1.0, None),  # "≥1.0"
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
        ("-2.0 - 3.0", -2.0, 3.0),  # a negative bound, correctly ordered
        # Ambiguous or malformed: never a guessed bound, only the text kept (owner review,
        # "the worst failure in CLAUDE.md" is a wrong result shown as right).
        ("6.0 - 3.9", None, None),  # reversed
        ("0.5-0.1", None, None),  # reversed
        ("13.0-17.0 (M) / 12.0-15.0 (F)", None, None),  # sex-specific, compound
        ("M: 13-17 F: 12-15", None, None),  # sex-specific, no leading number at all
        ("<0.5 (low risk) / 0.5-1.0 (moderate)", None, None),  # a second, compound range
        ("5.2 (desirable) / 6.2 (high)", None, None),  # a multi-threshold list
        ("4.0-10.0 x10^9/L", None, None),  # the unit itself carries digits
        ("3,9 - 6,0", None, None),  # comma decimals: never guessed at
        ("1,000 - 2,000", None, None),  # a thousands separator: never guessed at
    ],
)
def test_a_printed_range_parses_its_bounds_where_the_text_is_unambiguous(
    text: str, low: float | None, high: float | None
) -> None:
    parsed = parse_printed_range(text)
    assert parsed.low == low
    assert parsed.high == high
    assert parsed.text == text.strip()


def test_the_text_is_always_kept_exactly_as_printed_bounds_or_not() -> None:
    for raw in ("3.9 - 6.0 mmol/L", "<150", "Negative", ""):
        assert parse_printed_range(raw).text == raw.strip()


def test_an_unparseable_range_keeps_its_text_with_both_bounds_null() -> None:
    parsed = parse_printed_range("Negative")
    assert parsed == PrintedRange(low=None, high=None, text="Negative")


def test_the_parser_has_no_coupling_to_the_result_fields_own_unit() -> None:
    """A pure function over the printed text alone: it never sees, and is never affected by,
    the unit the result's own value is in — a range printed with its own unit still parses
    the same way whatever unit the number beside it carries (`web/src/onboarding/review.ts
    rangeStatus`'s own comment records the resulting invariant: range and value are read off
    the same row, so they always share a unit here; nothing here converts one)."""
    assert parse_printed_range("60 - 110 umol/L") == PrintedRange(low=60.0, high=110.0, text="60 - 110 umol/L")
    # The same text, parsed the same way, regardless of what unit a value beside it happens
    # to be in — a mismatch between the two is a fact about the page, never fixed up here.
    assert parse_printed_range("60 - 110 umol/L").low == 60.0


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


def test_the_merged_field_takes_the_lower_of_the_two_confidences() -> None:
    """A clearly-read number beside a faintly-read range must not read as "Nura is sure" once
    the range is folded into it: the card's `needs_confirm` is computed from confidence, so a
    low-confidence range on either side has to carry through to be seen at all."""
    confident_result = _field("lipid_panel", "ldl", 140, unit="mg/dL", confidence=0.95)
    faint_range = _field("lipid_panel", "ldl_reference_range", "<130", confidence=0.4)

    folded = fold_legacy_reference_ranges([confident_result, faint_range])

    assert folded[0].confidence == pytest.approx(0.4)
    assert folded[0].range == PrintedRange(low=None, high=130.0, text="<130")

    # The other way round: a faintly-read number beside a clearly-read range still ends up
    # at the lower of the two — the result's own low confidence is never raised by folding.
    faint_result = _field("lipid_panel", "ldl", 140, unit="mg/dL", confidence=0.4)
    confident_range = _field("lipid_panel", "ldl_reference_range", "<130", confidence=0.95)

    folded_reverse = fold_legacy_reference_ranges([faint_result, confident_range])

    assert folded_reverse[0].confidence == pytest.approx(0.4)


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
