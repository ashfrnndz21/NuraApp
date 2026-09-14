"""The provider that carries a login code to a person: by SMS, by WhatsApp, by email.

`CodeSender` is the whole of what the identity service knows about the outside world. A real
SMS or email provider arrives later as another implementation of it. Until then there is
only `LoggingCodeSender`, and it may only run where `Settings.dev_code_sender` says so: it
puts the code in the server log, which on a laptop is how you sign in and anywhere else is
how someone takes over an account.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.settings import Settings

log = logging.getLogger("nura.identity.sender")


class CodeSender(Protocol):
    """How a one-time secret reaches the person who asked for it."""

    async def send_phone_code(self, phone_e164: str, code: str, *, message: str) -> None:
        """Send the code to a phone, by SMS or by WhatsApp, in exactly the words given.

        `message` is `app.channels.strings.phone_code_message(code, language=...)`, already in
        the person's language (`app.identity.login` chooses it): a provider carries the
        sentence, it does not write one. `code` is the six digits inside it.
        """
        ...

    async def send_email_link(self, email: str, token: str) -> None:
        """Send a link carrying a one-time token to an email address."""
        ...


class DevSenderInProduction(RuntimeError):
    """The logging code sender was asked to run without NURA_DEV_CODE_SENDER=1."""


class NoCodeSender(RuntimeError):
    """No provider can carry a login code, so nobody could sign in. The process must not start."""


class LoggingCodeSender:
    """The fixture sender: keeps the secret so a test can read it back, and logs it if told to.

    `make dev` runs on this with `reveal=True`, which is why the code prints in the server
    log. Without `reveal` the line says a code went out and nothing more: never the code,
    never the code beside the number. `create_app` refuses this sender altogether unless the
    deployment's settings name it as a dev run.
    """

    def __init__(self, *, reveal: bool = False) -> None:
        self.reveal = reveal
        self._codes: dict[str, str] = {}
        self._messages: dict[str, str] = {}
        self._tokens: dict[str, str] = {}

    async def send_phone_code(self, phone_e164: str, code: str, *, message: str) -> None:
        self._codes[phone_e164] = code
        self._messages[phone_e164] = message
        if self.reveal:
            log.info("login code for %s: %s", phone_e164, code)
        else:
            log.info("login code sent by phone")

    async def send_email_link(self, email: str, token: str) -> None:
        self._tokens[email] = token
        if self.reveal:
            log.info("login link token for %s: %s", email, token)
        else:
            log.info("login link sent by email")

    def last_code(self, phone_e164: str) -> str:
        """The last code sent to this number. Tests only."""
        return self._codes[phone_e164]

    def last_message(self, phone_e164: str) -> str:
        """The words of the last code message sent to this number. Tests only."""
        return self._messages[phone_e164]

    def last_email_token(self, email: str) -> str:
        """The last link token sent to this address. Tests only."""
        return self._tokens[email]


def code_sender_for(settings: Settings) -> CodeSender:
    """The sender this deployment runs on.

    There is no real provider yet, so a deployment that is not a declared dev run has no way
    to carry a code and refuses to start rather than start unable to sign anyone in — or,
    worse, start on the logging sender.
    """
    if settings.dev_code_sender:
        return LoggingCodeSender(reveal=True)
    raise NoCodeSender(
        "no SMS or email provider is configured; set NURA_DEV_CODE_SENDER=1 for a local run"
    )


def check_sender(settings: Settings, sender: CodeSender) -> None:
    """Refuse the logging sender anywhere but a declared dev run. `create_app` calls this."""
    if isinstance(sender, LoggingCodeSender) and not settings.dev_code_sender:
        raise DevSenderInProduction(
            "LoggingCodeSender prints login codes to the log; set NURA_DEV_CODE_SENDER=1 "
            "for a local run or configure a real provider"
        )
