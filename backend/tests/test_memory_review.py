"""The safety review of E00-03 (#95), one test per required item.

Refusals raised while the profile is known are in the trail, not only scope refusals. A fact
names a predecessor only on its own profile, and a machine never quietly overwrites what a
person confirmed. An event comes from somewhere. Provenance is tied to the profile at the
table as well as at the service. An episode and an appointment each take one change, under
audit. An artefact's region is checked when it is read, not only when it is stored. And an
appointment carries who confirmed it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Outcome
from app.audit.trail import read_audit
from app.db import as_utc
from app.identity.models import Person, Profile
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import (
    EventFromNowhere,
    NoSuchArtifact,
    NoSuchEvent,
    NotTheArtefactsChannel,
    record_event,
    require_artifact,
    require_event,
    store_artifact,
)
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    Artifact,
    ArtifactKind,
    ConfidenceState,
    Episode,
    EpisodeKind,
    Event,
    EventKind,
    Fact,
    ImmutableRow,
    ProviderKind,
    SourceChannel,
)
from app.memory.semantic import (
    AlreadySuperseded,
    ConfirmedFactStands,
    NoSuchFact,
    NoSuchProvenance,
    NotAPersonsWord,
    NotTheFactInDispute,
    NotTheSameFact,
    assert_fact,
    current_facts,
    open_disputes,
    supersede_fact,
)
from app.memory.spine import (
    STATUS_GOES_TO,
    NobodyConfirmed,
    NoSuchAppointment,
    NotThatStatusChange,
    add_provider,
    book_appointment,
    change_appointment_status,
)
from app.memory.working import close_episode, open_episode
from app.regions import OutOfRegion, Region
from tests.support import refused_unit

SEPT_3 = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
SEPT_10 = SEPT_3 + timedelta(days=7)
SHA = "c" * 64


async def _pa(session: AsyncSession, phone: str = "+6591110001") -> KeyContext:
    pa = await register_person(session, region=Region.SG, display_name="Pa", phone_e164=phone)
    profile = await create_own_profile(session, region=Region.SG, owner=pa)
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


async def _photo(session: AsyncSession, context: KeyContext) -> Artifact:
    return await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key="sg/profiles/pa/bp-book.jpg",
        content_type="image/jpeg",
        sha256=SHA,
        captured_at=SEPT_3,
        source_channel=SourceChannel.APP,
        region=Region.SG,
        now=SEPT_3,
    )


async def _systolic(
    session: AsyncSession,
    context: KeyContext,
    photo: Artifact,
    value: int,
    *,
    state: ConfidenceState = ConfidenceState.EXTRACTED,
    when: datetime = SEPT_3,
) -> Fact:
    return await assert_fact(
        session,
        context=context,
        subject="blood_pressure",
        attribute="systolic",
        value=value,
        unit="mmHg",
        confidence=0.8,
        confidence_state=state,
        artifact_id=photo.id,
        valid_from=when,
        now=when,
    )


async def _dose(
    session: AsyncSession,
    context: KeyContext,
    photo: Artifact,
    value: int,
    *,
    state: ConfidenceState = ConfidenceState.EXTRACTED,
    confirmed_by: uuid.UUID | None = None,
    when: datetime = SEPT_3,
) -> Fact:
    return await assert_fact(
        session,
        context=context,
        subject="medication",
        attribute="dose",
        value=value,
        unit="mg",
        confidence=0.8 if state is ConfidenceState.EXTRACTED else 1.0,
        confidence_state=state,
        confirmed_by_person_id=confirmed_by,
        artifact_id=photo.id,
        valid_from=when,
        now=when,
    )


def _refusals(trail: list[AuditEntry] | tuple[AuditEntry, ...]) -> set[tuple[Action, str, str]]:
    return {
        (entry.action, entry.target, entry.refused_because or "")
        for entry in trail
        if entry.outcome is Outcome.REFUSED
    }


# --- 1. a refusal raised while the profile is known is in the trail ------------------------


async def test_an_artefact_held_out_of_region_is_refused_and_the_refusal_is_in_the_trail(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    with pytest.raises(OutOfRegion):
        await store_artifact(
            sg,
            context=owner,
            kind=ArtifactKind.PDF,
            storage_key="my/profiles/pa/discharge.pdf",
            content_type="application/pdf",
            sha256=SHA,
            captured_at=SEPT_3,
            source_channel=SourceChannel.WHATSAPP,
            region=Region.MY,
        )
    trail = list(await read_audit(sg, context=owner))
    assert _refusals(trail) == {(Action.WRITE, "artifact", "OutOfRegion")}
    refused = next(entry for entry in trail if entry.outcome is Outcome.REFUSED)
    assert refused.actor_person_id == owner.person_id
    assert refused.scope is Scope.RECORDS
    # The name of the refusal, never what was held back: no region, no key, no path.
    assert refused.refused_because == "OutOfRegion"


async def test_resolving_a_key_on_a_profile_pinned_elsewhere_is_refused_and_written_down(
    sg: AsyncSession,
) -> None:
    pa = await register_person(sg, region=Region.SG, display_name="Pa", phone_e164="+6591110001")
    # A row that is in this database but pinned to the other region: the thing guarded against.
    astray = Profile(region=Region.MY, display_name="Pa", owner_person_id=pa.id)
    sg.add(astray)
    await sg.flush()

    with pytest.raises(OutOfRegion):
        await resolve_key_context(sg, region=Region.SG, person_id=pa.id, profile_id=astray.id)

    # Nobody can resolve a context on this profile here, so the trail is read directly.
    lines = (await sg.scalars(select(AuditEntry).where(AuditEntry.profile_id == astray.id))).all()
    assert [(e.outcome, e.refused_because, e.actor_person_id, e.action) for e in lines] == [
        (Outcome.REFUSED, "OutOfRegion", pa.id, Action.READ)
    ]
    assert lines[0].key_id is None and lines[0].actor_role is None


# --- 2. a predecessor is validated under the key context ----------------------------------


async def test_a_fact_cannot_name_a_predecessor_that_is_not_a_current_fact_on_this_profile(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    neighbour = await _pa(sg, phone="+6591110002")
    mine = await _photo(sg, owner)
    theirs = await _systolic(sg, neighbour, await _photo(sg, neighbour), 150)

    for stray in (theirs.id, uuid.uuid4()):
        with pytest.raises(NoSuchFact):
            await assert_fact(
                sg,
                context=owner,
                subject="blood_pressure",
                attribute="systolic",
                value=138,
                confidence=0.8,
                artifact_id=mine.id,
                supersedes_id=stray,
            )

    # Naming a predecessor is superseding it: the old row closes, and it says the same thing.
    first = await _systolic(sg, owner, mine, 140)
    second = await assert_fact(
        sg,
        context=owner,
        subject="blood_pressure",
        attribute="systolic",
        value=138,
        confidence=0.8,
        artifact_id=mine.id,
        supersedes_id=first.id,
        now=SEPT_10,
    )
    assert second.supersedes_id == first.id and first.superseded_at is not None
    assert [f.id for f in await current_facts(sg, context=owner, now=SEPT_10)] == [second.id]
    with pytest.raises(AlreadySuperseded):
        await assert_fact(
            sg,
            context=owner,
            subject="blood_pressure",
            attribute="systolic",
            value=139,
            confidence=0.8,
            artifact_id=mine.id,
            supersedes_id=first.id,
        )
    with pytest.raises(NotTheSameFact):
        await assert_fact(
            sg,
            context=owner,
            subject="weight",
            attribute="kg",
            value=70,
            confidence=0.8,
            artifact_id=mine.id,
            supersedes_id=second.id,
        )

    # And the table refuses the cross-profile predecessor too.
    sg.add(
        Fact(
            profile_id=owner.profile_id,
            subject="blood_pressure",
            attribute="systolic",
            value=138,
            confidence=0.8,
            confidence_state=ConfidenceState.EXTRACTED,
            artifact_id=mine.id,
            valid_from=SEPT_3,
            supersedes_id=theirs.id,
        )
    )
    with pytest.raises(IntegrityError):
        await sg.flush()
    await sg.rollback()


# --- 3. a machine does not overwrite what a person confirmed -------------------------------


async def test_an_extraction_does_not_supersede_what_a_person_confirmed(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    extracted = await _dose(sg, owner, photo, 138)
    confirmed = await supersede_fact(
        sg,
        context=owner,
        fact_id=extracted.id,
        value=136,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmed_by_person_id=owner.person_id,
    )
    assert confirmed.confirmed_by_person_id == owner.person_id

    # The machine's value cannot quietly replace the person's.
    with pytest.raises(ConfirmedFactStands):
        await supersede_fact(sg, context=owner, fact_id=confirmed.id, value=150, confidence=0.9)
    assert confirmed.superseded_at is None
    assert _refusals(list(await read_audit(sg, context=owner))) == {
        (Action.WRITE, "fact", "ConfirmedFactStands")
    }

    # The same rule holds on the public door.
    with pytest.raises(ConfirmedFactStands):
        await assert_fact(
            sg,
            context=owner,
            subject="medication",
            attribute="dose",
            value=142,
            confidence=0.9,
            artifact_id=photo.id,
            supersedes_id=confirmed.id,
        )


async def test_a_confirmed_or_disputed_state_names_the_person_who_said_so(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    neighbour = await _pa(sg, phone="+6591110002")
    abroad = await register_person(
        sg, region=Region.MY, display_name="Cousin", phone_e164="+60121110003"
    )
    photo = await _photo(sg, owner)
    extracted = await _dose(sg, owner, photo, 138)

    # A label with nobody behind it is not a person's word.
    for state in (ConfidenceState.CONFIRMED_BY_PERSON, ConfidenceState.DISPUTED):
        with pytest.raises(NobodyConfirmed):
            await supersede_fact(
                sg,
                context=owner,
                fact_id=extracted.id,
                value=136,
                confidence=1.0,
                confidence_state=state,
            )
        with pytest.raises(NobodyConfirmed):
            await _dose(sg, owner, photo, 136, state=state)
    # Nor is a person from another household, another region, or nowhere.
    for who in (neighbour.person_id, abroad.id, uuid.uuid4()):
        with pytest.raises(NobodyConfirmed):
            await _dose(
                sg,
                owner,
                photo,
                136,
                state=ConfidenceState.CONFIRMED_BY_PERSON,
                confirmed_by=who,
            )
    # And an extraction does not name one: it is the machine's, not a person's.
    with pytest.raises(NotAPersonsWord):
        await _dose(sg, owner, photo, 136, confirmed_by=owner.person_id)
    assert extracted.superseded_at is None
    assert {r[2] for r in _refusals(list(await read_audit(sg, context=owner)))} == {
        "NobodyConfirmed",
        "NotAPersonsWord",
    }

    # The people who may: the owner, the person asking, and a key holder on this profile.
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110004"
    )
    await grant_key(
        sg, context=owner, holder=daughter, role=KeyRole.CAREGIVER, basis="owner_consent"
    )
    by_owner = await _dose(
        sg,
        owner,
        photo,
        136,
        state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmed_by=owner.person_id,
    )
    by_daughter = await supersede_fact(
        sg,
        context=owner,
        fact_id=by_owner.id,
        value=136,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmed_by_person_id=daughter.id,
    )
    assert by_daughter.confirmed_by_person_id == daughter.id


async def test_a_dispute_keeps_the_persons_number_current_until_a_person_settles_it(
    sg: AsyncSession,
) -> None:
    """medication.dose: confirmed 136, extracted 150 disputed, current is 136, confirmed 150."""
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    confirmed = await _dose(
        sg,
        owner,
        photo,
        136,
        state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmed_by=owner.person_id,
    )

    disputed = await supersede_fact(
        sg,
        context=owner,
        fact_id=confirmed.id,
        value=150,
        confidence=0.9,
        confidence_state=ConfidenceState.DISPUTED,
        confirmed_by_person_id=owner.person_id,
        now=SEPT_10,
    )
    # The dispute names the fact it disputes and is kept, but it closes nothing and is not
    # current: the person's 136 stands while the dispute is open.
    assert disputed.supersedes_id == confirmed.id and disputed.superseded_at is None
    assert confirmed.superseded_at is None
    current = await current_facts(sg, context=owner, subject="medication", now=SEPT_10)
    assert [(f.id, f.value) for f in current] == [(confirmed.id, 136)]
    assert [d.id for d in await open_disputes(sg, context=owner, fact_id=confirmed.id)] == [
        disputed.id
    ]

    # While it is open, no extraction settles it, and the dispute itself is not a predecessor.
    with pytest.raises(ConfirmedFactStands):
        await supersede_fact(sg, context=owner, fact_id=confirmed.id, value=150, confidence=0.9)
    with pytest.raises(NotTheFactInDispute):
        await supersede_fact(
            sg,
            context=owner,
            fact_id=disputed.id,
            value=150,
            confidence=1.0,
            confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
            confirmed_by_person_id=owner.person_id,
        )

    # A person settles it: the new number is current, and the old fact and its dispute close.
    settled = await supersede_fact(
        sg,
        context=owner,
        fact_id=confirmed.id,
        value=150,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmed_by_person_id=owner.person_id,
        now=SEPT_10 + timedelta(days=1),
    )
    later = SEPT_10 + timedelta(days=2)
    assert [(f.id, f.value) for f in await current_facts(sg, context=owner, now=later)] == [
        (settled.id, 150)
    ]
    assert confirmed.superseded_at is not None and disputed.superseded_at is not None
    assert await open_disputes(sg, context=owner, fact_id=confirmed.id) == []


# --- 4. an event comes from somewhere ------------------------------------------------------


async def test_an_event_names_its_artefact_or_says_where_it_came_in_from(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    for source, label in ((None, None), (SourceChannel.APP, None), (None, "saw Dr Tan")):
        with pytest.raises(EventFromNowhere):
            await record_event(
                sg,
                context=owner,
                kind=EventKind.VISIT,
                occurred_at=SEPT_3,
                source_channel=source,
                label=label,
            )

    visit = await record_event(
        sg,
        context=owner,
        kind=EventKind.VISIT,
        occurred_at=SEPT_3,
        source_channel=SourceChannel.APP,
        label="saw Dr Tan",
    )
    assert visit.source_channel is SourceChannel.APP

    # An event read from an artefact came in the way the artefact did.
    photo = await _photo(sg, owner)
    reading = await record_event(
        sg, context=owner, kind=EventKind.READING, occurred_at=SEPT_3, artifact_id=photo.id
    )
    assert reading.source_channel is photo.source_channel
    with pytest.raises(NotTheArtefactsChannel):
        await record_event(
            sg,
            context=owner,
            kind=EventKind.READING,
            occurred_at=SEPT_3,
            artifact_id=photo.id,
            source_channel=SourceChannel.CLINIC,
        )

    # Each of the four refusals is in the trail, in name only.
    assert _refusals(list(await read_audit(sg, context=owner))) == {
        (Action.WRITE, "event", "EventFromNowhere"),
        (Action.WRITE, "event", "NotTheArtefactsChannel"),
    }

    # The table refuses an event with no source at all.
    sg.add(Event(profile_id=owner.profile_id, kind=EventKind.VISIT, occurred_at=SEPT_3))
    with pytest.raises(IntegrityError):
        await sg.flush()
    await sg.rollback()


# --- 5. provenance is the profile's at the table -------------------------------------------


async def test_a_fact_citing_another_profiles_artefact_is_refused_at_the_service_and_table(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    neighbour = await _pa(sg, phone="+6591110002")
    theirs = await _photo(sg, neighbour)
    their_reading = await record_event(
        sg, context=neighbour, kind=EventKind.READING, occurred_at=SEPT_3, artifact_id=theirs.id
    )
    their_episode = await open_episode(
        sg, context=neighbour, kind=EpisodeKind.ILLNESS, label="a cold"
    )

    with pytest.raises(NoSuchProvenance):
        await assert_fact(
            sg,
            context=owner,
            subject="blood_pressure",
            attribute="systolic",
            value=138,
            confidence=0.8,
            artifact_id=theirs.id,
        )
    with pytest.raises(NoSuchProvenance):
        await assert_fact(
            sg,
            context=owner,
            subject="blood_pressure",
            attribute="systolic",
            value=138,
            confidence=0.8,
            event_id=their_reading.id,
        )

    def stray(**provenance: uuid.UUID) -> Fact:
        return Fact(
            profile_id=owner.profile_id,
            subject="blood_pressure",
            attribute="systolic",
            value=138,
            confidence=0.8,
            confidence_state=ConfidenceState.EXTRACTED,
            valid_from=SEPT_3,
            **provenance,
        )

    mine = await _photo(sg, owner)
    for row in (
        stray(artifact_id=theirs.id),
        stray(event_id=their_reading.id),
        stray(artifact_id=mine.id, episode_id=their_episode.id),
    ):
        sg.add(row)
        with pytest.raises(IntegrityError):
            await sg.flush()
        await sg.rollback()

    # The same tie holds on an event and on an appointment.
    owner = await _pa(sg)
    neighbour = await _pa(sg, phone="+6591110002")
    theirs = await _photo(sg, neighbour)
    sg.add(
        Event(
            profile_id=owner.profile_id,
            kind=EventKind.READING,
            occurred_at=SEPT_3,
            source_channel=SourceChannel.APP,
            artifact_id=theirs.id,
        )
    )
    with pytest.raises(IntegrityError):
        await sg.flush()
    await sg.rollback()

    owner = await _pa(sg)
    neighbour = await _pa(sg, phone="+6591110002")
    their_doctor = await add_provider(
        sg, context=neighbour, name="Dr Lim", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    sg.add(
        Appointment(
            profile_id=owner.profile_id,
            provider_id=their_doctor.id,
            scheduled_at=SEPT_10,
            status=AppointmentStatus.PLANNED,
            purpose="see Dr Lim",
            confirmed_by_person_id=owner.person_id,
        )
    )
    with pytest.raises(IntegrityError):
        await sg.flush()
    await sg.rollback()


# --- 6. an episode and an appointment take one change each, under audit --------------------


async def test_an_episode_only_closes_and_an_appointment_only_changes_status(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    episode = await open_episode(sg, context=owner, kind=EpisodeKind.ILLNESS, label="a cold")
    async with refused_unit(sg, ImmutableRow):
        episode.label = "the flu"
        await sg.flush()
    await sg.refresh(episode)
    assert episode.label == "a cold"

    dr_tan = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    visit = await book_appointment(
        sg,
        context=owner,
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10,
        purpose="see Dr Tan again",
        confirmed_by_person_id=owner.person_id,
        now=SEPT_3,
    )
    neighbour = await _pa(sg, phone="+6591110002")
    async with refused_unit(sg, ImmutableRow):
        # A refused reach earlier in the same unit of work is not lost with it.
        with pytest.raises(NoSuchAppointment):
            await change_appointment_status(
                sg,
                context=neighbour,
                appointment_id=visit.id,
                status=AppointmentStatus.CANCELLED,
                confirmed_by_person_id=neighbour.person_id,
            )
        visit.scheduled_at = SEPT_10 + timedelta(days=1)
        await sg.flush()
    await sg.refresh(visit)
    assert as_utc(visit.scheduled_at) == SEPT_10
    assert _refusals(list(await read_audit(sg, context=neighbour))) == {
        (Action.WRITE, "appointment", "NoSuchAppointment")
    }

    # Status goes one way, each step on a person's confirm, naming who gave it.
    before = len(await read_audit(sg, context=owner))
    confirmed = await change_appointment_status(
        sg,
        context=owner,
        appointment_id=visit.id,
        status=AppointmentStatus.CONFIRMED,
        confirmed_by_person_id=owner.person_id,
        now=SEPT_10,
    )
    assert confirmed.status is AppointmentStatus.CONFIRMED
    assert confirmed.status_changed_by_person_id == owner.person_id
    assert confirmed.confirmed_by_person_id == owner.person_id
    trail = await read_audit(sg, context=owner)
    # One read to find it, one write to change it, then the owner's own read of the trail.
    assert len(trail) == before + 3
    assert (Action.WRITE, "appointment", visit.id) in {
        (e.action, e.target, e.target_id) for e in trail if as_utc(e.at) == SEPT_10
    }
    with pytest.raises(NobodyConfirmed):
        await change_appointment_status(
            sg,
            context=owner,
            appointment_id=visit.id,
            status=AppointmentStatus.CANCELLED,
            confirmed_by_person_id=neighbour.person_id,
        )
    with pytest.raises(NotThatStatusChange):
        await change_appointment_status(
            sg,
            context=owner,
            appointment_id=visit.id,
            status=AppointmentStatus.PLANNED,
            confirmed_by_person_id=owner.person_id,
        )
    cancelled = await change_appointment_status(
        sg,
        context=owner,
        appointment_id=visit.id,
        status=AppointmentStatus.CANCELLED,
        confirmed_by_person_id=owner.person_id,
    )
    assert cancelled.status is AppointmentStatus.CANCELLED
    # Nothing leaves cancelled, attended or not attended: no way back to planned.
    for status in AppointmentStatus:
        with pytest.raises(NotThatStatusChange):
            await change_appointment_status(
                sg,
                context=owner,
                appointment_id=visit.id,
                status=status,
                confirmed_by_person_id=owner.person_id,
            )
    assert all(AppointmentStatus.PLANNED not in goes_to for goes_to in STATUS_GOES_TO.values())


async def test_what_was_done_is_not_undone_by_writing_none_over_it(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    old = await _systolic(sg, owner, photo, 138)
    await supersede_fact(sg, context=owner, fact_id=old.id, value=136, confidence=0.9)
    async with refused_unit(sg, ImmutableRow):
        old.superseded_at = None
        await sg.flush()
    await sg.refresh(old)
    assert old.superseded_at is not None

    episode = await open_episode(sg, context=owner, kind=EpisodeKind.ILLNESS, label="a cold")
    await close_episode(sg, context=owner, episode_id=episode.id, closed_at=SEPT_10)
    async with refused_unit(sg, ImmutableRow):
        episode.closed_at = None
        await sg.flush()
    await sg.refresh(episode)
    assert episode.closed_at is not None


async def test_deleting_a_profile_takes_every_row_of_it_with_it(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    reading = await record_event(
        sg, context=owner, kind=EventKind.READING, occurred_at=SEPT_3, artifact_id=photo.id
    )
    first = await _systolic(sg, owner, photo, 138)
    await supersede_fact(sg, context=owner, fact_id=first.id, value=136, confidence=0.9)
    episode = await open_episode(sg, context=owner, kind=EpisodeKind.ILLNESS, label="a cold")
    dr_tan = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    await book_appointment(
        sg,
        context=owner,
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10,
        purpose="see Dr Tan again",
        confirmed_by_person_id=owner.person_id,
        episode_id=episode.id,
    )
    assert reading.artifact_id == photo.id

    # The profile goes (PDPA), and the ties cascade past every composite key.
    await sg.execute(delete(Profile).where(Profile.id == owner.profile_id))
    for table in (Artifact, Event, Fact, Episode, Appointment, AuditEntry):
        rows = (await sg.scalars(select(table).where(table.profile_id == owner.profile_id))).all()
        assert rows == [], table.__tablename__
    assert await sg.get(Person, owner.person_id) is not None


# --- 7. an artefact's region is checked on read ---------------------------------------------


async def test_an_artefact_that_is_held_in_another_region_is_refused_on_read(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    # A row that entered out of band, naming bytes held across the causeway.
    astray = Artifact(
        profile_id=owner.profile_id,
        kind=ArtifactKind.PDF,
        storage_key="my/profiles/pa/discharge.pdf",
        content_type="application/pdf",
        sha256=SHA,
        captured_at=SEPT_3,
        source_channel=SourceChannel.CLINIC,
        region=Region.MY,
    )
    sg.add(astray)
    await sg.flush()

    # The region is in the query itself, so the row is never read: to this deployment it is
    # not there, and the refusal says no more than that, but it is written down.
    with pytest.raises(NoSuchArtifact):
        await require_artifact(sg, context=owner, artifact_id=astray.id)
    trail = list(await read_audit(sg, context=owner))
    assert _refusals(trail) == {(Action.READ, "artifact", "NoSuchArtifact")}
    assert all(e.rows == 0 for e in trail if e.target == "artifact")
    # Nothing downstream can cite it either.
    with pytest.raises(NoSuchArtifact):
        await record_event(
            sg, context=owner, kind=EventKind.DISCHARGE, occurred_at=SEPT_3, artifact_id=astray.id
        )
    with pytest.raises(NoSuchProvenance):
        await assert_fact(
            sg,
            context=owner,
            subject="weight",
            attribute="kg",
            value=70,
            confidence=0.8,
            artifact_id=astray.id,
        )

    # Rows that entered out of band citing it are not served either, by any reader.
    stray_event = Event(
        profile_id=owner.profile_id,
        kind=EventKind.READING,
        occurred_at=SEPT_3,
        source_channel=SourceChannel.CLINIC,
        artifact_id=astray.id,
    )
    stray_fact = Fact(
        profile_id=owner.profile_id,
        subject="weight",
        attribute="kg",
        value=70,
        confidence=0.8,
        confidence_state=ConfidenceState.EXTRACTED,
        artifact_id=astray.id,
        valid_from=SEPT_3,
    )
    sg.add_all([stray_event, stray_fact])
    await sg.flush()
    with pytest.raises(NoSuchEvent):
        await require_event(sg, context=owner, event_id=stray_event.id)
    assert await current_facts(sg, context=owner, subject="weight") == []
    with pytest.raises(NoSuchFact):
        await supersede_fact(sg, context=owner, fact_id=stray_fact.id, value=71, confidence=0.8)
    # ...while the same rows citing an artefact held here are.
    photo = await _photo(sg, owner)
    here = await _systolic(sg, owner, photo, 138)
    assert [f.id for f in await current_facts(sg, context=owner, now=SEPT_10)] == [here.id]


# --- 8. an appointment carries who confirmed it --------------------------------------------


async def test_an_appointment_records_the_person_who_confirmed_it(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    dr_tan = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    visit = await book_appointment(
        sg,
        context=owner,
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10,
        purpose="see Dr Tan again",
        confirmed_by_person_id=owner.person_id,
    )
    assert visit.confirmed_by_person_id == owner.person_id

    # Not a person from another household, nor from the other region, nor from nowhere.
    neighbour = await _pa(sg, phone="+6591110002")
    abroad = await register_person(
        sg, region=Region.MY, display_name="Cousin", phone_e164="+60121110003"
    )
    for who in (neighbour.person_id, abroad.id, uuid.uuid4()):
        with pytest.raises(NobodyConfirmed):
            await book_appointment(
                sg,
                context=owner,
                provider_id=dr_tan.id,
                scheduled_at=SEPT_10,
                purpose="see Dr Tan again",
                confirmed_by_person_id=who,
            )
    assert _refusals(list(await read_audit(sg, context=owner))) == {
        (Action.WRITE, "appointment", "NobodyConfirmed")
    }
    # A key holder on this profile may confirm.
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110004"
    )
    await grant_key(
        sg, context=owner, holder=daughter, role=KeyRole.CAREGIVER, basis="owner_consent"
    )
    by_daughter = await book_appointment(
        sg,
        context=owner,
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10,
        purpose="see Dr Tan again",
        confirmed_by_person_id=daughter.id,
    )
    assert by_daughter.confirmed_by_person_id == daughter.id
    # The confirm is not optional at the signature either.
    with pytest.raises(TypeError):
        await book_appointment(  # type: ignore[call-arg]
            sg, context=owner, provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="see Dr Tan"
        )
