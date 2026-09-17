"""E12 over HTTP: the family routes, each yes minted at `POST /profiles/{id}/confirmations`,
every refusal answered by name and written into the trail."""

from __future__ import annotations

import base64
from datetime import timedelta

from app.clock import FrozenClock
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.family_support import MONDAY

PA, MEI, SITI = "+6591110001", "+6592220002", "+6597770004"
HELPER = ["medicines", "emergency", "send"]


async def _household(
    deployment: Deployment,
) -> tuple[dict[str, str], dict[str, str], dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, "Pa", "ms")
    mei = await register_by_phone(deployment, MEI, "Mei", "en")
    siti = await register_by_phone(deployment, SITI, "Siti", "ms")
    profile_id = await own_profile(deployment, pa, display_name="Pa", language="ms")
    everything = [
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
    await let_in(deployment, pa, profile_id, MEI, everything, "daughter", role="chief")
    await let_in(deployment, pa, profile_id, SITI, HELPER, "helper", role="helper")
    cut = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_person_id": mei["person_id"], "role": "chief"},
        headers=bearer(pa["token"]),
    )
    assert cut.status_code == 201, cut.text
    return pa, mei, siti, profile_id


async def _yes(deployment: Deployment, who: dict[str, str], profile_id: str, body: dict) -> str:  # type: ignore[type-arg]
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations", json=body, headers=bearer(who["token"])
    )
    assert minted.status_code == 201, minted.text
    confirmation_id: str = minted.json()["confirmation_id"]
    return confirmation_id


async def _refusals(deployment: Deployment, pa: dict[str, str], profile_id: str) -> set[str]:
    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", headers=bearer(pa["token"]), params={"limit": 500}
    )
    assert trail.status_code == 200
    return {row["refused_because"] for row in trail.json() if row["outcome"] == "refused"}


