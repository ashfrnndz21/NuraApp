"""The timeline over HTTP (E03): the flow checkpoint 16 walks, behind the same key-context
dependency as every other profile route.

    POST /profiles/{id}/providers, /episodes, /appointments (+ /status), /readings, /photos
    POST /profiles/{id}/confirmations        subjects appointment, appointment_status, attach,
                                             and review_card naming an open episode
    GET  /profiles/{id}/timeline             the anchors, the items, the cursor, ?episode=
    GET  /profiles/{id}/episodes/{e}         the episode across its visits
    POST /profiles/{id}/episodes/{e}/attach  a paper on a yes
    GET  /profiles/{id}/providers[/{p}]      the directory and one provider's history
    POST /profiles/{id}/providers/{p}/notes  the chief's line about the place
    GET  /profiles/{id}/changes              what changed since the reader last looked
    POST /profiles/{id}/ask                  recall, with citations, the boundary last
"""

from __future__ import annotations

import base64
from datetime import timedelta
from typing import Any

from httpx import AsyncClient

from app.clock import FrozenClock, now
from app.keys.scopes import Scope
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.paper import LIPID_PANEL, placeholder_png

PA = "+6591110001"
MEI = "+6592220002"

EVERY_PART = [scope.value for scope in Scope if scope is not Scope.PROFILE]


async def _yes(client: AsyncClient, profile_id: str, who: dict[str, str], body: Any) -> str:
    made = await client.post(
        f"/profiles/{profile_id}/confirmations", json=body, headers=bearer(who["token"])
    )
    assert made.status_code == 201, made.text
    confirmation_id: str = made.json()["confirmation_id"]
    return confirmation_id


async def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


async def _visit(
    client: AsyncClient,
    profile_id: str,
    who: dict[str, str],
    provider_id: str,
    at: str,
    purpose: str,
    steps: tuple[str, ...] = (),
    episode_id: str | None = None,
) -> dict[str, Any]:
    yes = await _yes(
        client,
        profile_id,
        who,
        {
            "subject": "appointment",
            "provider_id": provider_id,
            "scheduled_at": at,
            "purpose": purpose,
        },
    )
    visit: dict[str, Any] = await _ok(
        await client.post(
            f"/profiles/{profile_id}/appointments",
            json={
                "provider_id": provider_id,
                "scheduled_at": at,
                "purpose": purpose,
                "confirmation_id": yes,
                "episode_id": episode_id,
            },
            headers=bearer(who["token"]),
        ),
        201,
    )
    for status in steps:
        step = await _yes(
            client,
            profile_id,
            who,
            {
                "subject": "appointment_status",
                "appointment_id": visit["appointment_id"],
                "status": status,
            },
        )
        visit = await _ok(
            await client.post(
                f"/profiles/{profile_id}/appointments/{visit['appointment_id']}/status",
                json={"status": status, "confirmation_id": step},
                headers=bearer(who["token"]),
            )
        )
    return visit


