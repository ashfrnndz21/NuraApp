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
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.clock import FrozenClock
from app.consent.models import ConsentPurpose
from app.consent.texts import current_version
from app.reasoning.visits.models import Memo
from app.safety.boundary import Surface, boundary_lines
from app.safety.plain_words import verify
from app.safety.red_flags import Flag, FlagKind
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
        json={
            "wording_version": current_version(ConsentPurpose.RECORDING),
            "language": "en",
            "captured_via": "app",
        },
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
    # The brief ends on its boundary line (E16-01), and the answer carries it whole.
    assert lines[-3:] == body["boundary"].splitlines()
    assert lines[-3:] == list(boundary_lines(Surface.BRIEF, "ms", doctor="Dr Tan"))
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
    assert card[-4] == "Nura simpan soalan-soalan ini untuk anda." and len(card) <= 4 + 3
    assert card[-3:] == list(boundary_lines(Surface.QUESTIONS, "ms", doctor="Dr Tan"))
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
    assert "Anda berjumpa Dr Tan lagi pada Khamis 15 Oktober pukul 10 pagi." in summary["lines"]
    assert "Anda akan tempahkannya." in summary["lines"]
    assert len(summary["spoken"]) == len(summary["lines"])
    assert summary["lines"][-3:] == summary["boundary"].splitlines()
    kinds = {item["kind"] for item in summary["items"]}
    assert kinds == {"action", "medication_change", "follow_up", "follow_up_who", "fact_heard"}
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
    assert set(memo_card.json()["card"][:-3]) == memos
    assert memo_card.json()["card"][-3:] == list(
        boundary_lines(Surface.SUMMARY, "ms", doctor="Dr Tan")
    )

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
        "Tell Dr Tan about the chest pain today.",
    ]
    _clean(summary["lines"], "en")
    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", params={"scope": "records", "limit": 500}, headers=his
    )
    assert ("write", "red_flag") in {(e["action"], e["target"]) for e in trail.json()}


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


async def test_a_red_flag_row_survives_a_refused_request(deployment: Deployment) -> None:
    """Review 2, #5, over HTTP: a doctor named with digits makes every card line unrenderable
    (`NotASlotValue`, 400) — and the red-flag Flag written before the card is still in the
    record afterwards, replayed like a refused audit line."""
    from sqlalchemy import select

    from app.safety.red_flags import Flag

    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    await _recording(deployment, his, profile_id)
    doctor = await deployment.client.post(
        f"/profiles/{profile_id}/providers", json={"name": "Dr 999", "kind": "doctor"}, headers=his
    )
    booking = {
        "provider_id": doctor.json()["provider_id"],
        "scheduled_at": VISIT_AT,
        "purpose": "check",
    }
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "appointment", **booking},
        headers=his,
    )
    booked = await deployment.client.post(
        f"/profiles/{profile_id}/appointments",
        json={**booking, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    appointment_id = booked.json()["appointment_id"]
    text = "He had chest pain twice this week on the stairs."
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/transcript",
        json={"data": base64.b64encode(text.encode()).decode(), "captured_at": VISIT_AT},
        headers=his,
    )
    assert posted.status_code == 400 and posted.json() == {"refusal": "NotASlotValue"}
    async with deployment.sessions() as session:
        flags = (await session.scalars(select(Flag))).all()
    assert [(f.kind.value, f.code) for f in flags] == [("red_flag", "chest_pain")]
    assert str(flags[0].appointment_id) == appointment_id
    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", params={"limit": 500}, headers=his
    )
    assert ("write", "red_flag", "allowed") in {
        (e["action"], e["target"], e["outcome"]) for e in trail.json()
    }


async def test_a_clinic_key_reads_the_visits_and_cannot_write_them(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    await _recording(deployment, his, profile_id)
    appointment_id = await _visit(deployment, his, profile_id)
    clinic = await register_by_phone(deployment, MEI, "Clinic")
    await let_in(deployment, pa, profile_id, MEI, ["visits", "records", "medicines"], "other")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={
            "holder_phone_e164": MEI,
            "role": "clinic",
            "scopes": ["visits", "records", "medicines"],
        },
        headers=his,
    )
    assert granted.status_code == 201, granted.text
    theirs = bearer(clinic["token"])
    read = await deployment.client.get(
        f"/profiles/{profile_id}/appointments/{appointment_id}/questions", headers=theirs
    )
    assert read.status_code == 200
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/transcript",
        json=_transcript(ROUTINE),
        headers=theirs,
    )
    assert posted.status_code == 403 and posted.json() == {"refusal": "NotTheirsToChangeVisits"}
    # A summary of another visit is not on this path.
    other = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/summary/{appointment_id}/confirm",
        json={"decisions": [], "confirmation_id": appointment_id},
        headers=his,
    )
    assert other.status_code == 404 and other.json() == {"refusal": "NoSuchSummary"}


