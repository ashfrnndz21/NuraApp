"""Walk one checkpoint from `docs/checkpoints.md` against the dev server, over HTTP only.

    make dev              # one terminal: migrates dev.db and serves on :8000
    make checkpoint N=2   # another: this script

Every step prints one line, `✓ <what it proved>` or `✗ <what failed> (<status>, <body>)`, and
the run stops at the first ✗ with a non-zero exit. The script is a client and nothing more:
it never imports the app, never opens the database, and reads the login code the way the
owner would — from the server log, which `make dev` also writes to `backend/.dev.log`
(gitignored) because the log itself is on the other terminal's screen. Each run registers
fresh phone numbers, so it can be run again on the same dev.db; `make reset-db` starts over.
"""

from __future__ import annotations

import base64
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

BASE_URL = os.environ.get("NURA_BASE_URL", "http://127.0.0.1:8000")
DEV_LOG = Path(os.environ.get("NURA_DEV_LOG", Path(__file__).resolve().parent.parent / ".dev.log"))
LOG_NAME = os.environ.get("NURA_DEV_LOG", "backend/.dev.log")
"""How the log is named in a message: the path as the owner knows it from the repo root."""
CODE_LINE = re.compile(r"login code for (\+[0-9]+): ([0-9]{6})")
"""What `LoggingCodeSender` logs on a dev run; see `app/identity/providers.py`."""
CODE_WAIT_SECONDS = 3.0

HOLD_WORDING = "1"
"""Today's words for `hold_health_record`, from `app/consent/texts.py`. Move this when they move."""
STALE_WORDING = "0"
"""A version that was never on file: opening a profile on it must refuse."""

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
LIPID_PANEL = "lipid-panel-2023-09-07"
WARFARIN_LABEL = "warfarin-label-2024-03-12"
CONFIDENCE_THRESHOLD = 0.8
"""Below this a field is shown dotted; `app/ingestion/models.py`. Move this when it moves."""

VISIT_FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "visits"
"""The visit transcripts the fixture summariser knows (E05). The script reads the transcript
text from the JSON beside it, the way the owner would paste it, and uploads that."""
ROUTINE_VISIT = "routine-bp-review"
RED_FLAG_VISIT = "red-flag-chest-pain"


def placeholder_png(label: str) -> bytes:
    """The bytes that stand in for one redacted paper — the same three lines as
    `backend/tests/paper.py`, so the fixture extractor recognises the digest. No photo is
    committed; the JSON beside each in `backend/tests/fixtures/paper/` is what it reads."""
    return PNG_SIGNATURE + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"


JSON = dict[str, Any]


class Failed(Exception):
    """One step did not do what the checkpoint says. Carries the printed line."""


def bearer(token: str | None) -> dict[str, str]:
    return {} if token is None else {"Authorization": f"Bearer {token}"}


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
    """The response body as JSON if the status is the expected one; otherwise ✗."""
    if response.status_code != status:
        raise fail(what, response, f"expected {status}")
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def refused(response: httpx.Response, status: int, refusal: str, what: str) -> JSON:
    """A refusal with this name, and nothing else in the body; otherwise ✗."""
    body = check(response, status, what)
    if not isinstance(body, dict) or body.get("refusal") != refusal:
        raise fail(what, response, f"expected refusal {refusal}")
    return body


# --- the login code ----------------------------------------------------------------------


def code_from_log(phone_e164: str, since: float) -> str:
    """The last login code the server logged for this number, waiting briefly for the line.

    The number is fresh for this run, so any line naming it is this run's. A missing file,
    or a file that stops updating, means the server on the other terminal is not the one
    `make dev` starts — that is the only one that writes the log here.
    """
    deadline = time.monotonic() + CODE_WAIT_SECONDS
    while True:
        if DEV_LOG.exists():
            found = [m for m in CODE_LINE.finditer(DEV_LOG.read_text(errors="replace"))]
            codes = [m.group(2) for m in found if m.group(1) == phone_e164]
            if codes:
                return codes[-1]
        if time.monotonic() > deadline:
            break
        time.sleep(0.2)
    if not DEV_LOG.exists():
        raise Failed(
            f"✗ {LOG_NAME} is missing: start the server with `make dev` in another terminal "
            "(it writes the server log there, and that is where the login code is read from)"
        )
    stale = DEV_LOG.stat().st_mtime < since
    raise Failed(
        f"✗ no login code for {phone_e164} appeared in {LOG_NAME} within {CODE_WAIT_SECONDS:.0f}s"
        + (" — the file has not changed since this run began" if stale else "")
        + ". The server answering /health is not the one `make dev` started; stop it and run "
        "`make dev` (only that writes the log here, with NURA_DEV_CODE_SENDER=1)"
    )


def fresh_phone(prefix: str) -> str:
    """A Singapore-shaped number nobody has used on this dev.db: random last four digits."""
    return f"{prefix}{random.randint(0, 9999):04d}"


# --- the walk ----------------------------------------------------------------------------


class Person:
    def __init__(self, name: str, phone_e164: str) -> None:
        self.name = name
        self.phone_e164 = phone_e164
        self.token: str = ""
        self.person_id: str = ""


def register(client: httpx.Client, person: Person, language: str) -> None:
    """Start and verify a phone login. One ✓ for the three things it proves."""
    who = f"{person.name} ({person.phone_e164})"
    began = time.time()
    started = client.post(
        "/auth/phone/start",
        json={"phone_e164": person.phone_e164, "display_name": person.name, "language": language},
    )
    body = check(started, 202, f"{who} asks for a code by phone")
    if "code" in str(body):
        raise fail(f"{who} asks for a code by phone", started, "the code came back on the wire")
    code = code_from_log(person.phone_e164, began)
    verified = client.post(
        "/auth/phone/verify", json={"phone_e164": person.phone_e164, "code": code}
    )
    session = check(verified, 200, f"{who} types the code in")
    person.token = session["token"]
    person.person_id = session["person_id"]
    ok(
        f"{who} registered by phone code: asked (202, no code in the answer), "
        f"read the six digits from {LOG_NAME} — no SMS — and signed in (200, token issued)"
    )


