"""The topic catalogue and the `TopicTagger` port (RE-04, docs/recommendation-engine.md §2.5).

`Catalogue()` is one table of `Topic`s: today it covers his conditions (from the onboarding
word cloud, `app.onboarding.conditions`) and his medicine generics (grouped by the licensed
registry's `plain_name_id`, the same grouping `app.medicines.strings.PLAIN_NAME` already
speaks in en, ms and zh — so a topic's name is never a new translation, only a reference to
one already held to `docs/plain-words.md`), plus the handful of `sensitive` topics decision
D3 names (§3.5): sexual health, a mental-health crisis, a stigmatised infection, pregnancy,
abuse, end of life. Tests, feelings, lifestyle and food groups are a later story's topics,
added beside these the same way; nothing here forecloses that.

Building the medicine topics reads the generic-to-family grouping straight out of the fixture
registry's own file (`tests/fixtures/drugs/registry.json`), never through `DrugRegistry.
identify` — that port's conformance suite is explicit that a licensed feed may hold tens of
thousands of products with no way to enumerate "every generic" (`test_drug_registry_
conformance.py`), so nothing that must enumerate a whole registry can be built on that port.
The catalogue is not an adapter of `DrugRegistry` and does not stand behind its port: it is
data, keyed by the same rule ids (`plain_name_id`) a `Monograph` already carries whichever
registry answers it, so the grouping holds even where a deployment runs a licensed adapter.

The `TopicTagger` port maps free text to the topic codes it is about, sensitive codes never
among them:

- `KeywordTagger`, the default: a topic is tagged when one of its phrases is in the text, in
  any of the three languages, in the pattern of `app.search.retrieve.KeywordRetriever`.
- `FixtureTagger`, for tests: files keyed by the sha256 of the text, each naming the codes a
  model would have tagged; a text with no fixture tags nothing.

Decision D3 (§3.5): search history is a new use of his data under PDPA purpose limitation,
and a new use needs its own consent — asked once, off by default, given by the owner alone.
That consent (a `ConsentPurpose.SEARCH_HISTORY`) does not exist yet; no story before RE-20 may
add it. **This port has no gate of its own and must never be called on Ask or search-bar text
until a caller has checked that consent (or, before it exists, an explicit preference) is in
force.** Calling it on a meal he typed, a page's text, or anything else already read under an
existing consent is unaffected — the gate is about the *source* of the text, not this port.
`test_topic_tagger_not_wired_to_search` guards that nothing wires this module into
`app.search.ask` or `app.delivery.feed.find` ahead of that story.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.errors import Refusal
from app.fixtures import fixture
from app.medicines.strings import PLAIN_NAME
from app.onboarding.conditions import graph as conditions_graph

LANGUAGES = ("en", "ms", "zh")

REGISTRY_FIXTURE = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "drugs" / "registry.json"
)
"""Read only for its `generic -> plain_name_id` grouping (module doc): never through
`DrugRegistry`, which cannot promise to enumerate a licensed feed."""

TOPIC_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "topics"


class NotATopic(Refusal):
    """A topic code named that is not in the catalogue."""


class NotATopicFixture(Refusal):
    """A tagger fixture does not key its text by its own sha256, or names an unknown code."""


@dataclass(frozen=True, slots=True)
class Topic:
    """One thing free text can be about."""

    code: str
    family: str
    """`condition`, `medicine` or `sensitive` today; a later story adds more."""
    names: Mapping[str, str]
    """His plain name for it, in `LANGUAGES` — never shown for a `sensitive` topic, which no
    screen renders, but held to the same shape so the pharmacist's review (D3f) reads it."""
    terms: Mapping[str, frozenset[str]]
    """Lower-case phrases a tagger may match, by language. Not patient-facing: search terms
    are matching data, not a line he reads, so they carry no `# @patient` tag."""
    sensitive: bool

    def name(self, language: str) -> str:
        return self.names[language]


@dataclass(frozen=True, slots=True)
class Catalogue:
    topics: Mapping[str, Topic]
    """Every topic, by code."""

    def __getitem__(self, code: str) -> Topic:
        try:
            return self.topics[code]
        except KeyError:
            raise NotATopic(f"{code!r} is not a topic in the catalogue") from None

    def __contains__(self, code: str) -> bool:
        return code in self.topics

    def __iter__(self) -> Iterator[str]:
        return iter(self.topics)

    def visible(self, codes: Iterable[str]) -> tuple[str, ...]:
        """`codes`, each once, sensitive ones dropped, in the catalogue's own order — the one
        place a sensitive code is filtered out, so every adapter's `tag()` goes through it."""
        seen: dict[str, None] = {}
        for code in codes:
            topic = self[code]
            if not topic.sensitive:
                seen.setdefault(code, None)
        return tuple(sorted(seen))


