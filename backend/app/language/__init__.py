"""The same words every time, in every language he reads or hears (E22).

`glossary` is docs/plain-words.md as a table: his words for things, per language where the doc
gives them, and the variants that are never said. `memory` is every patient string in every
catalogue — backend and web — in one table keyed by catalogue, key and language, with the
checker `make language` runs over it. `voice_script` renders a card's verified lines as the
script it is spoken from. `review` is the pharmacist's queue: new sources and the first fifty
renderings of each kind of card, de-identified, decided by staff and never by a patient key.
"""
