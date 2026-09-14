"""The voice notes of the first family, as the tests and the checkpoint hear them.

No audio is committed. Each note is a small deterministic byte string — a marker and a
label — whose sha256 is the key the fixture transcriber answers by, and a JSON file in
`tests/fixtures/voice/` that says what it heard and how sure it was. `scripts/checkpoints/cp11.py`
carries the same one-line generator so it can send the same bytes over HTTP without
importing anything from here. A label with no file is a note the transcriber cannot hear.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

VOICE = Path(__file__).resolve().parent / "fixtures" / "voice"

CONTENT_TYPE = "audio/m4a"

CHEST_PAIN = "chest-pain"
"""Pa, in English: "I have chest pain"."""

TIRED_TODAY = "tired-today"
"""Pa, in English: "I feel tired today"."""

DIZZY = "dizzy-quite-a-lot"
"""Pa, in English: "dizzy, quite a lot, since this morning"."""

SAKIT_DADA = "sakit-dada"
"""Pa, in Malay: "dada saya sakit" — chest pain."""

UNHEARD = "mumbled"
"""A note the transcriber has no file for: nothing heard."""


def placeholder_voice(label: str) -> bytes:
    """The bytes that stand in for one voice note. Same label, same bytes, same digest."""
    return b"nura-voice-placeholder:" + label.encode("ascii") + b"\n"


def digest_of(label: str) -> str:
    return hashlib.sha256(placeholder_voice(label)).hexdigest()


def fixture(label: str) -> dict[str, Any]:
    """The JSON the fixture transcriber answers with for this note."""
    found: dict[str, Any] = json.loads((VOICE / f"{digest_of(label)}.json").read_text())
    return found
