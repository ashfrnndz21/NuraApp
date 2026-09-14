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
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from scripts import checkpoints

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
        client.get(
            f"/profiles/{profile_id}/facts",
            headers=bearer(pa.token),
            params={"subject": "medicine"},
        ),
        200,
        "Pa reads his medicine facts",
    )
    if {m["attribute"] for m in medicines} != set(written):
        raise fail("Pa reads his medicine facts", why=f"got {medicines}")
    ok(
        "GET /profiles/{id}/facts?subject=medicine now lists the label's facts (subject medicine → "
        "scope medicines); the reconciled list at GET /profiles/{id}/medicines is checkpoint 6"
    )
    ok(
        "the high-risk label rule (E16-04): a warfarin dose fact whose provenance is not a PHOTO artefact "
        "is refused, HighRiskNeedsLabelPhoto (400), and written to the trail. No route can express it — the "
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


# --- checkpoint 6: medicines ----------------------------------------------------------------

NO_SUCH_YES = "00000000-0000-0000-0000-000000000001"


def label_photo(client: httpx.Client, person: Person, profile_id: str, what: str) -> str:
    """A label photo through E02's photo route: bytes the extractor does not know, so the card
    is `unknown` with no fields, and the artefact — a PHOTO — is what the label names."""
    made = check(
        client.post(
            f"/profiles/{profile_id}/photos",
            headers=bearer(person.token),
            json={
                "data": base64.b64encode(
                    placeholder_png(f"label-{random.randint(0, 10**9)}")
                ).decode(),
                "content_type": "image/png",
                "captured_at": "2026-09-14T08:00:00Z",
            },
        ),
        201,
        what,
    )
    if made["document_kind"] != "unknown" or made["fields"]:
        raise fail(what, why=f"the extractor guessed at unknown bytes: {made}")
    artifact_id: str = made["artifact_id"]
    return artifact_id


def medicine_label(generic: str, strength: str, dose_text: str, quantity: int) -> JSON:
    return {
        "generic": generic,
        "strength": strength,
        "dose_text": dose_text,
        "quantity": quantity,
        "prescriber": "Dr Tan",
        "source_kind": "retail",
    }


def say_yes(
    client: httpx.Client, person: Person, profile_id: str, label: JSON, artifact_id: str, what: str
) -> str:
    minted = check(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=bearer(person.token),
            json={"subject": "medicine", "label": label, "source_artifact_id": artifact_id},
        ),
        201,
        what,
    )
    confirmation_id: str = minted["confirmation_id"]
    return confirmation_id


def add_medicine(
    client: httpx.Client, person: Person, profile_id: str, label: JSON, artifact_id: str, what: str
) -> httpx.Response:
    """Say yes to what the label means, then write it. The write's response, unchecked."""
    yes = say_yes(client, person, profile_id, label, artifact_id, f"{what}: his OK")
    return client.post(
        f"/profiles/{profile_id}/medicines",
        headers=bearer(person.token),
        json={"label": label, "source_artifact_id": artifact_id, "confirmation_id": yes},
    )


def medicines_of(
    client: httpx.Client, person: Person, profile_id: str, what: str
) -> dict[str, JSON]:
    rows = check(
        client.get(f"/profiles/{profile_id}/medicines?language=en", headers=bearer(person.token)),
        200,
        what,
    )
    return {row["generic"]: row for row in rows}