def checkpoint_2(client: httpx.Client) -> None:
    pa = Person("Pa", fresh_phone("+659111"))
    mei = Person("Mei", fresh_phone("+659222"))

    # 1. Pa registers by phone.
    register(client, pa, "ms")
    me = check(client.get("/me", headers=bearer(pa.token)), 200, "Pa asks who he is")
    if me["profile_id"] is not None:
        raise fail(
            "Pa asks who he is", why="a fresh number already owns a profile; run make reset-db"
        )
    ok("Pa's account has no profile yet (GET /me)")

    # 2. Opens his own profile — first on stale words (refused), then on today's.
    stale = client.post(
        "/profiles/mine",
        headers=bearer(pa.token),
        json={
            "consent": {"wording_version": STALE_WORDING, "language": "ms", "captured_via": "app"},
            "display_name": pa.name,
            "language": "ms",
        },
    )
    refused(stale, 400, "NotTheCurrentWording", "Pa agrees to words that are not today's")
    ok(
        f"opening a profile on stale wording (version {STALE_WORDING}) was refused: "
        "NotTheCurrentWording (400), nothing opened"
    )
    opened = check(
        client.post(
            "/profiles/mine",
            headers=bearer(pa.token),
            json={
                "consent": {
                    "wording_version": HOLD_WORDING,
                    "language": "ms",
                    "captured_via": "app",
                },
                "display_name": pa.name,
                "language": "ms",
            },
        ),
        201,
        "Pa opens his own profile",
    )
    profile_id: str = opened["profile_id"]
    if opened["role"] is not None or not {"notes", "medicines", "family"} <= set(opened["scopes"]):
        raise fail("Pa opens his own profile", why=f"expected the owner's reach, got {opened}")
    ok(
        f"Pa opened his own profile (wording {HOLD_WORDING}, in Malay, in the app), agreeing to "
        "Nura keeping his record; as its owner he needs no key and every part is open to him"
    )

    # 3. A private note.
    check(
        client.post(
            f"/profiles/{profile_id}/notes",
            headers=bearer(pa.token),
            json={"text": "I did not tell the children about the fall."},
        ),
        201,
        "Pa writes a private note",
    )
    ok("Pa wrote a private note (scope notes: open to its owner, not to a caregiver key)")

    # 4. The daughter registers the same way.
    register(client, mei, "en")

    # 5. A key before consent is refused.
    grant = {
        "holder_phone_e164": mei.phone_e164,
        "role": "caregiver",
        "scopes": ["medicines", "visits"],
        "window": "thirty_days",
    }
    early = client.post(f"/profiles/{profile_id}/keys", headers=bearer(pa.token), json=grant)
    refused(early, 403, "ConsentWithheld", "Pa cuts Mei a key before agreeing to share")
    ok("a caregiver key for Mei before Pa agreed to share was refused: ConsentWithheld (403)")

    # 6. Pa lets his daughter in to medicines and visits.
    consent = check(
        client.post(
            f"/profiles/{profile_id}/consents/sharing",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "scopes": ["medicines", "visits"],
                "relationship": "daughter",
                "language": "en",
                "captured_via": "app",
            },
        ),
        201,
        "Pa agrees to let Mei see medicines and visits",
    )
    if consent["holder_person_id"] != mei.person_id or set(consent["scopes"]) != {
        "medicines",
        "visits",
    }:
        raise fail("Pa agrees to let Mei see medicines and visits", why=f"recorded as {consent}")
    ok("Pa agreed to let Mei, his daughter, see his medicines and visits; the words he read:")
    for line in consent["wording_text"].splitlines():
        print(f"    {line}")

    # 7. And cuts her a caregiver key on that consent.
    key = check(
        client.post(f"/profiles/{profile_id}/keys", headers=bearer(pa.token), json=grant),
        201,
        "Pa cuts Mei a caregiver key",
    )
    if key["consent_id"] != consent["consent_id"] or key["expires_at"] is None:
        raise fail("Pa cuts Mei a caregiver key", why=f"not on that consent for 30 days: {key}")
    if set(key["scopes"]) != {"medicines", "visits", "profile"}:
        raise fail("Pa cuts Mei a caregiver key", why=f"scopes {key['scopes']}")
    ok(
        "Pa cut Mei a caregiver key: medicines and visits (and whose profile it is), "
        "for thirty days, resting on that consent"
    )

    # 8. She reads what the key opens and is refused on the rest.
    seen = check(
        client.get(f"/profiles/{profile_id}", headers=bearer(mei.token)),
        200,
        "Mei opens Pa's profile",
    )
    if seen["role"] != "caregiver" or seen["display_name"] != pa.name:
        raise fail("Mei opens Pa's profile", why=f"got {seen}")
    ok("Mei opens Pa's profile with her key: his name and language, as caregiver")
    medicines = check(
        client.get(f"/profiles/{profile_id}/medicines", headers=bearer(mei.token)),
        200,
        "Mei reads Pa's medicines",
    )
    if medicines != []:
        raise fail("Mei reads Pa's medicines", why=f"expected none yet, got {medicines}")
    ok("Mei reads Pa's medicines: allowed, and none are recorded yet ([])")
    notes = client.get(f"/profiles/{profile_id}/notes", headers=bearer(mei.token))
    body = refused(notes, 403, "OutOfScope", "Mei reads Pa's notes")
    if body.get("scope") != "notes" or "fall" in notes.text:
        raise fail("Mei reads Pa's notes", notes, "expected scope notes and no note text")
    ok("Mei reads Pa's notes: refused, OutOfScope notes (403); the note itself never left")
    refused(
        client.get(f"/profiles/{profile_id}/consents", headers=bearer(mei.token)),
        403,
        "OutOfScope",
        "Mei reads Pa's consents",
    )
    ok("Mei reads Pa's consents: refused, OutOfScope family (403); only Pa or his chief may")

    # 9. Pa reads his consents, his keys and the trail.
    consents = check(
        client.get(f"/profiles/{profile_id}/consents", headers=bearer(pa.token)),
        200,
        "Pa lists his consents",
    )
    purposes = [row["purpose"] for row in consents]
    if "hold_health_record" not in purposes or "share_with_family" not in purposes:
        raise fail("Pa lists his consents", why=f"purposes {purposes}")
    ok(
        "Pa lists his consents: hold_health_record and share_with_family (naming Mei), both in force"
    )
    keys = check(
        client.get(f"/profiles/{profile_id}/keys", headers=bearer(pa.token)),
        200,
        "Pa lists his keys",
    )
    roles = sorted(row["role"] for row in keys)
    if "caregiver" not in roles:
        raise fail("Pa lists his keys", why=f"roles {roles}")
    ok(f"Pa lists the keys cut on his profile: {', '.join(roles)} (he holds none: it is his)")
    trail = check(
        client.get(f"/profiles/{profile_id}/audit", headers=bearer(pa.token)),
        200,
        "Pa reads his audit trail",
    )
    refusals = [row for row in trail if row["outcome"] == "refused"]
    by_mei = [row for row in refusals if row["actor_person_id"] == mei.person_id]
    if not any(
        row["refused_because"] == "OutOfScope" and row["scope"] == "notes" for row in by_mei
    ):
        raise fail("Pa reads his audit trail", why="no refused OutOfScope notes read by Mei")
    if not any(row["refused_because"] == "ConsentWithheld" for row in refusals):
        raise fail("Pa reads his audit trail", why="no refused ConsentWithheld line")
    ok(f"Pa reads his audit trail ({len(trail)} lines, newest first); the refusals are on it:")
    for row in refusals:
        who = "Mei" if row["actor_person_id"] == mei.person_id else "Pa"
        print(
            f"    {row['at'][:19]}  {who:>3}  {row['action']} {row['scope']} "
            f"{row['target']}  refused {row['refused_because']}"
        )

    # 10. He closes her key; her next reach is NoKey, and it is in his trail.
    closed = check(
        client.delete(f"/profiles/{profile_id}/keys/{key['key_id']}", headers=bearer(pa.token)),
        200,
        "Pa revokes Mei's key",
    )
    if closed["revoked_at"] is None:
        raise fail("Pa revokes Mei's key", why=f"not marked revoked: {closed}")
    ok("Pa revoked Mei's key")
    refused(
        client.get(f"/profiles/{profile_id}/medicines", headers=bearer(mei.token)),
        403,
        "NoKey",
        "Mei reads Pa's medicines after the key is closed",
    )
    ok("Mei's next read is refused: NoKey (403), medicines included")
    trail = check(
        client.get(f"/profiles/{profile_id}/audit", headers=bearer(pa.token)),
        200,
        "Pa reads his trail again",
    )
    newest = trail[0] if trail else {}
    if not (
        newest.get("outcome") == "refused"
        and newest.get("refused_because") == "NoKey"
        and newest.get("actor_person_id") == mei.person_id
    ):
        raise fail("Pa reads his trail again", why=f"newest line is not Mei's NoKey: {newest}")
    ok("that reach is on Pa's trail: the newest line is Mei's refused read, NoKey")

    # 11. Nothing without a token; logout closes the session.
    refused(client.get(f"/profiles/{profile_id}/notes"), 401, "NoSession", "a read with no token")
    ok("a read with no token is refused: NoSession (401)")
    check(client.post("/auth/logout", headers=bearer(mei.token)), 204, "Mei signs out")
    refused(client.get("/me", headers=bearer(mei.token)), 401, "NoSession", "Mei after signing out")
    ok("Mei signed out (204); her token is refused from then on: NoSession (401)")


def open_own_profile(client: httpx.Client, person: Person, language: str) -> str:
    """Register, then open the person's own profile on today's words. Two ✓ lines."""
    register(client, person, language)
    opened = check(
        client.post(
            "/profiles/mine",
            headers=bearer(person.token),
            json={
                "consent": {
                    "wording_version": HOLD_WORDING,
                    "language": language,
                    "captured_via": "app",
                },
                "display_name": person.name,
                "language": language,
            },
        ),
        201,
        f"{person.name} opens his own profile",
    )
    profile_id: str = opened["profile_id"]
    ok(
        f"{person.name} opened his own profile (wording {HOLD_WORDING}, in the app); "
        "as its owner every part is open to him"
    )
    return profile_id


def read_state(client: httpx.Client, person: Person, profile_id: str, what: str) -> JSON:
    state: JSON = check(
        client.get(f"/profiles/{profile_id}/state", headers=bearer(person.token)), 200, what
    )
    return state


