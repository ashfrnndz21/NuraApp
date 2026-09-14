"""Red-flag words are read first on every inbound message (E11-01, E11-06, a safety fix).

Before "ignore" and before the WhatsApp agreement: "ignore that, he fell" is a fall; on a
profile whose patient has not agreed to WhatsApp, the flag is raised on the word alone — the
message is not kept — escalated through the family's app rather than anyone's WhatsApp, and
the sender gets one fixed line; an unknown number still gets only its fixed reply and leaves
no trace, flag included. And "Taken" is a tap: it writes the Taken for the tablet whose
window is open, and nothing when none is.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp.models import MessageKind, WhatsAppMessage, WhatsAppThread
from app.clock import FrozenClock
from app.delivery.triggers.models import Delivery, DeliveryOutcome, Ladder
from app.identity.service import register_person
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.medicines.models import DoseTaken
from app.memory.models import Artifact, Event
from app.regions import Region
from app.safety.red_flags import Feeling, Flag
from tests.medicines_support import add, label
from tests.support import agree_to_family_sharing
from tests.whatsapp_support import KIT, MEI, PA, family

FIXED = (
    "This one we do not wait for.\n"
    "I put it first in the family's app.\n"
    "If it cannot wait, call 995 now."
)


async def _kit_on_the_emergency_card(sg: AsyncSession, home: object) -> object:
    kit = await register_person(sg, region=Region.SG, display_name="Kit", phone_e164=KIT)
    await agree_to_family_sharing(sg, home.owner, kit, scopes={Scope.EMERGENCY})  # type: ignore[attr-defined]
    await grant_key(sg, context=home.owner, holder=kit, role=KeyRole.EMERGENCY)  # type: ignore[attr-defined]
    return kit


async def test_ignore_never_cancels_a_red_flag_word_in_the_same_message(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, MEI, "ignore that, he fell in the bathroom")
    assert handled.outcome == "red_flag" and handled.flag_id is not None
    flag = await sg.get(Flag, handled.flag_id)
    assert flag is not None and flag.feeling is Feeling.FALL
    kept = (await sg.scalars(select(WhatsAppMessage))).all()
    assert any(row.kind is MessageKind.RED_FLAG for row in kept)
    # An ignore with no red-flag word is still honoured absolutely.
    ignored = await home.inbound(sg, MEI, "ignore: BP 150/90 was the neighbour's")
    assert ignored.outcome == "ignored"


async def test_without_whatsapp_consent_a_red_flag_is_raised_and_goes_to_the_familys_app(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path, whatsapp_consent=False)
    kit = await _kit_on_the_emergency_card(sg, home)
    handled = await home.inbound(sg, MEI, "ignore that, he fell in the bathroom")
    assert handled.outcome == "red_flag_unagreed" and handled.flag_id is not None
    flag = await sg.get(Flag, handled.flag_id)
    assert flag is not None and flag.feeling is Feeling.FALL
    assert flag.raised_by_person_id == home.mei.id
    moment = await sg.get(Event, flag.event_id)
    assert moment is not None and moment.label == "fall" and moment.artifact_id is None
    # The message itself is not kept: no words, no thread, no message row.
    assert (await sg.scalars(select(Artifact))).all() == []
    assert (await sg.scalars(select(WhatsAppThread))).all() == []
    assert (await sg.scalars(select(WhatsAppMessage))).all() == []
    # One fixed line to the sender, straight from the provider; nothing to anyone else's WhatsApp.
    assert [(one.to_e164, one.text) for one in home.whatsapp.sent] == [(MEI, FIXED)]
    # The ladder went through the app: Kit (the only other person holding the emergency card)
    # has no device registered yet, so the row says so, and the flag leads his feed.
    ladder = (await sg.scalars(select(Ladder))).one()
    assert ladder.flag_id == flag.id
    [row] = (await sg.scalars(select(Delivery))).all()
    assert row.to_person_id == kit.id and row.outcome is DeliveryOutcome.NO_CHANNEL  # type: ignore[attr-defined]
    assert row.passed_over == ["whatsapp: not agreed", "app_push: no device"]


async def test_an_unknown_number_gets_its_fixed_reply_and_raises_nothing(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, KIT, "he fell, please help")
    assert handled.outcome == "unknown_number" and handled.flag_id is None
    assert (await sg.scalars(select(Flag))).all() == []
    assert (await sg.scalars(select(Ladder))).all() == []
    assert (await sg.scalars(select(Event))).all() == []


async def test_taken_writes_the_tap_for_the_tablet_whose_window_is_open(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(datetime(2026, 9, 13, 22, 0, tzinfo=UTC))  # 06:00 on Monday, his wall clock
    home = await family(sg, tmp_path)
    made = await add(sg, home.owner, label("amlodipine", "5 mg", "1 tab OM"))
    clock.set(datetime(2026, 9, 13, 23, 40, tzinfo=UTC))  # 07:40, breakfast's window is open
    handled = await home.inbound(sg, PA, "Taken")
    assert handled.outcome == "taken"
    assert handled.replies[0].text.splitlines() == [
        "Thank you, I wrote it down.",
        "Mei can see it too.",
    ]
    tap = (await sg.scalars(select(DoseTaken))).one()
    assert tap.line_id == made.line.id and tap.anchor == "breakfast" and tap.by_person_id == home.pa.id
    # Again at 15:00: no window is open, nothing is written.
    clock.set(datetime(2026, 9, 14, 7, 0, tzinfo=UTC))
    again = await home.inbound(sg, PA, "Taken")
    assert again.outcome == "nothing_due"
    assert again.replies[0].text.splitlines() == [
        "There is no tablet to take right now.",
        "I did not write anything down.",
    ]
    assert len((await sg.scalars(select(DoseTaken))).all()) == 1
