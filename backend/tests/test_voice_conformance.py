"""E22-03: the fixture proven against the `Voice` conformance suite.

`FixtureVoice` is the only adapter Nura has — there is still no licensed speech provider in
the region (docs/parity.md, E22-03). What this file proves is the seam, not the provider: a
future regional adapter runs the same suite (`tests.voice_conformance`) unchanged and, if it
passes, drops into `app.channels.api.deps` with no caller anywhere touched.
"""

from __future__ import annotations

from pathlib import Path

from app.delivery.voice import FixtureVoice
from tests.voice_conformance import assert_voice_conformance


async def test_the_fixture_passes_the_voice_conformance_suite(tmp_path: Path) -> None:
    await assert_voice_conformance(FixtureVoice, tmp_path)
