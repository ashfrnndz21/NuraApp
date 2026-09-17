"""The migrations and the models must agree.

Migrations are never deleted, so the only way the two drift apart is a column added to one
and not the other. This loads every revision in the directory, runs them in dependency
order against an empty database, and checks the tables they build against the tables the
models declare.

Two stories built side by side each branch from the same revision; a merge revision joins
them, so the directory always has exactly one head and `alembic upgrade head` knows where
that is. What is not allowed is a revision that names a parent the directory does not hold.

The walks run on the suite's database: SQLite in memory by default, and each on a schema of
its own on Postgres when NURA_TEST_DATABASE_URL names one (`tests/conftest.py`), so the batch
rewrites SQLite needs and the plain ALTERs Postgres gets are both held to the models.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, Inspector, Table, inspect, select, text

from app.audit.models import AuditEntry
from app.channels.whatsapp.models import DoseQuestion, Proposal, WhatsAppMessage, WhatsAppThread
from app.consent.models import Consent
from app.delivery.feed.models import Engagement, FeedItem, FeedPage, SearchJob, Source
from app.delivery.nudges.models import Nudge, NudgeResponse
from app.delivery.triggers.models import Delivery, DeliverySettings, Ladder
from app.family.models import (
    Document,
    RosterSlot,
    ScheduledCall,
    ScheduledPush,
    Task,
    ThreadMessage,
)
from app.identity.models import LoginChallenge, LoginSession, Person, Profile, Stewardship
from app.ingestion.connectors.models import AppointmentProposal, Connector
from app.ingestion.models import (
    ConsultRecording,
    ConsultSegment,
    EventNote,
    ReviewCard,
    ReviewField,
)
from app.insurance.claim import InsuranceClaim
from app.insurance.policy import Policy
from app.keys.confirm import Confirmation
from app.keys.models import Key
from app.keys.privacy import Privacy
from app.medicines.models import DoseTaken, InteractionFlag, MedicationLine, Supply
from app.memory.models import (
    Appointment,
    Artifact,
    Attachment,
    Episode,
    Event,
    Fact,
    LastLooked,
    Provider,
    ProviderNote,
)
from app.notes.models import Note
from app.onboarding.models import (
    ActivationPlan,
    BiographyLine,
    BiographyPaper,
    BiographyQuestion,
    BiographySession,
    PlanPrompt,
    ProfileSettings,
)
from app.reasoning.feelings.models import FeelingNote, FeelingTap
from app.reasoning.models import TrendCard
from app.reasoning.visits.models import (
    Brief,
    Memo,
    Question,
    SummaryItem,
    VisitSummary,
)
from app.routines.models import Routine
from app.safety.models import EmergencyCard, Notice, WhatToDoCard
from app.safety.red_flags import Escalation, Flag
from app.state.models import StateSnapshot
from tests.conftest import on_an_empty_database

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"

TABLES: tuple[Table, ...] = (
    Person.__table__,
    Profile.__table__,
    Key.__table__,
    Confirmation.__table__,
    AuditEntry.__table__,
    Consent.__table__,
    Artifact.__table__,
    Event.__table__,
    Fact.__table__,
    Episode.__table__,
    Provider.__table__,
    Appointment.__table__,
    LoginChallenge.__table__,
    LoginSession.__table__,
    Note.__table__,
    Stewardship.__table__,
    StateSnapshot.__table__,
    ReviewCard.__table__,
    ReviewField.__table__,
    EventNote.__table__,
    Source.__table__,
    SearchJob.__table__,
    FeedItem.__table__,
    Engagement.__table__,
    FeedPage.__table__,
    Flag.__table__,
    MedicationLine.__table__,
    Supply.__table__,
    DoseTaken.__table__,
    InteractionFlag.__table__,
    Brief.__table__,
    Question.__table__,
    Memo.__table__,
    VisitSummary.__table__,
    SummaryItem.__table__,
    WhatsAppThread.__table__,
    Flag.__table__,
    WhatsAppMessage.__table__,
    Proposal.__table__,
    Escalation.__table__,
    Privacy.__table__,
    RosterSlot.__table__,
    Task.__table__,
    TrendCard.__table__,
    Routine.__table__,
    Connector.__table__,
    AppointmentProposal.__table__,
    ThreadMessage.__table__,
    ScheduledPush.__table__,
    Document.__table__,
    FeelingTap.__table__,
    FeelingNote.__table__,
    Nudge.__table__,
    NudgeResponse.__table__,
    ProfileSettings.__table__,
    BiographySession.__table__,
    BiographyPaper.__table__,
    BiographyLine.__table__,
    BiographyQuestion.__table__,
    ActivationPlan.__table__,
    PlanPrompt.__table__,
    DeliverySettings.__table__,
    Ladder.__table__,
    Delivery.__table__,
    Notice.__table__,
    WhatToDoCard.__table__,
    EmergencyCard.__table__,
    Attachment.__table__,
    ProviderNote.__table__,
    LastLooked.__table__,
    ConsultRecording.__table__,
    ConsultSegment.__table__,
    Policy.__table__,
    InsuranceClaim.__table__,
    ScheduledCall.__table__,
    DoseQuestion.__table__,
)


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parents(module: ModuleType) -> tuple[str, ...]:
    """A merge revision names several parents; every other revision names one or none."""
    down = module.down_revision
    if down is None:
        return ()
    return (down,) if isinstance(down, str) else tuple(down)


@pytest.fixture
def revisions() -> dict[str, ModuleType]:
    found = {module.revision: module for module in map(_load, sorted(VERSIONS.glob("*.py")))}
    assert found, "no migrations found"
    return found


def _in_order(revisions: dict[str, ModuleType]) -> tuple[ModuleType, ...]:
    """Every revision after all of its parents; siblings by file name, so the run is stable."""
    applied: list[str] = []
    waiting = dict(revisions)
    while waiting:
        ready = sorted(
            (rev for rev, module in waiting.items() if set(_parents(module)) <= set(applied)),
            key=lambda rev: revisions[rev].__name__,
        )
        assert ready, f"these revisions never become applicable: {sorted(waiting)}"
        applied.extend(ready)
        for rev in ready:
            del waiting[rev]
    return tuple(revisions[rev] for rev in applied)


def test_every_revision_links_to_one_the_directory_holds(
    revisions: dict[str, ModuleType],
) -> None:
    roots = [rev for rev, module in revisions.items() if not _parents(module)]
    assert roots == ["0001_accounts"]
    for module in revisions.values():
        for parent in _parents(module):
            assert parent in revisions, f"{module.revision} revises {parent}, which is not here"


def _tied(built: Inspector, table: Table) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    """Every foreign key on the built table, as (columns, referred table, referred columns)."""
    return {
        (
            tuple(key["constrained_columns"]),
            key["referred_table"],
            tuple(key["referred_columns"]),
        )
        for key in built.get_foreign_keys(table.name)
    }


def _tied_by_model(table: Table) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(element.parent.name for element in key.elements),
            key.referred_table.name,
            tuple(element.column.name for element in key.elements),
        )
        for key in table.foreign_key_constraints
    }


def test_the_chain_has_one_head(revisions: dict[str, ModuleType]) -> None:
    """Heads built side by side are joined by a merge revision, so upgrade knows where to go."""
    parents = {parent for module in revisions.values() for parent in _parents(module)}
    heads = sorted(rev for rev in revisions if rev not in parents)
    assert heads == ["0047_provider_category"]


async def test_the_migrations_build_the_tables_the_models_declare(
    revisions: dict[str, ModuleType],
) -> None:
    ordered = _in_order(revisions)

    def walk(connection: Connection) -> None:
        for migration in ordered:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()

        built = inspect(connection)
        assert set(built.get_table_names()) >= {table.name for table in TABLES}
        for table in TABLES:
            assert {column["name"] for column in built.get_columns(table.name)} == {
                column.name for column in table.columns
            }, table.name
            assert {
                column["name"] for column in built.get_columns(table.name) if column["nullable"]
            } == {column.name for column in table.columns if column.nullable}, table.name

        # The ties that keep provenance on the profile survive the batch rewrite (0004), and
        # so do the checks 0003 put on the fact table. The review card (0008) is tied to its
        # photo and its facts the same way.
        for table in (
            Artifact,
            Event,
            Fact,
            Episode,
            Provider,
            Appointment,
            ReviewCard,
            ReviewField,
            EventNote,
            FeedItem,
            Engagement,
            Flag,
            MedicationLine,
            Supply,
            DoseTaken,
            InteractionFlag,
            Brief,
            Question,
            Memo,
            VisitSummary,
            SummaryItem,
            ThreadMessage,
            ScheduledPush,
            Document,
            FeelingTap,
            FeelingNote,
            Nudge,
            NudgeResponse,
            ProfileSettings,
            BiographySession,
            BiographyPaper,
            BiographyLine,
            BiographyQuestion,
            ActivationPlan,
            PlanPrompt,
            TrendCard,
            Routine,
            AppointmentProposal,
            Ladder,
            Delivery,
            Notice,
            WhatToDoCard,
            EmergencyCard,
            ConsultRecording,
            ConsultSegment,
            Task,
            Policy,
            InsuranceClaim,
        ):
            assert _tied(built, table.__table__) == _tied_by_model(table.__table__), table.name
        assert {check["name"] for check in built.get_check_constraints("fact")} >= {
            "ck_fact_has_provenance",
            "ck_fact_confidence",
        }

        for migration in reversed(ordered):
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
        assert inspect(connection).get_table_names() == []

    await on_an_empty_database(walk)


def _apply(connection: Connection, migration: ModuleType, step: str) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        getattr(migration, step)()


async def test_0005_will_not_drop_a_persons_word_or_an_events_source_on_the_way_down(
    revisions: dict[str, ModuleType],
) -> None:
    """Upgrade, populate, down to 0005, downgrade (refused), clear, downgrade, upgrade again."""
    ordered = _in_order(revisions)
    review = revisions["0005_memory_review"]

    def walk(connection: Connection) -> None:
        for migration in ordered:
            _apply(connection, migration, "upgrade")

        pa, profile, photo = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        when = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
        connection.execute(
            Person.__table__.insert().values(
                id=pa, region="SG", display_name="Pa", language="en", created_at=when
            )
        )
        connection.execute(
            Profile.__table__.insert().values(
                id=profile,
                region="SG",
                display_name="Pa",
                language="en",
                owner_person_id=pa,
                created_at=when,
            )
        )
        connection.execute(
            Artifact.__table__.insert().values(
                written_scope="records",
                id=photo,
                profile_id=profile,
                kind="photo",
                storage_key="sg/x.jpg",
                content_type="image/jpeg",
                sha256="a" * 64,
                captured_at=when,
                source_channel="app",
                region="SG",
                stored_at=when,
            )
        )
        confirmed = uuid.uuid4()
        connection.execute(
            Fact.__table__.insert().values(
                id=confirmed,
                profile_id=profile,
                subject="medication",
                attribute="dose",
                value=136,
                confidence=1.0,
                confidence_state="confirmed_by_person",
                artifact_id=photo,
                valid_from=when,
                asserted_at=when,
                confirmed_by_person_id=pa,
            )
        )
        told = uuid.uuid4()
        connection.execute(
            Event.__table__.insert().values(
                written_scope="records",
                id=told,
                profile_id=profile,
                kind="visit",
                occurred_at=when,
                source_channel="app",
                label="saw Dr Tan",
                recorded_at=when,
            )
        )

        # Down to 0005 first, the way `alembic downgrade 0005_memory_review` goes: a later
        # revision ties new tables to the constraints 0005 made, and Postgres will not drop a
        # constraint something still depends on (SQLite's batch rewrite never asked).
        for later in reversed(ordered[ordered.index(review) + 1 :]):
            _apply(connection, later, "downgrade")

        with pytest.raises(RuntimeError, match="person's word"):
            _apply(connection, review, "downgrade")
        connection.execute(Fact.__table__.delete().where(Fact.__table__.c.id == confirmed))
        with pytest.raises(RuntimeError, match="event's source"):
            _apply(connection, review, "downgrade")
        connection.execute(Event.__table__.delete().where(Event.__table__.c.id == told))

        # With nothing to drop, the way down and back up is open, and the rows are kept.
        _apply(connection, review, "downgrade")
        assert "source_channel" not in {c["name"] for c in inspect(connection).get_columns("event")}
        _apply(connection, review, "upgrade")
        assert connection.execute(select(Artifact.__table__.c.id)).scalar_one() == photo

    await on_an_empty_database(walk)


async def test_0012_widens_a_red_flag_already_raised_and_keeps_it_on_the_way_down(
    revisions: dict[str, ModuleType],
) -> None:
    """A flag raised from the feeling cloud before the visit loop existed is kept whole: 0012
    gives it its kind, the code its feeling has in the word table, the subject and empty
    lists, and the way down leaves it as it was."""
    ordered = _in_order(revisions)
    visits = revisions["0012_visits"]

    def walk(connection: Connection) -> None:
        # Only the revisions before 0012: a later one may name a table 0012 makes, which
        # Postgres, unlike SQLite's batch rewrite, will not create a tie to before it exists.
        for migration in ordered[: ordered.index(visits)]:
            _apply(connection, migration, "upgrade")
        ids = {name: uuid.uuid4().hex for name in ("flag", "profile", "event", "person")}
        # The flag's person, profile and event, so its ties hold on a database that keeps
        # them (Postgres always does; the SQLite migration walks do not).
        for statement in (
            (
                "INSERT INTO person (id, region, display_name, language, created_at) "
                "VALUES (:person, 'SG', 'Pa', 'en', '2026-09-03 08:00:00')"
            ),
            (
                "INSERT INTO profile (id, region, display_name, language, owner_person_id, "
                "created_at) VALUES (:profile, 'SG', 'Pa', 'en', :person, '2026-09-03 08:00:00')"
            ),
            (
                "INSERT INTO event (id, profile_id, kind, occurred_at, recorded_at, "
                "source_channel) VALUES (:event, :profile, 'feeling', '2026-09-03 08:00:00', "
                "'2026-09-03 08:00:00', 'app')"
            ),
        ):
            connection.execute(text(statement), ids)
        connection.execute(
            text(
                "INSERT INTO red_flag (id, profile_id, feeling, event_id, raised_by_person_id, "
                "raised_at, told) VALUES (:flag, :profile, 'chest_tightness', :event, :person, "
                "'2026-09-03 08:00:00', '[]')"
            ),
            ids,
        )
        _apply(connection, visits, "upgrade")
        row = connection.execute(
            text(
                "SELECT kind, code, subject, fact_ids, payload, feeling, resolved_at FROM red_flag"
            )
        ).one()
        kind, code, subject, fact_ids, payload, feeling, resolved_at = row
        # A raw read of a json column: SQLite hands back its text, Postgres the value decoded.
        lists = [json.loads(v) if isinstance(v, str) else v for v in (fact_ids, payload)]
        assert (kind, code, subject, *lists, feeling, resolved_at) == (
            "red_flag",
            "chest_pain",
            "symptom",
            [],
            {},
            "chest_tightness",
            None,
        )

        _apply(connection, visits, "downgrade")
        assert (
            connection.execute(text("SELECT feeling FROM red_flag")).scalar_one()
            == "chest_tightness"
        )
        assert "kind" not in {c["name"] for c in inspect(connection).get_columns("red_flag")}

    await on_an_empty_database(walk)
