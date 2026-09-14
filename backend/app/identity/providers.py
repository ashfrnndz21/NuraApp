"""The provider that carries a login code to a person: by SMS, by WhatsApp, by email.

`CodeSender` is the whole of what the identity service knows about the outside world. A real
SMS or email provider arrives later as another implementation of it; until then
`LoggingCodeSender` is the fixture, and the code goes into the server log and nowhere else.
"""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("nura.identity.sender")


class CodeSender(Protocol):
    """How a one-time secret reaches the person who asked for it."""

    async def send_phone_code(self, phone_e164: str, code: str) -> None:
        """Send a six-digit code to a phone, by SMS or by WhatsApp."""
        ...

    async def send_email_link(self, email: str, token: str) -> None:
        """Send a link carrying a one-time token to an email address."""
        ...


class LoggingCodeSender:
    """The fixture sender: logs the secret at INFO and keeps it so a test can read it back.

    `make dev` runs on this, which is why the code prints in the server log. There is no
    SMS and no email behind it, and nothing on the wire ever carries the code.
    """

    def __init__(self) -> None:
        self._codes: dict[str, str] = {}
        self._tokens: dict[str, str] = {}

    async def send_phone_code(self, phone_e164: str, code: str) -> None:
        self._codes[phone_e164] = code
        log.info("login code for %s: %s", phone_e164, code)

    async def send_email_link(self, email: str, token: str) -> None:
        self._tokens[email] = token
        log.info("login link token for %s: %s", email, token)

    def last_code(self, phone_e164: str) -> str:
        """The last code sent to this number. Tests only."""
        return self._codes[phone_e164]

    def last_email_token(self, email: str) -> str:
        """The last link token sent to this address. Tests only."""
        return self._tokens[email]
