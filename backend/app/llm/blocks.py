"""Reading a model's answer out of its content blocks.

A message's `content` is a list of typed blocks, and the text is not promised to be the first
of them: a model that thinks before it answers puts a `thinking` block ahead of the `text` one
(live, 2026-09-18: the extractor read a real PDF, the API answered 200, and
`message.content[0].text` raised `AttributeError: 'ThinkingBlock' object has no attribute
'text'` — the page was reported unread when it had been read). Every adapter that wants the
answer's text asks here, by the block's type, never by its position.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class NoTextInAnswer(ValueError):
    """The model's answer held no text block at all."""


def answer_text(message: Any) -> str:
    """The answer's text: every `text` block's text, in order, joined. Blocks of any other
    type — thinking, tool use, a server tool's result — are passed over. Raises
    `NoTextInAnswer` when there is none, so a caller's own "did not match" path says so."""
    pieces: list[str] = []
    for block in getattr(message, "content", None) or ():
        kind = block.get("type") if isinstance(block, Mapping) else getattr(block, "type", None)
        if kind != "text":
            continue
        text = block.get("text") if isinstance(block, Mapping) else getattr(block, "text", None)
        if isinstance(text, str):
            pieces.append(text)
    if not pieces:
        raise NoTextInAnswer("the model's answer held no text block")
    return "".join(pieces)
