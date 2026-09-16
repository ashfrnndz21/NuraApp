"""Checkpoint 20 — Delivery: triggers, the ladder, the morning ritual (E11, E00-05), over HTTP.

    NURA_FROZEN_CLOCK=2026-09-14T06:00:00+08:00 make dev    # one terminal: a frozen clock
    make checkpoint N=20                                     # another: this module

Pa opens his own profile, agrees to WhatsApp, and adds his blood pressure tablet (two left, so
the reorder date is reached); Mei, his daughter, holds a chief key and is on the roster on
weekdays; Siti, the helper, holds a helper key. The day is Monday 14 September on a dev run's
frozen clock (#118): the checkpoint stands it at 06:00 and steps it (`POST /dev/clock`) to each
hour the scenario needs, running the engine there (`POST /dev/run-triggers`, the dev door onto
`run_due`): the morning card at his breakfast, as the approved template; the breakfast tablet's window closes with no Taken, and the ladder
asks Pa, then Siti, then Mei, and stops when Siti replies "sudah beri" on WhatsApp; the reorder
reaches Mei and is held by the cap the second time that day; at 22:30 Pa writes that he fell,
and the flag goes straight to the roster, neither quiet nor capped. Then today's top three with
why, and one card played as voice.

Self-contained, like every module here: `run(base_url, dev_log)` prints ✓/✗ lines and
returns 0 or 1.
"""

from __future__ import annotations

import base64
import random
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

CODE_LINE = re.compile(r"login code for (\+[0-9]+): ([0-9]{6})")
CODE_WAIT_SECONDS = 3.0
HOLD_WORDING = "1"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SGT = ZoneInfo("Asia/Singapore")
DAY = date(2026, 9, 14)
"""Monday 14 September 2026: a weekday, so Mei is on the roster."""

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


def say(line: str) -> None:
    print(f"    {line}", flush=True)


def check(response: httpx.Response, status: int, what: str) -> Any:
    if response.status_code != status:
        raise fail(what, response, f"expected {status}")
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


class Person:
    def __init__(self, name: str, phone_e164: str, language: str) -> None:
        self.name = name
        self.phone_e164 = phone_e164
        self.language = language
        self.token = ""
        self.person_id = ""


def fresh_phone(prefix: str) -> str:
    return f"{prefix}{random.randint(0, 9999):04d}"


class Walk:
    def __init__(self, client: httpx.Client, dev_log: Path) -> None:
        self.client = client
        self.dev_log = dev_log
        self.day = DAY
        self.seen: list[JSON] = []

    def clock(self, hour: int, minute: int = 0, *, days: int = 0) -> None:
        """Stand the dev run's frozen clock at this moment of Pa's day (`POST /dev/clock`)."""
        day = self.day + timedelta(days=days)
        at = datetime(day.year, day.month, day.day, hour, minute, tzinfo=SGT).isoformat()
        moved = self.client.post("/dev/clock", json={"at": at})
        if moved.status_code == 409:
            raise Failed(
                "✗ the dev server's clock is not frozen: start it with "
                "NURA_FROZEN_CLOCK=2026-09-14T06:00:00+08:00 make dev, then run this again"
            )
        check(moved, 200, f"the clock stands at {hour:02d}:{minute:02d}")

    # --- signing in -----------------------------------------------------------------------

    def code_from_log(self, phone_e164: str) -> str:
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

    def register(self, person: Person) -> None:
        who = f"{person.name} ({person.phone_e164})"
        check(
            self.client.post(
                "/auth/phone/start",
                json={
                    "phone_e164": person.phone_e164,
                    "display_name": person.name,
                    "language": person.language,
                },
            ),
            202,
            f"{who} asks for a code by phone",
        )
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

    # --- the engine and the thread ------------------------------------------------------------

    def run_due(self, profile_id: str, hour: int, minute: int = 0) -> list[JSON]:
        """The clock stepped to this hour, then one engine run; its rows, which are also kept
        for the steps that look back."""
        self.clock(hour, minute)
        ran = check(
            self.client.post("/dev/run-triggers", json={"profile_id": profile_id}),
            200,
            f"the engine runs at {hour:02d}:{minute:02d}",
        )
        rows: list[JSON] = ran["deliveries"]
        for row in rows:
            row["at"] = f"{hour:02d}:{minute:02d}"
        self.seen.extend(rows)
        return rows

    def inbound(self, person: Person, text: str, hour: int, minute: int) -> JSON:
        self.clock(hour, minute)
        handled: JSON = check(
            self.client.post(
                "/dev/whatsapp/inbound", json={"from_e164": person.phone_e164, "text": text}
            ),
            200,
            f'{person.name} writes "{text}" on WhatsApp',
        )
        return handled


