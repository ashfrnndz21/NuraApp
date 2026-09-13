.PHONY: dev test lint plain-words ios-test
dev: ; cd backend && uvicorn app.main:app --reload
test: ; cd backend && pytest -q
lint: ; cd backend && ruff check . && mypy app
plain-words: ; cd backend && python -m app.safety.plain_words
ios-test: ; cd ios && xcodebuild test -scheme Nura -destination 'platform=iOS Simulator,name=iPhone 16'
