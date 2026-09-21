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

LAB_REPORT_VITALS = "lab-report-vitals-2026-09-10"
"""A lab report naming one vital in a unit the app already knows (blood sugar, mmol/L)
beside an ordinary lipid row and a header field, 10 September 2026."""

LAB_REPORT_RED_FLAG = "lab-report-red-flag-2026-09-11"
"""A lab report whose facility remark names a red-flag word, 11 September 2026."""

METABOLIC_PANEL = "metabolic-panel-2026-09-18"
"""A wider metabolic panel, 18 September 2026: the controlled vocabulary added for defect #1
(kidney_panel, blood_test, liver_panel), a result's own printed `range` in the current shape
(defect #3, not a legacy `_reference_range` sibling), an analyte with no printed range at all,
and one line outside the vocabulary read as `other` with `label_on_paper` (defect #1's escape
hatch)."""

CLINIC_LETTER_HYPERTENSION = "clinic-letter-hypertension-2026-09-12"
"""A clinic slip naming a condition in the clinician's own words, 12 September 2026."""

INSURANCE_POLICY = "insurance-policy-2026-09-13"
"""A policy schedule, 13 September 2026."""

INSURANCE_CLAIM = "insurance-claim-2026-09-14"
"""A claim letter, 14 September 2026."""

PILL_PHOTO = "pill-photo-2026-09-15"
"""A loose white round tablet, imprint 'IP 190', scored, 15 September 2026: a vision model's
guess at paracetamol 500 mg, matched against the licensed registry and held below the
confirmation threshold either way (#pill-receipt)."""

PHARMACY_RECEIPT = "pharmacy-receipt-2026-08-25"
"""A pharmacy receipt, 25 August 2026: one line naming a medicine already on his list
(Panadol, matched to paracetamol) and one line naming something not on it (a hand sanitiser)
(#pill-receipt)."""

PHARMACY_RECEIPT_RED_FLAG = "pharmacy-receipt-red-flag-2026-08-26"
"""A pharmacy receipt whose item name names a red-flag word, 26 August 2026
(#pill-receipt)."""

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
