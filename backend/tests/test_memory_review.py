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
from app.clock import FrozenClock
from app.consent.models import Consent
from app.db import as_utc
from app.drafts import AppointmentDraft, Draft, FactDraft, StatusChange
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.identity.service import create_own_profile, register_person
from app.keys.confirm import (
    AlreadySpent,
    Confirmation,
    ConfirmationExpired,
    NotAConfirmerHere,
    NotWhatWasConfirmed,
    confirm,
)
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.grants import grant_key, revoke_key
from app.keys.scopes import KeyRole, Scope
from app.memory import semantic
from app.memory.episodic import (
    CameInAnotherWay,
    NoSuchArtifact,
    NoSuchEvent,
    SourceNotNamed,
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
    NoSuchAppointment,
    NotThatStatusChange,
    add_provider,
    book_appointment,
    change_appointment_status,
)
from app.memory.working import close_episode, open_episode
from app.regions import OutOfRegion, Region
from tests.support import OPENING_CONSENT, agree_to_family_sharing, refused_unit

SEPT_3 = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
SEPT_10 = SEPT_3 + timedelta(days=7)
SHA = "c" * 64


async def _pa(session: AsyncSession, phone: str = "+6591110001") -> KeyContext:
    pa = await register_person(session, region=Region.SG, display_name="Pa", phone_e164=phone)
    profile = await create_own_profile(session, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
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
    )


async def _yes(session: AsyncSession, context: KeyContext, draft: Draft) -> uuid.UUID:
    """The person asking says yes to exactly this, the way the surface writes it down."""
    return (await confirm(session, context, draft)).id


def _dose_draft(photo: Artifact, value: object, state: ConfidenceState) -> FactDraft:
    return FactDraft(
        subject="medication",
        attribute="dose",
        value=value,
        unit="mg",
        confidence=0.8 if state is ConfidenceState.EXTRACTED else 1.0,
        confidence_state=state,
        artifact_id=photo.id,
        event_id=None,
        episode_id=None,
        supersedes_id=None,
    )


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


async def _dose(
    session: AsyncSession,
    context: KeyContext,
    photo: Artifact,
    value: int,
    *,
    state: ConfidenceState = ConfidenceState.EXTRACTED,
    confirmation_id: uuid.UUID | None = None,
    yes: bool = False,
    when: datetime = SEPT_3,
) -> Fact:
    if yes:
        confirmation_id = await _yes(session, context, _dose_draft(photo, value, state))
    return await assert_fact(
        session,
        context=context,
        subject="medication",
        attribute="dose",
        value=value,
        unit="mg",
        confidence=0.8 if state is ConfidenceState.EXTRACTED else 1.0,
        confidence_state=state,
        confirmation_id=confirmation_id,
        artifact_id=photo.id,
        valid_from=when,
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


async def test_resolving_a_key_on_a_profile_pinned_elsewhere_is_refused_and_leaves_no_line(
    sg: AsyncSession,
) -> None:
    pa = await register_person(sg, region=Region.SG, display_name="Pa", phone_e164="+6591110001")
    # A row that is in this database but pinned to the other region: the thing guarded against.
    astray = Profile(region=Region.MY, display_name="Pa", owner_person_id=pa.id)
    sg.add(astray)
    await sg.flush()

    with pytest.raises(OutOfRegion):
        await resolve_key_context(sg, region=Region.SG, person_id=pa.id, profile_id=astray.id)

    # The owner is told the real reason; nothing about another region's profile is written
    # into this region's trail. The channel logs the reach by a handle.
    lines = (await sg.scalars(select(AuditEntry).where(AuditEntry.profile_id == astray.id))).all()
    assert lines == []


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
    )
    assert second.supersedes_id == first.id and first.superseded_at is not None
    assert [f.id for f in await current_facts(sg, context=owner, at=SEPT_10)] == [second.id]
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
        confirmation_id=await _yes(sg, owner, _next(extracted, 136)),
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


