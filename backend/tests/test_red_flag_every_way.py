"""Red flags reach someone whatever the settings (#162); WhatsApp consent narrowed (#163).

No setting chooses how a red flag goes: every rung tries every way each person can be reached
— an app push when they have a device, WhatsApp where they may be sent it — and the notice on
their family page is always written. A rung no phone reaches moves on at once, and the chief
sees who could not be reached. After Pa stops WhatsApp only a red flag goes to his family
there; a key holder's no to WhatsApp is kept to, a red flag included; and the chief sees who
Nura cannot message on WhatsApp. A message to him naming a medicine, scheduled before #164
refused them, is not sent.
"""

from __future__ import annotations

from datetime import time
from itertools import permutations
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_write
from app.channels.whatsapp.opt_in import record_opt_in
from app.channels.whatsapp.outbound.level0 import run_family_notice
from app.clock import FrozenClock
from app.consent.models import ConsentChannel, ConsentPurpose
from app.consent.opt_in_words import OPT_IN_VERSION
from app.consent.service import revoke_consent
from app.consent.withdrawal import stop_lines, stopped_lines
from app.db import utcnow
from app.delivery.reach import who_nura_reaches
from app.delivery.triggers.ladder import not_reached, open_flags_for
from app.delivery.triggers.models import (
    Delivery,
    DeliveryChannel,
    DeliveryOutcome,
    DeliverySettings,
    Ladder,
    TriggerType,
)
from app.delivery.triggers.rules import RULES, config_of
from app.family.models import PushChannel, ScheduledPush
from app.family.roster import add_slot
from app.keys.scopes import KeyRole, Scope
from app.safety.plain_words import verify
from app.state.service import render_from_state
from tests.delivery_support import MEI, PA, SITI, Home, home
from tests.test_triggers import _run, at

CHANNELS = ("app_push", "whatsapp", "caregiver")


async def _said_no(sg: AsyncSession, h: Home) -> None:
    """Siti answers no to "Nura may message you on WhatsApp." at the key-accept step."""
    await record_opt_in(
        sg,
        context=await h.ctx(sg, h.siti),
        messages=False,
        joins_group=False,
        wording_version=OPT_IN_VERSION,
        language="ms",
    )


async def _flag_rows(sg: AsyncSession) -> list[Delivery]:
    ladder = (await sg.scalars(select(Ladder).where(Ladder.flag_id.is_not(None)))).one()
    return list((await sg.scalars(select(Delivery).where(Delivery.ladder_id == ladder.id))).all())


# --- decision 1: no setting silences a red flag ------------------------------------------------


def test_no_stored_list_routes_a_red_flag() -> None:
    """Whatever a row kept before #162 says for the flag — any channels, in any order — the
    flag goes by every channel of its rule, and is never capped."""
    for size in (1, 2, 3):
        for listed in permutations(CHANNELS, size):
            row = DeliverySettings(channels={"flag": list(listed)}, caps={"flag": 1})
            config = config_of(row)
            assert config.channels_for(TriggerType.FLAG) == RULES[TriggerType.FLAG].channels
            assert config.cap_for(TriggerType.FLAG) is None


