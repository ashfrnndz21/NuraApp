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

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read, audited_read, person_display_name
from app.audit.models import Action
from app.audit.trail import read_audit
from app.channels.api.daily_schemas import ProposalConfirmIn, RoutineConfirmIn
from app.channels.api.deps import (
    ClosingContext,
    Context,
    CurrentPerson,
    Db,
    providers_of,
    settings_of,
)
from app.channels.api.schemas import (
    WITHHELD_TARGET,
    AppointmentConfirmIn,
    AttachConfirmIn,
    AuditOut,
    ClaimableOut,
    ClaimConfirmIn,
    ClaimIn,
    CloseConfirmIn,
    ConfirmationOut,
    ConfirmIn,
    ConsentIn,
    ConsentOut,
    CountCorrectionConfirmIn,
    DriveConfirmIn,
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
    QuestionConfirmIn,
    ReadingIn,
    ReadingOut,
    SharingConsentIn,
    SharingPreviewIn,
    SharingPreviewOut,
    StateOut,
    StatusConfirmIn,
    StewardshipOut,
    SummaryConfirmIn,
    TaskDoneConfirmIn,
    WhatsAppConsentIn,
    WithdrawalOut,
    WithdrawIn,
    WithdrawnOut,
)
from app.channels.printable import PrintableConsentRenderer
from app.channels.whatsapp.group import group_of, sync_group
from app.consent.export import export_consent_record
from app.consent.models import Consent, ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import (
    HolderNeedsAName,
    Sharing,
    SharingWords,
    all_consents,
    grant_consent,
    may_invite,
    preview_sharing,
    withdraw_consent,
    withdrawal_of,
)
from app.consent.texts import named_words
from app.consent.withdrawal import stop_lines, stopped_lines
from app.db import as_utc, utcnow
from app.drafts import AppointmentDraft, AttachDraft, FactDraft, StatusChange
from app.errors import Refusal
from app.family.privacy import only_me_draft
from app.family.pushes import preview_push, push_draft
from app.family.roster import task_done_draft_for
from app.identity.closing import close_draft_for
from app.identity.doors import (
    claim_draft_for,
    claim_profile,
    claimable_for,
    require_stewardship,
    set_up_for_someone,
)
from app.identity.models import Person, Stewardship
from app.identity.service import create_own_profile, invitee_by_phone
from app.ingestion.connectors.service import proposal_draft_for
from app.ingestion.review import review_draft_for
from app.keys.confirm import confirm
from app.keys.context import KeyContext, only_the_owner_while_closing, resolve_key_context
from app.keys.grants import grant_key, key_change_draft_for, list_keys, may_cut_keys, revoke_key
from app.keys.scopes import Scope
from app.medicines.reorder import count_correction_draft_for
from app.medicines.service import draft_for
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, EventKind, SourceChannel, short_label
from app.memory.semantic import assert_fact
from app.notes.service import list_notes, write_note
from app.reasoning.visits.logistics import drive_draft_for
from app.reasoning.visits.questions import question_draft_for
from app.reasoning.visits.summary import summary_draft_for
from app.routines.service import routine_draft_for
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
    as shown and every decision as made (E02-07: one tap saves the card). For a visit, it is
    with whom, when and why; for a question, the words as typed; for a post-visit summary,
    every item as decided (E05).
    """
    if isinstance(body, CloseConfirmIn):
        closing = await close_draft_for(
            session,
            context=context,
            language=body.language,
            retention_days=settings_of(request).account_retention_days,
        )
        return ConfirmationOut.of(await confirm(session, context, closing))
    if isinstance(body, ClaimConfirmIn):
        draft = await claim_draft_for(session, context=context, language=body.language)
        return ConfirmationOut.of(await confirm(session, context, draft))
    if isinstance(body, AppointmentConfirmIn):
        booking = AppointmentDraft(
            provider_id=body.provider_id,
            scheduled_at=body.scheduled_at,
            purpose=short_label(body.purpose),
        )
        return ConfirmationOut.of(await confirm(session, context, booking))
    if isinstance(body, QuestionConfirmIn):
        asked = await question_draft_for(
            session,
            context=context,
            appointment_id=body.appointment_id,
            text=body.text,
            question_id=body.question_id,
            remove=body.remove,
        )
        return ConfirmationOut.of(await confirm(session, context, asked))
    if isinstance(body, SummaryConfirmIn):
        heard = await summary_draft_for(
            session,
            context=context,
            summary_id=body.summary_id,
            decisions=[decision.as_decision() for decision in body.decisions],
        )
        return ConfirmationOut.of(await confirm(session, context, heard))
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
    if isinstance(body, DriveConfirmIn):
        # Who drives him to a visit (E05-03): the chief's yes, recomputed from the visit and
        # the person, so it cannot be minted for a visit that has been or a stranger.
        drive = await drive_draft_for(
            session, context=context, appointment_id=body.appointment_id, person_id=body.person_id
        )
        return ConfirmationOut.of(await confirm(session, context, drive))
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
    if isinstance(body, CountCorrectionConfirmIn):
        # Tablets found at home (E04-05): an active line on this profile, a key that may
        # change the list, and the number as typed; the yes binds to that number.
        more = await count_correction_draft_for(
            session, context=context, line_id=body.line_id, quantity=body.quantity
        )
        return ConfirmationOut.of(await confirm(session, context, more))
    if isinstance(body, RoutineConfirmIn):
        # The day (E10-01): the draft is recomputed — times checked, the routine it replaces
        # named — so the yes binds to exactly what `PUT /routine` writes.
        day = await routine_draft_for(
            session,
            context=context,
            anchors=body.anchors,
            reading_prompts=body.reading_prompts,
            walks=body.walks,
            morning_card_at=body.morning_card_at,
        )
        return ConfirmationOut.of(await confirm(session, context, day))
    if isinstance(body, ProposalConfirmIn):
        # A visit a calendar proposed (E18-02): the draft is recomputed from the proposal.
        proposed = await proposal_draft_for(session, context=context, proposal_id=body.proposal_id)
        return ConfirmationOut.of(await confirm(session, context, proposed))
    if isinstance(body, AppointmentConfirmIn):
        # A visit (E03-01): exactly the provider, time and purpose `POST /appointments` will
        # write, the purpose trimmed the way the booking trims it.
        visit = AppointmentDraft(
            provider_id=body.provider_id,
            scheduled_at=body.scheduled_at,
            purpose=short_label(body.purpose),
        )
        return ConfirmationOut.of(await confirm(session, context, visit))
    if isinstance(body, StatusConfirmIn):
        step = StatusChange(appointment_id=body.appointment_id, status=body.status)
        return ConfirmationOut.of(await confirm(session, context, step))
    if isinstance(body, AttachConfirmIn):
        # Hanging a paper off an episode or a visit (E03-01, E03-02).
        hang = AttachDraft(
            artifact_id=body.artifact_id,
            episode_id=body.episode_id,
            appointment_id=body.appointment_id,
        )
        return ConfirmationOut.of(await confirm(session, context, hang))
    review = await review_draft_for(
        session,
        context=context,
        card_id=body.card_id,
        decisions=[decision.as_decision() for decision in body.decisions],
        episode_id=body.episode_id,
    )
    return ConfirmationOut.of(await confirm(session, context, review))


@router.post("/{profile_id}/claim")
async def claim(body: ClaimIn, request: Request, context: Context, session: Db) -> ProfileOut:
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
    # His now: whoever reads the family thread is set in the family's WhatsApp group again,
    # under his own key, not the claimant's (#143).
    owner = await resolve_key_context(
        session,
        region=settings_of(request).region,
        person_id=context.person_id,
        profile_id=context.profile_id,
    )
    await sync_group(session, context=owner, provider=providers_of(request).whatsapp)
    return ProfileOut.of(profile, owner)


@router.get("/{profile_id}/stewardship")
async def stewardship(
    person: CurrentPerson, context: Context, session: Db, language: str | None = Language
) -> StewardshipOut:
    """Who holds this graph for the patient and on what footing, or held it until he claimed
    it. Read under the profile scope, which every key holds: who holds a graph is part of
    whose graph it is. `NoStewardshipHere` (404) if it was never set up for someone."""
    found = await require_stewardship(session, context=context)
    return StewardshipOut.of(
        found,
        await person_display_name(session, context, found.steward_person_id),
        language or person.language,
    )


@router.get("/{profile_id}")
async def get_profile(context: Context, session: Db) -> ProfileOut:
    """The profile as the caller holds it: name, language, and what his key opens.

    Read under `Scope.PROFILE`, which every key holds, and written down like any read.
    """
    return ProfileOut.of(await audited_profile_read(session, context), context)


# --- keys --------------------------------------------------------------------------------


async def _holder(
    session: Db,
    *,
    request: Request,
    body: KeyGrant | SharingConsentIn,
    name: str = "",
    named_by: uuid.UUID | None = None,
) -> Person:
    """The person the key is for.

    By phone, a number that is not an account yet becomes one — the account the invite will
    land on when the person proves the number, as the invited door does in E01 — carrying the
    name the owner typed and who typed it, until the person gives his own. Whether the number
    was already known is not something the answer gives away.
    """
    region = settings_of(request).region
    if body.holder_person_id is not None:
        found = await session.get(Person, body.holder_person_id)
        if found is None or found.region is not region:
            raise NoSuchHolder(f"no person {body.holder_person_id} in {region}")
        return found
    assert body.holder_phone_e164 is not None
    return await invitee_by_phone(
        session, region=region, phone_e164=body.holder_phone_e164, name=name, named_by=named_by
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
    # The family's WhatsApp group is who reads the family thread: set again from the keys.
    await sync_group(session, context=context, provider=providers_of(request).whatsapp)
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
async def revoke(key_id: uuid.UUID, request: Request, context: Context, session: Db) -> KeyOut:
    closed = await revoke_key(session, context=context, key_id=key_id)
    # A key closed is a person out of the family's WhatsApp group, now (E11-01).
    await sync_group(session, context=context, provider=providers_of(request).whatsapp)
    return KeyOut.of(closed)


# --- consent -----------------------------------------------------------------------------


@router.get("/{profile_id}/consents")
async def consents(context: ClosingContext, session: Db) -> list[ConsentOut]:
    """Every agreement ever given on this profile, withdrawn ones included, oldest first.
    Read under the family scope: the owner's and his chief's. While his account is closing
    (#143) it stays his to read, and nobody else's."""
    await only_the_owner_while_closing(session, context)
    return [ConsentOut.of(row) for row in await all_consents(session, context=context)]


@router.get("/{profile_id}/consents/record.html", response_class=HTMLResponse)
async def consent_record_page(request: Request, context: Context, session: Db) -> HTMLResponse:
    """Every agreement ever given on this profile, withdrawn ones included, as one printable
    page to keep (the PDPA record): the words as they were read, who agreed, for whom, how,
    when and when it stopped, with no health content. Self-contained like the emergency
    card's page. The owner's and his chief's; the page leaving is a share on his trail."""
    record = await export_consent_record(
        session,
        context=context,
        renderer=PrintableConsentRenderer(demo=settings_of(request).demo_mode),
    )
    return HTMLResponse(
        record.rendered.body.decode(),
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
        },
    )


