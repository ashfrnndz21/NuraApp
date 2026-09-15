"""The two questions at the key-accept step (#143), in his words: may Nura message you on
WhatsApp, and will you join the family's group there. A yes binds to these words by version
(`app.channels.whatsapp.opt_in`); new words are a new version, never an edit.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.channels.strings import language_of

OPT_IN_VERSION = "1"

# @patient
OPT_IN_MESSAGES: Mapping[str, tuple[str, ...]] = {
    "en": ("Nura may message you on WhatsApp.",),
    "ms": ("Nura boleh hantar mesej kepada anda di WhatsApp.",),
    "zh": ("Nura 可以在 WhatsApp 上给您发消息。",),
}

# @patient
OPT_IN_GROUP: Mapping[str, tuple[str, ...]] = {
    "en": (
        "Do you want to join the family group on WhatsApp?",
        "Everyone in it can see your number.",
    ),
    "ms": (
        "Anda mahu sertai kumpulan keluarga di WhatsApp?",
        "Semua orang di dalamnya boleh nampak nombor anda.",
    ),
    "zh": ("您想加入 WhatsApp 上的家人群组吗？", "群里的每个人都能看到您的电话号码。"),
}


def opt_in_questions(language: str | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The two questions, in `language`: WhatsApp, then the family's group."""
    lang = language_of(language)
    return OPT_IN_MESSAGES[lang], OPT_IN_GROUP[lang]
