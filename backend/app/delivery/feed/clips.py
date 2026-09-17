"""Clips (E09-06, E11-09): a still or a licensed excerpt, narrated in his language, with
captions — behind one port, `ClipRenderer`, the way the voice is behind `Voice`.

**What a clip is here.** The narration is the card's spoken twin: its verified lines, said by
the one voice port (`app.delivery.voice`, `GET …/feed/{item}/voice`), under thirty seconds.
The captions are those same lines as WebVTT, each shown for as long as it takes to say
(`captions`), in the card's language. What the renderer adds is the picture: a still for
every clip, and — only where the publisher's licence allows reuse (`may_excerpt`) — the
20–30 seconds of the video itself, cut and kept on this server (`clips/<profile>/…` in the
region's object store). There is no third-party player and no embed: the phone asks this
server for the still and the excerpt, so no video platform learns who watched what. Where
the licence does not allow it, or the renderer has no excerpt, the clip is the still with the
narration and captions (docs/health-feed-spec.md §7), and the card links to the whole video
on the publisher's own site — a link he taps, never a page that opens itself.

**Nothing plays by itself.** These functions hand bytes to the phone when it asks; the card's
`autoplay` is false and the web player starts only from a tap (`web/src/feed/clip.ts`).

The fixture renderer serves one small committed still and never an excerpt, so no ffmpeg is
needed here. A real renderer (ffmpeg: cut the licensed excerpt, scale it, keep it as MP4; a
frame of it as the still) arrives behind the same port.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard
from app.audit.models import Action
from app.delivery.feed.models import CardFormat, FeedItem
from app.delivery.voice import seconds_to_say, voice_language
from app.errors import Refusal
from app.fixtures import fixture
from app.ingestion.objects import NoSuchObject, ObjectStore, check_key
from app.keys.context import KeyContext
from app.language.voice_script import script_for
from app.regions import guard_region

CLIP_SHORTEST = 20
CLIP_LONGEST = 30
"""The part of a video a clip keeps: 20 to 30 seconds (spec §2, E11-09)."""

REUSE_LICENCES = frozenset({"cc-by", "cc-by-sa", "permission"})
"""The licences under which the server may keep and serve an excerpt: a Creative Commons
licence that allows adapting with attribution (a clip is cut to 20–30 seconds and narrated
over, so it is a derivative — "no derivatives" does not allow it), or the publisher's written
permission. Any other — or none named — and the clip is the still with the narration."""

FEED_TARGET = FeedItem.__tablename__


class NotAClipCard(Refusal):
    """This card is not a clip: it has no still, no excerpt and no captions."""


class NoExcerpt(Refusal):
    """This clip is the still with the narration: the licence does not allow the server to
    keep the video, or no excerpt was made. The card links to the whole video instead."""


class NoClipRenderer(Refusal):
    """No clip renderer is configured here, so a clip has its narration and captions but
    no still."""


def may_excerpt(licence: str | None) -> bool:
    """Whether the server may keep and serve an excerpt under this licence."""
    return licence is not None and licence.strip().lower() in REUSE_LICENCES


def clip_length_ok(start_sec: int | None, end_sec: int | None) -> bool:
    """A clip keeps 20 to 30 seconds of the video, in order."""
    if start_sec is None or end_sec is None:
        return False
    return 0 <= start_sec < end_sec and CLIP_SHORTEST <= end_sec - start_sec <= CLIP_LONGEST


@dataclass(frozen=True, slots=True)
class ClipAsk:
    """What a renderer is asked for: a still for this card, and — only when the licence
    allows it — the excerpt of the video between `start_sec` and `end_sec`."""

    key: str
    """The card's clip key: where what is rendered is kept, and the same key for the same card."""
    language: str
    excerpt_url: str | None
    start_sec: int | None
    end_sec: int | None


@dataclass(frozen=True, slots=True)
class Rendered:
    poster: bytes
    poster_type: str
    video: bytes | None = None
    video_type: str | None = None


