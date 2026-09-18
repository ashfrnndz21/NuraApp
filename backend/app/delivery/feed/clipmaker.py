"""ClipMaker (RE-07, item 1): a Nura-made explainer clip, 20-30 seconds, its captions shown
line by line over one of the kit's warm scenes — never a photo of him or of his medicine, and
never a third-party video (`app.delivery.feed.clips` is the other kind, the publisher's own
segment; this module never fetches or serves a still or a video file).

Two adapters behind one port, the way the feed's own search and compression already are
(`app.delivery.feed.compress`): `RuleClipMaker` composes a script from lines the catalogue
already carries — `app.medicines.story`'s purpose line for a new medicine, a lab reading's own
catalogue line — so it needs no model and no network, and is what the demo and every test run
on. `ClaudeClipMaker` (`NURA_CLIPMAKER=claude`, gated the same way every other Claude-backed
adapter is, `app.llm.residency.allow_external_model`) writes a short script from his own new
evidence plus the text of one allowlisted page it fetches through the existing `Searcher`
port — never a page of its own choosing, never a page off the allowlist.

**What a script may not carry.** Every line — whichever adapter wrote it — is checked before
it is kept: `app.delivery.timeline_strings.verified` (`docs/plain-words.md`, the same check
every other line spoken to him passes), `app.delivery.feed.compress.changes_treatment` (a line
that would start, stop or change a medicine), and the conclusion-or-advice words
`app.llm.narrate` already holds every rephrase to (`_has_conclusion_language`) — the same
blocklist, not a second copy of it. A line that trips any of these is dropped, not the whole
script; a script the catalogue or the model gave nothing safe to say is `None`, the same clean
"nothing for him" every port in this package already answers failure with. The boundary line
(`app.safety.boundary.boundary_line`, `Surface.LEARNING_CARD`) is appended last, always, and
is never itself checked against the blocklist above (it is this module's own words, not the
model's or the catalogue's).

**The captions.** `app.delivery.feed.clips.caption_cues` already times a card's lines the way
its voice says them (`app.delivery.voice.seconds_to_say`, his pace); this module calls the
same function so a Nura-made clip's captions advance in step with `Hear` (`app.delivery.feed.
clips.clip_captions`, unchanged) and with the phone's own on-device voice
(`web/src/speech/speak.ts`) the same way every other card's spoken twin already does — nothing
new is added to the playback path, only a script for it to read. `ClipScript.captions` is the
same timing carried as `{at_ms, text}` pairs, milliseconds from the clip's start, for the
card's `cite` to keep — so a caregiver's Why sheet or a test can read the timing back without
recomputing it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from app.delivery.feed.clips import CLIP_LONGEST, CLIP_SHORTEST, caption_cues
from app.delivery.feed.compress import Found, Searcher, changes_treatment
from app.delivery.strings import language_for, learning_lines
from app.delivery.timeline_strings import verified
from app.llm.narrate import _has_conclusion_language  # the one blocklist, not a second copy
from app.safety.boundary import YOUR_DOCTOR

if TYPE_CHECKING:
    # Only for mypy: `explainer_clip_item`'s own docstring explains why the real imports stay
    # local to the function at runtime (this module is imported with no database at all by
    # `app.demo_seed` and by tests that build a `ClipScript` alone). A `TYPE_CHECKING` import
    # costs nothing at import time and lets every caller's argument be checked for real.
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.delivery.feed.models import FeedItem
    from app.keys.context import KeyContext
    from app.keys.scopes import Scope
    from app.state.service import StateView

MIN_LINES = 4
MAX_LINES = 6
"""A Nura-made clip's script: 4-6 lines, the same shape as the reference clip cards
(docs/prototype.html) — long enough to explain one thing, short enough to stay 20-30s."""

SCENES: tuple[str, ...] = ("morning", "food", "clinic", "family", "walk")
"""The kit's warm scenes (docs/prototype.html `.scene`): gradients the web client already
knows how to draw. Never a photo — nothing here names or fetches an image."""

_SCENE_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("clinic", ("blood pressure", "tablet", "medicine", "dose", "pill", "clinic", "doctor", "result")),
    ("food", ("diet", "food", "meal", "salt", "sugar", "eat")),
    ("walk", ("exercise", "walk", "activity", "steps", "week")),
    ("family", ("family", "care", "caregiver")),
)
"""Ordered so the first match wins: a topic naming both a tablet and a meal ("your blood
pressure tablet and your food") is his clinic scene first, the one the reference card shows
for a new medicine."""


def scene_for(topic: str) -> str:
    """One of `SCENES`, chosen by what the clip is about. Never guessed past the list; a
    topic that matches nothing gets the calm default, `"morning"`."""
    words = topic.strip().lower()
    for scene, keywords in _SCENE_WORDS:
        if any(keyword in words for keyword in keywords):
            return scene
    return "morning"


@dataclass(frozen=True, slots=True)
class ClipCaption:
    at_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class ClipScript:
    """A Nura-made clip, ready for a card: `lines` is the voice script (already ending on the
    boundary), `captions` the same lines timed from the clip's start. `source` is who or what
    it rests on in his words ("Nura", or an allowlisted publisher's name for the Claude
    adapter); `cite_url`, only for the Claude adapter, is the one page it read."""

    language: str
    lines: tuple[str, ...]
    captions: tuple[ClipCaption, ...]
    scene: str
    source: str
    duration_ms: int
    headline: str
    why_topic: str
    boundary: str
    cite_url: str | None = None


@dataclass(frozen=True, slots=True)
class ClipTopic:
    """What a Nura-made clip is asked to explain: his own evidence, in words a search or a
    prompt can use, the catalogue lines already drawn from it (`RuleClipMaker`'s only
    material), and the words a card's headline and why line need."""

    why_topic: str
    """His words for what the clip is about ("your blood pressure tablet")."""
    headline: str
    evidence: str
    """A plain description of the new thing on his record this clip explains (a new medicine
    reconciled, a new result) — never a row, never free text off a form; the caller writes it
    from typed fields, the same discipline `app.delivery.feed.search` already holds a
    compressor's grounding facts to."""
    catalogue_lines: tuple[str, ...] = ()
    """Lines already drawn from a catalogue (`app.medicines.story.medication_story`'s
    `purpose`, a reading's own line) — `RuleClipMaker`'s script, verbatim, before the
    boundary. Ignored by `ClaudeClipMaker`."""
    doctor: str | None = None


def _script_lines(lines: Sequence[str], language: str) -> list[str]:
    """Every line that passes the plain-words check, the treatment-change check and the
    conclusion-or-advice blocklist, in order — a diagnosis or advice line is dropped, not the
    whole script."""
    kept: list[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if not verified(text, language):
            continue
        if changes_treatment([text]):
            continue
        if _has_conclusion_language(text, language):
            continue
        kept.append(text)
    return kept


def _script(
    lines: Sequence[str],
    *,
    language: str,
    scene: str,
    source: str,
    headline: str,
    why_topic: str,
    doctor: str | None,
    cite_url: str | None = None,
) -> ClipScript | None:
    """The shared tail of both adapters: gate the lines, cap them, hand them to
    `app.delivery.strings.learning_lines` — the same catalogue machinery every other learning
    card, local alert and food card already builds its `Lines` through — so the why line and
    the "this comes from {source}" line are the catalogue's own whole sentences, not raw words
    of this module's, and so `items.create_item`'s own plain-words check
    (`app.delivery.timeline_strings.verified`, run again per line above) never disagrees with
    what this function already checked. `None` when nothing safe is left to say."""
    kept = _script_lines(lines, language)[:MAX_LINES]
    if len(kept) < MIN_LINES:
        # Not "pad with filler": a script left with fewer than MIN_LINES safe lines is not a
        # 20-30s clip, whatever gated it down (too little material, or lines the safety
        # checks above dropped) — it is not made at all, the same clean "nothing for him"
        # every port in this package already answers failure with.
        return None
    told = learning_lines(
        language,
        headline=headline,
        body=tuple(kept),
        topic=why_topic,
        source_name=source,
        doctor=doctor or YOUR_DOCTOR.get(language_for(language), YOUR_DOCTOR["en"]),
    )
    cues = caption_cues(list(told.voice), told.language, boundary=told.boundary)
    captions = tuple(ClipCaption(at_ms=round(start * 1000), text=text) for start, _, text in cues)
    duration_ms = round(cues[-1][1] * 1000) if cues else 0
    return ClipScript(
        language=told.language,
        lines=tuple(told.voice),
        captions=captions,
        scene=scene,
        source=source,
        duration_ms=duration_ms,
        headline=told.headline,
        why_topic=told.why,
        boundary=told.boundary or "",
        cite_url=cite_url,
    )


class ClipMaker(Protocol):
    def make(self, topic: ClipTopic, language: str) -> ClipScript | None:
        """A clip script for this topic, in this language, or `None` when there is nothing
        safe enough, or grounded enough, to make one from."""
        ...


class RuleClipMaker:
    """Composes a script from the catalogue's own explainer lines — `topic.catalogue_lines`,
    already drawn by the caller from `app.medicines.story` or another catalogue module. No
    model, no network, no fixture file: the same lines the medicine's own story already says,
    said again as a clip. This is what the demo, and every deterministic test, run on."""

    def make(self, topic: ClipTopic, language: str) -> ClipScript | None:
        if not topic.catalogue_lines:
            return None
        return _script(
            topic.catalogue_lines,
            language=language,
            scene=scene_for(topic.why_topic),
            source="Nura",
            headline=topic.headline,
            why_topic=topic.why_topic,
            doctor=topic.doctor,
        )


_LINES_SCHEMA = {
    "name": "clip_script",
    "schema": {
        "type": "object",
        "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
        "required": ["lines"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _clip_prompt(evidence: str, page_title: str, page_text: str, language: str) -> str:
    return (
        f"Write 4 to 6 short spoken lines, in language code {language!r}, for a 20-30 second "
        "video explaining something new on a family member's health record to the elderly "
        "patient it is about, grounded only on the evidence below and on the page text below "
        "it. Never write a line that would tell him to start, stop, double, reduce or "
        "otherwise change a medicine or its dose, and never write a line that states what a "
        "number or a result means for him, or gives him advice — that is for his doctor, not "
        "this clip.\n\nEvidence:\n" + evidence.strip() + f"\n\nPage ({page_title}):\n" + page_text
    )


class ClaudeClipMaker:
    """The `ClipMaker` port, answered for real: one allowlisted page fetched through the
    existing `Searcher` (`app.delivery.feed.compress.Searcher`, never a searcher of this
    module's own), and one structured-output call asking for a handful of spoken lines
    grounded on his evidence and that page. Gated the same way every other Claude-backed
    adapter in this codebase is (`app.llm.residency.allow_external_model`): a declared demo
    or a declared dev run, and a key, or it refuses to construct."""

    MODEL = "claude-opus-5"

    def __init__(
        self,
        *,
        searcher: Searcher,
        domains: Sequence[str],
        api_key: str | None,
        demo_mode: bool,
        dev_run: bool = False,
        client: Any | None = None,
    ) -> None:
        from app.delivery.feed.claude_adapters import ClaudeAdapterNotAvailable, _client
        from app.llm.residency import allow_external_model

        allow_external_model(
            demo_mode=demo_mode, dev_run=dev_run, refusal=ClaudeAdapterNotAvailable, what="the Claude clip maker"
        )
        if not api_key:
            raise ClaudeAdapterNotAvailable("the Claude clip maker needs ANTHROPIC_API_KEY set")
        self._searcher = searcher
        self._domains = [d.strip().lower() for d in domains if d.strip()]
        self._client = client if client is not None else _client(api_key)

    def _one_page(self, terms: Sequence[str]) -> Found | None:
        for term in terms:
            found = self._searcher.search("clip", [term], self._domains)
            if found:
                return found[0]
        return None

    def make(self, topic: ClipTopic, language: str) -> ClipScript | None:
        from app.delivery.feed.claude_adapters import _structured_json

        page = self._one_page([topic.why_topic])
        if page is None or not page.text.strip():
            return None
        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=2048,
                output_config={"format": {"type": "json_schema", "json_schema": _LINES_SCHEMA}},
                messages=[
                    {
                        "role": "user",
                        "content": _clip_prompt(topic.evidence, page.title, page.text, language),
                    }
                ],
            )
        except Exception:  # noqa: BLE001 — a failed call makes nothing, never a guess
            return None
        if getattr(response, "stop_reason", None) == "refusal":
            return None
        payload = _structured_json(response)
        if payload is None:
            return None
        lines = [str(line) for line in payload.get("lines", []) or [] if str(line).strip()]
        if not lines:
            return None
        return _script(
            lines,
            language=language,
            scene=scene_for(topic.why_topic),
            source=page.domain,
            headline=topic.headline,
            why_topic=topic.why_topic,
            doctor=topic.doctor,
            cite_url=page.url,
        )


def clip_length_ok(script: ClipScript) -> bool:
    """Whether a script's narration falls in the 20-30s a clip keeps (`app.delivery.feed.
    clips.CLIP_SHORTEST`/`CLIP_LONGEST`) — the same window the publisher's own segment is
    held to, checked here so a caller can decide whether a script is short or long enough to
    show as a clip rather than a plain learning card."""
    seconds = script.duration_ms / 1000
    return CLIP_SHORTEST <= seconds <= CLIP_LONGEST


def cite_of(script: ClipScript) -> dict[str, object]:
    """The card's `cite` for a Nura-made clip: what `app.delivery.feed.clips` and the web
    client both read back — `kind` tells either apart from a publisher's segment (`cite["
    media"] == "video"`, `app.delivery.feed.compress.Found`), `captions` the same timing
    `ClipScript.captions` already carries, so a Why sheet or a test reads it without asking
    the voice pace again."""
    return {
        "kind": "nura_made",
        "scene": script.scene,
        "source": script.source,
        "duration_ms": script.duration_ms,
        "captions": [{"at_ms": cue.at_ms, "text": cue.text} for cue in script.captions],
        "cite_url": script.cite_url,
    }


async def explainer_clip_item(
    session: AsyncSession,
    *,
    context: KeyContext,
    state: StateView,
    script: ClipScript,
    fact_ids: Sequence[str],
    scope: Scope,
    day_key: str,
    dedupe_key: str,
    expires_at: datetime,
    gap: str | None = None,
) -> FeedItem:
    """Write a Nura-made clip as a card, through the same choke point every other card is
    written through (`app.delivery.feed.items.create_item`) — never a raw row. A thin seam:
    the caller (today, `app.demo_seed`; RE-07's gap-driven planner once it is wired to offer
    this alongside the search job, deliberately left for a later story) already has the
    `StateView`, the `KeyContext` and the day's own keys every other card uses; this only
    turns a `ClipScript` into the `Lines`/`Why`/`cite` shape `create_item` asks for.

    Imports are local, not at module level: this module is imported by `app.demo_seed` and
    by tests that build a `ClipScript` with no database at all, and the heavier chain behind
    `app.delivery.feed.items` (state, audit, keys) is only ever needed once a caller actually
    wants to write a row."""
    from app.delivery.feed.items import Why, create_item
    from app.delivery.feed.models import CardFormat, CardType, DeliverTo
    from app.delivery.strings import Lines

    lines = Lines(
        language=script.language,
        headline=script.headline,
        body=script.lines,
        voice=script.lines,
        why=script.why_topic,
        boundary=script.boundary,
    )
    return await create_item(
        session,
        context=context,
        state=state,
        type=CardType.CLIP,
        lines=lines,
        why=Why(kind="explainer_clip", plain=script.why_topic, fact_ids=tuple(fact_ids), gap=gap),
        scope=scope,
        deliver_to=DeliverTo.PATIENT,
        day=day_key,
        dedupe_key=dedupe_key,
        expires_at=expires_at,
        format=CardFormat.CLIP,
        cite=cite_of(script),
        self_made=True,
    )
