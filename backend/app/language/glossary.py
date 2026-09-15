"""The glossary of docs/plain-words.md as a table: his words for things, in each language.

The doc is the source; this module only reads it. Three parts of it are read:

- §2, the glossary: each row is the words *instead of* which Nura speaks (the red words, which
  the verifier already fails, `app.safety.plain_words.GLOSSARY`) and what it *says* instead.
- Rule 13, "the same words every time": the first quoted phrase is his word for the thing, the
  others are the variants that are never said ("the log", "the readings", "the record").
- §6, the same words in Malay and Chinese: one row per thing he has a word for, the English
  phrase, the Malay and the Chinese Nura says every time, and the variants never said in each
  language (`en "your record"`, `zh "医院信"`). The Malay and Chinese there were taken from the
  words already shipped in the catalogues, not written by a model or a translation service; a
  native speaker's pass is still owed, as the catalogues themselves say.

`load()` reads the doc from the repository; `parse(text)` reads any text of the same shape, so
a test can hold the parser to a small doc of its own.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

LANGUAGES = ("en", "ms", "zh")
DOC = Path("docs/plain-words.md")

_QUOTED = re.compile(r'"([^"]+)"|“([^”]+)”')
_NEVER = re.compile(r'\b(en|ms|zh)\s+"([^"]+)"')


@dataclass(frozen=True, slots=True)
class Row:
    """One row of §2: the words instead of which Nura speaks, and what it says."""

    instead_of: tuple[str, ...]
    say: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Term:
    """One thing he has a word for, in each language Nura speaks, and the words never said.

    `words` is the phrase per language as §6 gives it; a language the doc leaves empty has no
    entry. `never` is, per language, the variants that are not his word for this thing."""

    words: Mapping[str, str]
    never: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def en(self) -> str:
        return self.words["en"]

    def say(self, language: str) -> str | None:
        return self.words.get(language)


@dataclass(frozen=True, slots=True)
class Glossary:
    rows: tuple[Row, ...]
    """§2, row by row."""
    same_words: tuple[tuple[str, tuple[str, ...]], ...]
    """Rule 13: (his word, the variants never said)."""
    terms: tuple[Term, ...]
    """§6: his words for things in English, Malay and Chinese."""

    def red_words(self) -> tuple[str, ...]:
        return tuple(word for row in self.rows for word in row.instead_of)

    def term(self, en: str) -> Term | None:
        wanted = en.strip().lower()
        return next((t for t in self.terms if t.en.lower() == wanted), None)

    def never(self, language: str) -> Iterator[tuple[str, str]]:
        """Every variant never said in `language`, with the words said instead."""
        if language == "en":
            for canonical, variants in self.same_words:
                for variant in variants:
                    yield variant, canonical
        for term in self.terms:
            say = term.say(language) or term.en
            for variant in term.never.get(language, ()):
                yield variant, say


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table(lines: list[str]) -> Iterator[list[str]]:
    """The body rows of the first table in `lines`: the header and the rule are skipped."""
    seen_rule = False
    for line in lines:
        if not line.startswith("|"):
            if seen_rule:
                return
            continue
        if re.match(r"^\|\s*:?-{3,}", line):
            seen_rule = True
            continue
        if seen_rule:
            yield _cells(line)


def _section(text: str, number: int) -> list[str]:
    """The lines of `## <number>. …` up to the next `## ` heading."""
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if re.match(rf"^##\s+{number}\.\s", line)), None
    )
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return lines[start + 1 : end]


def _say_phrases(cell: str) -> tuple[str, ...]:
    """The phrases in a Say cell: every quoted phrase, and the plain sentences outside quotes."""
    quoted = [a or b for a, b in _QUOTED.findall(cell)]
    rest = _QUOTED.sub(" ", cell)
    plain = [p.strip(" .") for p in re.split(r"\.\s+|/", rest) if p.strip(" .")]
    return tuple(p.strip() for p in [*plain, *quoted] if p.strip())


def _rows(text: str) -> tuple[Row, ...]:
    rows: list[Row] = []
    for cells in _table(_section(text, 2)):
        if len(cells) != 2:
            continue
        instead = tuple(w.strip().lower() for w in re.split(r"[,/]", cells[0]) if w.strip())
        rows.append(Row(instead, _say_phrases(cells[1])))
    return tuple(rows)


def _same_words(text: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    for line in _section(text, 1):
        if "The same words every time" in line:
            quoted = [a or b for a, b in _QUOTED.findall(line)]
            if quoted:
                return ((quoted[0], tuple(quoted[1:])),)
    return ()


def _terms(text: str) -> tuple[Term, ...]:
    terms: list[Term] = []
    for cells in _table(_section(text, 6)):
        if len(cells) < 3 or not cells[0]:
            continue
        words = {
            code: cell for code, cell in zip(LANGUAGES, cells[:3], strict=True) if cell.strip()
        }
        never: dict[str, list[str]] = {}
        if len(cells) > 3:
            for code, variant in _NEVER.findall(cells[3]):
                never.setdefault(code, []).append(variant)
        terms.append(Term(words, {code: tuple(v) for code, v in never.items()}))
    return tuple(terms)


def parse(text: str) -> Glossary:
    """The glossary in a doc shaped like docs/plain-words.md."""
    return Glossary(rows=_rows(text), same_words=_same_words(text), terms=_terms(text))


def load(root: Path | None = None) -> Glossary:
    """The glossary in the repository's docs/plain-words.md."""
    from app.safety.plain_words import repo_root

    base = root or repo_root()
    return parse((base / DOC).read_text(encoding="utf-8"))
