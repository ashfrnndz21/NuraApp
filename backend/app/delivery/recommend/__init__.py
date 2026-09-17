"""The recommendation engine's own layer (docs/recommendation-engine.md §2).

`topics` is the first piece: the topic catalogue and the `TopicTagger` port (RE-04). Later
stories add series, patterns and the broker beside it, in the pattern this package already
sets — a port in this package, a conformance suite in `tests/`, two adapters, never a direct
call into a library or a model.
"""
