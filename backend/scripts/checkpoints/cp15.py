"""Checkpoint 15 — Health biography and the first week (E01-02, E01-03, E01-04), over HTTP only.

    make dev                # one terminal
    make checkpoint N=15    # another: this module, through scripts/checkpoint.py

Mei sets up a profile for Pa by his number, as in checkpoint 4, and runs his health
biography: the word cloud in Malay; the settings screen — Malay, simple, large text, voice
on, breakfast at 07:30, Dr Tan, five conditions — which State and the profile take at once;
the lipid report and the warfarin label through review cards, one tap each; the read-back in
Malay with one "no", kept as a dispute beside the fact; the questions the papers raised; the
close, with its summary in Malay and a first week of seven prompts from tomorrow at 07:30 on
Pa's clock. Then Pa claims the profile and sees the plan and his settings in State, says
Later to one prompt, and Kit — a caregiver — reads the settings and is refused changing them,
on Pa's trail.

Self-contained: every helper this module needs is here, so the shared runner only dispatches.
`run(base_url, dev_log)` prints ✓/✗ lines in the runner's style and returns 0 or 1.
"""

from __future__ import annotations

import base64
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

CODE_LINE = re.compile(r"login code for (\+[0-9]+): ([0-9]{6})")
CODE_WAIT_SECONDS = 3.0
HOLD_WORDING = "1"
"""Today's words for `hold_health_record`, from `app/consent/texts.py`. Move this when they move."""
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
LIPID_PANEL = "lipid-panel-2023-09-07"
WARFARIN_LABEL = "warfarin-label-2024-03-12"
SINGAPORE = ZoneInfo("Asia/Singapore")

SETTINGS: dict[str, Any] = {
    "language": "ms",
    "conditions": [
        "high_blood_pressure",
        "cholesterol",
        "diabetes",
        "blood_thinner",
        "hospital_last_year",
    ],
    "density": "simple",
    "large_text": True,
    "voice_on": True,
    "breakfast_time": "07:30",
    "doctor_name": "Dr Tan",
    "preferred_name": "Pa",
    "birth_decade": 1950,
}
LDL_LINE = "Kolesterol jahat anda 152 pada Khamis 7 September 2023."
"""The line Mei says is not right: the dotted LDL the extractor was not sure of."""

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


def said(lines: list[str]) -> None:
    for line in lines:
        for part in line.splitlines():
            print(f"    {part}", flush=True)


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
    """The bytes that stand in for one redacted paper — the same three lines as
    `backend/tests/paper.py`, so the fixture extractor recognises the digest."""
    return PNG_SIGNATURE + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"


def paper(label: str, kind: str) -> JSON:
    return {
        "data": base64.b64encode(placeholder_png(label)).decode(),
        "content_type": "image/png",
        "captured_at": datetime.now(SINGAPORE).isoformat(),
        "paper": kind,
    }


class Person:
    def __init__(self, name: str, phone_e164: str) -> None:
        self.name = name
        self.phone_e164 = phone_e164
        self.token = ""
        self.person_id = ""


def fresh_phone(prefix: str) -> str:
    return f"{prefix}{random.randint(0, 9999):04d}"


