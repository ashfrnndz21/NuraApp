"""Web Push to the home-screen app (ADR 0001): the real sender behind the push port.

The payload is encrypted with Mozilla's `http_ece` (RFC 8291) and every request is signed
with Mozilla's `py_vapid` (RFC 8292); the RFC's own worked example holds the first, and a
token checked with the public key holds the second. Then the sender behind the trigger
engine, against a push service in the test (`httpx.MockTransport`): a reorder reaches Mei's
phone as the one content-free line and an id, and nothing else; the quiet hours hold it; a
push service that has forgotten the phone (410) drops the subscription and the send goes by
WhatsApp; a phone signed out gets nothing. And the door: a phone subscribes and unsubscribes
over HTTP, under the profile, per login session.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, replace
from datetime import time, timedelta
from pathlib import Path

import http_ece  # type: ignore[import-untyped]
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid02  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.push import (
    BadVapidKeys,
    FixturePush,
    NoDevices,
    WebPush,
    b64url,
    encrypt_payload,
    push_sender_for,
    unb64url,
)
from app.delivery.strings import PUSH_LINE
from app.delivery.subscriptions import subscribe
from app.delivery.triggers.deliver import Via
from app.delivery.triggers.models import (
    DeliveryChannel,
    DeliveryOutcome,
    PushSubscription,
    TriggerType,
)
from app.delivery.triggers.preferences import change
from app.fixtures import is_fixture
from app.identity.models import LoginSession, Person
from app.regions import Region
from app.settings import MissingSetting, load_settings
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.delivery_support import Home, home
from tests.test_triggers import _rows, _run, at

# --- RFC 8291 §5 and appendix A: the worked example ------------------------------------------

PLAINTEXT = b"When I grow up, I want to be a watermelon"
AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
UA_PUBLIC = (
    "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
)
UA_PRIVATE = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"
SALT = "DGv6ra1nlYgDCS1FRnbzlw"
AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
HEADER = (
    "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
    "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8"
)
CIPHERTEXT = "8pfeW0KbunFT06SuDKoJH9Ql87S1QUrdirN6GcG7sFz1y1sqLgVi1VhjVkHsUoEsbI_0LpXMuGvnzQ"
MESSAGE = (
    "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
    "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
    "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
)
"""Section 5's body: the 86-octet header, then the 58-octet ciphertext — 144 octets (the
example's own Content-Length line says 145; the body it prints is 144)."""


def _private(raw: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(unb64url(raw), "big"), ec.SECP256R1())


def _public(key: ec.EllipticCurvePrivateKey) -> str:
    return b64url(key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))


def test_the_rfc_8291_example_encrypts_to_its_published_bytes() -> None:
    body = encrypt_payload(
        PLAINTEXT, p256dh=UA_PUBLIC, auth=AUTH, salt=unb64url(SALT), sender=_private(AS_PRIVATE)
    )
    assert body == unb64url(MESSAGE) and len(body) == 144
    assert body == unb64url(HEADER) + unb64url(CIPHERTEXT)
    # And the example's receiver reads it back with its own private key.
    read = http_ece.decrypt(
        body, private_key=_private(UA_PRIVATE), auth_secret=unb64url(AUTH), version="aes128gcm"
    )
    assert read == PLAINTEXT


# --- VAPID (RFC 8292) ------------------------------------------------------------------------


def _vapid_pair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    return _public(key), b64url(key.private_numbers().private_value.to_bytes(32, "big"))


def _sender(service: PushService | None = None) -> WebPush:
    public, private = _vapid_pair()
    return WebPush(
        public_key=public,
        private_key=private,
        subject="mailto:ops@nura.example",
        transport=None if service is None else httpx.MockTransport(service.answer),
    )


def _claims(header: str) -> dict[str, object]:
    token = re.search(r"t=([^,\s]+)", header)
    assert token is not None
    claims: dict[str, object] = json.loads(unb64url(token.group(1).split(".")[1]))
    return claims


