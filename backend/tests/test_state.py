"""What the six dimensions hold, what moves the posture, and what a narrower key reads.

The line the boundary sits on is in here twice: a reading on its own never moves the posture,
because nothing in State judges a number; a clinician's word recorded as a fact does, because
State is repeating what the record already says.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import WidenedRead, audited_read
from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.drafts import AppointmentDraft
from app.identity.service import create_own_profile, register_person
from app.keys.confirm import confirm
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
from app.memory.semantic import NoSuchFact, assert_fact
from app.memory.spine import add_provider, book_appointment
from app.memory.working import close_episode, open_episode
from app.regions import Region
from app.state.dimensions import Phase, dimension_of
from app.state.models import Dimension, Posture, StateSnapshot, StateTrigger, worse_of
from app.state.service import (
    FactWithoutItsTrigger,
    NoState,
    NotRenderable,
    StaleState,
    TriggerWithoutItsFact,
    current_state,
    latest_snapshot,
    recompute_state,
    render_from_state,
    state_history,
)
from tests.support import OPENING_CONSENT, Note, agree_to_family_sharing, render_card

MONDAY = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
SHA = "c" * 64


async def _pa(session: AsyncSession, phone: str = "+6591110011") -> KeyContext:
    pa = await register_person(session, region=Region.SG, display_name="Pa", phone_e164=phone)
    profile = await create_own_profile(session, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
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
    valid_to: datetime | None = None,
) -> Fact:
    photo = await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"sg/profiles/pa/{subject}-{attribute}-{uuid.uuid4()}.jpg",
        content_type="image/jpeg",
        sha256=SHA,
        captured_at=MONDAY,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )
    return await assert_fact(
        session,
        context=context,
        subject=subject,
        attribute=attribute,
        value=value,
        confidence=0.9,
        artifact_id=photo.id,
        valid_to=valid_to,
    )


async def _let_in(
    session: AsyncSession,
    owner: KeyContext,
    *,
    phone: str,
    role: KeyRole,
    scopes: set[Scope] | None = None,
) -> KeyContext:
    """The owner lets someone in and cuts them a key; the context they then hold."""
    holder = await register_person(session, region=Region.SG, display_name="Mei", phone_e164=phone)
    await agree_to_family_sharing(session, owner, holder)
    await grant_key(session, context=owner, holder=holder, role=role, scopes=scopes)
    return await resolve_key_context(
        session, region=Region.SG, person_id=holder.id, profile_id=owner.profile_id
    )


def test_a_fact_goes_to_its_dimension_and_health_is_the_default() -> None:
    assert dimension_of("mobility") is Dimension.FUNCTIONAL
    assert dimension_of("language") is Dimension.COGNITIVE
    assert dimension_of("goal") is Dimension.PREFERENCE
    # "What Nura uses" (RE-05): every switch is a `signals` fact, folded the same way.
    assert dimension_of("signals") is Dimension.PREFERENCE
    assert dimension_of("fasting") is Dimension.SITUATIONAL
    assert dimension_of("blood_pressure") is Dimension.CLINICAL
    assert dimension_of("something_nobody_has_classified") is Dimension.CLINICAL


def test_state_never_talks_itself_down() -> None:
    assert worse_of(Posture.STABLE, Posture.WATCH) is Posture.WATCH
    assert worse_of(Posture.ACT, Posture.WATCH) is Posture.ACT


async def test_a_reading_on_its_own_does_not_move_the_posture(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await _fact(sg, owner, subject="blood_pressure", attribute="systolic", value=176)

    state = await current_state(sg, context=owner)

    # 176 is a number State holds, not a number State reads. Judging it belongs to reasoning
    # and to safety, with a clinician's framing; nothing here decides it is high.
    assert state.posture is Posture.STABLE
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert clinical["facts"]["blood_pressure"]["systolic"]["value"] == 176
    assert clinical["conditions"] == {}
    assert clinical["because"] == []


async def test_the_posture_follows_the_word_already_in_the_record(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    said = await _fact(sg, owner, subject="heart_failure", attribute="control", value="watch")

    state = await current_state(sg, context=owner)
    assert state.posture is Posture.WATCH
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None

    # The condition keeps the fact it came from, so the card that shows it can cite the page,
    # and the dimension's posture says which fact raised it.
    assert [one["value"] for one in clinical["conditions"]["heart_failure"]] == ["watch"]
    assert clinical["conditions"]["heart_failure"][0]["artifact_id"] is not None
    assert clinical["posture"] == Posture.WATCH.value
    assert clinical["because"] == [
        {"posture": "watch", "subject": "heart_failure", "fact_id": str(said.id)}
    ]
    functional = state.dimension(Dimension.FUNCTIONAL)
    assert functional is not None and functional["posture"] == Posture.STABLE.value


async def test_a_word_about_an_ability_raises_its_own_dimension(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """The same route in every dimension: a `control` word in the record, never a number."""
    clock.set(MONDAY)
    owner = await _pa(sg)
    said = await _fact(sg, owner, subject="mobility", attribute="control", value="act")

    state = await current_state(sg, context=owner)
    functional = state.dimension(Dimension.FUNCTIONAL)
    clinical = state.dimension(Dimension.CLINICAL)
    assert functional is not None and clinical is not None
    assert functional["posture"] == Posture.ACT.value
    assert functional["because"] == [
        {"posture": "act", "subject": "mobility", "fact_id": str(said.id)}
    ]
    assert clinical["posture"] == Posture.STABLE.value
    assert clinical["conditions"] == {}
    assert state.posture is Posture.ACT


async def test_a_control_word_state_cannot_read_is_kept_and_is_not_a_settled_day(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await _fact(sg, owner, subject="heart_failure", attribute="control", value="poorly controlled")

    state = await current_state(sg, context=owner)
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None

    # The clinician's own words are kept and named, never dropped for not matching a list.
    assert clinical["conditions"]["heart_failure"][0]["value"] == "poorly controlled"
    assert clinical["control_not_read"][0]["subject"] == "heart_failure"
    assert state.posture is Posture.WATCH


async def test_two_facts_that_disagree_are_both_kept(sg: AsyncSession, clock: FrozenClock) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await _fact(sg, owner, subject="penicillin", attribute="allergy", value="rash")
    clock.step(timedelta(minutes=5))
    await _fact(sg, owner, subject="penicillin", attribute="allergy", value="no reaction recorded")

    state = await current_state(sg, context=owner)
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None

    # Two current facts about one substance is the thing a person needs to see. The one
    # that happened to be read last is not an answer, so both are here with their sources.
    said = clinical["allergies"]["penicillin"]
    assert sorted(one["value"] for one in said) == ["no reaction recorded", "rash"]
    assert all(one["fact_id"] for one in said)


async def test_an_open_admission_is_a_day_to_act_on(sg: AsyncSession, clock: FrozenClock) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    episode = await open_episode(
        sg, context=owner, kind=EpisodeKind.ADMISSION, label="in hospital, chest infection"
    )

    state = await current_state(sg, context=owner)
    assert state.trigger is StateTrigger.FIRST
    assert state.posture is Posture.ACT
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert clinical["open_episodes"] == [
        {"id": str(episode.id), "kind": "admission", "since": MONDAY.isoformat()}
    ]
    assert "label" not in clinical["open_episodes"][0]

    clock.step(timedelta(days=4))
    await close_episode(sg, context=owner, episode_id=episode.id)
    settled = await current_state(sg, context=owner)
    assert settled.trigger is StateTrigger.EPISODE_CHANGE
    assert settled.posture is Posture.STABLE


async def test_the_month_after_a_discharge_is_watched(sg: AsyncSession, clock: FrozenClock) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await record_event(
        sg,
        context=owner,
        kind=EventKind.DISCHARGE,
        occurred_at=MONDAY,
        label="home from hospital",
        source_channel=SourceChannel.APP,
    )

    clock.step(timedelta(days=5))
    inside = await current_state(sg, context=owner)
    assert inside.posture is Posture.WATCH
    situational = inside.dimension(Dimension.SITUATIONAL)
    assert situational is not None
    assert situational["phase"] == Phase.AFTER_DISCHARGE.value
    assert situational["posture"] == Posture.WATCH.value
    assert inside.stale_after == MONDAY + timedelta(days=30)

    clock.set(MONDAY + timedelta(days=31))
    outside = await current_state(sg, context=owner)
    assert outside.trigger is StateTrigger.NEW_EVENT  # the discharge left the window
    assert outside.posture is Posture.STABLE


async def test_the_week_before_a_visit_shows_in_the_situational_dimension(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    doctor = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    draft = AppointmentDraft(
        provider_id=doctor.id, scheduled_at=MONDAY + timedelta(days=20), purpose="heart check"
    )
    visit = await book_appointment(
        sg,
        context=owner,
        provider_id=draft.provider_id,
        scheduled_at=draft.scheduled_at,
        purpose=draft.purpose,
        confirmation_id=(await confirm(sg, owner, draft)).id,
    )

    clock.step(timedelta(days=1))
    far_off = await current_state(sg, context=owner)
    situational = far_off.dimension(Dimension.SITUATIONAL)
    assert situational is not None
    assert situational["phase"] == Phase.STEADY.value
    assert situational["next_visit"] == {
        "id": str(visit.id),
        "provider_id": str(doctor.id),
        "at": (MONDAY + timedelta(days=20)).isoformat(),
    }
    # The snapshot says when it stops describing today: the moment the visit is a week away.
    assert far_off.stale_after == MONDAY + timedelta(days=13)

    clock.set(MONDAY + timedelta(days=15))
    near = await current_state(sg, context=owner)
    assert near.trigger is StateTrigger.TIME_PASSED
    near_situational = near.dimension(Dimension.SITUATIONAL)
    assert near_situational is not None
    assert near_situational["phase"] == Phase.BEFORE_VISIT.value


async def test_a_fact_that_stops_holding_makes_state_recompute(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await _fact(
        sg,
        owner,
        subject="fasting",
        attribute="today",
        value=True,
        valid_to=MONDAY + timedelta(hours=6),
    )

    clock.step(timedelta(hours=1))
    during = await current_state(sg, context=owner)
    assert during.stale_after == MONDAY + timedelta(hours=6)
    situational = during.dimension(Dimension.SITUATIONAL)
    assert situational is not None
    assert situational["facts"]["fasting"]["today"]["value"] is True

    clock.set(MONDAY + timedelta(hours=7))
    after = await current_state(sg, context=owner)
    assert after.trigger is StateTrigger.TIME_PASSED
    ended = after.dimension(Dimension.SITUATIONAL)
    assert ended is not None
    assert ended["facts"] == {}


async def test_the_family_dimension_says_who_holds_what(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await recompute_state(sg, context=owner)
    clock.step(timedelta(minutes=30))
    held = await _let_in(sg, owner, phone="+6591110012", role=KeyRole.VIEWER)

    clock.step(timedelta(minutes=30))
    state = await current_state(sg, context=owner)
    assert state.trigger is StateTrigger.KEY_CHANGE
    family = state.dimension(Dimension.FAMILY)
    assert family is not None
    assert family["holding_now"] == 1
    holder = family["holders"][0]
    assert holder["person_id"] == str(held.person_id)
    assert holder["role"] == KeyRole.VIEWER.value
    assert Scope.MEDICINES.value in holder["scopes"]


async def test_a_narrower_key_reads_a_narrower_state(sg: AsyncSession, clock: FrozenClock) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await _fact(sg, owner, subject="heart_failure", attribute="control", value="watch")
    await _fact(sg, owner, subject="blood_pressure", attribute="systolic", value=138)
    medicine = await _fact(sg, owner, subject="medication", attribute="dose", value=5)
    await current_state(sg, context=owner)
    held = await _let_in(
        sg,
        owner,
        phone="+6591110013",
        role=KeyRole.CAREGIVER,
        scopes={Scope.RECORDS, Scope.READINGS},
    )

    clock.step(timedelta(hours=1))
    state = await current_state(sg, context=held)

    # A caregiver key to the record and the readings holds no key to the visits, the family
    # list or what he has said no to, so those dimensions are named as withheld rather than
    # quietly emptied. Within the clinical dimension the medicine is a medicines fact, and
    # this key does not cover medicines: it is taken out, and the scope is named.
    assert state.withheld == frozenset(
        {Dimension.FAMILY, Dimension.PREFERENCE, Dimension.SITUATIONAL}
    )
    assert state.withheld_scopes == frozenset(
        {Scope.FAMILY, Scope.NOTES, Scope.VISITS, Scope.MEDICINES}
    )
    assert state.dimension(Dimension.FAMILY) is None
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert set(clinical["facts"]) == {"heart_failure", "blood_pressure"}
    assert str(medicine.id) not in clinical["fact_ids"]
    assert clinical["conditions"]["heart_failure"][0]["value"] == "watch"
    assert state.posture is Posture.WATCH
    # She cannot recompute, so she is told that what she reads was not checked against the
    # record — and nothing may be rendered from it.
    assert state.stale is None
    with pytest.raises(StaleState):
        await render_card(sg, held, state=state)

    # The owner's trail has her allowed reads of the snapshot and no refusal: a narrowed
    # answer is not a refused one.
    trail = await read_audit(sg, context=owner, actor_person_id=held.person_id)
    assert trail
    assert {(e.action, e.scope, e.target, e.outcome) for e in trail} == {
        (Action.READ, Scope.RECORDS, StateSnapshot.__tablename__, Outcome.ALLOWED)
    }


async def test_a_key_missing_one_scope_writes_no_state_at_all(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    first = await recompute_state(sg, context=owner)
    held = await _let_in(sg, owner, phone="+6591110016", role=KeyRole.CAREGIVER)

    # A caregiver reaches the record and the visits but not the family list. A snapshot
    # written from two of the three would become the profile's State with the third empty,
    # and an empty dimension cannot be told from a quiet one.
    clock.step(timedelta(hours=1))
    with pytest.raises(OutOfScope) as refused:
        await recompute_state(sg, context=held)
    assert refused.value.scope is Scope.FAMILY
    still = await latest_snapshot(sg, context=owner)
    assert still is not None and still.id == first.id
    # One line for it, under the scope that was missing.
    refusals = [
        e
        for e in await read_audit(sg, context=owner, actor_person_id=held.person_id)
        if e.outcome is Outcome.REFUSED
    ]
    assert [(e.action, e.scope, e.refused_because) for e in refusals] == [
        (Action.WRITE, Scope.FAMILY, "OutOfScope")
    ]


async def test_a_fact_written_by_a_key_that_cannot_recompute_is_caught_up_by_one_that_can(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    first = await current_state(sg, context=owner)
    held = await _let_in(sg, owner, phone="+6591110017", role=KeyRole.CAREGIVER)

    # The caregiver's fact lands; the recompute it would have caused is refused at the door
    # and written down, and State stays where it was.
    clock.step(timedelta(hours=1))
    fact = await _fact(sg, held, subject="blood_pressure", attribute="systolic", value=138)
    still = await latest_snapshot(sg, context=owner)
    assert still is not None and still.id == first.id

    # The owner's next read finds the record has moved past the snapshot and catches it up,
    # naming the fact.
    after = await current_state(sg, context=owner)
    assert after.id != first.id
    assert after.trigger is StateTrigger.NEW_FACT
    assert after.trigger_fact_id == fact.id


async def test_a_key_that_cannot_reach_the_record_reads_no_state_at_all(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await current_state(sg, context=owner)
    held = await _let_in(sg, owner, phone="+6591110014", role=KeyRole.HELPER)

    with pytest.raises(OutOfScope):
        await current_state(sg, context=held)
    with pytest.raises(OutOfScope):
        await state_history(sg, context=held)


async def test_a_narrow_key_before_any_state_is_told_there_is_none(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    held = await _let_in(sg, owner, phone="+6591110018", role=KeyRole.CLINIC)
    with pytest.raises(NoState):
        await current_state(sg, context=held)


async def test_a_read_may_only_order_by_its_own_columns(sg: AsyncSession) -> None:
    """The narrowing `audited_read` grew for State cannot be turned into a wider read."""
    owner = await _pa(sg)
    with pytest.raises(WidenedRead):
        await audited_read(
            sg, StateSnapshot, owner, Scope.RECORDS, order_by=(Fact.asserted_at.desc(),), limit=1
        )


async def test_a_fact_trigger_names_its_fact_and_only_a_fact_trigger_does(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    with pytest.raises(TriggerWithoutItsFact):
        await recompute_state(sg, context=owner, trigger=StateTrigger.NEW_FACT)
    with pytest.raises(FactWithoutItsTrigger):
        await recompute_state(sg, context=owner, trigger=StateTrigger.ASKED, fact_id=uuid.uuid4())
    with pytest.raises(NoSuchFact):
        await recompute_state(
            sg, context=owner, trigger=StateTrigger.NEW_FACT, fact_id=uuid.uuid4()
        )
    assert await latest_snapshot(sg, context=owner) is None


async def test_only_something_rendered_to_a_person_records_a_state(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    with pytest.raises(NotRenderable):
        await render_from_state(sg, Note, owner, Scope.NOTES, scope=Scope.NOTES, body="not a card")


async def test_a_superseded_state_cannot_be_rendered_from(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    first = await recompute_state(sg, context=owner)
    clock.step(timedelta(hours=1))
    await recompute_state(sg, context=owner)

    with pytest.raises(StaleState):
        await render_card(sg, owner, state=first)


async def test_the_history_says_why_the_app_said_what_it_said(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    await recompute_state(sg, context=owner)
    clock.step(timedelta(hours=1))
    await _fact(sg, owner, subject="blood_pressure", attribute="systolic", value=138)

    history = await state_history(sg, context=owner)
    assert [one.sequence for one in history] == [2, 1]
    assert [one.trigger for one in history] == [StateTrigger.NEW_FACT, StateTrigger.FIRST]
    assert history[0].supersedes_id == history[1].id


async def test_state_is_the_profiles_own(sg: AsyncSession, clock: FrozenClock) -> None:
    clock.set(MONDAY)
    owner = await _pa(sg)
    other = await _pa(sg, phone="+6591110015")
    await _fact(sg, other, subject="heart_failure", attribute="control", value="act")

    state = await current_state(sg, context=owner)
    assert state.posture is Posture.STABLE
    clinical = state.dimension(Dimension.CLINICAL)
    assert clinical is not None
    assert clinical["conditions"] == {}
    assert clinical["fact_ids"] == []
