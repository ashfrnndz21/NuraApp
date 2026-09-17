"""The Narrator port: what says a trace's real steps aloud, one line per step already taken.

Ask (`app.search.ask.recall_stream`) and Find (`app.delivery.feed.find.find_stream`) stream a
`step` event the instant a real part of the record is read — never invented, never delayed for
effect (docs/design-direction.md "Conversation, waiting and thinking"). Until now every step's
label was the catalogue's own line (`app.delivery.timeline_strings.ASK_STEPS`, `app.delivery.
strings.FIND_STEPS`), read once and said exactly the same way every time. A `Narrator` may say
it livelier instead — the owner wants the trace to feel like a model narrating, in the demo —
but it can only ever rephrase a step that really happened; it cannot add one, slow one down, or
change what the answer itself is (untouched, the rule-based retriever's).

A step crosses this seam exactly as far as `backend/CLAUDE.md` allows: its id, the catalogue's
own label for it — already read, already real, already in the right voice (his own, or a
caregiver's twin by his name) — and how many things that part of the record held. Never a row,
never a fact's value, never free text off the record. `FixtureNarrator` is today's behaviour
unchanged, and the default; `app.llm.narrate.ClaudeNarrator` is the demo-only adapter that may
vary the words, never the facts — it lives under `app/llm/`, not here, because nothing under
`app/search/` may import the SDK or reach the network (`tests/test_recall.py::
test_recall_calls_no_model`; `backend/CLAUDE.md` model calls go through `app/llm/`).
`narrator_for` (`app.search.narrator_provider`) is the one place a deployment chooses between
them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.channels.about_him import Reader
from app.fixtures import fixture


@dataclass(frozen=True, slots=True)
class NarratedStep:
    """One real step of a trace, as far as a `Narrator` may see it. `label` is the catalogue's
    own line for it, already read under this reader's voice — the ground truth a livelier line
    may only rephrase, never depart from or add to. `count` is how many things that part of the
    record held, when the step carries one; 0 where it does not (Find's single "searching"
    step, before any result is known)."""

    key: str
    label: str
    count: int = 0


@dataclass(frozen=True, slots=True)
class NarratedLine:
    """One line for one step, in the reader's voice, already safe to send: `ClaudeNarrator`
    never yields one that has not passed the plain-words verifier and the caregiver-voice
    check; `FixtureNarrator` needs neither, its line always being the catalogue's own."""

    key: str
    text: str


class Narrator(Protocol):
    """Says a trace's real steps aloud, one line per step given — streamed, never delayed for
    it: every step it is asked about already happened, so nothing here waits on anything but
    the line itself. `steps` is the whole trace so far, oldest first; a caller reads the line
    for the step it just added and lets the rest go, so the words already shown for an earlier
    step never change under it."""

    external_processor: str | None
    """Not None when every call reaches a processor outside the region (`ClaudeNarrator`,
    ADR 0017): a caller writes the reach to the audit trail before the first call, the way
    `app.ingestion.review.review_artifact` does for the extractor. None for a narrator that
    never reaches outside this deployment (`FixtureNarrator`)."""

    def narrate(
        self, steps: Sequence[NarratedStep], *, language: str, reader: Reader
    ) -> AsyncIterator[NarratedLine]:
        """One `NarratedLine` per entry of `steps`, in order."""
        ...


@fixture
class FixtureNarrator:
    """Today's behaviour, unchanged, and the default: the catalogue's own label for each step,
    exactly as the routes said it before this port existed. No call, no delay, nothing to fall
    back from — asked and answered are the same words."""

    external_processor: str | None = None

    async def narrate(
        self, steps: Sequence[NarratedStep], *, language: str, reader: Reader
    ) -> AsyncIterator[NarratedLine]:
        for step in steps:
            yield NarratedLine(key=step.key, text=step.label)