def checkpoint_6(client: httpx.Client) -> None:
    pa = Person("Pa", fresh_phone("+659111"))
    mei = Person("Mei", fresh_phone("+659222"))

    # 1. Pa opens his profile, in Malay, and has no medicines yet.
    profile_id = open_own_profile(client, pa, "ms")
    if medicines_of(client, pa, profile_id, "Pa reads his medicines") != {}:
        raise fail("Pa reads his medicines", why="a fresh profile already has medicines")
    ok("Pa reads his medicines (GET /profiles/{id}/medicines): none yet ([])")

    # 2. A label photo, then what the label would mean: a new line, identified in the register.
    photo = label_photo(client, pa, profile_id, "Pa keeps the label photo")
    amlodipine = medicine_label("amlodipine", "5 mg", "1 biji sekali sehari pagi", 30)
    shown = check(
        client.post(
            f"/profiles/{profile_id}/medicines/draft",
            headers=bearer(pa.token),
            json={"label": amlodipine, "source_artifact_id": photo},
        ),
        200,
        "Pa asks what the amlodipine label means",
    )
    match = shown["match"]
    if shown["outcome"] != "new_line" or match["generic"] != "amlodipine" or match["high_risk"]:
        raise fail("Pa asks what the amlodipine label means", why=f"got {shown}")
    ok(
        "Pa kept a label photo (POST /profiles/{id}/photos: stored in the region's object store, "
        "an artefact of kind photo; the extractor read nothing off it, so no card to confirm) and asked "
        "what the label means (POST /profiles/{id}/medicines/draft): a new line — the fixture "
        f"register identified {match['brand']} {match['strength']} as {match['generic']} "
        f"({match['registration_no']}), the dose read from the label's Malay words, "
        "1 biji sekali sehari pagi; nothing written yet"
    )

    # 3. His OK, then the write.
    added = check(
        add_medicine(client, pa, profile_id, amlodipine, photo, "Pa adds amlodipine"),
        201,
        "Pa adds amlodipine",
    )
    if added["outcome"] != "new_line" or added["supply"]["quantity"] != 30 or added["flags"]:
        raise fail("Pa adds amlodipine", why=f"got {added}")
    amlodipine_id: str = added["line_id"]
    ok(
        "Pa said OK (POST /profiles/{id}/confirmations, subject medicine: a yes for exactly this "
        "label, good for ten minutes, used once) and added it (POST /profiles/{id}/medicines): "
        "one medication fact on the photo, confirmed by him, one line, one supply of 30"
    )

    # 4. The story, in Malay.
    story = check(
        client.get(
            f"/profiles/{profile_id}/medicines/{amlodipine_id}/story", headers=bearer(pa.token)
        ),
        200,
        "Pa hears the story of his blood pressure tablet",
    )
    if story["language"] != "ms" or "amlodipine" in " ".join(story["lines"]):
        raise fail("Pa hears the story of his blood pressure tablet", why=f"got {story}")
    ok(
        "Pa reads the story in Malay (GET .../story; his profile's language): purpose, how to "
        "take, what to look out for, what to avoid, if he forgot, and the boundary — from "
        "templates keyed by the licensed monograph, no model, the chemical name kept small:"
    )
    for line in story["lines"]:
        print(f"    {line}")

    # 5. Two taps; the count and the reorder date.
    for anchor in ("breakfast", None):
        check(
            client.post(
                f"/profiles/{profile_id}/medicines/{amlodipine_id}/taken",
                headers=bearer(pa.token),
                json={} if anchor is None else {"anchor": anchor},
            ),
            201,
            "Pa taps Taken",
        )
    row = medicines_of(client, pa, profile_id, "Pa reads the count")["amlodipine"]
    count = row["count"]
    if count["remaining"] != 28 or count["days_left"] != 28 or count["basis"] != "taps":
        raise fail("Pa reads the count", why=f"got {count}")
    ok(
        "Pa tapped Taken twice (POST .../taken: his own tap, no confirm, a DOSE_TAKEN event "
        f"each): {int(count['dispensed'])} dispensed − {int(count['taken'])} taken = "
        f"{int(count['remaining'])} left, about {count['days_left']} days; reorder on "
        f"{count['reorder_date']} (days left − 3 days lead time for a retail pharmacy); in his words:"
    )
    for line in count["lines"]:
        print(f"    {line}")

    # 6. Warfarin: high-risk, so only a label photo will do. Over HTTP every artefact is a
    # photo (POST /photos takes nothing else), so the refusal is held at the service.
    label_photo_id = label_photo(client, pa, profile_id, "Pa photographs the warfarin label")
    warfarin = medicine_label("warfarin", "3 mg", "1 tab ON", 28)
    shown = check(
        client.post(
            f"/profiles/{profile_id}/medicines/draft",
            headers=bearer(pa.token),
            json={"label": warfarin, "source_artifact_id": label_photo_id},
        ),
        200,
        "Pa asks what the warfarin label means",
    )
    if not shown["match"]["high_risk"] or shown["needs_label_photo"]:
        raise fail("Pa asks what the warfarin label means", why=f"got {shown}")
    saved = check(
        add_medicine(client, pa, profile_id, warfarin, label_photo_id, "Pa adds warfarin"),
        201,
        "Pa adds warfarin from the label",
    )
    if not saved["high_risk"] or saved["generic"] != "warfarin":
        raise fail("Pa adds warfarin from the label", why=f"got {saved}")
    warfarin_id: str = saved["line_id"]
    ok(
        "warfarin: the register marks its class, anticoagulant, high-risk; from the label photo it "
        "was added (201), marked high_risk. Without a label photo it is refused by class — "
        "HighRiskNeedsLabelPhoto (400, the body names the class) — at the medicines service and "
        "again as the hook on the memory store; no route can offer a voice note or a PDF as a "
        "medicine's source (POST /photos takes only photos), so that refusal is proven in "
        "backend/tests/test_medicines.py and test_medicines_api.py from a voice note and a PDF"
    )

    # 7. Aspirin: screened before it is saved; the flag is a question for the doctor.
    aspirin = medicine_label("aspirin", "100 mg", "1 tab OD", 30)
    aspirin_photo = label_photo(client, pa, profile_id, "Pa photographs the aspirin box")
    shown = check(
        client.post(
            f"/profiles/{profile_id}/medicines/draft",
            headers=bearer(pa.token),
            json={"label": aspirin, "source_artifact_id": aspirin_photo},
        ),
        200,
        "Pa asks what the aspirin label means",
    )
    flagged = shown["flagged"]
    if (
        len(flagged) != 1
        or flagged[0]["other_generic"] != "warfarin"
        or flagged[0]["severity"] != "major"
    ):
        raise fail("Pa asks what the aspirin label means", why=f"expected a major flag: {shown}")
    added = check(
        add_medicine(client, pa, profile_id, aspirin, aspirin_photo, "Pa adds aspirin"),
        201,
        "Pa adds aspirin",
    )
    if len(added["flags"]) != 1 or added["flags"][0]["text_id"] != "bleeding_risk":
        raise fail("Pa adds aspirin", why=f"got {added}")
    questions = check(
        client.get(
            f"/profiles/{profile_id}/medicines/interactions?language=en", headers=bearer(pa.token)
        ),
        200,
        "Pa reads the interaction questions",
    )
    if len(questions) != 1 or questions[0]["other_generic"] != "warfarin":
        raise fail("Pa reads the interaction questions", why=f"got {questions}")
    ok(
        "aspirin was screened before it was saved: the licensed data flagged aspirin with "
        "warfarin, major (bleeding_risk), shown on the draft and written as a flag with the "
        "line; GET .../medicines/interactions renders it as a question for the doctor, "
        "both medicines named in his words:"
    )
    for line in questions[0]["question"]:
        print(f"    {line}")

    # 8. A dose change: 10 mg on the new pack. Nothing moves without his OK.
    new_pack = label_photo(client, pa, profile_id, "Pa photographs the new pack")
    ten = medicine_label("amlodipine", "10 mg", "1 biji sekali sehari pagi", 30)
    shown = check(
        client.post(
            f"/profiles/{profile_id}/medicines/draft",
            headers=bearer(pa.token),
            json={"label": ten, "source_artifact_id": new_pack},
        ),
        200,
        "Pa asks what the new amlodipine pack means",
    )
    if shown["outcome"] != "dose_change" or shown["matched_line_id"] != amlodipine_id:
        raise fail("Pa asks what the new amlodipine pack means", why=f"got {shown}")
    no_yes = client.post(
        f"/profiles/{profile_id}/medicines",
        headers=bearer(pa.token),
        json={"label": ten, "source_artifact_id": new_pack, "confirmation_id": NO_SUCH_YES},
    )
    refused(no_yes, 400, "NotAConfirmerHere", "the dose change without Pa's OK")
    still = medicines_of(client, pa, profile_id, "Pa reads his medicines")["amlodipine"]
    if still["strength"] != "5 mg" or still["line_id"] != amlodipine_id:
        raise fail("the dose change without Pa's OK", why=f"the line moved: {still}")
    ok(
        "the new pack says 10 mg: the draft classifies it as a dose_change on the 5 mg line; "
        "written without his OK it is refused, NotAConfirmerHere (400), and the 5 mg line "
        "stays current"
    )
    changed = check(
        add_medicine(client, pa, profile_id, ten, new_pack, "Pa says OK to the new pack"),
        201,
        "Pa says OK to the new pack",
    )
    if changed["outcome"] != "dose_change" or changed["supersedes_id"] != amlodipine_id:
        raise fail("Pa says OK to the new pack", why=f"got {changed}")
    now = medicines_of(client, pa, profile_id, "Pa reads his medicines after the change")[
        "amlodipine"
    ]
    story = check(
        client.get(
            f"/profiles/{profile_id}/medicines/{now['line_id']}/story?language=en",
            headers=bearer(pa.token),
        ),
        200,
        "Pa reads the story after the change",
    )
    if now["strength"] != "10 mg" or now["change_kind"] != "dose_change":
        raise fail("Pa reads his medicines after the change", why=f"got {now}")
    if not now["doctor_question"] or any(line.startswith("Take ") for line in story["lines"]):
        raise fail("Pa reads the story after the change", why=f"got {story}")
    log = check(
        client.get(f"/profiles/{profile_id}/medicines/history", headers=bearer(pa.token)),
        200,
        "Pa reads the change log",
    )
    old = [row for row in log if row["line_id"] == amlodipine_id]
    if len(old) != 1 or old[0]["superseded_at"] is None:
        raise fail("Pa reads the change log", why=f"the 5 mg line is not kept as superseded: {log}")
    ok(
        "with his OK the 10 mg line supersedes the 5 mg line (kept, marked with when, in "
        "GET .../medicines/history); the story does not tell him an amount — it asks the doctor:"
    )
    for line in now["doctor_question"]:
        print(f"    {line}")

    # 9. Today's cards.
    cards = check(
        client.get(f"/profiles/{profile_id}/medicines/today?language=en", headers=bearer(pa.token)),
        200,
        "Pa reads today's doses",
    )
    if [(c["generic"], c["anchor"]) for c in cards] != [
        ("amlodipine", "breakfast"),
        ("aspirin", "breakfast"),
        ("warfarin", "bed"),
    ]:
        raise fail("Pa reads today's doses", why=f"got {cards}")
    ok("Pa reads today's doses (GET .../medicines/today): one card per medicine at its anchor:")
    for card in cards:
        mark = "taken" if card["taken"] else "not yet"
        print(f"    {card['anchor']:>9}  {card['card']}  [{card['taken_label']}: {mark}]")

    # 10. Mei, a helper with the medicines key: reads, taps, cannot add.
    register(client, mei, "en")
    check(
        client.post(
            f"/profiles/{profile_id}/consents/sharing",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "scopes": ["medicines"],
                "relationship": "helper",
                "language": "en",
                "captured_via": "app",
            },
        ),
        201,
        "Pa agrees to let Mei see his medicines",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=bearer(pa.token),
            json={"holder_phone_e164": mei.phone_e164, "role": "helper", "scopes": ["medicines"]},
        ),
        201,
        "Pa cuts Mei a helper key",
    )
    hers = medicines_of(client, mei, profile_id, "Mei reads Pa's medicines")
    if set(hers) != {"amlodipine", "warfarin", "aspirin"}:
        raise fail("Mei reads Pa's medicines", why=f"got {sorted(hers)}")
    told = check(
        client.get(
            f"/profiles/{profile_id}/medicines/{warfarin_id}/story", headers=bearer(mei.token)
        ),
        200,
        "Mei reads the warfarin story",
    )
    if told["language"] != "ms":
        raise fail("Mei reads the warfarin story", why=f"got {told}")
    paracetamol = medicine_label("paracetamol", "500 mg", "2 tabs prn", 20)
    her_draft = client.post(
        f"/profiles/{profile_id}/medicines/draft",
        headers=bearer(mei.token),
        json={"label": paracetamol, "source_artifact_id": photo},
    )
    refused(her_draft, 403, "NotTheirsToChange", "Mei asks what a label means")
    her_yes = client.post(
        f"/profiles/{profile_id}/confirmations",
        headers=bearer(mei.token),
        json={"subject": "medicine", "label": paracetamol, "source_artifact_id": photo},
    )
    refused(her_yes, 403, "NotTheirsToChange", "Mei mints a yes for a medicine")
    her_add = client.post(
        f"/profiles/{profile_id}/medicines",
        headers=bearer(mei.token),
        json={"label": paracetamol, "source_artifact_id": photo, "confirmation_id": NO_SUCH_YES},
    )
    refused(her_add, 403, "NotTheirsToChange", "Mei adds a medicine")
    if len(medicines_of(client, pa, profile_id, "Pa reads his medicines")) != 3:
        raise fail("Mei adds a medicine", why="a line was written")
    given = check(
        client.post(
            f"/profiles/{profile_id}/medicines/{warfarin_id}/taken",
            headers=bearer(mei.token),
            json={"anchor": "bed"},
        ),
        201,
        "Mei taps Taken for the warfarin",
    )
    if given["by_person_id"] != mei.person_id:
        raise fail("Mei taps Taken for the warfarin", why=f"not in her name: {given}")
    ok(
        "Mei (helper key, medicines) reads the list (3 lines) and the warfarin story in Pa's "
        "language, and taps Taken for him in her own name; asking what a label means, minting a "
        "yes and adding a line are all refused: NotTheirsToChange (403) — a key to read the "
        "medicines is not a key to change them"
    )

    # 11. The refusals are on Pa's trail, by name, with nothing of the medicines on them.
    lines: list[JSON] = []
    for person in (pa, mei):
        lines.extend(
            check(
                client.get(
                    f"/profiles/{profile_id}/audit?actor_person_id={person.person_id}"
                    "&scope=medicines&limit=500",
                    headers=bearer(pa.token),
                ),
                200,
                "Pa reads his trail",
            )
        )
    refusals = [row for row in lines if row["outcome"] == "refused"]
    names = {(row["actor_person_id"], row["refused_because"]) for row in refusals}
    wanted = {
        (pa.person_id, "NotAConfirmerHere"),
        (mei.person_id, "NotTheirsToChange"),
    }
    if not wanted <= names:
        raise fail("Pa reads his trail", why=f"missing {wanted - names}")
    if any(word in str(lines) for word in ("warfarin", "amlodipine", "aspirin", "Dr Tan")):
        raise fail("Pa reads his trail", why="a medicine's name is on the trail")
    ok(
        f"Pa reads his trail under the medicines scope ({len(lines)} lines for the two of them); "
        "every refusal is on it by name, and no line says which medicine:"
    )
    seen: set[tuple[str, str, str]] = set()
    for row in refusals:
        who = "Mei" if row["actor_person_id"] == mei.person_id else "Pa"
        key = (who, row["action"], row["refused_because"])
        if key in seen:
            continue
        seen.add(key)
        print(
            f"    {row['at'][:19]}  {who:>3}  {row['action']} {row['scope']} {row['target']}  "
            f"refused {row['refused_because']}"
        )


