"""Who Nura cannot reach, as the owner and his chief read it (#162, #163).

Two places say it. Beside an open red flag on the family page: who the ladder asked whose
phone nothing reached — they have only the notice on their family page (`NOT_REACHED`). And
under his circle: who Nura cannot send WhatsApp — they said no to it, or there is no number —
and who it can then reach only in the app, with no device for a push either. In the reader's
language, through docs/plain-words.md like every line.
"""

from __future__ import annotations

from collections.abc import Mapping

LANGUAGES = ("en", "ms", "zh")

# @patient
NOT_REACHED: Mapping[str, str] = {
    "en": "Nura could not reach {name} on their phone.",
    "ms": "Nura tidak dapat hubungi telefon {name}.",
    "zh": "Nura 无法通过手机联系{name}。",
}
"""Beside an open red flag: someone the ladder asked whom no push and no WhatsApp reached."""

# @patient
NO_WHATSAPP: Mapping[str, str] = {
    "en": "Nura cannot send {name} messages on WhatsApp.",
    "ms": "Nura tidak boleh hantar mesej kepada {name} di WhatsApp.",
    "zh": "Nura 不能在 WhatsApp 上给{name}发消息。",
}
"""Under his circle: someone who said no to WhatsApp, or has no number."""

# @patient
ONLY_IN_APP: Mapping[str, str] = {
    "en": "{name} sees what Nura says only in the app.",
    "ms": "{name} hanya nampak apa yang Nura kata dalam aplikasi.",
    "zh": "{name}只能在应用里看到 Nura 说的话。",
}
"""After `NO_WHATSAPP`, when they have no device for a push either."""


def language_of(asked: str | None) -> str:
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else "en"


def not_reached_line(name: str, language: str | None) -> str:
    return NOT_REACHED[language_of(language)].format(name=name)


def reach_lines(name: str, *, push: bool, language: str | None) -> list[str]:
    words = language_of(language)
    lines = [NO_WHATSAPP[words].format(name=name)]
    if not push:
        lines.append(ONLY_IN_APP[words].format(name=name))
    return lines
