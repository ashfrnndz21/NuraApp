"""Checkpoint 22 — Visit day: logistics, recording, clips (E05-03, E05-04, E02-05, E03-05).

    make dev                # one terminal
    make checkpoint N=22    # another: this module, through scripts/checkpoint.py

Pa, his chief Mei, Kit with a viewer's key and Siti with a helper's, fresh numbers every run.
Dr Tan is in Pa's directory with his address; the visit is tomorrow at 9 in the morning. Mei
wrote a note about the place, and she is on the roster tomorrow morning. Pa has his blood
pressure tablet and his hospital letter on the record. The logistics card for the visit comes
from all of that: when, where, Mei's note under her name, who drives him — Mei, the roster
says, as a suggestion that waits for a yes — and what to bring. Mei's yes makes it the task
"drive Pa to Dr Tan"; the card then says so, and the feed carries it the day before. No
recording without Pa's agreement to Nura listening; a viewer is refused before the room is
told anything. Pa agrees; the notice is said to Dr Tan by name; Mei's recording goes up once,
on Stop, and is kept as a consult, heard, separated by speaker — Dr Tan's yes the first
seconds after the notice — and read into the post-visit card with each line's place in the
recording. Mei asks what Dr Tan said about the water pill: before the card has a yes the
answer says it is waiting for it; after Mei confirms it, the answer cites the stretch. The clip
plays for Pa and the family he let in — Mei, Lim his caregiver — and a viewer's key and the
clinic's are refused, as the room was told. Last, the refusals on Pa's
trail.

Self-contained: every helper this module needs is here, so the shared runner only dispatches.
It is a client and nothing more. `run(base_url, dev_log)` prints ✓/✗ lines in the runner's
style and returns 0 or 1.
"""

from __future__ import annotations

import base64
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

CODE_LINE = re.compile(r"login code for (\+[0-9]+): ([0-9]{6})")
CODE_WAIT_SECONDS = 3.0
HOLD_WORDING = "1"
RECORDING_WORDING = "1"
SINGAPORE = ZoneInfo("Asia/Singapore")

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DISCHARGE_LETTER = "discharge-letter-2026-08-20"
ADDRESS = "Gleneagles Hospital, 6A Napier Road"
WEBM_MAGIC = b"\x1a\x45\xdf\xa3"
CONSULT = "consult-bp-review"
CONSULT_TYPE = "audio/webm;codecs=opus"
DURATION_S = 66.0
QUESTION = "what did Dr Tan say about the water pill"
EVERY_PART = ["medicines", "visits", "readings", "records", "notes", "money", "family", "emergency", "ask", "send"]

JSON = dict[str, Any]


class Failed(Exception):
    """One step did not do what the checkpoint says. Carries the printed line."""


class Person:
    def __init__(self, name: str, phone_e164: str) -> None:
        self.name = name
        self.phone_e164 = phone_e164
        self.token = ""
        self.person_id = ""


# --- the small helpers, the same shape as scripts/checkpoint.py -------------------------------


def placeholder_png(label: str) -> bytes:
    """The same lines as `backend/tests/paper.py`: the digest names the paper's fixture."""
    return PNG_SIGNATURE + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"


def placeholder_pdf(label: str) -> bytes:
    return b"%PDF-1.4\n" + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"


def placeholder_voice(label: str) -> bytes:
    """The same line as `backend/tests/voice_notes.py`: the digest names the transcript."""
    return b"nura-voice-placeholder:" + label.encode("ascii") + b"\n"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def short(body: str, limit: int = 300) -> str:
    text = " ".join(body.split())
    return text if len(text) <= limit else text[:limit] + "…"


def fail(what: str, response: httpx.Response | None = None, why: str | None = None) -> Failed:
    if response is None:
        return Failed(f"✗ {what}" + (f" ({why})" if why else ""))
    detail = f"{response.status_code}, {short(response.text) or 'empty body'}"
    return Failed(f"✗ {what} ({detail})" + (f" — {why}" if why else ""))


