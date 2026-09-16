"""The spoken twin: the `Voice` port, the fixture behind it, and the cache (E11-04, E22-03).

Every card is also a voice script (docs/plain-words.md §4, `app.language.voice_script`).
`Voice.speak(script)` is given the whole script — one segment per line, and the silence to
leave after each one, the boundary's own longer than the rest — and turns it into audio,
saying how long it runs. A provider that can control its own pauses (SSML `<break>`, or
whatever its API calls it) reads `segment.pause_ms` off each one; a provider that cannot
still reads the words in order and the fixture's own duration still counts every pause, so a
test and the checkpoint hold the length to the rule without a speech provider. A voice note
stays under thirty seconds (`MAX_SECONDS`, `TooLongToSay`); English, Malay and Mandarin at
T1, and Hokkien and Tamil at T2 (`NoVoiceFor` until then). A conformance suite any adapter
must pass is `tests/voice_conformance.py`, proven here against the fixture.

Rendered audio is a derived cache, not a record: it is Nura saying its own lines, not anyone's
voice, so it is never a VOICE artefact and never an Artifact row (ADR 0003, addendum). It is
kept in the region's object store under the profile, by the voice that said it and the digest
of the card's voice script (`app.language.voice_script`, E22-03: the same words and pauses,
the same digest, wherever they appear) — `voice/<profile_id>/<voice>/<digest>` — and read
back from there the next time the same card is played. What is said is the script's
`spoken()` form: numbers and dates as a voice says them, the words otherwise the card's own. The store is pinned to one region, like every byte of his.
"""

from __future__ import annotations

import re
import struct
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.errors import Refusal
from app.fixtures import fixture
from app.ingestion.objects import NoSuchObject, ObjectStore, check_key
from app.language.voice_script import VoiceScript, script_for
from app.regions import Region, guard_region
from app.settings import Settings

VOICE_LANGUAGES = ("en", "ms", "zh")
"""Spoken at T1. Hokkien and Tamil join at T2, with a recorded or vendor voice."""
MAX_SECONDS = 30.0
"""A voice note is under thirty seconds: as long as he can hold in his head."""
WORDS_PER_SECOND = 2.2
"""His pace in English and Malay: a little slower than speech on the radio (rate 0.9)."""
CHARACTERS_PER_SECOND = 3.5
"""The same pace in Mandarin, by character."""
PAUSE_SECONDS = 0.5
"""The pause between two lines: one idea, then a breath, then the next."""
SAMPLE_RATE = 8000
WAV = "audio/wav"

_HAN = re.compile(r"[㐀-鿿]")


class NoVoiceFor(Refusal):
    """No voice in this language yet: English, Malay and Mandarin now; Hokkien, Tamil at T2."""


class TooLongToSay(Refusal):
    """A voice note is under thirty seconds, and these lines would run longer."""


class NoVoiceProvider(RuntimeError):
    """No speech provider can say anything here. The process must not start on this setting."""


@dataclass(frozen=True, slots=True)
class Spoken:
    audio: bytes
    content_type: str
    duration_seconds: float
    language: str


class Voice(Protocol):
    @property
    def name(self) -> str: ...

    async def speak(self, script: VoiceScript) -> Spoken:
        """The script's segments, said in its language, as WAV audio, with the silence the
        script asks for after each one — the boundary's own longer than the rest — and how
        long the whole of it runs."""
        ...


def voice_language(asked: str | None) -> str:
    """One of the languages there is a voice for, or `NoVoiceFor`."""
    code = (asked or "").lower()[:2]
    if code in VOICE_LANGUAGES:
        return code
    raise NoVoiceFor(f"no voice in {asked!r} yet; Hokkien and Tamil come at T2")


def seconds_to_say(text: str, language: str) -> float:
    """How long the lines take at his pace, with a flat pause after each one: an estimate
    used where only the words are at hand, not a script (composing a card, budgeting a
    clip). Where a script exists, `seconds_for_script` is the true figure — it is what the
    boundary's own longer pause is for, which this cannot see."""
    total = 0.0
    for line in (one.strip() for one in text.splitlines()):
        if not line:
            continue
        characters = len(_HAN.findall(line))
        words = len(_HAN.sub(" ", line).split())
        total += characters / CHARACTERS_PER_SECOND + words / WORDS_PER_SECOND + PAUSE_SECONDS
    return round(total, 1)


