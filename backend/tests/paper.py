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


def placeholder_png(label: str) -> bytes:
    """The bytes that stand in for one redacted photo. Same label, same bytes, same digest."""
    return PNG_SIGNATURE + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"


def fixture(label: str) -> dict[str, Any]:
    """The JSON the fixture extractor answers with for this paper."""
    found: dict[str, Any] = json.loads((PAPER / f"{label}.json").read_text())
    return found
