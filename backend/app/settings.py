"""What one deployment needs to know about itself.

A process serves exactly one region and talks to exactly one database. Both are read once,
at startup, and passed down as parameters; nothing reaches for them from inside a repository.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from app.clock import FrozenClockOutsideDev
from app.regions import Region


@dataclass(frozen=True, slots=True)
class Settings:
    region: Region
    database_url: str
    dev_code_sender: bool = False
    """Only with NURA_DEV_CODE_SENDER=1 may the logging code sender run. It prints login
    codes to the server log, which is fine on a laptop and account takeover anywhere else."""
    object_store_root: str | None = None
    """NURA_OBJECT_STORE: the directory the local object store keeps artefact bytes under,
    one subdirectory per region (`app.ingestion.objects.LocalObjectStore`). No default: a
    deployment that cannot say where health data goes must not start."""
    paper_fixtures: str | None = None
    """NURA_PAPER_FIXTURES: the directory of paper fixtures the fixture extractor answers
    from (`app.ingestion.extract.FixtureExtractor`). Set on a laptop; the real extractor is
    a later adapter, and without either the process refuses to start."""
    voice_fixtures: str | None = None
    """NURA_VOICE_FIXTURES: the directory of transcripts the fixture transcriber answers from
    (`app.ingestion.transcribe.FixtureTranscriber`). Set on a laptop; a speech provider in the
    region is a later adapter, and without either the process refuses to start."""
    feed_fixtures: str | None = None
    """NURA_FEED_FIXTURES: the directory the fixture searcher and compressor answer from
    (`app.delivery.feed.compress`). Set on a laptop; the real fetcher and the grounded model
    call are later adapters behind the same two ports, and without either the process
    refuses to start."""
    drug_registry: str = "fixture"
    """NURA_DRUG_REGISTRY: which licensed drug registry the deployment runs on
    (`app.drugs.client`). Only the fixture is built; a name this build does not have refuses
    to start."""
    web_dist: str | None = None
    """NURA_WEB_DIST: the built web client (`web/dist`, from `make build-web`). When the
    directory exists the API serves it at `/app`, so one origin serves the app and its API;
    when it is unset or missing there is no `/app` and the API is unchanged."""
    whatsapp_provider: str = "fixture"
    """NURA_WHATSAPP_PROVIDER: which business solution provider carries WhatsApp
    (`app.channels.whatsapp.provider`). Only the fixture is built, and it runs only on a
    declared dev run; a name this build does not have refuses to start."""
    whatsapp_number: str | None = None
    """NURA_WHATSAPP_NUMBER: the business number for this region, E.164. Unset on a dev run
    means the sandbox placeholder for the region (`app.channels.whatsapp.config`)."""
    whatsapp_dev_secret: str | None = None
    """NURA_WHATSAPP_DEV_SECRET: the fixed secret the fixture provider signs webhooks with and
    accepts as the verify token. A laptop's secret, from the environment; never in the repo."""
    whatsapp_fixtures: str | None = None
    """NURA_WHATSAPP_FIXTURES: the directory the fixture provider serves media from
    (`backend/tests/fixtures/whatsapp/`), until a real provider fetches it."""
    frozen_clock: datetime | None = None
    """NURA_FROZEN_CLOCK: an instant with its offset (`2026-09-14T10:00:00+08:00`) the
    process's clock stands at from startup (`app.clock.install_frozen`), moved only by
    `POST /dev/clock`. For end-to-end runs that must not drift with the hour. Honoured only on
    a declared dev run: given without NURA_DEV_CODE_SENDER=1 the process refuses to start."""


class MissingSetting(RuntimeError):
    """A deployment that cannot name its region must not start."""


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Read NURA_REGION and NURA_DATABASE_URL. Both are required: neither has a safe default.

    NURA_DEV_CODE_SENDER is optional and its only safe default is off. NURA_OBJECT_STORE and
    NURA_PAPER_FIXTURES are optional here and checked by `main`, which refuses to serve
    without a store for the bytes or an extractor to read them.
    """
    source = os.environ if env is None else env
    try:
        region = Region(source["NURA_REGION"])
        database_url = source["NURA_DATABASE_URL"]
    except KeyError as missing:
        raise MissingSetting(f"{missing.args[0]} is not set") from missing
    dev_code_sender = source.get("NURA_DEV_CODE_SENDER", "") == "1"
    frozen_clock = _frozen_clock(source.get("NURA_FROZEN_CLOCK") or None, dev_run=dev_code_sender)
    return Settings(
        region=region,
        database_url=database_url,
        dev_code_sender=dev_code_sender,
        object_store_root=source.get("NURA_OBJECT_STORE") or None,
        paper_fixtures=source.get("NURA_PAPER_FIXTURES") or None,
        voice_fixtures=source.get("NURA_VOICE_FIXTURES") or None,
        feed_fixtures=source.get("NURA_FEED_FIXTURES") or None,
        drug_registry=source.get("NURA_DRUG_REGISTRY", "fixture"),
        web_dist=source.get("NURA_WEB_DIST") or None,
        whatsapp_provider=source.get("NURA_WHATSAPP_PROVIDER", "fixture"),
        whatsapp_number=source.get("NURA_WHATSAPP_NUMBER") or None,
        whatsapp_dev_secret=source.get("NURA_WHATSAPP_DEV_SECRET") or None,
        whatsapp_fixtures=source.get("NURA_WHATSAPP_FIXTURES") or None,
        frozen_clock=frozen_clock,
    )


def _frozen_clock(value: str | None, *, dev_run: bool) -> datetime | None:
    """NURA_FROZEN_CLOCK, read strictly: only on a dev run, and only an instant with an offset."""
    if value is None:
        return None
    if not dev_run:
        raise FrozenClockOutsideDev("NURA_FROZEN_CLOCK is for a declared dev run only (NURA_DEV_CODE_SENDER=1)")
    try:
        at = datetime.fromisoformat(value)
    except ValueError as bad:
        raise FrozenClockOutsideDev(f"NURA_FROZEN_CLOCK is not an instant: {value!r}") from bad
    if at.tzinfo is None:
        raise FrozenClockOutsideDev("NURA_FROZEN_CLOCK needs an offset, as in 2026-09-14T10:00:00+08:00")
    return at