def _of(rows: list[JSON], kind: str) -> list[JSON]:
    return [row for row in rows if row["trigger_type"] == kind]


def _line(row: JSON) -> str:
    via = row["channel"] or "—"
    rung = "" if row["rung"] is None else f", rung {row['rung']}"
    template = f", template {row['template_name']}" if row["template_name"] else ""
    return (
        f"{row['to_name']} ({row['standing']}{rung}): {row['outcome']} by {via}{template}; "
        f"rule {row['rule']}"
    )


def walk(client: httpx.Client, dev_log: Path) -> None:
    w = Walk(client, dev_log)
    pa = Person("Pa", fresh_phone("+659120"), "en")
    mei = Person("Mei", fresh_phone("+659220"), "en")
    siti = Person("Siti", fresh_phone("+659720"), "ms")

    # 1. The family, at 06:00 on Monday 14 September, his wall clock.
    w.clock(6, 0)
    for person in (pa, mei, siti):
        w.register(person)
    ok(
        f"Pa ({pa.phone_e164}), Mei ({mei.phone_e164}) and Siti ({siti.phone_e164}) registered "
        "by phone code (the codes read from the server log)"
    )
    opened = check(
        client.post(
            "/profiles/mine",
            headers=bearer(pa.token),
            json={
                "consent": {"wording_version": HOLD_WORDING, "language": "en", "captured_via": "app"},
                "display_name": "Pa",
                "language": "en",
            },
        ),
        201,
        "Pa opens his own profile",
    )
    profile_id: str = opened["profile_id"]
    check(
        client.post(
            f"/profiles/{profile_id}/consents/whatsapp",
            headers=bearer(pa.token),
            json={"language": "en", "captured_via": "app"},
        ),
        201,
        "Pa agrees to WhatsApp",
    )
    for person, role, scopes, relationship in (
        (
            mei,
            "chief",
            ["medicines", "visits", "readings", "records", "family", "emergency", "send"],
            "daughter",
        ),
        (siti, "helper", ["medicines", "emergency", "send"], "helper"),
    ):
        check(
            client.post(
                f"/profiles/{profile_id}/consents/sharing",
                headers=bearer(pa.token),
                json={
                    "holder_phone_e164": person.phone_e164,
                    "holder_display_name": person.name,
                    "scopes": scopes,
                    "relationship": relationship,
                    "language": "en",
                    "captured_via": "app",
                },
            ),
            201,
            f"Pa lets {person.name} in",
        )
        check(
            client.post(
                f"/profiles/{profile_id}/keys",
                headers=bearer(pa.token),
                json={"holder_phone_e164": person.phone_e164, "role": role},
            ),
            201,
            f"Pa cuts {person.name} a {role} key",
        )
    check(
        client.post(
            f"/profiles/{profile_id}/roster",
            headers=bearer(pa.token),
            json={
                "person_id": mei.person_id,
                "role": "chief",
                "weekdays": [0, 1, 2, 3, 4],
                "from_time": "06:00:00",
                "to_time": "23:00:00",
            },
        ),
        201,
        "Pa puts Mei on the roster on weekdays",
    )
    ok(
        "Pa opened his profile and agreed to WhatsApp; Mei (his daughter) holds a chief key and "
        "is on duty weekdays 6 in the morning to 11 at night; Siti holds a helper key "
        "(medicines, emergency, send)"
    )

    # 2. His blood pressure tablet, two left.
    photo = check(
        client.post(
            f"/profiles/{profile_id}/photos",
            headers=bearer(pa.token),
            json={
                "data": base64.b64encode(
                    PNG_SIGNATURE
                    + b"nura-paper-placeholder:label-"
                    + str(random.randint(0, 10**9)).encode()
                    + b"\n"
                ).decode(),
                "content_type": "image/png",
                "captured_at": datetime(2026, 9, 14, 5, 59, tzinfo=SGT).isoformat(),
            },
        ),
        201,
        "Pa keeps the label photo",
    )
    label = {
        "generic": "amlodipine",
        "strength": "5 mg",
        "dose_text": "1 tab OM",
        "quantity": 2,
        "prescriber": "Dr Tan",
        "source_kind": "retail",
    }
    yes = check(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=bearer(pa.token),
            json={"subject": "medicine", "label": label, "source_artifact_id": photo["artifact_id"]},
        ),
        201,
        "Pa's OK for the label",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/medicines",
            headers=bearer(pa.token),
            json={
                "label": label,
                "source_artifact_id": photo["artifact_id"],
                "confirmation_id": yes["confirmation_id"],
            },
        ),
        201,
        "Pa adds amlodipine",
    )
    ok(
        "Pa added amlodipine 5 mg, one every morning, two tablets left (checkpoint 6's route), "
        f"at 06:00 on {w.day.isoformat()} by the dev run's frozen clock"
    )

    # 3. The morning card at his breakfast — the one breakfast time his settings, else his
    #    routine, say; 07:30 until either does — by WhatsApp, once.
    assert_none = _of(w.run_due(profile_id, 7, 20), "morning")
    if assert_none:
        raise fail("nothing before breakfast", why=f"got {assert_none}")
    [morning] = _of(w.run_due(profile_id, 7, 31), "morning") or [None]
    if (
        morning is None
        or morning["outcome"] != "sent"
        or morning["channel"] != "whatsapp"
        or morning["template_name"] != "morning_card"
    ):
        raise fail("the morning card goes at breakfast", why=f"got {morning}")
    if _of(w.run_due(profile_id, 7, 45), "morning"):
        raise fail("one morning card a day", why="a second one went")
    ok(
        "07:20: nothing; 07:31, his breakfast (the one breakfast time, 07:30 until he says — "
        "the first week's prompt comes at the same moment): the morning card, the approved "
        "template (he has not written in 24 hours), once — 07:45 sends nothing. "
        + _line(morning)
        + ". What he reads:"
    )
    for line in (morning["text"] or "").splitlines():
        say(f"→ {line}")

    # 4. The breakfast tablet's window closes at 08:30 with no Taken (the routine calls
    #    breakfast due for an hour): the ladder.
    rows = _of(w.run_due(profile_id, 8, 31), "dose")
    if [r["to_name"] for r in rows] != ["Pa"] or rows[0]["outcome"] != "sent":
        raise fail("the ladder asks Pa first", why=f"got {rows}")
    ok("08:31, the window closed untapped: rung 0, Pa — " + _line(rows[0]))
    for line in (rows[0]["text"] or "").splitlines():
        say(f"→ {line}")
    rows = _of(w.run_due(profile_id, 9, 1), "dose")
    if [r["to_name"] for r in rows] != ["Siti"] or rows[0]["outcome"] != "sent":
        raise fail("half an hour on, the ladder asks Siti", why=f"got {rows}")
    ok("09:01, nobody answered: rung 1, the helper — " + _line(rows[0]) + ", in Malay:")
    for line in (rows[0]["text"] or "").splitlines():
        say(f"→ {line}")
    rows = _of(w.run_due(profile_id, 9, 31), "dose")
    if [r["to_name"] for r in rows] != ["Mei"] or rows[0]["outcome"] != "sent":
        raise fail("the third ask goes to the roster", why=f"got {rows}")
    ok("09:31, still nobody: the third ask goes to the roster, not to him — " + _line(rows[0]))

    given = w.inbound(siti, "sudah beri", 9, 35)
    if given["outcome"] != "taken":
        raise fail('Siti replies "sudah beri"', why=f"got {given}")
    today = check(
        client.get(f"/profiles/{profile_id}/medicines/today", headers=bearer(pa.token)),
        200,
        "Pa's list for today",
    )
    if not any(slot["taken"] for slot in today):
        raise fail("the Taken tap is on his list", why=f"got {today}")
    if _of(w.run_due(profile_id, 10, 5), "dose"):
        raise fail("the ladder stops at an answer", why="it asked again")
    ok(
        'Siti replied "sudah beri" on WhatsApp: the Taken tap was written for the breakfast '
        "tablet — on the medicines key she holds, on the WhatsApp channel — and the ladder "
        "stopped; 10:05 asks nobody. Her reply in the thread:"
    )
    for sent in given["replies"]:
        for line in sent["text"].splitlines():
            say(f"→ {line}")

    # 4b. His check-in time, 10:00: the schedule handed the day's nudge over at 10:05 and
    #     delivery sent it; the web handing it over again as he answers is the same nudge.
    nudged = [row for row in _of(w.seen, "nudge") if row["outcome"] == "sent"]
    if len(nudged) != 1 or nudged[0]["at"] != "10:05" or nudged[0]["template_name"] != "nudge":
        raise fail("the day's nudge goes at his check-in time, once", why=f"got {_of(w.seen, 'nudge')}")
    handed = check(
        client.post(f"/profiles/{profile_id}/nudges/plan", headers=bearer(pa.token)),
        201,
        "the web hands the day's nudge over as he answers",
    )
    listed = check(
        client.get(f"/profiles/{profile_id}/nudges", headers=bearer(pa.token)), 200, "the day's nudges"
    )
    if [one["nudge_id"] for one in listed["nudges"]] != [handed["nudge"]["nudge_id"]]:
        raise fail("handing the nudge over twice is one nudge", why=f"got {listed}")
    if any(row["trigger_type"] == "nudge" and row["outcome"] == "sent" for row in w.run_due(profile_id, 10, 10)):
        raise fail("the nudge is sent once", why="10:10 sent it again")
    ok(
        "10:05, after his check-in time (10:00): the schedule handed the day's nudge over and "
        "delivery sent it — " + _line(nudged[0]) + "; the web handing it over again as he answers "
        "(POST /nudges/plan) gives back the same nudge — one row (GET /nudges) — and 10:10 sends "
        "it no second time. What he reads:"
    )
    for line in (nudged[0].get("text") or "").splitlines():
        say(f"→ {line}")

    # 5. The reorder date reached (two tablets): the rule is true all day, so every run above
    #    evaluated it — the first run of the day told Mei, the next was held by the cap, and
    #    every run after that wrote nothing, because the hold is written down once.
    w.run_due(profile_id, 12, 0)
    reorders = _of(w.seen, "reorder")
    quiet = [r for r in reorders if r["outcome"] == "quiet"]
    sent = [r for r in reorders if r["outcome"] == "sent"]
    capped = [r for r in reorders if r["outcome"] == "capped"]
    if len(sent) != 1 or sent[0]["to_name"] != "Mei":
        raise fail("the reorder reaches Mei, once", why=f"got {reorders}")
    if len(capped) != 1 or capped[0]["reason"] != "once a day":
        raise fail("the second reorder that day is capped, once", why=f"got {reorders}")
    if len(reorders) != len(quiet) + 2:
        raise fail("the hold is written down once", why=f"got {reorders}")
    if quiet:
        ok(f"{quiet[0]['at']}, before 7 in the morning: the reorder was held for the quiet hours")
    ok(f"{sent[0]['at']}, the first run of the day, the reorder date reached: " + _line(sent[0]) + ":")
    for line in (sent[0]["text"] or "").splitlines():
        say(f"→ {line}")
    ok(
        f"{capped[0]['at']}, the same rule the second time that day: {capped[0]['outcome']} "
        f"({capped[0]['reason']}) — no second message, and no row at all on the runs after it"
    )

    # 5b. His directory (E03-03): Dr Tan, and Gleneagles marked as the hospital on his insurance.
    for provider in (
        {"name": "Dr Tan", "kind": "doctor"},
        {"name": "Gleneagles", "kind": "hospital", "panel": True},
    ):
        check(
            client.post(f"/profiles/{profile_id}/providers", headers=bearer(mei.token), json=provider),
            201,
            f"Mei adds {provider['name']} to his directory",
        )
    ok(
        "Mei added Dr Tan and Gleneagles to his directory (POST /profiles/{id}/providers), "
        "Gleneagles marked as the hospital on his insurance (panel: true); Dr Tan's hours are not "
        "set, so his clinic answers 08:00 to 20:00"
    )

    # 6. 22:30, the quiet hours: Pa writes that he fell.
    fell = w.inbound(pa, "I fell in the bathroom", 22, 30)
    if fell["outcome"] != "red_flag" or not fell["flag_id"]:
        raise fail("Pa writes that he fell at 22:30", why=f"got {fell}")
    log = check(
        client.get(f"/profiles/{profile_id}/deliveries", headers=bearer(pa.token)),
        200,
        "the delivery log",
    )
    flagged = [row for row in log if row["trigger_type"] == "flag"]
    if not flagged or any(row["outcome"] != "sent" for row in flagged):
        raise fail("the flag goes straight to the roster", why=f"got {flagged}")
    if any(row["to_person_id"] == pa.person_id for row in flagged):
        raise fail("a red flag skips his own rung", why=f"got {flagged}")
    # Every way each person can be reached, and the notice on their family page besides
    # (#162): the line names the first rung's WhatsApp.
    rung = next((row for row in reversed(flagged) if row["channel"] == "whatsapp"), flagged[-1])
    said = fell["replies"][0]["text"].splitlines() if fell["replies"] else []
    if said != [
        "This one we do not wait for.",
        "Go to the emergency department at Gleneagles now.",
        "Gleneagles is on your insurance.",
        "If you cannot get there safely, call the ambulance now on 995.",
        "Mei knows now.",
        "Nura does not decide what is wrong.",
    ]:
        raise fail("out of hours, the hospital on his insurance, never the doctor today", why=f"got {said}")
    ok(
        "22:30, inside the quiet hours: a red flag, written first, went straight to the roster — "
        f"{rung['standing']}, {rung['outcome']} by {rung['channel']} ({rung['template_name']}), "
        f"category {rung['category']}, never capped and never quiet; not to him. A fall is the "
        "same-day tier, and Dr Tan's clinic is closed at 22:30: never \"call your doctor today\" — "
        "the emergency department of the hospital on his insurance, named (E19-05). His reply:"
    )
    for sent in fell["replies"]:
        for line in sent["text"].splitlines():
            say(f"→ {line}")
    later = w.run_due(profile_id, 22, 36)
    nights = _of(later, "flag")
    if any(row["outcome"] != "sent" for row in nights):
        raise fail("the flag's next rung goes at night too", why=f"got {nights}")
    if any(row["outcome"] == "sent" for row in later if row["trigger_type"] != "flag"):
        raise fail("a reminder waits out the quiet hours", why=f"got {later}")
    if nights:
        ok(
            "22:36, nobody had answered: the next rung, still at night — "
            + "; ".join(_line(row) for row in nights)
            + "; nothing else went: a reminder waits out the quiet hours"
        )
    else:
        ok("22:36, nobody left to ask on the ladder; nothing else went in the quiet hours")

    # 7. Today's top three, with why, the next morning (at 22:37 the quiet hours hold every
    #    card but the flag); one card played as voice.
    w.clock(7, 30, days=1)
    top = check(
        client.get(f"/profiles/{profile_id}/feed/today", headers=bearer(pa.token)),
        200,
        "Pa's top three",
    )
    items = top["items"]
    if not items or items[0]["category"] != "alert":
        raise fail("the top three lead with the alert", why=f"got {items}")
    if any(not item["why"]["plain"] for item in items):
        raise fail("every card explains itself", why=f"got {items}")
    ok(
        "07:30 the next morning, the flag still inside its day: today's top three "
        "(GET /profiles/{id}/feed/today) — alerts first, then reminders, then insights:"
    )
    for item in items:
        say(
            f"[{item['category']:8}] {item['headline']} — one action: {item['action']}, "
            f"on the {item['colour']} wash. Why: {item['why']['plain']}"
        )
    card = items[1] if len(items) > 1 else items[0]
    played = client.get(
        f"/profiles/{profile_id}/feed/{card['item_id']}/voice", headers=bearer(pa.token)
    )
    if played.status_code != 200 or not played.headers.get("content-type", "").startswith("audio/"):
        raise fail("one card played as voice", played)
    seconds = float(played.headers["x-duration-seconds"])
    if seconds >= 30:
        raise fail("a voice note is under thirty seconds", why=f"{seconds} seconds")
    ok(
        f'"{card["headline"]}" played as its spoken twin (GET …/feed/{{item}}/voice): '
        f"{played.headers['content-type']}, {len(played.content)} bytes, {seconds} seconds, "
        f"cache {played.headers['x-voice-cache']} — the fixture voice is silence as long as the "
        "words take to say"
    )
    rules = sorted({row["rule"] for row in check(
        client.get(f"/profiles/{profile_id}/deliveries", headers=bearer(pa.token)),
        200,
        "the delivery log",
    )})
    ok(f"every attempt is on the delivery log with the rule that fired: {', '.join(rules)}")

    # 8. The pre-visit brief at T-3 (E05-01): a visit with Dr Tan on Friday 18 September; at
    #    07:40 on Tuesday the 15th — three days before, after his breakfast — the engine
    #    renders the brief and sends its card, once, under the cap on briefs a day.
    listed = check(client.get(f"/profiles/{profile_id}/providers", headers=bearer(pa.token)), 200, "his directory")
    tan = next(one["provider"] for one in listed if one["provider"]["name"] == "Dr Tan")
    booking = {
        "provider_id": tan["provider_id"],
        "scheduled_at": datetime(2026, 9, 18, 10, 0, tzinfo=SGT).isoformat(),
        "purpose": "blood pressure",
    }
    yes = check(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=bearer(pa.token),
            json={"subject": "appointment", **booking},
        ),
        201,
        "Pa says yes to the booking",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/appointments",
            headers=bearer(pa.token),
            json={**booking, "confirmation_id": yes["confirmation_id"]},
        ),
        201,
        "Pa writes down the visit",
    )
    w.clock(7, 40, days=1)
    ran = check(client.post("/dev/run-triggers", json={"profile_id": profile_id}), 200, "the engine runs at 07:40")
    briefs = [row for row in ran["deliveries"] if row["trigger_type"] == "visit_brief"]
    if (
        len(briefs) != 1
        or briefs[0]["outcome"] != "sent"
        or briefs[0]["rule"] != "brief_three_days_before"
        or briefs[0]["template_name"] != "visit_brief"
    ):
        raise fail("the brief at T-3", why=f"got {ran['deliveries']}")
    w.clock(8, 10, days=1)
    again = check(client.post("/dev/run-triggers", json={"profile_id": profile_id}), 200, "the engine runs at 08:10")
    if any(row["trigger_type"] == "visit_brief" for row in again["deliveries"]):
        raise fail("the brief goes once", why=f"got {again['deliveries']}")
    ok(
        "07:40 on Tuesday 15 September, three days before his visit with Dr Tan on Friday 18 "
        "September: the pre-visit brief was rendered then and its card sent — "
        + _line(briefs[0])
        + "; 08:10 sends it no second time. What he reads:"
    )
    for line in (briefs[0].get("text") or "").splitlines():
        say(f"→ {line}")


def run(base_url: str, dev_log: Path) -> int:
    try:
        with httpx.Client(base_url=base_url, timeout=20.0) as client:
            walk(client, dev_log)
    except Failed as failed:
        print(str(failed), flush=True)
        return 1
    return 0
