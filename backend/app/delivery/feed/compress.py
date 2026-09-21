"""The two ports the learning supply stands behind: finding a page, and compressing it.

Neither makes a live call in this repository. `Searcher` answers a job's terms with pages
from the sources it was given and no others; `Compressor` turns one page plus the profile's
relevant facts into the lines a card says, citing the passage they came from. The fixture
adapters answer from files under `backend/tests/fixtures/feed/`, keyed by the sha256 of what
they were shown, the way the paper extractor's fixture does. The real adapters — a fetcher
with robots respect and a cache, a grounded model call through `app/llm/` — arrive behind
these same two protocols; nothing above them changes.

What a compressor may not do is decided here, not in the adapter: an output with no cited
passage is rejected, and an output that could change treatment is not a card but a question
for the doctor (`TREATMENT_CHANGE`), rerouted by `search.run_job`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.fixtures import fixture


@dataclass(frozen=True, slots=True)
class Found:
    """One page a search turned up: where, what, when, and its text."""

    domain: str
    url: str
    title: str
    published_at: str
    text: str
    batch: str | None = None
    """For a safety notice: the batch number it concerns. Matched against the pack photo's
    batch fact; a notice that does not match his pack is held for the caregiver."""
    media: str | None = None
    """"video" for a video page (an allowlisted hospital's or ministry's own channel); None
    for a page of text. A video becomes a clip card (`app.delivery.feed.clips`)."""
    licence: str | None = None
    """Under what terms the publisher lets a video be reused ("cc-by", "permission"), or None
    when it does not say: then no excerpt is kept, and the card is the still and the
    narration, with the link to the whole video (docs/health-feed-spec.md §7)."""
    areas: tuple[str, ...] = ()
    """For a local bulletin: the districts or postcode prefixes it is about. Empty is the
    whole region (a haze or heat advisory). Matched on this server against his area; the
    area is never part of a search."""
    season: str | None = None
    """For a seasonal page: the season it is about (`app.delivery.feed.local.SEASONS`)."""


class PortUnavailable(Exception):
    """The searcher's or the compressor's own call failed — an API error, a timeout, a
    connection dropped — told apart from a clean "nothing for him" (an empty result, a
    refusal, an uncited passage), so `search.run_job` can mark the job `FAILED` and retry it
    the same day, instead of writing it down as looked at and done (#297 defect 2: on
    2026-09-18 the Anthropic API refused every call and every job that day was recorded
    `done`, `results=[]`, so nothing retried once the API came back). Fixture adapters never
    raise this — they always answer a clean empty on purpose, the same "nothing for him"
    every port in this package already uses. A real adapter raises it only from the one place
    its own call to the model can fail; every other empty answer it gives (a refusal, no
    matching page, unparseable output) stays a clean `[]`/`None`, unchanged."""


class Searcher(Protocol):
    external_processor: str | None
    """None for a searcher that never leaves the region (the fixture); a short name (e.g.
    "anthropic") for one whose terms and domains go to a third-party model processor outside
    it, so `search.search_and_compress` can write that reach down (`app.ingestion.review.
    EXTERNAL_MODEL_PROCESSOR`, the same line `Extractor`/`Narrator`/`Asker` already carry)
    without importing the adapter itself. Read defensively (`getattr(..., None)`) by callers,
    so a test double that predates this need not declare it."""

    def search(self, kind: str, terms: Sequence[str], domains: Sequence[str]) -> Sequence[Found]:
        """Pages for these terms, from these domains only. Never a page from anywhere else."""
        ...

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        """Pages whose words match, from these domains only — the ask bar's Web and Videos
        filters (`app.delivery.feed.find`). `media="video"` is videos only. The words are the
        question as typed and nothing else: no name, no area, no fact of his goes with them."""
        ...


@dataclass(frozen=True, slots=True)
class Compressed:
    """The part of one page that applies to this person, in his language, with its cite."""

    headline: str
    body: tuple[str, ...]
    why_topic: str
    """His words for what the card is about, to fill the why line ("your blood pressure")."""
    passage: str
    """The passage of the source the lines came from. Empty means uncited: rejected."""
    start_sec: int | None = None
    end_sec: int | None = None


class Compressor(Protocol):
    external_processor: str | None
    """The same meaning as `Searcher.external_processor`, for the page text and the facts a
    compressor grounds on."""

    def compress(self, text: str, language: str, facts: Mapping[str, Any]) -> Compressed | None:
        """The lines for this page and this person, or None when there is nothing for him."""
        ...


TREATMENT_CHANGE = re.compile(
    r"\b(?:stop|start|double|halve|increase|reduce|skip|change|do\s+not\s+take|don't\s+take)\b"
    r"[^.]{0,40}\b(?:tablet|tablets|pill|pills|medicine|medicines|dose|doses|warfarin|insulin)\b",
    re.IGNORECASE,
)
"""Lines that would start, stop or change a medicine. A card never carries one; the finding
becomes a question for the doctor and goes to the memo (docs/health-feed-spec.md §3.4, §7)."""


TREATMENT_CHANGE_MS = re.compile(
    r"\b(?:berhenti|hentikan|mula(?:kan)?|gandakan|tambah(?:kan)?|kurang(?:kan)?|langkau|"
    r"tukar|jangan\s+(?:ambil|makan|telan|guna)|tidak\s+perlu\s+(?:ambil|makan|guna))\b"
    r"[^.]{0,40}\b(?:ubat|pil|tablet|dos|warfarin|insulin)\b",
    re.IGNORECASE,
)
"""The same, in Malay: stop, start, double, add, cut, skip, change or do not take a medicine."""

TREATMENT_CHANGE_ZH = re.compile(
    r"(?:停|停止|开始|加倍|加大|增加|减少|减半|减量|加量|跳过|漏掉|换|改|不要|别|不吃)[^。]{0,12}"
    r"(?:药|药片|剂量|华法林|胰岛素)"
)
"""The same, in Chinese: stop, start, double, raise, lower, halve, skip, change or do not take."""

TREATMENT_CHANGE_ZH_AFTER = re.compile(
    r"(?:药|药片|剂量|华法林|胰岛素)[^。，]{0,6}(?:停|停掉|减量|加量|减半|加倍|减少|增加|跳过|不吃|别吃)"
)
"""Chinese names the medicine first as often as not ("降压药减量一半"): the same, the other way round."""


def changes_treatment(lines: Sequence[str]) -> bool:
    """Whether any line would start, stop or change a medicine, in English, Malay or Chinese:
    every language a card or a found page is said in is checked, not the English alone."""
    return any(
        pattern.search(line)
        for line in lines
        for pattern in (
            TREATMENT_CHANGE,
            TREATMENT_CHANGE_MS,
            TREATMENT_CHANGE_ZH,
            TREATMENT_CHANGE_ZH_AFTER,
        )
    )


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@fixture
class FixtureSearcher:
    """Answers from `searches.json`: `{"<kind>:<term>": [{domain, url, title, published_at,
    text}]}`. A page whose domain is not among the domains asked for is never returned, so
    the fixture cannot smuggle a source past the allowlist either."""

    external_processor: str | None = None
    """Answers from a file on disk; nothing ever leaves the region."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _table(self) -> dict[str, list[dict[str, Any]]]:
        path = self._root / "searches.json"
        if not path.exists():
            return {}
        loaded: dict[str, list[dict[str, Any]]] = json.loads(path.read_text(encoding="utf-8"))
        return loaded

    def search(self, kind: str, terms: Sequence[str], domains: Sequence[str]) -> Sequence[Found]:
        table = self._table()
        allowed = set(domains)
        found: list[Found] = []
        for term in terms:
            for page in table.get(f"{kind}:{term.strip().lower()}", []):
                if page["domain"] in allowed:
                    found.append(_found(page))
        return found

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        """Every page in the table, once, whose title or text holds every word, from the
        domains asked for only."""
        wanted = [word.strip().lower() for word in words if word.strip()]
        allowed = set(domains)
        seen: set[str] = set()
        found: list[Found] = []
        for pages in self._table().values():
            for page in pages:
                if page["domain"] not in allowed or page["url"] in seen:
                    continue
                if media is not None and page.get("media") != media:
                    continue
                haystack = f"{page['title']} {page['text']}".lower()
                if wanted and all(word in haystack for word in wanted):
                    seen.add(page["url"])
                    found.append(_found(page))
        return found


def _found(page: dict[str, Any]) -> Found:
    return Found(**{**page, "areas": tuple(page.get("areas", ()))})


@fixture
class FixtureCompressor:
    """Answers from `compressions/<sha256 of the text>.json`: `{"<language>": {headline, body,
    why_topic, passage, start_sec?, end_sec?}}`. No file, or no entry in the language, is
    "nothing for him". The `facts` are ignored by the fixture; the real adapter grounds on
    them."""

    external_processor: str | None = None
    """Answers from a file on disk; nothing ever leaves the region."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def compress(self, text: str, language: str, facts: Mapping[str, Any]) -> Compressed | None:
        path = self._root / "compressions" / f"{digest(text)}.json"
        if not path.exists():
            return None
        table: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        entry = table.get(language)
        if entry is None:
            return None
        return Compressed(
            headline=entry["headline"],
            body=tuple(entry["body"]),
            why_topic=entry["why_topic"],
            passage=entry.get("passage", ""),
            start_sec=entry.get("start_sec"),
            end_sec=entry.get("end_sec"),
        )
