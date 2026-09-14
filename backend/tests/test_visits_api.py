"""The visit loop over HTTP: the routes checkpoint 7 walks (E05-01, -02, -05, -06).

    POST /profiles/{id}/providers, POST /profiles/{id}/appointments (subject appointment)
    GET  /profiles/{id}/appointments/{appt}/brief            every line verifier-clean, in Malay
    GET  /profiles/{id}/appointments/{appt}/questions        sources on each; his card is three lines
    POST /profiles/{id}/appointments/{appt}/questions        with a yes (subject question)
    POST /profiles/{id}/appointments/{appt}/transcript       the summary card
    POST /profiles/{id}/appointments/{appt}/summary/{card}/confirm  (subject visit_summary)
    GET  /profiles/{id}/memos                                the memo card

Every route sits behind the same key-context dependency as every other profile route.
"""

from __future__ import annotations

import base64
from typing import Any

from app.safety.plain_words import verify
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.visits import RED_FLAG, ROUTINE, transcript

PA = "+6591110001"
MEI = "+6591110002"
VISIT_AT = "2026-09-10T02:00:00Z"
"""Thursday 10 September, 10 in the morning in Singapore."""


def _clean(lines: list[str], language: str) -> None:
    for line in lines:
        assert [f for f in verify(line, language) if f.severity != "note"] == [], line


def _transcript(label: str) -> dict[str, str]:
    return {"data": base64.b64encode(transcript(label).encode()).decode(), "captured_at": VISIT_AT}


async def _recording(deployment: Deployment, his: dict[str, str], profile_id: str) -> None:
    agreed = await deployment.client.post(
        f"/profiles/{profile_id}/consents/recording",
        json={"language": "en", "captured_via": "app"},
        headers=his,
    )
    assert agreed.status_code == 201, agreed.text
    assert agreed.json()["purpose"] == "recording"