# --- the visit loop on his feed (E05 × E21) -------------------------------------------------


async def _feed(deployment: Deployment, profile_id: str, his: dict[str, str]) -> dict[str, Any]:
    answer = await deployment.client.get(f"/profiles/{profile_id}/feed", headers=his)
    assert answer.status_code == 200, answer.text
    page: dict[str, Any] = answer.json()
    return page


async def test_inside_the_week_the_visit_card_on_his_feed_is_the_brief(
    deployment: Deployment,
) -> None:
    """The feed is what asks for the brief inside the week before a visit (E05-01), and the
    visit card carries the brief's own words — who and when, what it is about, what to bring —
    ending on the brief's boundary line (E16-01); why names the brief."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    appointment_id = await _visit(deployment, his, profile_id)

    page = await _feed(deployment, profile_id, his)
    [card] = [item for item in page["items"] if item["type"] == "visit"]
    brief = (
        await deployment.client.get(
            f"/profiles/{profile_id}/appointments/{appointment_id}/brief", headers=his
        )
    ).json()
    carried = [line for line in brief["lines"] if line["section"] in ("purpose", "bring")]
    closing = brief["boundary"].splitlines()
    assert carried and closing == list(boundary_lines(Surface.BRIEF, "en", doctor="Dr Tan"))
    assert card["why"]["brief_id"] == brief["brief_id"]
    assert card["why"]["visit_id"] == appointment_id
    assert card["headline"] == "Dr Tan on Thursday 10 September"
    assert card["body"] == [*(line["text"] for line in carried), *closing]
    assert card["voice"] == [*(line["spoken"] for line in carried), *closing]
    _clean(card["body"], "en")


async def test_after_the_visit_the_memo_card_on_his_feed_repeats_what_was_agreed(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """The memos heard at the visit (E05-06), consolidated, on one card in his words, ending on
    the summary's boundary line — until the follow-up they are filed against has passed."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    await _recording(deployment, his, profile_id)
    appointment_id = await _visit(deployment, his, profile_id)
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/transcript",
        json=_transcript(ROUTINE),
        headers=his,
    )
    assert posted.status_code == 201, posted.text
    summary = posted.json()
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
    [follow_up] = confirmed.json()["appointments"]

    clock.set(datetime(2026, 9, 11, 2, 0, tzinfo=UTC))  # the morning after the visit
    page = await _feed(deployment, profile_id, his)
    [card] = [item for item in page["items"] if item["type"] == "memo"]
    memo_card = (await deployment.client.get(f"/profiles/{profile_id}/memos", headers=his)).json()
    assert card["headline"] == "What Dr Tan said"
    assert card["body"][0] == "At your last visit Dr Tan said this:"
    assert card["body"][1:] == memo_card["card"]
    assert card["body"][-3:] == list(boundary_lines(Surface.SUMMARY, "en", doctor="Dr Tan"))
    assert any("(frusemide)" in line for line in card["body"])
    assert not any("(" in line for line in card["voice"])  # the chemical name is not read aloud
    assert card["why"]["memo_ids"] == [memo["memo_id"] for memo in memo_card["memos"]]
    assert card["why"]["visit_id"] == appointment_id
    _clean(card["body"], "en")

    # The follow-up they were filed against passes, and the card goes with it.
    clock.set(datetime.fromisoformat(follow_up["scheduled_at"]) + timedelta(days=1))
    again = bearer((await register_by_phone(deployment, PA))["token"])  # a month on: sign in again
    later = await _feed(deployment, profile_id, again)
    assert "memo" not in [item["type"] for item in later["items"]]


KIT = "+6591110003"


async def _confirm_all(
    deployment: Deployment, his: dict[str, str], profile_id: str, appointment_id: str, label: str
) -> dict[str, Any]:
    """Upload a transcript and keep every item on its card, with the yes for exactly that."""
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/transcript",
        json=_transcript(label),
        headers=his,
    )
    assert posted.status_code == 201, posted.text
    summary = posted.json()
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
    result: dict[str, Any] = confirmed.json()
    return result