def test_a_push_is_signed_for_the_push_services_origin_for_at_most_a_day(
    clock: FrozenClock,
) -> None:
    sender = _sender()
    header = sender.authorization("https://fcm.googleapis.com/fcm/send/abc:def")
    assert Vapid02.verify(header), "the token verifies with the public key it names"
    key = re.search(r"k=([^,\s]+)", header)
    assert key is not None and key.group(1) == sender.public_key
    claims = _claims(header)
    assert claims["aud"] == "https://fcm.googleapis.com"
    assert claims["sub"] == "mailto:ops@nura.example"
    now = clock.now().timestamp()
    assert isinstance(claims["exp"], int) and now < claims["exp"] <= now + 24 * 60 * 60


def test_keys_that_are_not_a_pair_are_refused_at_start() -> None:
    public, _ = _vapid_pair()
    _, private = _vapid_pair()
    with pytest.raises(BadVapidKeys):
        WebPush(public_key=public, private_key=private, subject="mailto:ops@nura.example")


# --- which sender a process runs on ----------------------------------------------------------

ENV = {"NURA_REGION": "SG", "NURA_DATABASE_URL": "sqlite+aiosqlite://"}


def _vapid_env() -> dict[str, str]:
    public, private = _vapid_pair()
    return {
        "NURA_VAPID_PUBLIC_KEY": public,
        "NURA_VAPID_PRIVATE_KEY": private,
        "NURA_VAPID_SUBJECT": "mailto:ops@nura.example",
    }


def test_the_three_vapid_settings_go_together() -> None:
    whole = _vapid_env()
    assert load_settings({**ENV, **whole}).vapid_public_key == whole["NURA_VAPID_PUBLIC_KEY"]
    for missing in whole:
        with pytest.raises(MissingSetting):
            load_settings({**ENV, **{k: v for k, v in whole.items() if k != missing}})
    with pytest.raises(MissingSetting):
        load_settings({**ENV, **whole, "NURA_VAPID_SUBJECT": "ops@nura.example"})


def test_web_push_wherever_the_keys_are_else_the_fixture_or_nobody() -> None:
    keys = _vapid_env()
    demo = {"NURA_DEMO_MODE": "1", "NURA_DEMO_LOGIN_CODE": "246810"}
    dev = {"NURA_DEV_CODE_SENDER": "1"}
    for extra in ({}, demo, dev):
        sender = push_sender_for(load_settings({**ENV, **extra, **keys}))
        assert isinstance(sender, WebPush) and not is_fixture(sender)
    assert isinstance(push_sender_for(load_settings({**ENV, **dev})), FixturePush)
    assert isinstance(push_sender_for(load_settings({**ENV, **demo})), NoDevices)
    # A deployment without keys is on `NoDevices`, a fixture: it refuses to start (app.fixtures).
    production = push_sender_for(load_settings(ENV))
    assert isinstance(production, NoDevices) and is_fixture(production)


# --- behind the trigger engine --------------------------------------------------------------


class PushService:
    """A push service in the test: what it was sent, and what it answers."""

    def __init__(self, status: int = 201) -> None:
        self.status = status
        self.requests: list[httpx.Request] = []

    def answer(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status)


@dataclass
class Phone:
    """A browser that subscribed: its keys, so a test can read what was pushed to it."""

    key: ec.EllipticCurvePrivateKey
    auth: bytes
    endpoint: str

    @classmethod
    def new(cls) -> Phone:
        return cls(
            key=ec.generate_private_key(ec.SECP256R1()),
            auth=uuid.uuid4().bytes,
            endpoint=f"https://push.example.test/send/{uuid.uuid4().hex}",
        )

    @property
    def p256dh(self) -> str:
        return _public(self.key)

    def read(self, request: httpx.Request) -> dict[str, str]:
        plain = http_ece.decrypt(
            request.content, private_key=self.key, auth_secret=self.auth, version="aes128gcm"
        )
        said: dict[str, str] = json.loads(plain)
        return said


async def _signed_in(sg: AsyncSession, person: Person) -> LoginSession:
    login = LoginSession(
        region=Region.SG,
        person_id=person.id,
        token_hash=uuid.uuid4().hex * 2,
        expires_at=utcnow() + timedelta(days=30),
    )
    sg.add(login)
    await sg.flush()
    return login


