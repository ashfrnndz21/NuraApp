"""The recommendation broker (docs/recommendation-engine.md, ADR 0016).

Everything Nura knows — the record, patterns, asked topics — turned into candidates for the
outputs that already exist: reminders, visit prep, reads, clips, nudges. The broker writes no
words and no rows, the way the retriever does not; each output still takes its own rules,
verifier and cap.

`models` holds the shapes: `Evidence` (one id, its kind, the scope it rests on), `Candidate`
(a rule's proposal — never without `because`, or `NoEvidence`), `OutputKind`, `SafetyClass`
and `Audience`. This is RE-01: the types and the one rule that must hold — no evidence, no
candidate. The catalogue that produces candidates (`rules.py`), the broker itself
(`broker.py`) and the `Ranker` port (`rank.py`) are later stories (RE-04 through RE-09).
"""
