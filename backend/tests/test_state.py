"""What the six dimensions hold, what moves the posture, and what a narrower key reads.

The line the boundary sits on is in here twice: a reading on its own never moves the posture,
because nothing in State judges a number; a clinician's word recorded as a fact does, because
State is repeating what the record already says.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import WidenedRead, audited_read
from app.audit.models import Outcome
from app.audit.trail import read_audit
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event, store_artifact
from app.memory.models import (
    ArtifactKind,
    EpisodeKind,
    EventKind,
    Fact,
    ProviderKind,
    SourceChannel,
)
from app.memory.semantic import assert_fact
from app.memory.spine import add_provider, book_appointment
from app.memory.working import close_episode, open_episode
from app.regions import Region
from app.state.dimensions import Phase, dimension_of
from app.state.models import (
    Dimension,
    ImmutableState,
    Posture,
    StateSnapshot,
    StateTrigger,
    worse_of,
)
from app.state.service import (
    NotRenderable,
    StaleState,
    TriggerWithoutItsFact,
    current_state,
    latest_snapshot,
    recompute,
    render_from_state,
    state_history,
)
from tests.support import Note, render_card

MONDAY = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
SHA = "c" * 64


async def _pa(session: AsyncSession) -> KeyContext:
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110011"
    )
    profile = await create_own_profile(session, region=Region.SG, owner=pa)
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


async def _fact(
    session: AsyncSession,
    context: KeyContext,
    *,
    subject: str,
    attribute: str,
    value: object,
    at: datetime = MONDAY,
    valid_to: datetime | None = None,
) -> None:
    photo = await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"sg/profiles/pa/{subject}-{attribute}.jpg",
        content_type="image/jpeg",
        sha256=SHA,
        captured_at=at,
        source_channel=SourceChannel.APP,
        region=Region.SG,
        now=at,
    )
    await assert_fact(
        session,
        context=context,
        subject=subject,
        attribute=attribute,
        value=value,
        confidence=0.9,
        artifact_id=photo.id,
        valid_to=valid_to,
        now=at,
    )


def test_a_fact_goes_to_its_dimension_and_health_is_the_default() -> None:
    assert dimension_of("mobility") is Dimension.FUNCTIONAL
    assert dimension_of("language") is Dimension.COGNITIVE
    assert dimension_of("goal") is Dimension.PREFERENCE
    assert dimension_of("fasting") is Dimension.SITUATIONAL
    assert dimension_of("blood_pressure") is Dimension.CLINICAL
    assert dimension_of("something_nobody_has_classified") is Dimension.CLINICAL


def test_state_never_talks_itself_down() -> None:
    assert worse_of(Posture.STABLE, Posture.WATCH) is Posture.WATCH
    assert worse_of(Posture.ACT, Posture.WATCH) is Posture.ACT


async def test_a_reading_on_its_own_does_not_move_the_posture(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    await _fact(sg, owner, subject="blood_pressure", attribute="systolic", value=176)

    state = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=1))

    # 176 is a number State holds, not a number State reads. Judging it belongs to reasoning
    # and to safety, with a clinician's framing; nothing here decides it is high.
    assert state.posture is Posture.STABLE
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert clinical["facts"]["blood_pressure"]["systolic"]["value"] == 176
    assert clinical["conditions"] == {}


async def test_the_posture_follows_the_word_already_in_the_record(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    await _fact(sg, owner, subject="heart_failure", attribute="control", value="watch")

    state = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=1))
    assert state.posture is Posture.WATCH
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None

    # The condition keeps the fact it came from, so the card that shows it can cite the page.
    said = clinical["conditions"]["heart_failure"]
    assert [one["value"] for one in said] == ["watch"]
    assert said[0]["artifact_id"] is not None

    # And the posture says which fact raised it.
    assert state.because == [
        {"posture": "watch", "subject": "heart_failure", "fact_id": said[0]["fact_id"]}
    ]


async def test_a_control_word_state_cannot_read_is_kept_and_is_not_a_settled_day(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    await _fact(sg, owner, subject="heart_failure", attribute="control", value="poorly controlled")

    state = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=1))
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None

    # The clinician's own words are kept and named, never dropped for not matching a list.
    assert clinical["conditions"]["heart_failure"][0]["value"] == "poorly controlled"
    assert clinical["control_not_read"][0]["subject"] == "heart_failure"
    assert state.posture is Posture.WATCH


async def test_two_facts_that_disagree_are_both_kept(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    await _fact(sg, owner, subject="penicillin", attribute="allergy", value="rash")
    await _fact(
        sg,
        owner,
        subject="penicillin",
        attribute="allergy",
        value="no reaction recorded",
        at=MONDAY + timedelta(minutes=5),
    )

    state = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=1))
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None

    # Two current facts about one substance is the thing a person needs to see. The one
    # that happened to be read last is not an answer, so both are here with their sources.
    said = clinical["allergies"]["penicillin"]
    assert sorted(one["value"] for one in said) == ["no reaction recorded", "rash"]
    assert all(one["fact_id"] for one in said)


async def test_an_open_admission_is_a_day_to_act_on(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    episode = await open_episode(
        sg,
        context=owner,
        kind=EpisodeKind.ADMISSION,
        label="in hospital, chest infection",
        now=MONDAY,
    )

    state = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=1))
    assert state.posture is Posture.ACT
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert clinical["open_episodes"][0]["id"] == str(episode.id)

    await close_episode(
        sg, context=owner, episode_id=episode.id, now=MONDAY + timedelta(days=4)
    )
    settled = await current_state(sg, context=owner, now=MONDAY + timedelta(days=4, hours=1))
    assert settled.trigger is StateTrigger.EPISODE_CHANGE
    assert settled.posture is Posture.STABLE


async def test_the_month_after_a_discharge_is_watched(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    await record_event(
        sg,
        context=owner,
        kind=EventKind.DISCHARGE,
        occurred_at=MONDAY,
        label="home from hospital",
        now=MONDAY,
    )

    inside = await current_state(sg, context=owner, now=MONDAY + timedelta(days=5))
    assert inside.posture is Posture.WATCH
    situational = inside.dimension(Dimension.SITUATIONAL)
    assert situational is not None
    assert situational["phase"] == Phase.AFTER_DISCHARGE.value

    outside = await current_state(sg, context=owner, now=MONDAY + timedelta(days=31))
    assert outside.posture is Posture.STABLE


async def test_the_week_before_a_visit_shows_in_the_situational_dimension(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    doctor = await add_provider(
        sg,
        context=owner,
        name="Dr Tan",
        kind=ProviderKind.DOCTOR,
        region=Region.SG,
        now=MONDAY,
    )
    visit = await book_appointment(
        sg,
        context=owner,
        provider_id=doctor.id,
        scheduled_at=MONDAY + timedelta(days=20),
        purpose="heart check",
        now=MONDAY,
    )

    far_off = await current_state(sg, context=owner, now=MONDAY + timedelta(days=1))
    situational = far_off.dimension(Dimension.SITUATIONAL)
    assert situational is not None
    assert situational["phase"] == Phase.STEADY.value
    assert situational["next_visit"]["id"] == str(visit.id)

    # The snapshot says when it stops describing today: the moment the visit is a week away.
    assert far_off.stale_after == MONDAY + timedelta(days=13)

    near = await current_state(sg, context=owner, now=MONDAY + timedelta(days=15))
    assert near.trigger is StateTrigger.TIME_PASSED
    near_situational = near.dimension(Dimension.SITUATIONAL)
    assert near_situational is not None
    assert near_situational["phase"] == Phase.BEFORE_VISIT.value


async def test_a_fact_that_stops_holding_makes_state_recompute(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    await _fact(
        sg,
        owner,
        subject="fasting",
        attribute="today",
        value=True,
        valid_to=MONDAY + timedelta(hours=6),
    )

    during = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=1))
    assert during.stale_after == MONDAY + timedelta(hours=6)
    situational = during.dimension(Dimension.SITUATIONAL)
    assert situational is not None
    assert situational["facts"]["fasting"]["today"]["value"] is True

    after = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=7))
    assert after.trigger is StateTrigger.TIME_PASSED
    ended = after.dimension(Dimension.SITUATIONAL)
    assert ended is not None
    assert ended["facts"] == {}


async def test_the_family_dimension_says_who_holds_what(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    await recompute(sg, context=owner, now=MONDAY)
    mei = await register_person(
        sg, region=Region.SG, display_name="Mei", phone_e164="+6591110012"
    )
    await grant_key(
        sg,
        context=owner,
        holder=mei,
        role=KeyRole.VIEWER,
        basis="owner_consent",
        now=MONDAY + timedelta(minutes=30),
    )

    state = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=1))
    assert state.trigger is StateTrigger.KEY_CHANGE
    family = state.dimension(Dimension.FAMILY)
    assert family is not None
    assert family["holding_now"] == 1
    holder = family["holders"][0]
    assert holder["person_id"] == str(mei.id)
    assert holder["role"] == KeyRole.VIEWER.value
    assert Scope.MEDICINES.value in holder["scopes"]


async def test_a_narrower_key_reads_a_narrower_state(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    await _fact(sg, owner, subject="heart_failure", attribute="control", value="watch")
    await current_state(sg, context=owner, now=MONDAY + timedelta(hours=1))

    mei = await register_person(
        sg, region=Region.SG, display_name="Mei", phone_e164="+6591110013"
    )
    await grant_key(
        sg, context=owner, holder=mei, role=KeyRole.CAREGIVER, basis="owner_consent", now=MONDAY
    )
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=mei.id, profile_id=owner.profile_id, now=MONDAY
    )

    state = await current_state(sg, context=held, now=MONDAY + timedelta(hours=2))

    # A caregiver holds no key to the family list and none to what he has said no to, so
    # those are named as withheld rather than quietly emptied — and she cannot recompute,
    # so she is told that what she is reading is behind the record.
    assert state.withheld == frozenset({Dimension.FAMILY, Dimension.PREFERENCE})
    assert state.dimension(Dimension.FAMILY) is None
    assert state.dimension(Dimension.PREFERENCE) is None
    assert state.dimension(Dimension.CLINICAL) is not None
    assert state.posture is Posture.WATCH
    assert state.stale is True

    # And the owner sees the reaching as well as the reads: one refused line per dimension
    # held back, saying which part was reached for and never what it held.
    trail = await read_audit(sg, context=owner, now=MONDAY + timedelta(hours=3))
    withheld = [
        entry
        for entry in trail
        if entry.outcome is Outcome.REFUSED and entry.target.startswith("state_snapshot.")
    ]
    assert {entry.target for entry in withheld} == {
        "state_snapshot.family",
        "state_snapshot.preference",
    }
    assert all(entry.actor_person_id == mei.id for entry in withheld)


async def test_a_key_missing_one_scope_writes_no_state_at_all(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    first = await recompute(sg, context=owner, now=MONDAY)

    mei = await register_person(
        sg, region=Region.SG, display_name="Mei", phone_e164="+6591110016"
    )
    await grant_key(
        sg, context=owner, holder=mei, role=KeyRole.CAREGIVER, basis="owner_consent", now=MONDAY
    )
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=mei.id, profile_id=owner.profile_id, now=MONDAY
    )

    # A caregiver reaches the record and the visits but not the family list. A snapshot
    # written from two of the three would become the profile's State with the third empty,
    # and an empty dimension cannot be told from a quiet one.
    with pytest.raises(OutOfScope):
        await recompute(sg, context=held, now=MONDAY + timedelta(hours=1))
    still = await latest_snapshot(sg, context=owner, now=MONDAY + timedelta(hours=2))
    assert still is not None and still.id == first.id


async def test_a_key_that_cannot_reach_the_record_reads_no_state_at_all(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    await current_state(sg, context=owner, now=MONDAY)

    helper = await register_person(
        sg, region=Region.SG, display_name="Auntie", phone_e164="+6591110014"
    )
    await grant_key(
        sg, context=owner, holder=helper, role=KeyRole.HELPER, basis="owner_consent", now=MONDAY
    )
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=helper.id, profile_id=owner.profile_id, now=MONDAY
    )

    with pytest.raises(OutOfScope):
        await current_state(sg, context=held, now=MONDAY + timedelta(hours=1))


async def test_a_fact_asserted_at_the_very_moment_of_a_state_is_not_lost(
    sg: AsyncSession,
) -> None:
    """The batch case: State computed at T, then a fact written at T in the same run."""
    owner = await _pa(sg)
    first = await recompute(sg, context=owner, now=MONDAY)
    await _fact(sg, owner, subject="blood_pressure", attribute="systolic", value=138, at=MONDAY)

    after = await current_state(sg, context=owner, now=MONDAY)
    assert after.id != first.id
    assert after.trigger is StateTrigger.NEW_FACT
    clinical = after.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert clinical["facts"]["blood_pressure"]["systolic"]["value"] == 138

    # And it settles: once folded in, the same fact does not make State recompute again.
    settled = await current_state(sg, context=owner, now=MONDAY)
    assert settled.id == after.id


async def test_a_read_may_only_order_by_its_own_columns(sg: AsyncSession) -> None:
    """The narrowing `audited_read` grew for State cannot be turned into a wider read."""
    owner = await _pa(sg)
    with pytest.raises(WidenedRead):
        await audited_read(
            sg,
            StateSnapshot,
            owner,
            Scope.RECORDS,
            order_by=(Fact.asserted_at.desc(),),
            limit=1,
            now=MONDAY,
        )


async def test_a_snapshot_is_superseded_never_edited(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    state = await recompute(sg, context=owner, now=MONDAY)

    snapshot = await sg.get(StateSnapshot, state.id)
    assert snapshot is not None
    snapshot.posture = Posture.ACT
    with pytest.raises(ImmutableState):
        await sg.flush()
    await sg.rollback()


async def test_a_fact_trigger_names_the_fact_that_caused_it(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    with pytest.raises(TriggerWithoutItsFact):
        await recompute(sg, context=owner, trigger=StateTrigger.NEW_FACT, now=MONDAY)


async def test_only_something_rendered_to_a_person_records_a_state(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    with pytest.raises(NotRenderable):
        await render_from_state(
            sg, Note, owner, Scope.NOTES, now=MONDAY, scope=Scope.NOTES, body="not a card"
        )


async def test_a_superseded_state_cannot_be_rendered_from(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    first = await recompute(sg, context=owner, now=MONDAY)
    await recompute(sg, context=owner, now=MONDAY + timedelta(hours=1))

    with pytest.raises(StaleState):
        await render_card(sg, owner, state=first, now=MONDAY + timedelta(hours=2))


async def test_the_history_says_why_the_app_said_what_it_said(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    await recompute(sg, context=owner, now=MONDAY)
    await _fact(
        sg,
        owner,
        subject="blood_pressure",
        attribute="systolic",
        value=138,
        at=MONDAY + timedelta(hours=1),
    )
    await current_state(sg, context=owner, now=MONDAY + timedelta(hours=2))

    history = await state_history(sg, context=owner, now=MONDAY + timedelta(hours=3))
    assert [one.sequence for one in history] == [2, 1]
    assert [one.trigger for one in history] == [StateTrigger.NEW_FACT, StateTrigger.FIRST]


async def test_state_is_the_profiles_own(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    ash = await register_person(
        sg, region=Region.SG, display_name="Ash", phone_e164="+6591110015"
    )
    other_profile = await create_own_profile(sg, region=Region.SG, owner=ash)
    other = await resolve_key_context(
        sg, region=Region.SG, person_id=ash.id, profile_id=other_profile.id
    )
    await _fact(sg, other, subject="heart_failure", attribute="control", value="act")

    state = await current_state(sg, context=owner, now=MONDAY + timedelta(hours=1))
    assert state.posture is Posture.STABLE
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert clinical["conditions"] == {}