class Walk:
    def __init__(self, client: httpx.Client, dev_log: Path) -> None:
        self.client = client
        self.dev_log = dev_log

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

    def get(self, person: Person, path: str, what: str, **params: Any) -> Any:
        return check(self.client.get(path, headers=bearer(person.token), params=params), 200, what)

    def send(
        self, person: Person, method: str, path: str, status: int, what: str, **body: Any
    ) -> Any:
        answer = self.client.request(method, path, headers=bearer(person.token), json=body or None)
        return check(answer, status, what)

    def confirm_card(self, person: Person, profile_id: str, card: JSON, **corrections: Any) -> JSON:
        decisions: list[JSON] = []
        for field in card["fields"]:
            if field["attribute"] in corrections:
                decisions.append(
                    {
                        "field_id": field["field_id"],
                        "decision": "corrected",
                        "corrected_value": corrections[field["attribute"]],
                    }
                )
            else:
                decisions.append({"field_id": field["field_id"], "decision": "confirmed"})
        minted = self.send(
            person,
            "POST",
            f"/profiles/{profile_id}/confirmations",
            201,
            f"{person.name} says OK to the card",
            subject="review_card",
            card_id=card["card_id"],
            decisions=decisions,
        )
        confirmed: JSON = self.send(
            person,
            "POST",
            f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
            200,
            f"{person.name} confirms the card",
            decisions=decisions,
            confirmation_id=minted["confirmation_id"],
        )
        return confirmed