def ok(line: str) -> None:
    print(f"✓ {line}", flush=True)


def say(line: str) -> None:
    print(f"    {line}", flush=True)


def check(response: httpx.Response, status: int, what: str) -> Any:
    if response.status_code != status:
        raise fail(what, response, f"expected {status}")
    if response.status_code == 204 or not response.content:
        return None
    if not response.headers.get("content-type", "").startswith("application/json"):
        return response.content
    return response.json()


def refused(response: httpx.Response, status: int, refusal: str, what: str) -> JSON:
    body = check(response, status, what)
    if not isinstance(body, dict) or body.get("refusal") != refusal:
        raise fail(what, response, f"expected refusal {refusal}")
    return body


def fresh_phone(prefix: str) -> str:
    return f"{prefix}{random.randint(0, 9999):04d}"


def code_from_log(dev_log: Path, phone_e164: str, since: float) -> str:
    deadline = time.monotonic() + CODE_WAIT_SECONDS
    while True:
        if dev_log.exists():
            codes = [
                m.group(2)
                for m in CODE_LINE.finditer(dev_log.read_text(errors="replace"))
                if m.group(1) == phone_e164
            ]
            if codes:
                return codes[-1]
        if time.monotonic() > deadline:
            break
        time.sleep(0.2)
    if not dev_log.exists():
        raise Failed(f"✗ {dev_log} is missing: start the server with `make dev` in another terminal")
    raise Failed(
        f"✗ no login code for {phone_e164} appeared in {dev_log} within {CODE_WAIT_SECONDS:.0f}s."
        " Stop the server and run `make dev` (only that writes the log here)"
    )


def register(client: httpx.Client, dev_log: Path, person: Person, language: str) -> None:
    who = f"{person.name} ({person.phone_e164})"
    began = time.time()
    started = client.post(
        "/auth/phone/start",
        json={"phone_e164": person.phone_e164, "display_name": person.name, "language": language},
    )
    body = check(started, 202, f"{who} asks for a code by phone")
    if "code" in str(body):
        raise fail(f"{who} asks for a code by phone", started, "the code came back on the wire")
    code = code_from_log(dev_log, person.phone_e164, began)
    verified = client.post(
        "/auth/phone/verify", json={"phone_e164": person.phone_e164, "code": code}
    )
    session = check(verified, 200, f"{who} types the code in")
    person.token = session["token"]
    person.person_id = session["person_id"]
    ok(f"{who} registered by phone code and signed in (the code read from the server log)")


def placeholder_consult(label: str) -> bytes:
    """The same line as `backend/tests/consult_audio.py`: a webm's first four bytes, a marker
    and a label, whose digest names what the fixture transcriber and separator heard."""
    return WEBM_MAGIC + b"nura-consult-placeholder:" + label.encode("ascii") + b"\n"


def open_profile(client: httpx.Client, pa: Person) -> str:
    opened = check(
        client.post(
            "/profiles/mine",
            headers=bearer(pa.token),
            json={
                "consent": {"wording_version": HOLD_WORDING, "language": "en", "captured_via": "app"},
                "display_name": pa.name,
                "language": "en",
            },
        ),
        201,
        "Pa opens his profile",
    )
    profile_id: str = opened["profile_id"]
    return profile_id


def let_in(client: httpx.Client, pa: Person, profile_id: str, who: Person, role: str, scopes: list[str]) -> None:
    his = bearer(pa.token)
    check(
        client.post(
            f"/profiles/{profile_id}/consents/sharing",
            headers=his,
            json={
                "holder_phone_e164": who.phone_e164,
                "holder_display_name": who.name,
                "scopes": scopes,
                "relationship": "other_family",
                "language": "en",
                "captured_via": "app",
            },
        ),
        201,
        f"Pa lets {who.name} in",
    )
    body: JSON = {"holder_phone_e164": who.phone_e164, "role": role}
    if role != "chief":
        body["scopes"] = scopes
    check(client.post(f"/profiles/{profile_id}/keys", headers=his, json=body), 201, f"Pa cuts {who.name} a {role} key")


