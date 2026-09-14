"""The visit loop: brief, questions, post-visit summary, memos (E05-01, -02, -05, -06).

`gaps` notices what the record is missing. `brief` composes the pre-visit brief from State.
`questions` turns gaps, memos and flags into questions for the doctor, editable by a person,
one card for him. `summary` reads a transcript into a card the person confirms; on his yes,
actions become memos, a medicine change becomes a flag and a question (never a change),
follow-ups become planned visits, facts heard become facts citing the transcript. `memos`
files one line in his words against the next appointment and consolidates them into the card
at the end of every conversation. Every line is rendered from `strings` and passes the
plain-words verifier, or is refused.
"""
