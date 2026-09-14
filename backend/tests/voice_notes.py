"""The voice notes of the first family, as the tests and the checkpoint hear them (E02-06).

No audio is committed. Each note is a small deterministic byte string — a marker and a label —
whose sha256 names a JSON file in `tests/fixtures/voice/` that says what the fixture
transcriber heard and how sure it was. `scripts/checkpoints/cp18.py` carries the same one-line
generator so it can send the same bytes over HTTP without importing anything from here. A
label with no file is a note the transcriber cannot hear.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

VOICE = Path(__file__).resolve().parent / "fixtures" / "voice"

CONTENT_TYPE = "audio/m4a"

AFTER_THE_WALK = "pa-after-the-walk"
"""Pa, in English, on his reading: "I took it after my walk. I felt fine, only a little tired"."""

MUMBLED = "pa-mumbled"
"""A note the transcriber has no file for: nothing heard, and the note kept."""


def placeholder_voice(label: str) -> bytes:
    """The bytes that stand in for one voice note. Same label, same bytes, same digest."""
    return b"nura-voice-placeholder:" + label.encode("ascii") + b"\n"


def digest_of(label: str) -> str:
    return hashlib.sha256(placeholder_voice(label)).hexdigest()