async def _key(
    deployment: Deployment,
    owner: dict[str, str],
    profile_id: str,
    phone: str,
    role: str,
    scopes: list[str],
) -> None:
    await let_in(deployment, owner, profile_id, phone, scopes, "other_family")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": phone, "role": role, "scopes": scopes},
        headers=bearer(owner["token"]),
    )
    assert granted.status_code == 201, granted.text


async def test_a_helper_refreshing_the_feed_supersedes_no_memo(deployment: Deployment) -> None:
    """Review 3: a key that may not change the visits never consolidates the memos, whatever
    reads them — here a helper opening the feed after the visit."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    await _recording(deployment, his, profile_id)
    appointment_id = await _visit(deployment, his, profile_id)
    await _confirm_all(deployment, his, profile_id, appointment_id, ROUTINE)
    kit = await register_by_phone(deployment, KIT, "Kit")
    await _key(deployment, pa, profile_id, KIT, "helper", ["medicines", "emergency"])

    async def memo_rows() -> list[tuple[Any, Any]]:
        async with deployment.sessions() as session:
            return [(m.id, m.superseded_at) for m in (await session.scalars(select(Memo))).all()]

    before = await memo_rows()
    assert before
    await _feed(deployment, profile_id, bearer(kit["token"]))
    assert await memo_rows() == before


async def test_a_red_flag_heard_at_the_visit_tells_the_family_on_their_feed(
    deployment: Deployment,
) -> None:
    """Review 3: a word heard at the visit tells what a tapped one tells — every live key with
    the emergency scope is on the flag, with a share line each — and the caregiver's feed
    carries it; his own summary card leads with calling the doctor, and his feed has no
    emergency card for it."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    await _recording(deployment, his, profile_id)
    mei = await register_by_phone(deployment, MEI, "Mei")
    await _key(
        deployment,
        pa,
        profile_id,
        MEI,
        "caregiver",
        ["medicines", "visits", "readings", "records", "emergency"],
    )
    appointment_id = await _visit(deployment, his, profile_id)
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/appointments/{appointment_id}/transcript",
        json=_transcript(RED_FLAG),
        headers=his,
    )
    assert posted.status_code == 201, posted.text
    assert posted.json()["lines"][0] == "Call Dr Tan today."

    async with deployment.sessions() as session:
        [flag] = (await session.scalars(select(Flag).where(Flag.kind == FlagKind.RED_FLAG))).all()
    assert mei["person_id"] in flag.told
    trail = (
        await deployment.client.get(
            f"/profiles/{profile_id}/audit", params={"limit": 500}, headers=his
        )
    ).json()
    assert any(e["action"] == "share" and e["target"] == "red_flag" for e in trail)

    his_page = await _feed(deployment, profile_id, his)
    assert "flag" not in [item["type"] for item in his_page["items"]]
    hers = await _feed(deployment, profile_id, bearer(mei["token"]))
    assert hers["audience"] == "caregiver"
    [card] = [item for item in hers["items"] if item["type"] == "flag"]
    assert card["headline"] == "Heard at the visit: chest pain"
    assert card["why"]["flag_id"] == str(flag.id)


async def test_a_brief_that_is_refused_leaves_the_visit_card_to_its_template(
    deployment: Deployment, monkeypatch: Any
) -> None:
    """Review 3: a brief the feed cannot build is refused inside its own savepoint — the
    refusal on the trail, nothing of it kept — and the visit card falls back to the template,
    which infers nothing and names no brief."""
    monkeypatch.setattr(
        "app.reasoning.visits.brief.boundary_line", lambda *args, **kwargs: "Not the line."
    )
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    await _visit(deployment, his, profile_id)

    page = await _feed(deployment, profile_id, his)
    [card] = [item for item in page["items"] if item["type"] == "visit"]
    assert card["body"] == [
        "You see Dr Tan on Thursday 10 September.",
        "Bring your blood pressure book and your tablets.",
    ]
    assert card["why"]["brief_id"] is None
    trail = (
        await deployment.client.get(
            f"/profiles/{profile_id}/audit", params={"limit": 500}, headers=his
        )
    ).json()
    assert any(
        e["outcome"] == "refused"
        and e["refused_because"] == "NoBoundaryLine"
        and e["target"] == "brief"
        for e in trail
    )