# --- checkpoint 8: the feed (backend) ---------------------------------------------------------


def _page(client: httpx.Client, person: Person, profile_id: str, what: str, **params: Any) -> JSON:
    """One page of the feed. Unless a step says otherwise it pretends it is 10 in the morning
    (`?at=`, a dev-run-only query), so the checkpoint passes whatever the hour it is run at;
    the quiet-hours step pretends 22:30 the same way."""
    params.setdefault("at", _local_today_at(10))
    page: JSON = check(
        client.get(f"/profiles/{profile_id}/feed", headers=bearer(person.token), params=params),
        200,
        what,
    )
    return page


def _types(page: JSON) -> list[str]:
    return [item["type"] for item in page["items"]]


def print_cards(page: JSON) -> None:
    """Every card on a page: its section, its type, its headline, and why it is there."""

    def short_ref(value: Any) -> str:
        if isinstance(value, list):
            return "[" + ", ".join(short_ref(one) for one in value) + "]"
        text = str(value)
        return text[:8] + "…" if len(text) > 20 else text

    for item in page["items"]:
        why = item["why"]
        refs = ", ".join(
            f"{key} {short_ref(value)}"
            for key, value in why.items()
            if key not in ("kind", "plain", "boosts") and value not in (None, [], "")
        )
        print(f"    [{item['supply']:<8}] {item['type']:<9} {item['headline']}  ({item['status']})")
        print(
            f"               why: {why['plain'] or '(held for the caregiver)'}  ({refs or 'no refs'})"
        )