def checkpoint_3(client: httpx.Client) -> None:
    pa = Person("Pa", fresh_phone("+659111"))
    mei = Person("Mei", fresh_phone("+659222"))
    six = ("clinical", "functional", "cognitive", "situational", "preference", "family")

    # 1. Pa registers and opens his profile; State exists before any fact does.
    profile_id = open_own_profile(client, pa, "ms")
    first = read_state(client, pa, profile_id, "Pa reads his State before any fact")
    if first["sequence"] != 1 or first["trigger"] != {"kind": "first", "fact_id": None}:
        raise fail(
            "Pa reads his State before any fact", why=f"expected the first snapshot: {first}"
        )
    if tuple(first["dimensions"]) != six or any(first["dimensions"][d] is None for d in six):
        raise fail("Pa reads his State before any fact", why=f"expected six dimensions: {first}")
    if first["posture"] != "stable" or first["stale"] is not False:
        raise fail("Pa reads his State before any fact", why=f"expected stable, checked: {first}")
    ok(
        "Pa reads his State (GET /profiles/{id}/state): snapshot 1, trigger first, posture "
        "stable, all six dimensions computed and empty — clinical, functional, cognitive, "
        "situational, preference, family"
    )

    # 2. A blood-pressure reading: one event, one fact resting on it; State recomputes as it lands.
    posted = check(
        client.post(
            f"/profiles/{profile_id}/readings",
            headers=bearer(pa.token),
            json={"systolic": 138, "diastolic": 84},
        ),
        201,
        "Pa adds a blood-pressure reading",
    )
    if not posted.get("event_id") or not posted.get("fact_id"):
        raise fail("Pa adds a blood-pressure reading", why=f"no event and fact in {posted}")
    ok(
        "Pa added a blood-pressure reading, 138/84 (POST /profiles/{id}/readings): one event "
        "(a reading, taken now, in the app) and one fact, blood_pressure.reading, that names it"
    )
    second = read_state(client, pa, profile_id, "Pa reads his State after the reading")
    if second["sequence"] != 2 or second["supersedes_id"] != first["state_id"]:
        raise fail(
            "Pa reads his State after the reading",
            why=f"expected snapshot 2 superseding {first['state_id']}: {second}",
        )
    if second["trigger"] != {"kind": "new_fact", "fact_id": posted["fact_id"]}:
        raise fail(
            "Pa reads his State after the reading", why=f"trigger does not name the fact: {second}"
        )
    entry = second["dimensions"]["clinical"]["facts"].get("blood_pressure", {}).get("reading")
    if entry is None or entry["value"] != {"systolic": 138, "diastolic": 84}:
        raise fail("Pa reads his State after the reading", why=f"reading not folded in: {second}")
    if (
        entry["event_id"] != posted["event_id"]
        or entry["confidence_state"] != "confirmed_by_person"
    ):
        raise fail("Pa reads his State after the reading", why=f"provenance not carried: {entry}")
    if second["posture"] != "stable" or second["dimensions"]["clinical"]["posture"] != "stable":
        raise fail(
            "Pa reads his State after the reading", why=f"a number moved the posture: {second}"
        )
    ok(
        "State recomputed as the fact landed: snapshot 2 supersedes snapshot 1, and records "
        f"its trigger — new_fact, naming fact {posted['fact_id'][:8]}…"
    )
    ok(
        "the reading is in the clinical dimension with its provenance (the event it came "
        "from, confirmed by Pa); the posture stays stable — 138/84 is a number State holds, "
        "not a number State judges"
    )

    # 3. A second reading supersedes the second snapshot; nothing new leaves it be.
    again = check(
        client.post(
            f"/profiles/{profile_id}/readings",
            headers=bearer(pa.token),
            json={"systolic": 142, "diastolic": 88},
        ),
        201,
        "Pa adds a second reading",
    )
    third = read_state(client, pa, profile_id, "Pa reads his State after the second reading")
    if (
        third["sequence"] != 3
        or third["supersedes_id"] != second["state_id"]
        or third["trigger"] != {"kind": "new_fact", "fact_id": again["fact_id"]}
    ):
        raise fail(
            "Pa reads his State after the second reading",
            why=f"expected snapshot 3 superseding snapshot 2, triggered by the new fact: {third}",
        )
    ok(
        "Pa added a second reading, 142/88: snapshot 3 supersedes snapshot 2 and names the "
        "new fact; snapshots are rows that are never edited"
    )
    same = read_state(client, pa, profile_id, "Pa reads his State again with nothing new")
    if same["state_id"] != third["state_id"]:
        raise fail(
            "Pa reads his State again with nothing new", why=f"a new snapshot was written: {same}"
        )
    ok(
        "reading State again with nothing new returns the same snapshot: no recompute for the same facts"
    )

    # 4. A fact without provenance: the API has no door that could ask for one.
    if any(
        e["event_id"] is None and e["artifact_id"] is None
        for s in third["dimensions"]["clinical"]["facts"].values()
        for e in s.values()
    ):
        raise fail("every fact in State names where it came from", why=str(third))
    ok(
        "every fact in State names the event or artefact it came from; the readings route "
        "writes the event first and the fact names it, so no request can ask for a fact with "
        "no provenance — that refusal (NoProvenance, 400) is held at the service and proven in "
        "backend/tests/test_memory_acceptance.py"
    )

    # 5. Mei: a key without the record cannot read State; one with it reads it narrowed.
    register(client, mei, "en")
    check(
        client.post(
            f"/profiles/{profile_id}/consents/sharing",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "scopes": ["readings", "records"],
                "relationship": "daughter",
                "language": "en",
                "captured_via": "app",
            },
        ),
        201,
        "Pa agrees to let Mei see his readings and his record",
    )
    ok("Pa agreed to let Mei, his daughter, see his readings and his record (not his notes)")
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=bearer(pa.token),
            json={"holder_phone_e164": mei.phone_e164, "role": "caregiver", "scopes": ["readings"]},
        ),
        201,
        "Pa cuts Mei a key to the readings only",
    )
    narrow = client.get(f"/profiles/{profile_id}/state", headers=bearer(mei.token))
    body = refused(narrow, 403, "OutOfScope", "Mei reads State with a readings-only key")
    if body.get("scope") != "records" or "138" in narrow.text:
        raise fail("Mei reads State with a readings-only key", narrow, "expected scope records")
    ok(
        "Pa cut Mei a caregiver key to the readings only; with it State is refused: OutOfScope "
        "records (403) — a snapshot is the record folded, so it is read under the record's scope"
    )
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "role": "caregiver",
                "scopes": ["readings", "records"],
            },
        ),
        201,
        "Pa cuts Mei a key to the readings and the record",
    )
    hers = read_state(client, mei, profile_id, "Mei reads State with a key to the record")
    reading = hers["dimensions"]["clinical"]["facts"].get("blood_pressure", {}).get("reading")
    if reading is None or reading["value"] != {"systolic": 142, "diastolic": 88}:
        raise fail("Mei reads State with a key to the record", why=f"no reading: {hers}")
    if (
        hers["withheld"]
        != {
            "dimensions": ["family", "preference", "situational"],
            "scopes": ["family", "notes", "visits"],
        }
        or hers["stale"] is not None
    ):
        raise fail(
            "Mei reads State with a key to the record",
            why=f"expected family, preference and situational withheld, unchecked: {hers}",
        )
    ok(
        "Pa re-cut the key to readings and records; Mei reads State: the clinical dimension "
        "with the reading in it; situational, preference and family withheld by name (her key "
        "covers no visits, notes or family), and she is told it was not checked against the record"
    )
    notes = client.get(f"/profiles/{profile_id}/notes", headers=bearer(mei.token))
    refused(notes, 403, "OutOfScope", "Mei reads Pa's notes")
    ok("Mei reads Pa's notes: refused, OutOfScope notes (403)")

    # 6. The refused reach is on Pa's trail.
    trail = check(
        client.get(f"/profiles/{profile_id}/audit", headers=bearer(pa.token)),
        200,
        "Pa reads his audit trail",
    )
    by_mei = [
        row
        for row in trail
        if row["outcome"] == "refused" and row["actor_person_id"] == mei.person_id
    ]
    if not any(row["scope"] == "records" and row["target"] == "state_snapshot" for row in by_mei):
        raise fail(
            "Pa reads his audit trail", why="no refused records read of state_snapshot by Mei"
        )
    ok(f"Pa reads his audit trail ({len(trail)} lines); Mei's refused reaches are on it:")
    for row in by_mei:
        print(
            f"    {row['at'][:19]}  Mei  {row['action']} {row['scope']} "
            f"{row['target']}  refused {row['refused_because']}"
        )


def _for_someone(patient: Person, language: str) -> JSON:
    return {
        "patient_phone_e164": patient.phone_e164,
        "display_name": patient.name,
        "language": language,
        "consent": {"wording_version": HOLD_WORDING, "language": "en", "captured_via": "app"},
        "basis": "patient_asked",
        "relationship": "daughter",
    }