def _split_terms(name: str) -> tuple[str, ...]:
    """A condition's name as one or more search phrases: "Sugar, diabetes" is two, not one,
    and "High blood pressure" is also matched by "blood pressure" alone — a leading qualifier
    ("high", "in", "an") is not how he always says it back."""
    parts = [part.strip().lower() for part in name.split(",") if part.strip()]
    if not parts:
        parts = [name.strip().lower()]
    terms = set(parts)
    for part in parts:
        words = part.split()
        if len(words) >= 3:
            terms.add(" ".join(words[1:]))
    return tuple(sorted(terms))


def _condition_topics() -> dict[str, Topic]:
    found: dict[str, Topic] = {}
    for code, condition in conditions_graph().conditions.items():
        topic_code = f"condition.{code}"
        names = dict(condition.names)
        terms = {
            language: frozenset(_split_terms(names[language])) for language in LANGUAGES
        }
        found[topic_code] = Topic(
            code=topic_code, family="condition", names=names, terms=terms, sensitive=False
        )
    return found


@lru_cache(maxsize=1)
def _generic_families() -> Mapping[str, str]:
    """Every generic the fixture registry names, to the `plain_name_id` its monograph gives
    it — the grouping medicine topics are built from (module doc)."""
    raw = json.loads(REGISTRY_FIXTURE.read_text(encoding="utf-8"))
    return {
        generic: monograph["plain_name_id"] for generic, monograph in raw["monographs"].items()
    }


def _medicine_topics() -> dict[str, Topic]:
    generics_by_family: dict[str, list[str]] = {}
    for generic, family in _generic_families().items():
        generics_by_family.setdefault(family, []).append(generic)
    found: dict[str, Topic] = {}
    for family_id, generics in generics_by_family.items():
        topic_code = f"medicine.{family_id}"
        names = {language: PLAIN_NAME[language][family_id] for language in LANGUAGES}
        generic_terms = frozenset(generic.lower() for generic in generics)
        terms = {language: generic_terms for language in LANGUAGES}
        found[topic_code] = Topic(
            code=topic_code, family="medicine", names=names, terms=terms, sensitive=False
        )
    return found


# Administrative names only (module doc, `Topic.names`): decision D3 names these six
# categories (§3.5) as codes that are never kept and never shown, so their words are for the
# pharmacist's review (D3f), not for him — nothing here is a `# @patient` string.
_SENSITIVE_NAMES: Mapping[str, Mapping[str, str]] = {
    "sexual_health": {"en": "sexual health", "ms": "kesihatan seksual", "zh": "性健康"},
    "mental_health_crisis": {"en": "a mental-health crisis", "ms": "krisis kesihatan mental", "zh": "心理健康危机"},
    "stigmatised_infection": {"en": "HIV or another stigmatised infection", "ms": "HIV atau jangkitan lain yang distigma", "zh": "艾滋病或其他受歧视的感染"},
    "pregnancy": {"en": "pregnancy", "ms": "kehamilan", "zh": "怀孕"},
    "abuse": {"en": "abuse", "ms": "penderaan", "zh": "虐待"},
    "end_of_life": {"en": "end of life", "ms": "hujung hayat", "zh": "临终"},
}

_SENSITIVE_TERMS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "sexual_health": {
        "en": ("sexual health", "std", "sti", "sex", "condom"),
        "ms": ("kesihatan seksual", "penyakit kelamin"),
        "zh": ("性健康", "性病"),
    },
    "mental_health_crisis": {
        "en": ("suicide", "suicidal", "self harm", "kill myself", "want to die"),
        "ms": ("bunuh diri", "cederakan diri"),
        "zh": ("自杀", "自残"),
    },
    "stigmatised_infection": {
        "en": ("hiv", "aids", "hepatitis b", "hepatitis c"),
        "ms": ("hiv", "aids", "hepatitis b", "hepatitis c"),
        "zh": ("艾滋病", "hiv", "乙型肝炎"),
    },
    "pregnancy": {
        "en": ("pregnant", "pregnancy", "miscarriage", "abortion"),
        "ms": ("hamil", "kehamilan", "keguguran", "gugur kandungan"),
        "zh": ("怀孕", "流产", "堕胎"),
    },
    "abuse": {
        "en": ("abuse", "hit me", "afraid at home", "domestic violence"),
        "ms": ("penderaan", "keganasan rumah tangga"),
        "zh": ("虐待", "家庭暴力"),
    },
    "end_of_life": {
        "en": ("end of life", "palliative", "dying", "hospice"),
        "ms": ("hujung hayat", "paliatif", "hospis"),
        "zh": ("临终", "安宁疗护", "临终关怀"),
    },
}


