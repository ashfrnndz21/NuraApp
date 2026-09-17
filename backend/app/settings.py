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
    red_flag_tiers: bool = False
    """NURA_RED_FLAG_TIERS=1: the red-flag tiers of ADR 0010 are signed off by a clinician
    (docs/trust/clinical-sign-off.md) and may reach a family — the doctor today in his hours,
    the hospital on his insurance or rest and the morning out of them, a fall on a blood thinner
    raised to the ambulance. Unset, every red flag's step is the ambulance, the stricter step
    the not-feeling-well card already gives. A dev run sets it (`make dev`)."""
    object_store_root: str | None = None
    """NURA_OBJECT_STORE: the directory the local object store keeps artefact bytes under,
    one subdirectory per region (`app.ingestion.objects.LocalObjectStore`). No default: a
    deployment that cannot say where health data goes must not start."""
    paper_fixtures: str | None = None
    """NURA_PAPER_FIXTURES: the directory of paper fixtures the fixture extractor answers
    from (`app.ingestion.extract.FixtureExtractor`). Set on a laptop; the real extractor is
    a later adapter, and without either the process refuses to start."""
    extractor: str = "fixture"
    """NURA_EXTRACTOR: which reader answers `POST /profiles/{id}/imports` and the photo
    capture route (`app.ingestion.extract_provider.extractor_for`). `fixture` (the default)
    answers from NURA_PAPER_FIXTURES; `claude` is the Claude-backed reader
    (`app.ingestion.claude_extract.ClaudeExtractor`), which only builds on a declared demo
    (NURA_DEMO_MODE=1) because Anthropic's first-party API does not process in SG or MY and
    no in-region provider exists yet (ADR 0017) — a laptop dev run stays on the fixture. A
    name this build does not have refuses to start."""
    anthropic_api_key: str | None = None
    """NURA_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY): the one key every Claude-backed adapter —
    the extractor, the narrator, `NURA_SEARCHER=claude`, `NURA_COMPRESSOR=claude` — calls the Anthropic API with,
    from the platform's secrets, never the repo, never a log. Unset, the SDK's own
    ANTHROPIC_API_KEY is used if the environment has it; with neither, the extractor refuses
    to build."""
    narrator: str = "fixture"
    """NURA_NARRATOR: what says Ask's and Find's trace steps aloud
    (`app.search.narrator_provider.narrator_for`). `fixture` (the default) is today's
    behaviour, unchanged — each step's catalogue label, every time; `claude` is the
    Claude-backed narrator (`app.llm.narrate.ClaudeNarrator`), which only builds on
    a declared demo (NURA_DEMO_MODE=1) because Anthropic's first-party API does not process
    in SG or MY and no in-region provider exists yet (ADR 0017) — a laptop dev run stays on
    the fixture. A name this build does not have refuses to start."""
    asker: str = "rule"
    """NURA_ASKER: which asker answers `POST /profiles/{id}/ask/stream`
    (`app.search.asker_provider.asker_for`). `rule` (the default) is today's behaviour,
    unchanged — a rule-based retriever over templates (`app.search.ask.recall_stream`);
    `claude` is the agent (`app.llm.ask_agent.ClaudeAsker`), which decides for itself what to
    look at and only builds on a declared demo (NURA_DEMO_MODE=1) because Anthropic's
    first-party API does not process in SG or MY and no in-region provider exists yet
    (ADR 0017) — a laptop dev run stays on `rule`. A name this build does not have refuses to
    start."""
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
    (`app.delivery.feed.compress`), and the clip renderer's stills. Set on a laptop; a real
    fetcher and a grounded model call are adapters behind the same two ports
    (`NURA_SEARCHER`/`NURA_COMPRESSOR`), and without one of the two the process refuses to
    start."""
    searcher: str = "fixture"
    """NURA_SEARCHER: which adapter answers the `Searcher` port (`app.delivery.feed.compress`).
    `fixture` (the default) answers from NURA_FEED_FIXTURES; `claude` reads the allowlist for
    real through Claude's web search and fetch tools (`app.delivery.feed.claude_adapters`) and
    runs only on a declared demo (`NURA_DEMO_MODE=1`) with `ANTHROPIC_API_KEY` set — no
    in-region provider exists yet. Any other name refuses to start."""
    compressor: str = "fixture"
    """NURA_COMPRESSOR: which adapter answers the `Compressor` port. `fixture` (the default)
    answers from NURA_FEED_FIXTURES; `claude` grounds a plain-words card on the fetched page
    through Claude's structured output (`app.delivery.feed.claude_adapters`), gated the same
    way as NURA_SEARCHER=claude. Any other name refuses to start."""
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
    vapid_public_key: str | None = None
    """NURA_VAPID_PUBLIC_KEY: this deployment's Web Push key, the uncompressed P-256 point in
    base64url. The home-screen app subscribes with it (`GET /deployment`)."""
    vapid_private_key: str | None = None
    """NURA_VAPID_PRIVATE_KEY: the private half, 32 bytes in base64url. It signs every push
    (RFC 8292). From the platform's secrets, never the repo, never a log."""
    vapid_subject: str | None = None
    """NURA_VAPID_SUBJECT: who a push service may contact about these pushes, `mailto:` or
    `https:`. The three VAPID settings go together; with them the deployment pushes by Web
    Push (`app.delivery.push.WebPush`), without them it has no real push sender."""
    account_retention_days: int = 30
    """NURA_ACCOUNT_RETENTION_DAYS: how long a closed account's papers wait before they are
    deleted, while his yes can still undo the closing (#143). 30 until counsel says otherwise
    (docs/trust/account-closure.md)."""
    review_origin: str | None = None
    """NURA_REVIEW_ORIGIN: the hostname (`review.nura.example`, no scheme, no path) the
    pharmacist's review queue is served from once a deployment holds real data (#145,
    docs/adr/0008-demo-mode.md "Before real data"). Unset — every demo and every laptop run —
    `/app/review` and `/review/*` stay on the same origin as the patient app, W6 (#137)'s
    posture, fine while nothing behind either is real. Named, `ReviewOrigin` (`app.channels.api`)
    splits the two by the Host header alone: the review surface answers only on this host, the
    rest of the app answers on every other host, and a request for either from the wrong one
    is refused — so no patient-origin script or storage can ever reach a staff session, and a
    review-origin page never serves the patient app."""

    @property
    def fixtures_allowed(self) -> bool:
        """Whether the fixture providers may run: on a declared dev run, or a declared demo."""
        return self.dev_code_sender or self.demo_mode


