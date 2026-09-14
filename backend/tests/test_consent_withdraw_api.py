"""E00-02 over HTTP: the owner stops one agreement from the app, and keeps the record.

    Consent event stored with timestamp, scope and version; revocation removes access
    within a minute.

The service-level acceptance is `tests/test_consent_acceptance.py`. These are the routes the
web client calls: the confirm step's words (`GET /consents/{id}/withdrawal`), the withdrawal
(`POST /consents/{id}/withdraw`), and the printable record (`GET /consents/record.html`). And
the promise the delivery engine keeps with them: nothing still waiting to be sent reaches a
key closed by a withdrawal. Plus E12-06's state: what became of a message to him.
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.consent.models import ConsentChannel, ConsentPurpose
from app.consent.service import withdraw_consent
from app.consent.texts import current_version
from app.consent.withdrawal import STOP_LINES, STOPPED, STOPPED_LINES, stop_lines
from app.delivery.triggers.models import DeliveryOutcome, Ladder, TriggerType
from app.safety.plain_words import verify
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.delivery_support import home
from tests.family_support import MONDAY
from tests.test_ladder import _of, _run, at

PA, MEI, KIT = "+6591118801", "+6592228802", "+6595558803"
EVERYTHING = [
    "medicines", "visits", "readings", "records", "notes", "money", "family", "emergency",
    "ask", "send",
]


async def _household(deployment: Deployment) -> tuple[dict[str, str], dict[str, str], dict[str, str], str]:
    """Pa, in Malay; Mei his chief; Kit his son with a caregiver key to the medicines."""
    pa = await register_by_phone(deployment, PA, "Pa", "ms")
    mei = await register_by_phone(deployment, MEI, "Mei", "en")
    kit = await register_by_phone(deployment, KIT, "Kit", "en")
    profile_id = await own_profile(deployment, pa, display_name="Pa", language="ms")
    await let_in(deployment, pa, profile_id, MEI, EVERYTHING, "daughter")
    await let_in(deployment, pa, profile_id, KIT, ["medicines"], "son", holder_display_name="Kit")
    for who, role in ((mei, "chief"), (kit, "caregiver")):
        cut = await deployment.client.post(
            f"/profiles/{profile_id}/keys",
            json={"holder_person_id": who["person_id"], "role": role},
            headers=bearer(pa["token"]),
        )
        assert cut.status_code == 201, cut.text
    return pa, mei, kit, profile_id


async def _sharing_with(deployment: Deployment, pa: dict[str, str], profile_id: str, person_id: str) -> str:
    listed = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=bearer(pa["token"]))
    assert listed.status_code == 200, listed.text
    (found,) = [
        row["consent_id"]
        for row in listed.json()
        if row["purpose"] == "share_with_family"
        and row["holder_person_id"] == person_id
        and row["revoked_at"] is None
    ]
    return str(found)


async def _refusals(deployment: Deployment, pa: dict[str, str], profile_id: str) -> list[str]:
    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", headers=bearer(pa["token"]), params={"limit": 500}
    )
    assert trail.status_code == 200, trail.text
    return [row["refused_because"] for row in trail.json() if row["outcome"] == "refused"]


async def test_the_owner_stops_letting_kit_in_and_kits_key_closes_at_once(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    client = deployment.client
    pa, _mei, kit, profile_id = await _household(deployment)
    assert (await client.get(f"/profiles/{profile_id}/medicines", headers=bearer(kit["token"]))).status_code == 200
    consent_id = await _sharing_with(deployment, pa, profile_id, kit["person_id"])

    # The confirm step: what stopping will do, in his words (Malay, his language), by name.
    asked = await client.get(
        f"/profiles/{profile_id}/consents/{consent_id}/withdrawal", headers=bearer(pa["token"])
    )
    assert asked.status_code == 200, asked.text
    assert asked.json()["purpose"] == "share_with_family"
    assert asked.json()["lines"] == [
        "Jika anda hentikan ini, Kit tidak boleh melihat surat-surat anda.",
        "Kit berhenti melihatnya serta-merta.",
        "Anda boleh benarkan Kit masuk semula nanti.",
    ]
    english = await client.get(
        f"/profiles/{profile_id}/consents/{consent_id}/withdrawal",
        params={"language": "en"},
        headers=bearer(pa["token"]),
    )
    assert english.json()["lines"][0] == "If you stop this, Kit cannot see your papers."

    # Asking is not stopping: Kit still reads.
    assert (await client.get(f"/profiles/{profile_id}/medicines", headers=bearer(kit["token"]))).status_code == 200

    stopped = await client.post(
        f"/profiles/{profile_id}/consents/{consent_id}/withdraw",
        json={"captured_via": "app", "language": "en"},
        headers=bearer(pa["token"]),
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["lines"] == ["You stopped this.", "Kit cannot see your papers now."]
    (row,) = stopped.json()["withdrawn"]
    assert row["consent_id"] == consent_id and row["revoked_at"] is not None
    assert row["revoked_by_person_id"] == pa["person_id"]

    # Access is gone the same second, not within the minute: the key closed with the consent.
    refused = await client.get(f"/profiles/{profile_id}/medicines", headers=bearer(kit["token"]))
    assert refused.status_code == 403 and refused.json()["refusal"] == "NoKey"
    keys = await client.get(f"/profiles/{profile_id}/keys", headers=bearer(pa["token"]))
    kits = [key for key in keys.json() if key["holder_person_id"] == kit["person_id"]]
    assert kits and all(key["revoked_at"] is not None for key in kits)

    # The row stays, marked; a second stop has nothing to stop.
    again = await client.post(
        f"/profiles/{profile_id}/consents/{consent_id}/withdraw", json={}, headers=bearer(pa["token"])
    )
    assert again.status_code == 404 and again.json()["refusal"] == "NoConsentToWithdraw"
    gone = await client.get(
        f"/profiles/{profile_id}/consents/{consent_id}/withdrawal", headers=bearer(pa["token"])
    )
    assert gone.status_code == 404 and gone.json()["refusal"] == "NoConsentToWithdraw"

    # On his trail: the agreement and the key written, as sentences he can read.
    trail = await client.get(f"/profiles/{profile_id}/trail", params={"language": "en"}, headers=bearer(pa["token"]))
    said = [s for day in trail.json() for line in day["lines"] for s in line["sentences"]]
    assert any("what you agreed to" in sentence for sentence in said), said


async def test_stopping_is_the_owners_alone_and_every_refusal_is_on_his_trail(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    client = deployment.client
    pa, mei, kit, profile_id = await _household(deployment)
    consent_id = await _sharing_with(deployment, pa, profile_id, kit["person_id"])
    for path, method in (("withdrawal", "GET"), ("withdraw", "POST")):
        url = f"/profiles/{profile_id}/consents/{consent_id}/{path}"
        hers = await client.request(method, url, headers=bearer(mei["token"]), json=None if method == "GET" else {})
        assert hers.status_code == 403 and hers.json()["refusal"] == "NotTheirConsentToWithdraw"
        # Kit's own key does not open the family list at all.
        his = await client.request(method, url, headers=bearer(kit["token"]), json=None if method == "GET" else {})
        assert his.status_code == 403 and his.json()["refusal"] == "OutOfScope"
    assert _refusals_of(await _refusals(deployment, pa, profile_id)) >= {"NotTheirConsentToWithdraw", "OutOfScope"}
    # Nothing was stopped: Kit still reads.
    assert (await client.get(f"/profiles/{profile_id}/medicines", headers=bearer(kit["token"]))).status_code == 200
    # An id that is not an agreement on this profile is nothing to stop.
    stray = await client.get(
        f"/profiles/{profile_id}/consents/{pa['person_id']}/withdrawal", headers=bearer(pa["token"])
    )
    assert stray.status_code == 404 and stray.json()["refusal"] == "NoConsentToWithdraw"


def _refusals_of(names: list[str]) -> set[str]:
    return set(names)


async def test_the_record_is_one_printable_page_his_and_his_chiefs(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    client = deployment.client
    pa, mei, kit, profile_id = await _household(deployment)
    consent_id = await _sharing_with(deployment, pa, profile_id, kit["person_id"])
    stopped = await client.post(
        f"/profiles/{profile_id}/consents/{consent_id}/withdraw", json={}, headers=bearer(pa["token"])
    )
    assert stopped.status_code == 200, stopped.text

    page = await client.get(f"/profiles/{profile_id}/consents/record.html", headers=bearer(pa["token"]))
    assert page.status_code == 200, page.text
    assert page.headers["content-type"].startswith("text/html")
    assert page.headers["cache-control"] == "private, no-store"
    html = page.text
    # Self-contained: nothing fetched, nothing run.
    assert "<script" not in html and "http://" not in html and "https://" not in html
    assert "<link" not in html and "<img" not in html
    assert "<h1>What you said yes to</h1>" in html
    assert "<h2>Who can see your papers</h2>" in html
    # Every agreement, the stopped one included, with who stopped it and when.
    assert "You stopped this one on Monday 14 September 2026." in html
    assert "This one is still on." in html
    # The words he read, in the language he read them.
    assert "Kit can no longer see these parts:" in html and "<li>your medicines</li>" in html
    # Nothing but the lines: every paragraph is a line of the record, escaped.
    assert not re.search(r"<p>\s*</p>", html)

    # His chief reads it too, addressed to her; a key without the family list does not.
    hers = await client.get(f"/profiles/{profile_id}/consents/record.html", headers=bearer(mei["token"]))
    assert hers.status_code == 200 and "What Pa said yes to" in hers.text
    kits = await client.get(f"/profiles/{profile_id}/consents/record.html", headers=bearer(kit["token"]))
    assert kits.status_code == 403

    # The page leaving is a share on his trail.
    audit = await client.get(f"/profiles/{profile_id}/audit", headers=bearer(pa["token"]), params={"limit": 500})
    shares = [row for row in audit.json() if row["action"] == "share" and row["target"] == "consent_record"]
    assert len(shares) == 2


async def test_a_name_on_the_record_is_printed_as_words_never_as_markup(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    pa = await register_by_phone(deployment, PA, "Pa <b>Tan</b>", "en")
    profile_id = await own_profile(deployment, pa, display_name="Pa <b>Tan</b>", language="en")
    page = await deployment.client.get(f"/profiles/{profile_id}/consents/record.html", headers=bearer(pa["token"]))
    assert page.status_code == 200
    assert "<b>" not in page.text


async def test_a_message_to_him_says_scheduled_then_sent_or_not_sent(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """E12-06 with E11: the state is the delivery log's, never the client's guess."""
    clock.set(MONDAY)
    client = deployment.client
    pa, mei, _kit, profile_id = await _household(deployment)
    agreed = await client.post(
        f"/profiles/{profile_id}/consents/whatsapp",
        json={"wording_version": current_version(ConsentPurpose.WHATSAPP), "language": "ms", "captured_via": "app"},
        headers=bearer(pa["token"]),
    )
    assert agreed.status_code == 201, agreed.text

    async def schedule(hours: int, lasting: int) -> str:
        compose = {"template_id": "pickup", "slots": {"who": "Mei", "when": "pukul 9"}}
        when = {
            "send_at": (MONDAY + timedelta(hours=hours)).isoformat(),
            "channel": "whatsapp",
            "expires_at": (MONDAY + timedelta(hours=hours + lasting)).isoformat(),
        }
        minted = await client.post(
            f"/profiles/{profile_id}/confirmations",
            json={"subject": "push", **compose, **when},
            headers=bearer(mei["token"]),
        )
        assert minted.status_code == 201, minted.text
        made = await client.post(
            f"/profiles/{profile_id}/pushes",
            json={**compose, **when, "confirmation_id": minted.json()["confirmation_id"]},
            headers=bearer(mei["token"]),
        )
        assert made.status_code == 201, made.text
        push_id: str = made.json()["push_id"]
        return push_id

    soon = await schedule(1, 4)
    brief = await schedule(1, 1)

    def states(body: list[dict[str, object]]) -> dict[object, tuple[object, object]]:
        return {row["push_id"]: (row["state"], row["sent_at"]) for row in body}

    listed = await client.get(f"/profiles/{profile_id}/pushes", headers=bearer(mei["token"]))
    assert states(listed.json()) == {soon: ("scheduled", None), brief: ("scheduled", None)}

    # Its moment comes and the engine runs: sent to him on WhatsApp, and the list says so.
    clock.set(MONDAY + timedelta(hours=1, minutes=5))
    ran = await client.post("/dev/run-triggers", json={"profile_id": profile_id})
    assert ran.status_code == 200, ran.text
    listed = await client.get(f"/profiles/{profile_id}/pushes", headers=bearer(mei["token"]))
    now = states(listed.json())
    # The cap on family messages is two a day, so both went; each is "sent" with its moment.
    assert now[soon][0] == "sent" and now[soon][1] is not None
    assert now[brief][0] == "sent"

    # One more, never delivered before its end: "not_sent".
    late = await schedule(6, 1)
    clock.set(MONDAY + timedelta(hours=8))
    listed = await client.get(f"/profiles/{profile_id}/pushes", headers=bearer(mei["token"]))
    assert states(listed.json())[late] == ("not_sent", None)


async def test_nothing_waiting_on_the_ladder_reaches_a_key_closed_by_a_withdrawal(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """The breakfast tablet's ladder names Siti for its second rung. Pa stops letting her in
    before her rung comes due: her rung is held as not covered, nothing reaches her, and the
    ladder climbs on to the roster."""
    clock.set(at(6))
    h = await home(sg, tmp_path)
    first = await _run(sg, h, clock, at(8, 31))
    assert _of(first, TriggerType.DOSE) == [(h.pa.id, 0, DeliveryOutcome.SENT)]
    ladder = (await sg.scalars(select(Ladder))).one()
    assert [step["standing"] for step in ladder.rungs] == ["patient", "helper", "on_duty"]

    clock.set(at(8, 40))
    sitis = [
        row
        for row in await _consents(sg, h)
        if row.purpose is ConsentPurpose.SHARE_WITH_PERSON and row.holder_person_id == h.siti.id
    ]
    _row, withdrawn = await withdraw_consent(
        sg, context=h.owner, consent_id=sitis[0].id, captured_via=ConsentChannel.APP
    )
    assert withdrawn

    second = await _run(sg, h, clock, at(9, 1))
    assert _of(second, TriggerType.DOSE) == [(h.siti.id, 1, DeliveryOutcome.NO_SCOPE)]
    assert h.sent_to(h.siti) == []
    third = await _run(sg, h, clock, at(9, 31))
    assert _of(third, TriggerType.DOSE) == [(h.mei.id, 2, DeliveryOutcome.SENT)]
    assert h.sent_to(h.siti) == []


async def _consents(sg: AsyncSession, h: object) -> list:  # type: ignore[type-arg]
    from app.consent.service import all_consents

    return list(await all_consents(sg, context=h.owner))  # type: ignore[attr-defined]


def test_every_agreement_has_its_words_in_every_language_and_they_are_plain() -> None:
    for language in ("en", "ms", "zh"):
        assert set(STOP_LINES[language]) == set(ConsentPurpose)
        assert set(STOPPED_LINES[language]) == set(ConsentPurpose)
        lines = [STOPPED[language]]
        for purpose in ConsentPurpose:
            lines += stop_lines(purpose, name="Ash", language=language)
            lines.append(STOPPED_LINES[language][purpose].format(name="Ash"))
        for line in lines:
            failures = [f for f in verify(line, language, "line") if f.severity == "fail"]
            assert failures == [], (language, line, failures)
    # A language Nura does not speak is English, never a gap.
    assert stop_lines(ConsentPurpose.CALENDAR, name="", language="ta") == list(
        STOP_LINES["en"][ConsentPurpose.CALENDAR]
    )
