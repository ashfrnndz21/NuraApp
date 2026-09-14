"""The WhatsApp provider port, and the fixture that stands behind it until a real one does.

`WhatsAppProvider` is the whole of what the channel knows about the business solution
provider: send a text, send an approved template, fetch a piece of media by its id, check a
webhook's signature, and parse the provider's inbound payload into `InboundMessage`s. The
real adapter — Twilio, 360dialog, Gupshup, or Meta's Cloud API directly — is a later
implementation of the same protocol. `FixtureProvider` is what runs in the tests and on a
laptop: it keeps every send in memory so a test can read it back, serves media from
`backend/tests/fixtures/whatsapp/`, and signs with the fixed dev secret from the settings.
Like the logging code sender, it may only run on a declared dev run.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.errors import Refusal
from app.settings import Settings

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """One message that reached the business number, as the provider handed it over.

    `from_e164` is the sender's number: their identity. `text` is what they typed, or None
    for a media message; `media_id` is the provider's handle for a photo or a PDF, fetched
    within the provider's time limit and never stored as a handle. `group_id` names the
    family group the message was posted in, or None for a private thread.
    """

    provider_message_id: str
    from_e164: str
    at: datetime
    text: str | None = None
    media_id: str | None = None
    content_type: str | None = None
    group_id: str | None = None


@dataclass(frozen=True, slots=True)
class Media:
    data: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class Sent:
    """One message that went out through the provider, as the fixture remembers it."""

    to_e164: str
    kind: str
    """`text` inside the 24-hour window, `template` outside it."""
    text: str
    template_name: str | None
    language: str
    params: Mapping[str, str]
    provider_message_id: str


class WhatsAppProvider(Protocol):
    """Everything the channel asks of the outside world, and nothing more."""

    @property
    def name(self) -> str: ...

    async def send_text(self, to_e164: str, text: str) -> str:
        """Free text, inside the 24-hour customer-service window. The provider's message id."""
        ...

    async def send_template(
        self, to_e164: str, template_name: str, language: str, params: Mapping[str, str]
    ) -> str:
        """One of the approved templates, with its slots filled. The provider's message id."""
        ...

    async def fetch_media(self, media_id: str) -> Media: ...

    def verify_webhook(self, signature: str | None, body: bytes) -> bool:
        """Whether `body` was signed by the provider (`X-Hub-Signature-256: sha256=…`)."""
        ...

    def verify_token_matches(self, token: str | None) -> bool:
        """Whether the verify token on the webhook's GET is ours."""
        ...

    def parse_inbound(self, payload: Mapping[str, Any]) -> Sequence[InboundMessage]:
        """The messages in one webhook delivery. Statuses and anything else are dropped."""
        ...


class NoSuchMedia(Refusal):
    """The provider has nothing under that media id, or it has expired."""


class NotAWebhook(Refusal):
    """The webhook body was not signed by the provider, or was not shaped like one."""


class NoWhatsAppProvider(RuntimeError):
    """No provider can carry a WhatsApp message. The process must not start on this setting."""


class FixtureProviderInProduction(RuntimeError):
    """The fixture provider was asked to run without NURA_DEV_CODE_SENDER=1."""


def _moment(seconds: str | None) -> datetime:
    if seconds is None or not seconds.isdigit():
        return datetime.now(UTC)
    return datetime.fromtimestamp(int(seconds), UTC)