def checkpoint_4(client: httpx.Client) -> None:
    pa = Person("Pa", fresh_phone("+659333"))
    mei = Person("Mei", fresh_phone("+659444"))
    kit = Person("Kit", fresh_phone("+659555"))

    # 1. Mei registers and sets up a profile for Pa, by his number. She is its steward.
    register(client, mei, "en")
    opened = check(
        client.post(
            "/profiles/for-someone", headers=bearer(mei.token), json=_for_someone(pa, "ms")
        ),
        201,
        "Mei sets up a profile for Pa by his number",
    )
    profile_id: str = opened["profile_id"]
    if opened["standing"] != "steward" or opened["role"] != "chief":
        raise fail("Mei sets up a profile for Pa by his number", why=f"got {opened}")
    if "notes" in opened["scopes"] or not {"medicines", "family", "records"} <= set(
        opened["scopes"]
    ):
        raise fail("Mei sets up a profile for Pa by his number", why=f"scopes {opened['scopes']}")
    ok(
        f"Mei set up a profile for Pa ({pa.phone_e164}) on the basis that he asked: she is its "
        "steward, holding a chief key over everything but his private notes"
    )
    doors = check(
        client.get("/doors", headers=bearer(mei.token)), 200, "Mei asks which doors apply"
    )
    if [d["profile_id"] for d in doors["stewarding"]] != [profile_id] or doors["own"] is not None:
        raise fail("Mei asks which doors apply", why=f"got {doors}")
    ok("Mei's doors (GET /doors): no profile of her own, one she is stewarding — Pa's")

    # 2. Pa's son tries the same number: refused, in words that name nobody. So is Mei, again.
    register(client, kit, "en")
    second = client.post(
        "/profiles/for-someone",
        headers=bearer(kit.token),
        json={**_for_someone(pa, "ms"), "relationship": "son"},
    )
    refused(second, 409, "AlreadySetUp", "Kit sets up a profile for the same number")
    if profile_id in second.text or mei.person_id in second.text:
        raise fail("Kit sets up a profile for the same number", second, "the answer named someone")
    again = client.post(
        "/profiles/for-someone", headers=bearer(mei.token), json=_for_someone(pa, "ms")
    )
    refused(again, 409, "AlreadySetUp", "Mei sets up the same profile again")
    if again.text != second.text:
        raise fail("Mei sets up the same profile again", again, "not the same words as Kit got")
    ok(
        f"Kit ({kit.phone_e164}) tried the same number and was refused: AlreadySetUp (409), the "
        f"answer naming nobody — {second.text}; Mei trying again got the very same words"
    )

    # 3. What the steward can and cannot do while nobody owns the profile.
    medicines = check(
        client.get(f"/profiles/{profile_id}/medicines", headers=bearer(mei.token)),
        200,
        "Mei reads Pa's medicines as steward",
    )
    if medicines != []:
        raise fail("Mei reads Pa's medicines as steward", why=f"expected none yet, got {medicines}")
    posted = check(
        client.post(
            f"/profiles/{profile_id}/readings",
            headers=bearer(mei.token),
            json={"systolic": 138, "diastolic": 84},
        ),
        201,
        "Mei records a blood-pressure reading for Pa as steward",
    )
    if not posted.get("event_id") or not posted.get("fact_id"):
        raise fail("Mei records a blood-pressure reading for Pa as steward", why=f"got {posted}")
    notes = client.get(f"/profiles/{profile_id}/notes", headers=bearer(mei.token))
    refused(notes, 403, "OutOfScope", "Mei reads Pa's private notes as steward")
    held = check(
        client.get(f"/profiles/{profile_id}/stewardship", headers=bearer(mei.token)),
        200,
        "Mei reads the stewardship",
    )
    if held["basis"] != "patient_asked" or held["closed_at"] is not None:
        raise fail("Mei reads the stewardship", why=f"got {held}")
    steward_key_id: str = held["key_id"]
    trail = check(
        client.get(f"/profiles/{profile_id}/audit", headers=bearer(mei.token)),
        200,
        "Mei reads the trail as steward",
    )
    ok(
        "as steward Mei reads the medicines (none yet), records a blood-pressure reading for Pa, "
        "138/84 (one event, one fact resting on it, under the agreement she gave for him), reads "
        f"the stewardship (open, basis patient_asked) and the trail ({len(trail)} lines); the "
        "private notes refuse her: OutOfScope notes (403)"
    )

    # 4. Pa registers with that number and finds the profile waiting for him.
    register(client, pa, "ms")
    me = check(client.get("/me", headers=bearer(pa.token)), 200, "Pa asks who he is")
    if me["profile_id"] is not None:
        raise fail(
            "Pa asks who he is", why="a fresh number already owns a profile; run make reset-db"
        )
    beside = client.post(
        "/profiles/mine",
        headers=bearer(pa.token),
        json={
            "consent": {"wording_version": HOLD_WORDING, "language": "ms", "captured_via": "app"}
        },
    )
    refused(beside, 409, "WaitingToBeClaimed", "Pa opens a second profile beside the one waiting")
    ok(
        "Pa registered; opening his own profile beside the one waiting was refused: WaitingToBeClaimed (409)"
    )
    waiting = check(
        client.get("/profiles/mine/claimable", headers=bearer(pa.token)),
        200,
        "Pa asks what is waiting for him",
    )
    if len(waiting) != 1 or waiting[0]["profile_id"] != profile_id:
        raise fail("Pa asks what is waiting for him", why=f"got {waiting}")
    offer = waiting[0]
    if (
        offer["set_up_by"] != mei.name
        or "notes" in offer["parts"]
        or offer["words_language"] != "ms"
    ):
        raise fail("Pa asks what is waiting for him", why=f"got {offer}")
    ok(
        f"Pa sees the profile waiting for him (GET /profiles/mine/claimable): set up by {offer['set_up_by']}, "
        f"{offer['relationship']}, who would keep seeing {len(offer['parts'])} parts; the words he reads, in Malay:"
    )
    for line in offer["hold_words"].splitlines():
        print(f"    {line}")
    for line in offer["sharing_words"].splitlines():
        print(f"    {line}")

    # 5. Pa mints his OK for exactly that, and claims.
    minted = check(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=bearer(pa.token),
            json={"subject": "claim", "language": "ms"},
        ),
        201,
        "Pa says OK",
    )
    claimed = check(
        client.post(
            f"/profiles/{profile_id}/claim",
            headers=bearer(pa.token),
            json={"confirmation_id": minted["confirmation_id"], "language": "ms"},
        ),
        200,
        "Pa claims the profile",
    )
    if claimed["standing"] != "owner" or "notes" not in claimed["scopes"]:
        raise fail("Pa claims the profile", why=f"got {claimed}")
    ok(
        "Pa minted his OK (a confirmation for subject claim, good for ten minutes, used once) and claimed the profile: he is its owner"
    )
    spent = client.post(
        f"/profiles/{profile_id}/claim",
        headers=bearer(pa.token),
        json={"confirmation_id": minted["confirmation_id"], "language": "ms"},
    )
    refused(spent, 403, "NotTheClaimant", "Pa claims again")
    ok("claiming again is refused: NotTheClaimant (403); there is nothing left to claim")

    # 6. What the claim recorded: consents, keys, the closed stewardship, the trail.
    consents = check(
        client.get(f"/profiles/{profile_id}/consents", headers=bearer(pa.token)),
        200,
        "Pa reads his consents",
    )
    proxy = [c for c in consents if c["basis"] == "patient_asked"]
    own = [c for c in consents if c["purpose"] == "hold_health_record" and c["basis"] == "owner"]
    sharing = [c for c in consents if c["purpose"] == "share_with_family"]
    if not (
        len(proxy) == 1
        and proxy[0]["revoked_by_person_id"] == pa.person_id
        and len(own) == 1
        and own[0]["language"] == "ms"
        and len(sharing) == 1
        and sharing[0]["holder_person_id"] == mei.person_id
        and sharing[0]["basis"] == "owner"
    ):
        raise fail("Pa reads his consents", why=f"got {consents}")
    ok(
        "Pa reads his consents: Mei's agreement for him (patient_asked) withdrawn by him at the claim; "
        "his own agreement to Nura keeping his record, in Malay; and his agreement to let Mei, his "
        "daughter, see the parts she held — on his own basis"
    )
    keys = check(
        client.get(f"/profiles/{profile_id}/keys", headers=bearer(pa.token)),
        200,
        "Pa reads his keys",
    )
    old = [k for k in keys if k["key_id"] == steward_key_id]
    live = [k for k in keys if k["revoked_at"] is None]
    if not (
        len(old) == 1
        and old[0]["revoked_at"] is not None
        and old[0]["consent_id"] is None
        and len(live) == 1
        and live[0]["role"] == "chief"
        and live[0]["holder_person_id"] == mei.person_id
        and live[0]["consent_id"] == sharing[0]["consent_id"]
        and live[0]["granted_by_person_id"] == pa.person_id
    ):
        raise fail("Pa reads his keys", why=f"got {keys}")
    ok(
        "Pa reads his keys: the steward key is closed; Mei now holds a chief key, cut by Pa, resting on that consent"
    )
    closed = check(
        client.get(f"/profiles/{profile_id}/stewardship", headers=bearer(pa.token)),
        200,
        "Pa reads the stewardship",
    )
    if closed["closed_at"] is None or closed["claimed_by_person_id"] != pa.person_id:
        raise fail("Pa reads the stewardship", why=f"got {closed}")
    ok("the stewardship is closed, naming Pa as the person who claimed")
    trail = check(
        client.get(f"/profiles/{profile_id}/audit", headers=bearer(pa.token)),
        200,
        "Pa reads his trail",
    )
    steps = {
        (e["action"], e["scope"], e["target"])
        for e in trail
        if e["actor_person_id"] == pa.person_id and e["outcome"] == "allowed"
    }
    wanted = {
        ("write", "profile", "profile"),
        ("write", "family", "consent"),
        ("share", "family", "key"),
        ("write", "family", "key"),
        ("write", "family", "stewardship"),
    }
    if not wanted <= steps:
        raise fail("Pa reads his trail", why=f"missing {wanted - steps}")
    refusals = [e for e in trail if e["outcome"] == "refused"]
    if not any(
        e["refused_because"] == "AlreadySetUp" and e["actor_person_id"] == mei.person_id
        for e in refusals
    ):
        raise fail("Pa reads his trail", why="Mei's refused second setup is not on it")
    if any(e["actor_person_id"] == kit.person_id for e in trail):
        raise fail("Pa reads his trail", why="a stranger's try was written into the trail")
    ok(
        f"Pa reads his trail ({len(trail)} lines): the claim is on it in his name — the transfer, the consents, the key, the closed stewardship — and the refusals:"
    )
    for row in refusals:
        who = {mei.person_id: "Mei", pa.person_id: "Pa"}.get(row["actor_person_id"], "?")
        print(
            f"    {row['at'][:19]}  {who:>3}  {row['action']} {row['scope']} {row['target']}  "
            f"refused {row['refused_because']}"
        )
    ok(
        "Kit's try is not on the trail: a stranger's reach is counted out of band, never written in, so nobody can fill a trail by repeating a number"
    )

    # 7. Mei after the claim: a chief on Pa's consent, still not the notes.
    check(
        client.post(
            f"/profiles/{profile_id}/notes",
            headers=bearer(pa.token),
            json={"text": "I did not tell the children about the fall."},
        ),
        201,
        "Pa writes a private note",
    )
    seen = check(
        client.get(f"/profiles/{profile_id}", headers=bearer(mei.token)),
        200,
        "Mei opens Pa's profile",
    )
    if seen["standing"] != "holder" or seen["role"] != "chief":
        raise fail("Mei opens Pa's profile", why=f"got {seen}")
    check(
        client.get(f"/profiles/{profile_id}/medicines", headers=bearer(mei.token)),
        200,
        "Mei reads Pa's medicines",
    )
    notes = client.get(f"/profiles/{profile_id}/notes", headers=bearer(mei.token))
    body = refused(notes, 403, "OutOfScope", "Mei reads Pa's private notes")
    if body.get("scope") != "notes" or "fall" in notes.text:
        raise fail("Mei reads Pa's private notes", notes, "expected scope notes and no note text")
    doors = check(
        client.get("/doors", headers=bearer(mei.token)), 200, "Mei asks which doors apply now"
    )
    if doors["stewarding"] != [] or [d["role"] for d in doors["invited"]] != ["chief"]:
        raise fail("Mei asks which doors apply now", why=f"got {doors}")
    ok(
        "Mei opens Pa's profile as his chief on his consent, reads his medicines, and cannot read his private notes: OutOfScope notes (403); her doors now list Pa's profile as one she was let in to"
    )
    later = client.post(
        "/profiles/for-someone",
        headers=bearer(kit.token),
        json={**_for_someone(pa, "ms"), "relationship": "son"},
    )
    refused(later, 409, "AlreadySetUp", "Kit tries the number once more, after the claim")
    if later.text != second.text:
        raise fail(
            "Kit tries the number once more, after the claim", later, "not the same words as before"
        )
    ok(
        "Kit trying the number once more, now that Pa owns the profile, gets the same words as before: nothing says which case it is"
    )


