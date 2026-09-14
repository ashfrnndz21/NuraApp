"""Closing an account (#143): the one way to withdraw "keep my papers".

The confirm step says in plain words what stops (`app.consent.closing_words`), and his yes
binds to exactly those lines (`CloseDraft`). Closing then, at once: writes the closing, which
suspends every key and his own reads (`app.keys.context.AccountClosing`); withdraws the
HOLD_HEALTH_RECORD agreement, on the record; revokes every push subscription under the
profile; and the delivery engine sends nothing more about him — except a red flag raised
before the closing, which is never hidden from the day it was raised
(`app.delivery.triggers.engine.run_due`).

Until `delete_after` (`NURA_ACCOUNT_RETENTION_DAYS`, 30 until counsel says) his yes undoes it:
he agrees to today's words for keeping his papers again, and the suspension lifts. After it,
the erasure job deletes the graph behind the `Eraser` port, the way the PDPA data map says
(`docs/trust/pdpa-data-map.md` §4): the consent rows are archived in an `ErasureRecord` outside
the graph with the one line that says the graph was erased; every other row of the profile,
its stored objects and its push subscriptions are deleted; his sign-in account stays.
`run_erasures` is what a scheduler calls — `POST /dev/run-erasures` on a dev run, the region's
own scheduler in a deployment.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Protocol

from sqlalchemy import Table, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard, audited_read, audited_write
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.consent.closing_words import closing_lines
from app.consent.models import Consent, ConsentBasis, ConsentPurpose
from app.consent.service import (
    NoConsentToWithdraw,
    RecordConsent,
    check_opening_words,
    grant_consent,
    revoke_consent,
)
from app.db import Base, ProfileScoped, as_utc, utcnow
from app.delivery.triggers.models import PushSubscription
from app.drafts import CloseDraft
from app.errors import Refusal
from app.identity.closure_models import AccountClosure, ErasureRecord
from app.identity.models import Profile
from app.ingestion.objects import ObjectStore, check_key
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import Artifact
from app.regions import REGION_TZ

TARGET = AccountClosure.__tablename__

OBJECT_KINDS = (
    "consults",
    "documents",
    "imports",
    "messages",
    "photos",
    "questions",
    "scribbles",
    "transcripts",
    "voice",
    "words",
)
"""Every kind of stored object a profile's bytes are kept under, as `<kind>/<profile_id>/…`.
A test holds this to the code: a new kind that is not here would outlive the erasure."""


class NotTheirsToClose(Refusal):
    """Only the person whose papers they are closes his account, or undoes the closing."""


class AlreadyClosing(Refusal):
    """This account is already closing."""


class NothingToUndo(Refusal):
    """There is no closing to undo."""


class TooLateToUndo(Refusal):
    """The window has passed: his papers are being deleted, and the closing cannot be undone."""


def _delete_on(moment: datetime, days: int, context: KeyContext) -> date:
    return (moment + timedelta(days=days)).astimezone(REGION_TZ[context.region]).date()


async def closing_status(session: AsyncSession, *, context: KeyContext) -> AccountClosure | None:
    """The closing that stands, for its owner. Nobody else asks after it."""
    async with audited_guard(session, context, Action.READ, Scope.PROFILE, TARGET):
        if not context.is_owner:
            raise NotTheirsToClose("only the owner reads his closing")
    return await pending_closure(session, context=context)


async def pending_closure(session: AsyncSession, *, context: KeyContext) -> AccountClosure | None:
    rows = await audited_read(
        session, AccountClosure, context, Scope.PROFILE, where=(AccountClosure.undone_at.is_(None),)
    )
    return rows[0] if rows else None


async def close_draft_for(
    session: AsyncSession, *, context: KeyContext, language: str | None, retention_days: int
) -> CloseDraft:
    """What closing will mean, in his words, for his yes to bind to. His alone."""
    async with audited_guard(session, context, Action.WRITE, Scope.PROFILE, TARGET):
        if not context.is_owner:
            raise NotTheirsToClose("only the owner closes his account")
    delete_on = _delete_on(utcnow(), retention_days, context)
    return CloseDraft(lines=closing_lines(language, delete_on), delete_on=delete_on.isoformat())


async def close_account(
    session: AsyncSession,
    *,
    context: KeyContext,
    confirmation_id: uuid.UUID,
    language: str | None,
    retention_days: int,
) -> AccountClosure:
    """Close it on his yes to exactly the lines he was shown: suspend, withdraw, stop."""
    async with audited_guard(session, context, Action.WRITE, Scope.PROFILE, TARGET):
        if not context.is_owner:
            raise NotTheirsToClose("only the owner closes his account")
        if await pending_closure(session, context=context) is not None:
            raise AlreadyClosing("this account is already closing")
    draft = await close_draft_for(
        session, context=context, language=language, retention_days=retention_days
    )
    await consume_confirmation(session, context, confirmation_id, draft)
    moment = utcnow()
    closure = await audited_write(
        session,
        AccountClosure,
        context,
        Scope.PROFILE,
        requested_by_person_id=context.person_id,
        requested_at=moment,
        delete_after=moment + timedelta(days=retention_days),
    )
    # Nura stops keeping his papers: the agreement is withdrawn, on the record.
    try:
        await revoke_consent(
            session,
            context=context,
            purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
            captured_via=_captured_via(),
        )
    except NoConsentToWithdraw:
        pass  # a graph set up for him and never claimed has nothing of his to withdraw
    # No phone is reached about him from now: every subscription under the profile goes.
    for device in await audited_read(
        session,
        PushSubscription,
        context,
        Scope.PROFILE,
        where=(PushSubscription.revoked_at.is_(None),),
    ):
        device.revoked_at = moment
    await session.flush()
    return closure


def _captured_via() -> Any:
    from app.consent.models import ConsentChannel

    return ConsentChannel.APP


async def undo_closure(
    session: AsyncSession, *, context: KeyContext, consent: RecordConsent
) -> AccountClosure:
    """His yes within the window: he agrees to today's words for keeping his papers again,
    and the suspension lifts. His keys, and his family's, work again at once."""
    async with audited_guard(session, context, Action.WRITE, Scope.PROFILE, TARGET):
        if not context.is_owner:
            raise NotTheirsToClose("only the owner undoes his closing")
        closure = await pending_closure(session, context=context)
        if closure is None:
            raise NothingToUndo("there is no closing to undo")
        if utcnow() >= as_utc(closure.delete_after):
            raise TooLateToUndo("the window to undo has passed")
        check_opening_words(consent, context.region)
    closure.undone_at = utcnow()
    closure.undone_by_person_id = context.person_id
    await session.flush()
    await grant_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        captured_via=consent.captured_via,
        basis=ConsentBasis.OWNER,
        language=consent.language,
        text_version=consent.text_version,
    )
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.PROFILE,
        target=TARGET,
        target_id=closure.id,
        rows=1,
        channel=Channel.APP,
    )
    return closure


