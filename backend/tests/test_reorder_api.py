"""The reorder card's two buttons over HTTP (E04-05, #30; PR #140 review).

    POST /profiles/{id}/medicines/{line}/ask-to-order/preview   who would be asked, his words
    POST /profiles/{id}/confirmations                           subject order
    POST /profiles/{id}/medicines/{line}/ask-to-order           "Ask the family to order."
    POST /profiles/{id}/confirmations                           subject count_correction
    POST /profiles/{id}/medicines/{line}/more                   "I have more at home."

Acceptance: the card appears at the threshold (checkpoint 8, `test_medicines`); Ask-to-order
notifies the roster — on his yes to a preview that names who, a task on the family's list for
whoever is on duty, else his chief, and a notice to his chief — and I-have-more writes a count
correction as a fact on his yes. The #140 review adds: no task for another person without a
confirm, one open order task a line a day, the task names him and the medicine, never his
"your", and a high-risk medicine's count rests on a photo of the box or the label.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from httpx import Response
from sqlalchemy import select

from app.clock import FrozenClock
from app.family.models import Task
from app.family.strings import DIGEST
from app.medicines.strings import LANGUAGES, ORDER_TASK
from app.memory.models import ArtifactKind
from app.safety.models import Notice, NoticeKind
from app.safety.not_feeling_well import notice_lines
from app.safety.plain_words import verify
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.test_medicines_api import _add, _artefact, _label, _not_a_photo

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


async def _on_duty(
    deployment: Deployment, chief: dict[str, str], profile_id: str, who: dict[str, str]
) -> None:
    slot = await deployment.client.post(
        f"/profiles/{profile_id}/roster",
        json={
            "person_id": who["person_id"],
            "role": "caregiver",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "from_time": "00:00:00",
            "to_time": "23:59:00",
        },
        headers=bearer(chief["token"]),
    )
    assert slot.status_code == 201, slot.text


async def _notices(deployment: Deployment, profile_id: str) -> list[Notice]:
    async with deployment.sessions() as session:
        found = await session.scalars(
            select(Notice).where(Notice.profile_id == uuid.UUID(profile_id))
        )
        return list(found.all())


async def _task_rows(deployment: Deployment, profile_id: str) -> list[Task]:
    """Every task row on the profile, read past the keys: to prove nothing was written."""
    async with deployment.sessions() as session:
        found = await session.scalars(select(Task).where(Task.profile_id == uuid.UUID(profile_id)))
        return list(found.all())


async def _tasks(deployment: Deployment, who: dict[str, str], profile_id: str) -> list[Any]:
    listed = await deployment.client.get(
        f"/profiles/{profile_id}/tasks", headers=bearer(who["token"])
    )
    assert listed.status_code == 200, listed.text
    tasks: list[Any] = listed.json()
    return tasks


async def _preview(
    deployment: Deployment, who: dict[str, str], profile_id: str, line_id: str, **params: str
) -> Response:
    return await deployment.client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/ask-to-order/preview",
        params=params,
        headers=bearer(who["token"]),
    )


async def _order_yes(
    deployment: Deployment, who: dict[str, str], profile_id: str, line_id: str, person_id: str
) -> Response:
    return await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "order", "line_id": line_id, "person_id": person_id},
        headers=bearer(who["token"]),
    )


async def _ask(
    deployment: Deployment,
    who: dict[str, str],
    profile_id: str,
    line_id: str,
    confirmation_id: str | None,
    **params: str,
) -> Response:
    return await deployment.client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/ask-to-order",
        json=None if confirmation_id is None else {"confirmation_id": confirmation_id},
        params=params,
        headers=bearer(who["token"]),
    )


async def _preview_and_yes(
    deployment: Deployment, who: dict[str, str], profile_id: str, line_id: str, **params: str
) -> Response:
    """The web's three steps: the preview, his yes to the person it names, the ask."""
    shown = await _preview(deployment, who, profile_id, line_id, **params)
    assert shown.status_code == 200, shown.text
    minted = await _order_yes(deployment, who, profile_id, line_id, shown.json()["asked_person_id"])
    assert minted.status_code == 201, minted.text
    return await _ask(
        deployment, who, profile_id, line_id, minted.json()["confirmation_id"], **params
    )