def _photo(label: str) -> JSON:
    return {
        "data": base64.b64encode(placeholder_png(label)).decode(),
        "content_type": "image/png",
        "captured_at": "2026-09-14T08:00:00Z",
    }


def print_fields(card: JSON) -> None:
    """Every field of a review card: value, unit, confidence, and dotted where it needs the eye."""
    for field in card["fields"]:
        unit = f" {field['unit']}" if field["unit"] else ""
        mark = "dotted — needs your eye" if field["needs_confirm"] else "clear"
        value = field["value"]
        shown = value if not isinstance(value, dict) else value.get("instruction", value)
        print(
            f"    {field['attribute']:<20} {shown!s:<32}{unit:<8} "
            f"confidence {field['confidence']:.2f}  {mark}"
        )


def decide(
    card: JSON, *, correct: dict[str, Any] | None = None, reject: set[str] = frozenset()
) -> list[JSON]:
    """Confirm every field, except those corrected (to the value given) or rejected."""
    decisions: list[JSON] = []
    for field in card["fields"]:
        if correct and field["attribute"] in correct:
            decisions.append(
                {
                    "field_id": field["field_id"],
                    "decision": "corrected",
                    "corrected_value": correct[field["attribute"]],
                }
            )
        elif field["attribute"] in reject:
            decisions.append({"field_id": field["field_id"], "decision": "rejected"})
        else:
            decisions.append({"field_id": field["field_id"], "decision": "confirmed"})
    return decisions


def mint_and_confirm(
    client: httpx.Client,
    person: Person,
    profile_id: str,
    card: JSON,
    decisions: list[JSON],
    what: str,
) -> JSON:
    """The person's OK for exactly these decisions, then the confirm that spends it."""
    minted = check(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=bearer(person.token),
            json={"subject": "review_card", "card_id": card["card_id"], "decisions": decisions},
        ),
        201,
        f"{what}: {person.name} says OK",
    )
    if minted["subject"] != "review_card":
        raise fail(f"{what}: {person.name} says OK", why=f"minted {minted}")
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


