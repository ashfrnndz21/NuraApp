"""Checkpoint 23 — Same words every time; the pharmacist's queue (E22-02, E22-03, E22-04).

    make dev                # one terminal
    make checkpoint N=23    # another: this module, through scripts/checkpoint.py

First the translation memory, the way `make language` runs it: every patient string in every
catalogue — cards, WhatsApp, the web client — in English, Malay and Chinese, 0 failures, and
the red-flag line one line in each language on the card, the reply and the notice. Then three
patients with fresh numbers every run — Pa in English with Mei holding a key, Kit in Chinese,
Aminah in Malay — each writes down a blood pressure, and each card comes back with its voice
script: the numbers as words in the card's language, a pause after each line, a longer one
before the boundary. Then the pharmacist, by the staff token `make dev` sets: the first cards
of each type in the queue with nobody in them ({name}, no profile id), a type flagged until its
first fifty are decided, Pa's own key refused, a rewrite that proposes a catalogue change and
changes nothing he sees, and a new source that no job may search until it is approved.

Self-contained: every helper this module needs is here, so the shared runner only dispatches.
It is a client and nothing more, except that it runs `python3 -m app.language.memory` the way
`make language` does, from the backend directory. `run(base_url, dev_log)` prints ✓/✗ lines in
the runner's style and returns 0 or 1.
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

CODE_LINE = re.compile(r"login code for (\+[0-9]+): ([0-9]{6})")
CODE_WAIT_SECONDS = 3.0
HOLD_WORDING = "1"
BACKEND = Path(__file__).resolve().parents[2]
STAFF_TOKEN = os.environ.get("NURA_REVIEW_STAFF_TOKEN", "nura-dev-pharmacist-token-0001")
"""The laptop's staff token `make dev` puts on NURA_REVIEW_STAFF_TOKENS (the Makefile)."""
RED_FLAG = "This one we do not wait for."
BOUNDARY_PAUSE_MS = 1200
WALL = timezone(timedelta(hours=8))
"""Singapore and Malaysia keep the same clock."""

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


def refused(response: httpx.Response, status: int, refusal: str, what: str) -> JSON:
    body = check(response, status, what)
    if not isinstance(body, dict) or body.get("refusal") != refusal:
        raise fail(what, response, f"expected refusal {refusal}")
    return body


def fresh_phone(prefix: str) -> str:
    return f"{prefix}{random.randint(0, 9999):04d}"


def code_from_log(dev_log: Path, phone_e164: str) -> str:
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
    started = client.post(
        "/auth/phone/start",
        json={"phone_e164": person.phone_e164, "display_name": person.name, "language": language},
    )
    check(started, 202, f"{who} asks for a code by phone")
    code = code_from_log(dev_log, person.phone_e164)
    verified = client.post("/auth/phone/verify", json={"phone_e164": person.phone_e164, "code": code})
    session = check(verified, 200, f"{who} types the code in")
    person.token = session["token"]
    person.person_id = session["person_id"]
    ok(f"{who} registered by phone code and signed in (the code read from the server log)")


def open_profile(client: httpx.Client, person: Person, language: str) -> str:
    consent = {"wording_version": HOLD_WORDING, "language": language, "captured_via": "app"}
    created = check(
        client.post(
            "/profiles/mine",
            json={"consent": consent, "language": language},
            headers=bearer(person.token),
        ),
        201,
        f"{person.name} opens his own papers in {language}",
    )
    return str(created["profile_id"])


def reading(client: httpx.Client, person: Person, profile_id: str, top: int, bottom: int) -> None:
    check(
        client.post(
            f"/profiles/{profile_id}/readings",
            json={"systolic": top, "diastolic": bottom},
            headers=bearer(person.token),
        ),
        201,
        f"{person.name} writes down {top}/{bottom}",
    )


def daytime() -> str:
    """Ten in the morning today on his clock: the feed keeps quiet at night, and `?at=` is how a
    dev run pretends it is day for that check (as checkpoint 8 does)."""
    return datetime.now(WALL).replace(hour=10, minute=0, second=0, microsecond=0).isoformat()


def feed(client: httpx.Client, person: Person, profile_id: str) -> JSON:
    page: JSON = check(
        client.get(
            f"/profiles/{profile_id}/feed", params={"at": daytime()}, headers=bearer(person.token)
        ),
        200,
        f"{person.name} opens his feed",
    )
    return page


