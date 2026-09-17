"""The recommendation engine's own layer (docs/recommendation-engine.md §2).

`topics` is the topic catalogue and the `TopicTagger` port (RE-04). `models` is the broker's
own types: `Evidence`, `Candidate`, `NoEvidence` (RE-01, vendored here — see
`app.delivery.recommend.broker`'s module doc for why). `rules` is the rule catalogue and
`rank` is the `Ranker` port (RE-06). `broker` is the one place they meet: `slate()`. Later
stories (patterns, RE-13 onward) add beside these, in the pattern this package already sets —
a port in this package, a conformance suite in `tests/`, two adapters, never a direct call
into a library or a model.
"""
