"""The strings catalogue: every sentence a patient reads or hears that the backend writes.

The first patient-facing strings live here, so that `make plain-words` and the reviewer look
in one place. Each is tagged `@patient` and follows `docs/plain-words.md`: whole sentences,
one idea per line, say what to do and who does the next thing, the same words every time.
"""

from __future__ import annotations

CODE_WORKS_FOR = "The code works for 10 minutes."
"""@patient The one line every code message and the sign-in screen share."""

PHONE_CODE_SELF = (
    "Your Nura code is {code}.",
    "Type it into the Nura app to sign in.",
    CODE_WORKS_FOR,
    "Nura will never call you to ask for it.",
)
"""@patient The message a phone receives when the person asked for the code himself."""

PHONE_CODE_ON_BEHALF = (
    "Your Nura code is {code}.",
    "{who} asked for this code, to sign you in.",
    "Type it into the Nura app.",
    CODE_WORKS_FOR,
    "If you did not expect this, call {who} first.",
)
"""@patient The message when someone else — the daughter setting him up — asked for it."""


def phone_code_message(code: str, *, asked_by: str | None = None) -> str:
    """The text a phone receives with its six digits, for the person or on his behalf."""
    lines = PHONE_CODE_SELF if asked_by is None else PHONE_CODE_ON_BEHALF
    return "\n".join(lines).format(code=code, who=asked_by or "")


# --- capture (E02) ---------------------------------------------------------------------------

COULD_NOT_READ = (
    "Nura could not read this.",
    "Please type it.",
)
"""@patient The lines beside a field on a review card that Nura could not read (E02-02)."""

NOT_A_HEALTH_PAPER = ("This does not look like a health paper.",)
"""@patient The line on a card for a page that is not a health paper: a receipt (E02-03)."""

NOT_A_MACHINE_SCREEN = ("This does not look like the screen of a machine.",)
"""@patient The line on a card for a photo sent as a machine screen that is not one (E02-08)."""

COULD_NOT_HEAR = (
    "Nura could not hear this note.",
    "Nura kept the note.",
)
"""@patient The lines under a voice note Nura could not hear; the recording is kept (E02-06)."""


# --- demo mode (ADR 0008) --------------------------------------------------------------------
# A demo deployment says so on every page it serves, in the person's language. The web client
# carries the same words in web/src/strings; these are the printable card's.

# @patient headline
DEMO_HEADLINE: dict[str, str] = {
    "en": "Demo — not for real health information",
    "ms": "Demo — bukan untuk maklumat kesihatan sebenar",
    "zh": "演示版 — 不用于真实的健康信息",
}

# @patient
DEMO_LINES: dict[str, tuple[str, ...]] = {
    "en": ("This is a demo.", "Do not put real health information in it."),
    "ms": ("Ini ialah demo.", "Jangan masukkan maklumat kesihatan sebenar."),
    "zh": ("这是演示版。", "请不要输入真实的健康信息。"),
}
