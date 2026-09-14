"""Checkpoint 16 — Timeline, providers, what changed, Ask (E03), over HTTP only.

    make dev                # one terminal
    make checkpoint N=16    # another: this module, through scripts/checkpoint.py

Pa, in English so every line can be read here, with two blood pressures, his blood pressure
tablet added from a label that names Dr Tan (POST /medicines, with his yes), a check-up with
Dr Tan that happened ten days ago, and a visit to Dr Tan a week from now inside the chest
infection he is going through. The timeline's three anchors and its first page. Pa's lab
paper, and Mei — his chief — putting it with the illness on her own yes. The providers
directory, Mei's note about the clinic ("parking at B2"), and a note naming a medicine
refused. Mei's what changed, read twice with a write between. Pa asks by voice and hears one
cited line; Mei asks in text and reads lines with their citations; a question nothing on the
record answers gets the honest line and the boundary. Pa's trail holds the refusal, the asks
and the looks.

Self-contained, like checkpoint 13: every helper this module needs is here, so the shared
runner only dispatches. `run(base_url, dev_log)` prints ✓/✗ lines and returns 0 or 1.
"""

from __future__ import annotations

import base64
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
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
LIPID_PANEL = "lipid-panel-2023-09-07"
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


def placeholder_png(label: str) -> bytes:
    """The bytes standing in for one redacted paper — the same as `backend/tests/paper.py`,
    so the fixture extractor recognises the digest."""
    return PNG_SIGNATURE + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"


def cited(line: JSON) -> str:
    return ", ".join(f"{c['kind']} {c['id'][:8]}…" for c in line["cites"])


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

    def post(self, who: Person, path: str, body: JSON, status: int, what: str) -> Any:
        return check(self.client.post(path, json=body, headers=bearer(who.token)), status, what)

    def get(self, who: Person, path: str, what: str, **params: Any) -> Any:
        return check(self.client.get(path, params=params, headers=bearer(who.token)), 200, what)

    def visit(
        self,
        who: Person,
        profile_id: str,
        provider_id: str,
        at: datetime,
        purpose: str,
        *,
        steps: tuple[str, ...] = (),
        episode_id: str | None = None,
    ) -> JSON:
        """Write down a visit on the person's yes, then walk its status, a yes a step."""
        when = at.isoformat()
        yes = self.yes(
            who,
            profile_id,
            {
                "subject": "appointment",
                "provider_id": provider_id,
                "scheduled_at": when,
                "purpose": purpose,
            },
            f"{who.name} says yes to the visit ({purpose})",
        )
        visit: JSON = self.post(
            who,
            f"/profiles/{profile_id}/appointments",
            {
                "provider_id": provider_id,
                "scheduled_at": when,
                "purpose": purpose,
                "confirmation_id": yes,
                "episode_id": episode_id,
            },
            201,
            f"{who.name} writes down the visit ({purpose})",
        )
        for status in steps:
            step = self.yes(
                who,
                profile_id,
                {
                    "subject": "appointment_status",
                    "appointment_id": visit["appointment_id"],
                    "status": status,
                },
                f"{who.name} says yes to the visit being {status}",
            )
            visit = self.post(
                who,
                f"/profiles/{profile_id}/appointments/{visit['appointment_id']}/status",
                {"status": status, "confirmation_id": step},
                200,
                f"{who.name} marks the visit {status}",
            )
        return visit


