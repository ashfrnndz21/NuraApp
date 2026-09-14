"""The retriever port: which things on the record a question is about (E03-05).

Recall reads the record itself — under the asker's key, part by part — and turns what it may
read into `Candidate`s: a kind, the id of the thing, when it was, and the phrases that name it
(his words for the subject, a provider's name, his name for a medicine). A retriever is handed
the question and those candidates and says which ones the question is about, best first. It
never reads the database and never writes a word of the answer, so a retriever cannot widen
what a key reaches and cannot put a sentence in front of him: scope stays in recall, words
stay in the templates.

Two adapters. `KeywordRetriever`, the default: a candidate is picked when one of its phrases is
in the question, the longer phrase first, then the newer thing. `FixtureRetriever`, for tests
and dev runs: files keyed by the sha256 of the question, each naming the phrases a model would
have picked out; a question it does not know picks nothing. A model-backed retriever is a later
adapter behind the same port.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.db import as_utc
from app.errors import Refusal
from app.fixtures import fixture


@dataclass(frozen=True, slots=True)
class Candidate:
    """One thing on the record a question could be about."""

    kind: str
    """`reading`, `fact`, `visit`, `medicine`, `paper`, `consult`, `consult_waiting` or
    `note` (a voice note or a scribble on one of his moments, E02-06)."""
    ref: uuid.UUID
    at: datetime
    names: frozenset[str]
    """Lower-case phrases that name it, in every language the product speaks."""


class Retriever(Protocol):
    """Which candidates a question is about, best first. Empty when none is."""

    def retrieve(self, question: str, candidates: Sequence[Candidate]) -> Sequence[Candidate]: ...


_SPACE = re.compile(r"\s+")
_NOT_WORD = re.compile(r"[^\w㐀-䶿一-鿿]+")
_CJK = re.compile(r"[㐀-䶿一-鿿]")


def normalise(question: str) -> str:
    """The question as the retrievers compare it: lower case, one space, no end mark."""
    return _SPACE.sub(" ", question.strip().lower()).rstrip("?!.。？！ ")


def question_digest(question: str) -> str:
    """The sha256 of the normalised question: what a fixture is keyed by."""
    return hashlib.sha256(normalise(question).encode("utf-8")).hexdigest()


def _found(name: str, spaced: str, raw: str) -> bool:
    if _CJK.search(name):
        return name in raw
    return f" {name} " in spaced


def _newest_first(candidate: Candidate) -> float:
    return -as_utc(candidate.at).timestamp()


class KeywordRetriever:
    """A candidate is about the question when one of its phrases is in it."""

    def retrieve(self, question: str, candidates: Sequence[Candidate]) -> Sequence[Candidate]:
        raw = normalise(question)
        spaced = f" {_NOT_WORD.sub(' ', raw).strip()} "
        scored: list[tuple[int, Candidate]] = []
        for candidate in candidates:
            best = max((len(n) for n in candidate.names if _found(n, spaced, raw)), default=0)
            if best:
                scored.append((best, candidate))
        scored.sort(key=lambda pair: (-pair[0], _newest_first(pair[1]), str(pair[1].ref)))
        return [candidate for _, candidate in scored]


class NotAFixture(Refusal):
    """A recall fixture names its question, the sha256 of it, and the phrases picked out."""


@fixture
class FixtureRetriever:
    """Answers from fixtures keyed by the sha256 of the question.

    Each fixture is `{"question": ..., "sha256": ..., "names": [...]}`: the phrases a model
    would have picked out of that question. A candidate is picked when it carries one of
    them, newest first. A question with no fixture picks nothing, and recall says so.
    """

    def __init__(self, fixtures: Mapping[str, Sequence[str]]) -> None:
        self._names = {
            digest: frozenset(n.lower() for n in names) for digest, names in fixtures.items()
        }

    @classmethod
    def load(cls, root: Path) -> FixtureRetriever:
        found: dict[str, Sequence[str]] = {}
        for path in sorted(root.glob("*.json")):
            entry = json.loads(path.read_text(encoding="utf-8"))
            digest = question_digest(str(entry.get("question", "")))
            if entry.get("sha256") != digest or not isinstance(entry.get("names"), list):
                raise NotAFixture(f"{path.name} does not key its question by its sha256")
            found[digest] = [str(name) for name in entry["names"]]
        return cls(found)

    def retrieve(self, question: str, candidates: Sequence[Candidate]) -> Sequence[Candidate]:
        wanted = self._names.get(question_digest(question))
        if not wanted:
            return []
        picked = [candidate for candidate in candidates if candidate.names & wanted]
        return sorted(picked, key=lambda c: (_newest_first(c), str(c.ref)))


__all__ = [
    "Candidate",
    "FixtureRetriever",
    "KeywordRetriever",
    "NotAFixture",
    "Retriever",
    "normalise",
    "question_digest",
]