async def test_a_stored_flag_list_that_reaches_nobody_still_reaches_the_one_on_duty(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """A row kept before #162 says the flag goes to "the caregiver" only — which, for a flag,
    reached nobody. Pa falls: Mei, on duty, is told on her WhatsApp all the same, and the
    notice waits on her family page."""
    clock.set(at(9))
    h = await home(sg, tmp_path)
    await audited_write(
        sg,
        DeliverySettings,
        h.owner,
        Scope.FAMILY,
        skip_quiet_days=False,
        channels={"flag": ["caregiver"]},
        caps={},
        set_by_person_id=h.pa.id,
        set_at=utcnow(),
    )
    handled = await h.inbound(sg, PA, "I fell in the bathroom")
    assert handled.outcome == "red_flag"
    rows = await _flag_rows(sg)
    assert {(row.to_person_id, row.via, row.outcome) for row in rows} == {
        (h.mei.id, DeliveryChannel.WHATSAPP, DeliveryOutcome.SENT),
        (h.mei.id, DeliveryChannel.IN_APP, DeliveryOutcome.SENT),
    }
    assert h.sent_to(h.mei)[-1].startswith("This one we do not wait for.")


async def test_a_rung_no_phone_reaches_moves_on_at_once_and_the_chief_sees_who(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """Siti is on duty, said no to WhatsApp and has no device. Pa falls at 09:00: her rung is
    the notice on her family page only, so the ladder does not wait five minutes on her — Mei,
    his chief, is told at 09:00. Mei sees that Siti could not be reached; Siti still sees the
    flag in the app and can say she is on it."""
    clock.set(at(9))
    h = await home(sg, tmp_path, roster=False)
    await add_slot(
        sg,
        context=h.owner,
        person_id=h.siti.id,
        role=KeyRole.HELPER,
        from_time=time(6, 0),
        to_time=time(23, 0),
        weekdays=list(range(7)),
    )
    await _said_no(sg, h)
    handled = await h.inbound(sg, PA, "I fell in the bathroom")
    assert handled.outcome == "red_flag"
    # She knows, and the card ends on the boundary line (B1: every urgent card does).
    said = handled.replies[0].text.splitlines()
    assert "Mei knows now." in said
    assert said[-1] == "Nura does not decide what is wrong."
    ladder = (await sg.scalars(select(Ladder).where(Ladder.flag_id.is_not(None)))).one()
    assert [(step["standing"], step["after_minutes"]) for step in ladder.rungs] == [
        ("on_duty", 0),
        ("chief", 5),
    ]
    rows = await _flag_rows(sg)
    hers = {(row.via, row.outcome) for row in rows if row.to_person_id == h.siti.id}
    assert hers == {
        (None, DeliveryOutcome.NO_CHANNEL),
        (DeliveryChannel.IN_APP, DeliveryOutcome.SENT),
    }
    [missed] = [row for row in rows if row.outcome is DeliveryOutcome.NO_CHANNEL]
    assert missed.passed_over == ["whatsapp: said no", "app_push: no device"]
    [meis] = [
        row for row in rows if row.to_person_id == h.mei.id and row.via is DeliveryChannel.WHATSAPP
    ]
    assert meis.due_at == at(9) and meis.outcome is DeliveryOutcome.SENT
    assert [one.to_e164 for one in h.whatsapp.sent if one.to_e164 == SITI] == []
    mei = await h.ctx(sg, h.mei)
    assert await not_reached(sg, context=mei, ladder=ladder) == [h.siti.id]
    siti_open = await open_flags_for(sg, context=await h.ctx(sg, h.siti))
    assert [one.id for one in siti_open] == [ladder.id]
    # Five minutes on, nobody new is asked: both rungs went at 09:00.
    later = await _run(sg, h, clock, at(9, 6))
    assert [s for s in later.sent if s.delivery.trigger_type is TriggerType.FLAG] == []


# --- decision 3: after he stops WhatsApp, only a red flag goes there ---------------------------


async def test_after_pa_stops_whatsapp_his_family_hears_about_him_there_only_for_a_red_flag(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await revoke_consent(
        sg, context=h.owner, purpose=ConsentPurpose.WHATSAPP, captured_via=ConsentChannel.APP
    )
    h.push.register(h.siti.id)
    await _run(sg, h, clock, at(8, 31))
    report = await _run(sg, h, clock, at(9, 1))
    # The tablet check to Siti goes by app push, not WhatsApp.
    [check] = [s.delivery for s in report.sent if s.delivery.trigger_type is TriggerType.DOSE]
    assert check.to_person_id == h.siti.id and check.via is DeliveryChannel.APP_PUSH
    # The weekly count to his chief does not go on WhatsApp: she reads it in the app.
    notices = await run_family_notice(
        sg,
        settings=h.via.settings,
        providers=h.via.providers,
        number=h.via.number,
        profile_id=h.owner.profile_id,
    )
    assert notices == []
    assert all(one.to_e164 != MEI for one in h.whatsapp.sent)
    before = len(h.whatsapp.sent)
    # A red flag still goes to his family on WhatsApp.
    handled = await h.inbound(sg, MEI, "he fell in the bathroom")
    assert handled.flag_id is not None
    assert [one.to_e164 for one in h.whatsapp.sent[before:] if one.to_e164 == SITI] == [SITI]


# --- decision 4: a key holder's no to WhatsApp is kept to --------------------------------------


async def test_a_key_holder_who_said_no_gets_a_red_flag_by_push_and_in_the_app_only(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(9))
    h = await home(sg, tmp_path)
    await _said_no(sg, h)
    h.push.register(h.siti.id)
    await h.inbound(sg, PA, "I fell in the bathroom")
    await _run(sg, h, clock, at(9, 6))
    hers = [row for row in await _flag_rows(sg) if row.to_person_id == h.siti.id]
    assert {row.via for row in hers} == {DeliveryChannel.APP_PUSH, DeliveryChannel.IN_APP}
    assert all(row.outcome is DeliveryOutcome.SENT for row in hers)
    [notice] = [row for row in hers if row.via is DeliveryChannel.IN_APP]
    assert "whatsapp: said no" in notice.passed_over
    assert [one.to_e164 for one in h.whatsapp.sent if one.to_e164 == SITI] == []


async def test_the_chief_sees_who_nura_cannot_message_on_whatsapp(
    sg: AsyncSession, tmp_path: Path
) -> None:
    h = await home(sg, tmp_path)
    await _said_no(sg, h)
    found = await who_nura_reaches(sg, context=h.owner, push=h.push, language="en")
    reach = {one.person_id: one for one in found}
    assert reach[h.mei.id].whatsapp and reach[h.mei.id].lines == []
    assert reach[h.siti.id].lines == [
        "Nura cannot send Siti messages on WhatsApp.",
        "Siti sees what Nura says only in the app.",
    ]
    h.push.register(h.siti.id)
    found = await who_nura_reaches(sg, context=h.owner, push=h.push, language="ms")
    reach = {one.person_id: one for one in found}
    assert reach[h.siti.id].lines == ["Nura tidak boleh hantar mesej kepada Siti di WhatsApp."]


def test_the_stop_lines_say_who_is_told_where_and_that_nothing_else_goes_there() -> None:
    lines = stop_lines(
        ConsentPurpose.WHATSAPP,
        name="",
        language="en",
        still_told=["Mei, your daughter,"],
        told_in_app=["Siti, your helper,"],
    )
    assert lines == [
        "If you stop this, Nura stops messaging you on WhatsApp.",
        "Your Today page and reminders will not come there.",
        "Mei, your daughter, is still told on WhatsApp when you are unwell.",
        "Siti, your helper, is still told in the app when you are unwell.",
        "Your family is told everything else only in the app.",
        "You can say yes to WhatsApp again later.",
    ]
    for language in ("en", "ms", "zh"):
        kwargs = {"name": "", "language": language, "still_told": ["Mei"], "told_in_app": ["Siti"]}
        said = stop_lines(ConsentPurpose.WHATSAPP, **kwargs) + stopped_lines(  # type: ignore[arg-type]
            ConsentPurpose.WHATSAPP,
            **kwargs,  # type: ignore[arg-type]
        )
        for line in said:
            assert [f for f in verify(line, language) if f.severity == "fail"] == [], line
    # With nobody on his family list, nothing is said about them; with family who hold no
    # emergency card, that nothing else about him goes to them on WhatsApp.
    assert len(stop_lines(ConsentPurpose.WHATSAPP, name="", language="en")) == 3
    assert stop_lines(ConsentPurpose.WHATSAPP, name="", language="en", family=True)[2] == (
        "Your family is told everything else only in the app."
    )


# --- decision 2: a message to him naming a medicine is not sent ---------------------------------


async def test_a_message_scheduled_naming_a_medicine_is_skipped_not_sent(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(9))
    h = await home(sg, tmp_path)
    await render_from_state(
        sg,
        ScheduledPush,
        h.owner,
        Scope.SEND,
        composed_by_person_id=h.mei.id,
        composed_at=utcnow(),
        language="en",
        template_id="water_pill_morning",
        lines=["Nura says the water pill is at 8.", "Take it with breakfast."],
        send_at=at(9, 30),
        via_channel=PushChannel.WHATSAPP,
        expires_at=at(12),
    )
    report = await _run(sg, h, clock, at(10))
    family = [
        s.delivery for s in report.sent if s.delivery.trigger_type is TriggerType.FAMILY_MESSAGE
    ]
    [row] = family
    assert row.outcome is DeliveryOutcome.SKIPPED and row.reason == "names a medicine or a dose"
    assert not any("water pill" in text for text in h.sent_to(h.pa))
    again = await _run(sg, h, clock, at(10, 30))
    assert [s for s in again.sent if s.delivery.trigger_type is TriggerType.FAMILY_MESSAGE] == []
