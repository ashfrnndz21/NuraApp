"""The words a person agreed to, by purpose, version and language.

Every wording ever shown stays here, because the record of a consent has to be able to say
what was agreed to even after the words have moved on. A new version is appended, never
edited in place; the newest per purpose is the one a fresh consent is asked for, and an
older one no longer stands for it. A consent can only be recorded in words that are here,
in the language they were shown in: the record never claims someone agreed to words that
do not exist.

The summaries are what the patient reads, so they follow `docs/plain-words.md`: whole
sentences, one idea per line, his words for things ("your papers", "your blood pressure
book", "today's list"), nothing to decode.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.consent.models import ConsentPurpose


@dataclass(frozen=True, slots=True)
class ConsentText:
    purpose: ConsentPurpose
    version: str
    language: str
    summary: str
    """The plain-words statement of what the person is agreeing to."""


TEXTS: tuple[ConsentText, ...] = (
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "en",
        "Nura keeps your papers, your medicines and your blood pressure book. "
        "They stay in your country.",
    ),
    ConsentText(
        ConsentPurpose.SHARE_WITH_FAMILY,
        "1",
        "en",
        "The family you name can see the parts you choose. "
        "You can see who looked. "
        "You can stop it at any time.",
    ),
    ConsentText(
        ConsentPurpose.RECORDING,
        "1",
        "en",
        "Nura records your visit when you press the button. "
        "It keeps the words so you can hear them again.",
    ),
    ConsentText(
        ConsentPurpose.WHATSAPP,
        "1",
        "en",
        "Nura sends today's list to you on WhatsApp.",
    ),
)
"""Append only. Within a purpose, versions are in the order they were introduced, and the
last one is current. Every version needs its English wording; other languages are added as
they are translated, and a consent in a language that is not here yet cannot be recorded."""


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


def wording(purpose: ConsentPurpose, version: str, language: str) -> str | None:
    """The words shown for this purpose at this version in this language, or None."""
    for text in TEXTS:
        if text.purpose is purpose and text.version == version and text.language == language:
            return text.summary
    return None
