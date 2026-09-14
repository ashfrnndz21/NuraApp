"""Medicines: the reconciled list, the running count, the interaction screen and the story.

A medication line is what a label said, identified through the licensed registry
(`app.drugs`), confirmed by a person, and kept as a Fact with provenance plus a typed row
here. `reconcile` classifies a new label against the active lines — a refill, a dose change,
a new line, or the same label twice — and every outcome that writes anything spends the
person's own yes. `record_dose_taken` is his tap. The count and the reorder date are
arithmetic over what was dispensed and what was taken. The story (`story`) is rendered from
templates in `strings`, keyed by the monograph's rule ids: the model writes no sentence here,
and no sentence tells him to start, stop or change anything.

The high-risk label-photo rule is `app.safety.high_risk`, a hook the safety module itself
registers on the memory store when it is imported; importing this package imports it, so a
medication fact for a high-risk class cannot land without a label photo by any path.
"""

from __future__ import annotations

import app.safety.high_risk  # noqa: F401  — registers the label-photo rule on the memory store