async def test_a_confirmed_or_disputed_state_is_a_persons_yes_used_once(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    extracted = await _dose(sg, owner, photo, 138)
    confirmed_136 = _dose_draft(photo, 136, ConfidenceState.CONFIRMED_BY_PERSON)

    # A label with no yes behind it is not a person's word; an extraction has no yes at all.
    for state in (ConfidenceState.CONFIRMED_BY_PERSON, ConfidenceState.DISPUTED):
        with pytest.raises(NotAConfirmerHere):
            await _dose(sg, owner, photo, 136, state=state)
    with pytest.raises(NotAPersonsWord):
        await _dose(sg, owner, photo, 136, confirmation_id=await _yes(sg, owner, confirmed_136))

    # A yes is for one thing: another act, another fact, another profile, nothing at all.
    neighbour = await _pa(sg, phone="+6591110002")
    dr_tan = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    for wrong in (
        await _yes(
            sg,
            owner,
            AppointmentDraft(provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="a visit"),
        ),
        await _yes(sg, owner, _next(extracted, 136)),
        await _yes(sg, neighbour, confirmed_136),
        uuid.uuid4(),
    ):
        with pytest.raises(NotAConfirmerHere):
            await _dose(
                sg,
                owner,
                photo,
                136,
                state=ConfidenceState.CONFIRMED_BY_PERSON,
                confirmation_id=wrong,
            )
    # A yes binds to what was shown: the same act with a different number is refused.
    with pytest.raises(NotWhatWasConfirmed):
        await _dose(
            sg,
            owner,
            photo,
            140,
            state=ConfidenceState.CONFIRMED_BY_PERSON,
            confirmation_id=await _yes(sg, owner, confirmed_136),
        )

    # A yes is used once, and only while it is fresh.
    once = await _yes(sg, owner, confirmed_136)
    by_owner = await _dose(
        sg, owner, photo, 136, state=ConfidenceState.CONFIRMED_BY_PERSON, confirmation_id=once
    )
    assert by_owner.confirmed_by_person_id == owner.person_id
    with pytest.raises(AlreadySpent):
        await _dose(
            sg, owner, photo, 136, state=ConfidenceState.CONFIRMED_BY_PERSON, confirmation_id=once
        )
    stale = await _yes(sg, owner, _next(by_owner, 140))
    clock.step(timedelta(minutes=11))
    with pytest.raises(ConfirmationExpired):
        await supersede_fact(
            sg,
            context=owner,
            fact_id=by_owner.id,
            value=140,
            confidence=1.0,
            confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
            confirmation_id=stale,
        )
    assert extracted.superseded_at is None
    assert {r[2] for r in _refusals(list(await read_audit(sg, context=owner)))} == {
        "NotAConfirmerHere",
        "NotAPersonsWord",
        "NotWhatWasConfirmed",
        "AlreadySpent",
        "ConfirmationExpired",
    }
    # And no yes is readable from the trail: the lines about it carry no id.
    assert all(
        e.target_id is None
        for e in await read_audit(sg, context=owner)
        if e.target == "confirmation"
    )

    # A caregiver cannot say yes as the patient: a confirm names its creator and nobody else,
    # and only the person who said yes may act on it.
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110004"
    )
    await agree_to_family_sharing(
        sg, owner, daughter, scopes=[Scope.MEDICINES, Scope.RECORDS], role=KeyRole.CAREGIVER
    )
    await grant_key(
        sg,
        context=owner,
        holder=daughter,
        role=KeyRole.CAREGIVER,
        scopes=[Scope.MEDICINES, Scope.RECORDS],
    )
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=daughter.id, profile_id=owner.profile_id
    )
    hers = await confirm(sg, held, _next(by_owner, 136))
    assert hers.person_id == daughter.id
    by_daughter = await supersede_fact(
        sg,
        context=held,
        fact_id=by_owner.id,
        value=136,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmation_id=hers.id,
    )
    assert by_daughter.confirmed_by_person_id == daughter.id
    # The patient's yes is his to act on; her request cannot spend it.
    his = await _yes(sg, owner, _next(by_daughter, 136))
    with pytest.raises(NotAConfirmerHere):
        await supersede_fact(
            sg,
            context=held,
            fact_id=by_daughter.id,
            value=136,
            confidence=1.0,
            confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
            confirmation_id=his,
        )


async def test_a_rule_from_above_this_layer_stops_a_fact_before_it_is_written(
    sg: AsyncSession,
) -> None:
    """The label-photo rule (E04) is a hook on `before_fact_write`, not a docstring."""
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    told = await record_event(
        sg,
        context=owner,
        kind=EventKind.MESSAGE,
        occurred_at=SEPT_3,
        source_channel=SourceChannel.WHATSAPP,
        label="the helper says half a tablet",
    )

    class NeedsTheLabelPhoto(Refusal):
        """A high-risk dose is saved from a label photo, never from a message alone."""

    seen: list[FactDraft] = []

    async def label_photo_rule(
        session: AsyncSession, context: KeyContext, draft: FactDraft
    ) -> None:
        seen.append(draft)
        if (draft.subject, draft.attribute) == ("medication", "dose") and draft.artifact_id is None:
            raise NeedsTheLabelPhoto("a dose is saved from the label photo")

    semantic.before_fact_write.append(label_photo_rule)
    try:
        with pytest.raises(NeedsTheLabelPhoto):
            await assert_fact(
                sg,
                context=owner,
                subject="medication",
                attribute="dose",
                value=0.5,
                unit="tablet",
                confidence=0.7,
                event_id=told.id,
            )
        from_photo = await _dose(sg, owner, photo, 138)
    finally:
        semantic.before_fact_write.remove(label_photo_rule)
    assert [d.event_id for d in seen] == [told.id, None]
    assert from_photo.artifact_id == photo.id
    assert _refusals(list(await read_audit(sg, context=owner))) == {
        (Action.WRITE, "fact", "NeedsTheLabelPhoto")
    }
    assert [f.value for f in await current_facts(sg, context=owner, subject="medication")] == [138]