@router.get("/{profile_id}/consents/{consent_id}/withdrawal")
async def withdrawal(
    consent_id: uuid.UUID,
    request: Request,
    context: Context,
    session: Db,
    language: str | None = Language,
) -> WithdrawalOut:
    """What stopping this agreement will do, in his words, for the confirm step. The owner's
    alone (`NotTheirConsentToWithdraw`, 403); an agreement already stopped or not on this
    profile is `NoConsentToWithdraw` (404). Nothing is written but the read on his trail.

    Stopping WhatsApp says exactly what changes (#143): what stops reaching him, that he
    leaves his family's group, and who is still told when he is unwell — on their own keys.
    Keeping his papers is stopped by closing his account: its lines are the closing's."""
    row = await withdrawal_of(session, context=context, consent_id=consent_id, allow_closing=True)
    words = language or (await audited_profile_read(session, context)).language
    if row.purpose is ConsentPurpose.HOLD_HEALTH_RECORD:
        draft = await close_draft_for(
            session,
            context=context,
            language=words,
            retention_days=settings_of(request).account_retention_days,
        )
        return WithdrawalOut(
            consent_id=row.id, purpose=row.purpose, lines=list(draft.lines), closes_account=True
        )
    in_group, still_told = await _what_whatsapp_changes(session, context, row, words)
    return WithdrawalOut(
        consent_id=row.id,
        purpose=row.purpose,
        lines=stop_lines(
            row.purpose,
            name=await _named(session, context, row),
            language=words,
            told=_told(row),
            in_group=in_group,
            still_told=still_told,
        ),
    )


