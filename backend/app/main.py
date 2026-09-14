"""The process: one region, one database, the app API on top.

Settings are read once, here, and nowhere else. The code sender comes from
`code_sender_for`: the logging fixture when the deployment is a declared dev run
(`NURA_DEV_CODE_SENDER=1`, which `make dev` sets), and otherwise the process refuses to
start, because there is no real provider yet and the fixture prints login codes. Logging is
set up so that, on a dev run, the code line is seen.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.channels.api import Providers, create_app
from app.db import make_engine, make_session_factory
from app.drugs.client import drug_registry_for
from app.identity.providers import code_sender_for
from app.memory.objects import LocalObjectStore
from app.settings import load_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")

settings = load_settings()
engine = make_engine(settings.database_url)
app = create_app(
    settings,
    make_session_factory(engine),
    Providers(
        code_sender=code_sender_for(settings),
        drug_registry=drug_registry_for(settings),
        object_store=(
            None
            if settings.object_store_dir is None
            else LocalObjectStore(Path(settings.object_store_dir))
        ),
    ),
)
