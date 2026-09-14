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
    return Settings(
        region=region,
        database_url=database_url,
        dev_code_sender=dev_code_sender,
        object_store_root=source.get("NURA_OBJECT_STORE") or None,
        paper_fixtures=source.get("NURA_PAPER_FIXTURES") or None,
        voice_fixtures=source.get("NURA_VOICE_FIXTURES") or None,
        feed_fixtures=source.get("NURA_FEED_FIXTURES") or None,
        drug_registry=source.get("NURA_DRUG_REGISTRY", "fixture"),
        whatsapp_provider=source.get("NURA_WHATSAPP_PROVIDER", "fixture"),
        whatsapp_number=source.get("NURA_WHATSAPP_NUMBER") or None,
        whatsapp_dev_secret=source.get("NURA_WHATSAPP_DEV_SECRET") or None,
        whatsapp_fixtures=source.get("NURA_WHATSAPP_FIXTURES") or None,
    )
