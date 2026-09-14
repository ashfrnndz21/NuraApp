"""What one deployment needs to know about itself.

A process serves exactly one region and talks to exactly one database. Both are read once,
at startup, and passed down as parameters; nothing reaches for them from inside a repository.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from app.regions import Region


@dataclass(frozen=True, slots=True)
class Settings:
    region: Region
    database_url: str
    dev_code_sender: bool = False
    """Only with NURA_DEV_CODE_SENDER=1 may the logging code sender run. It prints login
    codes to the server log, which is fine on a laptop and account takeover anywhere else."""


class MissingSetting(RuntimeError):
    """A deployment that cannot name its region must not start."""


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Read NURA_REGION and NURA_DATABASE_URL. Both are required: neither has a safe default.

    NURA_DEV_CODE_SENDER is the one optional setting, and its only safe default is off.
    """
    source = os.environ if env is None else env
    try:
        region = Region(source["NURA_REGION"])
        database_url = source["NURA_DATABASE_URL"]
    except KeyError as missing:
        raise MissingSetting(f"{missing.args[0]} is not set") from missing
    dev_code_sender = source.get("NURA_DEV_CODE_SENDER", "") == "1"
    return Settings(region=region, database_url=database_url, dev_code_sender=dev_code_sender)
