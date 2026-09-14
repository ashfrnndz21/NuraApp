"""Ingestion: paper in, facts out — with a person's yes in between.

A photo comes in and its bytes go to the object store of the profile's region (`objects`);
the row that names them is an Artifact (`photos`). Extraction (`extract`) runs behind an
interface and answers with fields, each carrying a confidence; nothing it says is a fact
yet. The fields become a review card (`review`): the one thing a person edits — confirm,
correct or reject, field by field — and the one place a proposed value waits. On the
person's explicit yes, each confirmed or corrected field is written as a Fact with the
photo as its provenance and the person as its confirmer; a rejected field writes nothing.
Facts themselves are never edited; a wrong one is superseded (`app.memory.semantic`).

Importing this package wires the label-photo rule for a high-risk drug
(`app.safety.high_risk`) onto the memory store, so that a medicine dose cannot land from
anything but a photo whichever surface writes it.
"""

from __future__ import annotations

import app.safety.high_risk  # noqa: F401  — registers the rule on `before_fact_write`
