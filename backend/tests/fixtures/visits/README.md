# Visit transcripts

The transcripts the fixture summariser (`app/reasoning/visits/summary.py`) answers from, by
the sha256 of the transcript text. Each file carries the transcript itself, its digest, and
the structure a summariser would hear in it: actions as codes the templates know, medicine
changes as a drug and a kind of change (never an amount), follow-ups, and facts heard, each
with where in the transcript it was heard and how sure.

No real person: the names are the docs' example names. No live model call: a model in the
profile's region is a later adapter behind the same `Summariser` protocol.

- `routine-bp-review.json` — a routine blood pressure visit with one dose change (rendered
  as "Ask Dr Tan about the new amount of the water pill."), a follow-up, actions, a reading.
- `red-flag-chest-pain.json` — a visit at which a red-flag word is heard; the card carries
  the flag and "Call Dr Tan today." first.
