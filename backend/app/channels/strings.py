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
