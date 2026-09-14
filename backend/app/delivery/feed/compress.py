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
from typing import Any, ClassVar, Protocol


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


class Searcher(Protocol):
    def search(self, kind: str, terms: Sequence[str], domains: Sequence[str]) -> Sequence[Found]:
        """Pages for these terms, from these domains only. Never a page from anywhere else."""
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
    def compress(self, text: str, language: str, facts: Mapping[str, Any]) -> Compressed | None:
        """The lines for this page and this person, or None when there is nothing for him."""
        ...


TREATMENT_CHANGE = re.compile(
    r"\b(?:stop|start|double|halve|increase|reduce|skip|change)\b[^.]{0,40}\b"
    r"(?:tablet|tablets|pill|pills|medicine|medicines|dose|doses|warfarin|insulin)\b",
    re.IGNORECASE,
)
"""Lines that would start, stop or change a medicine. A card never carries one; the finding
becomes a question for the doctor and goes to the memo (docs/health-feed-spec.md §3.4, §7)."""


def changes_treatment(lines: Sequence[str]) -> bool:
    return any(TREATMENT_CHANGE.search(line) for line in lines)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FixtureSearcher:
    """Answers from `searches.json`: `{"<kind>:<term>": [{domain, url, title, published_at,
    text}]}`. A page whose domain is not among the domains asked for is never returned, so
    the fixture cannot smuggle a source past the allowlist either."""

    FIXTURE: ClassVar[bool] = True
    """A fixture: runs only on a declared dev run or demo (`app.fixtures`)."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _table(self) -> dict[str, list[dict[str, str]]]:
        path = self._root / "searches.json"
        if not path.exists():
            return {}
        loaded: dict[str, list[dict[str, str]]] = json.loads(path.read_text(encoding="utf-8"))
        return loaded

    def search(self, kind: str, terms: Sequence[str], domains: Sequence[str]) -> Sequence[Found]:
        table = self._table()
        allowed = set(domains)
        found: list[Found] = []
        for term in terms:
            for page in table.get(f"{kind}:{term.strip().lower()}", []):
                if page["domain"] in allowed:
                    found.append(Found(**page))
        return found


class FixtureCompressor:
    """Answers from `compressions/<sha256 of the text>.json`: `{"<language>": {headline, body,
    why_topic, passage, start_sec?, end_sec?}}`. No file, or no entry in the language, is
    "nothing for him". The `facts` are ignored by the fixture; the real adapter grounds on
    them."""

    FIXTURE: ClassVar[bool] = True
    """A fixture: runs only on a declared dev run or demo (`app.fixtures`)."""

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
