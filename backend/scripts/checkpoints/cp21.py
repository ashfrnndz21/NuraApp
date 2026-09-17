"""Checkpoint 21 — the feeling cloud and smart nudges (E17), over HTTP only.

    make dev                # one terminal
    make checkpoint N=21    # another: this module, through scripts/checkpoint.py

Pa, in Malay, with Mei as his chief. Pa has Dr Tan in his directory and a visit with him the
day after tomorrow; he adds the blood pressure tablet (amlodipine) from a label photo on his
yes, taps Taken once, and types in a blood pressure. The cloud in Malay puts "Pening" (dizzy)
first, because the licensed monograph of the new medicine lists it; Pa taps it, answers
"since yesterday", and the note says what to tell Dr Tan and ends on the boundary. Pa taps
"chest pain": the red-flag path — the flag, the family told, the ladder — and no note. Today
has no nudge (a red flag today); tomorrow's plan is the visit, one a day, in the daytime, with
the proud number held; it is handed to delivery and Pa accepts it. Mei reads the metrics:
counts, and nothing else. The Me page says the number that only goes up.

Self-contained: every helper this module needs is here, so the shared runner only dispatches.
`run(base_url, dev_log)` prints ✓/✗ lines in the runner's style and returns 0 or 1.
"""

from __future__ import annotations

import base64
import os
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

DEMO_LOGIN_CODE = os.environ.get("NURA_DEMO_LOGIN_CODE") or None
"""Against a demo deployment (docs/deploy.md, ADR 0008): the operator's code signs every test
number in, so no log is read, and every number is drawn from the test range (+65 0…)."""
CODE_LINE = re.compile(r"login code for (\+[0-9]+): ([0-9]{6})")
CODE_WAIT_SECONDS = 3.0
HOLD_WORDING = "1"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
WALL = ZoneInfo("Asia/Singapore")
"""`make dev` serves Singapore (NURA_REGION=SG): his wall clock."""
MS_DAYS = ("Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad")
MS_MONTHS = (
    "Januari", "Februari", "Mac", "April", "Mei", "Jun",
    "Julai", "Ogos", "September", "Oktober", "November", "Disember",
)
"""Mirrors `app.medicines.strings.DAY_NAMES`/`MONTH_NAMES` ("ms") — kept here, not imported,
since this module is a client and nothing more."""


def say_date_ms(day: datetime) -> str:
    """`Weekday D Month`, in Malay, the way `app.medicines.strings.say_date` renders it (PR
    #233 review): `FeelingNote.lines` anchors "since yesterday" to the day he answered, fixed
    at compose time, so a note read back later never goes stale or false."""
    return f"{MS_DAYS[day.weekday()]} {day.day} {MS_MONTHS[day.month - 1]}"
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
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

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


def show(lines: list[str]) -> None:
    for line in lines:
        print(f"    {line}", flush=True)


def check(response: httpx.Response, status: int, what: str) -> Any:
    if response.status_code != status:
        raise fail(what, response, f"expected {status}")
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def placeholder_png(label: str) -> bytes:
    """Bytes the fixture extractor does not know: a label photo it reads nothing off."""
    return PNG_SIGNATURE + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"


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
        check(
            self.client.post(
                "/auth/phone/start",
                json={
                    "phone_e164": person.phone_e164,
                    "display_name": person.name,
                    "language": language,
                },
            ),
            202,
            f"{who} asks for a code by phone",
        )
        session = check(
            self.client.post(
                "/auth/phone/verify",
                json={
                    "phone_e164": person.phone_e164,
                    "code": self.code_from_log(person.phone_e164),
                },
            ),
            200,
            f"{who} types the code in",
        )
        person.token = session["token"]
        person.person_id = session["person_id"]
        ok(f"{who} registered by phone code (no SMS; the six digits read from the server log)")

    def post(
        self, who: Person, path: str, body: JSON | None, status: int, what: str, **params: Any
    ) -> Any:
        return check(
            self.client.post(path, json=body, params=params or None, headers=bearer(who.token)),
            status,
            what,
        )

    def get(self, who: Person, path: str, what: str, **params: Any) -> Any:
        return check(
            self.client.get(path, params=params or None, headers=bearer(who.token)), 200, what
        )

    def yes(self, who: Person, profile_id: str, body: JSON, what: str) -> str:
        minted = self.post(who, f"/profiles/{profile_id}/confirmations", body, 201, what)
        confirmation_id: str = minted["confirmation_id"]
        return confirmation_id


