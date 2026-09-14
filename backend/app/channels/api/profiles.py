"""The profile routes. Every one of them takes a key context; none can be reached without one.

`/profiles/mine` is the "for me" door: it opens the caller's own graph. The other two doors,
for someone I care for and I was invited, are E01. Notes and medicines are here so that
checkpoint 2 has a scoped thing to read and a scoped thing to be refused; the real medicines
module arrives with E04 and will replace the placeholder read.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query, Request, status

from app.audit.models import Action
from app.audit.trail import read_audit
from app.channels.api.deps import Context, CurrentPerson, Db, settings_of
from app.channels.api.schemas import (
    AuditOut,
    KeyGrant,
    KeyOut,
    MedicineOut,
    NoteIn,
    NoteOut,
    ProfileCreate,
    ProfileOut,
)
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.identity.service import create_own_profile, register_person
from app.keys.context import resolve_key_context
from app.keys.grants import grant_key, list_keys, revoke_key
from app.keys.scopes import Scope
from app.memory.semantic import current_facts
from app.notes.service import list_notes, write_note

router = APIRouter(prefix="/profiles", tags=["profiles"])


class NoSuchHolder(Refusal):
    """A key names its holder by a person id this deployment does not hold."""


@router.post("/mine", status_code=status.HTTP_201_CREATED)
async def create_mine(
    body: ProfileCreate, request: Request, person: CurrentPerson, session: Db
) -> ProfileOut:
    """Open the caller's own health graph, here, pinned to this region."""
    region = settings_of(request).region
    profile = await create_own_profile(
        session,
        region=region,
        owner=person,
        display_name=body.display_name,
        language=body.language,
    )
    context = await resolve_key_context(
        session, region=region, person_id=person.id, profile_id=profile.id
    )
    return ProfileOut.of(profile, context)


@router.get("/{profile_id}")
async def get_profile(context: Context, session: Db) -> ProfileOut:
    """The profile as the caller holds it: name, language, and what his key opens.

    The context is the read: what comes back is the profile's face and the caller's own
    reach, which he was told when the key was cut. The rows of the graph stay behind
    their scopes.
    """
    profile = await session.get(Profile, context.profile_id)
    assert profile is not None  # the context was resolved from this row a moment ago
    return ProfileOut.of(profile, context)


# --- keys --------------------------------------------------------------------------------


async def _holder(session: Db, *, request: Request, body: KeyGrant) -> Person:
    """The person the key is for.

    By phone, a number that is not an account yet becomes one — a name-less account the
    invite will land on when the person proves the number, as the invited door does in
    E01. Whether the number was already known is not something the answer gives away.
    """
    if body.holder_person_id is not None:
        found = await session.get(Person, body.holder_person_id)
        if found is None:
            raise NoSuchHolder(f"no person {body.holder_person_id}")
        return found
    return await register_person(
        session,
        region=settings_of(request).region,
        display_name="",
        phone_e164=body.holder_phone_e164,
    )


@router.post("/{profile_id}/keys", status_code=status.HTTP_201_CREATED)
async def grant(body: KeyGrant, request: Request, context: Context, session: Db) -> KeyOut:
    holder = await _holder(session, request=request, body=body)
    key = await grant_key(
        session,
        context=context,
        holder=holder,
        role=body.role,
        scopes=body.scopes,
        window=body.window,
        basis=body.basis,
    )
    return KeyOut.of(key)


@router.get("/{profile_id}/keys")
async def keys(context: Context, session: Db) -> list[KeyOut]:
    return [KeyOut.of(key) for key in await list_keys(session, context=context)]


@router.delete("/{profile_id}/keys/{key_id}")
async def revoke(key_id: uuid.UUID, context: Context, session: Db) -> KeyOut:
    return KeyOut.of(await revoke_key(session, context=context, key_id=key_id))


# --- the audit trail ---------------------------------------------------------------------


@router.get("/{profile_id}/audit")
async def audit(
    context: Context,
    session: Db,
    action: Action | None = None,
    scope: Scope | None = None,
    actor_person_id: uuid.UUID | None = None,
    since: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[AuditOut]:
    """Who touched what on this profile, newest first. The owner's and his chief's to read."""
    entries = await read_audit(
        session,
        context=context,
        action=action,
        scope=scope,
        actor_person_id=actor_person_id,
        since=since,
        limit=limit,
    )
    return [AuditOut.of(entry) for entry in entries]


# --- notes and medicines -----------------------------------------------------------------


@router.get("/{profile_id}/notes")
async def notes(context: Context, session: Db) -> list[NoteOut]:
    return [NoteOut.of(note) for note in await list_notes(session, context=context)]


@router.post("/{profile_id}/notes", status_code=status.HTTP_201_CREATED)
async def add_note(body: NoteIn, context: Context, session: Db) -> NoteOut:
    return NoteOut.of(await write_note(session, context=context, text=body.text))


@router.get("/{profile_id}/medicines")
async def medicines(context: Context, session: Db) -> list[MedicineOut]:
    """The current facts about medicines, read under the medicines scope. A placeholder
    until E04 builds the medicine line; it is here so a caregiver key has something to open."""
    facts = await current_facts(session, context=context, subject="medicine", scope=Scope.MEDICINES)
    return [MedicineOut.of(fact) for fact in facts]