async def test_grants_only_me_roster_thread_pushes_and_documents_over_http(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    client = deployment.client
    pa, mei, siti, profile_id = await _household(deployment)

    # --- E12-01: Mei cuts Siti a helper key, narrows it, and cannot widen it.
    cut = await client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_person_id": siti["person_id"], "role": "helper"},
        headers=bearer(mei["token"]),
    )
    assert cut.status_code == 201, cut.text
    key_id = cut.json()["key_id"]
    helpers = await client.get(f"/profiles/{profile_id}/helpers", headers=bearer(mei["token"]))
    assert helpers.status_code == 200 and helpers.json()["helpers"][0]["lines"][0] == (
        "Siti ialah pembantu anda."
    )
    yes = await _yes(
        deployment,
        mei,
        profile_id,
        {"subject": "key_change", "key_id": key_id, "scopes": ["medicines"]},
    )
    narrowed = await client.put(
        f"/profiles/{profile_id}/keys/{key_id}",
        json={"scopes": ["medicines"], "confirmation_id": yes},
        headers=bearer(mei["token"]),
    )
    assert narrowed.status_code == 200, narrowed.text
    assert narrowed.json()["scopes"] == ["medicines", "profile"]
    wider = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "key_change", "key_id": key_id, "scopes": ["medicines", "readings"]},
        headers=bearer(mei["token"]),
    )
    assert wider.status_code == 403 and wider.json() == {"refusal": "WouldWiden"}
    roles = await client.get("/family/roles", params={"name": "Siti"}, headers=bearer(mei["token"]))
    assert roles.status_code == 200 and len(roles.json()) == 6

    # --- E12-04: Pa marks his notes only me; Mei's read is refused and on his trail in words.
    note = await client.post(
        f"/profiles/{profile_id}/notes",
        json={"text": "I did not tell the children about the fall."},
        headers=bearer(pa["token"]),
    )
    assert note.status_code == 201
    yes = await _yes(deployment, pa, profile_id, {"subject": "only_me", "scope": "notes"})
    marked = await client.post(
        f"/profiles/{profile_id}/privacy",
        json={"scope": "notes", "confirmation_id": yes},
        headers=bearer(pa["token"]),
    )
    assert marked.status_code == 201, marked.text
    refused = await client.get(f"/profiles/{profile_id}/notes", headers=bearer(mei["token"]))
    assert refused.status_code == 403 and refused.json() == {
        "refusal": "OutOfScope",
        "scope": "notes",
    }
    assert "fall" not in refused.text
    trail = await client.get(
        f"/profiles/{profile_id}/trail", params={"language": "en"}, headers=bearer(pa["token"])
    )
    assert trail.status_code == 200, trail.text
    days = trail.json()
    assert days[0]["day_words"] == "Monday 14 September"
    sentences = [line["sentences"] for day in days for line in day["lines"]]
    assert [
        "Mei asked to see your private notes on Monday 14 September.",
        "Only you can.",
    ] in sentences
    not_his = await client.get(f"/profiles/{profile_id}/trail", headers=bearer(siti["token"]))
    assert not_his.status_code == 403 and not_his.json()["refusal"] == "NotTheirsToRead"

    # --- E12-03: the roster, and a task done by Siti alone.
    for person, role, days_on in ((mei, "chief", [0, 1, 2, 3, 4]),):
        slot = await client.post(
            f"/profiles/{profile_id}/roster",
            json={
                "person_id": person["person_id"],
                "role": role,
                "weekdays": days_on,
                "from_time": "08:00:00",
                "to_time": "20:00:00",
            },
            headers=bearer(mei["token"]),
        )
        assert slot.status_code == 201, slot.text
    on_duty = await client.get(
        f"/profiles/{profile_id}/roster/on-duty", headers=bearer(mei["token"])
    )
    assert [d["person_id"] for d in on_duty.json()] == [mei["person_id"]]
    task = await client.post(
        f"/profiles/{profile_id}/tasks",
        json={"what": "buy the water pill", "assigned_person_id": siti["person_id"]},
        headers=bearer(mei["token"]),
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["task_id"]
    mine = await client.get(
        f"/profiles/{profile_id}/tasks", params={"mine": "true"}, headers=bearer(siti["token"])
    )
    assert mine.status_code == 200 and [t["task_id"] for t in mine.json()] == [task_id]
    not_hers = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "task_done", "task_id": task_id},
        headers=bearer(mei["token"]),
    )
    assert not_hers.status_code == 403 and not_hers.json() == {"refusal": "NotTheDoer"}
    yes = await _yes(deployment, siti, profile_id, {"subject": "task_done", "task_id": task_id})
    done = await client.post(
        f"/profiles/{profile_id}/tasks/{task_id}/done",
        json={"confirmation_id": yes},
        headers=bearer(siti["token"]),
    )
    assert done.status_code == 200 and done.json()["done_by_person_id"] == siti["person_id"]

    # --- E12-02: a message and a card interleave; the digest reads back in whole sentences.
    reading = await client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 138, "diastolic": 84},
        headers=bearer(pa["token"]),
    )
    assert reading.status_code == 201
    posted = await client.post(
        f"/profiles/{profile_id}/thread",
        json={"text": "Pa slept well, I will come by at 6."},
        headers=bearer(mei["token"]),
    )
    assert posted.status_code == 201, posted.text
    clock.step(timedelta(minutes=1))
    card = await client.post(
        f"/profiles/{profile_id}/thread",
        json={"card_kind": "reading"},
        headers=bearer(mei["token"]),
    )
    assert card.status_code == 201, card.text
    page = await client.get(f"/profiles/{profile_id}/thread", headers=bearer(mei["token"]))
    assert [e["card_kind"] for e in page.json()["entries"]] == ["reading", None]
    digest = await client.get(
        f"/profiles/{profile_id}/thread/digest",
        params={"since": (MONDAY - timedelta(days=1)).isoformat(), "language": "en"},
        headers=bearer(mei["token"]),
    )
    assert digest.status_code == 200, digest.text
    assert digest.json()["headline"] == "Pa on Monday 14 September."
    assert "It was 138 over 84." in digest.json()["lines"]
    helper_thread = await client.get(
        f"/profiles/{profile_id}/thread", headers=bearer(siti["token"])
    )
    assert helper_thread.status_code == 403

    # --- E12-06: a push previewed in Malay, refused in red words, scheduled on a yes.
    compose = {"template_id": "pickup", "slots": {"who": "Mei", "when": "pukul 9"}}
    preview = await client.post(
        f"/profiles/{profile_id}/pushes/preview", json=compose, headers=bearer(mei["token"])
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["lines"] == [
        "Mei akan ambil anda pada pukul 9.",
        "Bawa buku tekanan darah anda.",
    ]
    red = await client.post(
        f"/profiles/{profile_id}/pushes/preview",
        json={"memo_lines": ["You missed your walk."], "language": "en"},
        headers=bearer(mei["token"]),
    )
    assert red.status_code == 400 and red.json()["refusal"] == "NotPlainWords"
    assert red.json()["findings"]
    when = {
        "send_at": (MONDAY + timedelta(hours=8)).isoformat(),
        "channel": "whatsapp",
        "expires_at": (MONDAY + timedelta(hours=12)).isoformat(),
    }
    yes = await _yes(deployment, mei, profile_id, {"subject": "push", **compose, **when})
    scheduled = await client.post(
        f"/profiles/{profile_id}/pushes",
        json={**compose, **when, "confirmation_id": yes},
        headers=bearer(mei["token"]),
    )
    assert scheduled.status_code == 201, scheduled.text
    assert scheduled.json()["lines"] == preview.json()["lines"]
    assert scheduled.json()["state_id"]
    listed = await client.get(f"/profiles/{profile_id}/pushes", headers=bearer(mei["token"]))
    assert [p["push_id"] for p in listed.json()] == [scheduled.json()["push_id"]]

    # --- E12-09: the LPA, uploaded and tagged, kept by reference.
    uploaded = await client.post(
        f"/profiles/{profile_id}/documents",
        json={
            "data": base64.b64encode(b"%PDF-1.4 placeholder").decode(),
            "content_type": "application/pdf",
            "captured_at": "2026-09-01T09:00:00Z",
            "tag": "lpa",
        },
        headers=bearer(mei["token"]),
    )
    assert uploaded.status_code == 201, uploaded.text
    assert [d["tag"] for d in uploaded.json()] == ["lpa"]
    assert uploaded.json()[0]["kind"] == "pdf" and uploaded.json()[0]["backs"] == []
    not_hers = await client.get(f"/profiles/{profile_id}/documents", headers=bearer(siti["token"]))
    assert not_hers.status_code == 403

    # --- Every refusal above is on Pa's trail by name.
    names = await _refusals(deployment, pa, profile_id)
    assert {"WouldWiden", "OutOfScope", "NotTheirsToRead", "NotTheDoer", "NotPlainWords"} <= names
