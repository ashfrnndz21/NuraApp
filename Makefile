.PHONY: setup dev migrate reset-db checkpoint test lint plain-words ios-test web build-web web-test web-e2e
# Every backend target runs `python3 -m …`: the Python 3.12 that `make setup` installed the
# backend into, never whatever bare `python` on the PATH happens to be.
setup: ; cd backend && python3 -m pip install -e ".[dev]"
# A local run needs a region and a database. These are the dev defaults, on your Mac only;
# the app itself has no default for either (see backend/app/settings.py) and a deployment
# sets both explicitly.
dev migrate: export NURA_REGION ?= SG
dev migrate: export NURA_DATABASE_URL ?= sqlite+aiosqlite:///./dev.db
# Where a local run keeps artefact bytes (gitignored, one subdirectory per region), and the
# paper fixtures the fixture extractor reads photos from until the real one exists (E02).
dev: export NURA_OBJECT_STORE ?= var/objects
dev: export NURA_PAPER_FIXTURES ?= tests/fixtures/paper
# The transcripts the fixture transcriber answers from, keyed by the digest of the bytes (E02-06).
dev: export NURA_VOICE_FIXTURES ?= tests/fixtures/voice
# The feed's fixture searcher and compressor (E21) answer from here until the real fetcher
# and the grounded model call exist behind the same two ports.
dev: export NURA_FEED_FIXTURES ?= tests/fixtures/feed
# The logging code sender prints login codes to the terminal. Local runs only; see settings.py.
dev: export NURA_DEV_CODE_SENDER = 1
# NURA_FROZEN_CLOCK=2026-09-14T10:00:00+08:00 stands the dev run's clock still (end-to-end runs:
# web/playwright.config.ts sets it); POST /dev/clock moves it. Refused outside a dev run.
# The built web client (`make build-web`), served by the API at http://127.0.0.1:8000/app when
# the directory exists; without a build there is no /app and nothing else changes.
dev: export NURA_WEB_DIST ?= ../web/dist
# The fixture WhatsApp provider (E19): sends into memory, serves media from the fixtures, and
# signs webhooks with a laptop-only secret. No Meta call is made; see app/channels/whatsapp/.
dev: export NURA_WHATSAPP_PROVIDER ?= fixture
dev: export NURA_WHATSAPP_DEV_SECRET ?= nura-dev-webhook-secret
dev: export NURA_WHATSAPP_FIXTURES ?= tests/fixtures/whatsapp
migrate: ; cd backend && python3 -m alembic upgrade heads
# The server log is also written to backend/.dev.log (gitignored, fresh on every start) so
# that `make checkpoint` in another terminal can read the login codes the sender prints.
dev: migrate ; cd backend && python3 -m uvicorn app.main:app --reload --no-access-log 2>&1 | tee .dev.log
# Start over on a clean local database: stop `make dev` first, then run this.
reset-db: ; rm -f backend/dev.db backend/dev.db-journal && $(MAKE) migrate
# Walk checkpoint N from docs/checkpoints.md against the running dev server, over HTTP.
checkpoint: ; cd backend && python3 -m scripts.checkpoint $(N)
test: ; cd backend && python3 -m pytest -q
lint: ; cd backend && python3 -m ruff check . && python3 -m mypy app
# Every patient string under the paths in .claude/rules/patient-strings.md, against docs/plain-words.md.
# `python3 -m app.safety.plain_words --explain` says what each rule checks; `--text "..."` checks one line.
plain-words: ; cd backend && python3 -m app.safety.plain_words
# The web client (ADR 0001). `make web` is the dev server on http://127.0.0.1:5173/app/, proxying
# /api to the backend `make dev` serves; `--host` also answers on the Mac's LAN address so a phone
# on the same Wi-Fi can open it. `make build-web` writes web/dist, which `make dev` then serves at
# /app. `npm install` runs once, when node_modules is missing.
web: web/node_modules ; cd web && npm run dev -- --host
build-web: web/node_modules ; cd web && npm run build
web-test: web/node_modules ; cd web && npm test
web-e2e: web/node_modules ; cd web && npm run e2e
web/node_modules: web/package.json web/package-lock.json ; cd web && npm ci
ios-test: ; cd ios && if [ -d Nura.xcodeproj ]; then DEV=$$(xcrun simctl list devices available | grep -m1 -oE 'iPhone [0-9]+[A-Za-z ]*' | sed 's/ *$$//'); echo "simulator: $$DEV"; xcodebuild test -scheme Nura -destination "platform=iOS Simulator,name=$$DEV"; else echo "ios-test: Nura.xcodeproj not generated yet (Session 10), skipping"; fi
