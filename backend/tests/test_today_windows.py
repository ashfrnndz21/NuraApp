"""The moment of a dose, and the proud number, both said by the backend (W1 review).

The client shows a dose as the one thing to do only while the backend marks it `due_now`,
shows the story's missed-dose lines once its window has passed, and shows the proud number
the backend counted — never one it worked out or kept for itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.keys.scopes import KeyRole, Scope
from app.medicines.dose import Anchor
from app.medicines.service import active_lines, proud_days, record_dose_taken, today
from app.medicines.windows import window_status
from tests.conftest import Deployment
from tests.medicines_support import REGISTRY, add, label, let_in, pa

SGT = timedelta(hours=8)


def test_window_status_by_local_hour() -> None:
    at = lambda hour: datetime(2026, 9, 3, hour, 0, tzinfo=UTC)
    assert window_status(Anchor.BREAKFAST, at(7), taken=False) == (True, False)
    assert window_status(Anchor.BREAKFAST, at(11), taken=False) == (False, True)
    assert window_status(Anchor.BREAKFAST, at(4), taken=False) == (False, False)
    assert window_status(Anchor.DINNER, at(16), taken=False) == (True, False)
    assert window_status(Anchor.DINNER, at(20), taken=False) == (True, False)
    assert window_status(Anchor.BED, at(20), taken=False) == (True, False)
    assert window_status(Anchor.BED, at(23), taken=False) == (True, False)
    # A taken dose is neither due nor missed, whatever the hour.
    assert window_status(Anchor.BREAKFAST, at(11), taken=True) == (False, False)
    assert window_status("lunch", at(12), taken=False) == (True, False)


async def test_todays_slots_say_due_now_and_missed_from_the_window(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """Frozen at 16:00 in Singapore: breakfast has passed, dinner is open, bed is not yet."""
    owner = await pa(sg)
    await add(sg, owner, label("amlodipine", "5 mg", "1 tab BD"))  # breakfast and dinner
    await add(sg, owner, label("metformin", "500 mg", "1 tab OD"))  # breakfast
    slots = await today(sg, context=owner, registry=REGISTRY, language="en")
    by = {(s.line.generic, s.anchor): s for s in slots}
    assert (by["amlodipine", "breakfast"].due_now, by["amlodipine", "breakfast"].missed) == (
        False,
        True,
    )
    assert (by["amlodipine", "dinner"].due_now, by["amlodipine", "dinner"].missed) == (True, False)
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
    assert (lines["amlodipine"].due_now, lines["amlodipine"].missed) == (True, True)
    assert (lines["metformin"].due_now, lines["metformin"].missed) == (False, True)
    assert lines["metformin"].source == by["metformin", "breakfast"].source
    # A tap on the dinner dose: nothing is due any more; the breakfast one stays missed.
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
    # A helper's tap is her help, not his day: a day only she tapped does not count, and her
    # key reads his number, not one of her own.
    helper = await let_in(
        sg, owner, phone="+6592220001", name="Mei", role=KeyRole.HELPER, scopes={Scope.MEDICINES}
    )
    clock.step(timedelta(days=1))
    await record_dose_taken(
        sg, context=helper, line_id=written.line.id, anchor="breakfast", amount=None
    )
    assert (await proud_days(sg, context=owner)).days == 2
    assert (await proud_days(sg, context=helper)).days == 2
    clock.step(timedelta(days=1))
    await record_dose_taken(
        sg, context=owner, line_id=written.line.id, anchor="breakfast", amount=None
    )
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
