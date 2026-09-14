"""The process: one region, one database, the app API on top.

Settings are read once, here, and nowhere else. The code sender is the logging fixture
until a real SMS or email provider is chosen, which is why `make dev` prints the code in
the server log. Logging is set up so that line is seen.
"""

from __future__ import annotations

import logging

from app.channels.api import Providers, create_app
from app.db import make_engine, make_session_factory
from app.identity.providers import LoggingCodeSender
from app.settings import load_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")

settings = load_settings()
engine = make_engine(settings.database_url)
app = create_app(settings, make_session_factory(engine), Providers(code_sender=LoggingCodeSender()))
