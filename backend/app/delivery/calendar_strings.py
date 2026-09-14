"""The lines a calendar proposal says to him (E18-02), in his three languages.

A calendar event that looks like a visit is a proposal, never a visit: the lines say what
Nura found, when it is, and that it is his yes that adds it. Each template is a whole line;
`app.ingestion.connectors.service` fills and verifies them.
"""

from __future__ import annotations

from collections.abc import Mapping

# @patient
FOUND: Mapping[str, str] = {
    "en": "Nura found a visit to {provider} in the calendar.",
    "ms": "Nura jumpa lawatan ke {provider} dalam kalendar.",
    "zh": "Nura 在日历里找到一次见{provider}的时间。",
}

# @patient
ON_DAY_AT: Mapping[str, str] = {
    "en": "It is on {day} at {clock}.",
    "ms": "Ia pada {day}, {clock}.",
    "zh": "时间：{day}{clock}。",
}

# @patient
ON_DAY: Mapping[str, str] = {
    "en": "It is on {day}.",
    "ms": "Ia pada {day}.",
    "zh": "时间：{day}。",
}

# @patient action
SAY_YES: Mapping[str, str] = {
    "en": "Tap Yes to add it to your visits.",
    "ms": "Tekan Ya untuk tambah ke lawatan anda.",
    "zh": "按「是」，就加到您看医生的记录里。",
}
"""Who does the next thing: he does, with his yes. Nothing is added without it."""

# @patient
ADDED: Mapping[str, str] = {
    "en": "It is in your visits now.",
    "ms": "Ia sudah ada dalam lawatan anda.",
    "zh": "已经加到您看医生的记录里了。",
}

# @patient phrase
THE_DOCTOR: Mapping[str, str] = {"en": "your doctor", "ms": "doktor anda", "zh": "您的医生"}
"""When the name the calendar gave is not a word he can read (an abbreviation, a code)."""