@router.post("/{profile_id}/consents/{consent_id}/withdraw")
async def withdraw(
    consent_id: uuid.UUID, body: WithdrawIn, request: Request, context: Context, session: Db
) -> WithdrawnOut:
    """The owner stops one agreement. For letting someone in, that person's keys close in
    the same transaction, and nothing still waiting to be sent reaches them; for WhatsApp, he
    is out of his family's group. Either way the group is set again now, not at its next use
    (#143). The rows stay, marked with when and by whom; the printable record says so.
    Keeping his papers is refused here (`StopsByClosingTheAccount`, 409): that is `/closure`."""
    words = body.language or (await audited_profile_read(session, context)).language
    preview = await withdrawal_of(session, context=context, consent_id=consent_id)
    in_group, still_told = await _what_whatsapp_changes(session, context, preview, words)
    row, withdrawn = await withdraw_consent(
        session, context=context, consent_id=consent_id, captured_via=ConsentChannel.APP
    )
    await sync_group(session, context=context, provider=providers_of(request).whatsapp)
    return WithdrawnOut(
        consent_id=row.id,
        purpose=row.purpose,
        withdrawn=[ConsentOut.of(each) for each in withdrawn],
        lines=stopped_lines(
            row.purpose,
            name=await _named(session, context, row),
            language=words,
            told=_told(row),
            in_group=in_group,
            still_told=still_told,
        ),
    )