class MissingSetting(RuntimeError):
    """A deployment that cannot name its region must not start."""


class DemoAndDevTogether(RuntimeError):
    """NURA_DEMO_MODE=1 with NURA_DEV_CODE_SENDER=1: a demo never prints a login code."""


_DEMO_CODE = re.compile(r"^[0-9]{6}$")
VAPID = ("PUBLIC_KEY", "PRIVATE_KEY", "SUBJECT")
"""The three NURA_VAPID_* settings: all of them, or none."""


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


class BadReviewOrigin(RuntimeError):
    """NURA_REVIEW_ORIGIN is not a bare hostname: no scheme, no path, no port, lowercase."""


_HOSTNAME = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)


def _review_origin(value: str | None) -> str | None:
    """NURA_REVIEW_ORIGIN, read strictly: a bare hostname with at least one dot (#145) — a
    scheme, a path, a port or an IP address is refused rather than silently stripped."""
    if value is None or not value.strip():
        return None
    origin = value.strip().lower()
    if not _HOSTNAME.match(origin):
        raise BadReviewOrigin(
            "NURA_REVIEW_ORIGIN is a bare hostname (review.nura.example), no scheme or path"
        )
    return origin


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
    vapid = {name: source.get(f"NURA_VAPID_{name}") or None for name in VAPID}
    if any(vapid.values()) and not all(vapid.values()):
        raise MissingSetting(
            "NURA_VAPID_PUBLIC_KEY, NURA_VAPID_PRIVATE_KEY and NURA_VAPID_SUBJECT go together"
        )
    subject = vapid["SUBJECT"]
    if subject is not None and not subject.startswith(("mailto:", "https://")):
        raise MissingSetting("NURA_VAPID_SUBJECT is a mailto: address or an https: page")
    retention = source.get("NURA_ACCOUNT_RETENTION_DAYS") or "30"
    if not retention.isdigit() or int(retention) < 1:
        raise MissingSetting("NURA_ACCOUNT_RETENTION_DAYS is a whole number of days, at least 1")
    return Settings(
        region=region,
        database_url=database_url,
        dev_code_sender=dev_code_sender,
        red_flag_tiers=source.get("NURA_RED_FLAG_TIERS", "") == "1",
        object_store_root=source.get("NURA_OBJECT_STORE") or None,
        paper_fixtures=source.get("NURA_PAPER_FIXTURES") or None,
        extractor=source.get("NURA_EXTRACTOR", "fixture"),
        anthropic_api_key=source.get("NURA_ANTHROPIC_API_KEY") or source.get("ANTHROPIC_API_KEY") or None,
        narrator=source.get("NURA_NARRATOR", "fixture"),
        asker=source.get("NURA_ASKER", "rule"),
        visit_fixtures=source.get("NURA_VISIT_FIXTURES") or None,
        voice_fixtures=source.get("NURA_VOICE_FIXTURES") or None,
        feed_fixtures=source.get("NURA_FEED_FIXTURES") or None,
        searcher=source.get("NURA_SEARCHER", "fixture"),
        compressor=source.get("NURA_COMPRESSOR", "fixture"),
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
        vapid_public_key=vapid["PUBLIC_KEY"],
        vapid_private_key=vapid["PRIVATE_KEY"],
        vapid_subject=subject,
        account_retention_days=int(retention),
        review_staff=_staff_tokens(
            source.get("NURA_REVIEW_STAFF_TOKENS") or None, dev_run=dev_code_sender
        ),
        review_origin=_review_origin(source.get("NURA_REVIEW_ORIGIN")),
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
        raise FrozenClockOutsideDev(
            "NURA_FROZEN_CLOCK is for a declared dev run only (NURA_DEV_CODE_SENDER=1)"
        )
    try:
        at = datetime.fromisoformat(value)
    except ValueError as bad:
        raise FrozenClockOutsideDev(f"NURA_FROZEN_CLOCK is not an instant: {value!r}") from bad
    if at.tzinfo is None:
        raise FrozenClockOutsideDev(
            "NURA_FROZEN_CLOCK needs an offset, as in 2026-09-14T10:00:00+08:00"
        )
    return at