def lines_of(card: JSON) -> None:
    for line in card["lines"]:
        say(f"[{line['section']:<6}] {line['text']}")
    if card.get("note"):
        say(f"         {card['note']['label']}: \"{card['note']['text']}\"  (as she wrote it)")


def walk(client: httpx.Client, dev_log: Path) -> None:
    pa = Person("Pa", fresh_phone("+659122"))
    mei = Person("Mei", fresh_phone("+659223"))
    kit = Person("Kit", fresh_phone("+659324"))
    siti = Person("Siti", fresh_phone("+659425"))
    lim = Person("Lim", fresh_phone("+659526"))
    clinic = Person("Clinic", fresh_phone("+659627"))
    for person in (pa, mei, kit, siti, lim, clinic):
        register(client, dev_log, person, "en")
    profile_id = open_profile(client, pa)
    his, hers = bearer(pa.token), bearer(mei.token)
    let_in(client, pa, profile_id, mei, "chief", EVERY_PART)
    let_in(client, pa, profile_id, kit, "viewer", ["visits", "readings"])
    let_in(client, pa, profile_id, siti, "helper", ["medicines"])
    let_in(client, pa, profile_id, lim, "caregiver", ["visits", "records", "readings"])
    let_in(client, pa, profile_id, clinic, "clinic", ["visits", "records"])
    ok(
        "Pa opened his profile: Mei his chief (every part), Lim a caregiver (the visits, the record, the readings), "
        "Kit a viewer (the visits, the readings), Siti a helper (the medicines), and the clinic (the visits, the record)"
    )

    # 1. Dr Tan, his address, the visit tomorrow at 9 in the morning on Pa's yes.
    tomorrow = (datetime.now(SINGAPORE) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    # On his clock, with its offset: kept as that instant (ADR 0009).
    at = tomorrow.isoformat()
    tan = check(
        client.post(
            f"/profiles/{profile_id}/providers",
            headers=his,
            json={"name": "Dr Tan", "kind": "doctor", "address": ADDRESS},
        ),
        201,
        "Pa adds Dr Tan with his address",
    )
    booking = {"provider_id": tan["provider_id"], "scheduled_at": at, "purpose": "blood pressure check"}
    yes = check(
        client.post(f"/profiles/{profile_id}/confirmations", headers=his, json={"subject": "appointment", **booking}),
        201,
        "Pa says yes to the visit",
    )
    visit = check(
        client.post(
            f"/profiles/{profile_id}/appointments",
            headers=his,
            json={**booking, "confirmation_id": yes["confirmation_id"]},
        ),
        201,
        "Pa writes the visit down",
    )
    appointment_id = visit["appointment_id"]
    route = f"/profiles/{profile_id}/appointments/{appointment_id}"
    check(
        client.post(
            f"/profiles/{profile_id}/providers/{tan['provider_id']}/notes",
            headers=hers,
            json={"text": "parking at B2"},
        ),
        201,
        "Mei writes her note about the place",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/roster",
            headers=hers,
            json={
                "person_id": mei.person_id,
                "role": "chief",
                "weekdays": [tomorrow.weekday()],
                "from_time": "07:00:00",
                "to_time": "12:00:00",
            },
        ),
        201,
        "Mei puts herself on the roster tomorrow morning",
    )
    ok(
        f"Dr Tan in Pa's directory at {ADDRESS}; the visit tomorrow, {tomorrow:%A %d %B} at 9, on Pa's yes; "
        "Mei's note about the place (\"parking at B2\") and Mei on the roster tomorrow from 7 to 12"
    )

    # 2. His blood pressure tablet and his hospital letter: what to bring.
    photo = check(
        client.post(
            f"/profiles/{profile_id}/photos",
            headers=his,
            json={
                "data": b64(PNG_SIGNATURE + b"nura-paper-placeholder:cp22-label-" + str(random.random()).encode() + b"\n"),
                "content_type": "image/png",
                "captured_at": "2026-09-14T08:00:00Z",
            },
        ),
        201,
        "Pa photographs his tablet box",
    )
    label = {
        "generic": "amlodipine",
        "strength": "5 mg",
        "dose_text": "1 tab OD",
        "quantity": 30,
        "prescriber": "Dr Tan",
        "source_kind": "retail",
    }
    minted = check(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=his,
            json={"subject": "medicine", "label": label, "source_artifact_id": photo["artifact_id"]},
        ),
        201,
        "Pa says yes to the tablet",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/medicines",
            headers=his,
            json={"label": label, "source_artifact_id": photo["artifact_id"], "confirmation_id": minted["confirmation_id"]},
        ),
        201,
        "Pa adds his blood pressure tablet",
    )
    letter = check(
        client.post(
            f"/profiles/{profile_id}/imports",
            headers=his,
            json={
                "data": b64(b"%PDF-1.4\n" + b"nura-paper-placeholder:" + DISCHARGE_LETTER.encode() + b"\n"),
                "content_type": "application/pdf",
                "captured_at": "2026-08-21T02:00:00Z",
                "source": "portal",
                "document_kind": "discharge_letter",
            },
        ),
        201,
        "Pa imports his hospital letter",
    )
    decisions = [{"field_id": field["field_id"], "decision": "confirmed"} for field in letter["fields"]]
    letter_yes = check(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=his,
            json={"subject": "review_card", "card_id": letter["card_id"], "decisions": decisions},
        ),
        201,
        "Pa says yes to the letter",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/review-cards/{letter['card_id']}/confirm",
            headers=his,
            json={"decisions": decisions, "confirmation_id": letter_yes["confirmation_id"]},
        ),
        200,
        "Pa confirms the letter",
    )
    ok("Pa's blood pressure tablet from its label, and his hospital letter confirmed: both are things to bring")

    # 3. The logistics card: the record, and the roster's suggestion waiting for a yes.
    card = check(client.get(f"{route}/logistics", headers=his), 200, "Pa reads the logistics card")
    driver = card["driver"]
    if driver["status"] != "suggested" or driver["name"] != "Mei" or not driver["needs_yes"]:
        raise fail("Pa reads the logistics card", why=f"the roster's suggestion is not waiting for a yes: {driver}")
    if not card["note"] or card["note"]["text"] != "parking at B2" or card["note"]["label"] != "Mei's note":
        raise fail("Pa reads the logistics card", why=f"Mei's note is not under her name: {card['note']}")
    when = next(line["text"] for line in card["lines"] if line["section"] == "when")
    if "at 9 in the morning" not in when:
        raise fail("Pa reads the logistics card", why=f"not the time it was booked for: {when}")
    bring = [line["text"] for line in card["lines"] if line["section"] == "bring"]
    if len(bring) != 3:
        raise fail("Pa reads the logistics card", why=f"not the book, the tablets and the letter: {bring}")
    ok(
        f"GET …/appointments/{{appt}}/logistics: the card for tomorrow, from the record and State "
        f"(state {card['state_id'][:8]}…), every line through the plain-words verifier:"
    )
    lines_of(card)
    say(f"driver: {driver['status']} — Mei, on the roster then; needs the chief's yes: {driver['needs_yes']}")

    refused(
        client.post(
            f"{route}/driver",
            headers=hers,
            json={"person_id": mei.person_id, "confirmation_id": appointment_id},
        ),
        400,
        "NotAConfirmerHere",
        "Mei gives the drive without a yes",
    )
    drive = {"subject": "drive", "appointment_id": appointment_id, "person_id": mei.person_id}
    kit_says = refused(
        client.post(f"/profiles/{profile_id}/confirmations", headers=bearer(kit.token), json=drive),
        403,
        "OutOfScope",
        "Kit says yes to the drive",
    )
    if kit_says.get("scope") != "family":
        raise fail("Kit says yes to the drive", why=f"refused at the wrong door: {kit_says}")
    drive_yes = check(
        client.post(f"/profiles/{profile_id}/confirmations", headers=hers, json=drive), 201, "Mei says yes to driving"
    )
    task = check(
        client.post(
            f"{route}/driver",
            headers=hers,
            json={"person_id": mei.person_id, "confirmation_id": drive_yes["confirmation_id"]},
        ),
        201,
        "Mei gives herself the drive",
    )
    after = check(client.get(f"{route}/logistics", headers=his), 200, "Pa reads the card again")
    driving = [line["text"] for line in after["lines"] if line["section"] == "driver"]
    if task["what"] != "drive Pa to Dr Tan" or task["errand"] != "drive" or after["driver"]["status"] != "assigned":
        raise fail("Mei gives herself the drive", why=f"{task} / {after['driver']}")
    ok(
        "the suggestion is nothing until a yes: without one, NotAConfirmerHere (400); Kit's viewer key does not "
        f"reach the family list, so it cannot mint one, OutOfScope (403, family). Mei's yes (subject drive) made the task \"{task['what']}\", "
        f"hers, due at the visit; the card now says: \"{driving[0]}\""
    )

    # 4. The feed: the logistics card the day before.
    page = check(client.get(f"/profiles/{profile_id}/feed", headers=his), 200, "Pa reads his feed")
    source = "Pa's feed"
    if page.get("quiet"):
        page = check(client.get(f"/profiles/{profile_id}/feed", headers=hers), 200, "Mei reads his list")
        source = "Mei's list (Pa's feed keeps quiet at night)"
    cards = [item for item in page["items"] if item["type"] == "visit_logistics"]
    if not cards or cards[0]["headline"] != "Getting to Dr Tan tomorrow":
        raise fail("Pa reads his feed", why=f"no logistics card the day before: {[i['type'] for i in page['items']]}")
    ok(
        f"{source}: the visit_logistics card the day before — \"{cards[0]['headline']}\", its lines the card's, "
        f"rendered from state {cards[0]['rendered_from_state'][:8]}…, no boundary (it infers nothing), never autoplayed"
    )

    # 5. No recording without his agreement; a viewer is refused before the room is told.
    refused(client.get(f"{route}/recording/notice", headers=hers), 403, "ConsentWithheld", "Mei asks for the notice")
    audio = placeholder_consult(CONSULT)
    refused(
        client.post(
            f"{route}/recording",
            headers={**hers, "Content-Type": CONSULT_TYPE},
            params={"duration_s": DURATION_S},
            content=audio,
        ),
        403,
        "ConsentWithheld",
        "Mei sends a recording",
    )
    none_kept = check(client.get(f"{route}/recordings", headers=his), 200, "Pa lists the recordings")
    if none_kept:
        raise fail("Pa lists the recordings", why=f"something was kept without his agreement: {none_kept}")
    refused(
        client.get(f"{route}/recording/notice", headers=bearer(kit.token)),
        403,
        "NotTheirsToChangeVisits",
        "Kit asks for the notice",
    )
    ok(
        "no recording without Pa's agreement: the notice and the upload are both refused, ConsentWithheld (403), "
        "and nothing is kept; Kit's viewer key is refused before the room is told anything, NotTheirsToChangeVisits (403)"
    )

    # 6. He agrees; the notice; the words for a no.
    check(
        client.post(
            f"/profiles/{profile_id}/consents/recording",
            headers=his,
            json={"wording_version": RECORDING_WORDING, "language": "en", "captured_via": "app"},
        ),
        201,
        "Pa agrees to Nura listening at the visit",
    )
    notice = check(client.get(f"{route}/recording/notice", headers=hers), 200, "Mei asks for the notice")
    if notice["spoken"][-1] != "Is that OK, Dr Tan?":
        raise fail("Mei asks for the notice", why=f"not to Dr Tan by name: {notice['spoken']}")
    ok("Pa agreed to Nura listening (POST …/consents/recording); the notice Mei's phone says first, to Dr Tan by name:")
    for line in notice["spoken"]:
        say(line)
    say(f"and on a no: {' / '.join(notice['when_no'])}")

    # 7. The recording, once, on Stop.
    kept = check(
        client.post(
            f"{route}/recording",
            headers={**hers, "Content-Type": CONSULT_TYPE},
            params={"duration_s": DURATION_S},
            content=audio,
        ),
        201,
        "Mei's phone sends the recording",
    )
    recording = kept["recording"]
    segments = recording["segments"]
    if not recording["heard"] or len(segments) != 11 or segments[1]["speaker"] != "doctor":
        raise fail("Mei's phone sends the recording", why=f"{recording}")
    ok(
        f"Mei's recording, sent once on Stop (POST …/recording, {CONSULT_TYPE}, {DURATION_S:g} s): a consult voice "
        f"artefact {recording['artifact_id'][:8]}… on the RECORDING consent {recording['consent_id'][:8]}…, heard at "
        f"{recording['heard_confidence']}, and who spoke when — {len(segments)} stretches, no words in any row:"
    )
    for one in segments:
        mark = "  ← Dr Tan's yes, the first seconds after the notice" if one["position"] == 1 else ""
        say(f"{one['start_s']:>5.1f}–{one['end_s']:<5.1f} {one['speaker']}{mark}")

    summary = kept["summary"]
    if summary is None or summary["recording_artifact_id"] != recording["artifact_id"]:
        raise fail("Mei's phone sends the recording", why=f"no post-visit card: {kept['summary_refused']}")
    placed = [item for item in summary["items"] if item["clip_start_s"] is not None]
    ok(
        f"the post-visit card from the transcript (summary {summary['summary_id'][:8]}…), each line with where in the "
        "recording Dr Tan said it:"
    )
    for item in summary["items"]:
        when = f"{item['clip_start_s']:>5.1f}–{item['clip_end_s']:<5.1f}" if item["clip_start_s"] is not None else "     —     "
        say(f"{when} {item['text']}")
    if len(placed) != len(summary["items"]):
        raise fail("the post-visit card", why="an item with no place in the recording")

    # 8. Ask: before his yes the card is waiting; after it, the answer cites where Dr Tan said it.
    waiting = check(
        client.post(f"/profiles/{profile_id}/ask", headers=hers, json={"question": QUESTION, "mode": "text"}),
        200,
        "Mei asks what Dr Tan said, before the card is confirmed",
    )
    on_the_card = [
        line["text"] for line in waiting["lines"] if any(c["kind"] == "visit_summary" for c in line["cites"])
    ]
    if not on_the_card or any(line.get("clip") for line in waiting["lines"]):
        raise fail("Mei asks before the card is confirmed", why=f"the recording was cited: {waiting['lines']}")
    ok(f"Mei asks \"{QUESTION}\" before the card has a yes: \"{on_the_card[0]}\" — nothing Dr Tan said is cited yet")
    decisions = [{"item_id": item["item_id"], "decision": "confirmed"} for item in summary["items"]]
    card_yes = check(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=hers,
            json={"subject": "visit_summary", "summary_id": summary["summary_id"], "decisions": decisions},
        ),
        201,
        "Mei says yes to the card",
    )
    check(
        client.post(
            f"{route}/summary/{summary['summary_id']}/confirm",
            headers=hers,
            json={"decisions": decisions, "confirmation_id": card_yes["confirmation_id"]},
        ),
        200,
        "Mei confirms the card",
    )
    answer = check(
        client.post(f"/profiles/{profile_id}/ask", headers=hers, json={"question": QUESTION, "mode": "text"}),
        200,
        "Mei asks what Dr Tan said",
    )
    said = [line for line in answer["lines"] if line.get("clip")]
    if not said:
        raise fail("Mei asks what Dr Tan said", why=f"no line plays the clip: {answer['lines']}")
    clip = said[0]["clip"]
    ok(
        f"Mei confirms the card on her yes, then asks again: \"{said[0]['text']}\" — citing the recording "
        f"{clip['artifact_id'][:8]}… from {clip['start_s']:g} to {clip['end_s']:g} seconds, the button "
        f"\"Hear what {clip['doctor']} said\""
    )
    where = f"/profiles/{profile_id}/artifacts/{clip['artifact_id']}/clip"
    stretch = {"start": clip["start_s"], "end": clip["end_s"]}
    whole = {"start": 0, "end": DURATION_S}
    played = client.get(where, headers=his, params=stretch)
    if played.status_code != 200 or played.content != audio:
        raise fail("Pa plays the clip", played)
    for params in (stretch, whole):
        heard = client.get(where, headers=bearer(lim.token), params=params)
        if heard.status_code != 200 or heard.content != audio:
            raise fail("Lim plays the recording", heard)
        refused(client.get(where, headers=bearer(kit.token), params=params), 403, "OnlyTheFamilyHears", "Kit plays the recording")
        refused(client.get(where, headers=bearer(clinic.token), params=params), 403, "OnlyTheFamilyHears", "the clinic plays the recording")
    refused(client.get(where, headers=bearer(siti.token), params=stretch), 403, "OutOfScope", "Siti plays the clip")
    refused(client.get(where, headers=his, params={"start": 10, "end": 500}), 400, "NotAClip", "Pa plays past the end")
    ok(
        f"the clip (GET …/artifacts/{{a}}/clip?start={clip['start_s']:g}&end={clip['end_s']:g}): the recording's "
        f"{len(played.content)} bytes, {played.headers['content-type']}, X-Media-Fragment {played.headers['x-media-fragment']} "
        "— the phone plays that stretch"
    )
    ok(
        "who hears it is what the room was told: Pa and the family he let in — Lim, his caregiver, hears the clip and the "
        "whole recording; Kit's viewer key and the clinic's key both hold the visits and are refused, OnlyTheFamilyHears "
        "(403); Siti's helper key does not reach the visits, OutOfScope (403); a stretch outside the recording is NotAClip (400)"
    )

    # 9. The trail.
    trail = check(
        client.get(f"/profiles/{profile_id}/audit", headers=his, params={"limit": 500}), 200, "Pa reads his trail"
    )
    names = {
        "Pa": pa.person_id,
        "Mei": mei.person_id,
        "Kit": kit.person_id,
        "Siti": siti.person_id,
        "Lim": lim.person_id,
        "Clin": clinic.person_id,
    }
    who = {value: key for key, value in names.items()}
    refusals = [e for e in trail if e["outcome"] == "refused"]
    wanted = {"ConsentWithheld", "NotTheirsToChangeVisits", "NotAClip", "OutOfScope", "OnlyTheFamilyHears"}
    missing = wanted - {e["refused_because"] for e in refusals}
    if missing:
        raise fail("Pa reads his trail", why=f"not on it: {sorted(missing)}")
    ok(f"Pa reads his trail ({len(trail)} lines); every refusal of this walk is on it:")
    seen: set[tuple[str, str, str, str]] = set()
    for row in refusals:
        key = (who.get(row["actor_person_id"], "?"), row["action"], row["target"], row["refused_because"])
        if key in seen:
            continue
        seen.add(key)
        say(f"{row['at'][:19]}  {key[0]:>4}  {row['action']} {row['scope']} {row['target']}  refused {row['refused_because']}")


def run(base_url: str, dev_log: Path) -> int:
    """Walk checkpoint 22 against the server at `base_url`; 0 when every step is a ✓."""
    try:
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            walk(client, Path(dev_log))
    except Failed as failed:
        print(str(failed), flush=True)
        return 1
    return 0
