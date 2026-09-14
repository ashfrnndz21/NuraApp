"""Every module that declares a table, imported for the side effect of registering it on
`app.db.Base.metadata`. Import this, never a hand list, wherever the whole schema is needed:
Alembic's `migrations/env.py` compares the migrations against it, and a table left out of
it is one `alembic check` would propose to drop.

A test (`tests/test_models_registry.py`) finds every class with a `__tablename__` under
`app/` and fails if this module does not load it, so a new table cannot be forgotten here.
"""

from __future__ import annotations

import app.audit.models
import app.channels.whatsapp.models
import app.consent.models
import app.delivery.feed.models
import app.delivery.nudges.models
import app.delivery.triggers.models
import app.family.models
import app.identity.models
import app.ingestion.connectors.models
import app.ingestion.models
import app.insurance.insurer
import app.keys.confirm
import app.keys.models
import app.keys.privacy
import app.language.models
import app.medicines.models
import app.memory.models
import app.notes.models
import app.onboarding.models
import app.reasoning.feelings.models
import app.reasoning.models
import app.reasoning.visits.models
import app.routines.models
import app.safety.models
import app.safety.red_flags
import app.state.models  # noqa: F401
from app.db import Base

metadata = Base.metadata
"""The whole schema: every table of the app, and nothing a test declared."""