def card(page: JSON, kind: str, who: str) -> JSON:
    for item in page["items"]:
        if item["type"] == kind:
            return dict(item)
    raise fail(f"{who}'s feed has a {kind} card", why=f"types: {[i['type'] for i in page['items']]}")


def staff() -> dict[str, str]:
    return bearer(STAFF_TOKEN)


def spoken(item: JSON) -> list[str]:
    return [f"{s['text']}  ⟨{s['pause_ms']} ms⟩" for s in item["voice_script"]["segments"]]


# --- the walk ---------------------------------------------------------------------------------


def the_memory() -> None:
    """`make language`, and the red-flag line in three languages across the catalogues."""
    ran = subprocess.run(
        [sys.executable, "-m", "app.language.memory", "--json"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    if ran.returncode != 0:
        raise Failed(f"✗ make language failed:\n{ran.stdout[-2000:]}{ran.stderr[-2000:]}")
    report = json.loads(ran.stdout)
    ok(
        f"make language: {report['strings']} strings, {report['keys']} keys in "
        f"{report['catalogues']} catalogues (backend and web), {len(report['failures'])} failures, "
        f"{len(report['notes'])} notes — the notes are consent words and WhatsApp templates, "
        "which change only as a new version: follow-ups, not failures"
    )
    table = json.loads(
        subprocess.run(
            [sys.executable, "-m", "app.language.memory", "--table"],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    groups: dict[tuple[str, str], dict[str, str]] = {}
    for entry in table:
        groups.setdefault((entry["catalogue"], entry["key"]), {})[entry["language"]] = entry["text"]
    said: dict[str, set[str]] = {"ms": set(), "zh": set()}
    where: set[str] = set()
    for (catalogue, _), by in groups.items():
        if by.get("en") == RED_FLAG and not catalogue.endswith("whatsapp/templates"):
            where.add("/".join(catalogue.split("/")[-2:]))
            for code, texts in said.items():
                if code in by:
                    texts.add(by[code])
    if len(said["ms"]) != 1 or len(said["zh"]) != 1:
        raise Failed(f"✗ “{RED_FLAG}” is said more than one way: {said}")
    ok(f"“{RED_FLAG}” is one line in each language on the card, the reply and the notice ({', '.join(sorted(where))}):")
    say(f"Malay: {next(iter(said['ms']))}")
    say(f"Chinese: {next(iter(said['zh']))}")


def the_voice(client: httpx.Client, dev_log: Path) -> tuple[Person, str, int, int, list[str]]:
    pa = Person("Pa", fresh_phone("+659223"))
    mei = Person("Mei", fresh_phone("+659224"))
    register(client, dev_log, pa, "en")
    register(client, dev_log, mei, "en")
    profile_id = open_profile(client, pa, "en")
    scopes = ["medicines", "readings", "family"]
    check(
        client.post(
            f"/profiles/{profile_id}/consents/sharing",
            json={
                "holder_phone_e164": mei.phone_e164,
                "scopes": scopes,
                "relationship": "daughter",
                "language": "en",
                "captured_via": "app",
            },
            headers=bearer(pa.token),
        ),
        201,
        "Pa agrees to let Mei in",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            json={"holder_phone_e164": mei.phone_e164, "role": "caregiver", "scopes": scopes},
            headers=bearer(pa.token),
        ),
        201,
        "Pa cuts Mei a caregiver key",
    )
    top, bottom = random.randint(121, 149), random.randint(71, 89)
    reading(client, pa, profile_id, top, bottom)
    page = feed(client, pa, profile_id)
    card_ = card(page, "reading", "Pa")
    segments = card_["voice_script"]["segments"]
    if re.search(r"\d", segments[0]["text"]) or "over" not in segments[0]["text"]:
        raise fail("Pa's reading card is said with its numbers as words", why=segments[0]["text"])
    if any(item["voice_script"]["digest"] == "" for item in page["items"]):
        raise fail("every card carries its voice script", why="a card with no digest")
    ok(
        f"Pa ({top}/{bottom}, Mei holds a key): every card on his feed carries its voice script, "
        "computed from its verified voice lines — the reading card is said:"
    )
    for line in spoken(card_):
        say(line)
    learning = [item for item in page["items"] if item["type"] == "learning"]
    if learning:
        pauses = [s["pause_ms"] for s in learning[0]["voice_script"]["segments"]]
        closing = len((learning[0]["boundary"] or "").splitlines())
        if closing and pauses[-closing - 1] != BOUNDARY_PAUSE_MS:
            raise fail("the learning card pauses longer before its boundary", why=str(pauses))
        ok("the learning card pauses longer before the boundary it ends on:")
        for line in spoken(learning[0])[-closing - 1 :]:
            say(line)
    for name, language, word in (("Kit", "zh", "比"), ("Aminah", "ms", "atas")):
        person = Person(name, fresh_phone("+659225" if language == "zh" else "+659226"))
        register(client, dev_log, person, language)
        own = open_profile(client, person, language)
        reading(client, person, own, top, bottom)
        said = card(feed(client, person, own), "reading", name)
        first = said["voice_script"]["segments"][0]["text"]
        if re.search(r"\d", first) or word not in first:
            raise fail(f"{name}'s reading card is said in {language} with the numbers as words", why=first)
        ok(f"{name}'s card in {'Chinese' if language == 'zh' else 'Malay'}: “{said['body'][0]}” is said “{first}”")
    return pa, profile_id, top, bottom, [pa.name, mei.name, "Kit", "Aminah", pa.phone_e164, mei.phone_e164]


def the_queue(
    client: httpx.Client, pa: Person, profile_id: str, top: int, bottom: int, names: list[str]
) -> None:
    refused(client.get("/review/queue", headers=bearer(pa.token)), 403, "NotStaff", "Pa's own key on the queue")
    refused(client.get("/review/queue"), 403, "NotStaff", "no key on the queue")
    ok("the queue is staff's: Pa's own key is refused, NotStaff (403), and so is no key at all")

    status = check(client.get("/review/status", headers=staff()), 200, "the pharmacist reads the status")
    flagged = [t["card_type"] for t in status["card_types"] if t["flag"]]
    ok(f"GET /review/status: the first {status['first']} of each card type, {status['sources_pending']} sources waiting; flagged until their first fifty are decided: {', '.join(flagged)}")
    for t in status["card_types"]:
        if t["sampled"]:
            say(f"{t['card_type']:<9} {t['sampled']:>2} queued, {t['reviewed']:>2} decided, flag {t['flag']}")

    queued = check(
        client.get(
            "/review/queue",
            params={"card_type": "reading", "verdict": "any", "limit": 500},
            headers=staff(),
        ),
        200,
        "the pharmacist reads the reading cards in the queue",
    )
    wanted = f"Your blood pressure today was {top} over {bottom}."
    mine = [item for item in queued if item["lines"]["body"][:1] == [wanted]]
    if not mine:
        reading_status = next(t for t in status["card_types"] if t["card_type"] == "reading")
        why = (
            "the first fifty readings are already queued on this dev.db: `make reset-db`"
            if reading_status["sampled"] >= status["first"]
            else "not in the queue"
        )
        raise fail(f"Pa's reading card ({wanted}) is in the queue", why=why)
    sample = mine[0]
    if "{name} can see it too." not in sample["lines"]["body"]:
        raise fail("Mei's name is a slot in the sample", why=str(sample["lines"]["body"]))
    everything = json.dumps(
        check(client.get("/review/queue", params={"verdict": "any", "limit": 500}, headers=staff()), 200, "the whole queue"),
        ensure_ascii=False,
    )
    leaked = [n for n in [*names, profile_id, pa.person_id] if re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", everything)]
    if leaked:
        raise fail("nothing in the queue names anyone", why=f"found {leaked}")
    ok(f"Pa's reading card is sample {sample['sample_number']} of its type, lines only — no profile id, no name, Mei is {{name}}:")
    for line in sample["lines"]["body"]:
        say(line)
    say(f"filled from: {', '.join(sample['catalogue_ids'][:4])}")

    body = list(sample["lines"]["body"])
    body[1] = "Nura keeps it in your blood pressure book."
    rewritten = check(
        client.post(
            f"/review/items/{sample['item_id']}/rewrite",
            json={"lines": {"body": body}, "reason": "Say who keeps it."},
            headers=staff(),
        ),
        200,
        "the pharmacist rewrites a line",
    )
    change = rewritten["proposed"]["changes"][0]
    ok("a rewrite is a proposed catalogue change, checked by the plain-words verifier, and nothing more:")
    say(f"{change['catalogue_id']}")
    say(f"from: {change['from']}")
    say(f"to:   {change['to']}")
    again = card(feed(client, pa, profile_id), "reading", "Pa")
    if "It is in your blood pressure book." not in again["body"]:
        raise fail("Pa's card still says the catalogue's words", why=str(again["body"]))
    proposals = check(client.get("/review/proposals", headers=staff()), 200, "the proposals")
    if sample["item_id"] not in {p["item_id"] for p in proposals}:
        raise fail("the rewrite is listed in GET /review/proposals")
    ok("Pa's card still says “It is in your blood pressure book.”; the rewrite waits in GET /review/proposals for a person to make it in the catalogue")

    pending = check(client.get("/review/queue", params={"kind": "card"}, headers=staff()), 200, "pending cards")
    if pending:
        first = pending[0]
        decided = check(
            client.post(f"/review/items/{first['item_id']}/approve", json={}, headers=staff()),
            200,
            "the pharmacist approves a card",
        )
        again_ = client.post(
            f"/review/items/{first['item_id']}/reject", json={"reason": "second thoughts"}, headers=staff()
        )
        refused(again_, 409, "AlreadyReviewed", "a decided item is decided again")
        ok(f"the pharmacist approves the {first['card_type']} card (decided by {decided['decided_by']}); deciding it again is refused, AlreadyReviewed (409)")


def the_sources(client: httpx.Client, pa: Person, profile_id: str) -> None:
    domain = f"cp23-{random.randint(0, 99999):05d}.example.sg"
    proposed = check(
        client.post(
            "/review/sources",
            json={"name": "A heart page for checkpoint 23", "domain": domain, "kind": "hospital", "regions": ["SG"], "languages": ["en"]},
            headers=staff(),
        ),
        201,
        "the pharmacist proposes a new source",
    )
    job = {"kind": "explainer", "terms": ["blood pressure"], "source_ids": [proposed["source_id"]], "cadence": "once", "reason": "a new page about his heart"}
    refused(
        client.post(f"/profiles/{profile_id}/search-jobs", json=job, headers=bearer(pa.token)),
        400,
        "SourceNotAllowlisted",
        "a search of a source still waiting for review",
    )
    ok(f"{domain} is on the list as pending: a self-search naming it is refused, SourceNotAllowlisted (400) — nothing from it can reach Pa")
    check(client.post(f"/review/items/{proposed['item_id']}/approve", json={}, headers=staff()), 200, "the pharmacist approves the source")
    check(client.post(f"/profiles/{profile_id}/search-jobs", json=job, headers=bearer(pa.token)), 201, "a search of the approved source")
    ok("approved, it is allowlisted: the same self-search is accepted (201)")
    other = check(
        client.post(
            "/review/sources",
            json={"name": "A shop that sells supplements", "domain": "shop-" + domain, "kind": "society", "regions": ["SG"], "languages": ["en"]},
            headers=staff(),
        ),
        201,
        "the pharmacist proposes a second source",
    )
    check(
        client.post(f"/review/items/{other['item_id']}/reject", json={}, headers=staff()),
        422,
        "a rejection with no reason is refused",
    )
    check(
        client.post(f"/review/items/{other['item_id']}/reject", json={"reason": "It sells supplements."}, headers=staff()),
        200,
        "the pharmacist rejects the second source",
    )
    listed = check(client.get(f"/profiles/{profile_id}/sources", headers=bearer(pa.token)), 200, "Pa's allowlist")
    shop = next((s for s in listed if s["domain"] == "shop-" + domain), None)
    if shop is None or shop["allowlisted"] or shop["review_status"] != "rejected":
        raise fail("the rejected source stays off the allowlist", why=str(shop))
    ok("the second source is rejected with a reason and stays off: allowlisted false, review_status rejected")


def walk(client: httpx.Client, dev_log: Path) -> None:
    the_memory()
    pa, profile_id, top, bottom, names = the_voice(client, dev_log)
    the_queue(client, pa, profile_id, top, bottom, names)
    the_sources(client, pa, profile_id)


def run(base_url: str, dev_log: Path) -> int:
    """Walk checkpoint 23 against the server at `base_url`; 0 when every step is a ✓."""
    try:
        with httpx.Client(base_url=base_url, timeout=20.0) as client:
            walk(client, Path(dev_log))
    except Failed as failed:
        print(str(failed), flush=True)
        return 1
    return 0