async def _pushing(
    sg: AsyncSession, h: Home, service: PushService, phone: Phone, person: Person | None = None
) -> LoginSession:
    """Reorders by app push first, Web Push behind the port, and one phone subscribed: Mei's,
    or `person`'s."""
    who = person or h.mei
    await change(
        sg,
        context=h.owner,
        skip_quiet_days=False,
        quiet_from=None,
        quiet_until=None,
        channels={"reorder": ["app_push", "whatsapp"]},
        caps={},
    )
    h.via = Via.of(h.via.settings, replace(h.via.providers, push=_sender(service)))
    login = await _signed_in(sg, who)
    await subscribe(
        sg,
        context=await h.ctx(sg, who),
        login_id=login.id,
        endpoint=phone.endpoint,
        p256dh=phone.p256dh,
        auth=b64url(phone.auth),
    )
    return login


HEALTH_WORDS = ("amlodipine", "blood", "pressure", "tablet", "medicine", "reorder", "dose", "30")


async def test_a_reorder_reaches_the_phone_as_one_line_and_an_id_and_nothing_else(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, quantity=2)
    service, phone = PushService(), Phone.new()
    await _pushing(sg, h, service, phone)
    report = await _run(sg, h, clock, at(10))
    [row] = _rows(report, TriggerType.REORDER)
    assert row.via is DeliveryChannel.APP_PUSH and row.passed_over == []
    # Every push that went to Mei's phone this run (the reorder, and anything else whose
    # channels start with the app) is one request, and each says a line and an id, no more.
    pushed = [
        sent.delivery for sent in report.sent if sent.delivery.via is DeliveryChannel.APP_PUSH
    ]
    assert len(service.requests) == len(pushed) >= 1
    ids = set()
    for request in service.requests:
        assert str(request.url) == phone.endpoint
        assert request.headers["content-encoding"] == "aes128gcm"
        assert int(request.headers["ttl"]) > 0
        assert Vapid02.verify(request.headers["authorization"])
        assert _claims(request.headers["authorization"])["aud"] == "https://push.example.test"
        said = phone.read(request)
        assert set(said) == {"text", "id"} and said["text"] in PUSH_LINE.values()
        uuid.UUID(said["id"])
        # No health word rides a push: not the medicine, not the count, not what it is about.
        # The id is a random uuid, checked as one above: it may hold "30" by chance.
        assert not any(word in said["text"].lower() for word in HEALTH_WORDS)
        ids.add(said["id"])
    assert str(row.id) in ids  # the reorder's push names its own delivery row


async def test_the_quiet_hours_hold_a_push(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, quantity=2)
    service, phone = PushService(), Phone.new()
    await _pushing(sg, h, service, phone)
    await change(
        sg,
        context=h.owner,
        skip_quiet_days=False,
        quiet_from=time(21, 0),
        quiet_until=time(7, 0),
        channels={"reorder": ["app_push", "whatsapp"]},
        caps={},
    )
    [row] = _rows(await _run(sg, h, clock, at(22)), TriggerType.REORDER)
    assert row.outcome is DeliveryOutcome.QUIET
    assert service.requests == []


async def test_a_phone_the_push_service_forgot_is_dropped_and_whatsapp_takes_the_send(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, quantity=2)
    service, phone = PushService(status=410), Phone.new()
    await _pushing(sg, h, service, phone)
    report = await _run(sg, h, clock, at(10))
    # The first push this run met the 410: that send went by WhatsApp, and the phone is dropped.
    (gone,) = [s.delivery for s in report.sent if "app_push: gone" in s.delivery.passed_over]
    assert gone.via is DeliveryChannel.WHATSAPP
    assert len(service.requests) == 1
    (device,) = (await sg.execute(select(PushSubscription))).scalars().all()
    assert device.gone_at is not None
    # Nothing after it tries the phone again: the reorder, today and tomorrow, goes by WhatsApp.
    [row] = _rows(report, TriggerType.REORDER)
    assert row.via is DeliveryChannel.WHATSAPP
    [again] = _rows(await _run(sg, h, clock, at(10, day=15)), TriggerType.REORDER)
    assert again.passed_over == ["app_push: no device"] and len(service.requests) == 1


