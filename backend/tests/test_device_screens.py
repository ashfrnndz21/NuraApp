"""E02-08: a reading by photo of a machine's screen — a blood pressure machine, a glucometer.

Acceptance line: value, unit and time captured from the screen photo; no typing. The card
shows the numbers with their units, the kind of machine and the time on its screen, each
with its confidence; one yes writes one READING event at that time and the facts of the
reading in the shape a typed reading takes, and State recomputes. A photo that is not a
machine's screen is an open card with no fields that says so.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.channels.strings import NOT_A_MACHINE_SCREEN
from app.clock import FrozenClock
from app.drafts import DecidedField
from app.ingestion.readings import NotAWholeReading, reading_from
from app.regions import REGION_TZ, Region
from tests.api import bearer, own_profile, register_by_phone
from tests.capture_support import confirm, decide, photo, refusals
from tests.conftest import Deployment
from tests.paper import BP_CUFF, GLUCOMETER, LIPID_PANEL

PA = "+6591200001"
LATER_THAT_DAY = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)


async def _pa(deployment: Deployment) -> tuple[dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, "Pa")
    return pa, await own_profile(deployment, pa, language="en")


async def _screen(deployment: Deployment, pa: dict[str, str], profile_id: str, label: str) -> dict:
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/readings/photo", json=photo(label), headers=bearer(pa["token"])
    )
    assert posted.status_code == 201, posted.text
    card: dict = posted.json()
    return card


async def test_a_blood_pressure_machine_is_read_off_its_screen_with_no_typing(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(LATER_THAT_DAY)
    pa, profile_id = await _pa(deployment)
    his = bearer(pa["token"])
    card = await _screen(deployment, pa, profile_id, BP_CUFF)
    assert card["document_kind"] == "device_screen" and card["asked_as"] == "device_screen"
    read = {
        (f["subject"], f["attribute"]): (f["value"], f["unit"], f["confidence"])
        for f in card["fields"]
    }
    assert read == {
        ("device", "kind"): ("blood_pressure_monitor", None, 0.9),
        ("blood_pressure", "systolic"): (138, "mmHg", 0.97),
        ("blood_pressure", "diastolic"): (84, "mmHg", 0.95),
        ("heart_rate", "pulse"): (72, "/min", 0.93),
        ("reading", "taken_at"): ("2026-09-14T07:42", None, 0.86),
    }
    assert not any(f["needs_confirm"] for f in card["fields"])

    before = (await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)).json()
    done = await confirm(deployment, pa["token"], profile_id, card, decide(card))
    assert done.status_code == 200, done.text
    result = done.json()
    facts = {f["subject"]: f for f in result["facts"]}
    assert set(facts) == {"blood_pressure", "heart_rate"}
    bp = facts["blood_pressure"]
    assert (bp["attribute"], bp["value"], bp["unit"]) == (
        "reading",
        {"systolic": 138, "diastolic": 84},
        "mmHg",
    )
    assert facts["heart_rate"]["value"] == {"pulse": 72} and facts["heart_rate"]["unit"] == "/min"
    for fact in facts.values():
        assert fact["event_id"] == result["event_id"] is not None
        assert fact["artifact_id"] == card["artifact_id"]
        assert fact["valid_from"].startswith("2026-09-13T23:42:00")  # 7.42 on his wall clock
        assert fact["confirmed_by_person_id"] == pa["person_id"]
    fields = {f["attribute"]: f for f in result["card"]["fields"]}
    assert fields["systolic"]["fact_id"] == fields["diastolic"]["fact_id"] == bp["fact_id"]
    assert fields["kind"]["fact_id"] is None and fields["kind"]["state"] == "confirmed"

    after = (await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)).json()
    assert after["sequence"] > before["sequence"]
    assert after["trigger"]["kind"] == "new_fact"
    assert after["trigger"]["fact_id"] in {f["fact_id"] for f in result["facts"]}
    folded = after["dimensions"]["clinical"]["facts"]["blood_pressure"]["reading"]
    assert folded["value"] == {"systolic": 138, "diastolic": 84}

    # The same shape as a typed reading.
    typed = await deployment.client.post(
        f"/profiles/{profile_id}/readings", json={"systolic": 142, "diastolic": 88}, headers=his
    )
    assert typed.status_code == 201
    both = await deployment.client.get(
        f"/profiles/{profile_id}/facts", params={"subject": "blood_pressure"}, headers=his
    )
    shapes = {(f["attribute"], f["unit"], tuple(sorted(f["value"]))) for f in both.json()}
    assert shapes == {("reading", "mmHg", ("diastolic", "systolic"))}
    assert len(both.json()) == 2


async def test_a_glucometer_is_read_off_its_screen(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(LATER_THAT_DAY)
    pa, profile_id = await _pa(deployment)
    card = await _screen(deployment, pa, profile_id, GLUCOMETER)
    done = await confirm(deployment, pa["token"], profile_id, card, decide(card))
    assert done.status_code == 200, done.text
    [sugar] = done.json()["facts"]
    assert (sugar["subject"], sugar["attribute"], sugar["value"], sugar["unit"]) == (
        "blood_sugar",
        "reading",
        {"glucose": 6.8},
        "mmol/L",
    )
    assert sugar["valid_from"].startswith("2026-09-13T22:55:00")


async def test_a_photo_that_is_not_a_machine_screen_is_an_open_card_that_says_so(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    card = await _screen(deployment, pa, profile_id, LIPID_PANEL)
    assert card["asked_as"] == "device_screen" and card["document_kind"] == "lab_report"
    assert card["fields"] == [] and card["confirmed_at"] is None
    assert card["notice"] == list(NOT_A_MACHINE_SCREEN)
    assert card["notice"] == ["This does not look like the screen of a machine."]


async def test_half_a_blood_pressure_is_not_a_reading_and_the_refusal_is_on_the_trail(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(LATER_THAT_DAY)
    pa, profile_id = await _pa(deployment)
    card = await _screen(deployment, pa, profile_id, BP_CUFF)
    refused = await confirm(
        deployment, pa["token"], profile_id, card, decide(card, reject={"diastolic"})
    )
    assert refused.status_code == 400 and refused.json() == {"refusal": "NotAWholeReading"}
    assert "NotAWholeReading" in await refusals(deployment, pa, profile_id)
    left = await deployment.client.get(f"/profiles/{profile_id}/facts", headers=bearer(pa["token"]))
    assert left.json() == []
    open_card = await deployment.client.get(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}", headers=bearer(pa["token"])
    )
    assert open_card.json()["confirmed_at"] is None


async def test_a_time_on_the_screen_later_than_now_is_refused_and_rejecting_it_uses_the_photos(
    deployment: Deployment, clock: FrozenClock
) -> None:
    # The frozen clock stands at 3 September; the screen says 14 September.
    pa, profile_id = await _pa(deployment)
    card = await _screen(deployment, pa, profile_id, BP_CUFF)
    refused = await confirm(deployment, pa["token"], profile_id, card, decide(card))
    assert refused.status_code == 400 and refused.json() == {"refusal": "NotAWholeReading"}
    clock.set(datetime(2026, 9, 3, 9, 0, tzinfo=UTC))
    card = await _screen(deployment, pa, profile_id, BP_CUFF)
    body = {**photo(BP_CUFF, at="2026-09-03T08:30:00Z")}
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/readings/photo", json=body, headers=bearer(pa["token"])
    )
    card = posted.json()
    done = await confirm(
        deployment, pa["token"], profile_id, card, decide(card, reject={"taken_at"})
    )
    assert done.status_code == 200, done.text
    assert all(f["valid_from"].startswith("2026-09-03T08:30:00") for f in done.json()["facts"])


def _field(
    subject: str, attribute: str, value: object, decision: str = "confirmed"
) -> DecidedField:
    return DecidedField(uuid.uuid4(), subject, attribute, value, None, decision)


def test_a_reading_is_whole_or_refused() -> None:
    tz = REGION_TZ[Region.SG]
    now = LATER_THAT_DAY
    whole = reading_from(
        [
            _field("blood_pressure", "systolic", 138),
            _field("blood_pressure", "diastolic", 84),
            _field("weight", "kg", 68.5),
            _field("device", "kind", "blood_pressure_monitor"),
        ],
        tz=tz,
        now=now,
    )
    assert whole.label == "blood pressure" and whole.taken_at is None
    assert [f.value for f in whole.facts] == [{"systolic": 138, "diastolic": 84}, {"kg": 68.5}]
    nothing = reading_from([_field("blood_pressure", "systolic", 138, "rejected")], tz=tz, now=now)
    assert nothing.facts == ()
    for bad in (
        [_field("blood_pressure", "systolic", 138)],
        [_field("blood_pressure", "systolic", "138"), _field("blood_pressure", "diastolic", 84)],
        [_field("blood_pressure", "systolic", 400), _field("blood_pressure", "diastolic", 84)],
        [_field("heart_rate", "pulse", True)],
        [_field("reading", "taken_at", "yesterday morning")],
    ):
        with pytest.raises(NotAWholeReading):
            reading_from(bad, tz=tz, now=now)
