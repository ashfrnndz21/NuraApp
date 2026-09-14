"""The speaker separator port: who spoke when in a consult recording (E02-05).

    Consult recording with consent prompt, transcription, speaker separation and timestamps.

A transcriber (`app.ingestion.transcribe`) hears the words; a `SpeakerSeparator` says who
said which of them and when: a list of `Segment`s — patient, doctor, family or unknown, a
start and an end in seconds, and the words of that stretch. Like the transcriber it is a
provider in the profile's region, and nothing in Nura calls one directly.

`align` is where a separator's answer meets the record: each segment's words are found, in
order, in the transcript the transcriber heard, so a segment is kept as a pointer into the
transcript artefact (`char_start`, `char_end`) and a time in the audio — never as words in a
row. An answer that does not fit the transcript, or runs backwards in time, is not guessed
at: `SegmentsDoNotFit`, and the recording is kept with no speakers.

`FixtureSeparator` answers from `backend/tests/fixtures/speakers/<sha256 of the audio>.json`.
`Unseparated` is what runs where no separator is configured: the whole transcript as one
stretch by an unknown speaker — honest, and still a time a clip can be played from.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.errors import Refusal
from app.ingestion.models import Speaker
from app.ingestion.transcribe import Transcript
from app.regions import Region, guard_region


@dataclass(frozen=True, slots=True)
class Segment:
    """One stretch of the recording: who, from when to when (seconds), and what was said."""

    speaker: Speaker
    start_s: float
    end_s: float
    text: str


@dataclass(frozen=True, slots=True)
class Aligned:
    """A segment as it is kept: who, when in the audio, and where its words are in the
    transcript. No words."""

    speaker: Speaker
    start_s: float
    end_s: float
    char_start: int
    char_end: int


class SegmentsDoNotFit(Refusal):
    """The separator's segments are not the transcript's words in order, or their times run
    backwards. Nothing is guessed: the recording is kept, with no speakers."""


class SpeakerSeparator(Protocol):
    """Who spoke when, in one region."""

    @property
    def region(self) -> Region: ...

    async def separate(
        self, transcript: Transcript, audio: bytes, region: Region
    ) -> Sequence[Segment]: ...


def align(text: str, segments: Sequence[Segment]) -> list[Aligned]:
    """Each segment's words found in `text`, in order, with its times; or `SegmentsDoNotFit`.

    Times must not run backwards: each segment starts at or after the last one's start, and
    ends after it starts. The words are matched after trimming, exactly, from where the last
    segment ended — so two segments cannot claim the same words.
    """
    aligned: list[Aligned] = []
    cursor = 0
    last_start = 0.0
    for segment in segments:
        words = segment.text.strip()
        if not words:
            raise SegmentsDoNotFit("a segment with no words")
        if segment.start_s < 0 or segment.end_s <= segment.start_s or segment.start_s < last_start:
            raise SegmentsDoNotFit("a segment whose times run backwards")
        at = text.find(words, cursor)
        if at < 0:
            raise SegmentsDoNotFit("a segment whose words are not next in the transcript")
        aligned.append(
            Aligned(segment.speaker, segment.start_s, segment.end_s, at, at + len(words))
        )
        cursor = at + len(words)
        last_start = segment.start_s
    return aligned


class FixtureSeparator:
    """Answers from `root/<sha256 of the audio>.json` — `{"segments": [{"speaker", "start_s",
    "end_s", "text"}]}` — and with no segments for audio it has no file for."""

    def __init__(self, root: Path, region: Region) -> None:
        self._root = Path(root)
        self._region = region

    @property
    def region(self) -> Region:
        return self._region

    def path_of(self, audio: bytes) -> Path:
        return self._root / f"{hashlib.sha256(audio).hexdigest()}.json"

    async def separate(
        self, transcript: Transcript, audio: bytes, region: Region
    ) -> Sequence[Segment]:
        guard_region(held_in=self._region, asked_from=region)
        found = self.path_of(audio)
        if not found.is_file():
            return ()
        loaded = json.loads(found.read_text(encoding="utf-8"))
        return tuple(
            Segment(
                speaker=Speaker(str(one["speaker"])),
                start_s=float(one["start_s"]),
                end_s=float(one["end_s"]),
                text=str(one["text"]),
            )
            for one in loaded.get("segments", [])
        )


class Unseparated:
    """No separator configured: the whole transcript is one stretch by an unknown speaker,
    from the start of the recording to its end. It says nothing it did not hear."""

    def __init__(self, region: Region, duration_s: float | None = None) -> None:
        self._region = region
        self._duration_s = duration_s

    @property
    def region(self) -> Region:
        return self._region

    async def separate(
        self, transcript: Transcript, audio: bytes, region: Region
    ) -> Sequence[Segment]:
        guard_region(held_in=self._region, asked_from=region)
        if not transcript.heard:
            return ()
        return (Segment(Speaker.UNKNOWN, 0.0, self._duration_s or 1.0, transcript.text.strip()),)


__all__ = [
    "Aligned",
    "FixtureSeparator",
    "Segment",
    "SegmentsDoNotFit",
    "SpeakerSeparator",
    "Unseparated",
    "align",
]
