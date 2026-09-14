"""What one deployment needs to know about itself.

A process serves exactly one region and talks to exactly one database. Both are read once,
at startup, and passed down as parameters; nothing reaches for them from inside a repository.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from app.clock import FrozenClockOutsideDev
from app.regions import Region

STAFF_HANDLE = re.compile(r"^[a-z0-9_-]{1,32}$")
STAFF_TOKEN_MIN = 24
DEV_STAFF_TOKEN_PREFIX = "nura-dev-"


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
    visit_fixtures: str | None = None
    """NURA_VISIT_FIXTURES: the directory of visit transcripts the fixture summariser answers
    from (`app.reasoning.visits.summary.FixtureSummariser`). No live model call exists yet;
    without it the process refuses to start."""
    voice_fixtures: str | None = None
    """NURA_VOICE_FIXTURES: the directory of transcripts the fixture transcriber answers from
    (`app.ingestion.transcribe.FixtureTranscriber`). Set on a laptop; a speech provider in the
    region is a later adapter, and without either the process refuses to start."""
    speaker_fixtures: str | None = None
    """NURA_SPEAKER_FIXTURES: the directory the fixture speaker separator answers from
    (`app.ingestion.speakers.FixtureSeparator`), keyed by the digest of a consult recording.
    Optional: without it a recording is kept as one stretch by an unknown speaker
    (`Unseparated`), which claims nothing it did not hear (E02-05)."""
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
    reference_ranges: str = "fixture"
    """NURA_REFERENCE_RANGES: which reference-range table the lab trend reads (E09-01,
    `app.reasoning.ranges`). Only the fixture is built; any other name refuses to start."""
    review_staff: tuple[tuple[str, str], ...] = ()
    """NURA_REVIEW_STAFF_TOKENS: who may work the pharmacist's review queue (`/review/*`,
    E22-04, ADR 0007), as `handle:token` pairs separated by commas. Staff are not people on
    anyone's record and hold no patient key; the handle is what a decision is signed with.
    Unset, the queue answers nobody. A token is at least 24 characters, a handle is lowercase
    letters, digits, `-` and `_`; a laptop's token (`nura-dev-…`) only runs on a dev run."""
    frozen_clock: datetime | None = None
    """NURA_FROZEN_CLOCK: an instant with its offset (`2026-09-14T10:00:00+08:00`) the
    process's clock stands at from startup (`app.clock.install_frozen`), moved only by
    `POST /dev/clock`. For end-to-end runs that must not drift with the hour. Honoured only on
    a declared dev run: given without NURA_DEV_CODE_SENDER=1 the process refuses to start."""
    demo_mode: bool = False
    """NURA_DEMO_MODE=1: a deployment that runs on the fixture providers and says so on every
    screen, takes test numbers only and is wiped each night (`app.demo`, ADR 0008). The one way
    a process that is not a laptop may start on the fixtures. Exclusive with a dev run."""
    demo_login_code: str | None = None
    """NURA_DEMO_LOGIN_CODE: six digits, a secret in the platform's store. On a demo it is the
    code that signs a test number in (`app.identity.providers.DemoCodeSender`); the operator
    gives it to the people he invites. Required with NURA_DEMO_MODE=1, refused without it."""
    object_bucket_url: str | None = None
    """NURA_OBJECT_BUCKET_URL: the bucket artefact bytes go to, as its https base URL
    (`https://<bucket>.s3.ap-southeast-1.amazonaws.com`, or path-style
    `https://fly.storage.tigris.dev/<bucket>`), in this deployment's region
    (`app.ingestion.s3.S3ObjectStore`). A deployment's object store; NURA_OBJECT_STORE (a
    directory) is a laptop's, and a demo's when it has no bucket."""
    object_bucket_region: str | None = None
    """NURA_OBJECT_BUCKET_REGION: the region name the bucket signs requests with
    (`ap-southeast-1`; Tigris says `auto`)."""
    object_access_key_id: str | None = None
    """NURA_OBJECT_ACCESS_KEY_ID: the bucket's access key id. From the platform's secrets."""
    object_secret_access_key: str | None = None
    """NURA_OBJECT_SECRET_ACCESS_KEY: the bucket's secret key. From the platform's secrets,
    never the repo, never a log."""

    @property
    def fixtures_allowed(self) -> bool:
        """Whether the fixture providers may run: on a declared dev run, or a declared demo."""
        return self.dev_code_sender or self.demo_mode


class MissingSetting(RuntimeError):
    """A deployment that cannot name its region must not start."""


class DemoAndDevTogether(RuntimeError):
    """NURA_DEMO_MODE=1 with NURA_DEV_CODE_SENDER=1: a demo never prints a login code."""


_DEMO_CODE = re.compile(r"^[0-9]{6}$")


_POSTGRES_SCHEMES = ("postgres://", "postgresql://")


