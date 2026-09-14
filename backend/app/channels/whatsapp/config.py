"""The business number: one per country, verified with Meta through a provider (E19-01).

Nothing here is health data: a number, a provider's name, where verification stands, and
the six approved templates by name. The templates themselves — their slots and the words a
patient reads — are `app.channels.whatsapp.templates`; a deployment names which of them are
approved for its number, and a send of a template not approved here is refused before it
reaches the provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.channels.whatsapp.templates import TEMPLATE_NAMES
from app.regions import Region
from app.settings import Settings


class VerificationState(StrEnum):
    """Where the number stands with Meta. `SANDBOX` is the fixture on a laptop."""

    SANDBOX = "sandbox"
    PENDING = "pending"
    VERIFIED = "verified"


SANDBOX_NUMBERS: dict[Region, str] = {Region.SG: "+6500000000", Region.MY: "+6000000000"}
"""Placeholders for a dev run with no number set. Not dialable, on purpose."""


@dataclass(frozen=True, slots=True)
class BusinessNumber:
    region: Region
    phone_e164: str
    provider_name: str
    verification: VerificationState
    display_name: str
    templates: tuple[str, ...]
    """The approved templates' names, in the order they were submitted."""

    def approves(self, template_name: str) -> bool:
        return template_name in self.templates


def business_number_for(settings: Settings) -> BusinessNumber:
    """This deployment's number, from its settings. The fixture provider is a sandbox."""
    fixture = settings.whatsapp_provider == "fixture"
    return BusinessNumber(
        region=settings.region,
        phone_e164=settings.whatsapp_number or SANDBOX_NUMBERS[settings.region],
        provider_name=settings.whatsapp_provider,
        verification=VerificationState.SANDBOX if fixture else VerificationState.PENDING,
        display_name="Nura",
        templates=TEMPLATE_NAMES,
    )
