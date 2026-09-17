"""The recommendation engine's own layer (docs/recommendation-engine.md §2, ADR 0016).

Everything Nura knows — the record, patterns, asked topics — turned into candidates for the
outputs that already exist: reminders, visit prep, reads, clips, nudges. The broker writes no
words and no rows, the way the retriever does not; each output still takes its own rules,
verifier and cap.

`models` holds the shapes: `Evidence` (one id, its kind, the scope it rests on), `Candidate`
(a rule's proposal — never without `because`, or `NoEvidence`), `OutputKind`, `SafetyClass`
and `Audience` (RE-01: no evidence, no candidate). `topics` is the topic catalogue and the
`TopicTagger` port (RE-04). Later stories add the rule catalogue (`rules.py`), the broker
itself (`broker.py`) and the `Ranker` port (`rank.py`), in the pattern this package already
sets — a port in this package, a conformance suite in `tests/`, two adapters, never a direct
call into a library or a model.
"""
