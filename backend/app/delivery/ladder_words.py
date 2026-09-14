"""What the web says about a red flag's ladder to someone it reached (E11-06).

The notice itself went by WhatsApp or push, in its own approved words. On the web, the person
it reached sees the ladder still open and one button, "I'm on it", which stops it for
everyone after them (`ladder.acknowledge_flag`). These are the lines beside that button and
the one after it, in the reader's language, through docs/plain-words.md like every line.
"""

from __future__ import annotations

from collections.abc import Mapping

LANGUAGES = ("en", "ms", "zh")

# @patient
ASKED: Mapping[str, tuple[str, str]] = {
    "en": (
        "Nura asked you to check on {name} on {day} at {time}.",
        "Once you say you have it, Nura asks nobody else.",
    ),
    "ms": (
        "Nura minta anda tengok {name} pada {day}, {time}.",
        "Bila anda kata anda uruskan, Nura tidak minta orang lain.",
    ),
    "zh": (
        "Nura 在{day}{time}请您去看看{name}。",
        "您说您来处理以后，Nura 就不再问别人。",
    ),
}
"""Beside the button: who was asked about whom, and what the button does."""

# @patient
ANSWERED: Mapping[str, str] = {
    "en": "Nura asks nobody else now.",
    "ms": "Nura tidak minta orang lain sekarang.",
    "zh": "Nura 现在不再问别人了。",
}
"""After the button: the ladder stopped."""


def language_of(asked: str | None) -> str:
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else "en"


def asked_lines(*, name: str, day: str, time: str, language: str | None) -> list[str]:
    """`day` and `time` are his words for when the ladder started ("Monday 14 September",
    "10 in the morning"): a red flag's moment matters as much as its day."""
    return [line.format(name=name, day=day, time=time) for line in ASKED[language_of(language)]]


def answered_lines(language: str | None) -> list[str]:
    return [ANSWERED[language_of(language)]]