async def test_a_dispute_keeps_the_persons_number_current_until_a_person_settles_it(
    sg: AsyncSession,
    clock: FrozenClock,
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
        yes=True,
    )

    clock.set(SEPT_10)
    disputed = await supersede_fact(
        sg,
        context=owner,
        fact_id=confirmed.id,
        value=150,
        confidence=0.9,
        confidence_state=ConfidenceState.DISPUTED,
        confirmation_id=await _yes(sg, owner, _next(confirmed, 150)),
    )
    # The dispute names the fact it disputes and is kept, but it closes nothing and is not
    # current: the person's 136 stands while the dispute is open.
    assert disputed.supersedes_id == confirmed.id and disputed.superseded_at is None
    assert confirmed.superseded_at is None
    current = await current_facts(sg, context=owner, subject="medication", at=SEPT_10)
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
            confirmation_id=await _yes(sg, owner, _next(disputed, 150)),
        )

    # A person settles it: the new number is current, and the old fact and its dispute close.
    clock.set(SEPT_10 + timedelta(days=1))
    settled = await supersede_fact(
        sg,
        context=owner,
        fact_id=confirmed.id,
        value=150,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmation_id=await _yes(sg, owner, _next(confirmed, 150)),
    )
    later = SEPT_10 + timedelta(days=2)
    assert [(f.id, f.value) for f in await current_facts(sg, context=owner, at=later)] == [
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
        with pytest.raises(SourceNotNamed):
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
    with pytest.raises(CameInAnotherWay):
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
        (Action.WRITE, "event", "SourceNotNamed"),
        (Action.WRITE, "event", "CameInAnotherWay"),
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
    clock: FrozenClock,
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
        confirmation_id=await _yes(
            sg,
            owner,
            AppointmentDraft(
                provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="see Dr Tan again"
            ),
        ),
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
                confirmation_id=await _yes(
                    sg,
                    neighbour,
                    StatusChange(appointment_id=visit.id, status=AppointmentStatus.CANCELLED),
                ),
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
    clock.set(SEPT_10)
    confirmed = await change_appointment_status(
        sg,
        context=owner,
        appointment_id=visit.id,
        status=AppointmentStatus.CONFIRMED,
        confirmation_id=await _yes(
            sg, owner, StatusChange(appointment_id=visit.id, status=AppointmentStatus.CONFIRMED)
        ),
    )
    assert confirmed.status is AppointmentStatus.CONFIRMED
    assert confirmed.status_changed_by_person_id == owner.person_id
    assert confirmed.confirmed_by_person_id == owner.person_id
    trail = await read_audit(sg, context=owner)
    # The yes written down; then one read to find the visit, one read of the yes, one write
    # to use it, one write to change the visit; then the owner's own read of the trail.
    assert len(trail) == before + 6
    assert (Action.WRITE, "appointment", visit.id) in {
        (e.action, e.target, e.target_id) for e in trail if as_utc(e.at) == SEPT_10
    }
    # A yes for a different visit, or from another profile, does not fit this one.
    for wrong in (
        await _yes(
            sg, owner, StatusChange(appointment_id=uuid.uuid4(), status=AppointmentStatus.CANCELLED)
        ),
        await _yes(
            sg, neighbour, StatusChange(appointment_id=visit.id, status=AppointmentStatus.CANCELLED)
        ),
    ):
        with pytest.raises(NotAConfirmerHere):
            await change_appointment_status(
                sg,
                context=owner,
                appointment_id=visit.id,
                status=AppointmentStatus.CANCELLED,
                confirmation_id=wrong,
            )
    with pytest.raises(NotThatStatusChange):
        await change_appointment_status(
            sg,
            context=owner,
            appointment_id=visit.id,
            status=AppointmentStatus.PLANNED,
            confirmation_id=await _yes(
                sg, owner, StatusChange(appointment_id=visit.id, status=AppointmentStatus.PLANNED)
            ),
        )
    cancelled = await change_appointment_status(
        sg,
        context=owner,
        appointment_id=visit.id,
        status=AppointmentStatus.CANCELLED,
        confirmation_id=await _yes(
            sg, owner, StatusChange(appointment_id=visit.id, status=AppointmentStatus.CANCELLED)
        ),
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
                confirmation_id=await _yes(
                    sg, owner, StatusChange(appointment_id=visit.id, status=status)
                ),
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
        confirmation_id=await _yes(
            sg,
            owner,
            AppointmentDraft(
                provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="see Dr Tan again"
            ),
        ),
        episode_id=episode.id,
    )
    assert reading.artifact_id == photo.id

    # The consent record outlives everything else by design (E00-02: RESTRICT): while it
    # stands, the profile cannot go.
    savepoint = await sg.begin_nested()
    with pytest.raises(IntegrityError):
        await sg.execute(delete(Profile).where(Profile.id == owner.profile_id))
    await savepoint.rollback()
    await sg.execute(delete(Consent).where(Consent.profile_id == owner.profile_id))
    # Then the profile goes (PDPA), and the ties cascade past every composite key.
    await sg.execute(delete(Profile).where(Profile.id == owner.profile_id))
    for table in (Artifact, Event, Fact, Episode, Appointment, Confirmation, AuditEntry):
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
        # Even a row that entered out of band says the scope it sits under: the table
        # refuses one that does not.
        written_scope=Scope.RECORDS,
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
        written_scope=Scope.READINGS,
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
    # ...and the chain is followed: a fact with no artefact, citing an event that cites it.
    twice_removed = Fact(
        profile_id=owner.profile_id,
        subject="weight",
        attribute="kg",
        value=69,
        confidence=0.8,
        confidence_state=ConfidenceState.EXTRACTED,
        event_id=stray_event.id,
        valid_from=SEPT_3,
    )
    sg.add(twice_removed)
    await sg.flush()
    assert await current_facts(sg, context=owner, subject="weight") == []
    # ...while the same rows citing an artefact held here are.
    photo = await _photo(sg, owner)
    here = await _systolic(sg, owner, photo, 138)
    assert [f.id for f in await current_facts(sg, context=owner, at=SEPT_10)] == [here.id]


# --- 8. an appointment carries who confirmed it --------------------------------------------


async def test_an_appointment_records_the_person_whose_yes_was_used(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await _pa(sg)
    dr_tan = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    again = AppointmentDraft(
        provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="see Dr Tan again"
    )
    visit = await book_appointment(
        sg,
        context=owner,
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10,
        purpose="see Dr Tan again",
        confirmation_id=await _yes(
            sg,
            owner,
            AppointmentDraft(
                provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="see Dr Tan again"
            ),
        ),
    )
    assert visit.confirmed_by_person_id == owner.person_id

    # Another profile's yes, a yes for something else, or no yes at all: none fits.
    neighbour = await _pa(sg, phone="+6591110002")
    photo = await _photo(sg, owner)
    for wrong in (
        await _yes(sg, neighbour, again),
        await _yes(sg, owner, _dose_draft(photo, 136, ConfidenceState.CONFIRMED_BY_PERSON)),
        uuid.uuid4(),
    ):
        with pytest.raises(NotAConfirmerHere):
            await book_appointment(
                sg,
                context=owner,
                provider_id=dr_tan.id,
                scheduled_at=SEPT_10,
                purpose="see Dr Tan again",
                confirmation_id=wrong,
            )
    # A yes for a visit on another day does not book this one.
    with pytest.raises(NotWhatWasConfirmed):
        await book_appointment(
            sg,
            context=owner,
            provider_id=dr_tan.id,
            scheduled_at=SEPT_10 + timedelta(days=1),
            purpose="see Dr Tan again",
            confirmation_id=await _yes(sg, owner, again),
        )
    assert _refusals(list(await read_audit(sg, context=owner))) == {
        (Action.WRITE, "appointment", "NotAConfirmerHere"),
        (Action.WRITE, "appointment", "NotWhatWasConfirmed"),
    }
    # The confirm is not optional at the signature either.
    with pytest.raises(TypeError):
        await book_appointment(  # type: ignore[call-arg]
            sg, context=owner, provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="see Dr Tan"
        )

    # A key holder's yes names her, and is hers alone to act on.
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110004"
    )
    await agree_to_family_sharing(sg, owner, daughter, role=KeyRole.CAREGIVER)
    key = await grant_key(sg, context=owner, holder=daughter, role=KeyRole.CAREGIVER)
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=daughter.id, profile_id=owner.profile_id
    )
    hers = await confirm(sg, held, again)
    with pytest.raises(NotAConfirmerHere):
        await book_appointment(
            sg,
            context=owner,
            provider_id=dr_tan.id,
            scheduled_at=SEPT_10,
            purpose="see Dr Tan again",
            confirmation_id=hers.id,
        )
    by_daughter = await book_appointment(
        sg,
        context=held,
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10,
        purpose="see Dr Tan again",
        confirmation_id=hers.id,
    )
    assert by_daughter.confirmed_by_person_id == daughter.id

    # Her key is closed. Her context is stale and her yes is fresh, and there is no time a
    # caller can pass: the clock says the key is gone, and the booking is refused.
    hers_again = await confirm(sg, held, again)
    await revoke_key(sg, context=owner, key_id=key.id)
    before = list(await read_audit(sg, context=owner))
    with pytest.raises(NotAConfirmerHere):
        await book_appointment(
            sg,
            context=held,
            provider_id=dr_tan.id,
            scheduled_at=SEPT_10,
            purpose="see Dr Tan again",
            confirmation_id=hers_again.id,
        )
    since = [e for e in await read_audit(sg, context=owner) if e not in before]
    assert {e.actor_person_id for e in since} == {daughter.id, owner.person_id}
    assert [e.refused_because for e in since if e.outcome is Outcome.REFUSED] == [
        "NotAConfirmerHere"
    ]


