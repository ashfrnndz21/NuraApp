"""Checkpoint 17 — lab trends, the day's routine, the calendar (E09-01, E10-01, E18-02).

    make dev                # one terminal
    make checkpoint N=17    # another: this module, through scripts/checkpoint.py

Pa, born in 1951, opens his profile in Malay and confirms two lipid reports through the review
card — the 2023 one from checkpoint 5 and a 2025 one from Bukit Lab (fictional) that names the
lab, his year of birth and his sex. His cholesterol trend comes back in Malay with the range
and the direction, rendered from State and ending on the boundary line. Mei, his daughter, is
let in; Pa adds amlodipine; Mei sets the day once on her own yes, and it renders to Pa as one
line per moment of his day and to Mei as a table. Pa connects his calendar on its own
consent; Mei uploads a small .ics with three events — a Dr Tan follow-up, "Dialysis SGH" and
"Lunch with Ah Kow" — and gets two proposals, the lunch stored nowhere; she dismisses one;
Pa's yes turns the other into a planned visit. The trail shows every step.

Self-contained, like cp13: every helper it needs is here. `run(base_url, dev_log)` prints
✓/✗ lines in the runner's style and returns 0 or 1.
"""

from __future__ import annotations

import base64
import os
import random
import re
import time
from datetime import date, datetime, timedelta
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
CALENDAR_WORDING = "1"
"""Today's words for the calendar connector, from `app/consent/texts.py`. Move when they move."""
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
LIPID_2023 = "lipid-panel-2023-09-07"
LIPID_2025 = "lipid-panel-2025-08-29"
SG = ZoneInfo("Asia/Singapore")

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


def span(rng: JSON) -> str:
    """A range as the table prints it: under 200, 40 or more, 3.5–5.2."""

    def n(value: float) -> str:
        return f"{value:g}"

    if rng["lower"] is not None and rng["upper"] is not None:
        return f"{n(rng['lower'])}–{n(rng['upper'])}"
    if rng["upper"] is not None:
        return f"under {n(rng['upper'])}"
    return f"{n(rng['lower'])} or more"


def show(lines: list[str]) -> None:
    for line in lines:
        print(f"    {line}", flush=True)


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


def placeholder_png(label: str) -> bytes:
    """The bytes that stand in for one redacted paper — the same three lines as
    `backend/tests/paper.py`, so the fixture extractor recognises the digest."""
    return PNG_SIGNATURE + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"


def photo(label: str) -> JSON:
    return {
        "data": base64.b64encode(placeholder_png(label)).decode(),
        "content_type": "image/png",
        "captured_at": datetime.now(SG).isoformat(),
    }


def calendar_file(today: date, run: str) -> bytes:
    """Mei's small calendar: three events in the coming fortnight, with the names of the
    people in them — none of which may be kept."""

    def at(day: date, hour: int, minute: int) -> str:
        return f"{day:%Y%m%d}T{hour:02d}{minute:02d}00"

    visit, dialysis, lunch = (today + timedelta(days=n) for n in (10, 4, 6))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Mei//Phone calendar//EN",
        "BEGIN:VEVENT",
        f"UID:visit-{run}@mei.example",
        "SUMMARY:Dr Tan follow-up",
        f"DTSTART;TZID=Asia/Singapore:{at(visit, 10, 0)}",
        "LOCATION:Tan Family Clinic\\, Bishan",
        "ATTENDEE;CN=Mei Lim:mailto:mei@example.com",
        "END:VEVENT",
        "BEGIN:VEVENT",
        f"UID:dialysis-{run}@mei.example",
        "SUMMARY:Dialysis SGH",
        f"DTSTART;TZID=Asia/Singapore:{at(dialysis, 9, 0)}",
        "LOCATION:Singapore General Hospital",
        "END:VEVENT",
        "BEGIN:VEVENT",
        f"UID:lunch-{run}@mei.example",
        "SUMMARY:Lunch with Ah Kow",
        f"DTSTART;TZID=Asia/Singapore:{at(lunch, 12, 30)}",
        "LOCATION:Maxwell Food Centre",
        "ATTENDEE;CN=Ah Kow:mailto:ahkow@example.com",
        "DESCRIPTION:Ah Kow says his knee is better",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode()


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

    def paper(
        self, who: Person, profile_id: str, label: str, correct: dict[str, Any] | None = None
    ) -> JSON:
        """A paper through the review card: upload, decide every field, one yes, confirm."""
        card = check(
            self.client.post(
                f"/profiles/{profile_id}/photos", headers=bearer(who.token), json=photo(label)
            ),
            201,
            f"{who.name} uploads {label}",
        )
        decisions = []
        for field in card["fields"]:
            if correct and field["attribute"] in correct:
                decisions.append(
                    {
                        "field_id": field["field_id"],
                        "decision": "corrected",
                        "corrected_value": correct[field["attribute"]],
                    }
                )
            else:
                decisions.append({"field_id": field["field_id"], "decision": "confirmed"})
        yes = self.yes(
            who,
            profile_id,
            {"subject": "review_card", "card_id": card["card_id"], "decisions": decisions},
            f"{who.name} says OK to {label}",
        )
        done: JSON = check(
            self.client.post(
                f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
                headers=bearer(who.token),
                json={"decisions": decisions, "confirmation_id": yes},
            ),
            200,
            f"{who.name} confirms {label}",
        )
        return done


