"""The reorder card's two buttons over HTTP (E04-05, #30).

    POST /profiles/{id}/medicines/{line}/ask-to-order   "Ask the family to order."
    POST /profiles/{id}/confirmations                   subject count_correction
    POST /profiles/{id}/medicines/{line}/more           "I have more at home."

Acceptance: the card appears at the threshold (checkpoint 8, `test_medicines`); Ask-to-order
notifies the roster — a task on the family's list for whoever is on duty, else his chief, and
a notice to his chief — and I-have-more writes a count correction as a fact on his yes.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.clock import FrozenClock
from app.safety.models import Notice, NoticeKind
from app.safety.not_feeling_well import notice_lines
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.test_medicines_api import _add, _artefact, _label

PA = "+6591120001"
MEI = "+6591120002"
KIT = "+6591120003"
SITI = "+6591120004"
EVERY_PART = [
    "medicines",
    "visits",
    "readings",
    "records",
    "notes",
    "money",
    "family",
    "emergency",
    "ask",
    "send",
]


async def _pa_with_tablets(deployment: Deployment, quantity: int = 5) -> tuple[dict[str, str], str, str]:
    """Pa, in English, with five blood pressure tablets: the count is at the threshold."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    photo = await _artefact(deployment.client, profile_id, pa, "reorder")
    added = await _add(
        deployment.client, profile_id, pa, _label("amlodipine", "5 mg", "1 tab OD", quantity), photo
    )
    assert added.status_code == 201, added.text
    return pa, profile_id, added.json()["line_id"]


async def _key(
    deployment: Deployment,
    pa: dict[str, str],
    profile_id: str,
    phone: str,
    name: str,
    role: str,
    parts: list[str],
) -> dict[str, str]:
    holder = await register_by_phone(deployment, phone, name)
    await let_in(deployment, pa, profile_id, phone, parts, None, holder_display_name=name)
    cut = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_person_id": holder["person_id"], "role": role, "scopes": parts},
        headers=bearer(pa["token"]),
    )
    assert cut.status_code == 201, cut.text
    return holder


async def _notices(deployment: Deployment, profile_id: str) -> list[Notice]:
    async with deployment.sessions() as session:
        found = await session.scalars(
            select(Notice).where(Notice.profile_id == uuid.UUID(profile_id))
        )
        return list(found.all())


async def _tasks(deployment: Deployment, who: dict[str, str], profile_id: str) -> list[Any]:
    listed = await deployment.client.get(
        f"/profiles/{profile_id}/tasks", headers=bearer(who["token"])
    )
    assert listed.status_code == 200, listed.text
    tasks: list[Any] = listed.json()
    return tasks


async def test_ask_to_order_gives_the_task_to_whoever_is_on_duty_and_tells_the_chief(
    deployment: Deployment, clock: FrozenClock
) -> None:
    client = deployment.client
    pa, profile_id, line_id = await _pa_with_tablets(deployment)
    mei = await _key(deployment, pa, profile_id, MEI, "Mei", "chief", EVERY_PART)
    kit = await _key(deployment, pa, profile_id, KIT, "Kit", "caregiver", ["medicines", "visits"])
    slot = await client.post(
        f"/profiles/{profile_id}/roster",
        json={
            "person_id": kit["person_id"],
            "role": "caregiver",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "from_time": "00:00:00",
            "to_time": "23:59:00",
        },
        headers=bearer(mei["token"]),
    )
    assert slot.status_code == 201, slot.text

    # The card's two buttons are the backend's words on the line at the threshold.
    lines = await client.get(f"/profiles/{profile_id}/medicines", headers=bearer(pa["token"]))
    count = lines.json()[0]["count"]
    assert count["reorder_due"] is True
    assert count["reorder_actions"] == {
        "ask_to_order": "Ask the family to order.",
        "i_have_more": "I have more at home.",
    }

    asked = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/ask-to-order",
        headers=bearer(pa["token"]),
    )
    assert asked.status_code == 201, asked.text
    body = asked.json()
    assert body["asked_person_id"] == kit["person_id"]
    assert body["told_person_ids"] == [mei["person_id"]]
    assert body["lines"] == [
        "Nura asked Kit to order more of your blood pressure tablet.",
        "Mei knows now.",
    ]

    # The task is on the family's list, in his words, for Kit; Kit reads it as hers.
    tasks = await _tasks(deployment, mei, profile_id)
    assert [(t["what"], t["assigned_person_id"]) for t in tasks] == [
        ("order more of your blood pressure tablet", kit["person_id"])
    ]
    mine = await client.get(
        f"/profiles/{profile_id}/tasks", params={"mine": "true"}, headers=bearer(kit["token"])
    )
    assert [t["task_id"] for t in mine.json()] == [body["task_id"]]

    # The chief is told: one notice, a reorder notice, never read as "not feeling well".
    notices = await _notices(deployment, profile_id)
    assert [(n.kind, str(n.to_person_id)) for n in notices] == [
        (NoticeKind.REORDER, mei["person_id"])
    ]
    assert notices[0].slots == {"task_id": body["task_id"], "line_id": line_id}
    assert notice_lines(notices[0], patient="Pa") == [
        "Pa asked the family to order more medicine.",
        "It is on the family's list.",
    ]
    assert notice_lines(notices[0], patient="Pa", language="ms") == [
        "Pa minta keluarga pesan lagi ubat.",
        "Ia ada dalam senarai keluarga.",
    ]


