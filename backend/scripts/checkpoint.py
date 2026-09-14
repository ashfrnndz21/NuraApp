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

import os
import random
import re
import sys
import time
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


CHECKPOINTS = {2: checkpoint_2}


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
