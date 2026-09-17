"""Upcoming calls with family (design-direction.md, Connect's "Upcoming Call").

    Acceptance: a call names a person, a time and a way to join; nothing is put on the
    calendar without an explicit confirm; the owner's and his chief's to arrange, like the
    roster and the tasks; open to any key that holds the family scope to read.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.family.calls import LinkTooLong, call_draft_for, cancel_call, schedule_call, upcoming_calls
from app.family.common import NotAChief
from app.family.roster import NotOnThisProfile
from app.keys.confirm import AlreadySpent, confirm
from app.keys.context import OutOfScope
from app.keys.scopes import Scope
from tests.conftest import FROZEN_AT
from tests.family_support import household


async def test_scheduling_a_call_needs_an_explicit_confirm(sg: AsyncSession) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    when = FROZEN_AT + timedelta(days=1)

    draft = await call_draft_for(
        sg, context=owner, with_person_id=home.mei.id, scheduled_at=when, call_link=None
    )
    yes = await confirm(sg, owner, draft)
    call = await schedule_call(
        sg, context=owner, with_person_id=home.mei.id, scheduled_at=when, confirmation_id=yes.id
    )
    assert call.with_person_id == home.mei.id
    assert call.call_link is None
    assert call.cancelled_at is None

    # The same yes cannot be spent twice.
    with pytest.raises(AlreadySpent):
        await schedule_call(
            sg, context=owner, with_person_id=home.mei.id, scheduled_at=when, confirmation_id=yes.id
        )


async def test_a_call_is_with_a_family_member_never_a_stranger(sg: AsyncSession) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    stranger_id = uuid.uuid4()
    with pytest.raises(NotOnThisProfile):
        await call_draft_for(
            sg, context=owner, with_person_id=stranger_id, scheduled_at=FROZEN_AT, call_link=None
        )


async def test_a_call_link_is_the_familys_own_join_is_the_link_or_his_phone(
    sg: AsyncSession,
) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    when = FROZEN_AT + timedelta(hours=2)
    link = "https://meet.example.com/pa-and-mei"
    draft = await call_draft_for(
        sg, context=owner, with_person_id=home.mei.id, scheduled_at=when, call_link=link
    )
    yes = await confirm(sg, owner, draft)
    call = await schedule_call(
        sg, context=owner, with_person_id=home.mei.id, scheduled_at=when, confirmation_id=yes.id, call_link=link
    )
    assert call.call_link == link

    with pytest.raises(LinkTooLong):
        await call_draft_for(
            sg,
            context=owner,
            with_person_id=home.mei.id,
            scheduled_at=when,
            call_link="x" * 301,
        )


async def test_upcoming_calls_are_soonest_first_and_cancelling_takes_one_off(
    sg: AsyncSession,
) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    later = FROZEN_AT + timedelta(days=2)
    sooner = FROZEN_AT + timedelta(days=1)
    for when in (later, sooner):
        draft = await call_draft_for(
            sg, context=owner, with_person_id=home.mei.id, scheduled_at=when, call_link=None
        )
        yes = await confirm(sg, owner, draft)
        await schedule_call(
            sg, context=owner, with_person_id=home.mei.id, scheduled_at=when, confirmation_id=yes.id
        )
    found = await upcoming_calls(sg, context=owner)
    assert [call.scheduled_at for call in found] == [sooner, later]

    cancelled = await cancel_call(sg, context=owner, call_id=found[0].id)
    assert cancelled.cancelled_at is not None
    remaining = await upcoming_calls(sg, context=owner)
    assert [call.id for call in remaining] == [found[1].id]


async def test_only_the_owner_or_his_chief_arranges_a_call(sg: AsyncSession) -> None:
    home = await household(sg)
    siti = await home.ctx(sg, home.siti)  # a helper: not the owner, not the chief
    with pytest.raises(NotAChief):
        await call_draft_for(
            sg, context=siti, with_person_id=home.mei.id, scheduled_at=FROZEN_AT, call_link=None
        )


async def test_reading_the_upcoming_calls_needs_the_family_scope(sg: AsyncSession) -> None:
    home = await household(sg, kit_scopes=frozenset({Scope.PROFILE}))
    kit = await home.ctx(sg, home.kit)
    with pytest.raises(OutOfScope):
        await upcoming_calls(sg, context=kit)
