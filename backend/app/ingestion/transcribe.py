"""The transcriber port: a voice note in, the words and how sure, out — in one region.

Speech recognition is a provider (docs/00-MASTER-BUILD-SPEC.md §11: English, Malay and
Mandarin via cloud in the profile's region). Nothing in Nura calls one directly: a flow that
hears a voice note takes a `Transcriber` and asks it for a `Transcript`. A transcriber serves
exactly one region, like the object store (`app.ingestion.objects`), and refuses a note from
the other: the audio of a Singapore profile is never sent to be heard across the causeway.

`FixtureTranscriber` is the one that runs on a laptop and in the tests: it answers from files
keyed by the sha256 of the bytes, under `backend/tests/fixtures/voice/`, and for bytes it has
no file for it answers that it heard nothing. A voice note is kept whether or not it was
heard; the words, when there are any, are kept by reference and are never a fact
(`app.ingestion.notes`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.fixtures import fixture
from app.regions import Region, guard_region


@dataclass(frozen=True, slots=True)
class Transcript:
    """The words heard, how sure the transcriber is of them (0 to 1), and in which language.
    `heard` is False when nothing came back: the note is kept, and nothing is guessed."""

    text: str
    confidence: float
    language: str | None = None

    @property
    def heard(self) -> bool:
        return bool(self.text.strip()) and self.confidence > 0


NOTHING_HEARD = Transcript(text="", confidence=0.0)


class Transcriber(Protocol):
    """Speech to words, in the profile's language, in one region."""

    @property
    def region(self) -> Region: ...

    async def transcribe(
        self, data: bytes, content_type: str, language: str, region: Region
    ) -> Transcript: ...


@fixture
class FixtureTranscriber:
    """Answers from `root/<sha256>.json` — `{"text": ..., "confidence": ..., "language": ...}`
    — and with `NOTHING_HEARD` for bytes it has no file for. No audio is committed: the
    placeholders in the tests and at the checkpoint are a few bytes whose digest names a
    file (`backend/tests/voice_notes.py`)."""

    def __init__(self, root: Path, region: Region) -> None:
        self._root = Path(root)
        self._region = region

    @property
    def region(self) -> Region:
        return self._region

    def path_of(self, data: bytes) -> Path:
        return self._root / f"{hashlib.sha256(data).hexdigest()}.json"

    async def transcribe(
        self, data: bytes, content_type: str, language: str, region: Region
    ) -> Transcript:
        guard_region(held_in=self._region, asked_from=region)
        found = self.path_of(data)
        if not found.is_file():
            return NOTHING_HEARD
        loaded = json.loads(found.read_text(encoding="utf-8"))
        return Transcript(
            text=str(loaded.get("text", "")),
            confidence=float(loaded.get("confidence", 0.0)),
            language=loaded.get("language") or language,
        )
