"""Checkpoint 13 — Family, roster and Dad's trail (E12), over HTTP only.

    make dev                # one terminal
    make checkpoint N=13    # another: this module, through scripts/checkpoint.py

Pa and Mei as in checkpoint 4 — Mei sets the profile up for Pa, this time on a lasting power
of attorney whose PDF is a redacted placeholder, and Pa claims it — then the family: Siti the
helper and Kit the son are let in and given keys; Mei narrows Siti to the medicines only and
is refused when she tries to widen; Pa marks his private notes "only me" and Mei's next read
is refused and on his trail in his words; the roster (Mei weekdays, Kit weekends) and a task
for Siti that only Siti can tap done; the family thread with a message and a reading card;
the digest for Kit; a message to Pa composed by Mei, previewed in Malay and scheduled; Pa's
trail as sentences; and the LPA uploaded, found to be the same paper the graph was set up on,
backing the stewardship.

Self-contained: every helper this module needs is here, so the shared runner only dispatches.
`run(base_url, dev_log)` prints ✓/✗ lines in the runner's style and returns 0 or 1.
"""

from __future__ import annotations

import base64
import hashlib
import os
import random
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

DEMO_LOGIN_CODE = os.environ.get("NURA_DEMO_LOGIN_CODE") or None
"""Against a demo deployment (docs/deploy.md, ADR 0008): the operator's code signs every test
number in, so no log is read, and every number is drawn from the test range (+65 0…)."""
CODE_LINE = re.compile(r"login code for (\+[0-9]+): ([0-9]{6})")
CODE_WAIT_SECONDS = 3.0
HOLD_WORDING = "1"
LPA_PDF = b"%PDF-1.4\n% nura-lpa-placeholder: a lasting power of attorney, redacted\n"

JSON = dict[str, Any]


class Failed(Exception):
    """One step did not do what the checkpoint says. Carries the printed line."""


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


def check(response: httpx.Response, status: int, what: str) -> Any:
    if response.status_code != status:
        raise fail(what, response, f"expected {status}")
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def refused(response: httpx.Response, status: int, refusal: str, what: str) -> JSON:
    body = check(response, status, what)
    if not isinstance(body, dict) or body.get("refusal") != refusal:
        raise fail(what, response, f"expected refusal {refusal}")
    return body


class Person:
    def __init__(self, name: str, phone_e164: str) -> None:
        self.name = name
        self.phone_e164 = phone_e164
        self.token = ""
        self.person_id = ""


def fresh_phone(prefix: str) -> str:
    if DEMO_LOGIN_CODE is not None:
        prefix = "+650" + prefix.removeprefix("+65")[1:]
    return f"{prefix}{random.randint(0, 9999):04d}"


class Walk:
    def __init__(self, client: httpx.Client, dev_log: Path) -> None:
        self.client = client
        self.dev_log = dev_log

    # --- signing in -----------------------------------------------------------------------

    def code_from_log(self, phone_e164: str) -> str:
        if DEMO_LOGIN_CODE is not None:
            return DEMO_LOGIN_CODE
        deadline = time.monotonic() + CODE_WAIT_SECONDS
        while True:
            if self.dev_log.exists():
                codes = [
                    m.group(2)
                    for m in CODE_LINE.finditer(self.dev_log.read_text(errors="replace"))
                    if m.group(1) == phone_e164
                ]
                if codes:
                    return codes[-1]
            if time.monotonic() > deadline:
                raise Failed(
                    f"✗ no login code for {phone_e164} appeared in {self.dev_log} within "
                    f"{CODE_WAIT_SECONDS:.0f}s; start the server with `make dev`"
                )
            time.sleep(0.2)

    def register(self, person: Person, language: str) -> None:
        who = f"{person.name} ({person.phone_e164})"
        started = self.client.post(
            "/auth/phone/start",
            json={
                "phone_e164": person.phone_e164,
                "display_name": person.name,
                "language": language,
            },
        )
        check(started, 202, f"{who} asks for a code by phone")
        code = self.code_from_log(person.phone_e164)
        session = check(
            self.client.post(
                "/auth/phone/verify", json={"phone_e164": person.phone_e164, "code": code}
            ),
            200,
            f"{who} types the code in",
        )
        person.token = session["token"]
        person.person_id = session["person_id"]
        ok(f"{who} registered by phone code and signed in (the code read from the server log)")

    # --- the yes --------------------------------------------------------------------------

    def yes(self, who: Person, profile_id: str, body: JSON, what: str) -> str:
        minted = check(
            self.client.post(
                f"/profiles/{profile_id}/confirmations", json=body, headers=bearer(who.token)
            ),
            201,
            what,
        )
        confirmation_id: str = minted["confirmation_id"]
        return confirmation_id