def checkpoint_5(client: httpx.Client) -> None:
    pa = Person("Pa", fresh_phone("+659111"))
    mei = Person("Mei", fresh_phone("+659222"))

    # 1. Pa registers and opens his profile.
    profile_id = open_own_profile(client, pa, "ms")

    # 2. He uploads the lipid report: the bytes go to the store, a review card comes back.
    card = check(
        client.post(
            f"/profiles/{profile_id}/photos", headers=bearer(pa.token), json=_photo(LIPID_PANEL)
        ),
        201,
        "Pa uploads the lipid report",
    )
    if card["document_kind"] != "lab_report" or card["document_date"] != "2023-09-07":
        raise fail(
            "Pa uploads the lipid report", why=f"not read as the lab report of 7 Sep 2023: {card}"
        )
    if len(card["fields"]) != 7 or card["confirmed_at"] is not None:
        raise fail("Pa uploads the lipid report", why=f"expected seven open fields: {card}")
    dotted = {f["attribute"] for f in card["fields"] if f["needs_confirm"]}
    if dotted != {"ldl", "triglycerides"} or any(
        (f["confidence"] < CONFIDENCE_THRESHOLD) != f["needs_confirm"] for f in card["fields"]
    ):
        raise fail("Pa uploads the lipid report", why=f"dotted fields are {dotted}")
    ok(
        "Pa uploaded the lipid report (POST /profiles/{id}/photos, the redacted sample's placeholder "
        f"bytes): stored in the SG object store as artefact {card['artifact_id'][:8]}…, read as a "
        "lab_report dated 2023-09-07, and answered with a review card — seven fields, each with its "
        f"confidence; the two below {CONFIDENCE_THRESHOLD} are dotted:"
    )
    print_fields(card)
    empty = check(
        client.get(
            f"/profiles/{profile_id}/facts",
            headers=bearer(pa.token),
            params={"subject": "lipid_panel"},
        ),
        200,
        "Pa reads his lipid facts before confirming",
    )
    if empty != []:
        raise fail("Pa reads his lipid facts before confirming", why=f"facts before a yes: {empty}")
    ok("nothing is a fact yet: GET /profiles/{id}/facts?subject=lipid_panel is [] until he says so")

    # 3. He corrects the misread triglycerides, mints his OK for exactly that, and confirms.
    decisions = decide(card, correct={"triglycerides": 54})
    other = decide(card, correct={"triglycerides": 45})
    minted = check(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=bearer(pa.token),
            json={"subject": "review_card", "card_id": card["card_id"], "decisions": decisions},
        ),
        201,
        "Pa says OK to his decisions",
    )
    wrong = client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        headers=bearer(pa.token),
        json={"decisions": other, "confirmation_id": minted["confirmation_id"]},
    )
    refused(wrong, 400, "NotWhatWasConfirmed", "Pa confirms with decisions he did not OK")
    ok(
        "Pa corrected triglycerides from 64 to 54 (the paper says 54) and minted his OK; the same OK "
        "offered for a different correction (45) was refused: NotWhatWasConfirmed (400) — the yes "
        "binds to the decisions as shown"
    )
    confirmed = check(
        client.post(
            f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
            headers=bearer(pa.token),
            json={"decisions": decisions, "confirmation_id": minted["confirmation_id"]},
        ),
        200,
        "Pa confirms the lipid card",
    )
    facts = confirmed["facts"]
    states = {f["attribute"]: f["state"] for f in confirmed["card"]["fields"]}
    if (
        len(facts) != 7
        or states["triglycerides"] != "corrected"
        or confirmed["card"]["confirmed_by_person_id"] != pa.person_id
    ):
        raise fail("Pa confirms the lipid card", why=f"got {confirmed}")
    for fact in facts:
        if (
            fact["artifact_id"] != card["artifact_id"]
            or fact["confidence_state"] != "confirmed_by_person"
            or fact["confirmed_by_person_id"] != pa.person_id
            or not fact["valid_from"].startswith("2023-09-06T16:00:00")
        ):
            raise fail("Pa confirms the lipid card", why=f"a fact without its provenance: {fact}")
    ok(
        "one tap saved the card: seven facts, each naming the photo as provenance, confirmed_by_person "
        "Pa, with unit, valid from 7 September 2023 on his clock (2023-09-06T16:00Z):"
    )
    for fact in sorted(facts, key=lambda f: f["attribute"]):
        unit = f" {fact['unit']}" if fact["unit"] else ""
        print(
            f"    {fact['attribute']:<20} {fact['value']}{unit}  ← artefact {fact['artifact_id'][:8]}…  by Pa"
        )
    spent = client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        headers=bearer(pa.token),
        json={"decisions": decisions, "confirmation_id": minted["confirmation_id"]},
    )
    refused(spent, 409, "AlreadyConfirmed", "Pa confirms the same card again")
    ok("confirming the card again is refused: AlreadyConfirmed (409); its facts are facts now")

    # 4. The facts read back with provenance; State recomputed and names the trigger.
    held = check(
        client.get(
            f"/profiles/{profile_id}/facts",
            headers=bearer(pa.token),
            params={"subject": "lipid_panel"},
        ),
        200,
        "Pa reads his lipid facts",
    )
    if {f["fact_id"] for f in held} != {f["fact_id"] for f in facts}:
        raise fail("Pa reads his lipid facts", why=f"got {held}")
    state = read_state(client, pa, profile_id, "Pa reads his State after the card")
    if state["trigger"]["kind"] != "new_fact" or state["trigger"]["fact_id"] not in {
        f["fact_id"] for f in facts
    }:
        raise fail(
            "Pa reads his State after the card", why=f"trigger does not name a card fact: {state}"
        )
    folded = state["dimensions"]["clinical"]["facts"].get("lipid_panel", {})
    if (
        folded.get("triglycerides", {}).get("value") != 54
        or folded.get("ldl", {}).get("value") != 152
    ):
        raise fail("Pa reads his State after the card", why=f"lipids not folded in: {folded}")
    ok(
        f"the facts read back (GET /profiles/{{id}}/facts?subject=lipid_panel, 7); State recomputed as "
        f"each landed — snapshot {state['sequence']}, trigger new_fact naming fact "
        f"{state['trigger']['fact_id'][:8]}…; the clinical dimension holds the lipid panel with the "
        "corrected 54"
    )

    # 5. The medicine label: high-risk shown on the card; confirm writes medicine facts.
    label = check(
        client.post(
            f"/profiles/{profile_id}/photos", headers=bearer(pa.token), json=_photo(WARFARIN_LABEL)
        ),
        201,
        "Pa uploads the warfarin label",
    )
    if label["document_kind"] != "medicine_label" or label["high_risk_class"] != "anticoagulant":
        raise fail("Pa uploads the warfarin label", why=f"got {label}")
    ok(
        "Pa uploaded the warfarin label: read as a medicine_label dated 2024-03-12, the dose line "
        'parsed from Malay ("1 biji sekali sehari waktu malam"), and the card marked high_risk_class '
        "anticoagulant — looked up from the safety table, not proposed by the extractor and not his to reject:"
    )
    print_fields(label)
    outcome = mint_and_confirm(
        client, pa, profile_id, label, decide(label, reject={"prescriber"}), "the label"
    )
    written = {f["attribute"]: f for f in outcome["facts"]}
    if set(written) != {"name", "strength", "dose", "quantity", "dispensed_at"}:
        raise fail("the label: Pa confirms the card", why=f"facts {sorted(written)}")
    if (
        written["dose"]["value"].get("drug") != "Warfarin"
        or written["dose"]["artifact_id"] != label["artifact_id"]
    ):
        raise fail("the label: Pa confirms the card", why=f"dose fact {written['dose']}")
    ok(
        "Pa rejected the unclear prescriber and confirmed the rest: five medicine facts under the "
        "medicines scope, the dose naming its drug and resting on the label photo; the rejected field "
        "wrote nothing"
    )
    medicines = check(
        client.get(f"/profiles/{profile_id}/medicines", headers=bearer(pa.token)),
        200,
        "Pa reads his medicines",
    )
    if {m["attribute"] for m in medicines} != set(written):
        raise fail("Pa reads his medicines", why=f"got {medicines}")
    ok(
        "GET /profiles/{id}/medicines now lists the label's facts (subject medicine → scope medicines)"
    )
    ok(
        "the high-risk label rule (E16-04): a warfarin dose fact whose provenance is not a PHOTO artefact "
        "is refused, NotFromALabelPhoto (400), and written to the trail. No route can express it — the "
        "only way to write a medicine dose over HTTP is a card from a photo — so the refusal is held at "
        "the service (app/safety/high_risk.py, a hook on before_fact_write) and proven in "
        "backend/tests/test_high_risk.py from a WhatsApp message, a PDF and a screenshot"
    )

    # 6. Mei: with a key to the record she sees the cards; without it she is refused.
    register(client, mei, "en")
    check(
        client.post(
            f"/profiles/{profile_id}/consents/sharing",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "scopes": ["readings", "records"],
                "relationship": "daughter",
                "language": "en",
                "captured_via": "app",
            },
        ),
        201,
        "Pa agrees to let Mei see his readings and his record",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=bearer(pa.token),
            json={"holder_phone_e164": mei.phone_e164, "role": "caregiver", "scopes": ["readings"]},
        ),
        201,
        "Pa cuts Mei a key to the readings only",
    )
    narrow = client.get(f"/profiles/{profile_id}/review-cards", headers=bearer(mei.token))
    body = refused(narrow, 403, "OutOfScope", "Mei reads the review cards with a readings-only key")
    if body.get("scope") != "records" or "230" in narrow.text:
        raise fail(
            "Mei reads the review cards with a readings-only key", narrow, "expected scope records"
        )
    ok(
        "Pa cut Mei a caregiver key to the readings only; the review cards refuse her: OutOfScope records (403)"
    )
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "role": "caregiver",
                "scopes": ["readings", "records"],
            },
        ),
        201,
        "Pa cuts Mei a key to the readings and the record",
    )
    hers = check(
        client.get(f"/profiles/{profile_id}/review-cards", headers=bearer(mei.token)),
        200,
        "Mei reads the review cards with a key to the record",
    )
    if {c["card_id"] for c in hers} != {card["card_id"], label["card_id"]}:
        raise fail("Mei reads the review cards with a key to the record", why=f"got {hers}")
    if any(c["confirmed_at"] is None for c in hers):
        raise fail(
            "Mei reads the review cards with a key to the record", why="a card is still open"
        )
    ok(
        "Pa re-cut the key to readings and records; Mei reads both cards, each closed and naming Pa as its confirmer"
    )
    refused(
        client.get(
            f"/profiles/{profile_id}/facts",
            headers=bearer(mei.token),
            params={"subject": "medicine"},
        ),
        403,
        "OutOfScope",
        "Mei reads the medicine facts with a key to the record",
    )
    ok(
        "the label's facts are under the medicines scope: Mei's key to the record does not open them, OutOfScope medicines (403)"
    )

    # 7. The trail. Seven facts and their State recomputes make a long trail, so read it at
    # the widest page the route allows.
    trail = check(
        client.get(
            f"/profiles/{profile_id}/audit", headers=bearer(pa.token), params={"limit": 500}
        ),
        200,
        "Pa reads his audit trail",
    )
    steps = {(e["action"], e["scope"], e["target"]) for e in trail if e["outcome"] == "allowed"}
    wanted = {
        ("write", "records", "artifact"),
        ("write", "records", "review_card"),
        ("write", "records", "review_field"),
        ("write", "records", "fact"),
        ("write", "medicines", "fact"),
        ("write", "records", "confirmation"),
    }
    if not wanted <= steps:
        raise fail("Pa reads his audit trail", why=f"missing {wanted - steps}")
    refusals = [e for e in trail if e["outcome"] == "refused"]
    names = {e["refused_because"] for e in refusals}
    if not {"NotWhatWasConfirmed", "AlreadyConfirmed", "OutOfScope"} <= names:
        raise fail("Pa reads his audit trail", why=f"refusals on it: {names}")
    ok(
        f"Pa reads his audit trail ({len(trail)} lines): the photos, the cards, every field, every fact and "
        "every yes are on it as writes, and so are the refusals:"
    )
    for row in refusals:
        who = {mei.person_id: "Mei", pa.person_id: "Pa"}.get(row["actor_person_id"], "?")
        print(
            f"    {row['at'][:19]}  {who:>3}  {row['action']} {row['scope']} {row['target']}  "
            f"refused {row['refused_because']}"
        )


# --- checkpoint 7: the visit loop -----------------------------------------------------------


def transcript_of(label: str) -> str:
    found = json.loads((VISIT_FIXTURES / f"{label}.json").read_text())
    text: str = found["transcript"]
    return text


