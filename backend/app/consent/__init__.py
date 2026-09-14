"""Consent: what the patient, or someone acting for him, agreed to, in which words, and when.

`models` is the row, `texts` is the catalogue of the wording ever shown, `service` gives,
withdraws, lists and checks a consent, and `export` turns the record into a document a
person can hold. Every read and write goes through `app.audit.access`, so consent is
reached the way the rest of the graph is: with a key context, and with a line in the trail.
"""