async def test_with_nobody_on_duty_the_chief_is_asked_and_with_no_chief_nobody_is(
    deployment: Deployment, clock: FrozenClock
) -> None:
    client = deployment.client
    pa, profile_id, line_id = await _pa_with_tablets(deployment)

    # Nobody on duty and no chief: refused by name, and nothing is written.
    alone = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/ask-to-order", headers=bearer(pa["token"])
    )
    assert alone.status_code == 409 and alone.json() == {"refusal": "NobodyToAsk"}
    assert await _notices(deployment, profile_id) == []

    # With a chief and no roster, she is the one asked, and told.
    mei = await _key(deployment, pa, profile_id, MEI, "Mei", "chief", EVERY_PART)
    assert await _tasks(deployment, mei, profile_id) == []
    asked = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/ask-to-order", headers=bearer(pa["token"])
    )
    assert asked.status_code == 201, asked.text
    assert asked.json()["asked_person_id"] == mei["person_id"]
    assert asked.json()["lines"] == ["Nura asked Mei to order more of your blood pressure tablet."]
    assert len(await _notices(deployment, profile_id)) == 1

    # Mei tapping it herself is not told about her own tap.
    herself = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/ask-to-order", headers=bearer(mei["token"])
    )
    assert herself.status_code == 201, herself.text
    assert herself.json()["told_person_ids"] == []
    assert len(await _notices(deployment, profile_id)) == 1
    assert len(await _tasks(deployment, mei, profile_id)) == 2

    # In his language when he reads Malay.
    malay = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/ask-to-order",
        params={"language": "ms"},
        headers=bearer(pa["token"]),
    )
    assert malay.json()["lines"] == ["Nura minta Mei pesan lagi ubat tekanan darah anda."]


async def test_a_helper_can_neither_ask_the_family_nor_add_to_the_count(
    deployment: Deployment, clock: FrozenClock
) -> None:
    client = deployment.client
    pa, profile_id, line_id = await _pa_with_tablets(deployment)
    siti = await _key(deployment, pa, profile_id, SITI, "Siti", "helper", ["medicines"])
    asked = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/ask-to-order", headers=bearer(siti["token"])
    )
    assert asked.status_code == 403, asked.text
    minted = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "count_correction", "line_id": line_id, "quantity": 20},
        headers=bearer(siti["token"]),
    )
    assert minted.status_code == 403 and minted.json() == {"refusal": "NotTheirsToChange"}


async def test_i_have_more_adds_to_the_count_on_his_yes_for_exactly_that_number(
    deployment: Deployment, clock: FrozenClock
) -> None:
    client = deployment.client
    pa, profile_id, line_id = await _pa_with_tablets(deployment)
    his = bearer(pa["token"])

    minted = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "count_correction", "line_id": line_id, "quantity": 20},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    yes = minted.json()["confirmation_id"]

    # A yes for 20 is not a yes for 30: refused, and the count does not move.
    other = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/more",
        json={"quantity": 30, "confirmation_id": yes},
        headers=his,
    )
    assert other.status_code == 400 and other.json() == {"refusal": "NotWhatWasConfirmed"}

    more = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/more",
        json={"quantity": 20, "confirmation_id": yes},
        headers=his,
    )
    assert more.status_code == 201, more.text
    body = more.json()
    assert body["quantity"] == 20 and body["count"]["remaining"] == 25
    assert body["count"]["lines"][0] == "You have 25 tablets of your blood pressure tablet left."
    assert body["count"]["reorder_due"] is False

    # The same yes is spent once.
    again = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/more",
        json={"quantity": 20, "confirmation_id": yes},
        headers=his,
    )
    assert again.status_code == 400, again.text

    # The count on the list moved, and the fact rests on the moment he said so.
    listed = await client.get(f"/profiles/{profile_id}/medicines", headers=his)
    assert listed.json()[0]["count"]["remaining"] == 25
    facts = await client.get(
        f"/profiles/{profile_id}/facts", params={"subject": "medication"}, headers=his
    )
    counted = [f for f in facts.json() if f["attribute"] == "count:amlodipine"]
    assert len(counted) == 1 and counted[0]["fact_id"] == body["fact_id"]
    assert counted[0]["event_id"] == body["event_id"] and counted[0]["artifact_id"] is None
    assert counted[0]["value"]["quantity"] == 20

    # Nothing but a whole number more than none.
    zero = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "count_correction", "line_id": line_id, "quantity": 0},
        headers=his,
    )
    assert zero.status_code == 422


async def test_more_of_a_high_risk_medicine_is_a_count_not_a_dose(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """Warfarin is saved from its label photo; tablets of it found at home change no dose, so
    the count moves on his word, and the line still rests on the photo."""
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    photo = await _artefact(client, profile_id, pa, "warfarin")
    added = await _add(client, profile_id, pa, _label("warfarin", "3 mg", "1 tab OD", 10), photo)
    assert added.status_code == 201, added.text
    line_id = added.json()["line_id"]
    minted = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "count_correction", "line_id": line_id, "quantity": 14},
        headers=his,
    )
    more = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/more",
        json={"quantity": 14, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert more.status_code == 201, more.text
    assert more.json()["count"]["remaining"] == 24
    listed = await client.get(f"/profiles/{profile_id}/medicines", headers=his)
    assert listed.json()[0]["source_artifact_id"] == photo
