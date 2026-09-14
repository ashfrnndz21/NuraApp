"""App push: the port, the real Web Push sender, and what stands in for it (E11-05).

A push carries no health content, by design: one line, "Nura has something for you.", and an
opaque id the app opens. Health data never rides a push through Apple's or Google's servers;
the app opens and reads the card from its region. `PushSender` is the port. `WebPush` is the
real sender: Web Push (RFC 8030) to the home-screen app (ADR 0001: iOS 16.4 and later push to
an installed PWA), the payload encrypted to the browser's keys (RFC 8291, Mozilla's
`http_ece`) and every request signed with this deployment's VAPID key (RFC 8292, Mozilla's
`py_vapid`), sent with httpx. `FixturePush` keeps pushes in memory, for the tests and a dev
run. `NoDevices` reaches nobody: a demo without VAPID keys runs on it, and a deployment that
is neither a dev run nor a demo refuses to start on it (it is a fixture).

The port takes the delivery run's session and key context because a person's devices are
rows of the profile (`PushSubscription`, one per login session and browser), read like any
other row of his: through the key context, on the trail.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from urllib.parse import urlsplit

import http_ece  # type: ignore[import-untyped]
import httpx
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid02  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.errors import Refusal
from app.fixtures import fixture
from app.keys.context import KeyContext
from app.settings import Settings

TTL_SECONDS = 12 * 60 * 60
"""How long a push service keeps a push for a phone that is off: half a day, then it lapses."""
VAPID_LIFETIME = timedelta(hours=12)
"""How long one signed request is good for. RFC 8292 allows at most 24 hours."""
GONE = (404, 410)
"""What a push service answers for a subscription that no longer exists."""


class NoDevice(Refusal):
    """This person has no device a push can reach, or every one of them has gone."""


class BadVapidKeys(RuntimeError):
    """The VAPID keys do not make a pair. The process must not start on them."""


@dataclass(frozen=True, slots=True)
class Pushed:
    """One push that went out, as the fixture remembers it."""

    person_id: uuid.UUID
    text: str
    push_id: str
    ref: str = ""


class PushSender(Protocol):
    @property
    def name(self) -> str: ...

    async def reachable(
        self, session: AsyncSession, context: KeyContext, person_id: uuid.UUID
    ) -> bool:
        """Whether this person has a device a push can reach, on this profile."""
        ...

    async def push(
        self,
        session: AsyncSession,
        context: KeyContext,
        person_id: uuid.UUID,
        text: str,
        *,
        ref: str,
    ) -> str:
        """Send one content-free line, and the id the app opens, to the person's devices.
        The push's id; `NoDevice` when none of them could be reached."""
        ...


@fixture
class NoDevices:
    """No device is registered anywhere: nobody is reachable by push."""

    name = "none"

    async def reachable(
        self, session: AsyncSession, context: KeyContext, person_id: uuid.UUID
    ) -> bool:
        return False

    async def push(
        self,
        session: AsyncSession,
        context: KeyContext,
        person_id: uuid.UUID,
        text: str,
        *,
        ref: str,
    ) -> str:
        raise NoDevice(f"person {person_id} has no device registered")


@fixture
class FixturePush:
    """Pushes into a list, to the people a test registered. Nothing leaves the process."""

    name = "fixture"

    def __init__(self) -> None:
        self.devices: set[uuid.UUID] = set()
        self.sent: list[Pushed] = []

    def register(self, person_id: uuid.UUID) -> None:
        self.devices.add(person_id)

    async def reachable(
        self, session: AsyncSession, context: KeyContext, person_id: uuid.UUID
    ) -> bool:
        return person_id in self.devices

    async def push(
        self,
        session: AsyncSession,
        context: KeyContext,
        person_id: uuid.UUID,
        text: str,
        *,
        ref: str,
    ) -> str:
        if person_id not in self.devices:
            raise NoDevice(f"person {person_id} has no device registered")
        push_id = f"push.fixture.{uuid.uuid4().hex[:12]}"
        self.sent.append(Pushed(person_id=person_id, text=text, push_id=push_id, ref=ref))
        return push_id


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encrypt_payload(
    payload: bytes,
    *,
    p256dh: str,
    auth: str,
    salt: bytes | None = None,
    sender: ec.EllipticCurvePrivateKey | None = None,
) -> bytes:
    """The payload as a push service carries it: `aes128gcm` (RFC 8188) keyed to the browser's
    P-256 key and auth secret (RFC 8291), by `http_ece`. A fresh sender key and salt for every
    push; `salt` and `sender` are given only by the RFC's worked example in the tests."""
    key = sender or ec.generate_private_key(ec.SECP256R1())
    # With no keyid given, http_ece puts the sender's public point in the header, as RFC 8291
    # has it: the browser needs it to derive the same key.
    body: bytes = http_ece.encrypt(
        payload,
        salt=salt or os.urandom(16),
        private_key=key,
        dh=unb64url(p256dh),
        auth_secret=unb64url(auth),
        version="aes128gcm",
    )
    return body