class ClipRenderer(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def excerpts(self) -> bool:
        """Whether this renderer cuts excerpts at all. The fixture does not: its clips are
        the still with the narration."""
        ...

    async def render(self, ask: ClipAsk) -> Rendered:
        """The still, and the excerpt when `ask.excerpt_url` is set. Never reached for a video
        whose licence does not allow reuse: `excerpt_url` is None then."""
        ...


@fixture
class FixtureClipRenderer:
    """One small committed still (`<fixtures>/clips/poster.png`) for every clip, and never an
    excerpt: a laptop and the demo show the still with the narration and captions."""

    name = "fixture"
    excerpts = False

    def __init__(self, root: Path) -> None:
        self._poster = Path(root) / "clips" / "poster.png"

    async def render(self, ask: ClipAsk) -> Rendered:
        return Rendered(poster=self._poster.read_bytes(), poster_type="image/png")


# --- captions ----------------------------------------------------------------------------------


def _stamp(seconds: float) -> str:
    whole = int(seconds)
    millis = round((seconds - whole) * 1000)
    if millis == 1000:
        whole, millis = whole + 1, 0
    return f"{whole // 3600:02d}:{whole % 3600 // 60:02d}:{whole % 60:02d}.{millis:03d}"


def caption_cues(
    lines: Sequence[str], language: str, *, boundary: str | None = None
) -> list[tuple[float, float, str]]:
    """Each line of the narration with when it is said: from the end of the line before, for
    as long as the line takes at his pace (`app.delivery.voice.seconds_to_say`, the pace the
    voice says it at), the pause after it included. The words shown are the card's own; the
    timing is the spoken form's (numbers said as words take longer)."""
    code = voice_language(language)
    script = script_for(lines, code, boundary=boundary)
    shown = [line for line in lines if line.strip()]
    cues: list[tuple[float, float, str]] = []
    at = 0.0
    for written, segment in zip(shown, script.segments, strict=True):
        took = seconds_to_say(segment.text, code)
        cues.append((round(at, 3), round(at + took, 3), written))
        at += took
    return cues


def captions(lines: Sequence[str], language: str, *, boundary: str | None = None) -> str:
    """The narration's captions as WebVTT, in the card's language."""
    out = ["WEBVTT", f"Language: {voice_language(language)}", ""]
    for index, (start, end, text) in enumerate(caption_cues(lines, language, boundary=boundary), 1):
        out.extend([str(index), f"{_stamp(start)} --> {_stamp(end)}", text, ""])
    return "\n".join(out)


# --- the routes' reads --------------------------------------------------------------------------


def is_clip(item: FeedItem) -> bool:
    return item.format is CardFormat.CLIP


def clip_key(item: FeedItem) -> str:
    """The same card, the same key: the item's id and its voice lines."""
    words = "\n".join(item.voice or item.body)
    return hashlib.sha256(f"{item.id}\n{words}".encode()).hexdigest()[:32]


async def _clip_item(session: AsyncSession, *, context: KeyContext, item_id: uuid.UUID) -> FeedItem:
    # A local import: `rank.py` imports `compose.py`, whose own chain reaches back to this
    # module (`search.py` imports `clips.py` for `ClipRenderer`), so importing `require_item`
    # at module level here would be a cycle.
    from app.delivery.feed.rank import require_item

    item = await require_item(session, context=context, item_id=item_id)
    if not is_clip(item):
        async with audited_guard(session, context, Action.READ, item.scope, FEED_TARGET):
            raise NotAClipCard(f"card {item_id} is a {item.type.value} card, not a clip")
    return item


def _cite(item: FeedItem) -> dict[str, Any]:
    return dict(item.cite or {})


async def clip_captions(
    session: AsyncSession, *, context: KeyContext, item_id: uuid.UUID
) -> str:
    """The captions of one clip, in its language: its narration's lines, timed."""
    item = await _clip_item(session, context=context, item_id=item_id)
    return captions(item.voice or item.body, item.language, boundary=item.boundary)


async def _rendered(
    item: FeedItem,
    *,
    context: KeyContext,
    renderer: ClipRenderer | None,
    store: ObjectStore,
    part: str,
) -> tuple[bytes, str] | None:
    """The still or the excerpt of one clip: from the region's store when it was made
    before, otherwise rendered now and kept there."""
    guard_region(held_in=store.region, asked_from=context.region)
    base = f"clips/{context.profile_id}/{renderer.name if renderer else 'none'}/{clip_key(item)}"
    kinds = {"poster": "image/png", "video": "video/mp4"}
    try:
        return await store.get(check_key(f"{base}/{part}")), kinds[part]
    except NoSuchObject:
        pass
    if renderer is None:
        raise NoClipRenderer("no clip renderer is configured on this server")
    cite = _cite(item)
    # The licence is read again here, not only when the card was made: an excerpt is asked for
    # only while the stored licence still allows reuse.
    excerpt = bool(cite.get("excerpt")) and may_excerpt(cite.get("licence"))
    ask = ClipAsk(
        key=clip_key(item),
        language=item.language,
        excerpt_url=cite.get("full_url") if excerpt else None,
        start_sec=cite.get("start_sec"),
        end_sec=cite.get("end_sec"),
    )
    made = await renderer.render(ask)
    await store.put(check_key(f"{base}/poster"), made.poster)
    if made.video is not None and excerpt:
        await store.put(check_key(f"{base}/video"), made.video)
    if part == "poster":
        return made.poster, made.poster_type
    if made.video is None or not excerpt:
        return None
    return made.video, made.video_type or "video/mp4"


async def clip_poster(
    session: AsyncSession,
    *,
    context: KeyContext,
    item_id: uuid.UUID,
    renderer: ClipRenderer | None,
    store: ObjectStore,
) -> tuple[bytes, str]:
    item = await _clip_item(session, context=context, item_id=item_id)
    # A server with no renderer refuses (`NoClipRenderer`), and the refusal is on his trail
    # like every other: there is no unlogged path off a card of his.
    async with audited_guard(session, context, Action.READ, item.scope, FEED_TARGET):
        got = await _rendered(item, context=context, renderer=renderer, store=store, part="poster")
    assert got is not None
    return got


async def clip_video(
    session: AsyncSession,
    *,
    context: KeyContext,
    item_id: uuid.UUID,
    renderer: ClipRenderer | None,
    store: ObjectStore,
) -> tuple[bytes, str]:
    """The excerpt, when the licence allowed the server to keep one; `NoExcerpt` otherwise,
    and the phone shows the still with the narration."""
    item = await _clip_item(session, context=context, item_id=item_id)
    cite = _cite(item)
    # A licence that forbids reuse is a refusal on the trail, not a silent nothing: the
    # publisher's terms are the reason he is shown a still, and the reason is recorded.
    async with audited_guard(session, context, Action.READ, item.scope, FEED_TARGET):
        if not cite.get("excerpt") or not may_excerpt(cite.get("licence")):
            raise NoExcerpt("this clip is the still with the narration")
        got = await _rendered(item, context=context, renderer=renderer, store=store, part="video")
        if got is None:
            raise NoExcerpt("no excerpt was made for this clip")
    return got
