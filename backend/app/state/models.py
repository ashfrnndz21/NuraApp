"""The State snapshot, and the mark every rendered thing carries.

A snapshot is how someone is, in six dimensions, at one moment, worked out from what is
known at that moment. It is written once and never edited: when a fact lands, a new snapshot
supersedes it and names both the one before it and the fact that caused it, so the question
"why did the app say that on Tuesday" is answered by a row and not by a reconstruction.

`RenderedFromState` is the other half. Anything shown to a person — a card, a clip, a nudge,
a message — carries the id of the snapshot it was rendered from, in a column that cannot be
left empty. That is what makes State the choke point rather than a convention: there is no
way to write a card and forget which State justified it.

Nothing in a snapshot is free text. The six dimensions are JSON of short codes, ids and the
values of the facts they were computed from; an episode or a visit is named by its id, never
by its label. The snapshot is the record folded, so it is read under the record's scope.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.errors import Refusal


class Dimension(StrEnum):
    """The six dimensions of docs/stage1-product-design.md section 2. Every one of them is
    computed, every time."""

    CLINICAL = "clinical"
    FUNCTIONAL = "functional"
    COGNITIVE = "cognitive"
    SITUATIONAL = "situational"
    PREFERENCE = "preference"
    FAMILY = "family"


class Posture(StrEnum):
    """How the day is held, in one word: the wash on the screen and the order of the feed.

    It is not a finding and it is not a grade. `ACT` means there is something for a person
    to do or to ask, never that Nura has decided what is wrong.
    """

    STABLE = "stable"
    WATCH = "watch"
    ACT = "act"


POSTURE_ORDER: tuple[Posture, ...] = (Posture.STABLE, Posture.WATCH, Posture.ACT)


def worse_of(one: Posture, other: Posture) -> Posture:
    """The more attentive of two postures. State never talks itself down."""
    return max(one, other, key=POSTURE_ORDER.index)


class StateTrigger(StrEnum):
    """What made State recompute. Every snapshot records one, and a `NEW_FACT` names its fact."""

    FIRST = "first"
    NEW_FACT = "new_fact"
    NEW_EVENT = "new_event"
    EPISODE_CHANGE = "episode_change"
    SPINE_CHANGE = "spine_change"
    KEY_CHANGE = "key_change"
    TIME_PASSED = "time_passed"
    ASKED = "asked"
    """Recomputed on demand with nothing moved: the same facts, worked out again."""


class NotRenderedFromState(Refusal):
    """Nothing renders without State. This card named none."""


class StateSnapshot(ProfileScoped, Base):
    """One computation of the six dimensions for one profile.

    `sequence` counts from one per profile and is unique, so the current snapshot is the
    highest one and two writers cannot both believe they wrote it. `computed_from` is the
    ids of everything the six were worked out from — facts, episodes, events, visits, keys —
    which is how a later read can tell whether the record has moved past this snapshot
    without comparing what it says. `stale_after` is the moment a window in it closes — a
    visit coming inside the week, a fact that stops holding — so time alone is enough to
    make State recompute.
    """

    __tablename__ = "state_snapshot"
    __table_args__ = (
        UniqueConstraint("profile_id", "sequence", name="uq_state_snapshot_sequence"),
        UniqueConstraint("profile_id", "id", name="uq_state_snapshot_profile_id_id"),
        # A snapshot that says a fact caused it must name the fact, and the fact it names
        # is on the same profile. Same discipline as provenance on the fact itself.
        CheckConstraint(
            "trigger <> 'new_fact' OR trigger_fact_id IS NOT NULL",
            name="ck_state_trigger_names_its_fact",
        ),
        ForeignKeyConstraint(
            ["profile_id", "trigger_fact_id"],
            ["fact.profile_id", "fact.id"],
            name="fk_state_snapshot_trigger_fact_profile",
        ),
        ForeignKeyConstraint(
            ["profile_id", "supersedes_id"],
            ["state_snapshot.profile_id", "state_snapshot.id"],
            name="fk_state_snapshot_supersedes_profile",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sequence: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    # The worst of the six dimensions' postures. Each dimension carries its own, and why.
    posture: Mapped[Posture] = mapped_column(enum_column(Posture, "posture"))
    trigger: Mapped[StateTrigger] = mapped_column(enum_column(StateTrigger, "state_trigger"))
    trigger_fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fact.id"), default=None)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("state_snapshot.id"), default=None
    )
    # The six dimensions, one column each, so a reader of the table can see them all named.
    clinical: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    functional: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cognitive: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    situational: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    preference: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    family: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # The ids this was computed from, by kind (`app.state.service.Inputs.fingerprint`).
    computed_from: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    stale_after: Mapped[datetime | None] = mapped_column(default=None)

    def dimensions(self) -> dict[Dimension, dict[str, Any]]:
        return {dimension: getattr(self, dimension.value) for dimension in Dimension}


# A snapshot is what was known then. It is superseded, never edited (`app.db.ImmutableRow`).
frozen(StateSnapshot)


class RenderedFromState:
    """Mixin for every table of something a person is shown.

    The column is not nullable and the guard below refuses a row that leaves it empty, so
    "every card records the State it was rendered from" is a property of the schema rather
    than a rule each renderer has to remember.
    """

    state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("state_snapshot.id"), index=True)


@event.listens_for(Mapper, "before_insert")
def _a_card_names_its_state(mapper: Any, connection: Any, target: Any) -> None:
    """Refuse any rendered row that reaches the database without a State behind it."""
    if isinstance(target, RenderedFromState) and getattr(target, "state_id", None) is None:
        raise NotRenderedFromState("a rendered row names the state it was rendered from")
