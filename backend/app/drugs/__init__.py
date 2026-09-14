"""Licensed drug data, behind one port.

Identification, interactions and dosing guidance come from a licensed registry and from
nowhere else: not from a model, not from anything a person typed, not from memory. `registry`
is the port — what any registry answers — and `fixture` is the one that runs in the tests and
on a dev run, loaded from `tests/fixtures/drugs/registry.json`. `client` picks the registry a
deployment runs on. Nothing here writes a sentence: a monograph is rule ids, and the words
for them live in `app.medicines.strings`.
"""
