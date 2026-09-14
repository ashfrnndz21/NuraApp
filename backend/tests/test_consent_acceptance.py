"""E00-02 acceptance.

    Consent event stored with timestamp, scope and version; revocation removes access
    within a minute.

One test per clause, and then the promises the story makes beyond its acceptance line:
opening a record is agreeing to Nura keeping it, in the same transaction; sharing is
agreed to one person at a time and a key records the consent it was cut under; older
wording does not stand for the current one; a withdrawn consent refuses; the record that
goes out holds every version and every withdrawal, with the day and date of each on the
patient's own clock, and none of the health graph; the rows are pinned to a profile and
its region; a refusal is written into the trail.

The words moving on is simulated by appending a new version to the catalogue, which is
exactly how it happens in the product: `texts.TEXTS` is append-only.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.consent import texts
from app.consent.export import export_consent_record
from app.consent.models import Consent, ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import (
    ConsentOutOfDate,
    ConsentRevoked,
    ConsentWithheld,
    NoConsent,
    NotTheCurrentWording,
    RecordConsent,
    WordingNotOnFile,
    active_consents,
    all_consents,
    grant_consent,
    require_consent,
    revoke_consent,
)
from app.consent.texts import ConsentText, current_version
from app.db import as_utc
from app.identity.models import Person, Profile
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, NoKey, OutOfScope, resolve_key_context
from app.keys.grants import grant_key
from app.keys.models import Key
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event, store_artifact
from app.memory.models import (
    AppointmentStatus,
    ArtifactKind,
    EpisodeKind,
    EventKind,
    ProviderKind,
    SourceChannel,
)
from app.memory.semantic import assert_fact
from app.memory.spine import add_provider, book_appointment
from app.memory.working import open_episode
from app.regions import Region
from tests.support import OPENING_CONSENT, add_note, agree_to_family_sharing

CLAIMED_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
WATER_PILL = "The water pill is at 8 in the morning."
PRIVATE = "Pa keeps this one to himself."
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


async def _pa(
    session: AsyncSession, opened_at: datetime | None = None
) -> tuple[Person, Profile, KeyContext]:
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    profile = await create_own_profile(
        session, region=Region.SG, owner=pa, consent=OPENING_CONSENT, now=opened_at
    )
    owner = await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )
    return pa, profile, owner


async def _agree(
    session: AsyncSession, owner: KeyContext, purpose: ConsentPurpose, now: datetime
) -> Consent:
    return await grant_consent(
        session,
        context=owner,
        purpose=purpose,
        captured_via=ConsentChannel.APP,
        basis=ConsentBasis.OWNER,
        language="en",
        now=now,
    )


def _the_words_move_on(monkeypatch: pytest.MonkeyPatch, purpose: ConsentPurpose) -> str:
    """A new version of the wording is appended to the catalogue. Returns its version."""
    version = str(int(current_version(purpose)) + 1)
    new = ConsentText(purpose, version, "en", "The new words, in plain words.")
    monkeypatch.setattr(texts, "TEXTS", (*texts.TEXTS, new))
    return version


def _strings_in(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings_in(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings_in(v)]
    return []


# --- consent event stored with timestamp, scope and version ------------------------------


async def test_opening_a_record_is_agreeing_to_nura_keeping_it(sg: AsyncSession) -> None:
    """Consent capture at onboarding: the record and its consent are one transaction."""
    pa, profile, owner = await _pa(sg, opened_at=CLAIMED_AT)

    [opening] = await all_consents(sg, context=owner)
    assert opening.purpose is ConsentPurpose.HOLD_HEALTH_RECORD
    assert as_utc(opening.granted_at) == CLAIMED_AT == as_utc(profile.created_at)
    assert opening.text_version == current_version(ConsentPurpose.HOLD_HEALTH_RECORD)
    assert opening.language == "en"
    assert opening.captured_via is ConsentChannel.APP
    assert opening.basis is ConsentBasis.OWNER
    assert opening.person_id == pa.id
    assert opening.holder_person_id is None  # keeping the record is for the whole profile
    # The words he read are on the row, as read.
    assert opening.wording_text == texts.wording(
        ConsentPurpose.HOLD_HEALTH_RECORD, opening.text_version, "en", Region.SG
    )


async def test_a_record_is_not_opened_on_words_that_are_not_todays_words(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    pa = await register_person(sg, region=Region.SG, display_name="Pa", phone_e164="+6591110001")
    in_words_he_never_saw = RecordConsent(
        text_version=current_version(ConsentPurpose.HOLD_HEALTH_RECORD),
        language="zh",
        captured_via=ConsentChannel.APP,
    )
    with pytest.raises(WordingNotOnFile):
        await create_own_profile(sg, region=Region.SG, owner=pa, consent=in_words_he_never_saw)

    _the_words_move_on(monkeypatch, ConsentPurpose.HOLD_HEALTH_RECORD)
    with pytest.raises(NotTheCurrentWording):
        await create_own_profile(sg, region=Region.SG, owner=pa, consent=OPENING_CONSENT)

    # Neither refusal opened anything: no profile, no consent, nothing to point a key at.
    assert await sg.scalar(select(func.count()).select_from(Profile)) == 0
    assert await sg.scalar(select(func.count()).select_from(Consent)) == 0


async def test_nothing_is_kept_once_the_consent_to_keep_it_is_withdrawn(
    sg: AsyncSession,
) -> None:
    """Every writer of health data asks the gate: artefacts, events, facts, episodes, the
    directory and the appointments alike."""
    _, _, owner = await _pa(sg, opened_at=CLAIMED_AT)
    day = CLAIMED_AT + timedelta(days=1)

    photo = await store_artifact(
        sg,
        context=owner,
        kind=ArtifactKind.PHOTO,
        storage_key="sg/profiles/pa/bp-book.jpg",
        content_type="image/jpeg",
        sha256="a" * 64,
        captured_at=day,
        source_channel=SourceChannel.APP,
        region=Region.SG,
        now=day,
    )
    dr_tan = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG, now=day
    )

    await revoke_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        captured_via=ConsentChannel.APP,
        now=CLAIMED_AT + timedelta(days=2),
    )
    later = CLAIMED_AT + timedelta(days=3)

    with pytest.raises(ConsentRevoked):
        await store_artifact(
            sg,
            context=owner,
            kind=ArtifactKind.PHOTO,
            storage_key="sg/profiles/pa/bp-book-2.jpg",
            content_type="image/jpeg",
            sha256="b" * 64,
            captured_at=later,
            source_channel=SourceChannel.APP,
            region=Region.SG,
            now=later,
        )
    with pytest.raises(ConsentRevoked):
        await record_event(
            sg, context=owner, kind=EventKind.READING, occurred_at=later, artifact_id=photo.id,
            now=later,
        )
    with pytest.raises(ConsentRevoked):
        await assert_fact(
            sg,
            context=owner,
            subject="blood_pressure",
            attribute="systolic",
            value=138,
            confidence=0.9,
            artifact_id=photo.id,
            now=later,
        )
    with pytest.raises(ConsentRevoked):
        await open_episode(sg, context=owner, kind=EpisodeKind.ILLNESS, label="flu", now=later)
    with pytest.raises(ConsentRevoked):
        await add_provider(
            sg, context=owner, name="Dr Lim", kind=ProviderKind.DOCTOR, region=Region.SG, now=later
        )
    with pytest.raises(ConsentRevoked):
        await book_appointment(
            sg,
            context=owner,
            provider_id=dr_tan.id,
            scheduled_at=later + timedelta(days=7),
            purpose="review",
            status=AppointmentStatus.PLANNED,
            now=later,
        )


async def test_a_consent_is_stored_with_its_moment_its_scope_and_its_version(
    sg: AsyncSession,
) -> None:
    pa, profile, owner = await _pa(sg)
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )

    given = await agree_to_family_sharing(sg, owner, daughter, now=CLAIMED_AT)

    assert given.granted_at == CLAIMED_AT
    assert given.revoked_at is None
    # Its scope: this profile, this purpose, this one person, and nothing wider.
    assert given.profile_id == profile.id
    assert given.purpose is ConsentPurpose.SHARE_WITH_FAMILY
    assert given.holder_person_id == daughter.id
    # Its version: the wording he saw, in the language he saw it in, and the words.
    assert given.text_version == current_version(ConsentPurpose.SHARE_WITH_FAMILY)
    assert given.language == "en"
    assert given.wording_text.startswith("You choose who in your family")
    assert given.person_id == pa.id
    assert given.captured_via is ConsentChannel.APP
    assert given.basis is ConsentBasis.OWNER

    held = await require_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.SHARE_WITH_FAMILY,
        scope=Scope.FAMILY,
        holder_person_id=daughter.id,
        now=CLAIMED_AT,
    )
    assert held.consent_id == given.id


async def test_research_is_not_something_nura_asks_consent_for() -> None:
    assert "research" not in {purpose.value for purpose in ConsentPurpose}


# --- per key: sharing is agreed to one person at a time ----------------------------------


async def test_a_key_is_cut_under_the_consent_that_names_its_holder_and_no_other(
    sg: AsyncSession,
) -> None:
    _, _, owner = await _pa(sg)
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )
    son = await register_person(sg, region=Region.SG, display_name="Son", phone_e164="+6591110004")

    # Nobody agreed to anyone yet: no key, and no key row left behind.
    with pytest.raises(ConsentWithheld):
        await grant_key(sg, context=owner, holder=daughter, role=KeyRole.CAREGIVER)
    assert await sg.scalar(select(func.count()).select_from(Key)) == 0

    # Pa agrees to his daughter. That says nothing about his son.
    hers = await agree_to_family_sharing(sg, owner, daughter, now=CLAIMED_AT)
    key = await grant_key(sg, context=owner, holder=daughter, role=KeyRole.CAREGIVER)
    assert key.consent_id == hers.id
    with pytest.raises(ConsentWithheld):
        await grant_key(sg, context=owner, holder=son, role=KeyRole.VIEWER)


# --- revocation removes access within a minute -------------------------------------------


async def test_withdrawing_sharing_from_one_person_closes_their_keys_within_a_minute(
    sg: AsyncSession,
) -> None:
    _, profile, owner = await _pa(sg)
    family = {
        KeyRole.CAREGIVER: await register_person(
            sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
        ),
        KeyRole.CHIEF: await register_person(
            sg, region=Region.SG, display_name="Son", phone_e164="+6591110004"
        ),
        KeyRole.EMERGENCY: await register_person(
            sg, region=Region.SG, display_name="Neighbour", phone_e164="+6591110005"
        ),
    }
    for role, person in family.items():
        await agree_to_family_sharing(sg, owner, person, now=CLAIMED_AT)
        await grant_key(sg, context=owner, holder=person, role=role, now=CLAIMED_AT)
    a_week_on = CLAIMED_AT + timedelta(days=7)
    for role, person in family.items():
        held = await resolve_key_context(
            sg, region=Region.SG, person_id=person.id, profile_id=profile.id, now=a_week_on
        )
        assert held.role is role

    # Pa stops sharing with his neighbour, the emergency contact.
    neighbour = family[KeyRole.EMERGENCY]
    withdrawn = await revoke_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.SHARE_WITH_FAMILY,
        captured_via=ConsentChannel.APP,
        holder_person_id=neighbour.id,
        now=a_week_on,
    )
    assert [consent.revoked_at for consent in withdrawn] == [a_week_on]

    # Within the minute the neighbour holds nothing; the daughter and the son still do.
    a_minute_short = a_week_on + timedelta(seconds=59)
    with pytest.raises(NoKey):
        await resolve_key_context(
            sg, region=Region.SG, person_id=neighbour.id, profile_id=profile.id,
            now=a_minute_short,
        )
    for person in (family[KeyRole.CAREGIVER], family[KeyRole.CHIEF]):
        assert await resolve_key_context(
            sg, region=Region.SG, person_id=person.id, profile_id=profile.id, now=a_minute_short
        )

    # And no new key can be cut for him on the strength of a consent that is gone.
    with pytest.raises(ConsentRevoked):
        await grant_key(
            sg, context=owner, holder=neighbour, role=KeyRole.VIEWER, now=a_minute_short
        )


# --- versioned: older wording does not stand for the current one ------------------------


async def test_a_consent_to_older_wording_does_not_satisfy_the_current_version(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, owner = await _pa(sg)
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )
    old = await agree_to_family_sharing(sg, owner, daughter, now=CLAIMED_AT)
    a_day_on = CLAIMED_AT + timedelta(days=1)
    assert old.is_active(a_day_on)

    new_version = _the_words_move_on(monkeypatch, ConsentPurpose.SHARE_WITH_FAMILY)

    with pytest.raises(ConsentOutOfDate):
        await require_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.SHARE_WITH_FAMILY,
            scope=Scope.FAMILY,
            holder_person_id=daughter.id,
            now=a_day_on,
        )
    # Which means no key can be cut for her until he agrees to the new words.
    with pytest.raises(ConsentOutOfDate):
        await grant_key(sg, context=owner, holder=daughter, role=KeyRole.VIEWER, now=a_day_on)

    # A fresh agreement to the current words stands, and the old one stays as history.
    fresh = await agree_to_family_sharing(sg, owner, daughter, now=a_day_on)
    assert fresh.text_version == new_version
    assert fresh.wording_text == "The new words, in plain words."
    held = await require_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.SHARE_WITH_FAMILY,
        scope=Scope.FAMILY,
        holder_person_id=daughter.id,
        now=a_day_on,
    )
    assert held.consent_id == fresh.id
    sharing = [
        c
        for c in await active_consents(sg, context=owner, now=a_day_on)
        if c.purpose is ConsentPurpose.SHARE_WITH_FAMILY
    ]
    assert [c.id for c in sharing] == [old.id, fresh.id]


# --- revocable: a withdrawn consent refuses ----------------------------------------------


async def test_a_withdrawn_consent_refuses_and_a_missing_one_refuses_differently(
    sg: AsyncSession,
) -> None:
    _, _, owner = await _pa(sg)

    with pytest.raises(ConsentWithheld):
        await require_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.RECORDING,
            scope=Scope.VISITS,
            now=CLAIMED_AT,
        )

    given = await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.VERBAL_WITNESSED,
        basis=ConsentBasis.OWNER,
        language="en",
        now=CLAIMED_AT,
    )
    await revoke_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.APP,
        now=CLAIMED_AT + timedelta(hours=1),
    )

    later = CLAIMED_AT + timedelta(hours=2)
    with pytest.raises(ConsentRevoked) as refused:
        await require_consent(
            sg, context=owner, purpose=ConsentPurpose.RECORDING, scope=Scope.VISITS, now=later
        )
    assert isinstance(refused.value, NoConsent)
    # The row stays: withdrawing is a mark on it, not a deletion.
    assert given.revoked_at == CLAIMED_AT + timedelta(hours=1)
    assert given.revoked_by_person_id == owner.person_id
    still_open = await active_consents(sg, context=owner, now=later)
    assert [c.purpose for c in still_open] == [ConsentPurpose.HOLD_HEALTH_RECORD]


# --- exportable: every version and withdrawal, with its day, and no health content -------


async def test_the_record_holds_every_version_and_withdrawal_and_none_of_the_graph(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    pa, profile, owner = await _pa(sg, opened_at=CLAIMED_AT)
    await add_note(sg, owner, scope=Scope.MEDICINES, body=WATER_PILL)
    await add_note(sg, owner, scope=Scope.NOTES, body=PRIVATE)
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )

    [first] = await all_consents(sg, context=owner)  # the one he gave opening the record
    _the_words_move_on(monkeypatch, ConsentPurpose.HOLD_HEALTH_RECORD)
    second = await _agree(
        sg, owner, ConsentPurpose.HOLD_HEALTH_RECORD, CLAIMED_AT + timedelta(days=30)
    )
    whatsapp = await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
        now=CLAIMED_AT + timedelta(days=31),
    )
    await revoke_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.APP,
        now=CLAIMED_AT + timedelta(days=40),
    )
    sharing = await agree_to_family_sharing(
        sg, owner, daughter, now=CLAIMED_AT + timedelta(days=40, hours=1)
    )
    await grant_key(
        sg, context=owner, holder=daughter, role=KeyRole.CAREGIVER,
        now=CLAIMED_AT + timedelta(days=40, hours=1),
    )

    record = await export_consent_record(
        sg, context=owner, now=CLAIMED_AT + timedelta(days=41)
    )

    # The structured half: one entry per consent ever given, oldest first.
    assert record.document["profile"] == {
        "name": "Pa",
        "region": "SG",
        "region_name": "Singapore",
    }
    assert record.document["prepared_at"] == "2026-10-25T08:00:00+00:00"
    entries = record.document["consents"]
    assert [entry["id"] for entry in entries] == [
        str(first.id), str(second.id), str(whatsapp.id), str(sharing.id)
    ]
    assert entries[0]["version"] == "1" and entries[0]["status"] == "out_of_date"
    assert entries[1]["version"] == current_version(ConsentPurpose.HOLD_HEALTH_RECORD) == "2"
    assert entries[1]["status"] == "in_force"
    assert entries[1]["wording"] == "The new words, in plain words."
    assert entries[2]["status"] == "withdrawn"
    assert entries[2]["withdrawn_at"] == "2026-10-24T08:00:00+00:00"
    assert entries[2]["withdrawn_by"] == "Pa"
    assert entries[0]["given_at"] == "2026-09-14T08:00:00+00:00"
    assert entries[0]["given_by"] == "Pa"
    assert entries[0]["basis"] == "owner"
    assert entries[2]["captured_via"] == "whatsapp"
    assert entries[3]["holder"] == "Daughter"  # who he has agreed to share with

    # The rendered half is plain words a person can read, with the day and date of every
    # moment and nothing to decode: no clock time, no zone, no "version".
    text = record.rendered.body.decode()
    assert record.rendered.media_type == "text/markdown"
    assert text.startswith("# What Pa agreed to\n")
    assert "Pa said yes to the things on this page.\nPa's papers never leave Singapore." in text
    assert "Nura made this page for Pa on Sunday 25 October 2026." in text
    assert "- Pa said yes in the app on Monday 14 September 2026." in text
    assert "- Pa said yes on WhatsApp on Thursday 15 October 2026." in text
    assert "  Pa stopped this on Saturday 24 October 2026." in text
    assert "  These are the words Pa read in English:\n  \"Nura keeps your papers" in text
    assert "They never leave Singapore." in text
    assert "  Nura has changed these words since Pa said yes.\n  Nura will ask Pa to say yes again." in text
    assert "  This one is still on." in text
    assert "## Sharing with your family\n\n- Pa said yes in the app on Saturday 24 October 2026.\n  Daughter can see Pa's papers." in text
    for jargon in ("UTC", "version", "08:00", "in force", "withdrew", "SG", "agreed to this"):
        assert jargon not in text, jargon

    # And nothing from the graph itself is in either half: no health content, and no
    # identifier but the consent rows' own.
    everything = _strings_in(record.document) + [text]
    joined = "\n".join(everything)
    assert WATER_PILL not in joined and PRIVATE not in joined
    assert set(UUID.findall(joined)) == {str(c.id) for c in (first, second, whatsapp, sharing)}
    assert str(profile.id) not in joined and str(pa.id) not in joined


async def test_the_words_on_the_page_are_the_words_on_the_row_not_todays_catalogue(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, owner = await _pa(sg, opened_at=CLAIMED_AT)
    [opening] = await all_consents(sg, context=owner)
    as_read = opening.wording_text

    # If the catalogue were ever edited in place, the record would still say what was read.
    edited = tuple(
        ConsentText(t.purpose, t.version, t.language, "Different words.", t.region)
        for t in texts.TEXTS
    )
    monkeypatch.setattr(texts, "TEXTS", edited)
    record = await export_consent_record(sg, context=owner, now=CLAIMED_AT + timedelta(days=1))
    assert record.document["consents"][0]["wording"] == as_read
    assert as_read in record.rendered.body.decode()
    assert "Different words." not in record.rendered.body.decode()


async def test_the_page_says_the_day_on_the_patients_own_clock(sg: AsyncSession) -> None:
    """Seven in the morning on Monday in Singapore is still Sunday in UTC."""
    seven_am_monday_sgt = datetime(2026, 9, 14, 7, 0, tzinfo=UTC) - timedelta(hours=8)
    assert seven_am_monday_sgt.strftime("%A") == "Sunday"
    _, _, owner = await _pa(sg, opened_at=seven_am_monday_sgt)
    record = await export_consent_record(sg, context=owner, now=seven_am_monday_sgt)
    assert record.document["consents"][0]["given_at"] == "2026-09-13T23:00:00+00:00"
    assert record.document["consents"][0]["given_at_plain"] == "Monday 14 September 2026"
    assert "- Pa said yes in the app on Monday 14 September 2026." in record.rendered.body.decode()


# --- region-pinned and profile-scoped ----------------------------------------------------


async def test_consent_rows_are_pinned_to_the_profile_and_stay_in_its_region(
    sg: AsyncSession, my: AsyncSession
) -> None:
    _, profile, owner = await _pa(sg)
    given = await _agree(sg, owner, ConsentPurpose.RECORDING, CLAIMED_AT)
    assert given.profile_id == profile.id

    # A caregiver's key reaches the medicines, not the record of what Pa agreed to.
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )
    await agree_to_family_sharing(sg, owner, daughter)
    await grant_key(sg, context=owner, holder=daughter, role=KeyRole.CAREGIVER)
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=daughter.id, profile_id=profile.id
    )
    with pytest.raises(OutOfScope):
        await active_consents(sg, context=held)
    with pytest.raises(OutOfScope):
        await export_consent_record(sg, context=held)

    # The Malaysian deployment holds none of it.
    assert await my.scalar(select(func.count()).select_from(Consent)) == 0


# --- refusals are in the trail -----------------------------------------------------------


async def test_a_refused_consent_check_is_written_into_the_trail(sg: AsyncSession) -> None:
    _, _, owner = await _pa(sg)
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
        now=CLAIMED_AT,
    )
    await revoke_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.APP,
        now=CLAIMED_AT + timedelta(days=1),
    )
    with pytest.raises(ConsentRevoked):
        await require_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.WHATSAPP,
            scope=Scope.SEND,
            now=CLAIMED_AT + timedelta(days=2),
        )
    with pytest.raises(ConsentWithheld):
        await require_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.RECORDING,
            scope=Scope.VISITS,
            now=CLAIMED_AT + timedelta(days=3),
        )

    refused = [
        entry for entry in await read_audit(sg, context=owner) if entry.outcome is Outcome.REFUSED
    ]
    assert [(entry.target, entry.scope, entry.refused_because) for entry in refused] == [
        (Consent.__tablename__, Scope.VISITS, "ConsentWithheld"),
        (Consent.__tablename__, Scope.SEND, "ConsentRevoked"),
    ]
    assert all(entry.action is Action.READ for entry in refused)