def verifier_clean(lines: list[str], language: str, what: str) -> None:
    """Every line through the plain-words verifier, as the owner would check by hand:
    `python3 -m app.safety.plain_words --text … --lang …`, run as a command, not imported."""
    for line in lines:
        ran = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.safety.plain_words",
                "--text",
                line,
                "--lang",
                language,
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            check=False,
        )
        try:
            report = json.loads(ran.stdout)
        except json.JSONDecodeError:
            raise Failed(
                f"✗ {what}: the verifier did not answer for {line!r}: {ran.stderr}"
            ) from None
        if report["failures"]:
            raise Failed(f"✗ {what}: the verifier fails {line!r}: {report['failures']}")


def mint(client: httpx.Client, person: Person, profile_id: str, body: JSON, what: str) -> str:
    minted = check(
        client.post(
            f"/profiles/{profile_id}/confirmations", headers=bearer(person.token), json=body
        ),
        201,
        f"{what}: {person.name} says OK",
    )
    confirmation_id: str = minted["confirmation_id"]
    return confirmation_id


def checkpoint_7(client: httpx.Client) -> None:
    pa = Person("Pa", fresh_phone("+659111"))
    mei = Person("Mei", fresh_phone("+659222"))
    language = "ms"

    # 1. Pa opens his profile in Malay, with a blood pressure reading and a medicine line.
    profile_id = open_own_profile(client, pa, language)
    taken = (datetime.now(UTC) - timedelta(days=20)).replace(microsecond=0)
    check(
        client.post(
            f"/profiles/{profile_id}/readings",
            headers=bearer(pa.token),
            json={
                "systolic": 138,
                "diastolic": 84,
                "taken_at": taken.isoformat().replace("+00:00", "Z"),
            },
        ),
        201,
        "Pa adds a blood pressure reading",
    )
    label = check(
        client.post(
            f"/profiles/{profile_id}/photos", headers=bearer(pa.token), json=_photo(WARFARIN_LABEL)
        ),
        201,
        "Pa uploads the warfarin label",
    )
    outcome = mint_and_confirm(
        client, pa, profile_id, label, decide(label, reject={"prescriber"}), "the label"
    )
    if {f["attribute"] for f in outcome["facts"]} != {
        "name",
        "strength",
        "dose",
        "quantity",
        "dispensed_at",
    }:
        raise fail("the label: Pa confirms the card", why=f"facts {outcome['facts']}")
    ok(
        "Pa opened his profile in Malay, added a blood pressure reading (138/84, taken twenty days "
        "ago) and a medicine line: the warfarin label through the review card (E02), five medicine "
        "facts, no purpose recorded"
    )

    # 2. He books a visit with Dr Tan, three days from now at 10 in the morning.
    doctor = check(
        client.post(
            f"/profiles/{profile_id}/providers",
            headers=bearer(pa.token),
            json={"name": "Dr Tan", "kind": "doctor"},
        ),
        201,
        "Pa adds Dr Tan to his directory",
    )
    when = (datetime.now(UTC) + timedelta(days=3)).replace(
        hour=2, minute=0, second=0, microsecond=0
    )
    booking = {
        "provider_id": doctor["provider_id"],
        "scheduled_at": when.isoformat().replace("+00:00", "Z"),
        "purpose": "tekanan darah",
    }
    yes = mint(client, pa, profile_id, {"subject": "appointment", **booking}, "the booking")
    visit = check(
        client.post(
            f"/profiles/{profile_id}/appointments",
            headers=bearer(pa.token),
            json={**booking, "confirmation_id": yes},
        ),
        201,
        "Pa writes down the visit",
    )
    if visit["status"] != "planned" or visit["confirmed_by_person_id"] != pa.person_id:
        raise fail("Pa writes down the visit", why=f"got {visit}")
    appointment_id = visit["appointment_id"]
    ok(
        f"Pa booked a visit with Dr Tan (POST /profiles/{{id}}/appointments) for {when.date()} at 10 in "
        "the morning, on a yes minted for exactly that booking (subject appointment): status planned"
    )

    # 3. The pre-visit brief, in Malay; every line through the verifier.
    brief = check(
        client.get(
            f"/profiles/{profile_id}/appointments/{appointment_id}/brief", headers=bearer(pa.token)
        ),
        200,
        "Pa reads the pre-visit brief",
    )
    lines = [line["text"] for line in brief["lines"]]
    sections = {line["section"] for line in brief["lines"]}
    if brief["language"] != language or not brief["state_id"]:
        raise fail("Pa reads the pre-visit brief", why=f"got {brief}")
    if not {"purpose", "changed", "questions", "bring"} <= sections:
        raise fail("Pa reads the pre-visit brief", why=f"sections {sections}")
    verifier_clean(lines, language, "Pa reads the pre-visit brief")
    ok(
        f"the pre-visit brief (GET …/brief), in Malay, rendered from State snapshot "
        f"{brief['state_id'][:8]}…: purpose, what changed, the open questions, what to bring — "
        f"{len(lines)} lines, every one passed the plain-words verifier (checked here again, one by "
        "one, with `python3 -m app.safety.plain_words --text … --lang ms`):"
    )
    for line in brief["lines"]:
        print(f"    [{line['section']:<9}] {line['text']}")

    # 4. Pa adds a question of his own, with a yes for exactly those words; then the card:
    # three lines for him, and the line that says he need not remember.
    own = "Adakah pil air ini buruk untuk buah pinggang saya?"
    yes = mint(
        client,
        pa,
        profile_id,
        {"subject": "question", "appointment_id": appointment_id, "text": own},
        "his own question",
    )
    added = check(
        client.post(
            f"/profiles/{profile_id}/appointments/{appointment_id}/questions",
            headers=bearer(pa.token),
            json={"text": own, "confirmation_id": yes},
        ),
        201,
        "Pa adds his own question",
    )
    if added["source"] != "person" or added["added_by_person_id"] != pa.person_id:
        raise fail("Pa adds his own question", why=f"got {added}")
    asked = check(
        client.get(
            f"/profiles/{profile_id}/appointments/{appointment_id}/questions",
            headers=bearer(pa.token),
        ),
        200,
        "Pa reads the questions",
    )
    card = asked["card"]
    sources = {q["source"] for q in asked["questions"]}
    if len(card) != 4 or len(asked["questions"]) < 3 or sources != {"gap", "person"}:
        raise fail("Pa reads the questions", why=f"got {asked}")
    verifier_clean(card, language, "Pa reads the questions")
    ok(
        f"the questions (GET …/questions): {len(asked['questions'])} for the caregiver, each naming its "
        "source — Pa's own (with his yes, subject question), a medicine line with no purpose, a "
        "reading with nothing recent (the gaps, with the facts each rests on); one card for Pa, one "
        "screen — the first three by priority and one reassurance — every line verifier-clean:"
    )
    for line in card:
        print(f"    {line}")
    for question in asked["questions"]:
        print(
            f"      from {question['source']} {question['source_kind'] or ''}: "
            f"{len(question['source_ids'])} id(s) — {question['text']}"
        )

    # 5. A fragment typed as a question is refused by the verifier, over HTTP, live. In Malay
    # the verifier checks the shape of a sentence — a capital, a full stop — so the fragment
    # is one with neither; the English rule about a sentence with nobody doing anything in
    # it ("Only the part for you.") is proven in backend/tests/test_visits.py.
    fragment = "hanya bahagian untuk anda"
    yes = mint(
        client,
        pa,
        profile_id,
        {"subject": "question", "appointment_id": appointment_id, "text": fragment},
        "the fragment",
    )
    refused(
        client.post(
            f"/profiles/{profile_id}/appointments/{appointment_id}/questions",
            headers=bearer(pa.token),
            json={"text": fragment, "confirmation_id": yes},
        ),
        400,
        "NotPlainEnough",
        "Pa adds a fragment as a question",
    )
    ok(
        f'a fragment offered as a question ("{fragment}": no capital, no full stop, docs/plain-words.md '
        "rule 1) is refused by the verifier: NotPlainEnough (400), nothing written, the refusal on the "
        'trail. The English fragment ("Only the part for you.") and a memo from a deliberately bad '
        "template are refused the same way in backend/tests/test_visits.py "
        "(test_a_fragment_typed_by_a_person_is_refused_by_the_verifier, "
        "test_a_memo_from_a_template_that_is_not_plain_is_refused)"
    )

    # 6. The routine transcript in: the summary card, the dose change as a question.
    summary = check(
        client.post(
            f"/profiles/{profile_id}/appointments/{appointment_id}/transcript",
            headers=bearer(pa.token),
            json={
                "data": base64.b64encode(transcript_of(ROUTINE_VISIT).encode()).decode(),
                "captured_at": booking["scheduled_at"],
            },
        ),
        201,
        "Pa uploads the routine transcript",
    )
    kinds = {item["kind"] for item in summary["items"]}
    if summary["red_flag"] or kinds != {"action", "medication_change", "follow_up", "fact_heard"}:
        raise fail("Pa uploads the routine transcript", why=f"got {summary}")
    if "Tanya Dr Tan tentang jumlah baru pil air." not in summary["lines"]:
        raise fail(
            "Pa uploads the routine transcript",
            why=f"no question for the change: {summary['lines']}",
        )
    if any(
        word in " ".join(summary["lines"]).lower() for word in ("penuh", "full", "half", "separuh")
    ):
        raise fail("Pa uploads the routine transcript", why="the card carries an amount")
    verifier_clean(summary["lines"], language, "Pa uploads the routine transcript")
    ok(
        f"Pa uploaded the routine transcript (POST …/transcript): stored as artefact "
        f"{summary['artifact_id'][:8]}… in the SG object store, read by the fixture summariser, and "
        f"answered with the summary card — {len(summary['items'])} items, each with its span in the "
        "transcript and its confidence; the dose change is a question for the doctor, never an "
        'amount ("Tanya Dr Tan tentang jumlah baru pil air." — in English, "Ask Dr Tan about the new '
        'amount of the water pill."); nothing is a memo, a booking or a fact yet:'
    )
    for line in summary["lines"]:
        print(f"    {line}")

    # 7. He confirms: memos, a planned follow-up, facts with the transcript as provenance.
    decisions = [{"item_id": item["item_id"], "decision": "confirmed"} for item in summary["items"]]
    yes = mint(
        client,
        pa,
        profile_id,
        {"subject": "visit_summary", "summary_id": summary["summary_id"], "decisions": decisions},
        "the summary",
    )
    confirmed = check(
        client.post(
            f"/profiles/{profile_id}/appointments/{appointment_id}/summary/{summary['summary_id']}/confirm",
            headers=bearer(pa.token),
            json={"decisions": decisions, "confirmation_id": yes},
        ),
        200,
        "Pa confirms the summary",
    )
    planned = confirmed["appointments"]
    heard = confirmed["facts"]
    if (
        len(planned) != 1
        or planned[0]["status"] != "planned"
        or not heard
        or any(f["artifact_id"] != summary["artifact_id"] for f in heard)
        or not confirmed["memos"]
        or len(confirmed["flag_ids"]) != 1
    ):
        raise fail("Pa confirms the summary", why=f"got {confirmed}")
    medicines = check(
        client.get(f"/profiles/{profile_id}/medicines", headers=bearer(pa.token)),
        200,
        "Pa reads his medicines after the summary",
    )
    if any(m["artifact_id"] == summary["artifact_id"] for m in medicines):
        raise fail(
            "Pa reads his medicines after the summary", why="a medicine fact from a transcript"
        )
    upcoming = check(
        client.get(f"/profiles/{profile_id}/appointments", headers=bearer(pa.token)),
        200,
        "Pa reads his visits",
    )
    if planned[0]["appointment_id"] not in {a["appointment_id"] for a in upcoming}:
        raise fail("Pa reads his visits", why=f"the follow-up is not among {upcoming}")
    ok(
        f"one OK saved the card: {len(confirmed['memos'])} memos filed against the next visit; the "
        f"follow-up appears as a planned visit with Dr Tan on {planned[0]['scheduled_at'][:10]} "
        "(GET …/appointments), needing its own confirm to be confirmed; the fact heard "
        f"({heard[0]['subject']}.{heard[0]['attribute']}) carries the transcript artefact "
        f"{heard[0]['artifact_id'][:8]}… as provenance, confirmed by Pa; the dose change became a flag "
        "for the medicines reconcile (ask the doctor) and no medicine fact — his medicines are as they were"
    )

    # 8. The memo card.
    memos = check(
        client.get(f"/profiles/{profile_id}/memos", headers=bearer(pa.token)),
        200,
        "Pa reads his memo card",
    )
    if not memos["card"] or set(memos["card"]) != {m["text"] for m in confirmed["memos"]}:
        raise fail("Pa reads his memo card", why=f"got {memos}")
    verifier_clean(memos["card"], language, "Pa reads his memo card")
    ok(
        "the memo card (GET /profiles/{id}/memos): the current memos, one line each, in his words, verified:"
    )
    for line in memos["card"]:
        print(f"    {line}")

    # 9. The red-flag transcript: the card carries the flag and the same-day line first.
    red = check(
        client.post(
            f"/profiles/{profile_id}/appointments/{appointment_id}/transcript",
            headers=bearer(pa.token),
            json={
                "data": base64.b64encode(transcript_of(RED_FLAG_VISIT).encode()).decode(),
                "captured_at": booking["scheduled_at"],
            },
        ),
        201,
        "Pa uploads the red-flag transcript",
    )
    if not red["red_flag"] or red["lines"][0] != "Telefon Dr Tan hari ini.":
        raise fail("Pa uploads the red-flag transcript", why=f"got {red}")
    verifier_clean(red["lines"], language, "Pa uploads the red-flag transcript")
    trail = check(
        client.get(
            f"/profiles/{profile_id}/audit",
            headers=bearer(pa.token),
            params={"scope": "records", "limit": 500},
        ),
        200,
        "Pa reads his trail for the flag",
    )
    if ("write", "flag") not in {
        (e["action"], e["target"]) for e in trail if e["outcome"] == "allowed"
    }:
        raise fail("Pa reads his trail for the flag", why="no flag written")
    ok(
        'the red-flag transcript ("chest pain", app/safety/red_flags.py): a Flag row was written before '
        "the card was composed (on the trail as a write of flag), the card carries red_flag=true and its "
        f'first line is "{red["lines"][0]}" (the English template: "Call Dr Tan today.") — a person and a '
        "day, never a diagnosis:"
    )
    for line in red["lines"]:
        print(f"    {line}")

    # 10. Mei with a key to the readings only cannot read the brief or the memos.
    register(client, mei, "en")
    check(
        client.post(
            f"/profiles/{profile_id}/consents/sharing",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "scopes": ["readings", "records"],
                "relationship": "daughter",
                "language": "en",
                "captured_via": "app",
            },
        ),
        201,
        "Pa agrees to let Mei see his readings and his record",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "role": "caregiver",
                "scopes": ["readings", "records"],
            },
        ),
        201,
        "Pa cuts Mei a key to the readings and the record",
    )
    body = refused(
        client.get(
            f"/profiles/{profile_id}/appointments/{appointment_id}/brief", headers=bearer(mei.token)
        ),
        403,
        "OutOfScope",
        "Mei reads the brief without the visits",
    )
    if body.get("scope") != "visits":
        raise fail(
            "Mei reads the brief without the visits", why=f"expected scope visits, got {body}"
        )
    refused(
        client.get(f"/profiles/{profile_id}/memos", headers=bearer(mei.token)),
        403,
        "OutOfScope",
        "Mei reads the memos without the visits",
    )
    trail = check(
        client.get(
            f"/profiles/{profile_id}/audit", headers=bearer(pa.token), params={"limit": 500}
        ),
        200,
        "Pa reads his audit trail",
    )
    refusals = [e for e in trail if e["outcome"] == "refused"]
    names = {e["refused_because"] for e in refusals}
    if not {"NotPlainEnough", "OutOfScope"} <= names:
        raise fail("Pa reads his audit trail", why=f"refusals on it: {names}")
    ok(
        "Pa cut Mei a caregiver key to the readings and the record; the brief and the memos refuse her: "
        "OutOfScope visits (403) — briefs, questions, summaries and memos are the visits'"
    )
    ok(f"Pa reads his audit trail ({len(trail)} lines); the refusals are on it:")
    for row in refusals:
        who = {mei.person_id: "Mei", pa.person_id: "Pa"}.get(row["actor_person_id"], "?")
        print(
            f"    {row['at'][:19]}  {who:>3}  {row['action']} {row['scope']} {row['target']}  "
            f"refused {row['refused_because']}"
        )


