"""Search: ask, find, act.

`ask` is natural-language recall over his own record (E03-05): a question in, an answer made
only of templates and the values of the facts it cites, every line naming the ids it rests
on, the boundary last. Which parts of the record a question is about is decided behind a port
(`retrieve.Retriever`): the keyword retriever by default, a fixture one in the tests, and a
model-backed one later behind the same port. No model is called here, and none writes a line.
"""
