"""The transcriber port: a voice note in, the words and how sure, out.

Speech recognition is a provider (docs/00-MASTER-BUILD-SPEC.md §11: English, Malay and
Mandarin via cloud in the profile's region). Nothing in Nura calls one directly; the flows
that hear a voice note (`app.safety.not_feeling_well`, `app.safety.symptom_log`) take a
`Transcriber` and ask it for a `Transcript`. `FixtureTranscriber` is the one that runs on a
laptop, in the tests and at checkpoint 11: it answers from files keyed by the sha256 of the
bytes, under `backend/tests/fixtures/voice/`, and for bytes it has no file for it answers
that it heard nothing — the flow goes on, the family is still told, and he is asked to say it
again or type it. A voice note is never silently dropped because a provider was down.

The transcript's `confidence` travels onto the fact the words become, the way an extracted
field's does (`app.ingestion.extract`): a fact from a voice note is an extraction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.errors import Refusal

VOICE_CONTENT_TYPES = frozenset(
    {"audio/m4a", "audio/mp4", "audio/aac", "audio/mpeg", "audio/wav", "audio/webm", "audio/ogg"}
)
"""What a voice note may be. The app records AAC in an m4a; WhatsApp sends ogg."""

MAX_VOICE_BYTES = 5 * 1024 * 1024
"""Five megabytes: a minute of speech with room; not a recording of a whole visit (E05)."""


class NotAVoiceNote(Refusal):
    """The bytes offered as a voice note were empty, or of a kind that is not one."""


class VoiceNoteTooLong(Refusal):
    """A voice note about how he feels is not this big."""


@dataclass(frozen=True, slots=True)
class Transcript:
    """The words heard, and how sure the transcriber is of them (0 to 1). `heard` is False
    when nothing came back: the note is kept, and the flow says so instead of guessing."""

    text: str
    confidence: float
    language: str | None = None

    @property
    def heard(self) -> bool:
        return bool(self.text.strip()) and self.confidence > 0


NOTHING_HEARD = Transcript(text="", confidence=0.0)


class Transcriber(Protocol):
    """Speech to words, in the profile's language. One per deployment, in its region."""

    async def transcribe(self, data: bytes, content_type: str, language: str) -> Transcript: ...


class FixtureTranscriber:
    """Answers from `root/<sha256>.json` — `{"text": ..., "confidence": ..., "language": ...}`
    — and with `NOTHING_HEARD` for bytes it has no file for. No audio is committed: the
    placeholders in the tests and at the checkpoint are a few bytes whose digest names a
    file (`backend/tests/fixtures/voice/README.md`)."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def path_of(self, data: bytes) -> Path:
        return self._root / f"{hashlib.sha256(data).hexdigest()}.json"

    async def transcribe(self, data: bytes, content_type: str, language: str) -> Transcript:
        found = self.path_of(data)
        if not found.is_file():
            return NOTHING_HEARD
        loaded = json.loads(found.read_text(encoding="utf-8"))
        return Transcript(
            text=str(loaded.get("text", "")),
            confidence=float(loaded.get("confidence", 0.0)),
            language=loaded.get("language") or language,
        )


def check_voice_note(data: bytes, content_type: str) -> str:
    """The content type, lower-cased, or a refusal: empty bytes, too many, or not audio."""
    kind = content_type.strip().lower().split(";", 1)[0]
    if kind not in VOICE_CONTENT_TYPES:
        raise NotAVoiceNote(f"{content_type} is not a voice note")
    if not data:
        raise NotAVoiceNote("the voice note was empty")
    if len(data) > MAX_VOICE_BYTES:
        raise VoiceNoteTooLong(f"a voice note is at most {MAX_VOICE_BYTES} bytes")
    return kind