class FixtureProvider:
    """Sends into a list, serves media from `fixtures/whatsapp/media.json`, signs with a secret.

    `media.json` maps a media id to `{"content_type": …, "label": …}`: the bytes served are
    the same placeholder the paper fixtures use (`tests/paper.py`), so a forwarded photo of
    the lipid report reads as the lipid report. No image is committed.
    """

    name = "fixture"

    def __init__(self, *, secret: str, fixtures: Path | None = None) -> None:
        self._secret = secret.encode()
        self._fixtures = fixtures
        self.sent: list[Sent] = []
        self._media: dict[str, dict[str, Any]] | None = None

    def _index(self) -> dict[str, dict[str, Any]]:
        if self._media is None:
            found: dict[str, dict[str, Any]] = {}
            if self._fixtures is not None:
                path = Path(self._fixtures) / "media.json"
                if path.is_file():
                    found = json.loads(path.read_text())
            self._media = found
        return self._media

    async def send_text(self, to_e164: str, text: str) -> str:
        message_id = f"wamid.fixture.{uuid.uuid4().hex[:12]}"
        self.sent.append(Sent(to_e164, "text", text, None, "", {}, message_id))
        return message_id

    async def send_template(
        self, to_e164: str, template_name: str, language: str, params: Mapping[str, str]
    ) -> str:
        # The fixture renders nothing itself: the channel hands it the rendered text as the
        # `text` slot so a test and the checkpoint can print what the person would read.
        message_id = f"wamid.fixture.{uuid.uuid4().hex[:12]}"
        rendered = params.get("_rendered", "")
        shown = {k: v for k, v in params.items() if not k.startswith("_")}
        self.sent.append(
            Sent(to_e164, "template", rendered, template_name, language, shown, message_id)
        )
        return message_id

    async def fetch_media(self, media_id: str) -> Media:
        entry = self._index().get(media_id)
        if entry is None:
            raise NoSuchMedia(f"no media {media_id} in the fixtures")
        label = str(entry.get("label", media_id))
        content_type = str(entry.get("content_type", "image/png"))
        if content_type == "application/pdf":
            data = b"%PDF-1.4\n%nura-paper-placeholder:" + label.encode("ascii") + b"\n"
        else:
            data = PNG_SIGNATURE + b"nura-paper-placeholder:" + label.encode("ascii") + b"\n"
        return Media(data=data, content_type=content_type)

    def sign(self, body: bytes) -> str:
        """What a provider would put in `X-Hub-Signature-256` for this body. Tests only."""
        return "sha256=" + hmac.new(self._secret, body, hashlib.sha256).hexdigest()

    def verify_webhook(self, signature: str | None, body: bytes) -> bool:
        if not signature:
            return False
        return hmac.compare_digest(signature, self.sign(body))

    def verify_token_matches(self, token: str | None) -> bool:
        return token is not None and hmac.compare_digest(token.encode(), self._secret)

    def parse_inbound(self, payload: Mapping[str, Any]) -> Sequence[InboundMessage]:
        """The Cloud API shape: entry[].changes[].value.messages[]."""
        found: list[InboundMessage] = []
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = change.get("value", {}) or {}
                for message in value.get("messages", []) or []:
                    parsed = _parse_one(message)
                    if parsed is not None:
                        found.append(parsed)
        return found


def _parse_one(message: Mapping[str, Any]) -> InboundMessage | None:
    kind = message.get("type")
    sender = message.get("from")
    if not isinstance(sender, str) or not sender:
        return None
    from_e164 = sender if sender.startswith("+") else f"+{sender}"
    at = _moment(str(message.get("timestamp")) if message.get("timestamp") else None)
    message_id = str(message.get("id") or uuid.uuid4())
    context = message.get("context") or {}
    group = context.get("group_id") if isinstance(context, Mapping) else None
    if kind == "text":
        body = (message.get("text") or {}).get("body")
        return InboundMessage(message_id, from_e164, at, text=body, group_id=group)
    if kind in ("image", "document"):
        media = message.get(kind) or {}
        return InboundMessage(
            message_id,
            from_e164,
            at,
            text=media.get("caption"),
            media_id=media.get("id"),
            content_type=media.get("mime_type"),
            group_id=group,
        )
    if kind == "button":
        return InboundMessage(
            message_id,
            from_e164,
            at,
            text=(message.get("button") or {}).get("text"),
            group_id=group,
        )
    return None


def whatsapp_provider_for(settings: Settings) -> WhatsAppProvider:
    """The provider this deployment runs on.

    Only the fixture exists, and it runs only on a declared dev run with a dev secret set,
    the way the logging code sender does: anywhere else the process refuses to start rather
    than pretend a sandbox is a provider.
    """
    if settings.whatsapp_provider != "fixture":
        raise NoWhatsAppProvider(
            f"no WhatsApp provider named {settings.whatsapp_provider!r} is built; "
            "set NURA_WHATSAPP_PROVIDER=fixture for a local run"
        )
    if not settings.dev_code_sender or not settings.whatsapp_dev_secret:
        raise NoWhatsAppProvider(
            "the fixture WhatsApp provider runs only on a dev run: set NURA_DEV_CODE_SENDER=1 "
            "and NURA_WHATSAPP_DEV_SECRET"
        )
    fixtures = Path(settings.whatsapp_fixtures) if settings.whatsapp_fixtures else None
    return FixtureProvider(secret=settings.whatsapp_dev_secret, fixtures=fixtures)


def check_whatsapp_provider(settings: Settings, provider: WhatsAppProvider) -> None:
    """Refuse the fixture anywhere but a declared dev run. `create_app` calls this."""
    if isinstance(provider, FixtureProvider) and not settings.dev_code_sender:
        raise FixtureProviderInProduction(
            "FixtureProvider sends nothing and signs with a dev secret; set "
            "NURA_DEV_CODE_SENDER=1 for a local run or configure a real provider"
        )


@dataclass(frozen=True, slots=True)
class DevInbound:
    """What the dev-only route takes to feed a message through the webhook's path without a
    provider: who from, what, and optionally which fixture media."""

    from_e164: str
    text: str | None = None
    media_id: str | None = None
    content_type: str | None = None
    group_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_message(self, at: datetime) -> InboundMessage:
        return InboundMessage(
            provider_message_id=f"wamid.dev.{uuid.uuid4().hex[:12]}",
            from_e164=self.from_e164,
            at=at,
            text=self.text,
            media_id=self.media_id,
            content_type=self.content_type,
            group_id=self.group_id,
        )