def walk(client: httpx.Client, dev_log: Path) -> None:
    w = Walk(client, dev_log)
    pa = Person("Pa", fresh_phone("+659711"))
    mei = Person("Mei", fresh_phone("+659722"))
    today = datetime.now(WALL).date()
    tomorrow = today + timedelta(days=1)

    # 1. Pa, in Malay, and Mei, his chief.
    w.register(pa, "ms")
    opened = w.post(
        pa,
        "/profiles/mine",
        {
            "consent": {"wording_version": HOLD_WORDING, "language": "ms", "captured_via": "app"},
            "language": "ms",
        },
        201,
        "Pa opens his own profile",
    )
    profile_id: str = opened["profile_id"]
    base = f"/profiles/{profile_id}"
    w.register(mei, "en")
    w.post(
        pa,
        f"{base}/consents/sharing",
        {
            "holder_phone_e164": mei.phone_e164,
            "holder_display_name": mei.name,
            "scopes": EVERY_PART,
            "role": "chief",
            "window": "always",
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
    ok(
        "Pa opened his profile in Malay, let Mei, his daughter, in to everything and cut her the chief key"
    )

    # 2. Dr Tan, and a visit the day after tomorrow at 10 on his wall.
    tan = w.post(
        pa, f"{base}/providers", {"name": "Dr Tan", "kind": "doctor"}, 201, "Pa adds Dr Tan"
    )
    at = datetime.combine(today + timedelta(days=2), datetime.min.time(), WALL).replace(hour=10)
    booking = {
        "provider_id": tan["provider_id"],
        "scheduled_at": at.isoformat(),
        "purpose": "check-up",
    }
    yes = w.yes(pa, profile_id, {"subject": "appointment", **booking}, "Pa says yes to the visit")
    visit = w.post(
        pa,
        f"{base}/appointments",
        {**booking, "confirmation_id": yes},
        201,
        "Pa writes the visit down",
    )
    ok(
        f"Pa has Dr Tan in his directory (POST /providers) and a visit with him on {at:%A %d %B} at 10, "
        "written down on his own yes (POST /confirmations subject appointment, POST /appointments)"
    )

    # 3. The blood pressure tablet, from a label photo, on his yes; one Taken; a blood pressure.
    photo = w.post(
        pa,
        f"{base}/photos",
        {
            "data": base64.b64encode(placeholder_png(f"label-{random.randint(0, 10**9)}")).decode(),
            "content_type": "image/png",
            "captured_at": datetime.now(WALL).isoformat(),
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
        "Pa adds amlodipine",
    )
    w.post(
        pa,
        f"{base}/medicines/{medicine['line_id']}/taken",
        {"anchor": "breakfast"},
        201,
        "Pa taps Taken",
    )
    w.post(
        pa,
        f"{base}/readings",
        {"systolic": 138, "diastolic": 84},
        201,
        "Pa types in a blood pressure",
    )
    ok(
        "Pa added amlodipine 5 mg from a label photo with his OK (POST /medicines, the label naming "
        "Dr Tan), tapped Taken once, and typed in a blood pressure (138 over 84)"
    )

    # 4. The cloud in Malay: "Pening" first, because of the new medicine's monograph.
    cloud = w.get(pa, f"{base}/feelings/cloud", "Pa opens the feeling cloud", language="ms")
    first = cloud["words"][0]
    reasons = {r["code"]: r for r in first["reasons"]}
    medicine_reason = reasons.get("new_medicine", {})
    if (
        not cloud["show"]
        or cloud["because"] != "changed"
        or first["word"] != "dizzy"
        or first["label"] != "Pening"
        or first["weight"] != 3
        or medicine_reason.get("generic") != "amlodipine"
        or medicine_reason.get("watch_out") != "dizzy_standing"
    ):
        raise fail(
            "the cloud puts dizzy first for the new medicine", why=f"got {short(str(cloud))}"
        )
    ok(
        f"the cloud in Malay (GET /feelings/cloud?language=ms) is on Today because State changed, "
        f"rendered from State {cloud['state_id'][:8]}…; the question, then the words biggest first — "
        "each with its reason code, kept for the audit and never shown to him:"
    )
    show(cloud["prompt"])
    show(
        [
            f"{w_['label']:<22} weight {w_['weight']}  "
            + ", ".join(sorted({r["code"] for r in w_["reasons"]}))
            + (
                f" ({medicine_reason['generic']}, monograph rule {medicine_reason['watch_out']})"
                if w_ is first
                else ""
            )
            for w_ in cloud["words"]
        ]
    )

    # 5. Pa taps "dizzy" and answers "since yesterday": the note for Dr Tan, the boundary last.
    tap = w.post(pa, f"{base}/feelings", {"word": "dizzy"}, 201, "Pa taps Pening")
    question = tap["question"]
    if tap["red_flag"] or question is None or question["follow_up"] != "since_when":
        raise fail("Pa taps Pening", why=f"got {short(str(tap))}")
    ok(
        f"Pa tapped Pening (POST /feelings): a SYMPTOM event in his word, and one question back — "
        f'"{question["words"]}" — with {", ".join(a["label"] for a in question["answers"])}'
    )
    answered = w.post(
        pa,
        f"{base}/feelings/{tap['tap_id']}/answer",
        {"answer": "yesterday"},
        201,
        "Pa answers since yesterday",
    )
    note = answered["note"]
    # PR #233 review: a note may be read back on a day that is not the day he answered, so
    # `compose_note` anchors "since yesterday" to that day instead — `TELL_ON`, day-anchored,
    # never `TELL`'s "sejak semalam", which is only ever true the moment the cloud replies.
    # `{date}` is fixed at compose time (the day he answered, here: today).
    said_on = say_date_ms(datetime.now(WALL))
    if (
        note is None
        or note["headline"] != "Perkara untuk diberitahu kepada Dr Tan"
        or note["lines"][0] != f"Beritahu Dr Tan bahawa anda rasa pening pada {said_on}."
        or not note["lines"][1].startswith("Ini boleh berlaku kerana ubat tekanan darah anda")
        or note["voice"][-2:] != ["Ini bukan nasihat doktor.", "Tanya Dr Tan."]
        or note["reasons"][0]["code"] != "new_medicine"
        or note["outcome"] != "for_the_doctor"
    ):
        raise fail("the note says what to tell Dr Tan", why=f"got {short(str(answered))}")
    ok(
        "Pa answered Sejak semalam (POST /feelings/{tap}/answer): the tap read against his medicines, "
        "his blood pressure and this week — the new medicine's licensed monograph lists dizziness — "
        f"into a note kept for the visit, rendered from State {note['rendered_from_state'][:8]}…, read aloud "
        "as: headline, two things to tell Dr Tan, who does the next thing, and the boundary last:"
    )
    show(note["voice"])
    again = w.get(pa, f"{base}/feelings/cloud", "Pa opens the cloud again", language="ms")
    if again["show"] or again["because"] != "tapped_today":
        raise fail(
            "the cloud goes after a tap",
            why=f"got show={again['show']}, because={again['because']}",
        )
    ok(
        "the strip is gone after his tap (show false, tapped_today), and stays gone until State changes again"
    )

    # 6. Pa taps "chest pain": the red-flag path first, and no note.
    red = w.post(pa, f"{base}/feelings", {"word": "chest_tightness"}, 201, "Pa taps Sakit dada")
    if (
        not red["red_flag"]
        or red["opens"] != "not_feeling_well"
        or red["question"] is not None
        or mei.person_id not in red["told"]
        or not red["escalation_id"]
        or red["lines"][-1] != "Nura tidak menentukan apa masalahnya."
        or red["card"] is None
        or red["card"]["kind"] != "red_flag"
        or red["card"]["posture"] != "act"
        or not red["card"]["card_id"]
    ):
        raise fail("chest pain takes the red-flag path", why=f"got {short(str(red))}")
    state = w.get(pa, f"{base}/state", "Pa's State")
    if state["posture"] != "act":
        raise fail("the red tap sets the day's posture to act", why=f"got {state['posture']}")
    notes = w.get(pa, f"{base}/feelings/notes", "Pa's notes")
    if [n["note_id"] for n in notes["notes"]] != [note["note_id"]] or notes["withheld"]:
        raise fail("no note for a red word", why=f"{len(notes)} notes")
    ok(
        f"Pa tapped Sakit dada: the red-flag path before anything else — the moment, the flag "
        f"({red['flag_id'][:8]}…, kept), Mei told, a notice to his emergency list and the ladder "
        f"({red['escalation_id'][:8]}…) for delivery — then the not-feeling-well button's whole flow, "
        f"server-side: the what-to-do card (urgent, card {red['card']['card_id'][:8]}…) and the day's "
        "posture act (GET /state); no question, and no note (GET /feelings/notes still holds only the "
        "one for dizzy); the card he is shown:"
    )
    show(red["lines"])

    # 7. The nudges: none today (a red flag today); tomorrow's, one, in the daytime.
    today_plan = w.get(pa, f"{base}/nudges/plan", "Pa's nudges today")
    if today_plan["none_because"] != "red_flag" or today_plan["drafts"]:
        raise fail("no nudge on a red-flag day", why=f"got {short(str(today_plan))}")
    ok(
        "no nudge today (GET /nudges/plan): a red flag was raised today, so nothing is planned for it"
    )
    plan = w.get(pa, f"{base}/nudges/plan", "Pa's nudges tomorrow", day=tomorrow.isoformat())
    drafts, held = plan["drafts"], {h["kind"]: h["because"] for h in plan["held"]}
    going = drafts[0] if drafts else {}
    send_after = datetime.fromisoformat(
        going.get("send_after", "1970-01-01T00:00:00+00:00")
    ).astimezone(WALL)
    if (
        len(drafts) != 1
        or going["kind"] != "anticipation"
        or not going["lines"][0].startswith("Anda berjumpa Dr Tan esok")
        or going["lines"][1] != "Sila bawa buku tekanan darah anda."
        or going["reason"].get("appointment_id") != visit["appointment_id"]
        or held.get("recognition") != "one_a_day"
        or not (7 <= send_after.hour < 21)
        or send_after.date() != tomorrow
    ):
        raise fail(
            "tomorrow's plan is the visit, one a day, in the daytime", why=f"got {short(str(plan))}"
        )
    ok(
        f"tomorrow's plan (GET /nudges/plan?day={tomorrow.isoformat()}): one nudge — anticipation, the visit "
        f"the day after — no earlier than {send_after:%H:%M} on his wall, cap class {going['cap_class']}, "
        f"with why; held, and said so: {', '.join(f'{k} ({v})' for k, v in held.items())}:"
    )
    show([*going["lines"], f"[why] {going['why']}"])
    handed = w.post(
        pa,
        f"{base}/nudges/plan",
        None,
        201,
        "the nudge is handed to delivery",
        day=tomorrow.isoformat(),
    )
    nudge = handed["nudge"]
    w.post(
        pa,
        f"{base}/nudges/{nudge['nudge_id']}/response",
        {"kind": "accepted"},
        201,
        "Pa accepts the nudge",
    )
    ok(
        f"the nudge was written down and handed to delivery (POST /nudges/plan: nudge {nudge['nudge_id'][:8]}…, "
        f"rendered from State {nudge['rendered_from_state'][:8]}…; nothing sent from here — E11 sends), and Pa "
        "accepted it (POST /nudges/{id}/response: an ENGAGEMENT event and a row)"
    )

    # 8. Mei reads the metrics: counts, and nothing about his health.
    raw = client.get(f"{base}/nudge-metrics", headers=bearer(mei.token))
    metrics = check(raw, 200, "Mei reads the nudge metrics")
    week = metrics["weeks"][0]
    anticipation = week["nudges"]["anticipation"]
    leaked = UUID.search(raw.text) or any(
        word in raw.text.lower() for word in ("dizzy", "pening", "chest", "dr tan")
    )
    if (
        week["taps"] != 2
        or week["fine_today"] != 0
        or anticipation["handed_over"] != 1
        or anticipation["accepted"] != 1
        or leaked
    ):
        raise fail("Mei reads counts and nothing else", raw, f"week {week}")
    ok(
        f"Mei, his chief, read the metrics (GET /nudge-metrics): week {week['week']} — {week['taps']} taps on "
        f"the cloud, {week['fine_today']} of them Fine today (share {week['fine_share']}), anticipation "
        f"handed over {anticipation['handed_over']}, accepted {anticipation['accepted']} (acceptance "
        f"{anticipation['acceptance']}); no word he tapped, no line, no id in the answer"
    )
    trail = w.get(pa, f"{base}/audit", "Pa reads his trail")
    reads = [
        e for e in trail if e["target"] == "nudge_metrics" and e["actor_person_id"] == mei.person_id
    ]
    if not reads:
        raise fail("Mei's metrics read is on Pa's trail", why="no nudge_metrics line")
    ok("Mei's metrics read is on Pa's trail (GET /audit): a read of nudge_metrics, in her name")

    # 9. The Me page: the number that only goes up.
    me = w.get(pa, f"{base}/me-summary", "Pa opens Me")
    if me["proud_days"] != 1 or me["lines"][-1] != "Nombor ini hanya naik.":
        raise fail("the Me page says the proud number", why=f"got {me}")
    ok(
        "Pa's Me page (GET /me-summary): the days with a tablet taken, counted by the backend, in his words:"
    )
    show(me["lines"])


def run(base_url: str, dev_log: Path) -> int:
    try:
        with httpx.Client(base_url=base_url, timeout=15.0) as client:
            walk(client, dev_log)
    except Failed as failed:
        print(str(failed), flush=True)
        return 1
    return 0
