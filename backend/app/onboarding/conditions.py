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


class NotAnAnswer(Refusal):
    """An answer to a follow-up question: a picked condition that carries one (`ask`), and
    one of its option ids. This was not that."""


class NotAGraph(Exception):
    """The graph file is not the shape this module reads. A packaging error, not a request."""


@dataclass(frozen=True, slots=True)
class AskOption:
    """One choice of a follow-up question, his words in every language."""

    id: str
    texts: Mapping[str, str]

    def text(self, language: str) -> str:
        return self.texts[language_for(language)]


@dataclass(frozen=True, slots=True)
class Ask:
    """The one follow-up question a condition carries once it is tapped (docs/onboarding.html:
    "On tablets for it -> For how long?"), and its options. His answer is one of the option
    ids, written as a `condition_answer` fact (`app.onboarding.settings`) — his own word,
    resting on the moment he tapped it, never inferred."""

    questions: Mapping[str, str]
    options: tuple[AskOption, ...]

    def question(self, language: str) -> str:
        return self.questions[language_for(language)]

    def option(self, option_id: str) -> AskOption | None:
        return next((one for one in self.options if one.id == option_id), None)


@dataclass(frozen=True, slots=True)
class Condition:
    code: str
    weight: int
    names: Mapping[str, str]
    related: tuple[str, ...]
    top: bool
    ask: Ask | None = None

    def name(self, language: str) -> str:
        return self.names[language_for(language)]


@dataclass(frozen=True, slots=True)
class Graph:
    version: int
    top: tuple[str, ...]
    conditions: Mapping[str, Condition]
    """Every condition, in the order the file lists them: the top level, then the rest."""


def _load_ask(code: str, raw: object | None) -> Ask | None:
    """`raw["ask"]`, checked: a question named in exactly `LANGUAGES`, one or more options
    each with a short id, unique within this ask, and its own text in every language."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise NotAGraph(f"{code}'s ask is not an object")
    question = raw.get("question")
    if not isinstance(question, dict) or set(question) != set(LANGUAGES):
        raise NotAGraph(f"{code}'s ask is not a question named in exactly {LANGUAGES}")
    options_raw = raw.get("options")
    if not isinstance(options_raw, list) or not options_raw:
        raise NotAGraph(f"{code}'s ask has no options")
    seen: set[str] = set()
    options: list[AskOption] = []
    for option in options_raw:
        if not isinstance(option, dict):
            raise NotAGraph(f"{code}'s ask has an option that is not an object")
        option_id = option.get("id")
        texts = option.get("text")
        if not isinstance(option_id, str) or not CODE.match(option_id):
            raise NotAGraph(f"{code}'s ask has an option id that is not a short code")
        if option_id in seen:
            raise NotAGraph(f"{code}'s ask repeats the option {option_id!r}")
        seen.add(option_id)
        if not isinstance(texts, dict) or set(texts) != set(LANGUAGES):
            raise NotAGraph(f"{code}'s option {option_id!r} is not named in exactly {LANGUAGES}")
        options.append(
            AskOption(id=option_id, texts={language: str(texts[language]) for language in LANGUAGES})
        )
    return Ask(
        questions={language: str(question[language]) for language in LANGUAGES},
        options=tuple(options),
    )


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
            ask=_load_ask(code, entry.get("ask")),
        )
    unknown = [one for one in top if one not in conditions] + [
        one
        for condition in conditions.values()
        for one in condition.related
        if one not in conditions
    ]
    if unknown:
        raise NotAGraph(f"codes named but not in the graph: {sorted(set(unknown))}")
    return Graph(version=int(raw["version"]), top=top, conditions=conditions)


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


def check_answers(answers: Mapping[str, str], *, picked: Iterable[str]) -> dict[str, str]:
    """`answers` (condition code -> option id) as the graph checks them: each key one of
    `picked` that carries a follow-up question (`ask`), each value one of its option ids.
    `NotAnAnswer` for anything else — a code not tapped, one with no question, or an option
    the question does not offer."""
    known = graph().conditions
    chosen = set(picked)
    checked: dict[str, str] = {}
    for code, option_id in answers.items():
        condition = known.get(code)
        if condition is None or condition.ask is None:
            raise NotAnAnswer(f"{code!r} carries no follow-up question")
        if code not in chosen:
            raise NotAnAnswer(f"{code!r} is not one of the conditions tapped")
        if condition.ask.option(option_id) is None:
            raise NotAnAnswer(f"{option_id!r} is not one of {code!r}'s options")
        checked[code] = option_id
    return checked
