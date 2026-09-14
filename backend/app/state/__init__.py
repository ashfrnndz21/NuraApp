"""State: how someone is, in six dimensions, recomputed from the record and stamped on cards.

`models` holds the snapshot table and the mixin that makes a card name the State it came
from. `dimensions` works the six out from facts, episodes, the spine and the keys, without
judging any of them. `service` is the door: recompute, read, and render from.

The layer sits between memory and everything that shows anything. Nothing renders without a
State, and no State exists without the facts it was computed from. Importing this package
wires the recompute onto the memory store, so that a fact cannot land without State moving.
"""

from __future__ import annotations

from app.memory import semantic
from app.state.service import recompute_on_fact

if recompute_on_fact not in semantic.after_fact_write:
    semantic.after_fact_write.append(recompute_on_fact)
