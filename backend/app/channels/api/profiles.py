"""The profile routes. Every one of them takes a key context; none can be reached without one.

`/profiles/mine` is the "for me" door: it opens the caller's own graph. `/profiles/for-someone`
is the second door: a graph set up for someone by his number, held until he claims it, and
`/profiles/mine/claimable` and `/profiles/{id}/claim` are that claim (E01, `app.identity.doors`).
The third door, I was invited, is `GET /doors`. Notes are here so that checkpoint 2 has a
scoped thing to read and a scoped thing to be refused; the medicines routes are in
`app.channels.api.medicines` (E04). Readings and State are here
so that checkpoint 3 has a fact to add and a State to watch recompute; the real capture is
E02.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Query, Request, status

from app.audit.access import audited_profile_read, person_display_name
from app.audit.models import Action
from app.audit.trail import read_audit
from app.channels.api.deps import Context, CurrentPerson, Db, providers_of, settings_of
from app.channels.api.schemas import (
    AuditOut,
    ClaimableOut,
    ClaimConfirmIn,
    ClaimIn,
    ConfirmationOut,
    ConfirmIn,
    ConsentIn,
    ConsentOut,
    KeyChangeConfirmIn,
    KeyGrant,
    KeyOut,
    MedicineConfirmIn,
    NoteIn,
    NoteOut,
    OnlyMeConfirmIn,
    ProfileCreate,
    ProfileForSomeone,
    ProfileOut,
    PushConfirmIn,
    ReadingIn,
    ReadingOut,
    SharingConsentIn,
    StateOut,
    StewardshipOut,
    TaskDoneConfirmIn,
    WhatsAppConsentIn,
)
from app.consent.models import ConsentBasis, ConsentPurpose
from app.consent.service import Sharing, all_consents, grant_consent
from app.db import utcnow
from app.drafts import FactDraft
from app.errors import Refusal
from app.family.privacy import only_me_draft
from app.family.pushes import preview_push, push_draft
from app.family.roster import task_done_draft_for
from app.identity.doors import (
    claim_draft_for,
    claim_profile,
    claimable_for,
    require_stewardship,
    set_up_for_someone,
)
from app.identity.models import Person
from app.identity.service import create_own_profile, register_person
from app.ingestion.review import review_draft_for
from app.keys.confirm import confirm
from app.keys.context import resolve_key_context
from app.keys.grants import grant_key, key_change_draft_for, list_keys, may_cut_keys, revoke_key
from app.keys.scopes import Scope
from app.medicines.service import draft_for
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, EventKind, SourceChannel
from app.memory.semantic import assert_fact
from app.notes.service import list_notes, write_note
from app.safety.boundary import Surface, boundary_line
from app.state.service import current_state

Language = Query(default=None, min_length=2, max_length=16)
"""The language a patient-facing line is asked for: one of Nura's, or the profile's own."""

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


def _account_handle(person: Person) -> str:
    return hashlib.sha256(str(person.id).encode()).hexdigest()[:8]


@router.post("/for-someone", status_code=status.HTTP_201_CREATED)
async def create_for_someone(
    body: ProfileForSomeone, request: Request, person: CurrentPerson, session: Db
) -> ProfileOut:
    """Set up a graph for someone by his phone number; the caller holds it until he claims it.

    One graph per number, ever: a second setup for the same number is refused as
    `AlreadySetUp` (409) in the same words whoever holds the first, naming nobody.
    Refusals before there is a graph are logged at the account, by a handle, like the
    for-me door's.
    """
    region = settings_of(request).region
    try:
        profile, _ = await set_up_for_someone(
            session,
            region=region,
            steward=person,
            patient_phone_e164=body.patient_phone_e164,
            display_name=body.display_name,
            language=body.language,
            consent=body.consent.as_record(),
            basis=body.basis,
            relationship=body.relationship,
            evidence=None if body.evidence is None else body.evidence.as_evidence(),
        )
    except Refusal as refusal:
        log.info(
            "profile door refused: refusal=%s account=%s",
            type(refusal).__name__,
            _account_handle(person),
        )
        raise
    context = await resolve_key_context(
        session, region=region, person_id=person.id, profile_id=profile.id
    )
    return ProfileOut.of(profile, context)


@router.get("/mine/claimable")
async def claimable(
    request: Request,
    person: CurrentPerson,
    session: Db,
    language: str | None = Query(default=None, min_length=2, max_length=16),
) -> list[ClaimableOut]:
    """The graphs set up for the caller's number that wait for his OK, with who set each up,
    what they keep seeing, and the words he is agreeing to — in `language`, or his own."""
    found = await claimable_for(
        session, region=settings_of(request).region, person=person, language=language
    )
    return [ClaimableOut.of(each) for each in found]


@router.post("/{profile_id}/confirmations", status_code=status.HTTP_201_CREATED)
async def mint_confirmation(
    body: ConfirmIn, request: Request, context: Context, session: Db
) -> ConfirmationOut:
    """Write down that the caller said yes to a draft on this profile, and hand him the yes.

    The caller confirms only as himself. For a claim, the draft is recomputed from the
    graph — the stewardship, the steward, the parts, today's words in `language` — so
    the yes binds to what he was shown by `GET /profiles/mine/claimable`. For a review
    card, it is recomputed from the card and his decisions, so the yes binds to every field
    as shown and every decision as made (E02-07: one tap saves the card).
    """
    if isinstance(body, ClaimConfirmIn):
        draft = await claim_draft_for(session, context=context, language=body.language)
        return ConfirmationOut.of(await confirm(session, context, draft))
    if isinstance(body, MedicineConfirmIn):
        # For a medicine, the draft is recomputed from the label and the list
        # (`app.medicines.service.plan`), so the yes binds to what `POST
        # /profiles/{id}/medicines/draft` showed; a label that would write nothing has
        # nothing to say yes to (`AlreadyRecorded`, 409).
        medicine = await draft_for(
            session,
            context=context,
            registry=providers_of(request).drug_registry,
            label=body.label.as_label(),
            source_artifact_id=body.source_artifact_id,
        )
        return ConfirmationOut.of(await confirm(session, context, medicine))
    if isinstance(body, KeyChangeConfirmIn):
        # Narrowing a key (E12-01): the draft is recomputed from the key, so a yes cannot
        # be minted for anything wider than it opens; `WouldWiden` refuses here already.
        _, _, _, change = await key_change_draft_for(
            session, context=context, key_id=body.key_id, scopes=body.scopes, window=body.window
        )
        return ConfirmationOut.of(await confirm(session, context, change))
    if isinstance(body, OnlyMeConfirmIn):
        return ConfirmationOut.of(
            await confirm(session, context, only_me_draft(body.scope, only_me=body.only_me))
        )
    if isinstance(body, TaskDoneConfirmIn):
        # The doer's own tap (E12-03): the task must name the person minting.
        done = await task_done_draft_for(session, context=context, task_id=body.task_id)
        return ConfirmationOut.of(await confirm(session, context, done))
    if isinstance(body, PushConfirmIn):
        # The yes binds to the lines exactly as previewed (E12-06).
        preview = await preview_push(
            session,
            context=context,
            template_id=body.template_id,
            slots=body.slots,
            memo_lines=body.memo_lines,
            language=body.language,
        )
        push = push_draft(
            preview, send_at=body.send_at, channel=body.channel, expires_at=body.expires_at
        )
        return ConfirmationOut.of(await confirm(session, context, push))
    review = await review_draft_for(
        session,
        context=context,
        card_id=body.card_id,
        decisions=[decision.as_decision() for decision in body.decisions],
    )
    return ConfirmationOut.of(await confirm(session, context, review))


@router.post("/{profile_id}/claim")
async def claim(body: ClaimIn, context: Context, session: Db) -> ProfileOut:
    """The patient claims the graph set up for him, with the yes he minted for it.

    Ownership passes to him; his agreement to Nura keeping the record is recorded in his
    words and the steward's withdrawn; he lets the steward in as a chief on a per-person
    consent; the steward's key is cut again resting on it; the stewardship closes. All on
    the trail. Anyone but the claimant is refused `NotTheClaimant` (403), and that is on
    the trail too.
    """
    profile = await claim_profile(
        session,
        context=context,
        confirmation_id=body.confirmation_id,
        language=body.language,
        captured_via=body.captured_via,
    )
    owner = await resolve_key_context(
        session, region=context.region, person_id=context.person_id, profile_id=profile.id
    )
    return ProfileOut.of(profile, owner)


@router.get("/{profile_id}/stewardship")
async def stewardship(context: Context, session: Db) -> StewardshipOut:
    """Who holds this graph for the patient and on what footing, or held it until he claimed
    it. Read under the profile scope, which every key holds: who holds a graph is part of
    whose graph it is. `NoStewardshipHere` (404) if it was never set up for someone."""
    found = await require_stewardship(session, context=context)
    return StewardshipOut.of(
        found, await person_display_name(session, context, found.steward_person_id)
    )


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
    """Every key on the profile, each with its holder's name: the owner reads who holds what,
    and the app can say whom to call."""
    return [
        KeyOut.of(key, await person_display_name(session, context, key.holder_person_id))
        for key in await list_keys(session, context=context)
    ]


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


@router.post("/{profile_id}/consents/whatsapp", status_code=status.HTTP_201_CREATED)
async def agree_to_whatsapp(
    body: WhatsAppConsentIn, context: Context, session: Db
) -> ConsentOut:
    """The owner agrees to WhatsApp: the morning card, the thread, every send (E19).

    Profile-wide and on his own basis; a chief acting for him needs a recorded proxy basis,
    which is not on this route. Without this in force the number keeps no thread with
    anyone about him and sends him nothing.
    """
    consent = await grant_consent(
        session,
        context=context,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=body.captured_via,
        basis=ConsentBasis.OWNER,
        language=body.language,
        text_version=body.wording_version,
    )
    return ConsentOut.of(consent)


@router.post("/{profile_id}/consents/recording", status_code=status.HTTP_201_CREATED)
async def agree_to_recording(body: ConsentIn, context: Context, session: Db) -> ConsentOut:
    """The owner agrees to Nura keeping what is said (E16-02), in today's words.

    Every VOICE artefact rests on this consent where its bytes land (`store_artifact`): a
    recording of a visit, and a voice note left on an event (E02-06). The owner agrees for
    himself; anyone else needs a recorded proxy basis, which is not on this route. Words
    that are not today's are refused, and the refusal is on the trail.
    """
    consent = await grant_consent(
        session,
        context=context,
        purpose=ConsentPurpose.RECORDING,
        captured_via=body.captured_via,
        basis=ConsentBasis.OWNER,
        language=body.language,
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


# --- notes -------------------------------------------------------------------------------


@router.get("/{profile_id}/notes")
async def notes(context: Context, session: Db) -> list[NoteOut]:
    return [NoteOut.of(note) for note in await list_notes(session, context=context)]


@router.post("/{profile_id}/notes", status_code=status.HTTP_201_CREATED)
async def add_note(body: NoteIn, context: Context, session: Db) -> NoteOut:
    return NoteOut.of(await write_note(session, context=context, text=body.text))


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
async def state(context: Context, session: Db, language: str | None = Language) -> StateOut:
    """The current State: the six dimensions as the caller's key reads them, the posture,
    and what triggered the snapshot. Read under the record's scope; recomputed first when
    the record has moved and the key can recompute. The posture is an inferring surface,
    so the answer carries the boundary line (E16-01) in `language`, or the profile's own."""
    view = await current_state(session, context=context)
    if language is None:
        language = (await audited_profile_read(session, context)).language
    return StateOut.of(view, boundary=boundary_line(Surface.STATE_POSTURE, language))