async def test_ask_to_order_previews_then_on_his_yes_gives_the_task_to_whoever_is_on_duty(
    deployment: Deployment, clock: FrozenClock
) -> None:
    client = deployment.client
    pa, profile_id, line_id = await _pa_with_tablets(deployment)
    mei = await _key(deployment, pa, profile_id, MEI, "Mei", "chief", EVERY_PART)
    kit = await _key(deployment, pa, profile_id, KIT, "Kit", "caregiver", ["medicines", "visits"])
    await _on_duty(deployment, mei, profile_id, kit)

    # The card's two buttons are the backend's words on the line at the threshold.
    lines = await client.get(f"/profiles/{profile_id}/medicines", headers=bearer(pa["token"]))
    count = lines.json()[0]["count"]
    assert count["reorder_due"] is True
    assert count["reorder_actions"] == {
        "ask_to_order": "Ask the family to order.",
        "i_have_more": "I have more at home.",
    }

    # The tap shows him who will be asked and for what, and writes nothing.
    shown = await _preview(deployment, pa, profile_id, line_id)
    assert shown.status_code == 200, shown.text
    assert shown.json() == {
        "line_id": line_id,
        "asked_person_id": kit["person_id"],
        "already_asked": False,
        "task_id": None,
        "language": "en",
        "lines": ["Nura will ask Kit to order more of your blood pressure tablet.", "Is that OK?"],
    }
    assert await _task_rows(deployment, profile_id) == []
    assert await _notices(deployment, profile_id) == []

    # His yes, for Kit and this line; then the ask spends it.
    minted = await _order_yes(deployment, pa, profile_id, line_id, kit["person_id"])
    assert minted.status_code == 201, minted.text
    asked = await _ask(deployment, pa, profile_id, line_id, minted.json()["confirmation_id"])
    assert asked.status_code == 201, asked.text
    body = asked.json()
    assert body["asked_person_id"] == kit["person_id"]
    assert body["told_person_ids"] == [mei["person_id"]]
    assert body["already_asked"] is False
    assert body["lines"] == [
        "Nura asked Kit to order more of your blood pressure tablet.",
        "Mei knows now.",
    ]

    # The task is on the family's list for Kit. Its words name Pa, and the medicine as its
    # box names it, chemical name and strength — never "your", which on Kit's list would be
    # hers (review #140, item 11).
    tasks = await _tasks(deployment, mei, profile_id)
    assert [(t["what"], t["assigned_person_id"], t["errand"]) for t in tasks] == [
        ("order more amlodipine 5 mg for Pa", kit["person_id"], "order")
    ]
    mine = await client.get(
        f"/profiles/{profile_id}/tasks", params={"mine": "true"}, headers=bearer(kit["token"])
    )
    assert [(t["task_id"], t["what"]) for t in mine.json()] == [
        (body["task_id"], "order more amlodipine 5 mg for Pa")
    ]

    # The family digest, which he reads too, says it in its own checked words and names no
    # medicine: the chemical name and strength are on the family's list only.
    card = await client.post(
        f"/profiles/{profile_id}/thread",
        json={"card_kind": "task", "task_id": body["task_id"]},
        headers=bearer(mei["token"]),
    )
    assert card.status_code == 201, card.text
    digested = await client.get(
        f"/profiles/{profile_id}/thread/digest",
        params={"since": "2020-01-01T00:00:00+00:00", "language": "en"},
        headers=bearer(mei["token"]),
    )
    assert digested.status_code == 200, digested.text
    said = digested.json()["lines"]
    assert "Kit will order more medicine for Pa." in said
    assert not any("amlodipine" in line for line in said)

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


async def test_no_yes_is_a_refusal_and_no_task(deployment: Deployment, clock: FrozenClock) -> None:
    """Review #140, item 10: nothing is put on another person's list without a confirm."""
    pa, profile_id, line_id = await _pa_with_tablets(deployment)
    await _key(deployment, pa, profile_id, MEI, "Mei", "chief", EVERY_PART)

    # One tap with no yes, as the web used to send it.
    bare = await _ask(deployment, pa, profile_id, line_id, None)
    assert bare.status_code == 400 and bare.json() == {"refusal": "NotAConfirmerHere"}
    # A yes nobody minted.
    made_up = await _ask(deployment, pa, profile_id, line_id, str(uuid.uuid4()))
    assert made_up.status_code == 400 and made_up.json() == {"refusal": "NotAConfirmerHere"}
    # A yes for something else: tablets found at home are not an order.
    other = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "count_correction", "line_id": line_id, "quantity": 20},
        headers=bearer(pa["token"]),
    )
    assert other.status_code == 201, other.text
    wrong = await _ask(deployment, pa, profile_id, line_id, other.json()["confirmation_id"])
    assert wrong.status_code == 400 and wrong.json() == {"refusal": "NotAConfirmerHere"}

    assert await _task_rows(deployment, profile_id) == []
    assert await _notices(deployment, profile_id) == []


