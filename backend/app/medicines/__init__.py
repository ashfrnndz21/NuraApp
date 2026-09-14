"""Medicines: the reconciled list, the running count, the interaction screen and the story.

A medication line is what a label said, identified through the licensed registry
(`app.drugs`), confirmed by a person, and kept as a Fact with provenance plus a typed row
here. `reconcile` classifies a new label against the active lines — a refill, a dose change,
a new line, or the same label twice — and every outcome that writes anything spends the
person's own yes. `record_dose_taken` is his tap. The count and the reorder date are
arithmetic over what was dispensed and what was taken. The story (`story`) is rendered from
templates in `strings`, keyed by the monograph's rule ids: the model writes no sentence here,
and no sentence tells him to start, stop or change anything.

Importing this package registers the high-risk label-photo rule on the memory store, so a
medication fact for a high-risk class cannot land without a label photo by any path.
"""

from __future__ import annotations

from app.memory import semantic
from app.safety.high_risk import label_photo_rule

if label_photo_rule not in semantic.before_fact_write:
    semantic.before_fact_write.append(label_photo_rule)
