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

from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, resolve_key_context
from app.keys.scopes import Scope
from app.memory.episodic import record_event, store_artifact
from app.memory.models import ArtifactKind, EventKind, SourceChannel
from app.memory.semantic import assert_fact, supersede_fact
from app.regions import Region
from app.state.models import Dimension, NotRenderedFromState, StateTrigger
from app.state.service import StaleState, current_state, recompute
from tests.support import RenderedCard, render_card

MONDAY = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
SHA = "b" * 64


async def _pa(session: AsyncSession) -> KeyContext:
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110004"
    )
    profile = await create_own_profile(session, region=Region.SG, owner=pa)
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


async def _a_reading(
    session: AsyncSession, context: KeyContext, *, systolic: int, at: datetime
) -> tuple[object, object]:
    """A blood pressure read off a photo of the book: the artefact, then the fact."""
    photo = await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"sg/profiles/pa/{at.date()}/bp-book.jpg",
        content_type="image/jpeg",
        sha256=SHA,
        captured_at=at,
        source_channel=SourceChannel.APP,
        region=Region.SG,
        now=at,
    )
    fact = await assert_fact(
        session,
        context=context,
        subject="blood_pressure",
        attribute="systolic",
        value=systolic,
        unit="mmHg",
        confidence=0.9,
        artifact_id=photo.id,
        now=at,
    )
    return photo, fact


async def test_state_recomputes_on_any_new_fact(sg: AsyncSession) -> None:
    owner = await _pa(sg)

    first = await current_state(sg, context=owner, now=MONDAY)
    assert first.trigger is StateTrigger.FIRST
    assert first.sequence == 1

    _, fact = await _a_reading(sg, owner, systolic=138, at=MONDAY + timedelta(hours=1))

    after = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=2))
    assert after.id != first.id
    assert after.sequence == 2
    assert after.supersedes_id == first.id

    # The trigger is recorded, and it names the fact that caused it.
    assert after.trigger is StateTrigger.NEW_FACT
    assert after.trigger_fact_id == fact.id

    # The reading is folded into the clinical dimension, still naming the photo it was read
    # from, so anything rendered from this State can cite the page.
    clinical = after.dimension(Dimension.CLINICAL)
    assert clinical is not None
    reading = clinical["facts"]["blood_pressure"]["systolic"]
    assert reading["value"] == 138
    assert reading["fact_id"] == str(fact.id)
    assert reading["artifact_id"] is not None


async def test_a_corrected_fact_recomputes_state_too(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    _, fact = await _a_reading(sg, owner, systolic=138, at=MONDAY)
    before = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=1))

    corrected = await supersede_fact(
        sg,
        context=owner,
        fact_id=fact.id,
        value=158,
        confidence=1.0,
        now=MONDAY + timedelta(hours=2),
    )

    after = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=3))
    assert after.id != before.id
    assert after.trigger is StateTrigger.NEW_FACT
    assert after.trigger_fact_id == corrected.id
    clinical = after.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert clinical["facts"]["blood_pressure"]["systolic"]["value"] == 158


async def test_every_card_records_the_state_it_was_rendered_from(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    await _a_reading(sg, owner, systolic=138, at=MONDAY)
    state = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=1))

    card = await render_card(
        sg, owner, state=state, scope=Scope.READINGS, now=MONDAY + timedelta(hours=1)
    )
    assert card.state_id == state.id

    # And the State is still reachable from the card: the reasons it was rendered for are
    # in the snapshot, not copied onto the card.
    assert state.dimension(Dimension.CLINICAL) is not None


async def test_a_card_cannot_be_written_without_the_state_it_came_from(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    await current_state(sg, context=owner, now=MONDAY)

    # Nothing renders without State: the table refuses a card that names none, so no path
    # that skips the renderer can slip one in.
    sg.add(RenderedCard(profile_id=owner.profile_id, scope=Scope.READINGS, kind="reading"))
    with pytest.raises(NotRenderedFromState):
        await sg.flush()
    await sg.rollback()


async def test_a_card_is_not_rendered_from_a_state_the_facts_have_moved_past(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    state = await current_state(sg, context=owner, now=MONDAY)

    await record_event(
        sg,
        context=owner,
        kind=EventKind.READING,
        occurred_at=MONDAY + timedelta(hours=1),
        label="blood pressure, morning",
        now=MONDAY + timedelta(hours=1),
    )
    await _a_reading(sg, owner, systolic=138, at=MONDAY + timedelta(hours=1))

    with pytest.raises(StaleState):
        await render_card(
            sg, owner, state=state, scope=Scope.READINGS, now=MONDAY + timedelta(hours=2)
        )


async def test_all_six_dimensions_are_computed(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    state = await recompute(sg, context=owner, now=MONDAY)
    for dimension in Dimension:
        assert state.dimension(dimension) is not None, dimension
    assert not state.withheld