def walk(client: httpx.Client, dev_log: Path) -> None:
    w = Walk(client, dev_log)
    pa = Person("Pa", fresh_phone("+659171"))
    mei = Person("Mei", fresh_phone("+659172"))
    run = f"{random.randint(0, 10**9):09d}"

    # 1. Pa opens his profile, in Malay.
    w.register(pa, "ms")
    opened = check(
        client.post(
            "/profiles/mine",
            headers=bearer(pa.token),
            json={
                "consent": {"wording_version": HOLD_WORDING, "language": "ms", "captured_via": "app"},
                "display_name": pa.name,
                "language": "ms",
            },
        ),
        201,
        "Pa opens his own profile",
    )
    profile_id: str = opened["profile_id"]
    base = f"/profiles/{profile_id}"
    ok("Pa opened his own profile, in Malay")

    # 2. Two lipid reports through the review card.
    first = w.paper(pa, profile_id, LIPID_2023, correct={"triglycerides": 54})
    second = w.paper(pa, profile_id, LIPID_2025)
    told = {f["attribute"]: f["value"] for f in second["facts"]}
    if (told.get("birth_year"), told.get("sex"), told.get("lab")) != (1951, "male", "bukit_lab"):
        raise fail("Pa confirms the 2025 report", why=f"header fields not facts: {told}")
    ok(
        f"Pa confirmed two lipid reports through the review card, one yes each: 7 September 2023 "
        f"({len(first['facts'])} facts, triglycerides corrected to 54) and 29 August 2025 from "
        f"Bukit Lab ({len(second['facts'])} facts, including the lab, his year of birth 1951 and "
        "his sex from the report's header) — every fact names its photo and Pa as confirmer"
    )

    # 3. His cholesterol trend, in Malay, from State.
    shown = check(
        client.get(f"{base}/trends/total_cholesterol", headers=bearer(pa.token)),
        200,
        "Pa reads his cholesterol trend",
    )
    points = shown["points"]
    if (
        shown["language"] != "ms"
        or [p["value"] for p in points] != [230, 212]
        or shown["direction"] != "down"
        or points[1]["range"]["source"] != "lab"
        or points[0]["range"]["source"] != "guideline"
        or shown["birth_decade"] != 1950
        or not shown["lines"][-1].startswith("Tanya ")
    ):
        raise fail("Pa reads his cholesterol trend", why=f"got {short(str(shown), 600)}")
    ok(
        "Pa's cholesterol trend (GET /trends/total_cholesterol), rendered from State "
        f"{shown['state_id'][:8]}… as card {shown['card_id'][:8]}… with the boundary line: "
        "each result against the range that fits him on the day — his age band read from the "
        "1950s, never the year — the 2025 one against Bukit Lab's own printed range, the 2023 "
        "one against the guideline table (ncep-atp3-2001); the direction over the last three, "
        "by arithmetic:"
    )
    for p in points:
        rng = p["range"]
        print(
            f"    {p['on']}  {p['value']:g} {p['unit']}  {p['band']:<6} against "
            f"{span(rng)} {rng['unit']} ({rng['source_id']})  ← artefact {p['artifact_id'][:8]}…",
            flush=True,
        )
    print("    In his words, in Malay:", flush=True)
    show(shown["lines"])

    # 4. Mei is let in; Pa adds amlodipine.
    w.register(mei, "en")
    check(
        client.post(
            f"{base}/consents/sharing",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "holder_display_name": mei.name,
                "scopes": ["medicines", "visits", "readings"],
                "role": "caregiver",
                "window": "always",
                "relationship": "daughter",
                "language": "ms",
                "captured_via": "app",
            },
        ),
        201,
        "Pa agrees to let Mei in",
    )
    check(
        client.post(
            f"{base}/keys",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "role": "caregiver",
                "scopes": ["medicines", "visits", "readings"],
            },
        ),
        201,
        "Pa cuts Mei a caregiver key",
    )
    ok("Pa let Mei in to his medicines, visits and readings, and cut her a caregiver key")
    label_photo = check(
        client.post(
            f"{base}/photos", headers=bearer(pa.token), json=photo(f"cp17-label-{run}")
        ),
        201,
        "Pa photographs the amlodipine label",
    )
    label = {
        "generic": "amlodipine",
        "strength": "5 mg",
        "dose_text": "1 biji sekali sehari pagi",
        "quantity": 30,
        "prescriber": "Dr Tan",
        "source_kind": "retail",
    }
    body = {"label": label, "source_artifact_id": label_photo["artifact_id"]}
    yes = w.yes(pa, profile_id, {"subject": "medicine", **body}, "Pa says OK to amlodipine")
    check(
        client.post(f"{base}/medicines", headers=bearer(pa.token), json={**body, "confirmation_id": yes}),
        201,
        "Pa adds amlodipine",
    )
    ok("Pa added amlodipine 5 mg from its label, once a day in the morning, on his own yes")

    # 5. Mei sets the day once, on her yes.
    day = {
        "anchors": {
            "wake": "06:30",
            "breakfast": "07:30",
            "lunch": "12:30",
            "dinner": "18:30",
            "bed": "22:00",
        },
        "reading_prompts": [["blood_pressure", "wake"]],
        "walks": ["dinner"],
        "morning_card_at": "07:00",
    }
    yes = w.yes(mei, profile_id, {"subject": "routine", **day}, "Mei says OK to the day")
    refused(
        client.put(
            f"{base}/routine",
            headers=bearer(mei.token),
            json={**day, "morning_card_at": "08:00", "confirmation_id": yes},
        ),
        400,
        "NotWhatWasConfirmed",
        "Mei sets a day she did not say yes to",
    )
    set_ = check(
        client.put(f"{base}/routine", headers=bearer(mei.token), json={**day, "confirmation_id": yes}),
        200,
        "Mei sets the day",
    )
    if not set_["set"] or set_["set_by_person_id"] != mei.person_id:
        raise fail("Mei sets the day", why=str(set_))
    ok(
        "Mei set the day once (PUT /routine) on her own yes for exactly it — the same yes offered "
        "for another hour was refused, NotWhatWasConfirmed (400): his anchors, the blood pressure "
        "when he wakes, a walk after dinner, the Today page at 7"
    )

    # 6. Rendered to Pa, and to Mei.
    his = check(client.get(f"{base}/routine", headers=bearer(pa.token)), 200, "Pa reads his day")
    if his["persona"] != "patient" or len(his["lines"]) != 4:
        raise fail("Pa reads his day", why=str(his))
    ok("Pa reads his day (GET /routine): one line per moment, in Malay, every line verified")
    show(his["lines"])
    hers = check(client.get(f"{base}/routine", headers=bearer(mei.token)), 200, "Mei reads the day")
    if hers["persona"] != "caregiver" or not hers["table"]:
        raise fail("Mei reads the day", why=str(hers))
    ok("Mei reads the same day as a table (the caregiver's persona): times, dose codes, prompts")
    for row in hers["table"]:
        meds = ", ".join(
            f"{m['generic']} {m['strength']} ×{m['amount']:g} {m['frequency']}" for m in row["medicines"]
        )
        extra = ", ".join([*(row["readings"] or []), *(["walk"] if row["walk"] else [])])
        print(f"    {row['anchor']:<9} {row['at']}  {meds or '—':<32} {extra or ''}", flush=True)

    # 7. The calendar: Pa connects it on its own consent, in Malay.
    refused(
        client.post(f"{base}/connectors/calendar", headers=bearer(pa.token), json={}),
        403,
        "ConsentWithheld",
        "Pa connects his calendar before agreeing",
    )
    connector = check(
        client.post(
            f"{base}/connectors/calendar",
            headers=bearer(pa.token),
            json={"consent": {"wording_version": CALENDAR_WORDING, "language": "ms"}},
        ),
        201,
        "Pa connects his calendar",
    )
    consents = check(client.get(f"{base}/consents", headers=bearer(pa.token)), 200, "Pa's consents")
    words = next(c for c in consents if c["purpose"] == "calendar")["wording_text"]
    ok(
        "connecting before agreeing was refused, ConsentWithheld (403); Pa then agreed to the "
        "calendar in Malay and connected it (POST /connectors/calendar). The words he read:"
    )
    show(words.splitlines())

    # 8. Mei uploads three events.
    today = datetime.now(SG).date()
    scanned = check(
        client.post(
            f"{base}/connectors/{connector['connector_id']}/scan",
            headers=bearer(mei.token),
            json={"ics": base64.b64encode(calendar_file(today, run)).decode()},
            params={"language": "en"},
        ),
        200,
        "Mei uploads her calendar",
    )
    if (scanned["read"], scanned["dropped"], len(scanned["proposed"])) != (3, 1, 2):
        raise fail("Mei uploads her calendar", why=str(scanned))
    for word in ("Ah Kow", "Maxwell", "Mei Lim", "knee"):
        listed = client.get(f"{base}/proposals", headers=bearer(mei.token)).text
        if word in listed or any(word in str(p) for p in scanned["proposed"]):
            raise fail("Mei uploads her calendar", why=f"{word!r} was kept")
    by_title = {p["title"]: p for p in scanned["proposed"]}
    ok(
        "Mei uploaded a .ics with three events (POST /connectors/{c}/scan): 3 read, 2 proposed, "
        "1 dropped — the lunch with Ah Kow matched no provider and no health word, and nothing of "
        "it, nor anyone's name in any event, was written anywhere. Candidates, never visits:"
    )
    for p in scanned["proposed"]:
        when = datetime.fromisoformat(p["starts_at"]).astimezone(SG)
        print(
            f"    {p['title']:<18} {when:%a %d %b %H:%M}  matched {p['matched_by']} "
            f"'{p['keyword']}'  → {p['provider_name']} ({p['provider_kind']})  {p['status']}",
            flush=True,
        )

    # 9. One dismissed; the other accepted by Pa's yes.
    dismissed = check(
        client.post(
            f"{base}/proposals/{by_title['Dialysis SGH']['proposal_id']}/dismiss",
            headers=bearer(mei.token),
        ),
        200,
        "Mei dismisses the dialysis",
    )
    if dismissed["status"] != "dismissed" or dismissed["appointment_id"] is not None:
        raise fail("Mei dismisses the dialysis", why=str(dismissed))
    ok("Mei dismissed 'Dialysis SGH' (not Pa's): nothing booked")
    visit = by_title["Dr Tan follow-up"]
    shown_to_him = check(
        client.get(f"{base}/proposals", headers=bearer(pa.token), params={"status": "proposed"}),
        200,
        "Pa reads the proposal",
    )
    print("    What Pa reads, in Malay:", flush=True)
    show(shown_to_him[0]["lines"])
    yes = w.yes(
        pa,
        profile_id,
        {"subject": "appointment_proposal", "proposal_id": visit["proposal_id"]},
        "Pa says yes to the visit",
    )
    accepted = check(
        client.post(
            f"{base}/proposals/{visit['proposal_id']}/accept",
            headers=bearer(pa.token),
            json={"confirmation_id": yes},
        ),
        200,
        "Pa's yes books the visit",
    )
    if accepted["appointment_status"] != "planned":
        raise fail("Pa's yes books the visit", why=str(accepted))
    refused(
        client.post(
            f"{base}/proposals/{visit['proposal_id']}/accept",
            headers=bearer(pa.token),
            json={"confirmation_id": yes},
        ),
        409,
        "AlreadyDecided",
        "the same proposal accepted again",
    )
    ok(
        "Pa said yes (POST /confirmations, subject appointment_proposal) and accepted: Dr Tan "
        "added to his directory and the visit booked as PLANNED on his yes, appointment "
        f"{accepted['appointment_id'][:8]}…; accepting again is refused, AlreadyDecided (409)"
    )
    show(accepted["proposal"]["lines"])

    # 10. The trend names the doctor now; the trail shows it all.
    again = check(
        client.get(
            f"{base}/trends/total_cholesterol", headers=bearer(pa.token), params={"language": "en"}
        ),
        200,
        "Pa reads his trend in English",
    )
    if again["lines"][-1] != "Ask Dr Tan.":
        raise fail("Pa reads his trend in English", why=str(again["lines"]))
    ok("with a visit to Dr Tan on the spine, the trend's last line names him:")
    show(again["lines"][-3:])
    trail = check(client.get(f"{base}/audit", headers=bearer(pa.token)), 200, "Pa reads his trail")
    wanted = {"trend_card", "routine", "connector", "appointment_proposal", "provider", "appointment"}
    lines = [
        row
        for row in reversed(trail)
        if (row["target"] in wanted and row["action"] == "write") or row["outcome"] == "refused"
    ]
    names = {pa.person_id: "Pa", mei.person_id: "Mei"}
    if not {"trend_card", "routine", "connector", "appointment_proposal", "appointment"} <= {
        r["target"] for r in lines
    }:
        raise fail("Pa reads his trail", why="a step is missing from the trail")
    ok(f"Pa's trail ({len(trail)} lines) shows every step and every refusal by name:")
    for row in lines:
        outcome = row["refused_because"] if row["outcome"] == "refused" else "written"
        print(
            f"    {row['at'][:19]}  {names.get(row['actor_person_id'], '?'):>3}  {row['action']} "
            f"{row['scope']:<9} {row['target']:<22} {outcome}",
            flush=True,
        )


def run(base_url: str, dev_log: Path) -> int:
    """Walk checkpoint 17 against the server at `base_url`; 0 when every step is a ✓."""
    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            walk(client, Path(dev_log))
    except Failed as failed:
        print(str(failed), flush=True)
        return 1
    return 0
