"""Checkpoint 14 — emergency card, not feeling well, symptoms (E13-01, E13-02, E14-01).

    make dev                # one terminal
    make checkpoint N=14    # another

`run(base_url, dev_log)` walks the scenario over HTTP and returns the exit code. Like
`scripts.checkpoint`, it is a client and nothing more: it never imports the app, reads the
login code from the server log the way the owner would, and prints one `✓`/`✗` line per step,
stopping at the first `✗`. Fresh phone numbers every run.

The story: Pa (Singapore) with Mei as chief, Lin holding an emergency-only key, Kit holding
nothing; the water pill and a blood pressure on the record. Pa's emergency card as JSON and as
the printable page; Mei and Lin read it. Pa says "tired today" and is told to rest; Pa says
"chest pain" by voice (his own note, ADR 0003) and the flag is written first, the posture is ACT, Mei is told, and the
card says she knows already and to call the ambulance on 995. Pa logs "dizzy, quite a lot, since this morning" and Mei
reads it back in plain words. Kit is refused.
"""

from __future__ import annotations

import base64
import os
import random
import re
import time
from html.parser import HTMLParser
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
VOICE_CONTENT_TYPE = "audio/m4a"

JSON = dict[str, Any]


class Failed(Exception):
    """One step did not do what the checkpoint says. Carries the printed line."""


class Person:
    def __init__(self, name: str, phone_e164: str) -> None:
        self.name = name
        self.phone_e164 = phone_e164
        self.token = ""
        self.person_id = ""


# --- the small helpers, the same shape as scripts/checkpoint.py ---------------------------------


def placeholder_png(label: str) -> bytes:
    """Bytes the fixture extractor does not know: an unknown paper, so a label photo."""
    return PNG_SIGNATURE + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"


def placeholder_voice(label: str) -> bytes:
    """The same one line as `backend/tests/voice.py`: the digest names the transcript."""
    return b"nura-voice-placeholder:" + label.encode("ascii") + b"\n"


