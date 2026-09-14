"""E00-04 acceptance.

    State recomputes on any new fact; every card records the State it was rendered from.

The first half is the Session 2 line from TASKS.md: adding a reading recomputes State and
records the trigger. The second half is the structural promise of the architecture — State is
the choke point, so a card that does not name the State it came from cannot be written at
all, and a State the facts have moved past cannot be rendered from.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.db import ImmutableRow, as_utc
from app.drafts import FactDraft
from app.identity.service import create_own_profile, register_person
from app.keys.confirm import confirm
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event, store_artifact
from app.memory.models import ArtifactKind, ConfidenceState, EventKind, Fact, SourceChannel
from app.memory.semantic import assert_fact, supersede_fact
from app.regions import Region
from app.state.models import (
    Dimension,
    NotRenderedFromState,
    Posture,
    StateSnapshot,
    StateTrigger,
)
from app.state.service import StaleState, current_state, latest_snapshot, recompute_state
from tests.support import OPENING_CONSENT, RenderedCard, agree_to_family_sharing, render_card

MONDAY = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
SHA = "b" * 64


async def _pa(session: AsyncSession) -> KeyContext:
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110004"
    )
    profile = await create_own_profile(session, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


async def _a_reading(session: AsyncSession, context: KeyContext, *, systolic: int) -> Fact:
    """A blood pressure read off a photo of the book: the artefact, then the fact."""
    photo = await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"sg/profiles/pa/{systolic}/bp-book.jpg",
        content_type="image/jpeg",
        sha256=SHA,
        captured_at=MONDAY,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )
    return await assert_fact(
        session,
        context=context,
        subject="blood_pressure",
        attribute="systolic",
        value=systolic,
        unit="mmHg",
        confidence=0.9,
        artifact_id=photo.id,
    )


async def test_adding_a_reading_recomputes_state_and_records_the_trigger(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)

    first = await current_state(sg, context=owner)
    assert first.trigger is StateTrigger.FIRST
    assert first.sequence == 1

    clock.step(timedelta(hours=1))
    fact = await _a_reading(sg, owner, systolic=138)

    # The snapshot was written as the fact landed, in the same unit of work: no read had to
    # ask for it. It supersedes the first and names the fact, and why, as its trigger.
    written = await latest_snapshot(sg, context=owner)
    assert written is not None
    assert written.id != first.id
    assert written.sequence == 2
    assert written.supersedes_id == first.id
    assert written.trigger is StateTrigger.NEW_FACT
    assert written.trigger_fact_id == fact.id
    assert as_utc(written.computed_at) == MONDAY + timedelta(hours=1)

    # And reading State back finds that snapshot current: nothing has moved since.
    after = await current_state(sg, context=owner)
    assert after.id == written.id
    assert after.stale is False

    # The reading is folded into the clinical dimension, still naming the photo it was read
    # from, so anything rendered from this State can cite the page; and the dimension says
    # which facts it was computed from.
    clinical = after.dimension(Dimension.CLINICAL)
    assert clinical is not None
    reading = clinical["facts"]["blood_pressure"]["systolic"]
    assert reading["value"] == 138
    assert reading["fact_id"] == str(fact.id)
    assert reading["artifact_id"] is not None
    assert clinical["fact_ids"] == [str(fact.id)]
    assert clinical["posture"] == Posture.STABLE.value


async def test_a_corrected_fact_recomputes_state_too(sg: AsyncSession, clock: FrozenClock) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    fact = await _a_reading(sg, owner, systolic=138)
    before = await current_state(sg, context=owner)

    clock.step(timedelta(hours=2))
    corrected = await supersede_fact(sg, context=owner, fact_id=fact.id, value=158, confidence=1.0)

    after = await current_state(sg, context=owner)
    assert after.id != before.id
    assert after.trigger is StateTrigger.NEW_FACT
    assert after.trigger_fact_id == corrected.id
    clinical = after.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert clinical["facts"]["blood_pressure"]["systolic"]["value"] == 158
    assert clinical["fact_ids"] == [str(corrected.id)]


async def test_a_disputed_fact_does_not_move_state(sg: AsyncSession, clock: FrozenClock) -> None:
    """A dispute is an open question beside the fact, not a fact that holds: the person's
    number stays current (`ConfirmedFactStands`) and State stays where it was."""
    clock.set(MONDAY)
    owner = await _pa(sg)
    fact = await _a_reading(sg, owner, systolic=138)
    before = await current_state(sg, context=owner)

    clock.step(timedelta(hours=1))
    draft = FactDraft(
        subject=fact.subject,
        attribute=fact.attribute,
        value=150,
        unit=fact.unit,
        confidence=0.9,
        confidence_state=ConfidenceState.DISPUTED,
        artifact_id=fact.artifact_id,
        event_id=None,
        episode_id=None,
        supersedes_id=fact.id,
    )
    disputed = await supersede_fact(
        sg,
        context=owner,
        fact_id=fact.id,
        value=150,
        confidence=0.9,
        confidence_state=ConfidenceState.DISPUTED,
        confirmation_id=(await confirm(sg, owner, draft)).id,
    )
    assert disputed.confidence_state is ConfidenceState.DISPUTED

    after = await current_state(sg, context=owner)
    assert after.id == before.id
    assert after.stale is False
    clinical = after.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert clinical["facts"]["blood_pressure"]["systolic"]["value"] == 138
    assert str(disputed.id) not in clinical["fact_ids"]


async def test_recompute_is_idempotent_for_the_same_facts(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await _a_reading(sg, owner, systolic=138)

    # Reading State with nothing new does not write another snapshot.
    once = await current_state(sg, context=owner)
    again = await current_state(sg, context=owner)
    assert again.id == once.id

    # Asking for a recompute outright does write one — snapshots are rows, never edited —
    # and it says the same thing: same dimensions, same posture, computed from the same ids.
    clock.step(timedelta(hours=1))
    asked = await recompute_state(sg, context=owner)
    assert asked.id != once.id
    assert asked.supersedes_id == once.id
    assert asked.trigger is StateTrigger.ASKED
    assert asked.trigger_fact_id is None
    assert asked.posture is once.posture
    assert asked.dimensions == once.dimensions
    written = await latest_snapshot(sg, context=owner)
    earlier = await sg.get(StateSnapshot, once.id)
    assert written is not None and earlier is not None
    assert written.computed_from == earlier.computed_from


async def test_a_snapshot_is_frozen(sg: AsyncSession, clock: FrozenClock) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    state = await recompute_state(sg, context=owner)

    snapshot = await sg.get(StateSnapshot, state.id)
    assert snapshot is not None
    snapshot.posture = Posture.ACT
    snapshot.clinical = {"facts": {}}
    with pytest.raises(ImmutableRow):
        await sg.flush()
    await sg.rollback()


async def test_a_caregiver_key_without_records_cannot_read_state(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await _a_reading(sg, owner, systolic=138)
    await current_state(sg, context=owner)

    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110005")
    await agree_to_family_sharing(sg, owner, mei, scopes={Scope.MEDICINES, Scope.VISITS})
    await grant_key(
        sg,
        context=owner,
        holder=mei,
        role=KeyRole.CAREGIVER,
        scopes=[Scope.MEDICINES, Scope.VISITS],
    )
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=mei.id, profile_id=owner.profile_id
    )

    with pytest.raises(OutOfScope) as refused:
        await current_state(sg, context=held)
    assert refused.value.scope is Scope.RECORDS

    # The refusal is on the owner's trail: her reach at the record, by name, and nothing of
    # what the snapshot held.
    trail = await read_audit(sg, context=owner, actor_person_id=mei.id)
    assert [(e.action, e.scope, e.target, e.outcome, e.refused_because) for e in trail] == [
        (Action.READ, Scope.RECORDS, StateSnapshot.__tablename__, Outcome.REFUSED, "OutOfScope")
    ]


async def test_every_card_records_the_state_it_was_rendered_from(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await _a_reading(sg, owner, systolic=138)
    state = await current_state(sg, context=owner)

    card = await render_card(sg, owner, state=state, scope=Scope.READINGS)
    assert card.state_id == state.id

    # And the State is still reachable from the card: the reasons it was rendered for are
    # in the snapshot, not copied onto the card.
    assert state.dimension(Dimension.CLINICAL) is not None


async def test_a_card_cannot_be_written_without_the_state_it_came_from(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await current_state(sg, context=owner)

    # Nothing renders without State: the table refuses a card that names none, so no path
    # that skips the renderer can slip one in.
    sg.add(RenderedCard(profile_id=owner.profile_id, scope=Scope.READINGS, kind="reading"))
    with pytest.raises(NotRenderedFromState):
        await sg.flush()
    await sg.rollback()


async def test_a_card_is_not_rendered_from_a_state_the_facts_have_moved_past(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    state = await current_state(sg, context=owner)

    clock.step(timedelta(hours=1))
    await record_event(
        sg,
        context=owner,
        kind=EventKind.READING,
        occurred_at=MONDAY + timedelta(hours=1),
        label="blood pressure, morning",
        source_channel=SourceChannel.APP,
    )
    await _a_reading(sg, owner, systolic=138)

    with pytest.raises(StaleState):
        await render_card(sg, owner, state=state, scope=Scope.READINGS)


async def test_all_six_dimensions_are_computed(sg: AsyncSession, clock: FrozenClock) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    state = await recompute_state(sg, context=owner)
    for dimension in Dimension:
        held = state.dimension(dimension)
        assert held is not None, dimension
        assert held["posture"] == Posture.STABLE.value
        assert held["fact_ids"] == []
    assert not state.withheld
