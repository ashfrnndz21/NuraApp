"""The shapes the recommendation broker deals in (RE-01, docs/recommendation-engine.md §2.4).

**No `why`, no recommendation** (§3.3). A `Candidate` is refused at construction, not filtered
later, if it names no evidence: `Candidate.because` is a tuple of `Evidence`, and an empty one
raises `NoEvidence`. Every id it names is on this profile, and a candidate is shown only to a
key that may read every one of them — the one-door rule ADR 0004 already holds `Pattern` and
`FeelingNote` to (`readable_by`).

This module is the types only: the broker that turns State, series and patterns into
candidates (`app.delivery.recommend.broker`, RE-06), the rule catalogue (`rules.py`) and the
`Ranker` port (`rank.py`) are later stories. Nothing here reads the database or writes a row.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope


class NoEvidence(Refusal):
    """A candidate named no evidence. Nothing is recommended without a `why` (§3.3): this is
    raised at construction, in `Candidate.__post_init__`, never discovered later by a filter."""


class OutputKind(StrEnum):
    """What kind of thing a candidate becomes: which existing output it competes for a slot
    in. The broker adds no new slot (§2.1 rule 4) — it only offers the outputs that already
    exist better things to show."""

    REMINDER = "reminder"
    """A bring-line, a log prompt: `delivery/triggers/engine.py`."""
    VISIT_QUESTION = "visit_question"
    """A question for the doctor: `reasoning/visits/questions.py`."""
    BRIEF_LINE = "brief_line"
    """A line on the pre-visit brief: `reasoning/visits/brief.py`."""
    READ = "read"
    """A learning, food or story card topic: `delivery/feed/compose.py`."""
    CLIP = "clip"
    """The same topic, video preferred: `delivery/feed/clips.py`."""
    NUDGE = "nudge"
    """`delivery/nudges/engine.py`: Pattern, Curiosity."""


class SafetyClass(StrEnum):
    """How a candidate is allowed to speak (§3.1, §3.2, §3.4)."""

    RECORD_BACK = "record_back"
    """Says his own record back to him: no boundary line needed."""
    PATTERN = "pattern"
    """`Surface.PATTERN`: memo and caregiver by default, never the patient without D1."""
    EXTERNAL = "external"
    """Allowlisted content: `Surface.LEARNING_CARD`."""


class Audience(StrEnum):
    """Who a candidate's output may reach. The broker sets this; nothing downstream widens
    it (`tests/test_recommend_audience.py`, §3.2)."""

    PATIENT = "patient"
    CAREGIVER = "caregiver"
    MEMO = "memo"


@dataclass(frozen=True, slots=True)
class Evidence:
    """One id a candidate rests on, and the scope it was read under.

    `kind` names what the id is: fact, event, tap, pattern, appointment, line, asked_topic or
    engagement (§2.4) — a string, not an enum, because the set of things that can be evidence
    grows with every story that adds a new input (readings today, lifestyle logs and asked
    topics later) and this module does not own that list.
    """

    kind: str
    id: uuid.UUID
    scope: Scope

    def readable_by(self, context: KeyContext) -> bool:
        """Whether this key holds the scope this id rests on (ADR 0004: a row is read under
        the scope it was written under)."""
        return context.allows(self.scope)


@dataclass(frozen=True, slots=True)
class Candidate:
    """A rule's proposal: what it found, what it rests on, who may see it.

    `because` is never empty — `NoEvidence` at construction, not a filter later. `private_to`
    is set only when a candidate rests on his own private curiosity (search history, §3.5):
    `readable_by` then refuses every key but his own, whatever her scopes, the same rule
    `FeedItem.private_to` holds the card it becomes to (RE-01, `app.delivery.feed.rank`).
    """

    rule_id: str
    output: OutputKind
    topic: str
    """A topic code from the catalogue (RE-04, `app.delivery.recommend.topics.TopicCode`,
    not yet built): a plain string here so this module does not depend on a story that runs
    in parallel with it (docs/recommendation-engine.md §6, Wave 0)."""
    because: tuple[Evidence, ...]
    safety: SafetyClass
    audience: frozenset[Audience]
    private_to: uuid.UUID | None = None
    base: int = 0
    boosts: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.because:
            raise NoEvidence(f"{self.rule_id} names no evidence: no why, no recommendation")

    def readable_by(self, context: KeyContext) -> bool:
        """Whether this key may be shown this candidate at all: every evidence id's scope,
        and — when it rests on his own search history — only him (§2.4, §3.5). The broker
        drops every candidate this refuses; nothing downstream widens what it lets through."""
        if self.private_to is not None and self.private_to != context.person_id:
            return False
        return all(item.readable_by(context) for item in self.because)


def readable_by(evidence: Sequence[Evidence], context: KeyContext) -> bool:
    """Whether a key holds every scope a group of evidence rests on — the one-door rule
    (ADR 0004 decision 10) that already holds `Pattern` and `FeelingNote` to this, named as
    its own function so a future multi-scope evidence check (a candidate, a pattern, a note)
    reads the same way everywhere."""
    return all(item.readable_by(context) for item in evidence)