def walk(client: httpx.Client, dev_log: Path) -> None:
    w = Walk(client, dev_log)
    pa = Person("Pa", fresh_phone("+659111"))
    mei = Person("Mei", fresh_phone("+659222"))
    now = datetime.now(UTC)

    # 1. Pa, his record: readings, Dr Tan, the illness, a check-up that happened, a visit to come.
    w.register(pa, "en")
    opened = w.post(
        pa,
        "/profiles/mine",
        {
            "consent": {"wording_version": HOLD_WORDING, "language": "en", "captured_via": "app"},
            "display_name": pa.name,
            "language": "en",
        },
        201,
        "Pa opens his own profile",
    )
    profile_id: str = opened["profile_id"]
    base = f"/profiles/{profile_id}"
    tan = w.post(pa, f"{base}/providers", {"name": "Dr Tan", "kind": "doctor"}, 201, "Pa adds Dr Tan")
    episode = w.post(
        pa,
        f"{base}/episodes",
        {"kind": "illness", "label": "chest infection"},
        201,
        "Pa writes down the chest infection",
    )
    w.post(
        pa,
        f"{base}/readings",
        {"systolic": 146, "diastolic": 90, "taken_at": (now - timedelta(days=6)).isoformat()},
        201,
        "Pa adds a blood pressure from six days ago",
    )
    w.post(
        pa,
        f"{base}/readings",
        {
            "systolic": 138,
            "diastolic": 84,
            "taken_at": (now - timedelta(days=1)).isoformat(),
            "episode_id": episode["episode_id"],
        },
        201,
        "Pa adds yesterday's blood pressure, during the illness",
    )
    checkup = w.visit(
        pa,
        profile_id,
        tan["provider_id"],
        now - timedelta(days=10),
        "check-up",
        steps=("confirmed", "attended"),
    )
    upcoming = w.visit(
        pa,
        profile_id,
        tan["provider_id"],
        now + timedelta(days=7),
        "see Dr Tan again",
        episode_id=episode["episode_id"],
    )
    ok(
        "Pa's record: Dr Tan in his directory (POST /providers); the chest infection open "
        "(POST /episodes); two blood pressures, 146/90 six days ago and 138/84 yesterday during "
        "the illness; a check-up with Dr Tan ten days ago, confirmed then attended — each step "
        "on its own yes (POST /confirmations, subjects appointment and appointment_status); and "
        "a visit to Dr Tan in a week, inside the illness"
    )

    # 2. A medicine, from a label that names Dr Tan, on Pa's yes.
    photo = w.post(
        pa,
        f"{base}/photos",
        {
            "data": base64.b64encode(
                placeholder_png(f"label-{random.randint(0, 10**9)}")
            ).decode(),
            "content_type": "image/png",
            "captured_at": now.isoformat(),
        },
        201,
        "Pa photographs the label",
    )
    label = {
        "generic": "amlodipine",
        "strength": "5 mg",
        "dose_text": "1 biji sekali sehari pagi",
        "quantity": 30,
        "prescriber": "Dr Tan",
        "source_kind": "retail",
    }
    yes = w.yes(
        pa,
        profile_id,
        {"subject": "medicine", "label": label, "source_artifact_id": photo["artifact_id"]},
        "Pa says yes to the label",
    )
    medicine = w.post(
        pa,
        f"{base}/medicines",
        {"label": label, "source_artifact_id": photo["artifact_id"], "confirmation_id": yes},
        201,
        "Pa adds the medicine",
    )
    ok(
        f"Pa added {medicine['generic']} {medicine['strength']} from the label photo (POST "
        "/medicines with the label and his yes): the label names Dr Tan"
    )

    # 3. The lab paper, confirmed as read.
    card = w.post(
        pa,
        f"{base}/photos",
        {
            "data": base64.b64encode(placeholder_png(LIPID_PANEL)).decode(),
            "content_type": "image/png",
            "captured_at": now.isoformat(),
        },
        201,
        "Pa photographs the lab paper",
    )
    decisions = [{"field_id": f["field_id"], "decision": "confirmed"} for f in card["fields"]]
    yes = w.yes(
        pa,
        profile_id,
        {"subject": "review_card", "card_id": card["card_id"], "decisions": decisions},
        "Pa says yes to the lab paper as read",
    )
    done = w.post(
        pa,
        f"{base}/review-cards/{card['card_id']}/confirm",
        {"decisions": decisions, "confirmation_id": yes},
        200,
        "Pa confirms the lab paper",
    )
    ok(
        f"Pa's lab paper read and confirmed: {len(done['facts'])} facts resting on the photo "
        f"{card['artifact_id'][:8]}…, dated on the paper"
    )

    # 4. The timeline: the three anchors and the first page.
    page = w.get(pa, f"{base}/timeline", "Pa opens his timeline", limit=2)
    anchors = [a["key"] for a in page["header"]]
    if anchors != ["last_checkup", "last_visit", "next_visit"] or any(
        "Dr Tan" not in a["line"] for a in page["header"]
    ):
        raise fail("Pa opens his timeline", why=f"expected the three anchors naming Dr Tan: {page}")
    if [i["id"] for i in page["items"]] != [upcoming["appointment_id"], episode["episode_id"]]:
        raise fail("Pa opens his timeline", why=f"expected the next visit, then the illness: {page}")
    rest = w.get(
        pa, f"{base}/timeline", "Pa pages on", limit=2, cursor=page["next_cursor"]
    )
    if [i["id"] for i in rest["items"]] != [checkup["appointment_id"]]:
        raise fail("Pa pages on", why=f"expected the check-up: {rest}")
    ok(
        "GET /profiles/{id}/timeline: the three anchors of the spine, in his words with the day, "
        "then the first page newest first — the visit to come, then the illness with the reading "
        "taken during it — and the cursor to the check-up:"
    )
    for anchor in page["header"]:
        print(f"    {anchor['line']}")
    for item in [*page["items"], *rest["items"]]:
        what = item["provider"]["name"] if item["provider"] else item["episode"]["label"]
        print(
            f"    [{item['kind']:<11}] {item['at'][:10]}  {what}  "
            f"({len(item['artifacts'])} papers, {len(item['events'])} events, "
            f"{len(item['facts'])} facts)"
        )

    # 5. Mei, his chief, puts the lab photo with the illness on her own yes.
    w.register(mei, "en")
    w.post(
        pa,
        f"{base}/consents/sharing",
        {
            "holder_phone_e164": mei.phone_e164,
            "holder_display_name": mei.name,
            "scopes": EVERY_PART,
            "relationship": "daughter",
            "language": "en",
            "captured_via": "app",
        },
        201,
        "Pa agrees to let Mei in",
    )
    w.post(
        pa,
        f"{base}/keys",
        {"holder_phone_e164": mei.phone_e164, "role": "chief"},
        201,
        "Pa cuts Mei a chief key",
    )
    yes = w.yes(
        mei,
        profile_id,
        {"subject": "attach", "artifact_id": card["artifact_id"], "episode_id": episode["episode_id"]},
        "Mei says yes to putting the lab photo with the illness",
    )
    hung = w.post(
        mei,
        f"{base}/episodes/{episode['episode_id']}/attach",
        {"artifact_id": card["artifact_id"], "confirmation_id": yes},
        201,
        "Mei puts the lab photo with the illness",
    )
    view = w.get(mei, f"{base}/episodes/{episode['episode_id']}", "Mei opens the illness")
    if [a["artifact_id"] for a in view["episode"]["artifacts"]] != [card["artifact_id"]] or (
        hung["attached_by_person_id"] != mei.person_id
    ):
        raise fail("Mei opens the illness", why=f"the photo does not hang there in her name: {view}")
    ok(
        "Pa agreed to let Mei, his daughter, in and cut her a chief key; Mei put the lab photo with "
        "the chest infection on her own yes (POST /episodes/{e}/attach, subject attach) — the "
        f"illness now holds {len(view['episode']['artifacts'])} paper, "
        f"{len(view['episode']['events'])} event and {len(view['episode']['facts'])} facts, "
        f"and the visit to come ({len(view['visits'])})"
    )

    # 6. The providers directory, and Mei's note about the place.
    notes = f"{base}/providers/{tan['provider_id']}/notes"
    w.post(mei, notes, {"text": "parking at B2"}, 201, "Mei writes a note about the clinic")
    refused(
        client.post(notes, json={"text": "warfarin at night"}, headers=bearer(mei.token)),
        400,
        "NoteNamesHealth",
        "Mei writes a note naming a medicine",
    )
    listed = w.get(mei, f"{base}/providers", "Mei opens the providers directory")
    history = w.get(mei, f"{base}/providers/{tan['provider_id']}", "Mei opens Dr Tan")
    if [n["text"] for n in history["notes"]] != ["parking at B2"] or len(history["visits"]) != 2:
        raise fail("Mei opens Dr Tan", why=f"expected two visits and her note: {history}")
    ok(
        f"the providers directory (GET /providers): {', '.join(p['provider']['name'] + ' — ' + str(p['visits']) + ' visits' for p in listed)}; "
        f"Dr Tan's history: {len(history['visits'])} visits, {len(history['papers'])} paper "
        f"(through the illness), {len(history['medicines'])} medicine on his name, and Mei's note "
        f'"{history["notes"][0]["text"]}" — the chief\'s alone; a note naming a medicine was '
        "refused, NoteNamesHealth (400), and nothing of it was kept"
    )

    # 7. What changed, read twice with a write between.
    first = w.get(mei, f"{base}/changes", "Mei reads what changed")
    if not first["first_look"]:
        raise fail("Mei reads what changed", why=f"expected her first look: {first}")
    ok(f"Mei's first look at what changed (GET /changes, {len(first['lines'])} lines):")
    for line in first["lines"]:
        print(f"    {line['text']}")
    for line in first["waiting"]:
        print(f"    (still waiting) {line['text']}")
    w.post(pa, f"{base}/readings", {"systolic": 132, "diastolic": 80}, 201, "Pa adds a blood pressure")
    second = w.get(mei, f"{base}/changes", "Mei reads what changed again")
    keys = [line["key"] for line in second["lines"]]
    if second["first_look"] or keys != ["new_fact"] or second["since"] != first["looked_at"]:
        raise fail("Mei reads what changed again", why=f"expected only the new reading: {second}")
    ok(
        "Pa added 132/80; Mei's second look counts from her first and says only that: "
        f'"{second["lines"][0]["text"]}" (fact {second["lines"][0]["refs"]["fact_ids"][0][:8]}…)'
    )

    # 8. Ask: Pa by voice, Mei in text, and a question nothing answers.
    voice = w.post(
        pa,
        f"{base}/ask",
        {"question": "what was my blood pressure", "mode": "voice"},
        200,
        "Pa asks by voice",
    )
    if len(voice["lines"]) != 1 or not voice["lines"][0]["cites"]:
        raise fail("Pa asks by voice", why=f"expected one cited line: {voice}")
    if voice["spoken"][-1] != "Ask Dr Tan.":
        raise fail("Pa asks by voice", why=f"expected the boundary last: {voice}")
    ok(
        'Pa asked by voice, "what was my blood pressure" (POST /ask, mode voice): one line, citing '
        f"{cited(voice['lines'][0])}, then the boundary; what he hears:"
    )
    for line in voice["spoken"]:
        print(f"    {line}")
    text = w.post(
        mei, f"{base}/ask", {"question": "what did Dr Tan say"}, 200, "Mei asks in text"
    )
    if not text["answered"] or any(not line["cites"] for line in text["lines"]):
        raise fail("Mei asks in text", why=f"expected cited lines: {text}")
    ok('Mei asked in text, "what did Dr Tan say": every line cites what it rests on:')
    for line in text["lines"]:
        print(f"    {line['text']}  ({cited(line)})")
    for line in text["boundary"]:
        print(f"    {line}")
    honest = w.post(
        pa, f"{base}/ask", {"question": "do I have cancer"}, 200, "Pa asks what is not written down"
    )
    if honest["answered"] or honest["honest"][0] != "Nura does not have that written down.":
        raise fail("Pa asks what is not written down", why=f"expected the honest line: {honest}")
    ok('"do I have cancer": nothing on the record answers it, so nothing is guessed:')
    for line in honest["spoken"]:
        print(f"    {line}")

    # 9. The trail.
    trail = w.get(pa, f"{base}/audit", "Pa reads his trail", limit=500)
    note_refused = [
        e
        for e in trail
        if e["refused_because"] == "NoteNamesHealth" and e["actor_person_id"] == mei.person_id
    ]
    asks = [e for e in trail if e["target"] == "ask" and e["outcome"] == "allowed"]
    looks = [e for e in trail if e["target"] == "last_looked" and e["action"] == "write"]
    if not note_refused or len(asks) != 3 or len(looks) != 2:
        raise fail(
            "Pa reads his trail",
            why=f"refused note {len(note_refused)}, asks {len(asks)}, looks {len(looks)}",
        )
    ok(
        f"Pa reads his trail ({len(trail)} lines): Mei's refused note by name, the three asks — "
        "each naming the question kept as a message by reference, never its words — and Mei's "
        "two looks"
    )


def run(base_url: str, dev_log: Path) -> int:
    """Walk checkpoint 16 against the server at `base_url`; 0 when every step is a ✓."""
    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            walk(client, Path(dev_log))
    except Failed as failed:
        print(str(failed), flush=True)
        return 1
    return 0
