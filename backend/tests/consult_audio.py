"""The consult recordings of the first family, as the tests, the checkpoint and the web's
end-to-end run send them (E02-05).

No audio is committed. A recording is a small deterministic byte string that starts the way a
webm does — the four bytes a recorder's container opens with — then a marker and a label. Its
sha256 names what the fixture transcriber heard (`tests/fixtures/voice/`), who the fixture
separator says spoke when (`tests/fixtures/speakers/`), and the transcript's own digest names
what the fixture summariser heard in it (`tests/fixtures/visits/consult-bp-review.json`).
`scripts/checkpoints/cp22.py` and `web/tests/e2e/visit.spec.ts` carry the same one-line
generator, so they send the same bytes without importing anything from here.
"""

from __future__ import annotations

import hashlib

WEBM_MAGIC = b"\x1a\x45\xdf\xa3"
"""How a webm opens: the EBML header's identifier."""

CONSULT = "consult-bp-review"
"""Dr Tan's blood pressure review as a recording is heard: the notice, his yes as the first
seconds after it, the visit, Pa's question and Mei's word — eleven stretches, 66 seconds."""

RED_FLAG_CONSULT = "consult-red-flag"
"""A visit at which Dr Tan hears of chest pain (#155): heard as the words of
`tests/fixtures/visits/red-flag-chest-pain.json`, so the card carries the flag."""

CONTENT_TYPE = "audio/webm;codecs=opus"
DURATION_S = 66.0


def placeholder_consult(label: str) -> bytes:
    """The bytes that stand in for one recording. Same label, same bytes, same digest."""
    return WEBM_MAGIC + b"nura-consult-placeholder:" + label.encode("ascii") + b"\n"


def digest_of(label: str) -> str:
    return hashlib.sha256(placeholder_consult(label)).hexdigest()
