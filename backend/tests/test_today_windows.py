"""The moment of a dose, and the proud number, both said by the backend (W1 review).

The client shows a dose as the one thing to do only while the backend marks it `due_now`,
shows the story's missed-dose lines once its window has passed, and shows the proud number
the backend counted — never one it worked out or kept for itself.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.delivery.triggers.preferences import current
from app.keys.scopes import KeyRole, Scope
from app.medicines.dose import Anchor
from app.medicines.service import active_lines, proud_days, record_dose_taken, today
from app.medicines.windows import window_status
from app.onboarding.settings import SettingsValues, save_settings
from app.routines.service import day_of
from tests.conftest import Deployment
from tests.medicines_support import REGISTRY, add, label, let_in, pa

SGT = timedelta(hours=8)


def test_window_status_follows_his_day() -> None:
    """His day (E04-02): an anchor's window opens an hour before its time and closes an hour
    after, or at the next anchor. Breakfast at 07:30 is 06:30 to 08:30; moved to 08:15 it is
    07:15 to 09:15 — the window moves with his breakfast, not with a fixed hour."""
    sgt = timezone(timedelta(hours=8))

    def at(hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 9, 3, hour, minute, tzinfo=sgt)

    usual = day_of(None)
    assert window_status(Anchor.BREAKFAST, at(6, 29), False, usual) == (False, False)
    assert window_status(Anchor.BREAKFAST, at(6, 30), False, usual) == (True, False)
    assert window_status(Anchor.BREAKFAST, at(8, 29), False, usual) == (True, False)
    assert window_status(Anchor.BREAKFAST, at(8, 30), False, usual) == (False, True)
    later = day_of(None, time(8, 15))
    assert window_status(Anchor.BREAKFAST, at(7, 14), False, later) == (False, False)
    assert window_status(Anchor.BREAKFAST, at(8, 50), False, later) == (True, False)
    assert window_status(Anchor.BREAKFAST, at(9, 15), False, later) == (False, True)
    # Lunch 12:30, dinner 18:30, bed 22:00, as the routine has them until someone sets them.
    assert window_status("lunch", at(12), False, usual) == (True, False)
    assert window_status(Anchor.DINNER, at(17, 30), False, usual) == (True, False)
    assert window_status(Anchor.DINNER, at(19, 30), False, usual) == (False, True)
    assert window_status(Anchor.BED, at(21), False, usual) == (True, False)
    assert window_status(Anchor.BED, at(23), False, usual) == (False, True)
    # A taken dose is neither due nor missed, whatever the hour.
    assert window_status(Anchor.BREAKFAST, at(11), True, usual) == (False, False)


async def test_moving_breakfast_to_08_15_moves_the_morning_window_and_its_taken_card(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """E04-02: the dose windows follow his breakfast from his settings (`reach_of`, the one
    settings read), not a fixed hour. At 08:50 with breakfast at 07:30 the morning tablet's
    window has closed: the missed card. He moves breakfast to 08:15: at 08:50 the Taken card
    is up again, and the ladder's window — the same one — moved with it."""
    owner = await pa(sg)
    await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD"))
    clock.set(datetime(2026, 9, 4, 0, 50, tzinfo=UTC))  # 08:50 in Singapore
    [slot] = await today(sg, context=owner, registry=REGISTRY, language="en")
    assert (slot.anchor, slot.due_now, slot.missed) == ("breakfast", False, True)
    assert slot.if_forgotten, "the missed card carries the story's own lines"

    await save_settings(
        sg, context=owner, values=SettingsValues(language="en", breakfast_time=time(8, 15))
    )
    [slot] = await today(sg, context=owner, registry=REGISTRY, language="en")
    assert (slot.due_now, slot.missed, slot.if_forgotten) == (True, False, [])
    config, _ = await current(sg, context=owner)
    sgt = ZoneInfo("Asia/Singapore")
    opens, closes = config.window(date(2026, 9, 4), "breakfast", sgt)
    assert (opens.time(), closes.time()) == (time(7, 15), time(9, 15))

    clock.set(datetime(2026, 9, 4, 1, 15, tzinfo=UTC))  # 09:15: the window has closed
    [slot] = await today(sg, context=owner, registry=REGISTRY, language="en")
    assert (slot.due_now, slot.missed) == (False, True)