async def _what_whatsapp_changes(
    session: AsyncSession, context: KeyContext, row: Consent, language: str
) -> tuple[bool, list[str]]:
    """For stopping WhatsApp: whether he is in his family's group there, and everyone a red
    flag still reaches — each live key holding the emergency card, named as the words name
    them, with who they are to him when a stewardship says (the relationship code, in his
    language). Nothing for any other agreement."""
    if row.purpose is not ConsentPurpose.WHATSAPP:
        return False, []
    in_group = await group_of(session, context=context) is not None
    moment = utcnow()
    said = {
        each.steward_person_id: each.relationship
        for each in sorted(
            await audited_read(session, Stewardship, context, Scope.FAMILY),
            key=lambda one: as_utc(one.opened_at),
        )
    }
    named: list[str] = []
    seen: set[uuid.UUID] = set()
    for key in sorted(
        await list_keys(session, context=context), key=lambda k: as_utc(k.granted_at)
    ):
        if key.holder_person_id in seen or not key.is_active(moment):
            continue
        if Scope.EMERGENCY not in key.scopes_held:
            continue
        seen.add(key.holder_person_id)
        name = await person_display_name(session, context, key.holder_person_id)
        named.append(named_words(name, said.get(key.holder_person_id), language))
    return in_group, named


def _told(row: Consent) -> bool:
    """Whether the person this agreement lets in is one a red flag reaches: the emergency card
    is among the parts it names."""
    if row.purpose is not ConsentPurpose.SHARE_WITH_PERSON:
        return False
    return row.scopes is None or Scope.EMERGENCY.value in row.scopes


