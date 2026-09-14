"""Who may change the visits: write a transcript, confirm a summary, add or remove a
question, refresh the questions. The same footing as changing the medicines
(`app.medicines.service.CHANGERS`): the owner, the steward, a chief, a caregiver. A viewer,
a helper and a clinic key hold the visits scope to read — the brief, the questions, the
memos — and not to write. Checked at the door of every write, so a clinic's try is on the
trail as a refused write.
"""

from __future__ import annotations

from app.errors import Refusal
from app.keys.context import KeyContext
from app.medicines.service import CHANGERS


class NotTheirsToChangeVisits(Refusal):
    """A viewer, a helper or a clinic key reads the visits; it does not change them."""


def can_change_visits(context: KeyContext) -> bool:
    """Whether this key may change the visits — the question a reader asks before it chooses
    between consolidating the memos and reading them as they stand."""
    return context.is_owner or context.is_steward or context.role in CHANGERS


def may_change_visits(context: KeyContext) -> None:
    if can_change_visits(context):
        return
    raise NotTheirsToChangeVisits(f"a {context.role} key reads the visits; it does not change them")