async def test_his_yes_binds_to_the_person_and_the_line(
    deployment: Deployment, clock: FrozenClock
) -> None:
    client = deployment.client
    pa, profile_id, amlodipine = await _pa_with_tablets(deployment)
    photo = await _artefact(client, profile_id, pa, "metformin")
    added = await _add(client, profile_id, pa, _label("metformin", "500 mg", "1 tab OD", 5), photo)
    assert added.status_code == 201, added.text
    metformin = added.json()["line_id"]
    mei = await _key(deployment, pa, profile_id, MEI, "Mei", "chief", EVERY_PART)
    kit = await _key(deployment, pa, profile_id, KIT, "Kit", "caregiver", ["medicines", "visits"])

    # A yes for the blood pressure tablet does not order the sugar tablet.
    shown = await _preview(deployment, pa, profile_id, amlodipine)
    assert shown.json()["asked_person_id"] == mei["person_id"]
    minted = await _order_yes(deployment, pa, profile_id, amlodipine, mei["person_id"])
    elsewhere = await _ask(deployment, pa, profile_id, metformin, minted.json()["confirmation_id"])
    assert elsewhere.status_code == 400 and elsewhere.json() == {"refusal": "NotAConfirmerHere"}
    assert await _task_rows(deployment, profile_id) == []

    # The roster moves on after his yes for Mei: the yes does not become a task for Kit.
    await _on_duty(deployment, mei, profile_id, kit)
    moved = await _ask(deployment, pa, profile_id, amlodipine, minted.json()["confirmation_id"])
    assert moved.status_code == 400 and moved.json() == {"refusal": "NotWhatWasConfirmed"}
    assert await _task_rows(deployment, profile_id) == []

    # A yes cannot be minted for anyone but the one the preview names now.
    again = await _preview(deployment, pa, profile_id, amlodipine)
    assert again.json()["asked_person_id"] == kit["person_id"]
    not_named = await _order_yes(deployment, pa, profile_id, amlodipine, mei["person_id"])
    assert not_named.status_code == 400 and not_named.json() == {"refusal": "NotWhatWasConfirmed"}

    # His yes for Kit and the blood pressure tablet: the one task, for exactly those.
    done = await _preview_and_yes(deployment, pa, profile_id, amlodipine)
    assert done.status_code == 201, done.text
    rows = await _task_rows(deployment, profile_id)
    assert [(str(t.assigned_person_id), str(t.medication_line_id)) for t in rows] == [
        (kit["person_id"], amlodipine)
    ]


