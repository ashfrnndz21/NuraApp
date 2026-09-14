"""The WhatsApp routes over HTTP: the webhook's handshake and signature, the dev door that
drives the channel without a provider, and the thread as its owner reads it."""

from __future__ import annotations

import json
from typing import Any

from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591110001"
MEI = "+6591110002"
KIT = "+6591110003"



def _words_in(payload: object) -> str:
    """Every string value in a response except ids and times, joined.

    "No words by reference" means no value a person wrote comes back; ids and
    timestamps are random or clock-derived and may contain any digits.
    """
    out: list[str] = []

    def walk(node: object, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, (str, int, float)) and not (
            key == "id" or key.endswith("_id") or key.endswith("_at") or key in {"at", "sha256"}
        ):
            out.append(str(node))

    walk(payload)
    return " ".join(out)

async def _pa_on_whatsapp(deployment: Deployment) -> tuple[dict[str, str], str, dict[str, str]]:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(
        deployment, pa, profile_id, MEI, ["medicines", "readings", "records", "family", "send"]
    )
    key = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "chief"},
        headers=bearer(pa["token"]),
    )
    assert key.status_code == 201, key.text
    agreed = await deployment.client.post(
        f"/profiles/{profile_id}/consents/whatsapp",
        json={"language": "en", "captured_via": "app"},
        headers=bearer(pa["token"]),
    )
    assert agreed.status_code == 201, agreed.text
    assert agreed.json()["purpose"] == "whatsapp" and agreed.json()["basis"] == "owner"
    # Only the owner agrees for himself; the chief cannot on this route.
    hers = await deployment.client.post(
        f"/profiles/{profile_id}/consents/whatsapp",
        json={"language": "en", "captured_via": "app"},
        headers=bearer(mei["token"]),
    )
    assert hers.status_code == 403 and hers.json() == {"refusal": "NotTheirConsentToGive"}
    return pa, profile_id, mei


def _cloud_api_text(from_e164: str, text: str) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": from_e164.lstrip("+"),
                                    "id": "wamid.test.1",
                                    "timestamp": "1788768000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ]
                        }
                    }
                ]
            }
        ],
    }


async def test_the_handshake_echoes_the_challenge_for_our_token_only(
    deployment: Deployment,
) -> None:
    ok = await deployment.client.get(
        "/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "nura-test-webhook-secret",
            "hub.challenge": "12345",
        },
    )
    assert ok.status_code == 200 and ok.text == "12345"
    wrong = await deployment.client.get(
        "/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "guess", "hub.challenge": "1"},
    )
    assert wrong.status_code == 403 and wrong.json() == {"refusal": "NotAWebhook"}


async def test_an_unsigned_webhook_is_refused_and_a_signed_one_walks_the_thread(
    deployment: Deployment,
) -> None:
    await _pa_on_whatsapp(deployment)
    body = json.dumps(_cloud_api_text(MEI, "BP 150/90 this morning")).encode()
    unsigned = await deployment.client.post(
        "/whatsapp/webhook", content=body, headers={"content-type": "application/json"}
    )
    assert unsigned.status_code == 403 and unsigned.json() == {"refusal": "NotAWebhook"}
    forged = await deployment.client.post(
        "/whatsapp/webhook",
        content=body,
        headers={"content-type": "application/json", "X-Hub-Signature-256": "sha256=00"},
    )
    assert forged.status_code == 403
    assert deployment.whatsapp.sent == []

    signed = await deployment.client.post(
        "/whatsapp/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "X-Hub-Signature-256": deployment.whatsapp.sign(body),
        },
    )
    assert signed.status_code == 200 and signed.json() == {"handled": 1}
    assert len(deployment.whatsapp.sent) == 1
    assert deployment.whatsapp.sent[0].to_e164 == MEI
    assert deployment.whatsapp.sent[0].text.startswith("Did I get this right?")
    # Nothing about what was said is on the wire back to the provider.
    assert "150" not in _words_in(signed.json())


async def test_the_dev_door_drives_the_same_path_and_the_owner_reads_the_thread(
    deployment: Deployment,
) -> None:
    pa, profile_id, mei = await _pa_on_whatsapp(deployment)
    heard = await deployment.client.post(
        "/dev/whatsapp/inbound", json={"from_e164": MEI, "text": "BP 150/90 this morning"}
    )
    assert heard.status_code == 200, heard.text
    assert heard.json()["outcome"] == "proposal", heard.text
    assert heard.json()["proposal_id"]
    yes = await deployment.client.post(
        "/dev/whatsapp/inbound", json={"from_e164": MEI, "text": "yes"}
    )
    assert yes.json()["outcome"] == "confirmed" and yes.json()["fact_id"]
    facts = await deployment.client.get(
        f"/profiles/{profile_id}/facts",
        params={"subject": "blood_pressure"},
        headers=bearer(pa["token"]),
    )
    assert [f["value"] for f in facts.json()] == [{"systolic": 150, "diastolic": 90}]
    assert facts.json()[0]["confirmed_by_person_id"] == mei["person_id"]

    thread = await deployment.client.get(
        f"/profiles/{profile_id}/whatsapp/thread", headers=bearer(pa["token"])
    )
    assert thread.status_code == 200, thread.text
    # The clock is frozen in the tests, so the four share one moment; the set is the check.
    kinds = sorted((m["direction"], m["kind"]) for m in thread.json())
    assert kinds == [
        ("inbound", "answer"),
        ("inbound", "health_event"),
        ("outbound", "reply"),
        ("outbound", "reply"),
    ]
    assert all(m["artifact_id"] for m in thread.json() if m["direction"] == "inbound")
    assert "150" not in _words_in(thread.json())  # by reference, never the words
    # The chief reads it too; a stranger to the profile cannot.
    as_mei = await deployment.client.get(
        f"/profiles/{profile_id}/whatsapp/thread", headers=bearer(mei["token"])
    )
    assert as_mei.status_code == 200
    kit = await register_by_phone(deployment, KIT, "Kit")
    refused = await deployment.client.get(
        f"/profiles/{profile_id}/whatsapp/thread", headers=bearer(kit["token"])
    )
    assert refused.status_code == 403 and refused.json() == {"refusal": "NoKey"}


async def test_a_stranger_through_the_dev_door_and_the_morning_card(deployment: Deployment) -> None:
    pa, profile_id, _ = await _pa_on_whatsapp(deployment)
    stranger = await deployment.client.post(
        "/dev/whatsapp/inbound", json={"from_e164": KIT, "text": "BP 150/90"}
    )
    assert stranger.json()["outcome"] == "unknown_number"
    assert stranger.json()["stranger_reply"].startswith("Hello, this is Nura.")
    assert stranger.json()["profile_id"] is None

    morning = await deployment.client.post(f"/dev/whatsapp/morning/{profile_id}")
    assert morning.status_code == 200, morning.text
    assert (
        morning.json()["kind"] == "template" and morning.json()["template_name"] == "morning_card"
    )
    assert morning.json()["text"].startswith("Good morning, Pa, this is Nura.")
    outbox = await deployment.client.get("/dev/whatsapp/outbox")
    assert [s["to_e164"] for s in outbox.json()] == [KIT, PA]
    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", headers=bearer(pa["token"]), params={"action": "share"}
    )
    shares = [e for e in trail.json() if e["channel"] == "whatsapp"]
    assert len(shares) == 1 and shares[0]["shared_with_person_id"] == pa["person_id"]