async def test_a_yes_takes_one_change_and_a_visit_changes_status_only_through_its_service(
    sg: AsyncSession,
) -> None:
    owner = await _pa(sg)
    dr_tan = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
    )
    again = AppointmentDraft(
        provider_id=dr_tan.id, scheduled_at=SEPT_10, purpose="see Dr Tan again"
    )
    yes = await confirm(sg, owner, again)

    # A yes is not extended, not re-aimed, and once spent not un-spent.
    async with refused_unit(sg, ImmutableRow):
        yes.expires_at = SEPT_10
        await sg.flush()
    async with refused_unit(sg, ImmutableRow):
        yes.content_digest = "0" * 64
        await sg.flush()
    await sg.refresh(yes)
    visit = await book_appointment(
        sg,
        context=owner,
        provider_id=dr_tan.id,
        scheduled_at=SEPT_10,
        purpose="see Dr Tan again",
        confirmation_id=yes.id,
    )
    assert yes.consumed_at is not None
    async with refused_unit(sg, ImmutableRow):
        yes.consumed_at = None
        await sg.flush()

    # A visit's status changes only while its service is changing it.
    async with refused_unit(sg, ImmutableRow):
        visit.status = AppointmentStatus.CANCELLED
        await sg.flush()
    await sg.refresh(visit)
    assert visit.status is AppointmentStatus.PLANNED
    cancelled = await change_appointment_status(
        sg,
        context=owner,
        appointment_id=visit.id,
        status=AppointmentStatus.CANCELLED,
        confirmation_id=await _yes(
            sg, owner, StatusChange(appointment_id=visit.id, status=AppointmentStatus.CANCELLED)
        ),
    )
    assert cancelled.status is AppointmentStatus.CANCELLED


