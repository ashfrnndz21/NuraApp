"""A conformance suite any `Voice` adapter must pass (E22-03).

`assert_voice_conformance(make_voice, tmp_path)` walks the same properties for whichever
adapter `make_voice()` returns — proven here against the fixture
(`test_voice_conformance.py`), and meant for a future regional provider's own test to import
and run against itself, unchanged. That is the whole point of the port: an adapter that
passes this needs no change from any caller.

What it holds every adapter to: the language it is asked for is the language it answers in;
the audio it returns is under the thirty-second bound and is as long as it says it is; the
script's own pauses are heard — the boundary's longer than an ordinary line's, not just the
same pause repeated; Hokkien and Tamil wait for T2; and a note run past the limit is refused
before anything is asked to say it. The last two are the `Voice` port's own promise
(`app.delivery.voice.voiced`, `voice_language`) and hold for any adapter beneath it — proven
here so a new adapter's test never has to reimplement either, only run this.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from app.delivery.voice import MAX_SECONDS, NoVoiceFor, TooLongToSay, Voice, voiced, wav_seconds
from app.ingestion.objects import LocalObjectStore
from app.language.voice_script import BOUNDARY_PAUSE_MS, PAUSE_MS, Segment, VoiceScript
from app.regions import Region

LINES: dict[str, list[str]] = {
    "en": ["Your blood pressure today was 138 over 84.", "It is in your blood pressure book."],
    "ms": ["Tekanan darah anda hari ini ialah 138 atas 84.", "Ia ada dalam buku tekanan darah anda."],
    "zh": ["您今天的血压是138比84。", "它在您的血压本里。"],
}
"""One line pair per T1 language: enough for a script with more than one segment, short
enough to stay well under the length bound."""

TOO_LONG = ["This line is one of many lines that together run far too long."] * 12


async def assert_voice_conformance(make_voice: Callable[[], Voice], tmp_path: Path) -> None:
    """Every adapter behind the `Voice` port passes this, unchanged. Call it from the
    adapter's own test with a factory that returns a fresh instance each time it is called."""
    store = LocalObjectStore(tmp_path, Region.SG)

    # The language it is asked for is the language it answers in, under the length bound,
    # and the audio it hands back is as long as it says it is.
    for language, lines in LINES.items():
        said = await voiced(
            store,
            make_voice(),
            profile_id=uuid.uuid4(),
            region=Region.SG,
            lines=lines,
            language=language,
        )
        assert said.spoken.language == language
        assert 0 < said.spoken.duration_seconds <= MAX_SECONDS
        if said.spoken.content_type == "audio/wav":
            assert wav_seconds(said.spoken.audio) == said.spoken.duration_seconds

    # The script's own pauses are heard: the boundary's longer than an ordinary line's, not
    # the same silence whatever the script asked for.
    voice = make_voice()
    line = Segment("One line on its own.", PAUSE_MS)
    boundary_line = Segment("One line on its own.", BOUNDARY_PAUSE_MS)
    said_line = await voice.speak(VoiceScript("en", (line,)))
    said_boundary = await voice.speak(VoiceScript("en", (boundary_line,)))
    assert said_boundary.duration_seconds > said_line.duration_seconds
    assert said_boundary.duration_seconds - said_line.duration_seconds == pytest.approx(
        (BOUNDARY_PAUSE_MS - PAUSE_MS) / 1000, abs=0.05
    )

    # Hokkien and Tamil wait for T2: refused before anything is asked to say them.
    for later in ("nan", "ta"):
        with pytest.raises(NoVoiceFor):
            await voiced(
                store,
                make_voice(),
                profile_id=uuid.uuid4(),
                region=Region.SG,
                lines=["Hello."],
                language=later,
            )

    # A note run past the limit is refused before anything is asked to say it.
    with pytest.raises(TooLongToSay):
        await voiced(
            store,
            make_voice(),
            profile_id=uuid.uuid4(),
            region=Region.SG,
            lines=TOO_LONG,
            language="en",
        )
