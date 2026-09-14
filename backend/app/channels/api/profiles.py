"""The profile routes. Every one of them takes a key context; none can be reached without one.

`/profiles/mine` is the "for me" door: it opens the caller's own graph. The other two doors,
for someone I care for and I was invited, are E01. Notes and medicines are here so that
checkpoint 2 has a scoped thing to read and a scoped thing to be refused; the real medicines
module arrives with E04 and will replace the placeholder read. Readings and State are here
so that checkpoint 3 has a fact to add and a State to watch recompute; the real capture is
E02.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Query, Request, status

from app.audit.access import audited_profile_read
from app.audit.models import Action
from app.audit.trail import read_audit
from app.channels.api.deps import Context, CurrentPerson, Db, settings_of
from app.channels.api.schemas import (
    AuditOut,
    ConsentOut,
    KeyGrant,
    KeyOut,
    MedicineOut,
    NoteIn,
    NoteOut,
    ProfileCreate,
    ProfileOut,
    ReadingIn,
    ReadingOut,
    SharingConsentIn,
    StateOut,
)
from app.consent.models import ConsentBasis, ConsentPurpose
from app.consent.service import Sharing, all_consents, grant_consent
from app.db import utcnow
from app.drafts import FactDraft
from app.errors import Refusal
from app.identity.models import Person
from app.identity.service import create_own_profile, register_person
from app.keys.confirm import confirm
from app.keys.context import resolve_key_context
from app.keys.grants import grant_key, list_keys, may_cut_keys, revoke_key
from app.keys.scopes import Scope
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, EventKind, SourceChannel
from app.memory.semantic import assert_fact, current_facts
from app.notes.service import list_notes, write_note
from app.state.service import current_state

router = APIRouter(prefix="/profiles", tags=["profiles"])
log = logging.getLogger("nura.channels.api")


class NoSuchHolder(Refusal):
    """A key names its holder by a person id this deployment does not hold.

    A person pinned to another region is, to this deployment, no holder either, and is
    refused in the same words: whether an id is an account somewhere else is not answered.
    """


@router.post("/mine", status_code=status.HTTP_201_CREATED)
async def create_mine(
    body: ProfileCreate, request: Request, person: CurrentPerson, session: Db
) -> ProfileOut:
    """Open the caller's own health graph, here, pinned to this region.

    The agreement he gave is recorded on it as the `HOLD_HEALTH_RECORD` consent in the same
    transaction; words that are not today's words on file refuse first, and no profile is
    opened. Those refusals have no profile to be written under, so the channel logs them
    at the account, by a handle.
    """
    region = settings_of(request).region
    try:
        profile = await create_own_profile(
            session,
            region=region,
            owner=person,
            consent=body.consent.as_record(),
            display_name=body.display_name,
            language=body.language,
        )
    except Refusal as refusal:
        log.info(
            "profile door refused: refusal=%s account=%s",
            type(refusal).__name__,
            hashlib.sha256(str(person.id).encode()).hexdigest()[:8],
        )
        raise
    context = await resolve_key_context(
        session, region=region, person_id=person.id, profile_id=profile.id
    )
    return ProfileOut.of(profile, context)


@router.get("/{profile_id}")
async def get_profile(context: Context, session: Db) -> ProfileOut:
    """The profile as the caller holds it: name, language, and what his key opens.

    Read under `Scope.PROFILE`, which every key holds, and written down like any read.
    """
    return ProfileOut.of(await audited_profile_read(session, context), context)


# --- keys --------------------------------------------------------------------------------


async def _holder(session: Db, *, request: Request, body: KeyGrant | SharingConsentIn) -> Person:
    """The person the key is for.

    By phone, a number that is not an account yet becomes one — a name-less account the
    invite will land on when the person proves the number, as the invited door does in
    E01. Whether the number was already known is not something the answer gives away.
    """
    region = settings_of(request).region
    if body.holder_person_id is not None:
        found = await session.get(Person, body.holder_person_id)
        if found is None or found.region is not region:
            raise NoSuchHolder(f"no person {body.holder_person_id} in {region}")
        return found
    return await register_person(
        session, region=region, display_name="", phone_e164=body.holder_phone_e164
    )


@router.post("/{profile_id}/keys", status_code=status.HTTP_201_CREATED)
async def grant(body: KeyGrant, request: Request, context: Context, session: Db) -> KeyOut:
    # Authorise first: nothing is done on the asker's behalf, not even naming the holder,
    # until the key context says he may cut keys at all.
    await may_cut_keys(session, context)
    holder = await _holder(session, request=request, body=body)
    key = await grant_key(
        session,
        context=context,
        holder=holder,
        role=body.role,
        scopes=body.scopes,
        window=body.window,
    )
    return KeyOut.of(key)


@router.get("/{profile_id}/keys")
async def keys(context: Context, session: Db) -> list[KeyOut]:
    return [KeyOut.of(key) for key in await list_keys(session, context=context)]


@router.delete("/{profile_id}/keys/{key_id}")
async def revoke(key_id: uuid.UUID, context: Context, session: Db) -> KeyOut:
    return KeyOut.of(await revoke_key(session, context=context, key_id=key_id))


# --- consent -----------------------------------------------------------------------------


@router.get("/{profile_id}/consents")
async def consents(context: Context, session: Db) -> list[ConsentOut]:
    """Every agreement ever given on this profile, withdrawn ones included, oldest first.
    Read under the family scope: the owner's and his chief's."""
    return [ConsentOut.of(row) for row in await all_consents(session, context=context)]


@router.post("/{profile_id}/consents/sharing", status_code=status.HTTP_201_CREATED)
async def let_someone_in(
    body: SharingConsentIn, request: Request, context: Context, session: Db
) -> ConsentOut:
    """The owner agrees to let one person in, to these parts of his record.

    This is what a key for that person rests on: `POST /profiles/{id}/keys` is refused
    (`ConsentWithheld`) until it is in force. The owner agrees for himself; anyone else
    needs a recorded proxy basis, which is not on this route.
    """
    holder = await _holder(session, request=request, body=body)
    consent = await grant_consent(
        session,
        context=context,
        purpose=ConsentPurpose.SHARE_WITH_PERSON,
        captured_via=body.captured_via,
        basis=ConsentBasis.OWNER,
        language=body.language,
        sharing=Sharing(
            holder=holder,
            scopes=frozenset(body.scopes) - {Scope.PROFILE},
            relationship=body.relationship,
        ),
        text_version=body.wording_version,
    )
    return ConsentOut.of(consent)


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
    """Who touched what on this profile, newest first. Read by the owner, or by someone he
    named to run his care; nobody else."""
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
    """The current facts with subject "medicine", which `app.keys.scopes` puts under the
    medicines scope. A placeholder until E04 builds the medicine line — it is here so a
    caregiver key has something to open — and not to be bound to a patient-mode screen
    before then: attribute codes, units and confidences are not plain words."""
    facts = await current_facts(session, context=context, subject="medicine")
    return [MedicineOut.of(fact) for fact in facts]


# --- readings and State ------------------------------------------------------------------

BLOOD_PRESSURE = "blood_pressure"
READING = "reading"
"""The fact a typed-in blood pressure becomes: subject `blood_pressure`, attribute `reading`,
value `{"systolic": …, "diastolic": …}` in mmHg, resting on the event of taking it."""


@router.post("/{profile_id}/readings", status_code=status.HTTP_201_CREATED)
async def add_reading(body: ReadingIn, context: Context, session: Db) -> ReadingOut:
    """Write down a blood pressure the person typed in.

    The event comes first — a reading, taken then, that came in on the app — and the fact
    names it, so there is no request that could ask for a fact with no provenance: the
    service's `NoProvenance` refusal is proven at the service, not reachable from here. The
    numbers he typed are his own word: the route writes the yes down and uses it in the
    same request, the way the app's save button does, so a later extraction from a photo
    cannot overwrite them (`ConfirmedFactStands`). State recomputes as the fact lands.
    """
    taken_at = body.taken_at or utcnow()
    event = await record_event(
        session,
        context=context,
        kind=EventKind.READING,
        occurred_at=taken_at,
        label="blood pressure",
        source_channel=SourceChannel.APP,
    )
    draft = FactDraft(
        subject=BLOOD_PRESSURE,
        attribute=READING,
        value={"systolic": body.systolic, "diastolic": body.diastolic},
        unit="mmHg",
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None,
    )
    yes = await confirm(session, context, draft)
    fact = await assert_fact(
        session,
        context=context,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        unit=draft.unit,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        event_id=event.id,
        valid_from=taken_at,
    )
    return ReadingOut.of(event, fact)


@router.get("/{profile_id}/state")
async def state(context: Context, session: Db) -> StateOut:
    """The current State: the six dimensions as the caller's key reads them, the posture,
    and what triggered the snapshot. Read under the record's scope; recomputed first when
    the record has moved and the key can recompute."""
    return StateOut.of(await current_state(session, context=context))