async def test_todays_slots_say_due_now_and_missed_from_the_window(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """Frozen at 16:00 in Singapore: breakfast (07:30) has passed; dinner (18:30) opens at
    17:30, so it is not due yet."""
    owner = await pa(sg)
    await add(sg, owner, label("amlodipine", "5 mg", "1 tab BD"))  # breakfast and dinner
    await add(sg, owner, label("metformin", "500 mg", "1 tab OD"))  # breakfast
    slots = await today(sg, context=owner, registry=REGISTRY, language="en")
    by = {(s.line.generic, s.anchor): s for s in slots}
    assert (by["amlodipine", "breakfast"].due_now, by["amlodipine", "breakfast"].missed) == (
        False,
        True,
    )
    assert (by["amlodipine", "dinner"].due_now, by["amlodipine", "dinner"].missed) == (False, False)
    assert (by["metformin", "breakfast"].due_now, by["metformin", "breakfast"].missed) == (
        False,
        True,
    )
    # The missed card carries the story's own lines; the due one carries none.
    assert by["metformin", "breakfast"].if_forgotten[0] == "If you forgot, leave it."
    assert by["metformin", "breakfast"].if_forgotten[-1] == "Never take 2 at once."
    assert by["amlodipine", "dinner"].if_forgotten == []
    # Every card carries the backend's source line: the label, and the day it started.
    assert by["metformin", "breakfast"].source == (
        "This comes from the label you kept on Thursday 3 September."
    )
    # The line view agrees.
    views = await active_lines(sg, context=owner, registry=REGISTRY, language="en")
    lines = {v.line.generic: v for v in views}
    assert (lines["amlodipine"].due_now, lines["amlodipine"].missed) == (False, True)
    assert (lines["metformin"].due_now, lines["metformin"].missed) == (False, True)
    assert lines["metformin"].source == by["metformin", "breakfast"].source
    # A tap on the dinner dose: it is taken, never due; the breakfast one stays missed.
    amlodipine = by["amlodipine", "dinner"].line.id
    await record_dose_taken(sg, context=owner, line_id=amlodipine, anchor="dinner", amount=None)
    slots = await today(sg, context=owner, registry=REGISTRY, language="en")
    by = {(s.line.generic, s.anchor): s for s in slots}
    assert by["amlodipine", "dinner"].taken and not by["amlodipine", "dinner"].due_now
    assert by["amlodipine", "breakfast"].missed
    # At 07:00 tomorrow the breakfast doses are due and nothing is missed.
    clock.set(datetime(2026, 9, 3, 23, 0, tzinfo=UTC))  # 07:00 SGT on the 4th
    slots = await today(sg, context=owner, registry=REGISTRY, language="en")
    assert {(s.anchor, s.due_now, s.missed) for s in slots} == {
        ("breakfast", True, False),
        ("dinner", False, False),
    }


async def test_the_proud_number_is_days_with_a_tablet_taken_from_the_events(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await pa(sg)
    written = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD"))
    assert (await proud_days(sg, context=owner)).days == 0
    await record_dose_taken(
        sg, context=owner, line_id=written.line.id, anchor="breakfast", amount=None
    )
    await record_dose_taken(sg, context=owner, line_id=written.line.id, anchor=None, amount=None)
    assert (await proud_days(sg, context=owner)).days == 1, "two taps on one day are one day"
    clock.step(timedelta(days=3))
    await record_dose_taken(
        sg, context=owner, line_id=written.line.id, anchor="breakfast", amount=None
    )
    counted = await proud_days(sg, context=owner)
    assert counted.days == 2, "a quiet day takes nothing away"
    assert counted.as_of == clock.now()
    # A helper's "given" is his tablet taken: the day counts, and her key reads the same number.
    helper = await let_in(
        sg, owner, phone="+6592220001", name="Mei", role=KeyRole.HELPER, scopes={Scope.MEDICINES}
    )
    clock.step(timedelta(days=1))
    await record_dose_taken(
        sg, context=helper, line_id=written.line.id, anchor="breakfast", amount=None
    )
    assert (await proud_days(sg, context=owner)).days == 3
    assert (await proud_days(sg, context=helper)).days == 3


async def test_the_proud_route_and_the_slots_over_http(deployment: Deployment) -> None:
    client = deployment.client
    await client.post("/auth/phone/start", json={"phone_e164": "+6591110009"})
    code = deployment.sender.last_code("+6591110009")
    token = (
        await client.post("/auth/phone/verify", json={"phone_e164": "+6591110009", "code": code})
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    words = (await client.get("/consent/wording", params={"language": "en"})).json()
    profile = (
        await client.post(
            "/profiles/mine",
            headers=headers,
            json={
                "consent": {
                    "wording_version": words["version"],
                    "language": "en",
                    "captured_via": "app",
                },
                "display_name": "Pa",
                "language": "en",
            },
        )
    ).json()["profile_id"]
    proud = await client.get(f"/api/profiles/{profile}/proud", headers=headers)
    assert proud.status_code == 200 and proud.json()["days"] == 0
    slots = await client.get(f"/api/profiles/{profile}/medicines/today", headers=headers)
    assert slots.status_code == 200 and slots.json() == []
    # A stranger's token gets the refusal, not a number.
    await client.post("/auth/phone/start", json={"phone_e164": "+6591110010"})
    other = (
        await client.post(
            "/auth/phone/verify",
            json={"phone_e164": "+6591110010", "code": deployment.sender.last_code("+6591110010")},
        )
    ).json()["token"]
    refused = await client.get(
        f"/profiles/{profile}/proud", headers={"Authorization": f"Bearer {other}"}
    )
    assert refused.status_code == 403 and refused.json() == {"refusal": "NoKey"}


async def test_keys_carry_the_holders_name_for_the_owner(sg: AsyncSession) -> None:
    from app.audit.access import person_display_name
    from app.keys.grants import list_keys

    owner = await pa(sg)
    await let_in(
        sg, owner, phone="+6592220002", name="Ash", role=KeyRole.CHIEF, scopes={Scope.MEDICINES}
    )
    keys = await list_keys(sg, context=owner)
    assert [await person_display_name(sg, owner, k.holder_person_id) for k in keys] == ["Ash"]
