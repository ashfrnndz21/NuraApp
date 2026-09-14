# Backend

Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL, Alembic, pydantic v2, pytest. Async throughout. Structured logging with the profile id redacted outside the region.

- Every request carries a key context resolved by `app/keys/context.py`; repositories require it as a parameter, not a global.
- Facts are immutable; supersession is a new Fact pointing at the old one.
- Extraction returns fields with confidence; anything below threshold is marked `needs_confirm`, never guessed.
- Model calls go through `app/llm/` with the profile's region client; prompts live in `app/llm/prompts/` as files, not strings in code.
- Licensed drug data goes through `app/drugs/client.py`; tests use the fixture registry in `tests/fixtures/drugs/`.
- The WhatsApp provider is behind `app/channels/whatsapp/provider.py`; templates in `app/channels/whatsapp/templates/`.
- `make plain-words` runs `app/safety/plain_words.py` over every string tagged `@patient` in delivery, WhatsApp, consent (`app/consent/`: the wording a patient agrees to and the record he holds) and the strings catalogue.
