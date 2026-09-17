"""The three stores and the spine: what each holds, what it refuses, and who may reach it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.db import as_utc
from app.drafts import AppointmentDraft, Draft, FactDraft
from app.identity.models import Person
from app.identity.service import create_own_profile, register_person
from app.keys.confirm import confirm
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import NoSuchArtifact, NotADigest, record_event, store_artifact
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
    NotALabel,
    Provider,
    ProviderKind,
    SourceChannel,
)
from app.memory.semantic import (
    AlreadySuperseded,
    EmptyWindow,
    assert_fact,
    current_facts,
    supersede_fact,
)
from app.memory.spine import (
    NoSuchProvider,
    add_provider,
    book_appointment,
    upcoming_appointments,
)
from app.memory.working import (
    EpisodeAlreadyClosed,
    EpisodeAlreadyOpen,
    NoSuchEpisode,
    close_episode,
    open_episode,
    open_episodes,
)
from app.regions import OutOfRegion, Region
from tests.support import OPENING_CONSENT, agree_to_family_sharing, refused_unit

SEPT_3 = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
SEPT_10 = SEPT_3 + timedelta(days=7)
SHA = "b" * 64


async def _pa(session: AsyncSession, phone: str = "+6591110001") -> KeyContext:
    pa = await register_person(session, region=Region.SG, display_name="Pa", phone_e164=phone)
    profile = await create_own_profile(session, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


async def _yes(session: AsyncSession, context: KeyContext, draft: Draft) -> uuid.UUID:
    """The person asking says yes to exactly this, the way the surface writes it down."""
    return (await confirm(session, context, draft)).id


def _next(old: Fact, value: object, *, unit: str | None = None) -> FactDraft:
    """The draft `supersede_fact` will write for `old`: same statement, provenance carried."""
    return FactDraft(
        subject=old.subject,
        attribute=old.attribute,
        value=value,
        unit=unit if unit is not None else old.unit,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=old.artifact_id,
        event_id=old.event_id,
        episode_id=old.episode_id,
        supersedes_id=old.id,
    )


async def _photo(session: AsyncSession, context: KeyContext, when: datetime = SEPT_3) -> Artifact:
    return await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key="sg/profiles/pa/bp-book.jpg",
        content_type="image/jpeg",
        sha256=SHA,
        captured_at=when,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )


async def _systolic(
    session: AsyncSession,
    context: KeyContext,
    photo: Artifact,
    value: int,
    *,
    when: datetime = SEPT_3,
    valid_to: datetime | None = None,
) -> Fact:
    return await assert_fact(
        session,
        context=context,
        subject="blood_pressure",
        attribute="systolic",
        value=value,
        unit="mmHg",
        confidence=0.8,
        artifact_id=photo.id,
        valid_from=when,
        valid_to=valid_to,
    )


# --- episodic: the raw things that came in ----------------------------------------------


async def test_an_artefact_is_a_reference_to_bytes_kept_in_the_profiles_region(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    assert photo.profile_id == owner.profile_id
    await sg.refresh(photo)
    assert photo.storage_key == "sg/profiles/pa/bp-book.jpg"
    assert photo.region is Region.SG

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
    with pytest.raises(NotADigest):
        await store_artifact(
            sg,
            context=owner,
            kind=ArtifactKind.PDF,
            storage_key="sg/profiles/pa/discharge.pdf",
            content_type="application/pdf",
            sha256="not a digest",
            captured_at=SEPT_3,
            source_channel=SourceChannel.WHATSAPP,
            region=Region.SG,
        )


async def test_an_artefact_and_an_event_cannot_be_changed_once_stored(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    async with refused_unit(sg, ImmutableRow):
        photo.storage_key = "somewhere/else.jpg"
        await sg.flush()
    await sg.refresh(photo)
    assert photo.storage_key == "sg/profiles/pa/bp-book.jpg"

    reading = await record_event(
        sg, context=owner, kind=EventKind.READING, occurred_at=SEPT_3, artifact_id=photo.id
    )
    async with refused_unit(sg, ImmutableRow):
        reading.occurred_at = SEPT_10
        await sg.flush()
    await sg.refresh(reading)
    assert as_utc(reading.occurred_at) == SEPT_3


async def test_an_event_carries_a_short_label_and_never_the_raw_content(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    with pytest.raises(NotALabel):
        await record_event(
            sg,
            context=owner,
            kind=EventKind.MESSAGE,
            occurred_at=SEPT_3,
            label="Pa says his chest felt tight after climbing the stairs this morning and "
            "he took the water pill late, around ten, because the helper was out",
        )
    with pytest.raises(NotALabel):
        await record_event(
            sg, context=owner, kind=EventKind.MESSAGE, occurred_at=SEPT_3, label="line\nbreak"
        )
    message = await record_event(
        sg,
        context=owner,
        kind=EventKind.MESSAGE,
        occurred_at=SEPT_3,
        label="message from the helper",
        artifact_id=photo.id,
    )
    assert message.label == "message from the helper"
    assert message.artifact_id == photo.id


async def test_an_event_cannot_point_at_another_profiles_artefact(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    neighbour = await _pa(sg, phone="+6591110002")
    theirs = await _photo(sg, neighbour)
    with pytest.raises(NoSuchArtifact):
        await record_event(
            sg, context=owner, kind=EventKind.READING, occurred_at=SEPT_3, artifact_id=theirs.id
        )


# --- semantic: facts with provenance, immutable with supersession -------------------------


async def test_supersession_keeps_the_history_and_current_facts_returns_only_the_live_one(
    sg: AsyncSession,
    clock: FrozenClock,
) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    extracted = await _systolic(sg, owner, photo, 138)

    clock.set(SEPT_10)
    confirmed = await supersede_fact(
        sg,
        context=owner,
        fact_id=extracted.id,
        value=136,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmation_id=await _yes(sg, owner, _next(extracted, 136)),
    )

    # The old row stays and says when it stopped being current; the new one names it.
    assert extracted.superseded_at is not None
    assert confirmed.supersedes_id == extracted.id
    assert confirmed.superseded_at is None
    # Provenance is carried over when the reading is the same: it still links to the photo.
    assert confirmed.artifact_id == photo.id
    assert confirmed.unit == "mmHg"

    live = await current_facts(sg, context=owner, subject="blood_pressure", at=SEPT_10)
    assert [(fact.id, fact.value) for fact in live] == [(confirmed.id, 136)]

    with pytest.raises(AlreadySuperseded):
        await supersede_fact(sg, context=owner, fact_id=extracted.id, value=140, confidence=0.5)


async def test_a_fact_cannot_be_edited_only_superseded(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    fact = await _systolic(sg, owner, photo, 138)
    async with refused_unit(sg, ImmutableRow):
        fact.value = 120
        await sg.flush()
    await sg.refresh(fact)
    assert fact.value == 138


async def test_current_facts_honours_the_validity_window(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    last_week = await _systolic(sg, owner, photo, 150, when=SEPT_3, valid_to=SEPT_10)
    this_week = await _systolic(sg, owner, photo, 138, when=SEPT_10)

    now_ish = SEPT_10 + timedelta(hours=1)
    assert [f.id for f in await current_facts(sg, context=owner, at=now_ish)] == [this_week.id]
    # Looking back, the old one was the fact of the day and the new one did not exist yet.
    back_then = SEPT_3 + timedelta(days=1)
    assert [f.id for f in await current_facts(sg, context=owner, at=back_then)] == [last_week.id]

    with pytest.raises(EmptyWindow):
        await _systolic(sg, owner, photo, 138, when=SEPT_10, valid_to=SEPT_3)


async def test_current_facts_narrows_by_subject_and_attribute(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    await _systolic(sg, owner, photo, 138)
    await assert_fact(
        sg,
        context=owner,
        subject="weight",
        attribute="kg",
        value=71.5,
        unit="kg",
        confidence=0.9,
        artifact_id=photo.id,
    )
    weight = await current_facts(sg, context=owner, subject="weight", at=SEPT_10)
    assert [fact.value for fact in weight] == [71.5]
    both = await current_facts(sg, context=owner, at=SEPT_10)
    assert {fact.subject for fact in both} == {"blood_pressure", "weight"}


# --- working: the current episode --------------------------------------------------------


async def test_one_open_episode_of_a_kind_at_a_time(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    infection = await open_episode(
        sg, context=owner, kind=EpisodeKind.ILLNESS, label="chest infection", opened_at=SEPT_3
    )
    assert infection.closed_at is None
    with pytest.raises(EpisodeAlreadyOpen):
        await open_episode(sg, context=owner, kind=EpisodeKind.ILLNESS, label="a cold")
    # A different kind can be open at the same time.
    trip = await open_episode(sg, context=owner, kind=EpisodeKind.TRAVEL, label="Penang")
    assert {e.id for e in await open_episodes(sg, context=owner)} == {infection.id, trip.id}

    closed = await close_episode(sg, context=owner, episode_id=infection.id, closed_at=SEPT_10)
    assert closed.closed_at == SEPT_10
    with pytest.raises(EpisodeAlreadyClosed):
        await close_episode(sg, context=owner, episode_id=infection.id)
    with pytest.raises(NoSuchEpisode):
        await close_episode(sg, context=owner, episode_id=uuid.uuid4())

    again = await open_episode(sg, context=owner, kind=EpisodeKind.ILLNESS, label="a cold")
    assert again.id != infection.id


async def test_events_and_facts_hang_off_the_open_episode(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    infection = await open_episode(
        sg, context=owner, kind=EpisodeKind.ILLNESS, label="chest infection", opened_at=SEPT_3
    )
    visit = await record_event(
        sg,
        context=owner,
        kind=EventKind.VISIT,
        occurred_at=SEPT_3,
        source_channel=SourceChannel.APP,
        label="saw Dr Tan",
        episode_id=infection.id,
    )
    fact = await assert_fact(
        sg,
        context=owner,
        subject="temperature",
        attribute="celsius",
        value=38.2,
        unit="C",
        confidence=0.9,
        event_id=visit.id,
        episode_id=infection.id,
    )
    assert visit.episode_id == infection.id and fact.episode_id == infection.id

    await close_episode(sg, context=owner, episode_id=infection.id, closed_at=SEPT_10)
    with pytest.raises(NoSuchEpisode):
        await record_event(
            sg,
            context=owner,
            kind=EventKind.VISIT,
            occurred_at=SEPT_10,
            source_channel=SourceChannel.APP,
            label="saw Dr Tan again",
            episode_id=infection.id,
        )


# --- the spine: providers and appointments ------------------------------------------------


async def test_appointments_hang_off_a_provider_and_come_back_soonest_first(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    dr_tan = await add_provider(
        sg,
        context=owner,
        name="Dr Tan, Bedok Polyclinic",
        kind=ProviderKind.CLINIC,
        region=Region.SG,
        phone_e164="+6562220000",
        address="11 Bedok North Street 1",
    )
    later = await book_appointment(
        sg,
        context=owner,
        confirmation_id=await _yes(
            sg,
            owner,
            AppointmentDraft(
                provider_id=dr_tan.id,
                scheduled_at=SEPT_10 + timedelta(days=14),
                purpose="blood pressure review",
            ),
        ),
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10 + timedelta(days=14),
        purpose="blood pressure review",
    )
    sooner = await book_appointment(
        sg,
        context=owner,
        confirmation_id=await _yes(
            sg,
            owner,
            AppointmentDraft(
                provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="chest infection"
            ),
        ),
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10,
        purpose="chest infection",
    )
    cancelled = await book_appointment(
        sg,
        context=owner,
        confirmation_id=await _yes(
            sg,
            owner,
            AppointmentDraft(
                provider_id=dr_tan.id, scheduled_at=SEPT_10 + timedelta(days=1), purpose="x-ray"
            ),
        ),
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10 + timedelta(days=1),
        purpose="x-ray",
        status=AppointmentStatus.CANCELLED,
    )
    past = await book_appointment(
        sg,
        context=owner,
        confirmation_id=await _yes(
            sg,
            owner,
            AppointmentDraft(
                provider_id=dr_tan.id,
                scheduled_at=SEPT_3 - timedelta(days=30),
                purpose="last check-up",
            ),
        ),
        provider_id=dr_tan.id,
        scheduled_at=SEPT_3 - timedelta(days=30),
        purpose="last check-up",
        status=AppointmentStatus.ATTENDED,
    )

    upcoming = await upcoming_appointments(sg, context=owner, at=SEPT_3)
    assert [a.id for a in upcoming] == [sooner.id, later.id]
    assert {cancelled.id, past.id}.isdisjoint({a.id for a in upcoming})
    assert sooner.provider_id == dr_tan.id and sooner.status is AppointmentStatus.PLANNED


async def test_an_appointment_needs_a_provider_on_this_profile_and_may_join_an_episode(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    neighbour = await _pa(sg, phone="+6591110002")
    their_doctor = await add_provider(
        sg, context=neighbour, name="Dr Lim", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    with pytest.raises(NoSuchProvider):
        await book_appointment(
            sg,
            context=owner,
            confirmation_id=await _yes(
                sg,
                owner,
                AppointmentDraft(
                    provider_id=their_doctor.id, scheduled_at=SEPT_10, purpose="review"
                ),
            ),
            provider_id=their_doctor.id,
            scheduled_at=SEPT_10,
            purpose="review",
        )

    dr_tan = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    infection = await open_episode(
        sg, context=owner, kind=EpisodeKind.ILLNESS, label="chest infection"
    )
    review = await book_appointment(
        sg,
        context=owner,
        confirmation_id=await _yes(
            sg,
            owner,
            AppointmentDraft(
                provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="chest infection review"
            ),
        ),
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10,
        purpose="chest infection review",
        episode_id=infection.id,
    )
    assert review.episode_id == infection.id
    with pytest.raises(NotALabel):
        await book_appointment(
            sg,
            context=owner,
            provider_id=dr_tan.id,
            scheduled_at=SEPT_10,
            purpose="x" * 81,
            confirmation_id=await _yes(
                sg,
                owner,
                AppointmentDraft(provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="x" * 81),
            ),
        )


# --- every row is the profile's, and every touch is written down ----------------------------


async def test_every_row_is_pinned_to_the_profile_and_every_write_is_in_the_trail(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    reading = await record_event(
        sg, context=owner, kind=EventKind.READING, occurred_at=SEPT_3, artifact_id=photo.id
    )
    fact = await _systolic(sg, owner, photo, 138)
    episode = await open_episode(sg, context=owner, kind=EpisodeKind.ILLNESS, label="cold")
    dr_tan = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    visit = await book_appointment(
        sg,
        context=owner,
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10,
        purpose="review",
        confirmation_id=await _yes(
            sg,
            owner,
            AppointmentDraft(provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="review"),
        ),
    )
    await current_facts(sg, context=owner)

    rows = (photo, reading, fact, episode, dr_tan, visit)
    assert {row.profile_id for row in rows} == {owner.profile_id}

    trail = await read_audit(sg, context=owner)
    written = {(entry.target, entry.target_id) for entry in trail if entry.action is Action.WRITE}
    for row in rows:
        assert (row.__tablename__, row.id) in written
    assert {e.scope for e in trail if e.target in {"artifact", "episode"}} == {Scope.RECORDS}
    # An event is read through the record's door; a reading taken is written under the
    # readings' part, and the row keeps the scope it was written under (row scope).
    events = {(e.action, e.scope) for e in trail if e.target == "event"}
    assert (Action.WRITE, Scope.READINGS) in events
    assert events <= {(Action.READ, Scope.RECORDS), (Action.WRITE, Scope.READINGS)}
    # A fact is written under its subject's scope — a blood-pressure reading is a reading —
    # and the whole record, read with no subject named, is read one scope at a time, each
    # under its own, for the scopes the key holds: the owner holds all three.
    assert {e.scope for e in trail if e.target == "fact" and e.action is Action.WRITE} == {
        Scope.READINGS
    }
    assert {e.scope for e in trail if e.target == "fact" and e.action is Action.READ} == {
        Scope.RECORDS,
        Scope.READINGS,
        Scope.MEDICINES,
    }
    assert {e.scope for e in trail if e.target in {"provider", "appointment"}} == {Scope.VISITS}
    assert any(e.action is Action.READ and e.target == "fact" for e in trail)


async def test_a_caregiver_key_without_records_cannot_read_facts_and_the_refusal_is_logged(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    await _systolic(sg, owner, photo, 138)
    dr_tan = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    await book_appointment(
        sg,
        context=owner,
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10,
        purpose="review",
        confirmation_id=await _yes(
            sg,
            owner,
            AppointmentDraft(provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="review"),
        ),
    )

    daughter: Person = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )
    await agree_to_family_sharing(sg, owner, daughter, role=KeyRole.CAREGIVER)
    await grant_key(
        sg,
        context=owner,
        holder=daughter,
        role=KeyRole.CAREGIVER,
        scopes=[Scope.MEDICINES, Scope.VISITS],
    )
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=daughter.id, profile_id=owner.profile_id
    )

    with pytest.raises(OutOfScope):
        await current_facts(sg, context=held, at=SEPT_10)
    with pytest.raises(OutOfScope):
        await _photo(sg, held)

    # She holds the visits, so the spine is hers to read.
    assert len(await upcoming_appointments(sg, context=held, at=SEPT_3)) == 1

    # The door on each service checks the scope first, so her reach for the photo is refused
    # at the artefact, before the consent gate (E00-02) is even asked.
    refused = [e for e in await read_audit(sg, context=owner) if e.outcome is Outcome.REFUSED]
    assert {(e.actor_person_id, e.action, e.scope, e.target) for e in refused} == {
        (daughter.id, Action.READ, Scope.RECORDS, "fact"),
        (daughter.id, Action.WRITE, Scope.RECORDS, "artifact"),
    }
    assert all(e.refused_because == "OutOfScope" for e in refused)


def test_the_memory_tables_all_carry_the_profile() -> None:
    for table in (Artifact, Event, Fact, Episode, Provider, Appointment):
        assert "profile_id" in table.__table__.columns