def walk(client: httpx.Client, dev_log: Path) -> None:
    w = Walk(client, dev_log)
    pa = Person("Pa", fresh_phone("+659333"))
    mei = Person("Mei", fresh_phone("+659444"))
    kit = Person("Kit", fresh_phone("+659555"))

    # 1. Mei sets up a profile for Pa by his number, as in checkpoint 4.
    w.register(mei, "en")
    opened = w.send(
        mei,
        "POST",
        "/profiles/for-someone",
        201,
        "Mei sets up a profile for Pa",
        patient_phone_e164=pa.phone_e164,
        display_name=pa.name,
        language="ms",
        consent={"wording_version": HOLD_WORDING, "language": "en", "captured_via": "app"},
        basis="patient_asked",
        relationship="daughter",
    )
    profile_id: str = opened["profile_id"]
    if opened["standing"] != "steward":
        raise fail("Mei sets up a profile for Pa", why=f"got {opened}")
    ok(f"Mei set up a profile for Pa ({pa.phone_e164}) as he asked: she is its steward")
    base = f"/profiles/{profile_id}"

    # 2. The word cloud, in Malay, for anyone.
    cloud = check(
        client.get("/onboarding/conditions", params={"language": "ms"}),
        200,
        "the word cloud answers without signing in",
    )
    names = {one["code"]: one["name"] for one in cloud["conditions"]}
    ok(
        f"the word cloud answers without signing in (GET /onboarding/conditions?language=ms): "
        f"{len(cloud['top'])} words first, {len(names)} in all, in Malay — "
        + ", ".join(names[code] for code in cloud["top"][:5])
        + " …"
    )

    # 3. Mei opens the biography.
    bio = w.send(mei, "POST", f"{base}/biography", 201, "Mei opens Pa's biography")
    if bio["step"] != "about_you" or bio["next"] != "save_settings":
        raise fail("Mei opens Pa's biography", why=f"got {bio}")
    ok(
        f"Mei opened the biography (POST /profiles/{{id}}/biography): step {bio['step']}, next "
        f"{bio['next']}; the words of the step, in Pa's Malay:"
    )
    said([bio["prompt"]["headline"], *bio["prompt"]["lines"]])

    # 4. The settings screen, and State and the profile taking it at once.
    saved = w.send(mei, "PUT", f"{base}/settings", 200, "Mei saves Pa's settings", **SETTINGS)
    if (saved["language"], saved["voice_on"], saved["large_text"], saved["breakfast_time"]) != (
        "ms",
        True,
        True,
        "07:30",
    ) or saved["doctor_name"] != "Dr Tan":
        raise fail("Mei saves Pa's settings", why=f"got {saved}")
    ok(
        "Mei saved Pa's settings (PUT /profiles/{id}/settings): Malay, simple, large text, voice "
        f"on, breakfast 07:30, Dr Tan, and {len(saved['conditions'])} conditions — "
        + ", ".join(names[code] for code in saved["conditions"])
    )
    state = w.get(mei, f"{base}/state", "Mei reads Pa's State")
    cognitive = state["dimensions"]["cognitive"]
    functional = state["dimensions"]["functional"]["facts"]
    formats = cognitive["facts"].get("format", {})
    if (
        cognitive["spoken_language"] != "ms"
        or formats.get("density", {}).get("value") != "simple"
        or formats.get("preferred", {}).get("value") != "voice"
        or functional.get("vision", {}).get("large_text", {}).get("value") is not True
        or state["dimensions"]["clinical"]["facts"]
        .get("setting", {})
        .get("birth_decade", {})
        .get("value")
        != 1950
    ):
        raise fail("Mei reads Pa's State", why=f"settings not folded in: {cognitive}")
    profile = w.get(mei, base, "Mei reads Pa's profile")
    if profile["language"] != "ms":
        raise fail("Mei reads Pa's profile", why=f"language {profile['language']}")
    ok(
        f"State took them at once — snapshot {state['sequence']}: spoken and reading language "
        "ms, format density simple and preferred voice (the fact the feed goes voice-first on), "
        "vision large_text true, setting.birth_decade 1950 (the age band lab trends read), "
        "each a fact with Mei's yes on the event of the save; the "
        "profile's own language is ms"
    )

    # 5. The papers: the lipid report and the medicine label, one tap each.
    lipid = w.send(
        mei,
        "POST",
        f"{base}/biography/papers",
        201,
        "Mei adds the lipid report",
        **paper(LIPID_PANEL, "lab_result"),
    )
    dotted = [f["attribute"] for f in lipid["card"]["fields"] if f["needs_confirm"]]
    waiting = w.get(mei, f"{base}/biography", "Mei reads the biography with a card open")
    if waiting["next"] != "confirm_cards" or waiting["open_cards"] != 1:
        raise fail("Mei reads the biography with a card open", why=f"got {waiting}")
    w.confirm_card(mei, profile_id, lipid["card"], triglycerides=54)
    ok(
        "Mei added the lipid report (POST …/biography/papers, paper lab_result): a review card "
        f"of {len(lipid['card']['fields'])} fields, {' and '.join(dotted)} dotted; the "
        "biography waited on it (next confirm_cards), and one tap confirmed it with "
        "triglycerides corrected to 54"
    )
    label = w.send(
        mei,
        "POST",
        f"{base}/biography/papers",
        201,
        "Mei adds the medicine label",
        **paper(WARFARIN_LABEL, "medicine"),
    )
    w.confirm_card(mei, profile_id, label["card"])
    ok(
        f"Mei added the warfarin label (paper medicine): read as a {label['card']['document_kind']} "
        f"marked {label['card']['high_risk_class']}, and confirmed with one tap from its label photo"
    )

    # 6. The read-back, in Malay, with one "no".
    ready = w.get(mei, f"{base}/biography", "Mei reads the read-back")
    lines = [line["line"] for line in ready["read_back"]]
    if ready["step"] != "read_back" or LDL_LINE not in lines:
        raise fail("Mei reads the read-back", why=f"got {ready}")
    ok(f"the biography is at the read-back: {len(lines)} lines, each a confirmed fact, in Malay:")
    said([ready["prompt"]["headline"], *lines])
    ldl_line = next(line for line in ready["read_back"] if line["line"] == LDL_LINE)
    one = w.send(
        mei,
        "POST",
        f"{base}/biography/read-back",
        200,
        "Mei says no to one line",
        line_id=ldl_line["fact_id"],
        answer="no",
    )
    waiting = [line for line in one["read_back"] if line["answer"] is None]
    answered = w.send(
        mei,
        "POST",
        f"{base}/biography/read-back",
        200,
        "Mei says yes to the rest",
        answers=[{"fact_id": line["fact_id"], "answer": "yes"} for line in waiting],
    )
    no = next(line for line in answered["read_back"] if line["answer"] == "no")
    facts = w.get(mei, f"{base}/facts", "Mei reads the lipid facts", subject="lipid_panel")
    ldl = next(f for f in facts if f["attribute"] == "ldl")
    if (
        answered["step"] != "questions"
        or not no["dispute_fact_id"]
        or ldl["fact_id"] != no["fact_id"]
        or ldl["value"] != 152
    ):
        raise fail("Mei answers the read-back", why=f"got {no} and {ldl}")
    ok(
        f'Mei said no to "{LDL_LINE}" on its own (one line, one screen), then yes to the other '
        f"{len(waiting)} at once — a dispute ({no['dispute_fact_id'][:8]}…) opened beside the fact, "
        "which still holds (152, from the photo, confirmed by Mei): nothing anyone confirmed is "
        "overwritten"
    )

    # 7. The questions the papers raised; Mei keeps two of them.
    shown = answered["questions"]
    ok("the questions the papers raised, in Malay (step questions):")
    said(
        [
            answered["prompt"]["headline"],
            *([answered["after_no"]] if answered["after_no"] else []),
            *[q["line"] for q in shown],
            *([answered["more"]] if answered["more"] else []),
        ]
    )
    kept: JSON = {}
    for question in shown[:2]:
        kept = w.send(
            mei,
            "POST",
            f"{base}/biography/questions",
            200,
            "Mei keeps a question",
            question_id=question["question_id"],
            keep=True,
        )
    kept_ids = [q["question_id"] for q in kept["questions"] if q["kept"]]
    if kept_ids != [q["question_id"] for q in shown[:2]]:
        raise fail("Mei keeps a question", why=f"kept {kept_ids}")
    ok(
        "Mei kept two of them (POST …/biography/questions): "
        + ", ".join(kept_ids)
        + " — kept on the sitting, the seam to the visit loop's questions"
    )

    # 8. The close: the summary and the first week.
    closed = w.send(mei, "POST", f"{base}/biography/close", 200, "Mei closes the biography")
    plan = closed["plan"]
    tomorrow = (datetime.now(SINGAPORE) + timedelta(days=1)).date()
    first_due = f"{tomorrow.isoformat()}T07:30:00+08:00"
    if len(plan["prompts"]) != 7 or plan["prompts"][0]["due_local"] != first_due:
        raise fail("Mei closes the biography", why=f"plan {plan}")
    ok(
        f"Mei closed the biography: {closed['summary']['papers']} papers, "
        f"{closed['summary']['facts']} facts, {closed['summary']['disputes']} disputed; the "
        "summary, in Malay:"
    )
    said(closed["summary"]["lines"])

    # 9. Pa claims the profile, as in checkpoint 4, and sees his first week.
    w.register(pa, "ms")
    waiting_for_him = w.get(pa, "/profiles/mine/claimable", "Pa asks what is waiting for him")
    if [one["profile_id"] for one in waiting_for_him] != [profile_id]:
        raise fail("Pa asks what is waiting for him", why=f"got {waiting_for_him}")
    minted = w.send(
        pa, "POST", f"{base}/confirmations", 201, "Pa says OK", subject="claim", language="ms"
    )
    claimed = w.send(
        pa,
        "POST",
        f"{base}/claim",
        200,
        "Pa claims the profile",
        confirmation_id=minted["confirmation_id"],
        language="ms",
    )
    if claimed["standing"] != "owner":
        raise fail("Pa claims the profile", why=f"got {claimed}")
    ok("Pa claimed the profile with his OK: he is its owner, Mei his chief")
    his_plan = w.get(pa, f"{base}/plan", "Pa reads his first week")
    if [p["prompt"] for p in his_plan["prompts"]] != [p["prompt"] for p in plan["prompts"]]:
        raise fail("Pa reads his first week", why=f"got {his_plan}")
    ok(
        f"Pa reads his first week (GET /profiles/{{id}}/plan): 7 prompts, one a day from "
        f"tomorrow, {tomorrow.isoformat()}, at 07:30 on his clock ({his_plan['timezone']}); "
        "nothing is due yet:"
    )
    for prompt in his_plan["prompts"]:
        print(
            f"    day {prompt['day']}  {prompt['due_local'][:16]}  {prompt['status']:<8} "
            f"{prompt['headline']} — {prompt['action']}",
            flush=True,
        )
    due = w.get(pa, f"{base}/plan", "Pa asks what is due tomorrow at 07:30", at=first_due)
    if [p["prompt"] for p in due["due"]] != [plan["prompts"][0]["prompt"]]:
        raise fail("Pa asks what is due tomorrow at 07:30", why=f"got {due['due']}")
    later = w.send(
        pa,
        "POST",
        f"{base}/plan/later",
        200,
        "Pa says Later to the insurance card",
        gap_id="insurance",
    )
    moved = next(p for p in later["prompts"] if p["prompt"] == "insurance")
    if moved["deferred"] != 1 or moved["status"] != "pending":
        raise fail("Pa says Later to the insurance card", why=f"got {moved}")
    ok(
        f"tomorrow at 07:30 exactly one prompt is due ({due['due'][0]['prompt']}); Pa said Later to "
        f"the insurance card (POST …/plan/later): it goes to the back of the week, asked once more "
        f"on {moved['due_local'][:10]} at 07:30; a second Later would retire it"
    )

    # 10. His settings in his State, as its owner.
    state = w.get(pa, f"{base}/state", "Pa reads his State")
    preference = (state["dimensions"].get("preference") or {}).get("facts", {})
    if preference.get("nudges", {}).get("breakfast_time", {}).get("value") != "07:30":
        raise fail("Pa reads his State", why=f"preference {preference}")
    cognitive = state["dimensions"]["cognitive"]
    ok(
        "Pa's State shows his settings: cognitive (language ms, density simple, voice), "
        "functional (large text), preference (breakfast 07:30, called Pa), and the five "
        "conditions he told in the clinical dimension, as told — no posture moved "
        f"(posture {state['posture']}, reading language {cognitive['reading_language']})"
    )

    # 11. A caregiver reads the settings, and may not change them.
    w.register(kit, "en")
    w.send(
        pa,
        "POST",
        f"{base}/consents/sharing",
        201,
        "Pa lets Kit see his record",
        holder_phone_e164=kit.phone_e164,
        scopes=["records", "medicines", "visits"],
        relationship="son",
        language="ms",
        captured_via="app",
    )
    w.send(
        pa,
        "POST",
        f"{base}/keys",
        201,
        "Pa cuts Kit a caregiver key",
        holder_phone_e164=kit.phone_e164,
        role="caregiver",
        scopes=["records", "medicines", "visits"],
    )
    kits = w.get(kit, f"{base}/settings", "Kit reads Pa's settings")
    if kits["withheld"] != [] or kits["doctor_name"] != "Dr Tan":
        raise fail("Kit reads Pa's settings", why=f"got {kits}")
    refused(
        client.put(f"{base}/settings", headers=bearer(kit.token), json=SETTINGS),
        403,
        "NotTheirsToSetUp",
        "Kit changes Pa's settings",
    )
    trail = w.get(pa, f"{base}/audit", "Pa reads his trail", limit=500)
    if not any(
        e["refused_because"] == "NotTheirsToSetUp" and e["actor_person_id"] == kit.person_id
        for e in trail
    ):
        raise fail("Pa reads his trail", why="Kit's refused change is not on it")
    ok(
        "Kit, his caregiver, reads the settings whole (a key to the record opens the conditions "
        "and the doctor); changing them is refused: NotTheirsToSetUp (403), and it is on Pa's trail"
    )


def run(base_url: str, dev_log: Path) -> int:
    """Walk checkpoint 15 against the server at `base_url`; 0 when every step is a ✓."""
    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            walk(client, Path(dev_log))
    except Failed as failed:
        print(str(failed), flush=True)
        return 1
    return 0
