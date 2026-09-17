"""What every safety test needs: a Pa in a region, his chief, a control word, a medicine, the
fixture transcriber, and the audit trail read back in order."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEntry
from app.channels.whatsapp.opt_in import record_opt_in
from app.consent.opt_in_words import OPT_IN_VERSION
from app.drugs.fixture import FixtureRegistry
from app.identity.service import create_own_profile, register_person
from app.ingestion.transcribe import FixtureTranscriber
from app.keys.context import KeyContext, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import store_artifact
from app.memory.models import ArtifactKind, Fact, Provider, ProviderKind, SourceChannel
from app.memory.semantic import assert_fact
from app.memory.spine import add_provider
from app.regions import Region
from app.safety.plain_words import verify
from tests.medicines_support import add, label
from tests.support import OPENING_CONSENT, agree_to_family_sharing
from tests.voice import VOICE

REGISTRY = FixtureRegistry.load()
TRANSCRIBER = FixtureTranscriber(VOICE, Region.SG)


def transcriber_for(region: Region) -> FixtureTranscriber:
    return FixtureTranscriber(VOICE, region)


SEPT_3 = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
SHA = "a" * 64


async def pa(
    session: AsyncSession,
    *,
    region: Region = Region.SG,
    phone: str = "+6591110021",
    language: str = "en",
    name: str = "Pa",
) -> KeyContext:
    person = await register_person(session, region=region, display_name=name, phone_e164=phone)
    profile = await create_own_profile(
        session, region=region, owner=person, consent=OPENING_CONSENT, language=language
    )
    return await resolve_key_context(
        session, region=region, person_id=person.id, profile_id=profile.id
    )


async def let_in(
    session: AsyncSession,
    owner: KeyContext,
    *,
    phone: str,
    name: str,
    role: KeyRole,
    scopes: set[Scope] | None = None,
    language: str = "en",
    opted_in: bool = True,
) -> KeyContext:
    holder = await register_person(
        session, region=owner.region, display_name=name, phone_e164=phone
    )
    holder.language = language
    await agree_to_family_sharing(session, owner, holder)
    await grant_key(session, context=owner, holder=holder, role=role, scopes=scopes)
    context = await resolve_key_context(
        session, region=owner.region, person_id=holder.id, profile_id=owner.profile_id
    )
    if opted_in:
        # His own answer at the key-accept step (#148, Meta's per-recipient opt-in): without
        # it Nura may send him nothing on WhatsApp, a red-flag notice included. A test that
        # wants a member nobody has asked yet passes `opted_in=False`.
        await record_opt_in(
            session,
            context=context,
            messages=True,
            joins_group=True,
            wording_version=OPT_IN_VERSION,
            language=language,
        )
    return context


async def fact(
    session: AsyncSession,
    context: KeyContext,
    *,
    subject: str,
    attribute: str,
    value: object,
    valid_to: datetime | None = None,
) -> Fact:
    """A fact on a letter photo: the way a clinician's control word or an allergy lands."""
    photo = await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"{context.region.value.lower()}/profiles/pa/{subject}-{attribute}-{uuid.uuid4()}.jpg",
        content_type="image/jpeg",
        sha256=SHA,
        captured_at=SEPT_3,
        source_channel=SourceChannel.APP,
        region=context.region,
    )
    return await assert_fact(
        session,
        context=context,
        subject=subject,
        attribute=attribute,
        value=value,
        confidence=0.9,
        artifact_id=photo.id,
        valid_to=valid_to,
    )


async def label_photo(session: AsyncSession, context: KeyContext):
    """A label photo in the profile's own region (the medicines helper's is Singapore's)."""
    digest = uuid.uuid4().hex + uuid.uuid4().hex
    return await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"{context.region.value.lower()}/profiles/{context.profile_id}/{digest}.photo",
        content_type="image/jpeg",
        sha256=digest,
        captured_at=SEPT_3,
        source_channel=SourceChannel.APP,
        region=context.region,
    )


async def water_pill(session: AsyncSession, context: KeyContext, dose: str = "1 tab OD morning"):
    """Frusemide 40 mg from a label photo: the water pill, once a day at breakfast."""
    photo = await label_photo(session, context)
    return await add(session, context, label("frusemide", "40 mg", dose), photo)


async def gliclazide(session: AsyncSession, context: KeyContext):
    """Gliclazide 30 mg from a label photo: the register's class for it is a sulfonylurea."""
    photo = await label_photo(session, context)
    return await add(session, context, label("gliclazide", "30 mg", "1 tab OD morning"), photo)


async def warfarin(session: AsyncSession, context: KeyContext):
    """Warfarin 3 mg from a label photo: the register's class for it is an anticoagulant."""
    photo = await label_photo(session, context)
    return await add(session, context, label("warfarin", "3 mg", "1 tab ON"), photo)


async def apixaban(session: AsyncSession, context: KeyContext):
    """Apixaban 5 mg from a label photo: the register classes it as an anticoagulant too."""
    photo = await label_photo(session, context)
    return await add(session, context, label("apixaban", "5 mg", "1 tab BD"), photo)


async def sugar_tablet(session: AsyncSession, context: KeyContext):
    photo = await label_photo(session, context)
    return await add(session, context, label("metformin", "500 mg", "1 tab BD"), photo)


async def clinic(session: AsyncSession, context: KeyContext, name: str = "Dr Tan") -> Provider:
    return await add_provider(
        session,
        context=context,
        name=name,
        kind=ProviderKind.DOCTOR,
        region=context.region,
        phone_e164="+6562223333",
    )


INSERTION_ORDER = {"sqlite": "audit_entry.rowid", "postgresql": "audit_entry.ctid"}
"""How a test database orders rows as they went in. SQLite: its implicit rowid. Postgres (the
`backend-postgres` CI job): the row's place in the table, which is the order of insertion for
a table nothing updates or deletes — the trail is append-only (`app.db.frozen`) — in a schema
made for the one test. Postgres has no rowid; asking for one was the first thing this suite
found when it ran there."""


async def trail(session: AsyncSession, profile_id: uuid.UUID) -> Sequence[AuditEntry]:
    """Every line on the profile, in the order it was written.

    The clock is frozen in every test, so `at` cannot order the lines; the test database's
    insertion order does (`INSERTION_ORDER`). This is a test's view of the trail, not the
    app's: `app.audit.trail.read_audit` orders by `at`.
    """
    found = await session.scalars(
        select(AuditEntry)
        .where(AuditEntry.profile_id == profile_id)
        .order_by(text(INSERTION_ORDER[session.get_bind().dialect.name]))
    )
    return found.all()


def first_write_of(lines: Sequence[AuditEntry], target: str, *, after: int = -1) -> int:
    """Where in the trail the first allowed write of `target` after index `after` sits; -1
    if none."""
    for index, line in enumerate(lines):
        if (
            index > after
            and line.target == target
            and line.action.value == "write"
            and line.outcome.value == "allowed"
        ):
            return index
    return -1


def assert_plain(lines, language: str = "en") -> None:
    """Every line passes the verifier, as it is written. Rule 5 reads a Malay or Chinese date
    against that language's own day names (E05 review, P3), so nothing is swapped first."""
    for line in lines:
        text = getattr(line, "text", line)
        assert [f for f in verify(text, language) if f.severity == "fail"] == [], line