async def _visit(deployment: Deployment, his: dict[str, str], profile_id: str) -> str:
    doctor = await deployment.client.post(
        f"/profiles/{profile_id}/providers", json={"name": "Dr Tan", "kind": "doctor"}, headers=his
    )
    assert doctor.status_code == 201, doctor.text
    booking = {
        "provider_id": doctor.json()["provider_id"],
        "scheduled_at": VISIT_AT,
        "purpose": "blood pressure check",
    }
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "appointment", **booking},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    booked = await deployment.client.post(
        f"/profiles/{profile_id}/appointments",
        json={**booking, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert booked.status_code == 201, booked.text
    assert booked.json()["status"] == "planned"
    appointment_id: str = booked.json()["appointment_id"]
    return appointment_id


async def _reading(deployment: Deployment, his: dict[str, str], profile_id: str) -> None:
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/readings", json={"systolic": 138, "diastolic": 84}, headers=his
    )
    assert posted.status_code == 201, posted.text


async def test_the_whole_loop_in_malay(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="ms")
    his = bearer(pa["token"])
    await _reading(deployment, his, profile_id)
    appointment_id = await _visit(deployment, his, profile_id)

    # No transcript without the agreement to recording (B3).
    refused = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/transcript",
        json=_transcript(ROUTINE),
        headers=his,
    )
    assert refused.status_code == 403 and refused.json() == {"refusal": "ConsentWithheld"}
    await _recording(deployment, his, profile_id)

    # The brief, in Malay, every line verifier-clean, naming its State.
    brief = await deployment.client.get(
        f"/profiles/{profile_id}/appointments/{appointment_id}/brief", headers=his
    )
    assert brief.status_code == 200, brief.text
    body = brief.json()
    lines = [line["text"] for line in body["lines"]]
    _clean(lines, "ms")
    assert body["language"] == "ms" and body["state_id"]
    assert lines[0] == "Anda berjumpa Dr Tan pada Khamis 10 September pukul 10 pagi."
    assert all(line["spoken"] for line in body["lines"])
    assert {line["section"] for line in body["lines"]} >= {"purpose", "changed", "bring"}
    again = await deployment.client.get(
        f"/profiles/{profile_id}/appointments/{appointment_id}/brief", headers=his
    )
    assert again.json()["brief_id"] == body["brief_id"]

    # The questions: each with its source; his card is three lines and the reassurance.
    asked = await deployment.client.get(
        f"/profiles/{profile_id}/appointments/{appointment_id}/questions", headers=his
    )
    assert asked.status_code == 200, asked.text
    card = asked.json()["card"]
    assert card[-1] == "Nura simpan soalan-soalan ini untuk anda." and len(card) <= 4
    assert asked.json()["spoken_card"] == card
    _clean(card, "ms")
    text = "Adakah pil air ini buruk untuk buah pinggang saya?"
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "question", "appointment_id": appointment_id, "text": text},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    added = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/questions",
        json={"text": text, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert added.status_code == 201, added.text
    assert added.json()["source"] == "person" and added.json()["text"] == text
    asked = await deployment.client.get(
        f"/profiles/{profile_id}/appointments/{appointment_id}/questions", headers=his
    )
    assert text in [q["text"] for q in asked.json()["questions"]]
    assert all(q["source"] for q in asked.json()["questions"])

    # The transcript in: the summary card, the dose change as a question for the doctor.
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/transcript",
        json=_transcript(ROUTINE),
        headers=his,
    )
    assert posted.status_code == 201, posted.text
    summary = posted.json()
    _clean(summary["lines"], "ms")
    assert summary["red_flag"] is False and summary["confirmed_at"] is None
    assert "Tanya Dr Tan tentang jumlah baru pil air." in summary["lines"]
    assert "Jumpa Dr Tan lagi pada Khamis 15 Oktober pukul 10 pagi." in summary["lines"]
    assert len(summary["spoken"]) == len(summary["lines"])
    kinds = {item["kind"] for item in summary["items"]}
    assert kinds == {"action", "medication_change", "follow_up", "fact_heard"}
    assert all(item["span"] and item["confidence"] > 0 for item in summary["items"])
    assert "full" not in " ".join(summary["lines"]).lower()

    # Nothing is a memo yet; the yes writes memos, a planned visit and the facts heard.
    empty = await deployment.client.get(f"/profiles/{profile_id}/memos", headers=his)
    assert empty.status_code == 200 and empty.json()["card"] == []
    decisions = [{"item_id": item["item_id"], "decision": "confirmed"} for item in summary["items"]]
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={
            "subject": "visit_summary",
            "summary_id": summary["summary_id"],
            "decisions": decisions,
        },
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    confirmed = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/summary/{summary['summary_id']}/confirm",
        json={"decisions": decisions, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert confirmed.status_code == 200, confirmed.text
    outcome: dict[str, Any] = confirmed.json()
    assert outcome["summary"]["confirmed_by_person_id"] == pa["person_id"]
    memos = {m["text"] for m in outcome["memos"]}
    assert "Tanya Dr Tan tentang jumlah baru pil air." in memos
    [planned] = outcome["appointments"]
    assert planned["status"] == "planned" and planned["scheduled_at"].startswith("2026-10-15T02:00")
    [heard] = outcome["facts"]
    assert heard["artifact_id"] == summary["artifact_id"]
    assert heard["confirmed_by_person_id"] == pa["person_id"]
    assert len(outcome["flag_ids"]) == 1
    upcoming = await deployment.client.get(f"/profiles/{profile_id}/appointments", headers=his)
    assert planned["appointment_id"] in {a["appointment_id"] for a in upcoming.json()}
    medicines = await deployment.client.get(f"/profiles/{profile_id}/medicines", headers=his)
    assert medicines.json() == []  # never a medicine fact from a transcript

    # The memo card: the current memos, in card order, verified.
    memo_card = await deployment.client.get(f"/profiles/{profile_id}/memos", headers=his)
    assert memo_card.status_code == 200
    _clean(memo_card.json()["card"], "ms")
    assert set(memo_card.json()["card"]) == memos

    # Confirming again is refused by name.
    spent = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/summary/{summary['summary_id']}/confirm",
        json={"decisions": decisions, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert spent.status_code == 409 and spent.json() == {"refusal": "AlreadyConfirmed"}


async def test_a_red_flag_transcript_marks_the_card_and_says_call_today(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    appointment_id = await _visit(deployment, his, profile_id)
    await _recording(deployment, his, profile_id)
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/transcript",
        json=_transcript(RED_FLAG),
        headers=his,
    )
    assert posted.status_code == 201, posted.text
    summary = posted.json()
    assert summary["red_flag"] is True
    assert summary["lines"][:2] == [
        "Call Dr Tan today.",
        "Dr Tan should hear about the chest pain today.",
    ]
    _clean(summary["lines"], "en")
    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", params={"scope": "records", "limit": 500}, headers=his
    )
    assert ("write", "flag") in {(e["action"], e["target"]) for e in trail.json()}


async def test_a_fragment_is_refused_and_a_narrow_key_cannot_read_the_brief(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    appointment_id = await _visit(deployment, his, profile_id)

    fragment = "Only the part for you."
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "question", "appointment_id": appointment_id, "text": fragment},
        headers=his,
    )
    refused = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/questions",
        json={"text": fragment, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert refused.status_code == 400 and refused.json() == {"refusal": "NotPlainEnough"}

    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(deployment, pa, profile_id, MEI, ["readings", "records"], "daughter")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": ["readings", "records"]},
        headers=his,
    )
    assert granted.status_code == 201, granted.text
    hers = bearer(mei["token"])
    narrow = await deployment.client.get(
        f"/profiles/{profile_id}/appointments/{appointment_id}/brief", headers=hers
    )
    assert narrow.status_code == 403 and narrow.json() == {
        "refusal": "OutOfScope",
        "scope": "visits",
    }
    memos = await deployment.client.get(f"/profiles/{profile_id}/memos", headers=hers)
    assert memos.status_code == 403 and memos.json()["refusal"] == "OutOfScope"
    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", params={"actor_person_id": mei["person_id"]}, headers=his
    )
    assert {(e["outcome"], e["refused_because"]) for e in trail.json()} >= {
        ("refused", "OutOfScope")
    }
