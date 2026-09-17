"""What a role presets, how long a window runs, and what a key holder cannot reach."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.identity.models import Person
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, NoKey, OutOfScope, resolve_key_context
from app.keys.grants import (
    ChiefMustNameSuccessor,
    NoKeyToClose,
    NotTheirKeyToCut,
    NotTheirKeyToLeave,
    SuccessorMustAlreadyHoldAKey,
    grant_key,
    leave_key,
    list_keys,
    revoke_key,
    waive_successor,
)
from app.keys.models import Key
from app.keys.scopes import ALL_SCOPES, DEFAULT_WINDOW, ROLE_SCOPES, KeyRole, KeyWindow, Scope
from app.regions import Region
from tests.support import OPENING_CONSENT, agree_to_family_sharing

GRANTED_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


async def _owner(session: AsyncSession) -> KeyContext:
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    profile = await create_own_profile(session, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
    owner = await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )
    return owner


def test_private_notes_and_money_are_preset_to_nobody_but_a_chief() -> None:
    assert ROLE_SCOPES[KeyRole.CHIEF] == ALL_SCOPES
    for role, scopes in ROLE_SCOPES.items():
        if role is KeyRole.CHIEF:
            continue
        assert Scope.NOTES not in scopes
        assert Scope.MONEY not in scopes
        assert Scope.FAMILY not in scopes, f"{role} must not be able to cut keys"


def test_a_clinic_key_closes_itself_after_three_days() -> None:
    assert DEFAULT_WINDOW[KeyRole.CLINIC] is KeyWindow.SEVENTY_TWO_HOURS
    key = Key(
        role=KeyRole.CLINIC,
        scopes=[],
        granted_at=GRANTED_AT,
        expires_at=GRANTED_AT + timedelta(hours=72),
    )
    assert key.is_active(GRANTED_AT + timedelta(hours=71))
    assert not key.is_active(GRANTED_AT + timedelta(hours=73))


def test_a_key_with_no_end_runs_until_it_is_closed() -> None:
    key = Key(role=KeyRole.CHIEF, scopes=[], granted_at=GRANTED_AT)
    far_off = GRANTED_AT + timedelta(days=3650)
    assert key.is_active(far_off)
    key.revoked_at = GRANTED_AT + timedelta(days=1)
    assert not key.is_active(far_off)


async def test_a_second_grant_to_one_person_replaces_the_first(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    clock.set(GRANTED_AT)
    await agree_to_family_sharing(sg, owner, mei)

    clock.set(GRANTED_AT)
    first = await grant_key(
        sg,
        context=owner,
        holder=mei,
        role=KeyRole.VIEWER,
    )
    clock.set(GRANTED_AT + timedelta(days=1))
    second = await grant_key(
        sg,
        context=owner,
        holder=mei,
        role=KeyRole.CAREGIVER,
    )

    assert first.revoked_at is not None
    clock.set(GRANTED_AT + timedelta(days=2))
    held = await resolve_key_context(
        sg,
        region=Region.SG,
        person_id=mei.id,
        profile_id=owner.profile_id,
    )
    assert held.key_id == second.id
    assert held.role is KeyRole.CAREGIVER

    # Both rows stay, so the owner can read what was held and when it was closed.
    assert {key.id for key in await list_keys(sg, context=owner)} == {first.id, second.id}


async def test_a_key_holder_cannot_read_the_family_list(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    await agree_to_family_sharing(sg, owner, mei)
    key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.CAREGIVER)

    held = await resolve_key_context(
        sg, region=Region.SG, person_id=mei.id, profile_id=owner.profile_id
    )
    with pytest.raises(OutOfScope):
        await list_keys(sg, context=held)
    with pytest.raises(OutOfScope):
        await revoke_key(sg, context=held, key_id=key.id)


async def test_closing_a_key_that_is_not_on_this_profile_is_refused(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    with pytest.raises(NoKeyToClose):
        await revoke_key(sg, context=owner, key_id=owner.profile_id)


# --- leaving (#144) -------------------------------------------------------------------------


async def _held(sg: AsyncSession, person: Person, profile_id: object) -> KeyContext:
    return await resolve_key_context(
        sg, region=Region.SG, person_id=person.id, profile_id=profile_id
    )


async def test_a_holder_with_no_family_scope_can_close_her_own_key(sg: AsyncSession) -> None:
    """The whole point of leaving (#144): a plain viewer, who cannot call `revoke_key` at
    all (`test_a_key_holder_cannot_read_the_family_list`), closes her own key on her own
    word."""
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    await agree_to_family_sharing(sg, owner, mei)
    key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.VIEWER)
    assert Scope.FAMILY not in key.scopes_held

    held = await _held(sg, mei, owner.profile_id)
    with pytest.raises(OutOfScope):
        await revoke_key(sg, context=held, key_id=key.id)

    closed = await leave_key(sg, context=held, key_id=key.id)
    assert closed.revoked_at is not None
    # The row stays, so Pa can still read that it was held.
    assert {row.id for row in await list_keys(sg, context=owner)} == {key.id}
    with pytest.raises(NoKey):
        await resolve_key_context(
            sg, region=Region.SG, person_id=mei.id, profile_id=owner.profile_id
        )


async def test_leaving_someone_elses_key_is_refused(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    kit = await register_person(sg, region=Region.SG, display_name="Kit", phone_e164="+6591110003")
    await agree_to_family_sharing(sg, owner, mei)
    await agree_to_family_sharing(sg, owner, kit)
    meis_key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.VIEWER)
    await grant_key(sg, context=owner, holder=kit, role=KeyRole.VIEWER)

    kits_context = await _held(sg, kit, owner.profile_id)
    with pytest.raises(NotTheirKeyToLeave):
        await leave_key(sg, context=kits_context, key_id=meis_key.id)


async def test_the_owner_has_no_key_of_his_own_to_leave(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    await agree_to_family_sharing(sg, owner, mei)
    key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.VIEWER)
    with pytest.raises(NotTheirKeyToLeave):
        await leave_key(sg, context=owner, key_id=key.id)


async def test_leaving_an_already_closed_key_is_refused(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    await agree_to_family_sharing(sg, owner, mei)
    key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.VIEWER)
    held = await _held(sg, mei, owner.profile_id)
    await leave_key(sg, context=held, key_id=key.id)
    with pytest.raises(NoKeyToClose):
        await leave_key(sg, context=held, key_id=key.id)


async def test_a_chief_cannot_leave_without_naming_a_successor_or_pas_own_word(
    sg: AsyncSession,
) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    await agree_to_family_sharing(sg, owner, mei)
    chief_key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.CHIEF)
    meis_context = await _held(sg, mei, owner.profile_id)

    with pytest.raises(ChiefMustNameSuccessor):
        await leave_key(sg, context=meis_context, key_id=chief_key.id)
    # Nothing closed: the refusal is written down, the key is still live.
    live = await _held(sg, mei, owner.profile_id)
    assert live.key_id == chief_key.id


async def test_a_chief_names_the_next_chief_and_leaves_in_one_go(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    kit = await register_person(sg, region=Region.SG, display_name="Kit", phone_e164="+6591110003")
    await agree_to_family_sharing(sg, owner, mei)
    await agree_to_family_sharing(sg, owner, kit)
    chief_key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.CHIEF)
    await grant_key(sg, context=owner, holder=kit, role=KeyRole.VIEWER)
    meis_context = await _held(sg, mei, owner.profile_id)

    closed = await leave_key(sg, context=meis_context, key_id=chief_key.id, successor_person_id=kit.id)
    assert closed.revoked_at is not None

    kits_context = await _held(sg, kit, owner.profile_id)
    assert kits_context.role is KeyRole.CHIEF
    assert Scope.FAMILY in kits_context.scopes


async def test_naming_a_stranger_as_the_next_chief_is_refused(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    stranger = await register_person(
        sg, region=Region.SG, display_name="Someone", phone_e164="+6591110099"
    )
    await agree_to_family_sharing(sg, owner, mei)
    chief_key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.CHIEF)
    meis_context = await _held(sg, mei, owner.profile_id)

    with pytest.raises(SuccessorMustAlreadyHoldAKey):
        await leave_key(
            sg, context=meis_context, key_id=chief_key.id, successor_person_id=stranger.id
        )


async def test_pas_own_word_lets_a_chief_leave_with_no_successor(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    await agree_to_family_sharing(sg, owner, mei)
    chief_key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.CHIEF)

    waived = await waive_successor(sg, context=owner, key_id=chief_key.id)
    assert waived.successor_waived_at is not None
    assert waived.successor_waived_by_person_id == owner.person_id

    meis_context = await _held(sg, mei, owner.profile_id)
    closed = await leave_key(sg, context=meis_context, key_id=chief_key.id)
    assert closed.revoked_at is not None


async def test_only_pa_may_say_there_will_be_no_next_chief(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    await agree_to_family_sharing(sg, owner, mei)
    chief_key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.CHIEF)
    meis_context = await _held(sg, mei, owner.profile_id)
    with pytest.raises(NotTheirKeyToCut):
        await waive_successor(sg, context=meis_context, key_id=chief_key.id)


async def test_waiving_a_non_chief_key_is_refused(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    await agree_to_family_sharing(sg, owner, mei)
    key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.VIEWER)
    with pytest.raises(NoKeyToClose):
        await waive_successor(sg, context=owner, key_id=key.id)
