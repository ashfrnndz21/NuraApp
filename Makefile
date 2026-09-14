.PHONY: setup dev migrate reset-db checkpoint test lint plain-words ios-test
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
# The logging code sender prints login codes to the terminal. Local runs only; see settings.py.
dev: export NURA_DEV_CODE_SENDER = 1
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
ios-test: ; cd ios && if [ -d Nura.xcodeproj ]; then DEV=$$(xcrun simctl list devices available | grep -m1 -oE 'iPhone [0-9]+[A-Za-z ]*' | sed 's/ *$$//'); echo "simulator: $$DEV"; xcodebuild test -scheme Nura -destination "platform=iOS Simulator,name=$$DEV"; else echo "ios-test: Nura.xcodeproj not generated yet (Session 10), skipping"; fi
