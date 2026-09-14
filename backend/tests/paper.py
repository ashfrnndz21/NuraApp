"""The redacted papers of the first family, as the tests and the checkpoint see them.

No photo is committed. Each paper is a small deterministic byte string — a PNG signature and
a label — whose sha256 is the key the fixture extractor answers by, and a JSON file in
`tests/fixtures/paper/` that says what the extractor reads off it. `scripts/checkpoint.py`
carries the same three-line generator so it can upload the same bytes over HTTP without
importing anything from here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PAPER = Path(__file__).resolve().parent / "fixtures" / "paper"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

LIPID_PANEL = "lipid-panel-2023-09-07"
"""A Thyrocare-style lipid profile, collected 7 September 2023."""

LIPID_PANEL_2025 = "lipid-panel-2025-08-29"
"""A second lipid profile, from Bukit Lab (fictional), collected 29 August 2025: the lab, his
year of birth and his sex on the header, for the lab trend (E09-01)."""

WARFARIN_LABEL = "warfarin-label-2024-03-12"
"""A dispensing label for warfarin 5 mg, dispensed 12 March 2024, instructions in Malay."""

CLINIC_SLIP = "clinic-slip-2026-09-10"
"""A clinic slip in Dr Tan's hand, 10 September 2026: amlodipine, the frequency unreadable."""

HANDWRITTEN_PRESCRIPTION = "handwritten-prescription-2026-08-28"
"""A handwritten prescription for metformin, 28 August 2026: drug, dose and frequency."""

DISCHARGE_LETTER = "discharge-letter-2026-08-20"
"""A two-page hospital discharge letter as a PDF from a portal, 20 August 2026."""

RECEIPT = "receipt-2026-09-01"
"""A shop receipt as a PDF, forwarded by mistake: not a health paper."""

BP_CUFF = "bp-cuff-2026-09-14"
"""A blood pressure machine's screen, 14 September 2026 at 7.42: 138/84, pulse 72."""

GLUCOMETER = "glucometer-2026-09-14"
"""A glucometer's screen, 14 September 2026 at 6.55: 6.8 mmol/L."""

PDF_HEADER = b"%PDF-1.4\n"


def placeholder_png(label: str) -> bytes:
    """The bytes that stand in for one redacted photo. Same label, same bytes, same digest."""
    return PNG_SIGNATURE + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"


def placeholder_pdf(label: str) -> bytes:
    """The bytes that stand in for one redacted PDF: a PDF header and a label."""
    return PDF_HEADER + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"


def placeholder_of(label: str) -> bytes:
    """The placeholder for a paper, by the format its fixture names (a photo unless a PDF)."""
    path = PAPER / f"{label}.json"
    kind = json.loads(path.read_text()).get("format", "png") if path.exists() else "png"
    return placeholder_pdf(label) if kind == "pdf" else placeholder_png(label)


def papers() -> list[str]:
    """Every paper fixture's label — the files the extractor answers from, not the labelled
    answers beside them (`*.expected.json`)."""
    return sorted(
        path.stem for path in PAPER.glob("*.json") if not path.name.endswith(".expected.json")
    )


def expected(label: str) -> dict[str, Any]:
    """What the paper says, labelled by hand: what the accuracy harness measures against."""
    found: dict[str, Any] = json.loads((PAPER / f"{label}.expected.json").read_text())
    return found


def fixture(label: str) -> dict[str, Any]:
    """The JSON the fixture extractor answers with for this paper."""
    found: dict[str, Any] = json.loads((PAPER / f"{label}.json").read_text())
    return found
