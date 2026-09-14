"""Regions.

One backend runs per country. A Person and a Profile are pinned to a region when they are
created and never move. Health data never leaves its region, so every deployment refuses to
write or read anything pinned somewhere else, even if the row is sitting in its database.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.errors import Refusal


class Region(StrEnum):
    """The regions Nura is deployed in. One database and one set of keys per region."""

    SG = "SG"
    MY = "MY"


REGION_TZ: Mapping[Region, ZoneInfo] = {
    Region.SG: ZoneInfo("Asia/Singapore"),
    Region.MY: ZoneInfo("Asia/Kuala_Lumpur"),
}
"""The clock on the patient's wall. Storage is UTC; anything he reads says his own day."""


class OutOfRegion(Refusal):
    """Asked for something that is held in another region."""

    def __init__(self, *, held_in: Region, asked_from: Region) -> None:
        super().__init__(f"held in {held_in}, asked from {asked_from}")
        self.held_in = held_in
        self.asked_from = asked_from


def guard_region(*, held_in: Region, asked_from: Region) -> None:
    """Raise unless the thing being touched belongs to the region asking for it."""
    if held_in is not asked_from:
        raise OutOfRegion(held_in=held_in, asked_from=asked_from)
