"""The refusals the family modules share, and the one check they all make."""

from __future__ import annotations

from collections.abc import Sequence

from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole


class NotAChief(Refusal):
    """The family's arrangements — the roster, the tasks, the messages to him, the papers
    behind a basis — are the owner's and his chief's to make."""


class NotPlainWords(Refusal):
    """Words that reach him did not pass docs/plain-words.md. The findings say which line
    and why, so the composer can fix it; nothing was kept."""

    def __init__(self, findings: Sequence[str]) -> None:
        super().__init__("; ".join(findings))
        self.findings = list(findings)


def a_chief(context: KeyContext) -> None:
    """Refuse anyone but the owner or a chief. The door around the caller writes it down."""
    if not context.is_owner and context.role is not KeyRole.CHIEF:
        raise NotAChief(f"a {context.role} key does not arrange this")