class WebPush:
    """Web Push to the browsers a person subscribed on this profile. Not a fixture."""

    name = "webpush"

    def __init__(
        self,
        *,
        public_key: str,
        private_key: str,
        subject: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        try:
            self._vapid = Vapid02.from_raw(private_key.encode())
            own = self._vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        except Exception as bad:  # a malformed key is refused at start, whatever the error
            raise BadVapidKeys("NURA_VAPID_PRIVATE_KEY is not a P-256 private key") from bad
        if b64url(own) != public_key.rstrip("="):
            raise BadVapidKeys("NURA_VAPID_PUBLIC_KEY is not the private key's own")
        self.public_key = public_key
        self.subject = subject
        self._transport = transport

    @classmethod
    def from_settings(
        cls, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> WebPush:
        assert settings.vapid_public_key and settings.vapid_private_key and settings.vapid_subject
        return cls(
            public_key=settings.vapid_public_key,
            private_key=settings.vapid_private_key,
            subject=settings.vapid_subject,
            transport=transport,
        )

    def authorization(self, endpoint: str) -> str:
        """The VAPID header for one push service: signed for its origin, good for 12 hours."""
        parts = urlsplit(endpoint)
        claims = {
            "aud": f"{parts.scheme}://{parts.netloc}",
            "exp": int((clock.now() + VAPID_LIFETIME).timestamp()),
            "sub": self.subject,
        }
        header: str = self._vapid.sign(claims)["Authorization"]
        return header

    async def reachable(
        self, session: AsyncSession, context: KeyContext, person_id: uuid.UUID
    ) -> bool:
        from app.delivery.subscriptions import live_for

        return bool(await live_for(session, context=context, person_id=person_id))

    async def push(
        self,
        session: AsyncSession,
        context: KeyContext,
        person_id: uuid.UUID,
        text: str,
        *,
        ref: str,
    ) -> str:
        from app.delivery.subscriptions import forget_gone, live_for

        payload = json.dumps({"text": text, "id": ref}, separators=(",", ":")).encode()
        reached = 0
        async with httpx.AsyncClient(transport=self._transport, timeout=10.0) as client:
            for device in await live_for(session, context=context, person_id=person_id):
                body = encrypt_payload(payload, p256dh=device.p256dh, auth=device.auth)
                try:
                    answer = await client.post(
                        device.endpoint,
                        content=body,
                        headers={
                            "Authorization": self.authorization(device.endpoint),
                            "TTL": str(TTL_SECONDS),
                            "Content-Encoding": "aes128gcm",
                            "Content-Type": "application/octet-stream",
                            "Urgency": "normal",
                        },
                    )
                except httpx.HTTPError:
                    continue  # this device this time; the next run tries again
                if answer.status_code in GONE:
                    await forget_gone(session, device)
                    continue
                if answer.is_success:
                    reached += 1
        if not reached:
            raise NoDevice(f"no device of person {person_id} took the push")
        return f"push.web.{uuid.uuid4().hex[:12]}"


def push_sender_for(settings: Settings) -> PushSender:
    """Web Push wherever the VAPID keys are set (a deployment, a demo, a laptop that wants
    it). Without them: the fixture on a declared dev run, and `NoDevices` anywhere else — a
    demo reaches nobody by push, and a deployment that is neither refuses to start, since
    `NoDevices` is a fixture (`app.fixtures`)."""
    if settings.vapid_private_key is not None:
        return WebPush.from_settings(settings)
    return FixturePush() if settings.dev_code_sender else NoDevices()
