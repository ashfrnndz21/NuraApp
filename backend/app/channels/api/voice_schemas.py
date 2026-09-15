"""The voice script on the wire (E22-03): what every card that has a spoken twin also carries.

`VoiceScriptOut.of(lines, language, boundary)` is `app.language.voice_script.script_for` over
the same lines the card answers with — its voice twin where it has one — so the client, a
voice note and a screen reader all say the words that passed the verifier and no others.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from app.language.voice_script import script_for


class SegmentOut(BaseModel):
    text: str
    pause_ms: int


class VoiceScriptOut(BaseModel):
    language: str
    digest: str
    """The sha256 of the words and pauses: what pre-rendered audio is kept under."""
    segments: list[SegmentOut]

    @classmethod
    def of(cls, lines: Sequence[str], language: str, boundary: str | None = None) -> VoiceScriptOut:
        script = script_for(lines, language, boundary=boundary)
        return cls(
            language=script.language,
            digest=script.digest,
            segments=[SegmentOut(text=s.text, pause_ms=s.pause_ms) for s in script.segments],
        )
