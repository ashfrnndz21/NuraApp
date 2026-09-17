"""The seams the web client rests on (W1, ADR 0001).

Every route answers under `/api` exactly as it does at the root; the consent words a person
is asked to agree to can be read before he has a profile; a built web client, when the
deployment names one, is served at `/app` from the same origin; and the plain-words verifier
reads the web client's strings files.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.channels.api import Providers, create_app
from app.channels.whatsapp.provider import FixtureProvider
from app.consent.models import ConsentPurpose
from app.consent.texts import current_version
from app.db import make_session_factory
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.drugs.fixture import FixtureRegistry
from app.identity.providers import LoggingCodeSender
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.transcribe import FixtureTranscriber
from app.reasoning.visits.summary import FixtureSummariser
from app.regions import Region
from app.safety.plain_words import (
    RULES_FILE,
    check_files,
    patient_paths,
    repo_root,
    strings_in_typescript,
)
from app.settings import Settings
from tests.conftest import FEED, STAFF_TOKEN, VISITS, WHATSAPP_FIXTURES, WHATSAPP_SECRET, Deployment
from tests.paper import PAPER
from tests.voice_notes import VOICE


async def test_every_route_answers_under_api_too(client: AsyncClient) -> None:
    assert (await client.get("/api/health")).json() == {"status": "ok"}
    root = await client.get("/me")
    prefixed = await client.get("/api/me")
    assert (root.status_code, root.json()) == (prefixed.status_code, prefixed.json())
    assert prefixed.json() == {"refusal": "NoSession"}


async def test_api_copy_is_not_in_the_openapi_page(client: AsyncClient) -> None:
    paths = (await client.get("/openapi.json")).json()["paths"]
    assert "/me" in paths and "/api/me" not in paths


async def test_consent_wording_is_todays_words_in_his_language(client: AsyncClient) -> None:
    got = (await client.get("/api/consent/wording", params={"language": "ms"})).json()
    assert got["purpose"] == "hold_health_record"
    assert got["version"] == current_version(ConsentPurpose.HOLD_HEALTH_RECORD)
    assert got["language"] == "ms" and got["region"] == "SG"
    assert got["lines"][1] == "Semuanya kekal di Singapura."
    # A language Nura does not speak falls back to English rather than guessing.
    english = (await client.get("/consent/wording", params={"language": "fr"})).json()
    assert english["language"] == "en" and english["lines"][1] == "They never leave Singapore."


async def test_the_words_open_a_profile(deployment: Deployment) -> None:
    """The version the route hands out is the one `POST /profiles/mine` accepts."""
    client = deployment.client
    await client.post("/api/auth/phone/start", json={"phone_e164": "+6591110001"})
    code = deployment.sender.last_code("+6591110001")
    token = (
        await client.post(
            "/api/auth/phone/verify", json={"phone_e164": "+6591110001", "code": code}
        )
    ).json()["token"]
    words = (await client.get("/api/consent/wording", params={"language": "en"})).json()
    opened = await client.post(
        "/api/profiles/mine",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "consent": {
                "wording_version": words["version"],
                "language": "en",
                "captured_via": "app",
            },
            "display_name": "Pa",
            "language": "en",
        },
    )
    assert opened.status_code == 201, opened.text
    assert opened.json()["standing"] == "owner"


def _app(web_dist: str | None, *, review_origin: str | None = None) -> AsyncClient:
    """A deployment that names (or does not name) a built web client, and (or does not)
    a review origin (#145)."""
    settings = Settings(
        region=Region.SG,
        database_url="sqlite+aiosqlite://",
        dev_code_sender=True,
        web_dist=web_dist,
        review_origin=review_origin,
        review_staff=(("pharmacist", STAFF_TOKEN),),
    )
    root = Path(tempfile.mkdtemp(prefix="nura-objects-"))
    providers = Providers(
        code_sender=LoggingCodeSender(reveal=True),
        object_store=LocalObjectStore(root, Region.SG),
        extractor=FixtureExtractor(PAPER),
        transcriber=FixtureTranscriber(VOICE, Region.SG),
        summariser=FixtureSummariser(VISITS),
        searcher=FixtureSearcher(FEED),
        compressor=FixtureCompressor(FEED),
        drug_registry=FixtureRegistry.load(),
        whatsapp=FixtureProvider(secret=WHATSAPP_SECRET, fixtures=WHATSAPP_FIXTURES),
    )
    engine = create_async_engine(settings.database_url)
    app = create_app(settings, make_session_factory(engine), providers)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://nura.test")


async def test_a_built_web_client_is_served_at_app(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<title>Nura</title>", encoding="utf-8")
    async with _app(str(dist)) as client:
        page = await client.get("/app/")
        assert page.status_code == 200 and "<title>Nura</title>" in page.text
        assert (await client.get("/api/health")).json() == {"status": "ok"}


async def test_no_web_client_means_no_app_route(tmp_path: Path) -> None:
    async with _app(str(tmp_path / "missing")) as client:
        assert (await client.get("/app/")).status_code == 404
    async with _app(None) as client:
        assert (await client.get("/app/")).status_code == 404


# --- #145: the review queue served from its own origin, before real data ----------------------


def _dist_with_review(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "review").mkdir(parents=True)
    (dist / "index.html").write_text("<title>Nura</title>", encoding="utf-8")
    (dist / "review" / "index.html").write_text("<title>Nura review</title>", encoding="utf-8")
    return dist


async def test_unset_the_review_queue_stays_on_the_apps_own_origin(tmp_path: Path) -> None:
    """The demo posture, unchanged: no `NURA_REVIEW_ORIGIN` means no split at all. (The
    review API itself — staff-only, hardened once split — is covered against a migrated
    database in `tests/test_review_queue.py`, not the bare engine this module uses.)"""
    dist = _dist_with_review(tmp_path)
    async with _app(str(dist)) as client:
        page = await client.get("/app/review/")
        assert page.status_code == 200 and "Nura review" in page.text
        assert "Content-Security-Policy" not in page.headers


async def test_named_the_review_queue_answers_only_on_its_own_host(tmp_path: Path) -> None:
    dist = _dist_with_review(tmp_path)
    async with _app(str(dist), review_origin="review.nura.test") as client:
        # The patient's own host never serves the review page, whatever is asked.
        blocked = await client.get("/app/review/")
        assert blocked.status_code == 404 and blocked.json() == {"refusal": "WrongOrigin"}
        blocked_api = await client.get("/review/status")
        assert blocked_api.status_code == 404 and blocked_api.json() == {"refusal": "WrongOrigin"}
        blocked_api_prefixed = await client.get("/api/review/status")
        assert blocked_api_prefixed.status_code == 404
        # The patient app itself is unaffected on its own host.
        app_page = await client.get("/app/")
        assert app_page.status_code == 200 and "<title>Nura</title>" in app_page.text
        # On the review host, the review page answers, hardened — its CSP is stricter than,
        # and never shared with, the patient app's (which sets none by default).
        review_headers = {"host": "review.nura.test"}
        page = await client.get("/app/review/", headers=review_headers)
        assert page.status_code == 200 and "Nura review" in page.text
        assert page.headers["Content-Security-Policy"] == (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'none'"
        )
        assert page.headers["X-Frame-Options"] == "DENY"
        # ...and the patient app itself is refused on the review host, both ways, while a
        # health check (no secret in the answer) still reaches either hostname.
        assert (await client.get("/app/", headers=review_headers)).status_code == 404
        assert (await client.get("/openapi.json", headers=review_headers)).status_code == 404
        health = await client.get("/api/health", headers=review_headers)
        assert health.status_code == 200 and health.json() == {"status": "ok"}


TS = """
export const en = {
  // @patient
  greeting: "Good morning, {name}.",
  // @patient headline
  today: "Today",
  // @patient
  consent: [
    "Nura keeps your papers.",
    "They never leave Singapore.",
  ],
  code: "Type the 6 digits from the message.", // @patient
  notForHim: "internal-key",
  // @patient action
  visit: {
    line: "Mei will drive you on Thursday at 10.",
  },
  old: "Dose logged.", // @patient
  older: "Dose logged.", // @patient  // plain-words: history, not shown
};
"""


def test_typescript_reader_finds_tagged_strings_and_only_those(tmp_path: Path) -> None:
    path = tmp_path / "en.ts"
    path.write_text(TS, encoding="utf-8")
    found = strings_in_typescript(path)
    by_text = {s.text: s for s in found}
    assert set(by_text) == {
        "Good morning, {name}.",
        "Today",
        "Nura keeps your papers.",
        "They never leave Singapore.",
        "Type the 6 digits from the message.",
        "Mei will drive you on Thursday at 10.",
        "Dose logged.",
    }
    assert by_text["Today"].kind == "headline"
    assert by_text["Mei will drive you on Thursday at 10."].kind == "action"
    assert by_text["They never leave Singapore."].line == 10
    assert all(s.language == "en" for s in found)
    exempt = [s for s in found if s.exempt]
    assert [s.line for s in exempt] == [19]
    report = check_files([path])
    assert not report.ok
    assert any("Dose logged." in f.text and f.line == 18 for f in report.failures)
    assert not any(f.line == 19 for f in report.failures)


def test_a_mention_of_the_tag_in_a_comment_is_not_a_tag(tmp_path: Path) -> None:
    """The doc comment in `web/src/strings/types.ts` names the tag; nothing there is shown."""
    path = tmp_path / "types.ts"
    path.write_text(
        "/** Every property carries a `// @patient [kind]` tag on the line above it.\n"
        " * The `// @patient` tag, and `plain-words` too, are explained here. */\n"
        '// A line comment that says // @patient is not a tag either: "no."\n'
        'export const taken = "You took it."; // @patient\n',
        encoding="utf-8",
    )
    assert [s.text for s in strings_in_typescript(path)] == ["You took it."]


def test_typescript_reader_takes_the_language_from_the_file_name(tmp_path: Path) -> None:
    ms = tmp_path / "ms.ts"
    ms.write_text(
        'export const ms = {\n  // @patient\n  taken: "Sudah ambil.",\n};\n', encoding="utf-8"
    )
    zh = tmp_path / "zh.ts"
    zh.write_text('export const zh = {\n  // @patient\n  taken: "吃了。",\n};\n', encoding="utf-8")
    assert [s.language for s in strings_in_typescript(ms)] == ["ms"]
    assert [s.language for s in strings_in_typescript(zh)] == ["zh"]


def test_verifier_walks_web_strings_with_the_rest() -> None:
    assert "web/src/strings/**" in patient_paths((repo_root() / RULES_FILE).read_text())