def _local_today_at(hour: int, minute: int = 0) -> str:
    """Today on the Singapore wall clock at this hour, as the `?at=` query wants it."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Singapore"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


def checkpoint_8(client: httpx.Client) -> None:
    from datetime import UTC, datetime, timedelta

    pa = Person("Pa", fresh_phone("+659111"))
    mei = Person("Mei", fresh_phone("+659222"))

    # 1. Pa, in English so every line can be read here; three numbers in his book.
    profile_id = open_own_profile(client, pa, "en")
    now = datetime.now(UTC)
    for days_ago, (top, bottom) in ((7, (146, 90)), (3, (142, 88))):
        check(
            client.post(
                f"/profiles/{profile_id}/readings",
                headers=bearer(pa.token),
                json={
                    "systolic": top,
                    "diastolic": bottom,
                    "taken_at": (now - timedelta(days=days_ago)).isoformat(),
                },
            ),
            201,
            f"Pa adds a blood pressure from {days_ago} days ago",
        )
    today = check(
        client.post(
            f"/profiles/{profile_id}/readings",
            headers=bearer(pa.token),
            json={"systolic": 138, "diastolic": 84},
        ),
        201,
        "Pa adds today's blood pressure",
    )
    ok(
        "Pa added three blood pressures (POST /profiles/{id}/readings): 146/90 a week ago, 142/88 "
        "three days ago, 138/84 today — each an event and a fact, State recomputing as they land"
    )

    # 2. The warfarin label from checkpoint 5: medicine facts, so there is a tablet to speak of.
    label = check(
        client.post(
            f"/profiles/{profile_id}/photos", headers=bearer(pa.token), json=_photo(WARFARIN_LABEL)
        ),
        201,
        "Pa uploads the warfarin label",
    )
    mint_and_confirm(
        client, pa, profile_id, label, decide(label, reject={"prescriber"}), "the label"
    )
    ok(
        "Pa uploaded the warfarin label and confirmed the card (the checkpoint-5 steps): five "
        "medicine facts under the medicines scope, resting on the photo"
    )
    # ...and a medicine through E04's route, five tablets at one a day: running low from today.
    pack = label_photo(client, pa, profile_id, "Pa photographs the amlodipine pack")
    added = check(
        add_medicine(
            client,
            pa,
            profile_id,
            medicine_label("amlodipine", "5 mg", "1 biji sekali sehari pagi", 5),
            pack,
            "Pa adds amlodipine",
        ),
        201,
        "Pa adds amlodipine",
    )
    ok(
        "Pa added amlodipine the checkpoint-6 way (POST /profiles/{id}/medicines with his OK): one "
        f"line ({added['generic']} {added['strength']}), a supply of "
        f"{added['supply']['quantity']} at one a day — five days left, inside the reorder threshold"
    )

    # 3. The feed: the supply order, with why on every card.
    first = _page(client, pa, profile_id, "Pa opens his feed")
    types = _types(first)
    if first["audience"] != "patient" or first["quiet"] is not False:
        raise fail("Pa opens his feed", why=f"expected the patient supply by day: {first}")
    if types[:4] != ["now", "reorder", "reading", "gate"]:
        raise fail(
            "Pa opens his feed", why=f"expected now, reorder, reading, gate first; got {types}"
        )
    if not types[4:] or not set(types[4:]) <= {"story", "learning"}:
        raise fail("Pa opens his feed", why=f"expected story and learning past the gate: {types}")
    if any(item["autoplay"] is not False for item in first["items"]):
        raise fail("Pa opens his feed", why="a card says autoplay")
    if any(not item["rendered_from_state"] for item in first["items"]):
        raise fail("Pa opens his feed", why="a card names no State")
    reading = next(item for item in first["items"] if item["type"] == "reading")
    if reading["why"]["fact_ids"] != [today["fact_id"]]:
        raise fail(
            "Pa opens his feed", why=f"the reading card does not cite today's fact: {reading}"
        )
    state = read_state(client, pa, profile_id, "Pa reads his State beside the feed")
    if {item["rendered_from_state"] for item in first["items"]} != {state["state_id"]}:
        raise fail("Pa opens his feed", why="the cards were not rendered from the current State")
    ok(
        f"GET /profiles/{{id}}/feed: the supply order — {', '.join(types)} — every card rendered "
        f"from State snapshot {state['sequence']} ({state['state_id'][:8]}…), none set to autoplay, "
        "and each says why it is there:"
    )
    print_cards(first)
    if reading["body"][0] != "Your blood pressure today was 138 over 84.":
        raise fail("Pa opens his feed", why=f"the reading card does not say the number: {reading}")
    reorder = next(item for item in first["items"] if item["type"] == "reorder")
    if reorder["why"]["fact_ids"] != [added["fact_id"]] or "runs out on" not in reorder["body"][0]:
        raise fail("Pa opens his feed", why=f"the reorder card is not from E04's count: {reorder}")
    ok(
        f'the reorder card repeats E04\'s own lines — "{reorder["body"][0]}" — cites the '
        f'medication fact {added["fact_id"][:8]}… and says why: "{reorder["why"]["plain"]}"'
    )
    ok(
        f'the reading card says his number back — "{reading["body"][0]}" — cites fact '
        f"{today['fact_id'][:8]}… and event {today['event_id'][:8]}…, and has a spoken twin of "
        f"{len(reading['voice'])} lines"
    )

    # 4. Two pages with the cursor: the same cursor is the same page; past the gate it is endless.
    cursor = first["next_cursor"]
    if not cursor:
        raise fail("Pa pages on", why="no cursor on the first page")
    second = _page(client, pa, profile_id, "Pa pages on (cursor)", cursor=cursor)
    third = _page(
        client, pa, profile_id, "Pa pages on again (next cursor)", cursor=second["next_cursor"]
    )
    again = _page(client, pa, profile_id, "Pa asks for the second page again", cursor=cursor)
    for page in (second, third):
        if not page["items"] or not set(_types(page)) <= {"story", "learning"}:
            raise fail(
                "Pa pages on", why=f"expected only story and learning past the gate: {_types(page)}"
            )
        if any(item["type"] == "learning" and not item["source_id"] for item in page["items"]):
            raise fail("Pa pages on", why="a learning card names no source")
    if [i["item_id"] for i in again["items"]] != [i["item_id"] for i in second["items"]]:
        raise fail("Pa asks for the second page again", why="the same cursor gave a different page")
    ok(
        f"paged twice with the cursor (GET …/feed?cursor=): {len(second['items'])} then "
        f"{len(third['items'])} cards, all story or learning — the list is endless past the gate — "
        "and the same cursor answers the same page"
    )

    # 5. Caps: a burst of numbers, one card.
    for top, bottom in ((140, 86), (136, 82)):
        check(
            client.post(
                f"/profiles/{profile_id}/readings",
                headers=bearer(pa.token),
                json={"systolic": top, "diastolic": bottom},
            ),
            201,
            "Pa adds another blood pressure",
        )
    burst = _page(client, pa, profile_id, "Pa opens his feed after a burst of numbers")
    if _types(burst).count("reading") != 1 or burst["held_by_caps"].get("reading") != 2:
        raise fail(
            "Pa opens his feed after a burst of numbers",
            why=f"expected one reading card and two held: {_types(burst)} {burst['held_by_caps']}",
        )
    ok(
        "caps: three numbers today made three cards, one is shown — one of each kind a day, two "
        f"new cards a day — and the page says what was held: {burst['held_by_caps']}"
    )

    # 6. Quiet hours, pretending it is 22:30 (dev run only: `?at=`).
    night = _page(
        client, pa, profile_id, "Pa opens his feed at night (?at=22:30)", at=_local_today_at(22, 30)
    )
    if night["quiet"] is not True or night["items"]:
        raise fail("Pa opens his feed at night (?at=22:30)", why=f"expected nothing: {night}")
    ok(
        "quiet hours (21:00–07:00 on his wall clock, pretended with ?at=22:30 on this dev run): "
        f"nothing is delivered; held: {night['held_by_caps']}"
    )

    # 7. A red flag: raised before any ranking, first in the queue, unaffected by caps or the hour.
    felt = check(
        client.post(
            f"/profiles/{profile_id}/feelings", headers=bearer(pa.token), json={"word": "fall"}
        ),
        201,
        "Pa taps 'a fall' on the feeling cloud",
    )
    if felt["red_flag"] is not True or not felt["flag_id"]:
        raise fail("Pa taps 'a fall' on the feeling cloud", why=f"no flag raised: {felt}")
    night = _page(
        client,
        pa,
        profile_id,
        "Pa opens his feed at night after the fall",
        at=_local_today_at(22, 30),
    )
    if _types(night) != ["flag"]:
        raise fail(
            "Pa opens his feed at night after the fall",
            why=f"expected only the flag: {_types(night)}",
        )
    flagged = _page(client, pa, profile_id, "Pa opens his feed after the fall")
    if _types(flagged)[:2] != ["flag", "now"] or flagged["held_by_caps"].get("reading") != 2:
        raise fail(
            "Pa opens his feed after the fall",
            why=f"expected the flag first and the caps untouched: {_types(flagged)} {flagged['held_by_caps']}",
        )
    flag = flagged["items"][0]
    ok(
        "a red flag jumps the queue: POST /profiles/{id}/feelings {word: fall} raised a flag before "
        "any ranking; the flag card is first, in quiet hours too, and took no place from the two a day:"
    )
    for line in flag["body"]:
        print(f"    {line}")

    # 8. "Not for me": the kind is held for the rest of the day, and State folded his word in.
    shown = next(item for item in flagged["items"] if item["type"] == "reading")
    check(
        client.post(
            f"/profiles/{profile_id}/feed/{shown['item_id']}/engagement",
            headers=bearer(pa.token),
            json={"event": "dismissed"},
        ),
        201,
        "Pa taps 'Not for me' on the reading card",
    )
    after = _page(client, pa, profile_id, "Pa opens his feed after 'Not for me'")
    if "reading" in _types(after):
        raise fail(
            "Pa opens his feed after 'Not for me'",
            why=f"a reading card is still shown: {_types(after)}",
        )
    state = read_state(client, pa, profile_id, "Pa reads his State after 'Not for me'")
    declined = state["dimensions"]["preference"]["facts"].get("declined", {}).get("reading")
    if not declined or declined["confidence_state"] != "confirmed_by_person":
        raise fail(
            "Pa reads his State after 'Not for me'",
            why=f"no declined fact folded in: {state['dimensions']['preference']}",
        )
    ok(
        "'Not for me' (POST …/feed/{item}/engagement {event: dismissed}): the reading cards are held "
        f"for the rest of today ({after['held_by_caps']}); his word is a fact — declined.reading, "
        f"confirmed by him, resting on the engagement event {declined['event_id'][:8]}… — and State "
        f"folded it into the preference dimension (snapshot {state['sequence']})"
    )

    # 9. Mei: the caregiver supply, narrowed; the held notice; no gate; sources are not hers.
    register(client, mei, "en")
    scopes = ["medicines", "visits", "readings", "records", "emergency"]
    check(
        client.post(
            f"/profiles/{profile_id}/consents/sharing",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "scopes": scopes,
                "relationship": "daughter",
                "language": "en",
                "captured_via": "app",
            },
        ),
        201,
        "Pa agrees to let Mei in",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=bearer(pa.token),
            json={"holder_phone_e164": mei.phone_e164, "role": "caregiver", "scopes": scopes},
        ),
        201,
        "Pa cuts Mei a caregiver key",
    )
    hers = _page(client, mei, profile_id, "Mei opens Pa's feed")
    if hers["audience"] != "caregiver" or "gate" in _types(hers) or _types(hers)[0] != "flag":
        raise fail(
            "Mei opens Pa's feed",
            why=f"expected the caregiver supply, flag first, no gate: {_types(hers)}",
        )
    notice = [item for item in hers["items"] if item["type"] == "notice"]
    if (
        not notice
        or notice[0]["status"] != "held"
        or notice[0]["why"].get("suppressed") != "batch_does_not_match_the_pack"
    ):
        raise fail("Mei opens Pa's feed", why=f"expected the held safety notice: {notice}")
    if any(item["scope"] == "notes" for item in hers["items"]):
        raise fail(
            "Mei opens Pa's feed", why="a card built from his private notes reached a caregiver key"
        )
    ok(
        "Mei (caregiver key: medicines, visits, readings, records, emergency) sees the caregiver "
        f"supply — {', '.join(_types(hers))} — the flag first, no gate, each with its status; the "
        "safety notice about a warfarin batch that is not the one on his box is held for her and "
        "was never on his feed:"
    )
    print_cards(hers)
    refused(
        client.get(f"/profiles/{profile_id}/sources", headers=bearer(mei.token)),
        403,
        "NotTheirsToManage",
        "Mei asks for the allowlist",
    )
    ok(
        "the allowlist is the owner's and his chief's: Mei's caregiver key is refused, NotTheirsToManage (403)"
    )

    # 10. Learning from the allowlist: the jobs State started, and the card that came of them.
    jobs = check(
        client.get(f"/profiles/{profile_id}/search-jobs", headers=bearer(pa.token)),
        200,
        "Pa reads the search jobs the engine started",
    )
    kinds = {(job["kind"], tuple(job["terms"]), job["cadence"], job["status"]) for job in jobs}
    if ("explainer", ("warfarin",), "on_change", "done") not in kinds or (
        "safety",
        ("warfarin",),
        "daily",
        "done",
    ) not in kinds:
        raise fail("Pa reads the search jobs the engine started", why=f"jobs {sorted(kinds)}")
    explainer = next(
        job for job in jobs if job["kind"] == "explainer" and job["terms"] == ["warfarin"]
    )
    if not explainer["results"]["items"] or not explainer["results"]["questions"]:
        raise fail(
            "Pa reads the search jobs the engine started", why=f"results {explainer['results']}"
        )
    learning = [
        item
        for page in (first, second, third)
        for item in page["items"]
        if item["type"] == "learning" and "blood thinner" in item["headline"]
    ]
    if not learning or not learning[0]["cite"]["url"].startswith("https://www.hsa.gov.sg/"):
        raise fail(
            "Pa reads the search jobs the engine started", why="no learning card from the HSA page"
        )
    sources = check(
        client.get(f"/profiles/{profile_id}/sources", headers=bearer(pa.token)),
        200,
        "Pa reads the allowlist",
    )
    if learning[0]["source_id"] not in {source["source_id"] for source in sources}:
        raise fail("Pa reads the allowlist", why="the learning card's source is not on it")
    # E16-01: a learning card is an inferring surface; it ends on the boundary line and the
    # line is on the card. A card that shows the record back carries none.
    boundary = (learning[0].get("boundary") or "").splitlines()
    if not boundary or learning[0]["body"][-len(boundary) :] != boundary:
        raise fail("Pa reads the learning card", why="it does not end on the boundary line")
    shown = [item for page in (first, second, third) for item in page["items"]]
    if any(item.get("boundary") for item in shown if item["type"] not in {"learning", "notice"}):
        raise fail("Pa reads the learning card", why="a card that infers nothing carries a line")
    ok(
        f"self-search: the medicine started an explainer job and a daily safety job (GET …/search-jobs, "
        f"{len(jobs)} jobs, all done against the fixture searcher); the explainer made a learning card "
        f'"{learning[0]["headline"]}" citing {learning[0]["cite"]["url"]} — a source on the allowlist '
        f"(GET …/sources, {len(sources)} sources) — and rerouted the page that would change a dose "
        f"as a question for the memo ({len(explainer['results']['questions'])}), never a card; "
        "it ends on the boundary line it carries (E16-01), and no other card carries one:"
    )
    for line in learning[0]["body"]:
        print(f"    {line}")

    # 11. The offline page.
    cached = check(
        client.get(f"/profiles/{profile_id}/feed/cached", headers=bearer(pa.token)),
        200,
        "Pa's app asks for the cached page",
    )
    if [i["item_id"] for i in cached["items"]] != [i["item_id"] for i in after["items"]]:
        raise fail("Pa's app asks for the cached page", why="not the last first page rendered")
    ok(
        f"GET …/feed/cached: the last first page rendered for Pa, {len(cached['items'])} cards, as it "
        "was — what the app keeps for an offline launch"
    )

    # 12. The trail holds the refusals.
    trail = check(
        client.get(
            f"/profiles/{profile_id}/audit",
            headers=bearer(pa.token),
            params={"limit": 500},
        ),
        200,
        "Pa reads his audit trail",
    )
    refusals = [e for e in trail if e["outcome"] == "refused"]
    if not any(
        e["refused_because"] == "NotTheirsToManage" and e["actor_person_id"] == mei.person_id
        for e in refusals
    ):
        raise fail(
            "Pa reads his audit trail", why="Mei's refused reach for the allowlist is not on it"
        )
    shares = [e for e in trail if e["action"] == "share" and e["target"] == "red_flag"]
    ok(
        f"Pa reads his audit trail ({len(trail)} lines): every card, page, job and engagement is on "
        f"it as a write, Mei's refusal is on it by name, and the flag's escalation is {len(shares)} "
        "share line(s) — none, here, because the fall came before Mei held a key with the emergency scope"
    )


# --- checkpoint 9: WhatsApp (sandbox) ------------------------------------------------------------


def inbound(client: httpx.Client, person: Person, what: str, **message: Any) -> JSON:
    """A message from this person's number through the dev door, the webhook's own path."""
    handled: JSON = check(
        client.post("/dev/whatsapp/inbound", json={"from_e164": person.phone_e164, **message}),
        200,
        what,
    )
    return handled


def print_reply(handled: JSON) -> None:
    for sent in handled.get("replies", []):
        for line in sent["text"].splitlines():
            print(f"    → {line}")
    if handled.get("stranger_reply"):
        for line in handled["stranger_reply"].splitlines():
            print(f"    → {line}")


def checkpoint_9(client: httpx.Client) -> None:
    pa = Person("Pa", fresh_phone("+659111"))
    mei = Person("Mei", fresh_phone("+659222"))
    kit = Person("Kit", fresh_phone("+659555"))

    # 1. Pa opens his profile; Mei is his chief; nobody has agreed to WhatsApp yet.
    profile_id = open_own_profile(client, pa, "en")
    register(client, mei, "en")
    check(
        client.post(
            f"/profiles/{profile_id}/consents/sharing",
            headers=bearer(pa.token),
            json={
                "holder_phone_e164": mei.phone_e164,
                "scopes": [
                    "medicines",
                    "visits",
                    "readings",
                    "records",
                    "family",
                    "emergency",
                    "send",
                ],
                "relationship": "daughter",
                "language": "en",
                "captured_via": "app",
            },
        ),
        201,
        "Pa agrees to let Mei in",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/keys",
            headers=bearer(pa.token),
            json={"holder_phone_e164": mei.phone_e164, "role": "chief"},
        ),
        201,
        "Pa cuts Mei a chief key",
    )
    ok("Pa let Mei, his daughter, in to his record and cut her a chief key")
    early = inbound(client, mei, "Mei writes before Pa agreed to WhatsApp", text="BP 150/90")
    if early["outcome"] != "refused" or early["refused"] != "ConsentWithheld":
        raise fail("Mei writes before Pa agreed to WhatsApp", why=f"got {early}")
    if client.get(f"/profiles/{profile_id}/facts", headers=bearer(pa.token)).json():
        raise fail("Mei writes before Pa agreed to WhatsApp", why="something was written")
    ok(
        "Mei wrote to the number before Pa agreed to WhatsApp: refused, ConsentWithheld, nothing "
        "kept — the one line she got says so, and names no health content:"
    )
    print_reply(early)
    outbox = check(client.get("/dev/whatsapp/outbox"), 200, "the outbox")
    for sent in outbox[-1:]:
        for line in sent["text"].splitlines():
            print(f"    → {line}")

    # 2. Pa agrees to WhatsApp, in words he read.
    agreed = check(
        client.post(
            f"/profiles/{profile_id}/consents/whatsapp",
            headers=bearer(pa.token),
            json={"language": "en", "captured_via": "app"},
        ),
        201,
        "Pa agrees to WhatsApp",
    )
    ok(
        "Pa agreed to WhatsApp (POST /profiles/{id}/consents/whatsapp, his own basis); the words he read:"
    )
    for line in agreed["wording_text"].splitlines():
        print(f"    {line}")

    # 3. Level 0: a medicine on the list, then the morning card to Pa as a template — Pa has
    #    not written to the number, so it goes as one of the six, not as free text.
    label = label_photo(client, pa, profile_id, "Pa keeps the amlodipine label photo")
    amlodipine = medicine_label("amlodipine", "5 mg", "1 tab OM", 30)
    check(
        add_medicine(client, pa, profile_id, amlodipine, label, "Pa adds amlodipine"),
        201,
        "Pa adds amlodipine",
    )
    morning = check(
        client.post(f"/dev/whatsapp/morning/{profile_id}"), 200, "the morning card goes to Pa"
    )
    if morning["kind"] != "template" or morning["template_name"] != "morning_card":
        raise fail("the morning card goes to Pa", why=f"got {morning}")
    if "blood pressure tablet" not in morning["text"]:
        raise fail("the morning card goes to Pa", why=f"no dose on the card: {morning}")
    ok(
        "Pa added amlodipine from a label (checkpoint 6's route); run_morning (POST "
        "/dev/whatsapp/morning/{id}, what the scheduler will call) sent Pa the morning card — one of "
        "the six approved templates, because Pa has not written in the last 24 hours, composed from "
        "the now and today cards of his feed (the tablets card said as today's doses) and the State "
        "they came from, through his WHATSAPP consent, verified against plain words:"
    )
    for line in morning["text"].splitlines():
        print(f"    → {line}")

    # 4. Mei forwards a photo: filed as a review card, replied to in her thread.
    photo = inbound(
        client,
        mei,
        "Mei forwards the lipid report",
        media_id="lipid-panel-photo",
        content_type="image/png",
    )
    if photo["outcome"] != "document" or not photo["review_card_id"]:
        raise fail("Mei forwards the lipid report", why=f"got {photo}")
    card = check(
        client.get(
            f"/profiles/{profile_id}/review-cards/{photo['review_card_id']}",
            headers=bearer(pa.token),
        ),
        200,
        "Pa reads the card the photo became",
    )
    if card["document_kind"] != "lab_report" or len(card["fields"]) != 7 or card["confirmed_at"]:
        raise fail("Pa reads the card the photo became", why=f"got {card}")
    ok(
        "Mei forwarded the lipid report (POST /dev/whatsapp/inbound, media from the fixtures — the "
        "webhook's own path, no Meta): the bytes went to the SG store as a WhatsApp photo artefact, "
        f"the extractor read it as a lab_report, and a review card with {len(card['fields'])} fields "
        "waits for a yes in the app; nothing is a fact. The reply in her thread:"
    )
    print_reply(photo)

    # 5. A health event becomes a proposal. Nothing is written before the yes.
    heard = inbound(client, mei, "Mei posts a blood pressure", text="BP 150/90 this morning")
    if heard["outcome"] != "proposal" or not heard["proposal_id"] or heard["fact_id"]:
        raise fail("Mei posts a blood pressure", why=f"got {heard}")
    facts = check(
        client.get(
            f"/profiles/{profile_id}/facts",
            headers=bearer(pa.token),
            params={"subject": "blood_pressure"},
        ),
        200,
        "Pa reads his blood pressure facts",
    )
    if facts != []:
        raise fail("Pa reads his blood pressure facts", why=f"a fact before the yes: {facts}")
    ok(
        'Mei posted "BP 150/90 this morning": the classifier heard a blood pressure and wrote a '
        "proposal — what was heard, who said it, good for a day — and nothing else: "
        "GET /facts?subject=blood_pressure is []. The read-back in her thread:"
    )
    print_reply(heard)

    # 6. Kit, a number nobody knows: one fixed line, nothing stored.
    stranger = inbound(client, kit, "Kit writes to the number", text="BP 160/95, this is Pa's son")
    if stranger["outcome"] != "unknown_number" or stranger["profile_id"] is not None:
        raise fail("Kit writes to the number", why=f"got {stranger}")
    if any(k in stranger["stranger_reply"] for k in ("Pa", "160", "Mei")):
        raise fail("Kit writes to the number", why="the reply named someone or something")
    ok(
        f"Kit ({kit.phone_e164}), a number no profile knows, wrote to the number: one fixed reply, "
        "no health content, nothing stored, no thread, no line on any trail:"
    )
    print_reply(stranger)

    # 7. Someone else's yes finds nothing open; the poster's yes writes the fact.
    his = inbound(client, pa, "Pa answers yes to Mei's question", text="yes")
    if his["outcome"] != "nothing_open" or his["fact_id"]:
        raise fail("Pa answers yes to Mei's question", why=f"got {his}")
    ok(
        'Pa answered "yes": nothing of his is waiting, so nothing was written — only the poster confirms:'
    )
    print_reply(his)
    yes = inbound(client, mei, "Mei answers yes", text="yes")
    if yes["outcome"] != "confirmed" or not yes["fact_id"]:
        raise fail("Mei answers yes", why=f"got {yes}")
    facts = check(
        client.get(
            f"/profiles/{profile_id}/facts",
            headers=bearer(pa.token),
            params={"subject": "blood_pressure"},
        ),
        200,
        "Pa reads his blood pressure facts after the yes",
    )
    if len(facts) != 1 or facts[0]["fact_id"] != yes["fact_id"]:
        raise fail("Pa reads his blood pressure facts after the yes", why=f"got {facts}")
    fact = facts[0]
    if (
        fact["value"] != {"systolic": 150, "diastolic": 90}
        or fact["confirmed_by_person_id"] != mei.person_id
        or not fact["event_id"]
        or fact["artifact_id"] != heard["artifact_id"]
    ):
        raise fail("Pa reads his blood pressure facts after the yes", why=f"got {fact}")
    state = read_state(client, pa, profile_id, "Pa reads his State after the yes")
    if state["trigger"] != {"kind": "new_fact", "fact_id": fact["fact_id"]}:
        raise fail("Pa reads his State after the yes", why=f"trigger {state['trigger']}")
    ok(
        'Mei answered "yes": a confirmation was minted for exactly the draft recomputed from the '
        "proposal and spent in the same unit of work; the reading is a Fact, 150/90 mmHg, "
        "confirmed_by_person Mei, resting on the event of the reading and on the message it was "
        f"heard in (artefact {heard['artifact_id'][:8]}…); State recomputed, snapshot "
        f"{state['sequence']}, trigger new_fact naming it. The reply:"
    )
    print_reply(yes)

    # 8. A red flag: the flag first, the reply in the thread, the ladder written down.
    fell = inbound(client, mei, "Mei posts a fall", text="he fell in the bathroom")
    if fell["outcome"] != "red_flag" or not fell["flag_id"] or fell["proposal_id"]:
        raise fail("Mei posts a fall", why=f"got {fell}")
    trail = check(
        client.get(
            f"/profiles/{profile_id}/audit",
            headers=bearer(pa.token),
            params={"scope": "emergency", "limit": 500},
        ),
        200,
        "Pa reads the emergency lines of his trail",
    )
    steps = [e["target"] for e in reversed(trail) if e["action"] == "write"]
    if "red_flag" not in steps or "safety_escalation" not in steps:
        raise fail("Pa reads the emergency lines of his trail", why=f"got {steps}")
    if steps.index("red_flag") > steps.index("safety_escalation"):
        raise fail("Pa reads the emergency lines of his trail", why=f"flag after ladder: {steps}")
    ok(
        'Mei posted "he fell in the bathroom": a red flag (the word table in app/safety/red_flags.py) '
        "— the moment it was said (a SYMPTOM event) and the Flag on it were written first, before the "
        "message was even kept, then the message, then the "
        "escalation record naming the ladder from the keys table (owner, chief keys, others; the "
        "poster left out); nothing was extracted, no proposal. The reply in her thread, at once:"
    )
    print_reply(fell)
    for row in reversed(trail):
        if row["action"] == "write" and row["target"] in ("red_flag", "safety_escalation"):
            print(f"    {row['at'][:19]}  Mei  write emergency {row['target']}  {row['channel']}")

    # 9. Pa's own word about himself: written down without a second yes.
    tired = inbound(client, pa, 'Pa answers "tired"', text="tired")
    if tired["outcome"] != "check_in_answer" or not tired["fact_id"] or tired["proposal_id"]:
        raise fail('Pa answers "tired"', why=f"got {tired}")
    feeling = check(
        client.get(
            f"/profiles/{profile_id}/facts",
            headers=bearer(pa.token),
            params={"subject": "feeling"},
        ),
        200,
        "Pa reads his feeling fact",
    )
    if len(feeling) != 1 or feeling[0]["value"] != "tired" or not feeling[0]["event_id"]:
        raise fail("Pa reads his feeling fact", why=f"got {feeling}")
    ok(
        'Pa answered "tired": his own word about himself, one of the three the check-in offers, so no '
        "read-back — a SYMPTOM event and a feeling fact confirmed by him, the yes minted and spent in "
        "the same request the way the app's save button does. The reply:"
    )
    print_reply(tired)

    # 10. The thread as Pa reads it, by reference; and every line on the trail.
    thread = check(
        client.get(f"/profiles/{profile_id}/whatsapp/thread", headers=bearer(pa.token)),
        200,
        "Pa reads the thread",
    )
    # Every field but the ids and the times: a uuid is hex and a time is digits, so "150" can
    # turn up in one by chance. The words could only be in one of the other fields.
    fields = [
        str(value)
        for message in thread
        for key, value in message.items()
        if not key.endswith("_id") and key != "at"
    ]
    if any(word in field for field in fields for word in ("150", "fell", "tired")):
        raise fail("Pa reads the thread", why="the words are on the thread; it is by reference")
    kinds = sorted({(m["direction"], m["kind"]) for m in thread})
    wanted_kinds = {
        ("inbound", "document"),
        ("inbound", "health_event"),
        ("inbound", "answer"),
        ("inbound", "red_flag"),
        ("inbound", "check_in_answer"),
        ("outbound", "reply"),
        ("outbound", "template"),
    }
    if not wanted_kinds <= set(kinds):
        raise fail("Pa reads the thread", why=f"kinds {kinds}")
    if any(m["person_id"] == kit.person_id for m in thread):
        raise fail("Pa reads the thread", why="Kit is on the thread")
    ok(
        f"Pa reads the thread (GET /profiles/{{id}}/whatsapp/thread, {len(thread)} messages, owner and "
        "chief only): every kept message by reference — who, when, what kind, which artefact, template "
        "or State — never the words; Kit is not on it"
    )
    register(client, kit, "en")
    refused_ = client.get(f"/profiles/{profile_id}/whatsapp/thread", headers=bearer(kit.token))
    refused(refused_, 403, "NoKey", "Kit reads the thread")
    ok("Kit, now registered but on no family list, is refused the thread: NoKey (403)")
    lines = check(
        client.get(
            f"/profiles/{profile_id}/audit", headers=bearer(pa.token), params={"limit": 500}
        ),
        200,
        "Pa reads his trail",
    )
    on_whatsapp = [e for e in lines if e["channel"] == "whatsapp"]
    shares = [e for e in on_whatsapp if e["action"] == "share"]
    if len(shares) < 6 or not any(e["target"] == "refusal_notice" for e in shares):
        raise fail("Pa reads his trail", why=f"{len(shares)} share lines")
    if any(e["actor_person_id"] == kit.person_id for e in lines):
        raise fail("Pa reads his trail", why="Kit's reach was written into the trail")
    refusals = [e for e in on_whatsapp if e["outcome"] == "refused"]
    ok(
        f"Pa reads his trail ({len(lines)} lines, {len(on_whatsapp)} on the WhatsApp channel): every "
        f"kept message is a write, every send a SHARE naming who it went to ({len(shares)} of them, "
        "the refusal notice included), and the refusals are on it by name; Kit is on none of it:"
    )
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
    6: checkpoint_6,
    8: checkpoint_8,
    9: checkpoint_9,
    13: lambda client: checkpoints.cp13.run(BASE_URL, DEV_LOG) and sys.exit(1),
    17: lambda client: checkpoints.cp17.run(BASE_URL, DEV_LOG) and sys.exit(1),
    18: lambda client: checkpoints.cp18.run(BASE_URL, DEV_LOG) and sys.exit(1),
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