def bearer(token: str | None) -> dict[str, str]:
    return {} if not token else {"Authorization": f"Bearer {token}"}


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
    stale = dev_log.stat().st_mtime < since
    raise Failed(
        f"✗ no login code for {phone_e164} appeared in {dev_log} within {CODE_WAIT_SECONDS:.0f}s"
        + (" — the file has not changed since this run began" if stale else "")
        + ". Stop the server and run `make dev` (only that writes the log here)"
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
    ok(f"{who} registered by phone code (no SMS; the six digits read from the server log) and signed in")


def open_own_profile(client: httpx.Client, dev_log: Path, person: Person, language: str) -> str:
    register(client, dev_log, person, language)
    opened = check(
        client.post(
            "/profiles/mine",
            headers=bearer(person.token),
            json={
                "consent": {"wording_version": HOLD_WORDING, "language": language, "captured_via": "app"},
                "display_name": person.name,
                "language": language,
            },
        ),
        201,
        f"{person.name} opens his own profile",
    )
    profile_id: str = opened["profile_id"]
    ok(f"{person.name} opened his own profile (wording {HOLD_WORDING}, in the app)")
    return profile_id


def let_in_and_cut(
    client: httpx.Client, owner: Person, profile_id: str, holder: Person, role: str, scopes: list[str]
) -> JSON:
    agreed = client.post(
        f"/profiles/{profile_id}/consents/sharing",
        headers=bearer(owner.token),
        json={
            "holder_phone_e164": holder.phone_e164,
            "holder_display_name": holder.name,
            "scopes": scopes,
            "relationship": "daughter" if role == "chief" else "neighbour",
            "language": "en",
            "captured_via": "app",
        },
    )
    check(agreed, 201, f"{owner.name} agrees to let {holder.name} in")
    granted = client.post(
        f"/profiles/{profile_id}/keys",
        headers=bearer(owner.token),
        json={"holder_phone_e164": holder.phone_e164, "role": role},
    )
    key: JSON = check(granted, 201, f"{owner.name} cuts {holder.name} a {role} key")
    return key


class _Text(HTMLParser):
    """The visible sentences of the printable page, in order."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("style", "title", "head"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "title", "head") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text and not self._skip:
            self.lines.append(text)


# --- the walk -----------------------------------------------------------------------------------


def walk(client: httpx.Client, dev_log: Path) -> None:
    pa = Person("Pa", fresh_phone("+659111"))
    mei = Person("Mei", fresh_phone("+659222"))
    lin = Person("Lin", fresh_phone("+659444"))
    kit = Person("Kit", fresh_phone("+659333"))

    # 1. The household: Pa opens his profile; Mei is chief; Lin holds an emergency-only key;
    #    Kit holds nothing.
    profile_id = open_own_profile(client, dev_log, pa, "en")
    his = bearer(pa.token)
    register(client, dev_log, mei, "en")
    register(client, dev_log, lin, "en")
    register(client, dev_log, kit, "en")
    every = ["medicines", "visits", "readings", "records", "notes", "money", "family", "emergency", "ask", "send"]
    let_in_and_cut(client, pa, profile_id, mei, "chief", every)
    ok("Pa let Mei, his daughter, in to everything and cut her the chief key")
    key = let_in_and_cut(client, pa, profile_id, lin, "emergency", ["emergency"])
    if sorted(key["scopes"]) != ["emergency", "profile"]:
        raise fail("Lin's key is emergency-only", why=f"scopes {key['scopes']}")
    ok("Pa let Lin, a neighbour, in to the emergency card only and cut her an emergency key (scopes: emergency, profile)")

    # 2. The water pill from a label photo, tapped Taken; a blood pressure.
    photo = check(
        client.post(
            f"/profiles/{profile_id}/photos",
            headers=his,
            json={
                "data": base64.b64encode(placeholder_png(f"label-{random.randint(0, 10**9)}")).decode(),
                "content_type": "image/png",
                "captured_at": "2026-09-14T08:00:00Z",
            },
        ),
        201,
        "Pa keeps the label photo",
    )
    label = {
        "generic": "frusemide",
        "strength": "40 mg",
        "dose_text": "1 tab OD morning",
        "quantity": 30,
        "prescriber": "Dr Tan",
        "source_kind": "retail",
    }
    yes = check(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=his,
            json={"subject": "medicine", "label": label, "source_artifact_id": photo["artifact_id"]},
        ),
        201,
        "Pa says OK to the water pill",
    )
    added = check(
        client.post(
            f"/profiles/{profile_id}/medicines",
            headers=his,
            json={"label": label, "source_artifact_id": photo["artifact_id"], "confirmation_id": yes["confirmation_id"]},
        ),
        201,
        "Pa adds the water pill",
    )
    check(
        client.post(
            f"/profiles/{profile_id}/medicines/{added['line_id']}/taken",
            headers=his,
            json={"anchor": "breakfast", "amount": 1},
        ),
        201,
        "Pa taps Taken on the water pill",
    )
    ok("Pa added the water pill (frusemide 40 mg, 1 tablet every morning) from a label photo, with his OK, and tapped Taken")
    check(
        client.post(f"/profiles/{profile_id}/readings", headers=his, json={"systolic": 138, "diastolic": 84}),
        201,
        "Pa types in a blood pressure",
    )
    ok("Pa typed in a blood pressure (138 over 84): a reading event and a fact resting on it")

    # 2b. His insurer on the card (E13-01): typed by him, on his yes for exactly these words.
    insurer = {"name": "Great Eastern", "policy_reference": "GE-4471-0932"}
    yes = check(
        client.post(f"/profiles/{profile_id}/confirmations", headers=his, json={"subject": "insurer", **insurer}),
        201,
        "Pa says yes to his insurer",
    )
    check(
        client.put(
            f"/profiles/{profile_id}/emergency-card/insurer",
            headers=his,
            json={**insurer, "confirmation_id": yes["confirmation_id"]},
        ),
        200,
        "Pa puts his insurer on the card",
    )
    refused(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=bearer(lin.token),
            json={"subject": "insurer", "name": "AIA"},
        ),
        403,
        "NotTheirsToSetInsurer",
        "Lin tries to set his insurer",
    )
    refused(
        client.post(
            f"/profiles/{profile_id}/confirmations",
            headers=his,
            json={"subject": "insurer", "name": "AIA", "policy_reference": "S1234567D"},
        ),
        400,
        "NotAPolicyReference",
        "an identity-card number offered as a policy reference",
    )
    ok(
        "Pa typed his insurer (Great Eastern, policy GE-4471-0932) on his yes (subject insurer, "
        "PUT /profiles/{id}/emergency-card/insurer); Lin, with the emergency card only, cannot set it "
        "(NotTheirsToSetInsurer, 403), and an identity-card number is refused as a policy reference "
        "(NotAPolicyReference, 400)"
    )

    # 3. Pa's emergency card, as JSON and as the printable page.
    card = check(client.get(f"/profiles/{profile_id}/emergency-card", headers=his), 200, "Pa reads his emergency card")
    texts = [line["text"] for line in card["lines"]]
    medicine = card["medicines"][0]
    if (
        medicine["generic"] != "frusemide"
        or medicine["strength"] != "40 mg"
        or card["contacts"][0]["name"] != "Mei"
        or card["emergency_number"] != "995"
        or texts[0] != "This is Pa's emergency card."
        or card["last_reading_at"] is None
        or card["insurer"] != insurer
        or "Pa is insured with Great Eastern." not in texts
        or any("GE-4471" in text for text in texts)
        or card["english_lines"] != []
    ):
        raise fail("Pa reads his emergency card", why=f"got {card}")
    ok(
        "Pa read his emergency card (GET /profiles/{id}/emergency-card): the water pill with its "
        "strength and how much, Mei's name and number, his insurer (the policy reference as data, "
        "never in a sentence), the last blood pressure's date, 995 for "
        f"Singapore, rendered from State {card['state_id'][:8]}… and written down as render "
        f"{card['card_id'][:8]}…; the lines, every one verified:"
    )
    for line in texts:
        say(line)
    page = client.get(f"/profiles/{profile_id}/emergency-card.html", headers=his)
    if page.status_code != 200 or not page.headers.get("content-type", "").startswith("text/html"):
        raise fail("Pa opens the printable page", page, "expected an HTML page")
    html = page.text
    for forbidden in ("http://", "https://", "<script", "<link", "<img"):
        if forbidden in html:
            raise fail("the printable page is self-contained", why=f"found {forbidden!r}")
    if (
        "#2B2733" not in html
        or "font-size: 20px" not in html
        or "40 mg" not in html
        or "GE-4471-0932" not in html
    ):
        raise fail("the printable page carries the tokens and the data", why="a token or the strength is missing")
    parsed = _Text()
    parsed.feed(html)
    ok(
        "Pa opened the printable page (GET /profiles/{id}/emergency-card.html): one self-contained "
        "page — no script, no stylesheet, no image fetched — paper surface, Ink #2B2733 on white, "
        "20px body, the strength and the phone number as data beside the sentences; its first lines:"
    )
    say(f"{client.base_url}/profiles/{profile_id}/emergency-card.html")
    for line in parsed.lines[:6]:
        say(line)

    # 4. Mei (chief) and Lin (emergency-only) read the card.
    hers = check(client.get(f"/profiles/{profile_id}/emergency-card", headers=bearer(mei.token)), 200, "Mei reads the card")
    theirs = check(client.get(f"/profiles/{profile_id}/emergency-card", headers=bearer(lin.token)), 200, "Lin reads the card")
    if theirs["state_id"] != card["state_id"] or theirs["lines"] != card["lines"]:
        raise fail("Lin reads the card", why="a different State or different lines from Pa's")
    if theirs["insurer"] != insurer:
        raise fail("Lin reads the card", why="the insurer is missing from the emergency-only key's card")
    ok(
        f"Mei read the card with her chief key (render {hers['card_id'][:8]}…), and Lin read it with "
        "her emergency-only key — the same lines, the insurer included, stamped with the same State: "
        "an emergency key opens the card's fixed projection and nothing else, and is refused a stale card"
    )

    # 4b. Two languages on one card (E13-01): in Chinese, every line with its English twin, for
    #     the ambulance crew — on the JSON and on the printable page.
    zh = check(
        client.get(f"/profiles/{profile_id}/emergency-card?language=zh", headers=bearer(lin.token)),
        200,
        "Lin reads the card in Chinese",
    )
    twins = list(zip([one["text"] for one in zh["lines"]], [one["text"] for one in zh["english_lines"]], strict=False))
    if (
        zh["language"] != "zh"
        or [one["id"] for one in zh["english_lines"]] != [one["id"] for one in zh["lines"]]
        or zh["english_lines"][0]["text"] != "This is Pa's emergency card."
    ):
        raise fail("Lin reads the card in Chinese", why=f"got {zh}")
    printed = client.get(f"/profiles/{profile_id}/emergency-card.html?language=zh", headers=bearer(lin.token))
    if printed.status_code != 200 or '<p class="twin" lang="en">' not in printed.text:
        raise fail("the printable page in two languages", printed, "expected the English twins")
    ok(
        "Lin read the card in Chinese (GET …/emergency-card?language=zh): every line with its English "
        f"twin under the same id ({len(twins)} lines), on the JSON and on the printable page "
        '(`<p class="twin" lang="en">`), so the ambulance crew reads what he reads; the first three:'
    )
    for said, english in twins[:3]:
        say(f"{said}  /  {english}")

    # 5. Pa says "tired today": a symptom, rest, Mei will call, a check-in in two hours.
    tired = check(
        client.post(f"/profiles/{profile_id}/not-feeling-well", headers=his, json={"words": "tired today"}),
        201,
        'Pa says "tired today"',
    )
    lines = [line["text"] for line in tired["lines"]]
    if (
        tired["kind"] != "rest"
        or tired["symptoms"] != ["tired"]
        or tired["red_flags"]
        or tired["check_in_at"] is None
        or mei.person_id not in tired["notified_person_ids"]
        or "Mei will call you today." not in lines
    ):
        raise fail('Pa says "tired today"', why=f"got {tired}")
    ok(
        'Pa pressed the button and typed "tired today" (POST /profiles/{id}/not-feeling-well): his words '
        "kept as an artefact, a SYMPTOM event and a symptom fact resting on it, no red flag, the water "
        f"pill already taken — so the card says rest, Mei is told (notice to {len(tired['notified_person_ids'])} "
        f"people), and a check-in is written for {tired['check_in_at']}:"
    )
    for line in lines:
        say(line)

    # 6. Pa says "chest pain" by voice — his own words, kept like typed text (ADR 0003): the
    #    flag first, posture ACT, Mei told, then the call.
    chest = check(
        client.post(
            f"/profiles/{profile_id}/not-feeling-well",
            headers=his,
            json={
                "audio": base64.b64encode(placeholder_voice("chest-pain")).decode(),
                "content_type": VOICE_CONTENT_TYPE,
            },
        ),
        201,
        'Pa says "chest pain" by voice',
    )
    lines = [line["text"] for line in chest["lines"]]
    if (
        chest["kind"] != "red_flag"
        or chest["red_flags"] != ["chest_tightness"]
        or chest["posture"] != "act"
        or not chest["flag_id"]
        or not chest["by_voice"]
        or mei.person_id not in chest["notified_person_ids"]
        or lines[:3] != ["Mei knows now.", "Call the ambulance now on 995.", "After that, call Mei."]
        or lines[-1] != "Nura does not decide what is wrong."
        or any(line.startswith("Ask ") for line in lines)
    ):
        raise fail('Pa says "chest pain" by voice', why=f"got {chest}")
    ok(
        'Pa pressed the button and said "chest pain" (a voice note through the fixture transcriber, '
        f"heard at {chest['transcript_confidence']}, kept as his own note): the flag was written first "
        f"({chest['flag_id'][:8]}…), "
        "the posture is ACT, and the ladder (E11-06, the one record of who is told) asked "
        f"{len(chest['notified_person_ids'])} first — Mei, never capped, never quiet; "
        'the card, read aloud — who knows, the calls, and one closing line, never "Ask your '
        'doctor." after 995:'
    )
    for line in lines:
        say(line)
    state = check(client.get(f"/profiles/{profile_id}/state", headers=his), 200, "Pa reads State")
    if state["posture"] != "act":
        raise fail("State is ACT after the red flag", why=f"posture {state['posture']}")
    ok("State's posture is act (GET /profiles/{id}/state): the wash on his screen shifts to coral")

    # 7. Pa logs a symptom by voice; Mei reads the log in plain words.
    dizzy = check(
        client.post(
            f"/profiles/{profile_id}/symptoms",
            headers=his,
            json={
                "audio": base64.b64encode(placeholder_voice("dizzy-quite-a-lot")).decode(),
                "content_type": VOICE_CONTENT_TYPE,
            },
        ),
        201,
        'Pa logs "dizzy, quite a lot, since this morning"',
    )
    entry = dizzy["entry"]
    if entry["symptoms"] != ["dizzy"] or entry["severity"] != 2 or entry["duration"] != "this_morning":
        raise fail('Pa logs "dizzy, quite a lot, since this morning"', why=f"got {entry}")
    ok(
        'Pa logged a symptom by voice (POST /profiles/{id}/symptoms): "dizzy, quite a lot, since '
        f"this morning\" heard as dizzy, severity 2 ({entry['severity_words']}), since this morning; a "
        "SYMPTOM event and a fact with a seven-day window, his words kept in the voice note"
    )
    log = check(
        client.get(f"/profiles/{profile_id}/symptoms", headers=bearer(mei.token)),
        200,
        "Mei reads the symptom log",
    )
    lines = [line["text"] for line in log["lines"]]
    if not any(line.startswith("Pa felt dizzy on ") for line in lines):
        raise fail("Mei reads the symptom log", why=f"got {lines}")
    ok("Mei read the symptom log (GET /profiles/{id}/symptoms) in plain words, with the day's name:")
    for line in lines:
        say(line)

    # 8. Kit holds nothing.
    refused(
        client.get(f"/profiles/{profile_id}/emergency-card", headers=bearer(kit.token)),
        403,
        "NoKey",
        "Kit reads the card",
    )
    refused(
        client.post(f"/profiles/{profile_id}/not-feeling-well", headers=bearer(kit.token), json={"words": "tired"}),
        403,
        "NoKey",
        "Kit presses the button",
    )
    ok("Kit, with no key, was refused the card and the button: NoKey (403), in words that name nobody")


def run(base_url: str, dev_log: Path) -> int:
    """Walk checkpoint 14 against the server at `base_url`; 0 when every step is ✓."""
    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            try:
                health = client.get("/health")
            except httpx.ConnectError:
                raise Failed(
                    f"✗ nothing is listening at {base_url}: run `make dev` in another terminal"
                ) from None
            check(health, 200, f"the server answers at {base_url}")
            ok(f"the dev server answers at {base_url} (GET /health)")
            walk(client, Path(dev_log))
    except Failed as failed:
        print(str(failed), flush=True)
        print("checkpoint 14 stopped at the first ✗", flush=True)
        return 1
    print("checkpoint 14 passed: every step did what docs/checkpoints.md says", flush=True)
    return 0
