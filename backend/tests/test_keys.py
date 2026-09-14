"""What a role presets, how long a window runs, and what a key holder cannot reach."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.grants import NoKeyToClose, grant_key, list_keys, revoke_key
from app.keys.models import Key
from app.keys.scopes import ALL_SCOPES, DEFAULT_WINDOW, ROLE_SCOPES, KeyRole, KeyWindow, Scope
from app.regions import Region

GRANTED_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


async def _owner(session: AsyncSession) -> KeyContext:
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    profile = await create_own_profile(session, region=Region.SG, owner=pa)
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


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
        basis="owner_consent",
        granted_at=GRANTED_AT,
        expires_at=GRANTED_AT + timedelta(hours=72),
    )
    assert key.is_active(GRANTED_AT + timedelta(hours=71))
    assert not key.is_active(GRANTED_AT + timedelta(hours=73))


def test_a_key_with_no_end_runs_until_it_is_closed() -> None:
    key = Key(role=KeyRole.CHIEF, scopes=[], basis="lpa", granted_at=GRANTED_AT)
    far_off = GRANTED_AT + timedelta(days=3650)
    assert key.is_active(far_off)
    key.revoked_at = GRANTED_AT + timedelta(days=1)
    assert not key.is_active(far_off)


async def test_a_second_grant_to_one_person_replaces_the_first(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")

    first = await grant_key(
        sg,
        context=owner,
        holder=mei,
        role=KeyRole.VIEWER,
        basis="owner_consent",
        now=GRANTED_AT,
    )
    second = await grant_key(
        sg,
        context=owner,
        holder=mei,
        role=KeyRole.CAREGIVER,
        basis="owner_consent",
        now=GRANTED_AT + timedelta(days=1),
    )

    assert first.revoked_at is not None
    held = await resolve_key_context(
        sg,
        region=Region.SG,
        person_id=mei.id,
        profile_id=owner.profile_id,
        now=GRANTED_AT + timedelta(days=2),
    )
    assert held.key_id == second.id
    assert held.role is KeyRole.CAREGIVER

    # Both rows stay, so the owner can read what was held and when it was closed.
    assert {key.id for key in await list_keys(sg, context=owner)} == {first.id, second.id}


async def test_a_key_holder_cannot_read_the_family_list(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    mei = await register_person(sg, region=Region.SG, display_name="Mei", phone_e164="+6591110002")
    key = await grant_key(sg, context=owner, holder=mei, role=KeyRole.CAREGIVER, basis="consent")

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
