"""E00-01 acceptance.

    Patient node owns all data; family accounts attach via grants; data at rest in region.

One test per clause. `region=` is always the region the deployment under test serves.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.identity.models import Profile
from app.identity.service import ProfileAlreadyOwned, create_own_profile, register_person
from app.keys.context import NoKey, OutOfScope, resolve_key_context
from app.keys.grants import grant_key, list_keys, revoke_key
from app.keys.scopes import KeyRole, KeyWindow, Scope
from app.regions import OutOfRegion, Region
from tests.support import OPENING_CONSENT, Note, add_note, agree_to_family_sharing, read_notes

# --- the patient node owns all data ------------------------------------------------------


async def test_the_patient_owns_every_row_of_his_health_graph(sg: AsyncSession) -> None:
    pa = await register_person(sg, region=Region.SG, display_name="Pa", phone_e164="+6591110001")
    profile = await create_own_profile(sg, region=Region.SG, owner=pa, consent=OPENING_CONSENT)

    assert profile.owner_person_id == pa.id
    assert profile.region is Region.SG

    # A person owns at most one profile: the health graph has exactly one owner.
    with pytest.raises(ProfileAlreadyOwned):
        await create_own_profile(sg, region=Region.SG, owner=pa, consent=OPENING_CONSENT)

    # The owner reads his own graph without a key, and every scope is his.
    owner = await resolve_key_context(sg, region=Region.SG, person_id=pa.id, profile_id=profile.id)
    assert owner.is_owner
    assert owner.scopes == frozenset(Scope)

    note = await add_note(sg, owner, scope=Scope.NOTES, body="Pa keeps this one to himself.")
    assert note.profile_id == profile.id

    # Every row of the graph hangs off the profile, so a stranger reaches none of it.
    stranger = await register_person(
        sg, region=Region.SG, display_name="Someone", phone_e164="+6591110099"
    )
    with pytest.raises(NoKey):
        await resolve_key_context(
            sg, region=Region.SG, person_id=stranger.id, profile_id=profile.id
        )

    # A profile that does not exist refuses in the same words, so none can be enumerated.
    with pytest.raises(NoKey):
        await resolve_key_context(
            sg, region=Region.SG, person_id=stranger.id, profile_id=uuid.uuid4()
        )


# --- family accounts attach via grants ---------------------------------------------------


async def test_family_accounts_attach_through_a_grant_and_reach_only_its_scope(
    sg: AsyncSession,
    clock: FrozenClock,
) -> None:
    pa = await register_person(sg, region=Region.SG, display_name="Pa", phone_e164="+6591110001")
    profile = await create_own_profile(sg, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
    owner = await resolve_key_context(sg, region=Region.SG, person_id=pa.id, profile_id=profile.id)
    await add_note(sg, owner, scope=Scope.MEDICINES, body="The water pill is at 8 in the morning.")
    await add_note(sg, owner, scope=Scope.NOTES, body="Pa keeps this one to himself.")

    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )

    # No grant, no reach.
    with pytest.raises(NoKey):
        await resolve_key_context(
            sg, region=Region.SG, person_id=daughter.id, profile_id=profile.id
        )

    # Pa agrees to share with his daughter (E00-02); her key rests on that and names it.
    hers = await agree_to_family_sharing(sg, owner, daughter, role=KeyRole.CAREGIVER)

    key = await grant_key(
        sg,
        context=owner,
        holder=daughter,
        role=KeyRole.CAREGIVER,
        scopes=[Scope.MEDICINES, Scope.VISITS],
        window=KeyWindow.THIRTY_DAYS,
    )
    assert key.profile_id == profile.id
    assert key.consent_id == hers.id
    assert key.granted_by_person_id == pa.id
    assert key.expires_at is not None

    held = await resolve_key_context(
        sg, region=Region.SG, person_id=daughter.id, profile_id=profile.id
    )
    assert not held.is_owner
    # The two she was cut, and the face of the graph, which every key opens.
    assert held.scopes == frozenset({Scope.MEDICINES, Scope.VISITS, Scope.PROFILE})

    assert [n.body for n in await read_notes(sg, held, scope=Scope.MEDICINES)] == [
        "The water pill is at 8 in the morning."
    ]
    with pytest.raises(OutOfScope):
        await read_notes(sg, held, scope=Scope.NOTES)

    # Holding a key is not the same as cutting one.
    siti = await register_person(
        sg, region=Region.SG, display_name="Siti", phone_e164="+6591110003"
    )
    await agree_to_family_sharing(sg, owner, siti, role=KeyRole.HELPER)
    with pytest.raises(OutOfScope):
        await grant_key(sg, context=held, holder=siti, role=KeyRole.HELPER)

    # A chief may cut one, but never wider than the key he holds.
    son = await register_person(sg, region=Region.SG, display_name="Son", phone_e164="+6591110004")
    await agree_to_family_sharing(sg, owner, son, role=KeyRole.CHIEF)
    chief_key = await grant_key(
        sg,
        context=owner,
        holder=son,
        role=KeyRole.CHIEF,
        scopes=[Scope.MEDICINES, Scope.FAMILY],
    )
    assert chief_key.expires_at is None
    chief = await resolve_key_context(sg, region=Region.SG, person_id=son.id, profile_id=profile.id)
    helper_key = await grant_key(sg, context=chief, holder=siti, role=KeyRole.HELPER)
    assert helper_key.scopes_held == frozenset({Scope.MEDICINES, Scope.PROFILE})

    # The owner reads every key cut on his own graph.
    assert {k.id for k in await list_keys(sg, context=owner)} == {
        key.id,
        chief_key.id,
        helper_key.id,
    }

    # The window closes on its own.
    later = datetime.now(UTC) + timedelta(days=31)
    with pytest.raises(NoKey):
        clock.set(later)
        await resolve_key_context(
            sg, region=Region.SG, person_id=daughter.id, profile_id=profile.id
        )

    # And the owner can close it sooner.
    await revoke_key(sg, context=owner, key_id=key.id)
    with pytest.raises(NoKey):
        await resolve_key_context(
            sg, region=Region.SG, person_id=daughter.id, profile_id=profile.id
        )


# --- data at rest in region --------------------------------------------------------------


async def test_health_data_is_written_and_read_only_in_its_own_region(
    sg: AsyncSession, my: AsyncSession
) -> None:
    pa = await register_person(sg, region=Region.SG, display_name="Pa", phone_e164="+6591110001")
    profile = await create_own_profile(sg, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
    owner = await resolve_key_context(sg, region=Region.SG, person_id=pa.id, profile_id=profile.id)
    await add_note(sg, owner, scope=Scope.MEDICINES, body="The water pill is at 8 in the morning.")

    # The Malaysian deployment holds none of it.
    assert await my.scalar(select(func.count()).select_from(Profile)) == 0
    assert await my.scalar(select(func.count()).select_from(Note)) == 0

    # It will not open a health graph for a person pinned to Singapore either.
    with pytest.raises(OutOfRegion):
        await create_own_profile(my, region=Region.MY, owner=pa, consent=OPENING_CONSENT)

    # And it refuses to read an out-of-region profile, however that row arrived.
    ash = await register_person(my, region=Region.MY, display_name="Ash", phone_e164="+60121110001")
    my.add(
        Profile(
            id=profile.id,
            region=Region.SG,
            display_name=profile.display_name,
            language=profile.language,
            owner_person_id=ash.id,
        )
    )
    await my.flush()
    with pytest.raises(OutOfRegion):
        await resolve_key_context(my, region=Region.MY, person_id=ash.id, profile_id=profile.id)