def database_url_for(url: str) -> str:
    """NURA_DATABASE_URL as SQLAlchemy's async engine wants it.

    A hosting platform hands out `postgres://…` or `postgresql://…` (Render's
    `connectionString`, Fly's `DATABASE_URL`); the engine needs the asyncpg driver named, as
    `postgresql+asyncpg://…`. The platform's `sslmode=` is libpq's word, which asyncpg takes
    as `ssl=` with the same values. Anything else — SQLite, a URL that already names its
    driver — is returned as it was given.
    """
    for scheme in _POSTGRES_SCHEMES:
        if url.startswith(scheme):
            url = "postgresql+asyncpg://" + url.removeprefix(scheme)
            break
    if url.startswith("postgresql+asyncpg://"):
        url = re.sub(r"([?&])sslmode=", r"\1ssl=", url)
    return url


class BadStaffTokens(RuntimeError):
    """The review queue's staff list is malformed, or carries a laptop's token outside a dev
    run. The process must not start on it."""


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Read NURA_REGION and NURA_DATABASE_URL. Both are required: neither has a safe default.

    NURA_DEV_CODE_SENDER is optional and its only safe default is off. NURA_OBJECT_STORE and
    NURA_PAPER_FIXTURES are optional here and checked by `main`, which refuses to serve
    without a store for the bytes or an extractor to read them.
    """
    source = os.environ if env is None else env
    try:
        region = Region(source["NURA_REGION"])
        database_url = database_url_for(source["NURA_DATABASE_URL"])
    except KeyError as missing:
        raise MissingSetting(f"{missing.args[0]} is not set") from missing
    dev_code_sender = source.get("NURA_DEV_CODE_SENDER", "") == "1"
    frozen_clock = _frozen_clock(source.get("NURA_FROZEN_CLOCK") or None, dev_run=dev_code_sender)
    demo_mode = source.get("NURA_DEMO_MODE", "") == "1"
    demo_login_code = source.get("NURA_DEMO_LOGIN_CODE") or None
    if demo_mode and dev_code_sender:
        raise DemoAndDevTogether(
            "NURA_DEMO_MODE=1 and NURA_DEV_CODE_SENDER=1 are exclusive: a demo prints no code"
        )
    if demo_mode and (demo_login_code is None or not _DEMO_CODE.match(demo_login_code)):
        raise MissingSetting("NURA_DEMO_MODE=1 needs NURA_DEMO_LOGIN_CODE: six digits, a secret")
    if not demo_mode and demo_login_code is not None:
        raise MissingSetting("NURA_DEMO_LOGIN_CODE is for a demo only (NURA_DEMO_MODE=1)")
    return Settings(
        region=region,
        database_url=database_url,
        dev_code_sender=dev_code_sender,
        object_store_root=source.get("NURA_OBJECT_STORE") or None,
        paper_fixtures=source.get("NURA_PAPER_FIXTURES") or None,
        visit_fixtures=source.get("NURA_VISIT_FIXTURES") or None,
        voice_fixtures=source.get("NURA_VOICE_FIXTURES") or None,
        feed_fixtures=source.get("NURA_FEED_FIXTURES") or None,
        speaker_fixtures=source.get("NURA_SPEAKER_FIXTURES") or None,
        drug_registry=source.get("NURA_DRUG_REGISTRY", "fixture"),
        web_dist=source.get("NURA_WEB_DIST") or None,
        whatsapp_provider=source.get("NURA_WHATSAPP_PROVIDER", "fixture"),
        whatsapp_number=source.get("NURA_WHATSAPP_NUMBER") or None,
        whatsapp_dev_secret=source.get("NURA_WHATSAPP_DEV_SECRET") or None,
        whatsapp_fixtures=source.get("NURA_WHATSAPP_FIXTURES") or None,
        reference_ranges=source.get("NURA_REFERENCE_RANGES", "fixture"),
        frozen_clock=frozen_clock,
        demo_mode=demo_mode,
        demo_login_code=demo_login_code,
        object_bucket_url=source.get("NURA_OBJECT_BUCKET_URL") or None,
        object_bucket_region=source.get("NURA_OBJECT_BUCKET_REGION") or None,
        object_access_key_id=source.get("NURA_OBJECT_ACCESS_KEY_ID") or None,
        object_secret_access_key=source.get("NURA_OBJECT_SECRET_ACCESS_KEY") or None,
        review_staff=_staff_tokens(
            source.get("NURA_REVIEW_STAFF_TOKENS") or None, dev_run=dev_code_sender
        ),
    )


def _staff_tokens(value: str | None, *, dev_run: bool) -> tuple[tuple[str, str], ...]:
    """NURA_REVIEW_STAFF_TOKENS, read strictly: `handle:token` pairs, each handle once."""
    if value is None:
        return ()
    staff: list[tuple[str, str]] = []
    for pair in (part.strip() for part in value.split(",") if part.strip()):
        handle, sep, token = pair.partition(":")
        handle, token = handle.strip(), token.strip()
        if not sep or not STAFF_HANDLE.match(handle):
            raise BadStaffTokens("each staff entry is handle:token, the handle lowercase")
        if len(token) < STAFF_TOKEN_MIN:
            raise BadStaffTokens(f"the token for {handle} is shorter than {STAFF_TOKEN_MIN}")
        if token.startswith(DEV_STAFF_TOKEN_PREFIX) and not dev_run:
            raise BadStaffTokens(f"the token for {handle} is a laptop's token; dev runs only")
        if any(handle == known for known, _ in staff):
            raise BadStaffTokens(f"{handle} is on the staff list twice")
        staff.append((handle, token))
    return tuple(staff)


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
