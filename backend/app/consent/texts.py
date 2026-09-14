"""The words a person agreed to, by purpose, version, language and region.

Every wording ever shown stays here, because the record of a consent has to be able to say
what was agreed to even after the words have moved on. A new version is appended, never
edited in place; the newest per purpose is the one a fresh consent is asked for, and an
older one no longer stands for it. A consent can only be recorded in words that are here,
in the language they were shown in: the record never claims someone agreed to words that
do not exist.

The summaries are what the patient reads, so they follow `docs/plain-words.md`: whole
sentences, one idea per line, his words for things ("your papers", "your blood pressure
book", "your Today page"), the name of his country, nothing to decode. Where the words
name the country, there is one text per region.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.consent.models import ConsentPurpose
from app.regions import Region

# @patient
LANGUAGES: Mapping[str, str] = {"en": "English", "zh": "Chinese", "ms": "Malay", "ta": "Tamil"}
"""The languages Nura speaks, by code, with the name the page uses. Nothing else is a
language a consent can be recorded in."""


@dataclass(frozen=True, slots=True)
class ConsentText:
    purpose: ConsentPurpose
    version: str
    language: str
    summary: str
    """The plain-words statement of what the person is agreeing to."""
    region: Region | None = None
    """The region these words are for, or None for words that serve every region."""


# @patient
TEXTS: tuple[ConsentText, ...] = (
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "en",
        "Nura keeps your papers, your medicines and your blood pressure book. "
        "They never leave Singapore.",
        region=Region.SG,
    ),
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "en",
        "Nura keeps your papers, your medicines and your blood pressure book. "
        "They never leave Malaysia.",
        region=Region.MY,
    ),
    ConsentText(
        ConsentPurpose.SHARE_WITH_FAMILY,
        "1",
        "en",
        "You choose who in your family can see your papers. "
        "You can see who looked at them. "
        "You can stop this at any time.",
    ),
    ConsentText(
        ConsentPurpose.RECORDING,
        "1",
        "en",
        "When you see the doctor, Nura can listen and keep what the doctor said. "
        "You can hear it again later. "
        "You can stop this at any time.",
    ),
    ConsentText(
        ConsentPurpose.WHATSAPP,
        "1",
        "en",
        "Every morning, Nura sends your Today page to you on WhatsApp. "
        "You can stop this at any time.",
    ),
)
"""Append only. Within a purpose, versions are in the order they were introduced, and the
last one is current. Every version needs its English wording for every region; other
languages are added as they are translated, and a consent in a language that is not here
yet cannot be recorded."""


def versions(purpose: ConsentPurpose) -> list[str]:
    """Every version ever shown for this purpose, oldest first, each once."""
    seen: list[str] = []
    for text in TEXTS:
        if text.purpose is purpose and text.version not in seen:
            seen.append(text.version)
    return seen


def current_version(purpose: ConsentPurpose) -> str:
    """The version a consent given today is asked for: the last one appended."""
    return versions(purpose)[-1]


def wording(purpose: ConsentPurpose, version: str, language: str, region: Region) -> str | None:
    """The words shown for this purpose, version and language in this region, or None.

    Words written for the region win over words written for every region. A language Nura
    does not speak has no words, whatever the catalogue says.
    """
    if language not in LANGUAGES:
        return None
    anywhere: str | None = None
    for text in TEXTS:
        if text.purpose is purpose and text.version == version and text.language == language:
            if text.region is region:
                return text.summary
            if text.region is None:
                anywhere = text.summary
    return anywhere