# --- erasure ------------------------------------------------------------------------------------

_PREFIX = re.compile(r"^[a-z]+/[0-9a-f-]{36}/$")


class Eraser(Protocol):
    """Deletes one closed account's graph when its window has passed."""

    async def erase(self, session: AsyncSession, closure: AccountClosure) -> ErasureRecord: ...


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def profile_tables() -> list[Table]:
    """Every table of profile data, children before the tables they point at."""
    scoped: set[str] = set()
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if issubclass(model, ProfileScoped):
            scoped.add(model.__tablename__)
    return [table for table in reversed(Base.metadata.sorted_tables) if table.name in scoped]


class GraphEraser:
    """The erasure the PDPA data map describes: archive the consents, delete the rest."""

    def __init__(self, store: ObjectStore) -> None:
        self.store = store

    async def erase(self, session: AsyncSession, closure: AccountClosure) -> ErasureRecord:
        profile_id = closure.profile_id
        profile = await session.get(Profile, profile_id)
        assert profile is not None, "a closing stands on its profile"
        consents = (
            await session.scalars(select(Consent).where(Consent.profile_id == profile_id))
        ).all()
        archive = [
            {column.key: _plain(getattr(row, column.key)) for column in Consent.__mapper__.columns}
            for row in consents
        ]
        removed: dict[str, int] = {}
        # The bytes first. Every object of a profile is kept under `<kind>/<profile_id>/`
        # (`OBJECT_KINDS`, held to the code by a test), so one prefix per kind takes them all —
        # an artefact's own bytes and what has no row, like a card's spoken twin.
        objects = 0
        prefixes = [f"{kind}/{profile_id}/" for kind in OBJECT_KINDS]
        for prefix in prefixes:
            assert _PREFIX.match(prefix), prefix
            objects += await self.store.delete_prefix(prefix)
        # The erasure's own read of the keys, as the system (approved in the row-scope test):
        # evidence for a documented basis is stored at a key its caller chose, which may lie
        # outside those prefixes. Such an object goes too, unless another profile's artefact
        # rests on the same bytes. Nothing read here reaches a caller.
        keys = (
            await session.scalars(
                select(Artifact.storage_key).where(Artifact.profile_id == profile_id)
            )
        ).all()
        for key in sorted(set(keys)):
            if any(key.startswith(prefix) for prefix in prefixes):
                continue
            shared = await session.scalar(
                select(Artifact.id)
                .where(Artifact.storage_key == key, Artifact.profile_id != profile_id)
                .limit(1)
            )
            if shared is None:
                await self.store.delete(check_key(key))
                objects += 1
        removed["objects"] = objects
        region, requested_by, requested_at = (
            profile.region,
            closure.requested_by_person_id,
            closure.requested_at,
        )
        for table in profile_tables():
            gone = await session.execute(delete(table).where(table.c.profile_id == profile_id))
            count = getattr(gone, "rowcount", 0) or 0
            if count:
                removed[table.name] = count
        await session.execute(
            delete(Profile)
            .where(Profile.id == profile_id)
            .execution_options(synchronize_session=False)
        )
        erased = ErasureRecord(
            profile_id=profile_id,
            region=region,
            requested_by_person_id=requested_by,
            requested_at=requested_at,
            erased_at=utcnow(),
            consents=archive,
            removed=removed,
        )
        session.add(erased)
        await session.flush()
        return erased


async def run_erasures(
    session: AsyncSession, *, eraser: Eraser, at: datetime | None = None
) -> Sequence[ErasureRecord]:
    """Every closing whose window has passed, erased. What a scheduler calls."""
    moment = at or utcnow()
    due = (
        await session.scalars(
            select(AccountClosure).where(
                AccountClosure.undone_at.is_(None), AccountClosure.delete_after <= moment
            )
        )
    ).all()
    return [await eraser.erase(session, closure) for closure in due]
