.PHONY: dev test lint plain-words ios-test
dev: ; cd backend && uvicorn app.main:app --reload
test: ; cd backend && pytest -q
lint: ; cd backend && ruff check . && mypy app
plain-words: ; cd backend && if [ -f app/safety/plain_words.py ]; then python -m app.safety.plain_words; else echo "plain-words: app/safety/plain_words.py not built yet (Session 6), skipping"; fi
ios-test: ; cd ios && if [ -d Nura.xcodeproj ]; then xcodebuild test -scheme Nura -destination 'platform=iOS Simulator,name=iPhone 16'; else echo "ios-test: Nura.xcodeproj not generated yet (Session 10), skipping"; fi
