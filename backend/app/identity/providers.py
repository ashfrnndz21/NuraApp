"""The provider that carries a login code to a person: by SMS, by WhatsApp, by email.

`CodeSender` is the whole of what the identity service knows about the outside world. A real
SMS or email provider arrives later as another implementation of it. Until then there is
only `LoggingCodeSender`, and it may only run where `Settings.dev_code_sender` says so: it
puts the code in the server log, which on a laptop is how you sign in and anywhere else is
how someone takes over an account.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from app.demo import NotInTheDemo, refuse_unless_demo_number
from app.fixtures import fixture
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


@runtime_checkable
class SharedCode(Protocol):
    """A sender whose code the person already holds: a demo's, given out by the operator.
    `app.identity.login` asks it for the code instead of minting one."""

    def shared_code(self, phone_e164: str) -> str: ...


class DevSenderInProduction(RuntimeError):
    """The logging code sender was asked to run without NURA_DEV_CODE_SENDER=1."""


class DemoSenderOutsideDemo(RuntimeError):
    """The demo sender, whose one code signs in every test number, outside NURA_DEMO_MODE=1."""


class NoCodeSender(RuntimeError):
    """No provider can carry a login code, so nobody could sign in. The process must not start."""


@fixture
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


class DemoCodeSender:
    """The sender on a demo deployment (`app.demo`, ADR 0008). It sends nothing and logs no
    code. A test number (+65 0…, +60 0…) signs in with the operator's code,
    NURA_DEMO_LOGIN_CODE; any other number is refused before a challenge is written, and so is
    an email, since no email could carry the link."""

    def __init__(self, code: str) -> None:
        if len(code) != 6 or not code.isdigit():
            raise NoCodeSender("the demo's login code is six digits (NURA_DEMO_LOGIN_CODE)")
        self._code = code

    def shared_code(self, phone_e164: str) -> str:
        refuse_unless_demo_number(phone_e164)
        return self._code

    async def send_phone_code(self, phone_e164: str, code: str, *, message: str) -> None:
        # The message is in his language (#132) and carries the operator's code: it goes
        # nowhere, and neither it nor the code is logged. No SMS path exists on a demo.
        refuse_unless_demo_number(phone_e164)
        log.info("demo: a login code was asked for a test number; nothing was sent")

    async def send_email_link(self, email: str, token: str) -> None:
        raise NotInTheDemo("a demo signs in by test phone number only")


def code_sender_for(settings: Settings) -> CodeSender:
    """The sender this deployment runs on.

    There is no real provider yet, so a deployment that is neither a declared dev run nor a
    declared demo has no way to carry a code and refuses to start rather than start unable to
    sign anyone in — or, worse, start on the logging sender.
    """
    if settings.dev_code_sender:
        return LoggingCodeSender(reveal=True)
    if settings.demo_mode and settings.demo_login_code is not None:
        return DemoCodeSender(settings.demo_login_code)
    raise NoCodeSender(
        "no SMS or email provider is configured; set NURA_DEV_CODE_SENDER=1 for a local run "
        "or NURA_DEMO_MODE=1 with NURA_DEMO_LOGIN_CODE for a demo"
    )


def check_sender(settings: Settings, sender: CodeSender) -> None:
    """Refuse the logging sender anywhere but a declared dev run, and the demo sender anywhere
    but a declared demo. `create_app` calls this."""
    if isinstance(sender, LoggingCodeSender) and not settings.dev_code_sender:
        raise DevSenderInProduction(
            "LoggingCodeSender prints login codes to the log; set NURA_DEV_CODE_SENDER=1 "
            "for a local run or configure a real provider"
        )
    if isinstance(sender, DemoCodeSender) and not settings.demo_mode:
        raise DemoSenderOutsideDemo(
            "DemoCodeSender signs every test number in with one code; it runs only with "
            "NURA_DEMO_MODE=1"
        )