def seconds_for_script(script: VoiceScript) -> float:
    """How long a script runs at his pace: each segment's own words, then its own pause —
    the boundary's longer than the rest. What `Voice.speak` is held to, and what the fixture
    times itself against."""
    total = 0.0
    for segment in script.segments:
        characters = len(_HAN.findall(segment.text))
        words = len(_HAN.sub(" ", segment.text).split())
        total += characters / CHARACTERS_PER_SECOND + words / WORDS_PER_SECOND
        total += segment.pause_ms / 1000
    return round(total, 1)


def silence(seconds: float) -> bytes:
    """A mono 8-bit WAV of silence, `seconds` long."""
    data = b"\x80" * round(seconds * SAMPLE_RATE)
    fmt = struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE, 1, 8)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVE"
        + b"fmt "
        + fmt
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )


def wav_seconds(audio: bytes) -> float:
    """How long a WAV runs, read from its header."""
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    rate = struct.unpack("<I", audio[24:28])[0]
    block = struct.unpack("<H", audio[32:34])[0]
    size = struct.unpack("<I", audio[40:44])[0]
    return round(size / (rate * block), 1)


@fixture
class FixtureVoice:
    """Silence as long as the script runs, its pauses counted like any other adapter's would
    be. Deterministic: the same script, the same bytes."""

    name = "fixture"

    async def speak(self, script: VoiceScript) -> Spoken:
        seconds = seconds_for_script(script)
        return Spoken(
            audio=silence(seconds),
            content_type=WAV,
            duration_seconds=seconds,
            language=script.language,
        )


def voice_for(settings: Settings) -> Voice:
    """The fixture on a declared dev run or demo (ADR 0008, `app.fixtures`); anywhere else
    there is no speech provider yet, and a process that cannot speak a card must not pretend
    to with silence."""
    if settings.fixtures_allowed:
        return FixtureVoice()
    raise NoVoiceProvider(
        "no speech provider is built; the fixture voice runs only on a dev run "
        "(NURA_DEV_CODE_SENDER=1) or a demo (NURA_DEMO_MODE=1)"
    )


def cache_key(profile_id: uuid.UUID, voice_name: str, digest: str) -> str:
    """Where a rendering is kept: under the profile and the voice that said it, by the voice
    script's digest (its language, its words and its pauses)."""
    return check_key(f"voice/{profile_id}/{voice_name}/{digest}")


@dataclass(frozen=True, slots=True)
class Voiced:
    spoken: Spoken
    key: str
    cached: bool
    """True when the audio came back from the store rather than from the voice."""


async def voiced(
    store: ObjectStore,
    voice: Voice,
    *,
    profile_id: uuid.UUID,
    region: Region,
    lines: Sequence[str],
    language: str | None,
    boundary: str | None = None,
) -> Voiced:
    """The spoken twin of these lines: from the region's store when it has been said before,
    otherwise said now and kept there. Refused before anything is said when the lines would
    run past thirty seconds, or when there is no voice in the language yet."""
    code = voice_language(language)  # before the script: a T2 language is refused, not guessed
    script = script_for(lines, code, boundary=boundary)
    estimate = seconds_for_script(script)
    if estimate > MAX_SECONDS:
        raise TooLongToSay(f"{estimate} seconds is over {MAX_SECONDS:g}")
    guard_region(held_in=store.region, asked_from=region)
    key = cache_key(profile_id, voice.name, script.digest)
    try:
        audio = await store.get(key)
    except NoSuchObject:
        pass
    else:
        return Voiced(Spoken(audio, WAV, wav_seconds(audio), code), key, cached=True)
    spoken = await voice.speak(script)
    if spoken.duration_seconds > MAX_SECONDS:
        raise TooLongToSay(f"{spoken.duration_seconds} seconds is over {MAX_SECONDS:g}")
    await store.put(key, spoken.audio)
    return Voiced(spoken, key, cached=False)
