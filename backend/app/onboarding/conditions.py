"""The conditions graph (E01-03): the words of the word cloud, fixed, in three languages.

`conditions.json` is the graph. Each condition has a code, how large it sits in the cloud
(`weight`, 1 to 3), its name in English, Malay and Chinese, and the related conditions that
appear beside it once it is tapped; `top` is what the cloud shows first. Nothing in it is a
diagnosis: a tapped word says where to look (docs/onboarding.html), and is kept as a fact
"as told" — the person's word, resting on the moment he said it.

The graph is data, and it is checked as it is loaded: every related code and every top code
is in the graph, every code is a short code, every name exists in every language. The names
are his words: the tests hold every one to docs/plain-words.md, and a read-back line that
carries one is verified again when it is served.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.errors import Refusal
from app.onboarding.strings import LANGUAGES, language_for

GRAPH_FILE = Path(__file__).with_name("conditions.json")

CODE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")


class NotACondition(Refusal):
    """A condition is one of the codes in the graph. This was not one."""


class NotAGraph(Exception):
    """The graph file is not the shape this module reads. A packaging error, not a request."""


@dataclass(frozen=True, slots=True)
class Condition:
    code: str
    weight: int
    names: Mapping[str, str]
    related: tuple[str, ...]
    top: bool

    def name(self, language: str) -> str:
        return self.names[language_for(language)]


@dataclass(frozen=True, slots=True)
class Graph:
    top: tuple[str, ...]
    conditions: Mapping[str, Condition]
    """Every condition, in the order the file lists them: the top level, then the rest."""


def _load(path: Path) -> Graph:
    raw = json.loads(path.read_text(encoding="utf-8"))
    top = tuple(raw["top"])
    entries: Mapping[str, dict[str, object]] = raw["conditions"]
    conditions: dict[str, Condition] = {}
    for code, entry in entries.items():
        names = entry["names"]
        related = entry["related"]
        weight = entry["weight"]
        if not CODE.match(code):
            raise NotAGraph(f"{code!r} is not a short code")
        if not isinstance(names, dict) or set(names) != set(LANGUAGES):
            raise NotAGraph(f"{code} is not named in exactly {LANGUAGES}")
        if not isinstance(weight, int) or not 1 <= weight <= 3:
            raise NotAGraph(f"{code} has a weight outside 1 to 3")
        if not isinstance(related, list):
            raise NotAGraph(f"{code} lists its related codes as a list")
        conditions[code] = Condition(
            code=code,
            weight=weight,
            names={language: str(names[language]) for language in LANGUAGES},
            related=tuple(str(one) for one in related),
            top=code in top,
        )
    unknown = [one for one in top if one not in conditions] + [
        one
        for condition in conditions.values()
        for one in condition.related
        if one not in conditions
    ]
    if unknown:
        raise NotAGraph(f"codes named but not in the graph: {sorted(set(unknown))}")
    return Graph(top=top, conditions=conditions)


@lru_cache(maxsize=1)
def graph() -> Graph:
    """The graph, loaded and checked once per process."""
    return _load(GRAPH_FILE)


def check_conditions(codes: Iterable[str]) -> tuple[str, ...]:
    """The codes as the graph orders them, each once; `NotACondition` for any it does not hold."""
    known = graph().conditions
    asked = list(codes)
    strangers = [code for code in asked if code not in known]
    if strangers:
        raise NotACondition(f"{len(strangers)} code(s) are not in the conditions graph")
    wanted = set(asked)
    return tuple(code for code in known if code in wanted)


def name_of(code: str, language: str) -> str:
    """His name for a condition, in his language."""
    return graph().conditions[code].name(language)