def _sensitive_topics() -> dict[str, Topic]:
    found: dict[str, Topic] = {}
    for code, names in _SENSITIVE_NAMES.items():
        topic_code = f"sensitive.{code}"
        terms = {
            language: frozenset(_SENSITIVE_TERMS[code][language]) for language in LANGUAGES
        }
        found[topic_code] = Topic(
            code=topic_code, family="sensitive", names=dict(names), terms=terms, sensitive=True
        )
    return found


@lru_cache(maxsize=1)
def catalogue() -> Catalogue:
    """The catalogue, built once per process."""
    topics: dict[str, Topic] = {}
    topics.update(_condition_topics())
    topics.update(_medicine_topics())
    topics.update(_sensitive_topics())
    return Catalogue(topics=topics)


class TopicTagger(Protocol):
    """Which topics free text is about, sensitive ones never among them (module doc).

    A text that tags only sensitive topics returns nothing at all — not an empty list picked
    from a longer one, but the same shape as a text about nothing this catalogue knows
    (§3.5). A text that tags a sensitive topic *and* an ordinary one returns the ordinary one;
    only the sensitive code itself is withheld, never a topic beside it.

    Do not call this on Ask or search-bar text before checking decision D3's consent (module
    doc). Every other caller — recall's own answer, a meal he typed, a page's text — may call
    it exactly as any other reader of the catalogue would.
    """

    def tag(self, text: str) -> Sequence[str]: ...


_SPACE = re.compile(r"\s+")
_NOT_WORD = re.compile(r"[^\w㐀-䶿一-鿿]+")
_CJK = re.compile(r"[㐀-䶿一-鿿]")


def normalise(text: str) -> str:
    """The text as a tagger compares it: lower case, one space, no end mark."""
    return _SPACE.sub(" ", text.strip().lower()).rstrip("?!.。？！ ")


def text_digest(text: str) -> str:
    """The sha256 of the normalised text: what a fixture is keyed by."""
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def _found(term: str, spaced: str, raw: str) -> bool:
    if _CJK.search(term):
        return term in raw
    cleaned = _NOT_WORD.sub(" ", term).strip()
    return f" {cleaned} " in spaced


class KeywordTagger:
    """A topic is tagged when one of its phrases, in any language, is in the text."""

    def tag(self, text: str) -> Sequence[str]:
        raw = normalise(text)
        if not raw:
            return ()
        spaced = f" {_NOT_WORD.sub(' ', raw).strip()} "
        found = catalogue()
        matched = [
            code
            for code, topic in found.topics.items()
            if any(
                _found(term, spaced, raw)
                for language in LANGUAGES
                for term in topic.terms[language]
            )
        ]
        return found.visible(matched)


@fixture
class FixtureTagger:
    """Answers from fixtures keyed by the sha256 of the text.

    Each fixture is `{"text": ..., "sha256": ..., "codes": [...]}`: the topic codes a model
    would have tagged. A text with no fixture tags nothing, and every code a fixture names
    must already be in the catalogue — a fixture cannot invent a topic.
    """

    def __init__(self, fixtures: Mapping[str, Sequence[str]]) -> None:
        self._codes = {digest: tuple(codes) for digest, codes in fixtures.items()}

    @classmethod
    def load(cls, root: Path = TOPIC_FIXTURES) -> FixtureTagger:
        found: dict[str, Sequence[str]] = {}
        known = catalogue()
        for path in sorted(root.glob("*.json")):
            entry = json.loads(path.read_text(encoding="utf-8"))
            digest = text_digest(str(entry.get("text", "")))
            codes = entry.get("codes")
            if entry.get("sha256") != digest or not isinstance(codes, list):
                raise NotATopicFixture(f"{path.name} does not key its text by its sha256")
            for code in codes:
                if code not in known:
                    raise NotATopicFixture(f"{path.name} names {code!r}, not in the catalogue")
            found[digest] = [str(code) for code in codes]
        return cls(found)

    def tag(self, text: str) -> Sequence[str]:
        codes = self._codes.get(text_digest(text), ())
        return catalogue().visible(codes)


__all__ = [
    "Catalogue",
    "FixtureTagger",
    "KeywordTagger",
    "NotATopic",
    "NotATopicFixture",
    "Topic",
    "TopicTagger",
    "catalogue",
    "normalise",
    "text_digest",
]