def walk(client: httpx.Client, dev_log: Path) -> None:
    w = Walk(client, dev_log)
    pa = Person("Pa", fresh_phone("+659333"))
    mei = Person("Mei", fresh_phone("+659444"))
    kit = Person("Kit", fresh_phone("+659555"))
    siti = Person("Siti", fresh_phone("+659666"))
    digest = hashlib.sha256(LPA_PDF).hexdigest()

    # 1. Mei sets Pa up on a lasting power of attorney, and Pa claims — as in checkpoint 4.
    w.register(mei, "en")
    opened = check(
        client.post(
            "/profiles/for-someone",
            headers=bearer(mei.token),
            json={
                "patient_phone_e164": pa.phone_e164,
                "display_name": pa.name,
                "language": "ms",
                "consent": {
                    "wording_version": HOLD_WORDING,
                    "language": "en",
                    "captured_via": "app",
                },
                "basis": "lpa",
                "relationship": "daughter",
                "evidence": {
                    "kind": "pdf",
                    "storage_key": f"documents/{digest}",
                    "content_type": "application/pdf",
                    "sha256": digest,
                    "captured_at": "2026-09-01T09:00:00Z",
                },
            },
        ),
        201,
        "Mei sets up a profile for Pa on a lasting power of attorney",
    )
    profile_id: str = opened["profile_id"]
    if opened["standing"] != "steward" or opened["basis" if "basis" in opened else "role"] not in (
        "chief",
        "lpa",
    ):
        raise fail("Mei sets up a profile for Pa on a lasting power of attorney", why=str(opened))
    ok(
        f"Mei set up a profile for Pa ({pa.phone_e164}) on the basis of a lasting power of "
        f"attorney, citing its PDF by digest {digest[:8]}…; she is its steward"
    )
    w.register(pa, "ms")
    minted = w.yes(
        pa, profile_id, {"subject": "claim", "language": "ms"}, "Pa says OK to the claim"
    )
    claimed = check(
        client.post(
            f"/profiles/{profile_id}/claim",
            headers=bearer(pa.token),
            json={"confirmation_id": minted, "language": "ms"},
        ),
        200,
        "Pa claims the profile",
    )
    if claimed["standing"] != "owner":
        raise fail("Pa claims the profile", why=str(claimed))
    ok("Pa claimed the profile: he is its owner, Mei his chief on his own consent")

    # 2. Pa lets Siti and Kit in; Mei cuts the keys.
    w.register(siti, "ms")
    w.register(kit, "en")
    for person, scopes, relationship in (
        (siti, ["medicines", "emergency", "send"], "helper"),
        (kit, ["medicines", "visits", "readings", "records", "emergency", "family"], "son"),
    ):
        check(
            client.post(
                f"/profiles/{profile_id}/consents/sharing",
                headers=bearer(pa.token),
                json={
                    "holder_person_id": person.person_id,
                    "scopes": scopes,
                    "relationship": relationship,
                    "language": "ms",
                    "captured_via": "app",
                },
            ),
            201,
            f"Pa agrees to let {person.name} in",
        )
    ok("Pa agreed, in Malay, to let Siti (his helper) and Kit (his son) see named parts")
    siti_key = check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=bearer(mei.token),
            json={"holder_person_id": siti.person_id, "role": "helper"},
        ),
        201,
        "Mei cuts Siti a helper key",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=bearer(mei.token),
            json={
                "holder_person_id": kit.person_id,
                "role": "caregiver",
                "scopes": ["medicines", "visits", "readings", "records", "emergency", "family"],
            },
        ),
        201,
        "Mei cuts Kit a caregiver key",
    )
    helpers = check(
        client.get(f"/profiles/{profile_id}/helpers", headers=bearer(mei.token)),
        200,
        "Mei reads the helper list",
    )
    if [h["name"] for h in helpers["helpers"]] != ["Siti"]:
        raise fail("Mei reads the helper list", why=str(helpers))
    ok("Mei cut Siti a helper key and Kit a caregiver key; the helper list, in Pa's words:")
    for line in helpers["helpers"][0]["lines"]:
        print(f"    {line}")

    # 3. Mei narrows Siti to the medicines only; widening is refused.
    yes = w.yes(
        mei,
        profile_id,
        {"subject": "key_change", "key_id": siti_key["key_id"], "scopes": ["medicines"]},
        "Mei says yes to narrowing Siti's key",
    )
    narrowed = check(
        client.put(
            f"/profiles/{profile_id}/keys/{siti_key['key_id']}",
            headers=bearer(mei.token),
            json={"scopes": ["medicines"], "confirmation_id": yes},
        ),
        200,
        "Mei narrows Siti's key to the medicines",
    )
    if narrowed["scopes"] != ["medicines", "profile"] or narrowed["key_id"] != siti_key["key_id"]:
        raise fail("Mei narrows Siti's key to the medicines", why=str(narrowed))
    ok("Mei narrowed Siti's key in place to the medicines only, on her own yes (PUT /keys/{key})")
    refused(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=bearer(mei.token),
            json={
                "subject": "key_change",
                "key_id": siti_key["key_id"],
                "scopes": ["medicines", "readings"],
            },
        ),
        403,
        "WouldWiden",
        "Mei tries to widen Siti's key to the readings",
    )
    ok(
        "widening Siti's key to the readings was refused: WouldWiden (403) — wider is a fresh "
        "consent from Pa and a new key"
    )
    refused(
        client.get(f"/profiles/{profile_id}/roster", headers=bearer(siti.token)),
        403,
        "OutOfScope",
        "Siti reads the roster with a medicines-only key",
    )
    ok("Siti's narrowed key opens the medicines and nothing else: the roster refuses her (403)")

    # 4. Pa marks his private notes "only me"; Mei's read is refused and on his trail.
    check(
        client.post(
            f"/profiles/{profile_id}/notes",
            headers=bearer(pa.token),
            json={"text": "I did not tell the children about the fall."},
        ),
        201,
        "Pa writes a private note",
    )
    # The chief key from the claim opens everything but the notes (the steward never held
    # them); Pa now lets Mei in to those too, in words that name them, and cuts her key again.
    check(
        client.post(
            f"/profiles/{profile_id}/consents/sharing",
            headers=bearer(pa.token),
            json={
                "holder_person_id": mei.person_id,
                "scopes": [
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
                ],
                "relationship": "daughter",
                "language": "ms",
                "captured_via": "app",
            },
        ),
        201,
        "Pa agrees to let Mei see his private notes too",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=bearer(pa.token),
            json={"holder_person_id": mei.person_id, "role": "chief"},
        ),
        201,
        "Pa cuts Mei a chief key over everything",
    )
    check(
        client.get(f"/profiles/{profile_id}/notes", headers=bearer(mei.token)),
        200,
        "Mei reads Pa's notes as his chief",
    )
    ok(
        "Pa let Mei in to his private notes as well (a fresh consent naming them, a chief key "
        "cut again); Mei reads the note"
    )
    yes = w.yes(pa, profile_id, {"subject": "only_me", "scope": "notes"}, "Pa says yes to only me")
    check(
        client.post(
            f"/profiles/{profile_id}/privacy",
            headers=bearer(pa.token),
            json={"scope": "notes", "confirmation_id": yes},
        ),
        201,
        "Pa marks his notes only me",
    )
    notes = client.get(f"/profiles/{profile_id}/notes", headers=bearer(mei.token))
    body = refused(notes, 403, "OutOfScope", "Mei reads Pa's notes after the mark")
    if body.get("scope") != "notes" or "fall" in notes.text:
        raise fail("Mei reads Pa's notes after the mark", notes, "expected scope notes, no text")
    ok(
        "Pa marked his private notes only me (his own yes); Mei, who read them a moment ago as "
        "his chief, is refused at once: OutOfScope notes (403), the note never left"
    )
    trail = check(
        client.get(
            f"/profiles/{profile_id}/trail",
            headers=bearer(pa.token),
            params={"language": "en"},
        ),
        200,
        "Pa reads his trail in words",
    )
    sentences = [line["sentences"] for day in trail for line in day["lines"]]
    only_you = [
        s
        for s in sentences
        if len(s) == 2
        and s[0].startswith("Mei asked to see your private notes on ")
        and s[1] == "Only you can."
    ]
    if not only_you:
        raise fail("Pa reads his trail in words", why=f"no only-you line; got {sentences[:6]}")
    ok(f"and it is on Pa's trail in his words: {' '.join(only_you[0])}")

    # 5. The roster: Mei on weekdays, Kit at weekends; a task for Siti that only Siti taps done.
    for person, role, weekdays in ((mei, "chief", [0, 1, 2, 3, 4]), (kit, "caregiver", [5, 6])):
        check(
            client.post(
                f"/profiles/{profile_id}/roster",
                headers=bearer(mei.token),
                json={
                    "person_id": person.person_id,
                    "role": role,
                    "weekdays": weekdays,
                    "from_time": "07:00:00",
                    "to_time": "22:00:00",
                },
            ),
            201,
            f"Mei puts {person.name} on the roster",
        )
    saturday = datetime(2026, 9, 19, 4, 0, tzinfo=UTC)  # Saturday noon on Pa's wall
    on_duty = check(
        client.get(
            f"/profiles/{profile_id}/roster/on-duty",
            headers=bearer(mei.token),
            params={"at": saturday.isoformat()},
        ),
        200,
        "Mei asks who is on duty on Saturday",
    )
    if [d["person_id"] for d in on_duty] != [kit.person_id]:
        raise fail("Mei asks who is on duty on Saturday", why=str(on_duty))
    ok(
        "the roster: Mei Monday to Friday, Kit at the weekend, 7 in the morning to 10 at night "
        "on Pa's wall clock; on Saturday 19 September at noon Kit is on duty"
    )
    task = check(
        client.post(
            f"/profiles/{profile_id}/tasks",
            headers=bearer(mei.token),
            json={"what": "buy the water pill", "assigned_person_id": siti.person_id},
        ),
        201,
        "Mei gives Siti a task",
    )
    refused(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=bearer(mei.token),
            json={"subject": "task_done", "task_id": task["task_id"]},
        ),
        403,
        "NotTheDoer",
        "Mei tries to tap Siti's task done",
    )
    mine = check(
        client.get(
            f"/profiles/{profile_id}/tasks", headers=bearer(siti.token), params={"mine": "true"}
        ),
        200,
        "Siti reads her tasks",
    )
    if [t["task_id"] for t in mine] != [task["task_id"]]:
        raise fail("Siti reads her tasks", why=str(mine))
    yes = w.yes(
        siti, profile_id, {"subject": "task_done", "task_id": task["task_id"]}, "Siti taps done"
    )
    done = check(
        client.post(
            f"/profiles/{profile_id}/tasks/{task['task_id']}/done",
            headers=bearer(siti.token),
            json={"confirmation_id": yes},
        ),
        200,
        "Siti marks her task done",
    )
    if done["done_by_person_id"] != siti.person_id:
        raise fail("Siti marks her task done", why=str(done))
    ok(
        'a task "buy the water pill" for Siti: Mei tapping it done is refused, NotTheDoer '
        "(403); Siti sees it with her medicines-only key and taps it done herself"
    )

    # 6. The thread: a message from Mei, a reading card between; the digest for Kit.
    check(
        client.post(
            f"/profiles/{profile_id}/thread",
            headers=bearer(mei.token),
            json={"text": "Pa slept well. I will come by at 6."},
        ),
        201,
        "Mei posts to the family thread",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/readings",
            headers=bearer(pa.token),
            json={"systolic": 138, "diastolic": 84},
        ),
        201,
        "Pa adds a blood-pressure reading",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/thread",
            headers=bearer(mei.token),
            json={"card_kind": "reading"},
        ),
        201,
        "Mei puts the reading card into the thread",
    )
    page = check(
        client.get(f"/profiles/{profile_id}/thread", headers=bearer(kit.token)),
        200,
        "Kit reads the thread",
    )
    kinds = [e["card_kind"] for e in page["entries"]]
    if kinds[:2] != ["reading", None]:
        raise fail("Kit reads the thread", why=f"entries {kinds}")
    ok(
        "the family thread: Mei's message, then the reading card (a reference to the State it "
        "was rendered from, never words); Kit reads it newest first"
    )
    since = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    summary = check(
        client.get(
            f"/profiles/{profile_id}/thread/digest",
            headers=bearer(kit.token),
            params={"since": since, "language": "en"},
        ),
        200,
        "Kit reads his digest",
    )
    if "It was 138 over 84." not in summary["lines"]:
        raise fail("Kit reads his digest", why=str(summary["lines"]))
    ok("the digest for Kit, every line through the plain-words verifier:")
    for entry in (
        [summary["headline"]]
        + [
            line
            for e in summary["entries"]
            for line in e["lines"] + ([e["text"]] if e["text"] else [])
        ]
        + summary["lines"][-1:]
    ):
        print(f"    {entry}")

    # 7. Mei composes a message to Pa, previews it in Malay, schedules it.
    compose = {"template_id": "pickup", "slots": {"who": "Mei", "when": "pukul 9"}}
    preview = check(
        client.post(
            f"/profiles/{profile_id}/pushes/preview", headers=bearer(mei.token), json=compose
        ),
        200,
        "Mei previews a message to Pa",
    )
    if preview["language"] != "ms":
        raise fail("Mei previews a message to Pa", why=str(preview))
    when = {
        "send_at": (datetime.now(UTC) + timedelta(hours=8)).isoformat(),
        "channel": "whatsapp",
        "expires_at": (datetime.now(UTC) + timedelta(hours=12)).isoformat(),
    }
    yes = w.yes(
        mei, profile_id, {"subject": "push", **compose, **when}, "Mei says yes to the message"
    )
    scheduled = check(
        client.post(
            f"/profiles/{profile_id}/pushes",
            headers=bearer(mei.token),
            json={**compose, **when, "confirmation_id": yes},
        ),
        201,
        "Mei schedules the message",
    )
    if scheduled["lines"] != preview["lines"] or not scheduled["state_id"]:
        raise fail("Mei schedules the message", why=str(scheduled))
    ok(
        "Mei composed a message to Pa from a template; the preview, exactly as he will see it, in Malay:"
    )
    for line in preview["lines"]:
        print(f"    {line}")
    ok(
        "and scheduled it for 8 hours from now on WhatsApp, on her yes for exactly those lines, "
        "stamped with the State it was composed against; nothing is sent here (E11 delivers)"
    )

    # 8. Pa reads his trail as sentences, in Malay.
    trail = check(
        client.get(f"/profiles/{profile_id}/trail", headers=bearer(pa.token)),
        200,
        "Pa reads his trail",
    )
    shown = 0
    ok(f"Pa reads his trail as sentences in his language, {len(trail)} day(s), newest first:")
    for day in trail:
        print(f"    {day['day_words']}")
        for line in day["lines"]:
            if shown >= 8:
                break
            print(f"      {' '.join(line['sentences'])}")
            shown += 1
    raw = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}|OutOfScope|NoKey|audit_entry|state_snapshot")
    if any(raw.search(s) for day in trail for line in day["lines"] for s in line["sentences"]):
        raise fail("Pa reads his trail", why="a sentence carried a class name or an id")
    ok("no sentence on it carries a class name, a table name or an id")

    # 9. Mei uploads the LPA PDF: the same paper the graph was set up on.
    docs = check(
        client.post(
            f"/profiles/{profile_id}/documents",
            headers=bearer(mei.token),
            json={
                "data": base64.b64encode(LPA_PDF).decode(),
                "content_type": "application/pdf",
                "captured_at": "2026-09-01T09:00:00Z",
                "tag": "lpa",
            },
        ),
        201,
        "Mei uploads the LPA PDF",
    )
    if len(docs) != 1 or docs[0]["tag"] != "lpa" or docs[0]["sha256"] != digest:
        raise fail("Mei uploads the LPA PDF", why=str(docs))
    backs = {(b["kind"], b["basis"]) for b in docs[0]["backs"]}
    if ("stewardship", "lpa") not in backs or ("consent", "lpa") not in backs:
        raise fail("Mei uploads the LPA PDF", why=f"backs {backs}")
    ok(
        "Mei uploaded the LPA PDF placeholder: found by its digest to be the paper the graph was "
        "set up on — one artefact, now with its bytes — tagged lpa, and listed under documents "
        "backing the stewardship and the agreement Mei gave for Pa on that basis"
    )


def run(base_url: str, dev_log: Path) -> int:
    """Walk checkpoint 13 against the server at `base_url`; 0 when every step is a ✓."""
    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            walk(client, Path(dev_log))
    except Failed as failed:
        print(str(failed), flush=True)
        return 1
    return 0
