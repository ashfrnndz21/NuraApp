"""Checkpoint 18 — Handwriting, PDFs, notes, device screens (E02-02, E02-03, E02-06, E02-08).

    make dev                # one terminal
    make checkpoint N=18    # another: this module, through scripts/checkpoint.py

Pa and Mei, fresh numbers every run. Pa photographs Dr Tan's handwritten clinic slip: the
drug, the dose and the rest come back with their confidence, and the frequency — scrawled —
comes back as a field Nura could not read, with the lines that ask for it. Confirming it as
read is refused; Mei types what the slip says and Pa confirms the card. Pa imports a two-page
hospital letter from the portal: every field says its page, and confirming it records the
discharge on the letter's date. A receipt forwarded by mistake is an open card that says it is
not a health paper; a photo offered as a PDF is refused. Pa types this morning's blood
pressure and leaves a voice note on it — his own words, so kept on the record consent with
no recording consent asked (ADR 0003) — heard, played back, and never a fact. Pa photographs his blood pressure machine: 138/84,
pulse 72, the time on the screen, no typing; one yes, one reading, State recomputed. A photo
of a lab report sent as a machine's screen says it is not one. Last, the accuracy harness over
the labelled papers, quoted, and the refusals on Pa's trail.

Self-contained: every helper this module needs is here, so the shared runner only dispatches.
It is a client and nothing more, except that it runs the harness (`python3 -m
tests.paper_accuracy`) the way the owner would, from the backend directory.
`run(base_url, dev_log)` prints ✓/✗ lines in the runner's style and returns 0 or 1.
"""

from __future__ import annotations

import base64
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

DEMO_LOGIN_CODE = os.environ.get("NURA_DEMO_LOGIN_CODE") or None
"""Against a demo deployment (docs/deploy.md, ADR 0008): the operator's code signs every test
number in, so no log is read, and every number is drawn from the test range (+65 0…)."""
CODE_LINE = re.compile(r"login code for (\+[0-9]+): ([0-9]{6})")
CODE_WAIT_SECONDS = 3.0
HOLD_WORDING = "1"
BACKEND = Path(__file__).resolve().parents[2]

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CLINIC_SLIP = "clinic-slip-2026-09-10"
DISCHARGE_LETTER = "discharge-letter-2026-08-20"
RECEIPT = "receipt-2026-09-01"
BP_CUFF = "bp-cuff-2026-09-14"
LIPID_PANEL = "lipid-panel-2023-09-07"
AFTER_THE_WALK = "pa-after-the-walk"
TYPED = "once a day in the morning"

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
    if DEMO_LOGIN_CODE is not None:
        prefix = "+650" + prefix.removeprefix("+65")[1:]
    return f"{prefix}{random.randint(0, 9999):04d}"


def code_from_log(dev_log: Path, phone_e164: str, since: float) -> str:
    if DEMO_LOGIN_CODE is not None:
        return DEMO_LOGIN_CODE
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


def decide(card: JSON, *, reject: set[str] = frozenset()) -> list[JSON]:
    """Confirm every field, except the ones rejected."""
    return [
        {
            "field_id": field["field_id"],
            "decision": "rejected" if field["attribute"] in reject else "confirmed",
        }
        for field in card["fields"]
    ]


def mint(client: httpx.Client, person: Person, profile_id: str, card: JSON, decisions: list[JSON]) -> httpx.Response:
    return client.post(
        f"/profiles/{profile_id}/confirmations",
        headers=bearer(person.token),
        json={"subject": "review_card", "card_id": card["card_id"], "decisions": decisions},
    )


def say_yes(
    client: httpx.Client, person: Person, profile_id: str, card: JSON, decisions: list[JSON], what: str
) -> JSON:
    """The person's OK for exactly these decisions, then the confirm that spends it."""
    minted = check(mint(client, person, profile_id, card, decisions), 201, f"{what}: {person.name} says OK")
    confirmed: JSON = check(
        client.post(
            f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
            headers=bearer(person.token),
            json={"decisions": decisions, "confirmation_id": minted["confirmation_id"]},
        ),
        200,
        f"{what}: {person.name} confirms the card",
    )
    return confirmed


def show(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, dict):
        return str(value.get("instruction") or value.get("as_written") or value)
    return str(value)


def print_fields(card: JSON, *, pages: bool = False) -> None:
    for field in card["fields"]:
        # A structured value (a dose) already says its unit in words.
        worded = isinstance(field["value"], dict)
        unit = f" {field['unit']}" if field["unit"] and not worded else ""
        where = f"page {field['page']}  " if pages else ""
        name = f"{field['subject']}.{field['attribute']}"
        mark = (
            "unreadable — " + " ".join(field["prompt"] or [])
            if field["unreadable"]
            else ("dotted" if field["needs_confirm"] else "clear")
        )
        say(
            f"{where}{name:<30} {show(field['value']) + unit:<24} "
            f"confidence {field['confidence']:.2f}  {mark}"
        )


