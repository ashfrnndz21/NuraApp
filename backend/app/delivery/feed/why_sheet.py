"""The Why sheet's plain lines (docs/recommendation-engine.md §3.3, story RE-08).

Every card already carries its plain reason (`Why.plain`, `app.delivery.feed.items`) and the
one scope it and everything it rests on were written under (`FeedItem.scope`, the door
`create_item` writes the whole card behind). This turns that into the lines the "Why am I
seeing this?" sheet shows: the reason itself, in words, when the reader's key covers the
card's scope — or the line that says it rests on a part of the record the reader cannot see,
withheld, never silent, in the reader's own voice (`WHY` / `WHY_THEIRS`,
`app.delivery.strings`), in English, Malay and Chinese.

No row crosses here: this reads nothing, it only decides which of two already-written
sentences a reader is shown.
"""

from __future__ import annotations

from app.delivery.strings import WHY, WHY_THEIRS, language_for
from app.keys.context import KeyContext
from app.keys.scopes import Scope


def why_lines(
    plain: str,
    *,
    scope: Scope,
    context: KeyContext,
    language: str,
    his: bool,
    patient_name: str = "",
) -> tuple[str, ...]:
    """The Why sheet's lines for this reader.

    `scope` is the door the card — and every piece of evidence it names — was written behind.
    A key that does not cover it never reads the card's own words: only that a part of the
    record is withheld, in the reader's own voice. A key that does cover it reads the card's
    plain reason, unchanged; an empty reason is no line at all, never a blank one.
    """
    code = language_for(language)
    if not context.allows(scope):
        if his:
            return (WHY[code]["withheld"],)
        return (WHY_THEIRS[code]["withheld"].format(patient=patient_name),)
    return (plain,) if plain else ()
