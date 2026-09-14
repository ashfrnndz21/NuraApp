"""E12-01: roles and scoped grants by category and time window.

    Chief, caregiver, viewer, helper, emergency-only; scope enforced on every read.

Narrowing a key takes parts and days away on the chief's own yes; widening is refused
without a fresh consent and a new key; the presets and the helper list are in his words.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.db import as_utc
from app.family.grants import grants, helper_list, role_presets
from app.keys.confirm import NotWhatWasConfirmed, confirm
from app.keys.context import OutOfScope
from app.keys.grants import (
    NothingToNarrow,
    NotTheirKeyToCut,
    WouldWiden,
    grant_key,
    key_change_draft_for,
    narrow_key,
)
from app.keys.scopes import DEFAULT_WINDOW, ROLE_SCOPES, KeyRole, KeyWindow, Scope
from app.safety.plain_words import verify
from tests.family_support import MONDAY, household


def _refusals(entries: list[AuditEntry] | tuple[AuditEntry, ...], name: str) -> list[AuditEntry]:
    return [e for e in entries if e.outcome is Outcome.REFUSED and e.refused_because == name]


async def test_narrowing_a_key_takes_parts_and_days_away_at_once(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    assert (await h.ctx(sg, h.siti)).scopes == ROLE_SCOPES[KeyRole.HELPER]

    _, _, _, draft = await key_change_draft_for(
        sg,
        context=mei,
        key_id=h.siti_key.id,
        scopes=[Scope.MEDICINES],
        window=KeyWindow.THIRTY_DAYS,
    )
    yes = await confirm(sg, mei, draft)
    key = await narrow_key(
        sg,
        context=mei,
        key_id=h.siti_key.id,
        scopes=[Scope.MEDICINES],
        window=KeyWindow.THIRTY_DAYS,
        confirmation_id=yes.id,
    )
    assert key.id == h.siti_key.id, "narrowed in place, not replaced"
    assert key.scopes_held == {Scope.PROFILE, Scope.MEDICINES}
    assert as_utc(key.expires_at) == MONDAY + timedelta(days=30)

    # Enforced on the next read: her context is what the key says now.
    siti = await h.ctx(sg, h.siti)
    assert siti.scopes == {Scope.PROFILE, Scope.MEDICINES}
    with pytest.raises(OutOfScope):
        siti.require(Scope.EMERGENCY)

    # And on the trail, in Mei's name.
    pa = await h.ctx(sg, h.pa)
    lines = await read_audit(sg, context=pa, action=Action.WRITE, scope=Scope.FAMILY)
    assert any(
        e.target == "key" and e.target_id == key.id and e.actor_person_id == h.mei.id for e in lines
    )


async def test_widening_is_refused_and_the_way_wider_is_a_new_key_on_the_consent(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)

    # One part more than the key opens: refused before any yes is looked for.
    with pytest.raises(WouldWiden):
        await key_change_draft_for(
            sg, context=mei, key_id=h.siti_key.id, scopes=[Scope.MEDICINES, Scope.READINGS]
        )
    # A longer window: a 30-day key asked to run always.
    _, _, _, shorten = await key_change_draft_for(
        sg, context=mei, key_id=h.siti_key.id, window=KeyWindow.THIRTY_DAYS
    )
    yes = await confirm(sg, mei, shorten)
    await narrow_key(
        sg,
        context=mei,
        key_id=h.siti_key.id,
        window=KeyWindow.THIRTY_DAYS,
        confirmation_id=yes.id,
    )
    with pytest.raises(WouldWiden):
        await narrow_key(
            sg,
            context=mei,
            key_id=h.siti_key.id,
            window=KeyWindow.ALWAYS,
            confirmation_id=yes.id,
        )
    # The key is as it was, and the refusals are on the trail.
    siti = await h.ctx(sg, h.siti)
    assert siti.scopes == ROLE_SCOPES[KeyRole.HELPER]
    pa = await h.ctx(sg, h.pa)
    assert len(_refusals(list(await read_audit(sg, context=pa)), "WouldWiden")) >= 1

    # Wider is a new key, cut under the consent Pa gave for Siti — which caps it too.
    wider = await grant_key(
        sg,
        context=mei,
        holder=h.siti,
        role=KeyRole.HELPER,
        scopes=[Scope.MEDICINES, Scope.EMERGENCY, Scope.SEND, Scope.READINGS],
    )
    assert wider.id != h.siti_key.id
    assert Scope.READINGS not in wider.scopes_held, "never wider than the words Pa read"
    assert wider.scopes_held == ROLE_SCOPES[KeyRole.HELPER]


async def test_a_yes_binds_to_the_change_and_only_a_chief_narrows(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    _, _, _, draft = await key_change_draft_for(
        sg, context=mei, key_id=h.siti_key.id, scopes=[Scope.MEDICINES]
    )
    yes = await confirm(sg, mei, draft)
    with pytest.raises(NotWhatWasConfirmed):
        await narrow_key(
            sg,
            context=mei,
            key_id=h.siti_key.id,
            scopes=[Scope.MEDICINES, Scope.EMERGENCY],
            confirmation_id=yes.id,
        )
    with pytest.raises(NothingToNarrow):
        await key_change_draft_for(
            sg, context=mei, key_id=h.siti_key.id, scopes=sorted(ROLE_SCOPES[KeyRole.HELPER])
        )
    kit = await h.ctx(sg, h.kit)
    with pytest.raises(NotTheirKeyToCut):
        await key_change_draft_for(sg, context=kit, key_id=h.siti_key.id, scopes=[Scope.MEDICINES])
    pa = await h.ctx(sg, h.pa)
    assert _refusals(list(await read_audit(sg, context=pa)), "NotTheirKeyToCut")


def test_the_six_roles_are_preset_with_a_window_each_in_plain_words() -> None:
    for language in ("en", "ms", "zh"):
        presets = role_presets(language, name="Mei")
        assert [p.role for p in presets] == list(KeyRole)
        for preset in presets:
            assert preset.scopes == ROLE_SCOPES[preset.role]
            assert preset.window is DEFAULT_WINDOW[preset.role]
            assert preset.lines[0].startswith("Mei")
            for line in preset.lines:
                if line.startswith("- "):
                    continue
                assert not [f for f in verify(line, language) if f.severity == "fail"], line
    helper = next(p for p in role_presets("en", name="Siti") if p.role is KeyRole.HELPER)
    assert helper.lines[0] == "Siti is your helper."
    assert "- your medicines" in helper.lines
    assert helper.lines[-1] == "Siti can see them until you say stop."


async def test_the_helper_list_says_who_holds_a_helper_key_and_what_she_may_do(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    helpers, empty = await helper_list(sg, context=mei, language="en")
    assert empty == []
    assert [helper.name for helper in helpers] == ["Siti"]
    assert helpers[0].lines == [
        "Siti is your helper.",
        "Siti can see your medicines and tap Taken for you.",
        "Siti can see your emergency card.",
        "Siti gets the list from Nura every morning.",
        "Siti can see them until you say stop.",
    ]
    for line in helpers[0].lines:
        assert not [f for f in verify(line, "en") if f.severity == "fail"], line

    # Narrowed to the medicines only: the list says so, and the end is a day of its own.
    _, _, _, draft = await key_change_draft_for(
        sg,
        context=mei,
        key_id=h.siti_key.id,
        scopes=[Scope.MEDICINES],
        window=KeyWindow.SEVENTY_TWO_HOURS,
    )
    yes = await confirm(sg, mei, draft)
    await narrow_key(
        sg,
        context=mei,
        key_id=h.siti_key.id,
        scopes=[Scope.MEDICINES],
        window=KeyWindow.SEVENTY_TWO_HOURS,
        confirmation_id=yes.id,
    )
    helpers, _ = await helper_list(sg, context=mei, language="en")
    assert helpers[0].lines == [
        "Siti is your helper.",
        "Siti can see your medicines and tap Taken for you.",
        "Siti can see them for 3 days.",
    ]
    everyone = await grants(sg, context=mei, language="ms")
    assert sorted(grant.holder_name for grant in everyone) == ["Kit", "Mei", "Siti"]
    siti = next(grant for grant in everyone if grant.holder_name == "Siti")
    assert siti.lines[0] == "Siti ialah pembantu anda."
    assert siti.window is KeyWindow.SEVENTY_TWO_HOURS

    # A helper key closed: nobody holds one, and the screen has a line for that.
    from app.keys.grants import revoke_key

    await revoke_key(sg, context=mei, key_id=h.siti_key.id)
    helpers, empty = await helper_list(sg, context=mei, language="en")
    assert helpers == [] and empty == ["Nobody holds a helper key to your record yet."]