async def test_a_medicine_fact_is_held_under_the_medicines_scope(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    photo = await _photo(sg, owner)
    await _dose(sg, owner, photo, 138)
    await _systolic(sg, owner, photo, 138)

    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110004"
    )
    await agree_to_family_sharing(
        sg, owner, daughter, scopes=[Scope.RECORDS, Scope.READINGS, Scope.VISITS], role=KeyRole.CAREGIVER
    )
    await grant_key(
        sg,
        context=owner,
        holder=daughter,
        role=KeyRole.CAREGIVER,
        scopes=[Scope.RECORDS, Scope.READINGS, Scope.VISITS],
    )
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=daughter.id, profile_id=owner.profile_id
    )
    # The records and the readings are hers; the medicines are not, however reached.
    assert [f.subject for f in await current_facts(sg, context=held, subject="blood_pressure")] == [
        "blood_pressure"
    ]
    with pytest.raises(OutOfScope):
        await current_facts(sg, context=held, subject="medication")
    with pytest.raises(OutOfScope):
        await _dose(sg, held, photo, 136)
    with pytest.raises(OutOfScope):
        await confirm(sg, held, _dose_draft(photo, 136, ConfidenceState.CONFIRMED_BY_PERSON))
    assert {
        (e.scope, e.refused_because)
        for e in await read_audit(sg, context=owner)
        if e.outcome is Outcome.REFUSED
    } == {(Scope.MEDICINES, "OutOfScope")}
