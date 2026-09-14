.PHONY: dev migrate test lint plain-words ios-test
# A local run needs a region and a database. These are the dev defaults, on your Mac only;
# the app itself has no default for either (see backend/app/settings.py) and a deployment
# sets both explicitly.
dev migrate: export NURA_REGION ?= SG
dev migrate: export NURA_DATABASE_URL ?= sqlite+aiosqlite:///./dev.db
migrate: ; cd backend && alembic upgrade heads
dev: migrate ; cd backend && uvicorn app.main:app --reload
test: ; cd backend && pytest -q
lint: ; cd backend && ruff check . && mypy app
plain-words: ; cd backend && if [ -f app/safety/plain_words.py ]; then python -m app.safety.plain_words; else echo "plain-words: app/safety/plain_words.py not built yet (Session 6), skipping"; fi
ios-test: ; cd ios && if [ -d Nura.xcodeproj ]; then DEV=$$(xcrun simctl list devices available | grep -m1 -oE 'iPhone [0-9]+[A-Za-z ]*' | sed 's/ *$$//'); echo "simulator: $$DEV"; xcodebuild test -scheme Nura -destination "platform=iOS Simulator,name=$$DEV"; else echo "ios-test: Nura.xcodeproj not generated yet (Session 10), skipping"; fi