async def test_a_phone_signed_out_gets_nothing(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, quantity=2)
    service, phone = PushService(), Phone.new()
    login = await _pushing(sg, h, service, phone)
    login.revoked_at = utcnow()
    await sg.flush()
    [row] = _rows(await _run(sg, h, clock, at(10)), TriggerType.REORDER)
    assert row.via is DeliveryChannel.WHATSAPP and row.passed_over == ["app_push: no device"]
    assert service.requests == []


async def test_a_nudge_push_names_the_nudge_the_web_reads(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """A push carries no words, so a nudge's push carries the nudge's own id: the one
    `GET /profiles/{id}/nudges?day=` (#138) returns, where the app reads what it says."""
    from app.db import as_utc
    from app.delivery.nudges.engine import hand_over
    from tests.feelings_support import REGISTRY

    clock.set(at(9))
    h = await home(sg, tmp_path)
    service, phone = PushService(), Phone.new()
    await _pushing(sg, h, service, phone, person=h.pa)
    _, nudge = await hand_over(sg, context=h.owner, registry=REGISTRY)
    due = as_utc(nudge.send_after) + timedelta(minutes=1)
    [row] = _rows(await _run(sg, h, clock, due), TriggerType.NUDGE)
    assert row.via is DeliveryChannel.APP_PUSH and row.outcome is DeliveryOutcome.SENT
    said = [phone.read(request) for request in service.requests]
    assert all(set(one) == {"text", "id"} for one in said)
    assert str(nudge.id) in {one["id"] for one in said}


async def test_a_nudge_he_answered_in_the_app_is_not_pushed(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """#138: delivery skips a nudge he already answered in the app, before any channel, so
    no push goes for it either."""
    from app.db import as_utc
    from app.delivery.nudges.engine import hand_over, respond
    from app.delivery.nudges.models import ResponseKind
    from tests.feelings_support import REGISTRY

    clock.set(at(9))
    h = await home(sg, tmp_path)
    service, phone = PushService(), Phone.new()
    await _pushing(sg, h, service, phone, person=h.pa)
    _, nudge = await hand_over(sg, context=h.owner, registry=REGISTRY)
    await respond(sg, context=h.owner, nudge_id=nudge.id, kind=ResponseKind.DISMISSED)
    due = as_utc(nudge.send_after) + timedelta(minutes=1)
    [row] = _rows(await _run(sg, h, clock, due), TriggerType.NUDGE)
    assert row.outcome is DeliveryOutcome.SKIPPED and row.reason == "answered in the app"
    assert str(nudge.id) not in {phone.read(request)["id"] for request in service.requests}


# --- the door --------------------------------------------------------------------------------


async def test_a_phone_subscribes_and_unsubscribes_over_http(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, "+6591440001", "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    phone = Phone.new()
    path = f"/profiles/{profile_id}/push-subscriptions"
    body = {
        "endpoint": phone.endpoint,
        "keys": {"p256dh": phone.p256dh, "auth": b64url(phone.auth)},
    }
    first = await deployment.client.post(path, json=body, headers=his)
    assert first.status_code == 201, first.text
    again = await deployment.client.post(path, json=body, headers=his)
    assert again.status_code == 201 and again.json() != first.json()

    async def live() -> list[PushSubscription]:
        async with deployment.sessions() as session:
            rows = (await session.execute(select(PushSubscription))).scalars().all()
            logins = (await session.execute(select(LoginSession))).scalars().all()
        assert {row.session_id for row in rows} <= {login.id for login in logins}
        return [row for row in rows if row.revoked_at is None]

    (kept,) = await live()  # the same browser again replaced the one before
    assert str(kept.id) == again.json()["subscription_id"]
    refused = await deployment.client.post(
        path, json={**body, "endpoint": "http://push.example.test/x"}, headers=his
    )
    assert refused.status_code == 400 and refused.json() == {"refusal": "NotAPushSubscription"}
    gone = await deployment.client.request(
        "DELETE", path, json={"endpoint": phone.endpoint}, headers=his
    )
    assert gone.status_code == 204
    assert await live() == []
    shown = (await deployment.client.get("/deployment")).json()
    assert shown["push_key"] is None  # this test deployment has no Web Push
