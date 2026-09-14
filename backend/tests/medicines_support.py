"""What every medicines test needs: a Pa, a label photo, a label, the fixture registry, a yes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.drafts import Draft
from app.drugs.fixture import FixtureRegistry
from app.identity.service import create_own_profile, register_person
from app.keys.confirm import confirm
from app.keys.context import KeyContext, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.medicines.dose import Dose, parse_dose_text
from app.medicines.service import Label, Plan, Reconciled, plan, reconcile
from app.memory.episodic import store_artifact
from app.memory.models import Artifact, ArtifactKind, Recording, SourceChannel
from app.regions import Region
from tests.support import OPENING_CONSENT, agree_to_family_sharing

SEPT_3 = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
REGISTRY = FixtureRegistry.load()


async def pa(session: AsyncSession, phone: str = "+6591110001", language: str = "ms") -> KeyContext:
    person = await register_person(session, region=Region.SG, display_name="Pa", phone_e164=phone)
    profile = await create_own_profile(
        session, region=Region.SG, owner=person, consent=OPENING_CONSENT, language=language
    )
    return await resolve_key_context(
        session, region=Region.SG, person_id=person.id, profile_id=profile.id
    )


async def let_in(
    session: AsyncSession,
    owner: KeyContext,
    *,
    phone: str,
    name: str,
    role: KeyRole,
    scopes: set[Scope],
) -> KeyContext:
    holder = await register_person(session, region=Region.SG, display_name=name, phone_e164=phone)
    await agree_to_family_sharing(session, owner, holder, scopes=scopes)
    await grant_key(session, context=owner, holder=holder, role=role, scopes=scopes)
    return await resolve_key_context(
        session, region=Region.SG, person_id=holder.id, profile_id=owner.profile_id
    )


async def artefact(
    session: AsyncSession,
    context: KeyContext,
    *,
    kind: ArtifactKind = ArtifactKind.PHOTO,
    when: datetime = SEPT_3,
) -> Artifact:
    """A label photo by default; any other kind is not a label photo."""
    digest = uuid.uuid4().hex + uuid.uuid4().hex
    return await store_artifact(
        session,
        context=context,
        kind=kind,
        storage_key=f"sg/profiles/{context.profile_id}/{digest}.{kind.value}",
        content_type="image/jpeg" if kind is ArtifactKind.PHOTO else "application/octet-stream",
        sha256=digest,
        captured_at=when,
        source_channel=SourceChannel.APP,
        region=Region.SG,
        # A voice note is someone's own words, kept on the record consent (ADR 0003).
        recording=Recording.OWN_NOTE if kind is ArtifactKind.VOICE else None,
    )


def label(
    generic: str,
    strength: str,
    dose: str | Dose = "1 tab OD",
    *,
    quantity: int | None = 30,
    prescriber: str | None = "Dr Tan",
    **more: object,
) -> Label:
    return Label(
        dose=dose if isinstance(dose, Dose) else parse_dose_text(dose),
        generic=generic,
        strength=strength,
        quantity=quantity,
        prescriber=prescriber,
        **more,  # type: ignore[arg-type]
    )


async def yes(session: AsyncSession, context: KeyContext, draft: Draft) -> uuid.UUID:
    return (await confirm(session, context, draft)).id


async def planned(session: AsyncSession, context: KeyContext, what: Label, photo: Artifact) -> Plan:
    return await plan(
        session, context=context, registry=REGISTRY, label=what, source_artifact_id=photo.id
    )


async def add(
    session: AsyncSession, context: KeyContext, what: Label, photo: Artifact | None = None
) -> Reconciled:
    """Plan, say yes to exactly that, write it: the way the app's card does it."""
    source = photo or await artefact(session, context)
    shown = await planned(session, context, what, source)
    assert shown.draft is not None, shown.outcome
    return await reconcile(
        session,
        context=context,
        registry=REGISTRY,
        label=what,
        source_artifact_id=source.id,
        confirmation_id=await yes(session, context, shown.draft),
    )