async def test_an_episodes_body_systems_round_trip_over_http(deployment: Deployment) -> None:
    """#175: the body-systems map's own tags, named on the way in, read back the same way
    everywhere an episode appears — the episode route itself and the timeline it sits on."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    episode = await _ok(
        await deployment.client.post(
            f"/profiles/{profile_id}/episodes",
            json={"kind": "illness", "label": "chest infection", "body_systems": ["lungs", "heart"]},
            headers=his,
        ),
        201,
    )
    assert sorted(episode["body_systems"]) == ["heart", "lungs"]

    fetched = await _ok(
        await deployment.client.get(f"/profiles/{profile_id}/episodes/{episode['episode_id']}", headers=his)
    )
    assert sorted(fetched["episode"]["episode"]["body_systems"]) == ["heart", "lungs"]

    untagged = await _ok(
        await deployment.client.post(
            f"/profiles/{profile_id}/episodes",
            json={"kind": "travel", "label": "Penang"},
            headers=his,
        ),
        201,
    )
    assert untagged["body_systems"] == []

    timeline = await _ok(await deployment.client.get(f"/profiles/{profile_id}/timeline", headers=his))
    on_the_timeline = {
        item["episode"]["episode_id"]: item["episode"]["body_systems"]
        for item in timeline["items"]
        if item["kind"] == "episode"
    }
    assert sorted(on_the_timeline[episode["episode_id"]]) == ["heart", "lungs"]
    assert on_the_timeline[untagged["episode_id"]] == []


async def test_the_timeline_flow_over_http(deployment: Deployment, clock: FrozenClock) -> None:
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])

    tan = await _ok(
        await client.post(
            f"/profiles/{profile_id}/providers",
            json={"name": "Dr Tan", "kind": "doctor"},
            headers=his,
        ),
        201,
    )
    episode = await _ok(
        await client.post(
            f"/profiles/{profile_id}/episodes",
            json={"kind": "illness", "label": "chest infection"},
            headers=his,
        ),
        201,
    )
    checkup = await _visit(
        client,
        profile_id,
        pa,
        tan["provider_id"],
        (now() - timedelta(days=10)).isoformat(),
        "check-up",
        steps=("confirmed", "attended"),
    )
    upcoming = await _visit(
        client,
        profile_id,
        pa,
        tan["provider_id"],
        (now() + timedelta(days=7)).isoformat(),
        "see Dr Tan again",
        episode_id=episode["episode_id"],
    )
    assert checkup["status"] == "attended" and upcoming["episode_id"] == episode["episode_id"]
    reading = await _ok(
        await client.post(
            f"/profiles/{profile_id}/readings",
            json={"systolic": 138, "diastolic": 84, "episode_id": episode["episode_id"]},
            headers=his,
        ),
        201,
    )

    # The lab paper, confirmed into the illness: its photo hangs there under the card's yes.
    card = await _ok(
        await client.post(
            f"/profiles/{profile_id}/photos",
            json={
                "data": base64.b64encode(placeholder_png(LIPID_PANEL)).decode(),
                "content_type": "image/png",
                "captured_at": "2026-09-03T08:00:00Z",
            },
            headers=his,
        ),
        201,
    )
    decisions = [{"field_id": f["field_id"], "decision": "confirmed"} for f in card["fields"]]
    yes = await _yes(
        client,
        profile_id,
        pa,
        {
            "subject": "review_card",
            "card_id": card["card_id"],
            "decisions": decisions,
            "episode_id": episode["episode_id"],
        },
    )
    done = await _ok(
        await client.post(
            f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
            json={
                "decisions": decisions,
                "confirmation_id": yes,
                "episode_id": episode["episode_id"],
            },
            headers=his,
        )
    )
    view = await _ok(
        await client.get(f"/profiles/{profile_id}/episodes/{episode['episode_id']}", headers=his)
    )
    assert [a["artifact_id"] for a in view["episode"]["artifacts"]] == [card["artifact_id"]]
    assert {f["fact_id"] for f in view["episode"]["facts"]} == {
        reading["fact_id"],
        *(f["fact_id"] for f in done["facts"]),
    }
    assert [v["id"] for v in view["visits"]] == [upcoming["appointment_id"]]

    # The timeline: the three anchors, newest first, paged, filtered by the illness.
    page = await _ok(await client.get(f"/profiles/{profile_id}/timeline", headers=his))
    assert [a["line"] for a in page["header"]] == [
        "Your last check-up was with Dr Tan on Monday 24 August.",
        "Your last visit was to Dr Tan on Monday 24 August.",
        "Your next visit is to Dr Tan on Thursday 10 September.",
    ]
    assert [i["id"] for i in page["items"]] == [
        upcoming["appointment_id"],
        episode["episode_id"],
        checkup["appointment_id"],
    ]
    first = await _ok(await client.get(f"/profiles/{profile_id}/timeline?limit=2", headers=his))
    rest = await _ok(
        await client.get(
            f"/profiles/{profile_id}/timeline",
            params={"limit": 2, "cursor": first["next_cursor"]},
            headers=his,
        )
    )
    assert [i["id"] for i in rest["items"]] == [checkup["appointment_id"]]
    only = await _ok(
        await client.get(
            f"/profiles/{profile_id}/timeline",
            params={"episode": episode["episode_id"]},
            headers=his,
        )
    )
    assert [i["kind"] for i in only["items"]] == ["appointment", "episode"]

    # Mei, his chief: a note about the place, and one that names a medicine.
    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(deployment, pa, profile_id, MEI, EVERY_PART, relationship="daughter")
    await _ok(
        await client.post(
            f"/profiles/{profile_id}/keys",
            json={"holder_phone_e164": MEI, "role": "chief"},
            headers=his,
        ),
        201,
    )
    hers = bearer(mei["token"])
    notes = f"/profiles/{profile_id}/providers/{tan['provider_id']}/notes"
    await _ok(await client.post(notes, json={"text": "parking at B2"}, headers=hers), 201)
    refused = await client.post(notes, json={"text": "warfarin at night"}, headers=hers)
    assert refused.status_code == 400 and refused.json() == {"refusal": "NoteNamesHealth"}
    history = await _ok(
        await client.get(f"/profiles/{profile_id}/providers/{tan['provider_id']}", headers=hers)
    )
    assert [n["text"] for n in history["notes"]] == ["parking at B2"]
    assert [p["artifact"]["artifact_id"] for p in history["papers"]] == [card["artifact_id"]]
    directory = await _ok(await client.get(f"/profiles/{profile_id}/providers", headers=hers))
    assert [(p["provider"]["name"], p["visits"]) for p in directory] == [("Dr Tan", 2)]

    # What changed, read twice with a write between.
    seen = await _ok(await client.get(f"/profiles/{profile_id}/changes", headers=hers))
    assert seen["first_look"] and seen["lines"][0]["key"] == "first_look"
    clock.step(timedelta(minutes=1))
    await _ok(
        await client.post(
            f"/profiles/{profile_id}/readings", json={"systolic": 132, "diastolic": 80}, headers=his
        ),
        201,
    )
    since = await _ok(await client.get(f"/profiles/{profile_id}/changes", headers=hers))
    assert not since["first_look"] and since["since"] == seen["looked_at"]
    assert [line["text"] for line in since["lines"]] == [
        "A new blood pressure was written down on Thursday 3 September."
    ]

    # Asking: Pa by voice, Mei in text, and a question nothing answers.
    voice = await _ok(
        await client.post(
            f"/profiles/{profile_id}/ask",
            json={"question": "what was my blood pressure", "mode": "voice"},
            headers=his,
        )
    )
    assert [line["text"] for line in voice["lines"]] == [
        "Your blood pressure on Thursday 3 September was 132 over 80."
    ]
    assert voice["lines"][0]["cites"] and voice["spoken"][-1] == "Ask Dr Tan."
    text = await _ok(
        await client.post(
            f"/profiles/{profile_id}/ask", json={"question": "what did Dr Tan say"}, headers=hers
        )
    )
    assert text["answered"] and all(line["cites"] for line in text["lines"])
    honest = await _ok(
        await client.post(
            f"/profiles/{profile_id}/ask", json={"question": "do I have cancer"}, headers=his
        )
    )
    assert not honest["answered"]
    assert honest["spoken"] == [
        "Nura does not have that written down.",
        "Ask Dr Tan.",
        "Nura looked in your papers.",
        "This is not a doctor's advice.",
        "Ask Dr Tan.",
    ]

    # The trail: the refused note by name, the asks, the looks.
    trail = await _ok(
        await client.get(f"/profiles/{profile_id}/audit", params={"limit": 500}, headers=his)
    )
    assert any(
        e["refused_because"] == "NoteNamesHealth" and e["actor_person_id"] == mei["person_id"]
        for e in trail
    )
    assert len([e for e in trail if e["target"] == "ask" and e["outcome"] == "allowed"]) == 3
    assert len([e for e in trail if e["target"] == "last_looked" and e["action"] == "write"]) == 2


async def test_the_new_yeses_are_bound_to_what_they_say(deployment: Deployment) -> None:
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    tan = await _ok(
        await client.post(
            f"/profiles/{profile_id}/providers",
            json={"name": "Dr Tan", "kind": "doctor"},
            headers=his,
        ),
        201,
    )
    at = (now() + timedelta(days=3)).isoformat()
    yes = await _yes(
        client,
        profile_id,
        pa,
        {
            "subject": "appointment",
            "provider_id": tan["provider_id"],
            "scheduled_at": at,
            "purpose": "check-up",
        },
    )
    other = await client.post(
        f"/profiles/{profile_id}/appointments",
        json={
            "provider_id": tan["provider_id"],
            "scheduled_at": at,
            "purpose": "something else",
            "confirmation_id": yes,
        },
        headers=his,
    )
    assert other.status_code == 400 and other.json() == {"refusal": "NotWhatWasConfirmed"}
    # A paper hangs off one thing: an episode or a visit, never both, never neither.
    both = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "attach", "artifact_id": tan["provider_id"]},
        headers=his,
    )
    assert both.status_code == 422
    missing = await client.get(f"/profiles/{profile_id}/episodes/{tan['provider_id']}", headers=his)
    assert missing.status_code == 404 and missing.json() == {"refusal": "NoSuchEpisode"}