def field_of(card: JSON, attribute: str) -> JSON:
    found: JSON = next(f for f in card["fields"] if f["attribute"] == attribute)
    return found


# --- the walk ----------------------------------------------------------------------------------


def walk(client: httpx.Client, dev_log: Path) -> None:
    pa = Person("Pa", fresh_phone("+659181"))
    mei = Person("Mei", fresh_phone("+659282"))

    # 1. Pa and his profile; Mei let in to the record and the readings.
    register(client, dev_log, pa, "en")
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
    profile_id = opened["profile_id"]
    his = bearer(pa.token)
    register(client, dev_log, mei, "en")
    check(
        client.post(
            f"/profiles/{profile_id}/consents/sharing",
            headers=his,
            json={
                "holder_phone_e164": mei.phone_e164,
                "holder_display_name": mei.name,
                "scopes": ["records", "readings"],
                "relationship": "daughter",
                "language": "en",
                "captured_via": "app",
            },
        ),
        201,
        "Pa lets Mei see his record and his readings",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=his,
            json={
                "holder_phone_e164": mei.phone_e164,
                "role": "caregiver",
                "scopes": ["records", "readings"],
            },
        ),
        201,
        "Pa cuts Mei a caregiver key",
    )
    ok("Pa opened his profile and cut Mei a caregiver key to his record and his readings")

    # 2. Handwriting: the clinic slip, one field Nura could not read.
    slip = check(
        client.post(
            f"/profiles/{profile_id}/photos",
            headers=his,
            json={
                "data": b64(placeholder_png(CLINIC_SLIP)),
                "content_type": "image/png",
                "captured_at": "2026-09-10T03:00:00Z",
                "document_kind": "clinic_slip",
            },
        ),
        201,
        "Pa photographs the clinic slip",
    )
    frequency = field_of(slip, "frequency")
    if slip["document_kind"] != "clinic_slip" or not frequency["unreadable"]:
        raise fail("Pa photographs the clinic slip", why=f"not read as a slip with the frequency unreadable: {slip}")
    if frequency["prompt"] != ["Nura could not read this.", "Please type it."]:
        raise fail("Pa photographs the clinic slip", why=f"the frequency does not ask for itself: {frequency}")
    ok(
        "Pa photographed Dr Tan's handwritten clinic slip (offered as a clinic_slip): drug, dose and "
        "the rest read with their confidence; the frequency, scrawled, came back unreadable — no value, "
        "never guessed — with the lines the card shows:"
    )
    print_fields(slip)
    refused(
        mint(client, pa, profile_id, slip, decide(slip)),
        400,
        "UnreadableField",
        "Pa confirms the slip with the frequency as read",
    )
    ok("confirming the frequency as read is refused: UnreadableField (400) — it is typed in, or rejected")
    typed = check(
        client.post(
            f"/profiles/{profile_id}/review-cards/{slip['card_id']}/fields/{frequency['field_id']}/type",
            headers=bearer(mei.token),
            json={"value": TYPED},
        ),
        200,
        "Mei types the frequency",
    )
    after = field_of(typed, "frequency")
    if after["corrected_value"] != TYPED or after["corrected_by_person_id"] != mei.person_id:
        raise fail("Mei types the frequency", why=f"the field does not name her: {after}")
    ok(f'Mei, with her key to the record, typed what the slip says — "{TYPED}"; the field names her, the card is still open')
    done = say_yes(client, pa, profile_id, typed, decide(typed), "the slip")
    kept = field_of(done["card"], "frequency")
    facts = {f["attribute"]: f for f in done["facts"]}
    if (
        kept["state"] != "corrected"
        or kept["corrected_by_person_id"] != mei.person_id
        or facts["frequency"]["value"] != TYPED
        or facts["frequency"]["confirmed_by_person_id"] != pa.person_id
        or done["event_id"] is None
    ):
        raise fail("the slip: Pa confirms the card", why=f"got {done}")
    ok(
        f"Pa confirmed the card: {len(done['facts'])} facts, each resting on the photo and on the visit the "
        "slip records (an event on 10 September); the frequency is Mei's words, confirmed by Pa"
    )

    # 3. A two-page PDF from the portal.
    letter = check(
        client.post(
            f"/profiles/{profile_id}/imports",
            headers=his,
            json={
                "data": b64(placeholder_pdf(DISCHARGE_LETTER)),
                "content_type": "application/pdf",
                "captured_at": "2026-08-21T02:00:00Z",
                "source": "portal",
                "document_kind": "discharge_letter",
            },
        ),
        201,
        "Pa imports the hospital letter",
    )
    pages = sorted({f["page"] for f in letter["fields"]})
    if letter["document_kind"] != "discharge_letter" or pages != [1, 2] or letter["source"] != "portal":
        raise fail("Pa imports the hospital letter", why=f"not read page by page: {letter}")
    ok(
        "Pa imported his two-page hospital letter from the portal (POST /profiles/{id}/imports): a PDF "
        "artefact, read as a discharge_letter dated 2026-08-20, every field with its page:"
    )
    print_fields(letter, pages=True)
    closed = say_yes(client, pa, profile_id, letter, decide(letter), "the letter")
    if closed["event_id"] is None or any(f["event_id"] != closed["event_id"] for f in closed["facts"]):
        raise fail("the letter: Pa confirms the card", why=f"no dated event: {closed}")
    ok(
        f"one yes: the discharge recorded as an event on 20 August, and {len(closed['facts'])} facts "
        "naming it and the PDF, valid from the date on the letter"
    )

    # 4. The receipt, and something that is not a PDF.
    receipt = check(
        client.post(
            f"/profiles/{profile_id}/imports",
            headers=his,
            json={
                "data": b64(placeholder_pdf(RECEIPT)),
                "content_type": "application/pdf",
                "captured_at": "2026-09-01T02:00:00Z",
                "source": "email",
            },
        ),
        201,
        "Pa imports the receipt",
    )
    if receipt["fields"] != [] or receipt["notice"] != ["This does not look like a health paper."]:
        raise fail("Pa imports the receipt", why=f"not refused honestly: {receipt}")
    ok(
        'the shop receipt forwarded by email is an open card with no fields and one line: '
        f'"{receipt["notice"][0]}"'
    )
    refused(
        client.post(
            f"/profiles/{profile_id}/imports",
            headers=his,
            json={
                "data": b64(placeholder_png(CLINIC_SLIP)),
                "content_type": "image/png",
                "captured_at": "2026-09-01T02:00:00Z",
                "source": "share",
            },
        ),
        400,
        "NotAPdf",
        "Pa imports a photo as a PDF",
    )
    ok("a photo offered as a PDF is refused before a byte lands: NotAPdf (400)")

    # 5. A voice note on this morning's reading.
    reading = check(
        client.post(f"/profiles/{profile_id}/readings", headers=his, json={"systolic": 142, "diastolic": 88}),
        201,
        "Pa types this morning's blood pressure",
    )
    event_id = reading["event_id"]
    notes = f"/profiles/{profile_id}/events/{event_id}/notes"
    note_body = {
        "kind": "voice",
        "data": b64(placeholder_voice(AFTER_THE_WALK)),
        "content_type": "audio/m4a",
        "captured_at": reading["taken_at"],
        "label": "after my walk",
    }
    facts_before = check(client.get(f"/profiles/{profile_id}/facts", headers=his), 200, "Pa reads his facts")
    note = check(client.post(notes, headers=his, json=note_body), 201, "Pa leaves a voice note")
    if note["transcript"] is None or note["event_id"] != event_id:
        raise fail("Pa leaves a voice note", why=f"got {note}")
    agreed = check(client.get(f"/profiles/{profile_id}/consents", headers=his), 200, "Pa reads his consents")
    if "recording" in {c["purpose"] for c in agreed}:
        raise fail("Pa reads his consents", why="a recording consent was given, and none should be needed")
    ok(
        "Pa typed this morning's blood pressure (142/88) and left a voice note on it: his own words, kept as a "
        "voice artefact on the record consent — no recording consent asked or on file (ADR 0003) — and heard "
        f'at {note["transcript"]["confidence"]:.2f} as "{note["transcript"]["text"]}"'
    )
    recalled = check(client.get(notes, headers=bearer(mei.token)), 200, "Mei recalls the reading's notes")
    if [n["note_id"] for n in recalled] != [note["note_id"]]:
        raise fail("Mei recalls the reading's notes", why=f"got {recalled}")
    audio = client.get(f"{notes}/{note['note_id']}/content", headers=bearer(mei.token))
    if audio.status_code != 200 or audio.content != placeholder_voice(AFTER_THE_WALK):
        raise fail("Mei plays the voice note", audio, "not the bytes Pa sent")
    facts_after = check(client.get(f"/profiles/{profile_id}/facts", headers=his), 200, "Pa reads his facts again")
    if facts_after != facts_before:
        raise fail("Pa reads his facts again", why="the voice note became a fact")
    ok(
        f"Mei recalls the note on the reading and plays it back ({audio.headers['content-type']}, "
        f"{len(audio.content)} bytes, the same Pa sent): hearable, and not a fact — his facts are the "
        f"same {len(facts_after)} as before"
    )

    # 6. The blood pressure machine's screen.
    state_before = check(client.get(f"/profiles/{profile_id}/state", headers=his), 200, "Pa reads his State")
    screen = check(
        client.post(
            f"/profiles/{profile_id}/readings/photo",
            headers=his,
            json={
                "data": b64(placeholder_png(BP_CUFF)),
                "content_type": "image/png",
                "captured_at": "2026-09-13T23:43:00Z",
            },
        ),
        201,
        "Pa photographs his blood pressure machine",
    )
    read = {f["attribute"]: f["value"] for f in screen["fields"]}
    if (read.get("systolic"), read.get("diastolic"), read.get("pulse")) != (138, 84, 72):
        raise fail("Pa photographs his blood pressure machine", why=f"got {screen}")
    ok(
        "Pa photographed his blood pressure machine's screen (POST /profiles/{id}/readings/photo): "
        "read with no typing — the numbers, their units, the machine and the time on its screen:"
    )
    print_fields(screen)
    reading_done = say_yes(client, pa, profile_id, screen, decide(screen), "the screen")
    written = {f["subject"]: f for f in reading_done["facts"]}
    bp = written.get("blood_pressure", {})
    if (
        bp.get("value") != {"systolic": 138, "diastolic": 84}
        or bp.get("unit") != "mmHg"
        or written.get("heart_rate", {}).get("value") != {"pulse": 72}
        or bp.get("event_id") != reading_done["event_id"]
        or not str(bp.get("valid_from", "")).startswith("2026-09-13T23:42:00")
    ):
        raise fail("the screen: Pa confirms the card", why=f"got {reading_done}")
    state_after = check(client.get(f"/profiles/{profile_id}/state", headers=his), 200, "Pa reads his State again")
    folded = state_after["dimensions"]["clinical"]["facts"].get("blood_pressure", {}).get("reading", {})
    if (
        state_after["sequence"] <= state_before["sequence"]
        or state_after["trigger"]["fact_id"] not in {f["fact_id"] for f in reading_done["facts"]}
        or folded.get("value") != {"systolic": 138, "diastolic": 84}
    ):
        raise fail("Pa reads his State again", why=f"not recomputed from the reading: {state_after}")
    ok(
        "one yes: a reading event at 7.42 on his clock and its facts — blood_pressure.reading "
        "{systolic 138, diastolic 84} mmHg, the shape POST /readings writes, and heart_rate.reading "
        f"{{pulse 72}} — State recomputed, snapshot {state_before['sequence']} → {state_after['sequence']}, "
        f"trigger new_fact naming fact {state_after['trigger']['fact_id'][:8]}…"
    )
    wrong = check(
        client.post(
            f"/profiles/{profile_id}/readings/photo",
            headers=his,
            json={
                "data": b64(placeholder_png(LIPID_PANEL)),
                "content_type": "image/png",
                "captured_at": "2026-09-14T01:00:00Z",
            },
        ),
        201,
        "Pa sends a lab report as a machine's screen",
    )
    if wrong["fields"] != [] or wrong["notice"] != ["This does not look like the screen of a machine."]:
        raise fail("Pa sends a lab report as a machine's screen", why=f"got {wrong}")
    ok(f'a lab report sent as a machine\'s screen is an open card with no fields: "{wrong["notice"][0]}"')

    # 7. The accuracy harness over the labelled papers.
    harness = subprocess.run(
        [sys.executable, "-m", "tests.paper_accuracy"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    last = (harness.stdout.strip().splitlines() or [""])[-1]
    if harness.returncode != 0 or "100.0% read right or put in front of a person" not in last:
        raise fail("the accuracy harness", why=short(harness.stdout + harness.stderr))
    ok(f"the accuracy harness over every labelled paper (python3 -m tests.paper_accuracy): {last}")

    # 8. The refusals are on Pa's trail.
    trail = check(
        client.get(f"/profiles/{profile_id}/audit", headers=his, params={"limit": 500}),
        200,
        "Pa reads his trail",
    )
    names = {e["refused_because"] for e in trail if e["outcome"] == "refused"}
    if not {"UnreadableField", "NotAPdf"} <= names or "ConsentWithheld" in names:
        raise fail("Pa reads his trail", why=f"refusals on it: {names}")
    ok(f"Pa reads his trail ({len(trail)} lines); every refusal of this walk is on it:")
    for row in (e for e in trail if e["outcome"] == "refused"):
        who = {mei.person_id: "Mei", pa.person_id: "Pa"}.get(row["actor_person_id"], "?")
        say(f"{row['at'][:19]}  {who:>3}  {row['action']} {row['scope']} {row['target']}  refused {row['refused_because']}")


def run(base_url: str, dev_log: Path) -> int:
    """Walk checkpoint 18 against the server at `base_url`; 0 when every step is a ✓."""
    try:
        with httpx.Client(base_url=base_url, timeout=20.0) as client:
            walk(client, Path(dev_log))
    except Failed as failed:
        print(str(failed), flush=True)
        return 1
    return 0