async def _named(session: AsyncSession, context: KeyContext, row: Consent) -> str:
    """The person an agreement lets in, by name; nobody for a profile-wide one."""
    if row.holder_person_id is None:
        return ""
    return await person_display_name(session, context, row.holder_person_id)


@router.post("/{profile_id}/consents/sharing", status_code=status.HTTP_201_CREATED)
async def let_someone_in(
    body: SharingConsentIn, request: Request, context: Context, session: Db
) -> ConsentOut:
    """The owner agrees to let one person in, to these parts of his record.

    This is what a key for that person rests on: `POST /profiles/{id}/keys` is refused
    (`ConsentWithheld`) until it is in force. The owner agrees for himself; anyone else
    needs a recorded proxy basis, which is not on this route.
    """
    # Who may let someone in, and whether the words have a name, are settled before anything
    # is written: a refused caller leaves no account behind for the number he gave.
    await may_invite(session, context=context)
    named = (body.holder_display_name or "").strip()
    if body.holder_phone_e164 is not None and not named:
        # The words name the person; nothing is made for the number without that name.
        raise HolderNeedsAName("a person let in by phone is named by the one letting them in")
    holder = await _holder(
        session, request=request, body=body, name=named, named_by=context.person_id
    )
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
            named=named or None,
        ),
        text_version=body.wording_version,
    )
    return ConsentOut.of(consent)


@router.post("/{profile_id}/consents/sharing/preview")
async def preview_letting_in(
    body: SharingPreviewIn, request: Request, context: Context, session: Db
) -> SharingPreviewOut:
    """The words the owner would agree to by `POST /consents/sharing` for this person and these
    parts, rendered now by the function the consent keeps them with — so what he reads first
    is what is kept, word for word. Nothing is written but the READ on his trail: no account
    is made for a number, and by phone the words use only the name he typed, so they never
    say whether the number is already someone's. The owner's, or the steward's setting up for
    him; `HolderNeedsAName` (400) without a name."""
    if body.holder_person_id is not None:
        found = await session.get(Person, body.holder_person_id)
        if found is None or found.region is not settings_of(request).region:
            raise NoSuchHolder(
                f"no person {body.holder_person_id} in {settings_of(request).region}"
            )
        name = found.display_name.strip()
    else:
        name = (body.holder_display_name or "").strip()
    version, words = await preview_sharing(
        session,
        context=context,
        about=SharingWords(
            name=name,
            relationship=body.relationship,
            scopes=frozenset(body.scopes) - {Scope.PROFILE},
        ),
        language=body.language,
    )
    return SharingPreviewOut(
        wording_version=version, language=body.language, lines=words.split("\n")
    )


@router.post("/{profile_id}/consents/whatsapp", status_code=status.HTTP_201_CREATED)
async def agree_to_whatsapp(
    body: WhatsAppConsentIn, request: Request, context: Context, session: Db
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
    # His agreement in force: he is in the family's group again, now (#143).
    await sync_group(session, context=context, provider=providers_of(request).whatsapp)
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
    since: AwareDatetime | None = None,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[AuditOut]:
    """Who touched what on this profile, newest first. Read by the owner, or by someone he
    named to run his care; nobody else. A line written under a scope the reader's key does
    not hold is shown without the id of the row it touched, and says so."""
    entries = await read_audit(
        session,
        context=context,
        action=action,
        scope=scope,
        actor_person_id=actor_person_id,
        since=since,
        limit=limit,
    )
    return [
        AuditOut.of(
            entry,
            () if entry.target_id is None or context.allows(entry.scope) else (WITHHELD_TARGET,),
        )
        for entry in entries
    ]


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
        episode_id=body.episode_id,
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
        episode_id=body.episode_id,
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
        episode_id=body.episode_id,
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
    return StateOut.of(
        view, boundary=boundary_line(Surface.STATE_POSTURE, language), language=language
    )
