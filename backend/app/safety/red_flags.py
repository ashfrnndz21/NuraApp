"""The red-flag words: what bypasses planning and goes to the same-day path.

    Red flags (chest tightness, breathlessness at rest, one-sided swelling, worst-ever
    headache, sudden blurring, a fall, confusion, shaky-and-sweaty on sugar medicines, 1 kg
    or more in two days after a heart discharge) bypass planning and ranking: escalate
    immediately. — .claude/rules/safety.md, docs/smart-nudges.md

`RED_FLAGS` is that sentence as a table, plus the discharge-watch words the spec names (black
stool, fever with a medicine name). Each entry is a code and the words, in the three
languages, that a transcript or a fact might carry. Nothing here is a diagnosis: matching a
word writes a `Flag` and puts one template sentence on the card — "Call Dr Tan today." —
before anything is ranked. `find_red_flags` is the whole of the rule; the sentence lives in
`app.reasoning.visits.strings`, never here.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

RED_FLAGS: Mapping[str, tuple[str, ...]] = {
    "chest_pain": (
        "chest pain",
        "chest tightness",
        "tight chest",
        "sakit dada",
        "dada ketat",
        "胸痛",
        "胸闷",
    ),
    "breathless": (
        "breathless",
        "breathlessness",
        "short of breath",
        "cannot breathe",
        "sesak nafas",
        "susah bernafas",
        "气促",
        "呼吸困难",
    ),
    "black_stool": ("black stool", "black stools", "najis hitam", "berak hitam", "黑便"),
    "fall": ("a fall", "fell down", "fell over", "had a fall", "jatuh", "terjatuh", "跌倒"),
    "confusion": ("confusion", "confused", "keliru", "celaru", "神志不清", "糊涂"),
    "one_sided_swelling": (
        "one-sided swelling",
        "one leg swollen",
        "sebelah kaki bengkak",
        "单侧肿胀",
    ),
    "worst_headache": (
        "worst headache",
        "worst-ever headache",
        "sakit kepala paling teruk",
        "最严重的头痛",
    ),
    "sudden_blurring": ("sudden blurring", "suddenly blurry", "kabur tiba-tiba", "突然模糊"),
    "shaky_and_sweaty": ("shaky and sweaty", "menggigil dan berpeluh", "发抖出汗"),
    "fever_on_medicine": ("fever", "demam", "发烧", "发热"),
}
"""The codes and their words. `fever_on_medicine` is the discharge-watch entry: a fever is a
red-flag word only beside a medicine name (`FEVER_NEEDS_A_MEDICINE`)."""

FEVER_NEEDS_A_MEDICINE = frozenset({"fever_on_medicine"})

MEDICINE_WORDS = re.compile(
    r"\b(?:tablet|tablets|pill|pills|medicine|medicines|ubat|pil|药|药片)\b", re.IGNORECASE
)
"""How a medicine is named beside a fever: a word for a medicine, or a drug name the
caller passes in (`medicine_names`)."""


@dataclass(frozen=True, slots=True)
class RedFlagHit:
    """One red-flag word found: the code, the word as it appeared, and where."""

    code: str
    word: str
    start: int
    end: int

    def span(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end}


def _pattern(word: str) -> re.Pattern[str]:
    # Words in Latin script match whole words; Chinese has no word boundaries.
    if re.search(r"[A-Za-z]", word):
        return re.compile(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", re.IGNORECASE)
    return re.compile(re.escape(word))


_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = tuple(
    (code, word, _pattern(word))
    for code, words in RED_FLAGS.items()
    for word in sorted(words, key=len, reverse=True)
)


def _strings_in(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for inner in value.values():
            yield from _strings_in(inner)
    elif isinstance(value, list | tuple):
        for inner in value:
            yield from _strings_in(inner)


def find_red_flags(text: str, *, medicine_names: tuple[str, ...] = ()) -> list[RedFlagHit]:
    """Every red-flag word in `text`, in the order found. A fever counts only beside a
    medicine word or one of `medicine_names` on the same text."""
    names_medicine = bool(MEDICINE_WORDS.search(text)) or any(
        name and name.lower() in text.lower() for name in medicine_names
    )
    hits: list[RedFlagHit] = []
    for code, word, pattern in _PATTERNS:
        if code in FEVER_NEEDS_A_MEDICINE and not names_medicine:
            continue
        for match in pattern.finditer(text):
            if any(h.start <= match.start() < h.end for h in hits):
                continue
            hits.append(RedFlagHit(code, match.group(), match.start(), match.end()))
    return sorted(hits, key=lambda h: h.start)


def red_flags_in(*values: Any, medicine_names: tuple[str, ...] = ()) -> list[RedFlagHit]:
    """Red-flag words anywhere in these values — strings, or the strings inside JSON."""
    found: list[RedFlagHit] = []
    for value in values:
        for text in _strings_in(value):
            found.extend(find_red_flags(text, medicine_names=medicine_names))
    return found
