"""App push: the port, and what stands behind it until the app registers a device (E11-05).

A push carries no health content, by design: one line, "Nura has something for you." Health
data never rides a push through Apple's or Google's servers; the app opens and reads the card
from its region. `PushSender` is the port. `FixturePush` keeps pushes in memory, for the tests
and a dev run, and reaches only the people a test registered. `NoDevices` is what a
deployment has until the app registers devices (the web client's push, ADR 0001; the iOS app,
Session 10): it reaches nobody, so the app channel on a trigger's list falls through to the
next one — WhatsApp, then the caregiver — and the Delivery row says it did.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.errors import Refusal
from app.settings import Settings


class NoDevice(Refusal):
    """This person has no device registered for app pushes."""


@dataclass(frozen=True, slots=True)
class Pushed:
    """One push that went out, as the fixture remembers it."""

    person_id: uuid.UUID
    text: str
    push_id: str


class PushSender(Protocol):
    @property
    def name(self) -> str: ...

    def reachable(self, person_id: uuid.UUID) -> bool:
        """Whether this person has a device a push can reach."""
        ...

    async def push(self, person_id: uuid.UUID, text: str) -> str:
        """Send one content-free line to the person's device. The push's id."""
        ...


class NoDevices:
    """No device is registered anywhere yet: nobody is reachable by push."""

    name = "none"

    def reachable(self, person_id: uuid.UUID) -> bool:
        return False

    async def push(self, person_id: uuid.UUID, text: str) -> str:
        raise NoDevice(f"person {person_id} has no device registered")


class FixturePush:
    """Pushes into a list, to the people a test registered. Nothing leaves the process."""

    name = "fixture"

    def __init__(self) -> None:
        self.devices: set[uuid.UUID] = set()
        self.sent: list[Pushed] = []

    def register(self, person_id: uuid.UUID) -> None:
        self.devices.add(person_id)

    def reachable(self, person_id: uuid.UUID) -> bool:
        return person_id in self.devices

    async def push(self, person_id: uuid.UUID, text: str) -> str:
        if person_id not in self.devices:
            raise NoDevice(f"person {person_id} has no device registered")
        push_id = f"push.fixture.{uuid.uuid4().hex[:12]}"
        self.sent.append(Pushed(person_id=person_id, text=text, push_id=push_id))
        return push_id


def push_sender_for(settings: Settings) -> PushSender:
    """The fixture on a declared dev run (with no devices until one is registered), and
    `NoDevices` anywhere else until a real sender exists."""
    return FixturePush() if settings.dev_code_sender else NoDevices()
