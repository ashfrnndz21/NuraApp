"""About him, to someone else (D1): the same lines, said about the patient by name to a family
member who reads his papers with her own key.

His lines speak to him ("Your blood pressure today was 138 over 84."). On a key that is not
his, every endpoint his chief's Home reads says them about him instead ("Pa's blood pressure
today was 138 over 84.") — whole sentences from the catalogues' `*_THEIRS` twins, in English,
Malay and Chinese, never composed on the client. A line is matched against its catalogue
template, which gives back its slots; its twin is filled with the same slots and his name, a
possessive inside a slot ("your blood pressure tablet") said about him too. A line that speaks
to him and has no twin stays as it was here; a feed card of his that still speaks to him after
this is not shown to anyone else (`page`).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read
from app.channels import state_words
from app.consent import texts as consent_words
from app.delivery import strings as feed_words
from app.delivery import timeline_strings
from app.delivery.strings import language_for, theirs
from app.family import strings as family_words
from app.keys.context import KeyContext
from app.medicines import strings as medicine_words
from app.safety.boundary import BOUNDARY_THEIRS

if TYPE_CHECKING:
    from app.channels.api.feed_schemas import FeedItemOut, FeedPageOut, SentOut

LANGUAGES = ("en", "ms", "zh")

TO_HIM: Mapping[str, re.Pattern[str]] = {
    "en": re.compile(r"\b(you|your|yours|yourself)\b", re.IGNORECASE),
    "ms": re.compile(r"\banda\b", re.IGNORECASE),
    "zh": re.compile(r"[您你]"),
}
"""A line that speaks to him, in each language."""

_SLOT = re.compile(r"\{(\w+)\}")

Out = TypeVar("Out", bound=BaseModel)


def _mirror(originals: Any, twins: Any) -> Iterator[tuple[str, str]]:
    """Each original with its twin, place for place and key for key."""
    if isinstance(originals, str):
        if isinstance(twins, str):
            yield originals, twins
    elif isinstance(originals, Mapping):
        if isinstance(twins, Mapping):
            for key, value in originals.items():
                if key in twins:
                    yield from _mirror(value, twins[key])
    elif (
        isinstance(originals, tuple | list)
        and isinstance(twins, tuple | list)
        and len(originals) == len(twins)
    ):
        for one, other in zip(originals, twins, strict=True):
            yield from _mirror(one, other)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for each in value.values():
            yield from _strings(each)
    elif isinstance(value, tuple | list):
        for each in value:
            yield from _strings(each)


def _bulleted(mapping: Mapping[str, Mapping[Any, str]]) -> dict[str, dict[Any, str]]:
    """Each part of the record as the family's grant lines and the consent wording both list
    it: one bullet a line (`app.family.grants._grant_lines`, `app.consent.texts.render_sharing`,
    both `f"- {part}"`)."""
    return {
        language: {scope: f"- {text}" for scope, text in by_scope.items()}
        for language, by_scope in mapping.items()
    }


def _catalogues() -> tuple[tuple[Mapping[str, Any], Mapping[str, Any]], ...]:
    return (
        (feed_words.HEADLINES, feed_words.HEADLINES_THEIRS),
        (feed_words.LINES, feed_words.LINES_THEIRS),
        (feed_words.WHY, feed_words.WHY_THEIRS),
        (timeline_strings.CHANGED, timeline_strings.CHANGED_THEIRS),
        (timeline_strings.ANCHORS, timeline_strings.ANCHORS_THEIRS),
        (medicine_words.DOSE_CARD, medicine_words.DOSE_CARD_THEIRS),
        (medicine_words.TAKEN, medicine_words.TAKEN_THEIRS),
        (medicine_words.COUNT, medicine_words.COUNT_THEIRS),
        (medicine_words.REORDER, medicine_words.REORDER_THEIRS),
        (medicine_words.REORDER_ACTIONS, medicine_words.REORDER_ACTIONS_THEIRS),
        (medicine_words.SOURCE, medicine_words.SOURCE_THEIRS),
        (medicine_words.IF_FORGOTTEN, medicine_words.IF_FORGOTTEN_THEIRS),
        (state_words.POSTURE_LINE, state_words.POSTURE_LINE_THEIRS),
        # The family's grant lines (#210) and the consent wording (#214): who a role is to
        # him and the parts a key opens speak to him inside a slot ("the person who runs your
        # care"), so the outer template needs no twin of its own — registering it here is
        # enough for the slot it carries to be said about him (`_theirs`, below).
        (family_words.ROLE_IS, family_words.ROLE_IS),
        (family_words.WINDOW_LINES, family_words.WINDOW_LINES_THEIRS),
        (_bulleted(consent_words.SCOPE_WORDS), _bulleted(consent_words.SCOPE_WORDS_THEIRS)),
    )


def _pattern(template: str) -> re.Pattern[str] | None:
    """The template as a pattern that gives its slots back; None for one that is all slot."""
    if not _SLOT.sub("", template).strip():
        return None
    seen: set[str] = set()
    parts: list[str] = []
    for index, piece in enumerate(_SLOT.split(template)):
        if index % 2 == 0:
            parts.append(re.escape(piece))
        elif piece in seen:
            parts.append(f"(?P={piece})")
        else:
            seen.add(piece)
            parts.append(f"(?P<{piece}>.+?)")
    return re.compile("".join(parts))


def twins(language: str) -> tuple[tuple[str, str], ...]:
    """Every (original, twin) pair in one language: the written twins first; then each template
    that does not speak to him itself, as its own twin, so a slot that does ("your blood
    pressure tablet") is still said about him; then the boundary's lines."""
    written: list[tuple[str, str]] = []
    same: list[tuple[str, str]] = []
    for originals, twin_maps in _catalogues():
        mine = originals.get(language)
        if mine is None:
            continue
        written.extend(_mirror(mine, twin_maps.get(language)))
        same.extend((one, one) for one in _strings(mine) if not TO_HIM[language].search(one))
    # The written twins first, so a template that is all slot around a few words ("This comes
    # from {…}.") never takes a line that has a twin of its own.
    pairs = [
        *written,
        *BOUNDARY_THEIRS.get(language, {}).values(),
        *consent_words.CONSENT_THEIRS.get(language, {}).values(),
        *same,
    ]
    first: dict[str, str] = {}
    for original, twin in pairs:
        first.setdefault(original, twin)
    return tuple(first.items())


@lru_cache(maxsize=len(LANGUAGES))
def _table(language: str) -> tuple[tuple[re.Pattern[str], str], ...]:
    compiled = []
    for original, twin in twins(language):
        pattern = _pattern(original)
        if pattern is not None:
            compiled.append((pattern, twin))
    return tuple(compiled)


@lru_cache(maxsize=len(LANGUAGES))
def _exact(language: str) -> Mapping[str, str]:
    """Whole lines with no slot whose twin differs though they do not speak to him ("Taken" is
    "Pa took it" when someone else taps it)."""
    return {
        original: twin
        for original, twin in twins(language)
        if original != twin and not _SLOT.search(original) and not TO_HIM[language].search(original)
    }


@lru_cache(maxsize=len(LANGUAGES))
def _names(language: str) -> frozenset[str]:
    return frozenset(medicine_words.PLAIN_NAME[language].values())


def _theirs(value: str, name: str, language: str) -> str:
    """A possessive inside a slot said about him (`app.delivery.strings.theirs`)."""
    return theirs(value, name, language)


@dataclass(frozen=True, slots=True)
class Reader:
    """Who is reading: his own key, or someone else's with his name to say."""

    his: bool
    name: str = ""
    language: str = "en"

    def says(self, text: str) -> str:
        """The text as this reader hears it: unchanged on his own key; line by line about him
        by name on anyone else's."""
        if self.his or not text:
            return text
        return "\n".join(self._line(line) for line in text.split("\n"))

    def _line(self, line: str) -> str:
        exact = _exact(self.language).get(line)
        if exact is not None:
            return exact.format(patient=self.name)
        if not any(pattern.search(line) for pattern in TO_HIM.values()):
            return line
        order = (self.language, *(code for code in LANGUAGES if code != self.language))
        for code in order:
            for pattern, twin in _table(code):
                found = pattern.fullmatch(line)
                if found is None:
                    continue
                slots = {
                    key: _theirs(value, self.name, code) for key, value in found.groupdict().items()
                }
                try:
                    return twin.format(patient=self.name, **slots)
                except (KeyError, IndexError, ValueError):
                    continue
            if line in _names(code):
                return _theirs(line, self.name, code)
        return line

    def speaks_to_him(self, value: Any) -> bool:
        """Whether anything in `value` still speaks to him."""
        return any(pattern.search(text) for text in _strings(value) for pattern in TO_HIM.values())

    def about(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.says(value)
        if isinstance(value, list):
            return [self.about(each) for each in value]
        if isinstance(value, dict):
            return {key: self.about(each) for key, each in value.items()}
        return value

    def model(self, out: Out) -> Out:
        """An output model as this reader hears it."""
        if self.his:
            return out
        return type(out).model_validate(self.about(out.model_dump(mode="json")))

    def _kept(self, item: FeedItemOut) -> bool:
        """Whether a card belongs in front of this reader: hers are hers already; one of his
        with no twin for a line that still speaks to him is not shown to anyone else."""
        return item.deliver_to != "patient" or not self.speaks_to_him(
            [item.headline, item.body, item.voice, item.why.get("plain", "")]
        )

    def page(self, out: FeedPageOut) -> FeedPageOut:
        """A feed page as this reader hears it: his cards about him by name, and a card of his
        with no twin for a line that speaks to him not shown (hers are hers already)."""
        if self.his:
            return out
        heard = self.model(out)
        return heard.model_copy(update={"items": [item for item in heard.items if self._kept(item)]})

    def sent(self, items: Sequence[SentOut]) -> list[SentOut]:
        """"Sent to Pa this week" as this reader hears it: the same rule `page` holds every
        other card to — his cards about him by name, and one of his with no twin for a line
        that still speaks to him not shown to anyone else."""
        if self.his:
            return list(items)
        heard = [self.model(one) for one in items]
        return [one for one in heard if self._kept(one.item)]


async def reader_of(session: AsyncSession, context: KeyContext, language: str | None) -> Reader:
    """The reader behind this key: his own, or someone else's, with his name as the family
    writes it (read under the profile scope every role holds)."""
    if context.is_owner:
        return Reader(his=True)
    profile = await audited_profile_read(session, context)
    return Reader(
        his=False,
        name=profile.display_name or "",
        language=language_for(language or profile.language),
    )
