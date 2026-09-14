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
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Outcome
from app.audit.trail import read_audit
from app.db import as_utc
from app.identity.models import Profile
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, resolve_key_context
from app.keys.scopes import Scope
from app.memory.episodic import (
    EventFromNowhere,
    NotTheArtefactsChannel,
    record_event,
    require_artifact,
    store_artifact,
)
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    Artifact,
    ArtifactKind,
    ConfidenceState,
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
    NotTheSameFact,
    assert_fact,
    current_facts,
    supersede_fact,
)
from app.memory.spine import (
    NobodyConfirmed,
    NoSuchAppointment,
    add_provider,
    book_appointment,
    change_appointment_status,
)
from app.memory.working import open_episode
from app.regions import OutOfRegion, Region

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
    extracted = await _systolic(sg, owner, photo, 138)
    confirmed = await supersede_fact(
        sg,
        context=owner,
        fact_id=extracted.id,
        value=136,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
    )

    # The machine's value cannot quietly replace the person's.
    with pytest.raises(ConfirmedFactStands):
        await supersede_fact(sg, context=owner, fact_id=confirmed.id, value=150, confidence=0.9)
    assert confirmed.superseded_at is None
    assert _refusals(list(await read_audit(sg, context=owner))) == {
        (Action.WRITE, "fact", "ConfirmedFactStands")
    }

    # It can say, explicitly, that the two disagree.
    disputed = await supersede_fact(
        sg,
        context=owner,
        fact_id=confirmed.id,
        value=150,
        confidence=0.9,
        confidence_state=ConfidenceState.DISPUTED,
    )
    assert disputed.confidence_state is ConfidenceState.DISPUTED
    # A disagreement is not settled by another extraction either; only a person settles it.
    with pytest.raises(ConfirmedFactStands):
        await supersede_fact(sg, context=owner, fact_id=disputed.id, value=140, confidence=0.9)
    settled = await supersede_fact(
        sg,
        context=owner,
        fact_id=disputed.id,
        value=140,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
    )
    assert [f.id for f in await current_facts(sg, context=owner)] == [settled.id]

    # The same rule holds on the public door.
    with pytest.raises(ConfirmedFactStands):
        await assert_fact(
            sg,
            context=owner,
            subject="blood_pressure",
            attribute="systolic",
            value=142,
            confidence=0.9,
            artifact_id=photo.id,
            supersedes_id=settled.id,
        )


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
    episode.label = "the flu"
    with pytest.raises(ImmutableRow):
        await sg.flush()
    await sg.rollback()

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
    visit.scheduled_at = SEPT_10 + timedelta(days=1)
    with pytest.raises(ImmutableRow):
        await sg.flush()
    await sg.rollback()

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
        now=SEPT_3,
    )
    before = len(await read_audit(sg, context=owner))
    changed = await change_appointment_status(
        sg,
        context=owner,
        appointment_id=visit.id,
        status=AppointmentStatus.ATTENDED,
        now=SEPT_10,
    )
    assert changed.id == visit.id and changed.status is AppointmentStatus.ATTENDED
    trail = await read_audit(sg, context=owner)
    # One read to find it, one write to change it, then the owner's own read of the trail.
    assert len(trail) == before + 3
    assert (Action.WRITE, "appointment", visit.id) in {
        (e.action, e.target, e.target_id) for e in trail if as_utc(e.at) == SEPT_10
    }

    neighbour = await _pa(sg, phone="+6591110002")
    with pytest.raises(NoSuchAppointment):
        await change_appointment_status(
            sg, context=neighbour, appointment_id=visit.id, status=AppointmentStatus.CANCELLED
        )


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

    with pytest.raises(OutOfRegion):
        await require_artifact(sg, context=owner, artifact_id=astray.id)
    assert _refusals(list(await read_audit(sg, context=owner))) == {
        (Action.READ, "artifact", "OutOfRegion")
    }
    # Nothing downstream can cite it either.
    with pytest.raises(OutOfRegion):
        await record_event(
            sg, context=owner, kind=EventKind.DISCHARGE, occurred_at=SEPT_3, artifact_id=astray.id
        )
    with pytest.raises(OutOfRegion):
        await assert_fact(
            sg,
            context=owner,
            subject="weight",
            attribute="kg",
            value=70,
            confidence=0.8,
            artifact_id=astray.id,
        )


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

    with pytest.raises(NobodyConfirmed):
        await book_appointment(
            sg,
            context=owner,
            provider_id=dr_tan.id,
            scheduled_at=SEPT_10,
            purpose="see Dr Tan again",
            confirmed_by_person_id=uuid.uuid4(),
        )
    assert _refusals(list(await read_audit(sg, context=owner))) == {
        (Action.WRITE, "appointment", "NobodyConfirmed")
    }
    # The confirm is not optional at the signature either.
    with pytest.raises(TypeError):
        await book_appointment(  # type: ignore[call-arg]
            sg, context=owner, provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="see Dr Tan"
        )