async def test_two_yeses_the_same_day_give_one_task(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """One open order task a line a day: a second yes answers with the task on the list."""
    pa, profile_id, line_id = await _pa_with_tablets(deployment)
    mei = await _key(deployment, pa, profile_id, MEI, "Mei", "chief", EVERY_PART)

    first = await _preview_and_yes(deployment, pa, profile_id, line_id)
    assert first.status_code == 201, first.text
    task_id = first.json()["task_id"]

    # The preview now says the family was asked, and by whom.
    shown = await _preview(deployment, pa, profile_id, line_id)
    assert shown.json()["already_asked"] is True and shown.json()["task_id"] == task_id
    assert shown.json()["lines"] == ["Nura asked Mei to order more of your blood pressure tablet."]

    # A second yes, his or Mei's own, answers with that task and writes nothing more.
    for who in (pa, mei):
        again = await _preview_and_yes(deployment, who, profile_id, line_id)
        assert again.status_code == 200, again.text
        assert again.json()["task_id"] == task_id and again.json()["already_asked"] is True
        assert again.json()["told_person_ids"] == []
    assert [t["task_id"] for t in await _tasks(deployment, mei, profile_id)] == [task_id]
    assert len(await _notices(deployment, profile_id)) == 1

    # The next day is a new day: a yes then is a new task.
    clock.step(timedelta(days=1))
    tomorrow = await _preview_and_yes(deployment, pa, profile_id, line_id)
    assert tomorrow.status_code == 201, tomorrow.text
    assert tomorrow.json()["task_id"] != task_id
    assert len(await _tasks(deployment, mei, profile_id)) == 2


async def test_with_nobody_on_duty_the_chief_is_asked_and_with_no_chief_nobody_is(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id, line_id = await _pa_with_tablets(deployment)

    # Nobody on duty and no chief: refused by name, before any yes, and nothing is written.
    alone = await _preview(deployment, pa, profile_id, line_id)
    assert alone.status_code == 409 and alone.json() == {"refusal": "NobodyToAsk"}
    tried = await _ask(deployment, pa, profile_id, line_id, None)
    assert tried.status_code == 409 and tried.json() == {"refusal": "NobodyToAsk"}
    assert await _task_rows(deployment, profile_id) == []
    assert await _notices(deployment, profile_id) == []

    # With a chief and no roster, she is the one asked, and told.
    mei = await _key(deployment, pa, profile_id, MEI, "Mei", "chief", EVERY_PART)
    asked = await _preview_and_yes(deployment, pa, profile_id, line_id)
    assert asked.status_code == 201, asked.text
    assert asked.json()["asked_person_id"] == mei["person_id"]
    assert asked.json()["lines"] == ["Nura asked Mei to order more of your blood pressure tablet."]
    assert len(await _notices(deployment, profile_id)) == 1

    # In his language when he reads Malay.
    malay = await _preview(deployment, pa, profile_id, line_id, language="ms")
    assert malay.json()["lines"] == ["Nura minta Mei pesan lagi ubat tekanan darah anda."]


async def test_the_one_asked_is_one_whose_key_opens_his_medicines(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """The task names his medicine by its chemical name and strength, so the one asked to buy
    it is one whose key opens the medicines: someone on duty whose key does not is passed
    over, and the chief is asked."""
    pa, profile_id, line_id = await _pa_with_tablets(deployment)
    mei = await _key(deployment, pa, profile_id, MEI, "Mei", "chief", EVERY_PART)
    kit = await _key(deployment, pa, profile_id, KIT, "Kit", "caregiver", ["visits"])
    await _on_duty(deployment, mei, profile_id, kit)
    shown = await _preview(deployment, pa, profile_id, line_id)
    assert shown.json()["asked_person_id"] == mei["person_id"]
    done = await _preview_and_yes(deployment, pa, profile_id, line_id)
    assert done.status_code == 201, done.text
    tasks = await _tasks(deployment, mei, profile_id)
    assert [(t["assigned_person_id"], t["what"]) for t in tasks] == [
        (mei["person_id"], "order more amlodipine 5 mg for Pa")
    ]


async def test_the_preview_in_malay_and_chinese_names_who_and_what(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id, line_id = await _pa_with_tablets(deployment)
    await _key(deployment, pa, profile_id, MEI, "Mei", "chief", EVERY_PART)
    malay = await _preview(deployment, pa, profile_id, line_id, language="ms")
    assert malay.json()["lines"] == [
        "Nura akan minta Mei pesan lagi ubat tekanan darah anda.",
        "Boleh begitu?",
    ]
    chinese = await _preview(deployment, pa, profile_id, line_id, language="zh")
    assert chinese.json()["lines"] == ["Nura会请Mei再订您的血压药。", "这样可以吗？"]


def test_every_order_task_names_him_and_the_medicine_and_passes_plain_words() -> None:
    """The family's label, in every language, names him and the medicine as its box does, and
    never says "your". It is the family's words, not his: what reaches him about it — the
    digest — is Nura's own checked sentence (`DIGEST` order lines), which passes."""
    for language in LANGUAGES:
        label = ORDER_TASK[language].format(patient="Pa", medicine="amlodipine 5 mg")
        for key in ("order_open", "order_done"):
            line = DIGEST[language][key]
            failures = [f for f in verify(line, language, "line") if f.severity == "fail"]
            assert failures == [], (line, failures)
        assert "Pa" in label and "amlodipine 5 mg" in label
        assert not any(word in label.lower() for word in ("your", "anda", "您"))


async def test_a_helper_can_neither_ask_the_family_nor_add_to_the_count(
    deployment: Deployment, clock: FrozenClock
) -> None:
    pa, profile_id, line_id = await _pa_with_tablets(deployment)
    mei = await _key(deployment, pa, profile_id, MEI, "Mei", "chief", EVERY_PART)
    siti = await _key(deployment, pa, profile_id, SITI, "Siti", "helper", ["medicines"])
    shown = await _preview(deployment, siti, profile_id, line_id)
    assert shown.status_code == 403, shown.text
    minted = await _order_yes(deployment, siti, profile_id, line_id, mei["person_id"])
    assert minted.status_code == 403, minted.text
    asked = await _ask(deployment, siti, profile_id, line_id, None)
    assert asked.status_code == 403, asked.text
    counted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "count_correction", "line_id": line_id, "quantity": 20},
        headers=bearer(siti["token"]),
    )
    assert counted.status_code == 403 and counted.json() == {"refusal": "NotTheirsToChange"}


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
    assert body["artifact_id"] is None
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


async def test_more_of_a_high_risk_medicine_rests_on_a_photo_of_the_box_or_the_label(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """Review #140, note 3: a typed count that is too high would put off a warfarin reorder,
    so a high-risk medicine's count needs a photo, the same rule as its dose."""
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    label_photo = await _artefact(client, profile_id, pa, "warfarin")
    added = await _add(
        client, profile_id, pa, _label("warfarin", "3 mg", "1 tab OD", 10), label_photo
    )
    assert added.status_code == 201, added.text
    line_id = added.json()["line_id"]
    refusal = {"refusal": "HighRiskNeedsLabelPhoto", "drug_class": "anticoagulant"}

    # A typed number alone: refused before a yes is minted, and at the write.
    typed = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "count_correction", "line_id": line_id, "quantity": 14},
        headers=his,
    )
    assert typed.status_code == 400 and typed.json() == refusal
    bare = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/more",
        json={"quantity": 14, "confirmation_id": str(uuid.uuid4())},
        headers=his,
    )
    assert bare.status_code == 400 and bare.json() == refusal

    # A paper that is not a photo is not a photo of the box.
    paper = await _not_a_photo(deployment, profile_id, pa, ArtifactKind.PDF)
    from_paper = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "count_correction", "line_id": line_id, "quantity": 14, "artifact_id": paper},
        headers=his,
    )
    assert from_paper.status_code == 400 and from_paper.json() == refusal
    listed = await client.get(f"/profiles/{profile_id}/medicines", headers=his)
    assert listed.json()[0]["count"]["remaining"] == 10

    # With a photo of the box: his yes binds to the number and the photo.
    box = await _artefact(client, profile_id, pa, "warfarin-box")
    minted = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "count_correction", "line_id": line_id, "quantity": 14, "artifact_id": box},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    yes = minted.json()["confirmation_id"]
    another = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/more",
        json={"quantity": 14, "confirmation_id": yes, "artifact_id": label_photo},
        headers=his,
    )
    assert another.status_code == 400 and another.json() == {"refusal": "NotWhatWasConfirmed"}
    more = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/more",
        json={"quantity": 14, "confirmation_id": yes, "artifact_id": box},
        headers=his,
    )
    assert more.status_code == 201, more.text
    assert more.json()["count"]["remaining"] == 24 and more.json()["artifact_id"] == box

    # The fact and the supply rest on the photo, and the line still on its label photo.
    facts = await client.get(
        f"/profiles/{profile_id}/facts", params={"subject": "medication"}, headers=his
    )
    counted = [f for f in facts.json() if f["attribute"] == "count:warfarin"]
    assert [(f["artifact_id"], f["event_id"]) for f in counted] == [
        (box, more.json()["event_id"])
    ]
    listed = await client.get(f"/profiles/{profile_id}/medicines", headers=his)
    assert listed.json()[0]["source_artifact_id"] == label_photo


async def test_a_typed_count_stays_his_word_for_a_medicine_that_is_not_high_risk(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """The photo rule is for the five classes only: his word is enough for the rest, and a
    photo he adds anyway is where the count rests."""
    client = deployment.client
    pa, profile_id, line_id = await _pa_with_tablets(deployment)
    his = bearer(pa["token"])
    box = await _artefact(client, profile_id, pa, "amlodipine-box")
    minted = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "count_correction", "line_id": line_id, "quantity": 10, "artifact_id": box},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    # A yes with the photo is not a yes without it.
    without = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/more",
        json={"quantity": 10, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert without.status_code == 400 and without.json() == {"refusal": "NotWhatWasConfirmed"}
    more = await client.post(
        f"/profiles/{profile_id}/medicines/{line_id}/more",
        json={"quantity": 10, "confirmation_id": minted.json()["confirmation_id"], "artifact_id": box},
        headers=his,
    )
    assert more.status_code == 201, more.text
    assert more.json()["artifact_id"] == box and more.json()["count"]["remaining"] == 15