CHECKPOINTS = {
    2: checkpoint_2,
    3: checkpoint_3,
    4: checkpoint_4,
    5: checkpoint_5,
    7: checkpoint_7,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].isdigit() or int(argv[1]) not in CHECKPOINTS:
        ready = ", ".join(str(n) for n in sorted(CHECKPOINTS))
        print(f"usage: python -m scripts.checkpoint <n>   (ready: {ready})", file=sys.stderr)
        return 2
    number = int(argv[1])
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            try:
                health = client.get("/health")
            except httpx.ConnectError:
                raise Failed(
                    f"✗ nothing is listening at {BASE_URL}: run `make dev` in another terminal "
                    "and wait for it to say it is serving (set NURA_BASE_URL for another address)"
                ) from None
            check(health, 200, f"the server answers at {BASE_URL}")
            ok(f"the dev server answers at {BASE_URL} (GET /health)")
            if not DEV_LOG.exists():
                raise Failed(
                    f"✗ {LOG_NAME} is missing, so login codes cannot be read: the server answering "
                    "is not the one `make dev` starts. Stop it and run `make dev` there instead"
                )
            CHECKPOINTS[number](client)
    except Failed as failed:
        print(str(failed), flush=True)
        print(f"checkpoint {number} stopped at the first ✗", flush=True)
        return 1
    print(f"checkpoint {number} passed: every step did what docs/checkpoints.md says", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
