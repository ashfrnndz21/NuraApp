"""One inbound message, from the provider's webhook to the reply in the thread (E19-02).

The order is the design: the sender's number is resolved to a Person and to the one profile
they may act on; the words are read for a red flag *before* anything else — before "ignore",
and before the profile's WHATSAPP consent — and a flag is written first. "Ignore that, he
fell" is still a fall; and on a profile whose patient has not agreed to WhatsApp, a fall is
still raised, on the word alone (the message is not kept), escalated through the family's app
rather than to anyone's WhatsApp, and answered with one fixed line. Then the consent is
checked, the thread is found and its window opened; then the classifier says what the message is, and the thread does the one
thing that kind allows — a document through the review card, a health event as a proposal,
a yes or a no against the poster's own open proposal, coordination kept for the family, and
everything else not kept at all. Every step runs inside the sender's key context through
the same doors as the app, so an out-of-scope caregiver gets the same refusal, on the trail.
A stranger's message gets one fixed reply and leaves nothing behind.

A voice note is heard in the region before any of that, whoever sent it, so its words are
read like a message's. One with no words in it — a mumble, the transcriber down, the audio
never fetched — may carry a red word nobody could read, so a person is always told: the
chief on her own channels, as an alert that climbs a ladder of its own (#173). That holds for
the helper's note as much as his, and on a profile whose patient has not agreed to WhatsApp,
where nothing of the note is kept and the sender gets one fixed line.

Past the red-flag check, a heard voice note's transcript is classified through the same door
the classifier reads a typed message through (E11-01): "Taken" said aloud writes the tap "Taken"
typed does, and his own word answers an open check-in or proposal exactly as typing it would —
but only at or above `CONFIDENCE_THRESHOLD` (`app/ingestion/models.py`), the same floor a
scanned document field is held to before it is trusted undotted. A Taken tap stops the
escalation ladder, so a transcript too unsure to trust is never let close it on a guess: below
the floor, or on anything the classifier did not read as TAKEN or an answer, the note is kept
as his own, unread, and he is asked again — nothing is lost, and nothing is silently assumed.
An unintelligible note is never guessed into one of those — it stays what it always was, kept
as his own note, with the family told when nothing could be heard in it at all.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard, audited_profile_read, audited_read, audited_write
from app.audit.models import Action, Channel, Outcome
from app.audit.trail import record
from app.channels.api.deps import Providers
from app.channels.whatsapp.classifier import (
    FEELING,
    Classification,
    Classifier,
    HealthEvent,
    Kind,
)
from app.channels.whatsapp.config import BusinessNumber
from app.channels.whatsapp.group import is_member, sync_group
from app.channels.whatsapp.models import (
    Direction,
    DoseQuestion,
    MessageKind,
    WhatsAppMessage,
    WhatsAppThread,
)
from app.channels.whatsapp.outbound.send import Delivered, send, thread_for
from app.channels.whatsapp.proposals import (
    PROPOSAL,
    NoOpenProposal,
    ProposalExpired,
    answer,
    propose,
)
from app.channels.whatsapp.provider import InboundMessage, Media, MediaTooLarge, NoSuchMedia
from app.channels.whatsapp.strings import (
    BOXED,
    DOSE_CHOICE,
    DOSE_CHOICE_BARE,
    FEELING_WORDS,
    TOOK,
    YOU,
    YOUR_DOCTOR,
    join_names,
    red_flag_reply_key,
    reply,
)
from app.channels.whatsapp.templates import language_of
from app.consent.models import ConsentPurpose
from app.consent.service import NoConsent, require_consent
from app.db import as_utc, nested_unit_of_work, unit_of_work, utcnow
from app.delivery.strings import EMERGENCY_NUMBER, theirs
from app.delivery.triggers.deliver import Via, open_run
from app.delivery.triggers.ladder import (
    DoseAsked,
    acknowledge_dose,
    acknowledge_flag,
    climb_unheard,
    close,
    doses_for_reply,
    escalate_flag,
    medicine_words,
    unheard_ladder,
)
from app.delivery.triggers.models import PHONE, DeliveryOutcome, Ladder, TriggerType
from app.drafts import FactDraft
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.family.thread import post_message
from app.identity.models import Person, Profile
from app.identity.service import find_person_by_phone
from app.ingestion.models import CONFIDENCE_THRESHOLD
from app.ingestion.notes import MAX_VOICE_BYTES, NoteView, keep_voice_message
from app.ingestion.objects import check_key, sha256_of
from app.ingestion.photos import store_photo
from app.ingestion.review import review_photo
from app.ingestion.transcribe import NOTHING_HEARD, Transcript
from app.keys.confirm import confirm
from app.keys.context import (
    KeyContext,
    OutOfScope,
    closing_since,
    owned_profile,
    resolve_key_context,
)
from app.keys.handles import profile_for_group
from app.keys.models import Key
from app.keys.scopes import Scope, scope_for_subject
from app.medicines.service import record_dose_taken
from app.medicines.service import today as doses_today
from app.medicines.strings import ANCHOR_WORDS, PLAIN_NAME, say_date
from app.memory.episodic import record_event, store_artifact
from app.memory.models import (
    Artifact,
    ArtifactKind,
    ConfidenceState,
    Event,
    EventKind,
    Provider,
    ProviderKind,
    SourceChannel,
)
from app.memory.semantic import assert_fact, current_facts
from app.regions import REGION_TZ, OutOfRegion, Region, guard_region
from app.safety.red_flags import (
    FLAG_WINDOW,
    NIGHT_UNTIL,
    Flag,
    detect,
    escalation_now,
    flag_to_raise,
    raise_flag,
    record_the_moment,
)
from app.settings import Settings

log = logging.getLogger("nura.channels.whatsapp")

MESSAGE = WhatsAppMessage.__tablename__
TEXT_CONTENT_TYPE = "text/plain; charset=utf-8"
IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/heic", "image/webp"})
PDF_CONTENT_TYPE = "application/pdf"
FEELING_VOCABULARY = frozenset({"ok", "tired", "pain"})
CHECK_IN_OK = dict(FEELING)["ok"]
"""His "OK": a yes when something of his is open to say yes to, else his check-in answer."""
OK_FEELING = HealthEvent(
    subject="feeling",
    attribute="reported",
    value="ok",
    unit=None,
    event_kind=EventKind.SYMPTOM,
    said="feeling",
    words={},
    word="ok",
)


class NotADocument(Refusal):
    """The media was neither a photo nor a PDF."""


@dataclass(frozen=True, slots=True)
class Handled:
    """What one inbound message became: what was kept, and what was said back."""

    outcome: str
    replies: tuple[Delivered, ...] = ()
    profile_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    artifact_id: uuid.UUID | None = None
    proposal_id: uuid.UUID | None = None
    fact_id: uuid.UUID | None = None
    flag_id: uuid.UUID | None = None
    review_card_id: uuid.UUID | None = None
    stranger_reply: str | None = None
    """The one fixed reply to a number no profile knows: sent, and kept on no trail."""
    refused: str | None = None
    note_id: uuid.UUID | None = None
    """His own voice note, kept as his note (E11-01)."""
    thread_message_id: uuid.UUID | None = None
    """A message from the family's group, landed in the family thread (E11-01)."""


@dataclass(slots=True)
class _Work:
    settings: Settings
    providers: Providers
    number: BusinessNumber
    classifier: Classifier
    message: InboundMessage
    person: Person
    context: KeyContext
    profile: Profile
    thread: WhatsAppThread
    language: str
    replies: list[Delivered] = field(default_factory=list)
    voice: Media | None = None
    """A voice note's audio, fetched from the provider and heard in the region (E11-01)."""
    heard: Transcript | None = None
    voice_missing: bool = False
    """A voice note whose audio could not be fetched, or ran past its cap: nothing of it heard."""


def _handle(person_id: uuid.UUID | None, phone: str) -> str:
    """A short handle for the log: never the number, never the id."""
    return hashlib.sha256(f"{person_id}:{phone}".encode()).hexdigest()[:8]


# --- resolving the sender ------------------------------------------------------------------


async def _profiles_reachable(
    session: AsyncSession, *, region: Region, person: Person, closing: bool = False
) -> list[uuid.UUID]:
    """The profiles this person may act on here: their own, then every live key's. A profile
    whose account is closing is nobody's to act on (#143); with `closing`, only those."""
    moment = utcnow()
    found: list[uuid.UUID] = []
    own = await owned_profile(session, region=region, owner_person_id=person.id)
    if own is not None:
        found.append(own.id)
    keys = await session.scalars(
        select(Key).where(Key.holder_person_id == person.id).order_by(Key.granted_at)
    )
    for key in keys:
        if key.is_active(moment) and key.profile_id not in found:
            profile = await session.get(Profile, key.profile_id)
            if profile is not None and profile.region is region:
                found.append(key.profile_id)
    return [
        profile_id
        for profile_id in found
        if (await closing_since(session, profile_id=profile_id) is not None) is closing
    ]


async def _not_kept_in_the_group(
    providers: Providers, message: InboundMessage, *, region: Region, language: str | None
) -> Handled:
    """A post in a family's group from a number that is not in that family now — a stranger,
    a number kept elsewhere, a key closed since (#143). Nothing is kept and nothing is said
    into the group; a red word is answered to the sender alone, with who to call, because a
    red word is never met with silence."""
    if detect(message.text) is not None:
        return await _stranger(
            providers,
            message,
            key="group_not_kept",
            language=language,
            emergency_number=EMERGENCY_NUMBER[region.value],
        )
    return Handled(outcome="ignored")


async def _answer_while_closing(
    session: AsyncSession,
    *,
    providers: Providers,
    classifier: Classifier,
    message: InboundMessage,
    person: Person,
    region: Region,
    closing: Sequence[uuid.UUID],
) -> Handled | None:
    """A yes, while a family's closing stands, is the answer to a red flag of theirs raised
    before the closing that reached this number (the engine still carries those, #143): the
    ladder asks nobody else. Nothing else is taken in; None when it is not that."""
    if not message.text:
        return None
    heard = classifier.classify(text=message.text, content_type=None)
    if heard.kind is not Kind.ANSWER or not heard.answer:
        return None
    for profile_id in closing:
        context = await resolve_key_context(
            session, region=region, person_id=person.id, profile_id=profile_id, while_closing=True
        )
        if not context.allows(Scope.EMERGENCY):
            continue
        answered = await acknowledge_flag(session, context=context, channel=Channel.WHATSAPP)
        if answered is not None:
            await providers.whatsapp.send_text(
                message.from_e164, reply("flag_seen", person.language)
            )
            return Handled(outcome="flag_acknowledged", profile_id=profile_id)
    return None


async def _most_recent_thread(
    session: AsyncSession, *, person: Person, profiles: Sequence[uuid.UUID]
) -> uuid.UUID | None:
    """Among several profiles, the one this number last talked to, if any."""
    threads = list(
        await session.scalars(
            select(WhatsAppThread).where(
                WhatsAppThread.person_id == person.id, WhatsAppThread.profile_id.in_(profiles)
            )
        )
    )
    with_traffic = [t for t in threads if t.last_inbound_at is not None]
    if not with_traffic:
        return None
    latest = max(with_traffic, key=lambda t: as_utc(t.last_inbound_at or utcnow()))
    return latest.profile_id


async def _stranger(
    providers: Providers,
    message: InboundMessage,
    *,
    key: str = "unknown_number",
    language: str | None = None,
    **params: str,
) -> Handled:
    """One fixed reply, no health content, nothing stored. Logged by a handle."""
    text = reply(key, language, **params)
    await providers.whatsapp.send_text(message.from_e164, text)
    log.info("whatsapp: %s reply to %s", key, _handle(None, message.from_e164))
    return Handled(outcome=key, stranger_reply=text)


# --- keeping things ---------------------------------------------------------------------------


async def _keep_text(
    session: AsyncSession, *, work: _Work, scope: Scope = Scope.RECORDS
) -> Artifact:
    """The words, as an artefact in the region's store: bytes by digest, the row a reference.

    Under the record's scope for a health event; under the family scope for coordination,
    which is the family's business and not the record's. The same checks `store_artifact`
    makes — the region pin, the agreement to keep the record — under a door that says which
    channel the words came in on.
    """
    data = (work.message.text or "").encode("utf-8")
    store = work.providers.object_store
    guard_region(held_in=store.region, asked_from=work.context.region)
    digest = sha256_of(data)
    key = check_key(f"messages/{work.context.profile_id}/{digest}")
    await require_consent(
        session,
        context=work.context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=scope,
        channel=Channel.WHATSAPP,
    )
    await store.put(key, data)
    return await audited_write(
        session,
        Artifact,
        work.context,
        scope,
        channel=Channel.WHATSAPP,
        kind=ArtifactKind.MESSAGE,
        storage_key=key,
        content_type=TEXT_CONTENT_TYPE,
        sha256=digest,
        captured_at=work.message.at,
        source_channel=SourceChannel.WHATSAPP,
        region=store.region,
        stored_at=utcnow(),
    )


async def _keep_row(
    session: AsyncSession,
    *,
    work: _Work,
    kind: MessageKind,
    artifact: Artifact | None,
    flag_id: uuid.UUID | None = None,
) -> WhatsAppMessage:
    return await audited_write(
        session,
        WhatsAppMessage,
        work.context,
        Scope.PROFILE,
        channel=Channel.WHATSAPP,
        thread_id=work.thread.id,
        direction=Direction.INBOUND,
        kind=kind,
        person_id=work.person.id,
        at=work.message.at,
        provider_message_id=work.message.provider_message_id[:80],
        artifact_id=None if artifact is None else artifact.id,
        flag_id=flag_id,
    )


async def _say(session: AsyncSession, work: _Work, key: str, **params: str) -> None:
    """One reply in the thread, through the one door, in the poster's language."""
    work.replies.append(
        await send(
            session,
            context=work.context,
            to_person=work.person,
            kind=key,
            params=params,
            provider=work.providers.whatsapp,
            number=work.number,
            language=work.language,
        )
    )


async def _who_checks(session: AsyncSession, work: _Work) -> str:
    """Who looks at a kept document in the app: the poster, or — when the poster is the
    patient, who has no app — the chief who runs his care."""
    if work.thread.is_patient:
        keys = await audited_read(
            session, Key, work.context, Scope.FAMILY, channel=Channel.WHATSAPP
        )
        moment = utcnow()
        chiefs = [k for k in keys if k.is_active(moment) and k.role.value == "chief"]
        if chiefs:
            chief = await session.get(Person, chiefs[0].holder_person_id)
            if chief is not None and chief.display_name:
                return chief.display_name
    return YOU[work.language]


async def _doctor(session: AsyncSession, work: _Work) -> str:
    """The doctor's name every time, when the profile names one; his word for one otherwise."""
    try:
        providers = await audited_read(
            session, Provider, work.context, Scope.VISITS, channel=Channel.WHATSAPP
        )
    except OutOfScope:
        return YOUR_DOCTOR[work.language]
    for kind in (ProviderKind.DOCTOR, ProviderKind.CLINIC, ProviderKind.HOSPITAL):
        for provider in providers:
            if provider.kind is kind:
                return provider.name
    return YOUR_DOCTOR[work.language]


# --- the kinds ----------------------------------------------------------------------------------


async def _red_flag(session: AsyncSession, work: _Work) -> Handled:
    """The words matched the table: the flag before anything else, then the thread.

    The Flag rests on the SYMPTOM event the words were said in (the same row the feeling
    cloud raises one on), so the event is recorded first — a moment, with no content — and
    the flag right after it, before the words themselves are kept. Then the message, the
    reply in the thread, and the ladder for E11. The moment and the words are kept under the
    emergency scope, not the record's: a helper's key holds the one and not the other, and
    her word is enough to start this. A flag written with `suppressed_because` (shaky-and-
    sweaty with no sugar condition on the record) is kept for the caregiver to see and is not
    escalated in the thread.
    """
    feeling = await flag_to_raise(session, context=work.context, text=work.message.text)
    assert feeling is not None
    said = await record_the_moment(
        session,
        context=work.context,
        feeling=feeling,
        occurred_at=work.message.at,
        source_channel=SourceChannel.WHATSAPP,
        channel=Channel.WHATSAPP,
    )
    flag = await raise_flag(
        session,
        context=work.context,
        feeling=feeling,
        event_id=said.id,
        channel=Channel.WHATSAPP,
    )
    artifact = await _keep_text(session, work=work, scope=Scope.EMERGENCY)
    row = await _keep_row(
        session, work=work, kind=MessageKind.RED_FLAG, artifact=artifact, flag_id=flag.id
    )
    if flag.suppressed_because is not None:
        # Held back, not escalated — but the poster still hears who to call if it gets worse.
        await _say(session, work, "red_flag_held", doctor=await _doctor(session, work))
        return Handled(
            outcome="red_flag_suppressed",
            replies=tuple(work.replies),
            profile_id=work.profile.id,
            message_id=row.id,
            artifact_id=artifact.id,
            flag_id=flag.id,
        )
    # The ladder at once (E11-06): straight to the roster, whatever the hour, whatever the
    # caps. The reply names exactly who it reached — nobody is said to know who was not told.
    reached = await _escalate(
        session,
        settings=work.settings,
        providers=work.providers,
        number=work.number,
        context=work.context,
        flag=flag,
        told=(work.person.id,),
        at=work.message.at,
    )
    names: list[str] = []
    for person_id in reached:
        person = await session.get(Person, person_id)
        if person is not None and person.display_name and person.display_name not in names:
            names.append(person.display_name)
    # What to do now (E19-05): the flag's tier, the doctor's hours and the hospital marked as
    # on his insurance, at the moment the words were written — the ambulance at any hour for
    # chest pain and the signs of a stroke; out of the doctor's hours, never "call the doctor
    # today". Read under the emergency scope, so a helper's word names the same doctor. If
    # the directory cannot be read, the ambulance: nothing about it may weaken the step.
    try:
        step = await escalation_now(
            session,
            context=work.context,
            feeling=feeling,
            local=as_utc(work.message.at).astimezone(REGION_TZ[work.context.region]),
            emergency_number=EMERGENCY_NUMBER[work.context.region.value],
            channel=Channel.WHATSAPP,
            tiered=work.settings.red_flag_tiers,
        )
        step_name, doctor, hospital = step.step.value, step.doctor, step.hospital
    except Refusal as refusal:
        log.warning(
            "whatsapp: the directory refused %s; the ambulance step", type(refusal).__name__
        )
        step_name, doctor, hospital = "ambulance", None, None
    # "Call Dr Tan on Tuesday 15 September in the morning.": the morning he can call, by its
    # day and date (rule 5) — this one's before the clinic's hours begin, else tomorrow's.
    local = as_utc(work.message.at).astimezone(REGION_TZ[work.context.region])
    morning = local.date() + timedelta(days=0 if local.time() < NIGHT_UNTIL else 1)
    params = {
        "doctor": doctor or YOUR_DOCTOR[work.language],
        "day": say_date(morning, work.language),
        "name": work.profile.display_name,
        "hospital": hospital or "",
        "emergency_number": EMERGENCY_NUMBER[work.context.region.value],
        "names": join_names(names, work.language),
    }
    # The reply is its own savepoint: the flag and the ladder are written already, and a reply
    # that cannot go never takes them back. Failing that, the ambulance line, which names
    # nobody but who knows.
    # Written by someone who is not him (his chief, his helper): the words say who does the
    # next thing — "Help Pa sit down and rest now." — and whose insurance it is (rule 7).
    about = not work.thread.is_patient
    for key in (
        red_flag_reply_key(step_name, len(names), about=about),
        red_flag_reply_key("ambulance", len(names), about=about),
    ):
        try:
            async with nested_unit_of_work(session):
                await _say(session, work, key, **params)
            break
        except Exception as failed:  # noqa: BLE001 — the flag stands; the reply is logged
            log.warning("whatsapp: the red-flag reply %s not sent: %s", key, type(failed).__name__)
    # The ladder (`delivery_ladder`, its `delivery` rows) is the one record of who is told
    # and who is still to be asked; nothing else is written beside it.
    return Handled(
        outcome="red_flag",
        replies=tuple(work.replies),
        profile_id=work.profile.id,
        message_id=row.id,
        artifact_id=artifact.id,
        flag_id=flag.id,
    )


async def _whatsapp_agreed(session: AsyncSession, *, context: KeyContext) -> bool:
    """Whether the patient's WHATSAPP consent is in force. A refusal here is written down,
    as the gate's refusal always is; it only decides which way a red flag goes."""
    try:
        await require_consent(
            session,
            context=context,
            purpose=ConsentPurpose.WHATSAPP,
            scope=Scope.PROFILE,
            channel=Channel.WHATSAPP,
        )
    except NoConsent:
        return False
    return True


async def _escalate(
    session: AsyncSession,
    *,
    settings: Settings,
    providers: Providers,
    number: BusinessNumber,
    context: KeyContext,
    flag: Flag,
    told: Sequence[uuid.UUID],
    at: datetime,
) -> tuple[uuid.UUID, ...]:
    """The flag's ladder, started now; who it reached. A ladder that cannot start does not
    take the flag down with it: the flag leads the family's feed either way."""
    try:
        escalated = await escalate_flag(
            session,
            context,
            flag,
            told_already=told,
            via=Via(settings=settings, providers=providers, number=number),
            at=at,
        )
    except Refusal as refusal:
        log.warning("whatsapp: the ladder refused %s; the flag stands", type(refusal).__name__)
        return ()
    return escalated.told


async def _red_flag_unagreed(
    session: AsyncSession,
    *,
    settings: Settings,
    providers: Providers,
    number: BusinessNumber,
    person: Person,
    context: KeyContext,
    profile: Profile,
    message: InboundMessage,
) -> Handled:
    """A red-flag word on a profile whose patient has not agreed to WhatsApp.

    The flag is raised on the word's code alone — the SYMPTOM moment and the flag, the same
    rows the feeling cloud writes — and the message itself is not kept: no artefact, no
    thread, no message row. It is escalated through the family's app: the ladder's WhatsApp
    channel is closed without his agreement, so every rung goes to the app, and the flag
    card leads the family's feed. The poster gets one fixed line straight from the provider,
    written down as a share of a notice, the way the consent refusal's line is.
    """
    feeling = await flag_to_raise(session, context=context, text=message.text)
    assert feeling is not None
    try:
        async with unit_of_work(session):
            said = await record_the_moment(
                session,
                context=context,
                feeling=feeling,
                occurred_at=message.at,
                source_channel=SourceChannel.WHATSAPP,
                channel=Channel.WHATSAPP,
            )
            flag = await raise_flag(
                session,
                context=context,
                feeling=feeling,
                event_id=said.id,
                channel=Channel.WHATSAPP,
            )
            if flag.suppressed_because is None:
                await _escalate(
                    session,
                    settings=settings,
                    providers=providers,
                    number=number,
                    context=context,
                    flag=flag,
                    told=(person.id,),
                    at=message.at,
                )
    except Refusal as refusal:
        log.info(
            "whatsapp: red flag refused %s for %s",
            type(refusal).__name__,
            _handle(person.id, message.from_e164),
        )
        return Handled(outcome="refused", profile_id=profile.id, refused=type(refusal).__name__)
    text = reply(
        "red_flag_fixed", person.language, emergency_number=EMERGENCY_NUMBER[settings.region.value]
    )
    await providers.whatsapp.send_text(message.from_e164, text)
    await record(
        session,
        context=context,
        action=Action.SHARE,
        scope=Scope.EMERGENCY,
        target="red_flag_notice",
        channel=Channel.WHATSAPP,
        rows=1,
        shared_with_person_id=person.id,
        shared_with_label="red_flag_fixed",
    )
    return Handled(outcome="red_flag_unagreed", profile_id=profile.id, flag_id=flag.id)


async def _red_flag_everywhere(
    session: AsyncSession,
    *,
    settings: Settings,
    providers: Providers,
    number: BusinessNumber,
    person: Person,
    profiles: Sequence[uuid.UUID],
    message: InboundMessage,
) -> Handled | None:
    """A red-flag word from someone on more than one family's list who has not said which.

    It never waits on the answer: the flag is raised on every profile where the sender's key
    holds the emergency card, each marked `ambiguous_profile`, and each ladder starts at once
    with a notice that says it may be about theirs. The message itself is not kept — it may
    be about someone else — only the moment and the flag, as on a profile without WhatsApp.
    The sender is asked which one, in one fixed line, written down as a share on each. None
    when the sender holds the emergency card on none of them.
    """
    assert detect(message.text) is not None
    raised: list[tuple[Profile, KeyContext, Flag]] = []
    for profile_id in profiles:
        context = await resolve_key_context(
            session, region=settings.region, person_id=person.id, profile_id=profile_id
        )
        if not context.allows(Scope.EMERGENCY):
            continue
        # Each family's own record chooses the flag: a fall said with shaky-and-sweaty is the
        # fall where no sugar condition or sugar medicine is on it (B1 re-check).
        feeling = await flag_to_raise(session, context=context, text=message.text)
        assert feeling is not None
        profile = await audited_profile_read(session, context, channel=Channel.WHATSAPP)
        try:
            async with unit_of_work(session):
                said = await record_the_moment(
                    session,
                    context=context,
                    feeling=feeling,
                    occurred_at=message.at,
                    source_channel=SourceChannel.WHATSAPP,
                    channel=Channel.WHATSAPP,
                )
                flag = await raise_flag(
                    session,
                    context=context,
                    feeling=feeling,
                    event_id=said.id,
                    channel=Channel.WHATSAPP,
                    ambiguous_profile=True,
                )
                if flag.suppressed_because is None:
                    await _escalate(
                        session,
                        settings=settings,
                        providers=providers,
                        number=number,
                        context=context,
                        flag=flag,
                        told=(person.id,),
                        at=message.at,
                    )
        except Refusal as refusal:
            log.info(
                "whatsapp: red flag refused %s on one of several profiles for %s",
                type(refusal).__name__,
                _handle(person.id, message.from_e164),
            )
            continue
        raised.append((profile, context, flag))
    if not raised:
        return None
    names = [profile.display_name for profile, _, _ in raised]
    text = reply(
        "red_flag_which",
        person.language,
        both=join_names(names, person.language),
        either=join_names(names, person.language, either=True),
    )
    await providers.whatsapp.send_text(message.from_e164, text)
    for _, context, _ in raised:
        await record(
            session,
            context=context,
            action=Action.SHARE,
            scope=Scope.EMERGENCY,
            target="red_flag_notice",
            channel=Channel.WHATSAPP,
            rows=1,
            shared_with_person_id=person.id,
            shared_with_label="red_flag_which",
        )
    return Handled(outcome="red_flag_ambiguous", flag_id=raised[0][2].id)


async def _which_one(
    session: AsyncSession,
    *,
    settings: Settings,
    providers: Providers,
    person: Person,
    profiles: Sequence[uuid.UUID],
    message: InboundMessage,
) -> Handled | None:
    """The answer to "who is it about?": a message naming exactly one of the profiles whose
    ambiguous flag from this sender is still climbing. That ladder goes on; the others close
    ("not_this_one"), each closing on the trail of its own profile, in the sender's name.
    None when there is no such question open, or the message names none or several."""
    words = (message.text or "").lower()
    if not words:
        return None
    moment = utcnow()
    open_: list[tuple[Profile, KeyContext, list[Ladder]]] = []
    for profile_id in profiles:
        context = await resolve_key_context(
            session, region=settings.region, person_id=person.id, profile_id=profile_id
        )
        if not context.allows(Scope.EMERGENCY):
            continue
        flags = await audited_read(
            session,
            Flag,
            context,
            Scope.EMERGENCY,
            where=(
                Flag.raised_by_person_id == person.id,
                Flag.ambiguous_profile.is_(True),
                Flag.raised_at > moment - FLAG_WINDOW,
            ),
            channel=Channel.WHATSAPP,
        )
        if not flags:
            continue
        ladders = await audited_read(
            session,
            Ladder,
            context,
            Scope.EMERGENCY,
            where=(Ladder.flag_id.in_([flag.id for flag in flags]), Ladder.closed_at.is_(None)),
            channel=Channel.WHATSAPP,
        )
        profile = await session.get(Profile, profile_id)
        if ladders and profile is not None:
            open_.append((profile, context, list(ladders)))
    if len(open_) < 2:
        return None
    named = [
        one
        for one in open_
        if re.search(rf"(?<!\w){re.escape(one[0].display_name.lower())}(?!\w)", words)
    ]
    if len(named) != 1:
        return None
    chosen, chosen_context, _ = named[0]
    for profile, context, ladders in open_:
        if profile.id == chosen.id:
            continue
        for ladder in ladders:
            await close(session, context, ladder, "not_this_one", channel=Channel.WHATSAPP)
    text = reply("red_flag_which_thanks", person.language, name=chosen.display_name)
    await providers.whatsapp.send_text(message.from_e164, text)
    await record(
        session,
        context=chosen_context,
        action=Action.SHARE,
        scope=Scope.EMERGENCY,
        target="red_flag_notice",
        channel=Channel.WHATSAPP,
        rows=1,
        shared_with_person_id=person.id,
        shared_with_label="red_flag_which_thanks",
    )
    return Handled(outcome="which_one", profile_id=chosen.id)


DOSE_QUESTION_FOR = timedelta(hours=2)
"""How long "which tablet?" stays open for its answer (#162)."""
ALL_OF_THEM = re.compile(
    r"^\s*(?:(?:i\s+|he\s+|she\s+)?(?:took|gave|had|have taken|have given)\s+|"
    r"(?:sudah|dah)\s+(?:ambil|beri|bagi|makan)\s+)?"
    r"(?:both|all|both of them|all of them|semua|kedua-dua|kedua-duanya|"
    r"都|都吃了|都给了|两个都|两种都|全部)\s*[.!。！]?\s*$",
    re.IGNORECASE,
)
"""An answer to "which tablet?" that names every tablet it read out."""
NUMBERS_ONLY = re.compile(
    r"^\s*\d{1,2}(?:\s*(?:,|，|、|&|\+|\band\b|\bdan\b|和|\s)\s*\d{1,2})*\s*[.!。！]?\s*$",
    re.IGNORECASE,
)
"""An answer made of the question's numbers and nothing else: "1", "2", "1 and 2"."""
_POSSESSIVE = re.compile(r"^(?:your |the )|(?: anda)$|^您的")
_QUOTES = re.compile(r"[\"'“”‘’「」『』]")
NOT = re.compile(
    r"(?<!\w)(?:not|no|never|didn'?t|did not|haven'?t|have not|tidak|tak|belum|bukan)(?!\w)"
    r"|不|没",
    re.IGNORECASE,
)
"""A "no" in an answer naming a tablet: it does not say which he took (#162)."""


def _question_closes(moment: datetime, region: Region) -> datetime:
    """When "which tablet?" stops taking an answer: two hours on, or at the end of his day if
    that comes first — a tablet is his day's, and tomorrow's is another (#162)."""
    zone = REGION_TZ[region]
    local = as_utc(moment).astimezone(zone)
    midnight = datetime.combine(local.date() + timedelta(days=1), time(0), zone)
    return min(as_utc(moment) + DOSE_QUESTION_FOR, midnight.astimezone(UTC))


def _medicine(work: _Work, dose: DoseAsked) -> str:
    """His words for the tablet, said to whoever wrote: his own to him, "Pa's" to anyone else."""
    words = medicine_words(work.providers.drug_registry, dose.generic, work.language)
    if work.thread.is_patient:
        return words
    return theirs(words, work.profile.display_name, work.language)


def _box_number(strength: str) -> str | None:
    """The strength as the number on his box: "5 mg" is 5, "5/80 mg" is 5/80. None when
    there is no number."""
    found = re.match(r"\s*(\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)*)", strength or "")
    return None if found is None else re.sub(r"\s+", "", found.group(1))


def _named(work: _Work, dose: DoseAsked, listed: Sequence[DoseAsked]) -> str:
    """The tablet as a reply names it: his words, and the number on its box too when another
    tablet on the list goes by the same words, so the read-back says which one it was."""
    words = _medicine(work, dose)
    strength = _box_number(dose.strength)
    clashes = any(other != dose and _medicine(work, other) == words for other in listed)
    if not clashes or strength is None:
        return words
    return BOXED[work.language].format(medicine=words, strength=strength)


def _dose_lines(work: _Work, doses: Sequence[DoseAsked]) -> str:
    """The question's list, one line a tablet, numbered from 1 in the order it is read out."""
    lines: list[str] = []
    for number, dose in enumerate(doses, start=1):
        strength = _box_number(dose.strength)
        words = DOSE_CHOICE if strength is not None else DOSE_CHOICE_BARE
        lines.append(
            words[work.language].format(
                number=str(number),
                medicine=_medicine(work, dose),
                strength=strength or "",
                anchor=ANCHOR_WORDS[work.language][dose.anchor],
            )
        )
    return "\n".join(lines)


def _which_key(work: _Work, doses: Sequence[DoseAsked]) -> str:
    asked = "taken_which" if work.thread.is_patient else "given_which"
    return asked if len(doses) == 2 else f"{asked}_all"


async def _ask_which(session: AsyncSession, work: _Work, doses: Sequence[DoseAsked]) -> Handled:
    """ "Which tablet?" — a "Taken" or "given" that could be about more than one tablet at that
    moment (#162). Nothing is written down: the question is kept, with the tablets in the
    order they were read out, under the medicines scope the reply's key holds, and each is
    read out by number, in his words, with its strength and its moment."""
    moment = utcnow()
    # A new question closes any still open in this thread: only the newest is answered.
    earlier = await _open_question(session, work)
    if earlier is not None:
        await _close_question(session, work, earlier)
    await audited_write(
        session,
        DoseQuestion,
        work.context,
        Scope.MEDICINES,
        channel=Channel.WHATSAPP,
        thread_id=work.thread.id,
        asked_at=moment,
        expires_at=_question_closes(moment, work.context.region),
        doses=[{"line_id": str(dose.line_id), "anchor": dose.anchor} for dose in doses],
    )
    await _say(
        session,
        work,
        _which_key(work, doses),
        doses=_dose_lines(work, doses),
        name=work.profile.display_name,
    )
    return Handled(outcome="which_tablet", replies=tuple(work.replies), profile_id=work.profile.id)


async def _write_taken(
    session: AsyncSession,
    work: _Work,
    doses: Sequence[DoseAsked],
    *,
    listed: Sequence[DoseAsked] = (),
    already: frozenset[tuple[uuid.UUID, str]] = frozenset(),
) -> Handled:
    """The Taken taps for exactly these tablets, the way the app's button writes each — the
    tap is the yes, under the medicines scope the helper's key holds — on the WhatsApp
    channel; the ladder stops for these and for no other (#162). One tapped since the
    question was asked (`already`) is not tapped twice. The reply names them, each told apart
    from the others on the list (`listed`) where their words are the same."""
    listed = listed or doses
    artifact = await _keep_text(session, work=work, scope=Scope.MEDICINES)
    row = await _keep_row(session, work=work, kind=MessageKind.TAKEN, artifact=artifact)
    day = as_utc(work.message.at).astimezone(REGION_TZ[work.context.region]).date().isoformat()
    for dose in doses:
        if (dose.line_id, dose.anchor) in already:
            continue
        await record_dose_taken(
            session,
            context=work.context,
            line_id=dose.line_id,
            anchor=dose.anchor,
            source_channel=SourceChannel.WHATSAPP,
            channel=Channel.WHATSAPP,
        )
        await acknowledge_dose(
            session,
            context=work.context,
            line_id=dose.line_id,
            anchor=dose.anchor,
            day=day,
            channel=Channel.WHATSAPP,
        )
    if work.thread.is_patient:
        took: list[str] = []
        for anchor in dict.fromkeys(dose.anchor for dose in doses):
            named = [_named(work, dose, listed) for dose in doses if dose.anchor == anchor]
            took.append(
                TOOK[work.language].format(
                    medicine=join_names(named, work.language),
                    anchor=ANCHOR_WORDS[work.language][anchor],
                )
            )
        who = await _who_checks(session, work)
        if who != YOU[work.language]:
            # "took it" names one tablet; more than one is "took them" (#173).
            key = "taken_patient" if len(doses) == 1 else "taken_patient_many"
            await _say(session, work, key, who=who, took="\n".join(took))
        else:
            await _say(session, work, "taken_alone", took="\n".join(took))
    else:
        medicine = join_names([_named(work, dose, listed) for dose in doses], work.language)
        await _say(session, work, "given", name=work.profile.display_name, medicine=medicine)
    return Handled(
        outcome="taken",
        replies=tuple(work.replies),
        profile_id=work.profile.id,
        message_id=row.id,
        artifact_id=artifact.id,
    )


async def _taken(session: AsyncSession, work: _Work) -> Handled:
    """ "Taken" from him, "given" from the helper: the Taken tap, said as a reply (E11-01).

    It is about every tablet the ladder has asked this person about today and is still open,
    and every one whose window is open now with no Taken yet (`doses_for_reply`). One is
    written down at once, and named in the reply. More than one is never a guess (#162): he
    is asked which, by number, and nothing is written until he answers. None: nothing is
    written and the reply says so.
    """
    doses = await doses_for_reply(
        session, context=work.context, registry=work.providers.drug_registry, at=work.message.at
    )
    if not doses:
        await _say(session, work, "taken_nothing_due")
        return Handled(
            outcome="nothing_due", replies=tuple(work.replies), profile_id=work.profile.id
        )
    if len(doses) > 1:
        return await _ask_which(session, work, doses)
    return await _write_taken(session, work, doses)


async def _open_question(session: AsyncSession, work: _Work) -> DoseQuestion | None:
    """The newest "which tablet?" still open in this thread, if its key reads the medicines."""
    if not work.context.allows(Scope.MEDICINES):
        return None
    found = await audited_read(
        session,
        DoseQuestion,
        work.context,
        Scope.MEDICINES,
        where=(
            DoseQuestion.thread_id == work.thread.id,
            DoseQuestion.answered_at.is_(None),
            DoseQuestion.expires_at > utcnow(),
        ),
        order_by=(DoseQuestion.asked_at.desc(),),
        limit=1,
        channel=Channel.WHATSAPP,
    )
    return found[0] if found else None


def _words_for(registry: DrugRegistry, dose: DoseAsked) -> set[str]:
    """What names one tablet in an answer: its generic name, and his words for it in every
    language, without "your" or "the"."""
    words = {dose.generic.lower()}
    plain = registry.monograph(dose.generic).plain_name_id
    for language in PLAIN_NAME.values():
        said = language.get(plain)
        if said:
            words.add(_POSSESSIVE.sub("", said.lower()).strip())
    return {word for word in words if word}


def _chosen(
    text: str, doses: Sequence[DoseAsked], registry: DrugRegistry
) -> list[DoseAsked] | None:
    """Exactly which tablets an answer to "which tablet?" says, or None when it does not say
    exactly (#162): a number from the list, several numbers, "both" or "all", or the
    tablet's own word. A number that is not on the list, or a word that names more than one
    tablet on it, says nothing, and nothing is written."""
    said = _QUOTES.sub("", text).strip().lower()
    if ALL_OF_THEM.match(said):
        return list(doses)
    if NUMBERS_ONLY.match(said):
        numbers = sorted({int(number) for number in re.findall(r"\d+", said)})
        if numbers and all(1 <= number <= len(doses) for number in numbers):
            return [doses[number - 1] for number in numbers]
        return None
    named: dict[str, set[int]] = {}
    for index, dose in enumerate(doses):
        for word in _words_for(registry, dose):
            named.setdefault(word, set()).add(index)
    found: set[int] = set()
    for word, which in named.items():
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", said) or (
            not word.isascii() and word in said
        ):
            if len(which) > 1:
                return None
            found |= which
    # A name answers only when it names exactly one tablet, with no "not" beside it: "the
    # aspirin, not the water pill" and "the aspirin and the water pill" say nothing sure.
    if len(found) != 1 or NOT.search(said):
        return None
    return [doses[index] for index in sorted(found)]


async def _answer_which(
    session: AsyncSession, work: _Work, question: DoseQuestion, what: Classification
) -> Handled | None:
    """An answer to the open "which tablet?" (#162). Exactly which: the question is answered
    and the Taken written for those tablets alone. Not exactly which: nothing is written, he
    is told so and asked again. None when the message is not an answer at all."""
    slots = await doses_today(session, context=work.context, registry=work.providers.drug_registry)
    lines = {slot.line.id: slot.line for slot in slots}
    doses = [
        DoseAsked(
            line_id=line.id, anchor=asked["anchor"], generic=line.generic, strength=line.strength
        )
        for asked in question.doses
        if (line := lines.get(uuid.UUID(asked["line_id"]))) is not None
    ]
    if len(doses) != len(question.doses):
        # A tablet it read out has left today's list since: its numbers no longer mean what
        # was read to him. Nothing is written; he is asked again from what is open now.
        await _close_question(session, work, question)
        await _say(session, work, "which_not_sure")
        fresh = await doses_for_reply(
            session,
            context=work.context,
            registry=work.providers.drug_registry,
            at=work.message.at,
        )
        if fresh:
            return await _ask_which(session, work, fresh)
        return Handled(
            outcome="which_tablet", replies=tuple(work.replies), profile_id=work.profile.id
        )
    chosen = _chosen(work.message.text or "", doses, work.providers.drug_registry)
    if chosen is None:
        if what.kind is not Kind.OTHER and not (
            what.kind is Kind.HEALTH_EVENT
            and what.event is not None
            and what.event.subject == "medication"
        ):
            return None
        await _say(session, work, "which_not_sure")
        if doses:
            await _say(
                session,
                work,
                _which_key(work, doses),
                doses=_dose_lines(work, doses),
                name=work.profile.display_name,
            )
        return Handled(
            outcome="which_tablet", replies=tuple(work.replies), profile_id=work.profile.id
        )
    await _close_question(session, work, question)
    tapped = frozenset((slot.line.id, slot.anchor) for slot in slots if slot.taken)
    return await _write_taken(session, work, chosen, listed=doses, already=tapped)


async def _close_question(session: AsyncSession, work: _Work, question: DoseQuestion) -> None:
    """The question's one change: answered, or asked again — it takes no answer after this."""
    question.answered_at = utcnow()
    await session.flush()
    await record(
        session,
        context=work.context,
        action=Action.WRITE,
        scope=Scope.MEDICINES,
        target=DoseQuestion.__tablename__,
        target_id=question.id,
        rows=1,
        channel=Channel.WHATSAPP,
    )


async def _document(session: AsyncSession, work: _Work) -> Handled:
    assert work.message.media_id is not None
    media = await work.providers.whatsapp.fetch_media(work.message.media_id)
    content_type = (work.message.content_type or media.content_type).strip().lower()
    card_id: uuid.UUID | None = None
    if content_type in IMAGE_CONTENT_TYPES:
        artifact = await store_photo(
            session,
            context=work.context,
            store=work.providers.object_store,
            data=media.data,
            content_type=content_type,
            captured_at=work.message.at,
            source_channel=SourceChannel.WHATSAPP,
        )
        card = await review_photo(
            session,
            context=work.context,
            artifact_id=artifact.id,
            store=work.providers.object_store,
            extractor=work.providers.extractor,
            language=work.profile.language,
        )
        card_id = card.id
        said = "kept_photo"
    elif content_type == PDF_CONTENT_TYPE:
        store = work.providers.object_store
        guard_region(held_in=store.region, asked_from=work.context.region)
        digest = sha256_of(media.data)
        key = check_key(f"documents/{work.context.profile_id}/{digest}")
        await store.put(key, media.data)
        artifact = await store_artifact(
            session,
            context=work.context,
            kind=ArtifactKind.PDF,
            storage_key=key,
            content_type=content_type,
            sha256=digest,
            captured_at=work.message.at,
            source_channel=SourceChannel.WHATSAPP,
            region=store.region,
        )
        said = "kept_letter"
    else:
        raise NotADocument(f"{content_type} is neither a photo nor a PDF")
    row = await _keep_row(session, work=work, kind=MessageKind.DOCUMENT, artifact=artifact)
    await _say(session, work, said, name=await _who_checks(session, work))
    return Handled(
        outcome="document",
        replies=tuple(work.replies),
        profile_id=work.profile.id,
        message_id=row.id,
        artifact_id=artifact.id,
        review_card_id=card_id,
    )


async def _check_in_answer(
    session: AsyncSession,
    work: _Work,
    event: HealthEvent,
    *,
    kept: tuple[Artifact, WhatsAppMessage] | None = None,
) -> Handled:
    """The patient's own feeling word, in his own thread: the reply is the yes.

    No proposal: there is nothing to read back. Mei's "he's tired" is a third party's
    account of him, read out of free text, so she is asked whether Nura heard it right; his
    "tired" is one of the three words Nura offered him, about himself, with nothing
    extracted from it. So — like the Taken tap — the word is written down as his own, the
    confirmation minted and spent in the same unit of work, the way the app's save button
    does for a number he typed.
    """
    assert event.word is not None
    if kept is not None:
        # Already kept, as the answer it was first read as (`_answer`): the same message.
        artifact, row = kept
    else:
        artifact = await _keep_text(session, work=work)
        row = await _keep_row(
            session, work=work, kind=MessageKind.CHECK_IN_ANSWER, artifact=artifact
        )
    told = await record_event(
        session,
        context=work.context,
        kind=EventKind.SYMPTOM,
        occurred_at=work.message.at,
        artifact_id=artifact.id,
    )
    draft = FactDraft(
        subject="feeling",
        attribute="reported",
        value=event.word,
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=artifact.id,
        event_id=told.id,
        episode_id=None,
        supersedes_id=None,
    )
    minted = await confirm(session, work.context, draft, channel=Channel.WHATSAPP)
    fact = await assert_fact(
        session,
        context=work.context,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=minted.id,
        artifact_id=artifact.id,
        event_id=told.id,
        valid_from=work.message.at,
    )
    await _say(session, work, "written_down")
    return Handled(
        outcome="check_in_answer",
        replies=tuple(work.replies),
        profile_id=work.profile.id,
        message_id=row.id,
        artifact_id=artifact.id,
        fact_id=fact.id,
    )


async def _health_event(session: AsyncSession, work: _Work, event: HealthEvent) -> Handled:
    if work.thread.is_patient and event.word in FEELING_VOCABULARY:
        return await _check_in_answer(session, work, event)
    # The fact's own scope, first: a key that could not write the reading cannot propose it,
    # and the refusal is the one the app gives — OutOfScope readings — before a byte is kept.
    scope = scope_for_subject(event.subject)
    async with audited_guard(
        session, work.context, Action.WRITE, scope, PROPOSAL, channel=Channel.WHATSAPP
    ):
        work.context.require(scope)
    artifact = await _keep_text(session, work=work)
    row = await _keep_row(session, work=work, kind=MessageKind.HEALTH_EVENT, artifact=artifact)
    proposal = await propose(
        session, context=work.context, thread=work.thread, message=row, event=event
    )
    words = dict(event.words)
    if event.word is not None:
        words["word"] = FEELING_WORDS[work.language][event.word]
    await _say(session, work, f"propose_{event.said}", name=work.profile.display_name, **words)
    return Handled(
        outcome="proposal",
        replies=tuple(work.replies),
        profile_id=work.profile.id,
        message_id=row.id,
        artifact_id=artifact.id,
        proposal_id=proposal.id,
    )


async def _answer(session: AsyncSession, work: _Work, yes: bool) -> Handled:
    artifact = await _keep_text(session, work=work)
    row = await _keep_row(session, work=work, kind=MessageKind.ANSWER, artifact=artifact)
    try:
        proposal, fact = await answer(session, context=work.context, yes=yes)
    except NoOpenProposal:
        if yes and work.context.allows(Scope.EMERGENCY):
            answered = await acknowledge_flag(
                session, context=work.context, channel=Channel.WHATSAPP
            )
            if answered is not None:
                await _say(session, work, "flag_seen")
                return Handled(
                    outcome="flag_acknowledged",
                    replies=tuple(work.replies),
                    profile_id=work.profile.id,
                    message_id=row.id,
                    artifact_id=artifact.id,
                )
        if (
            work.thread.is_patient
            and CHECK_IN_OK.match(work.message.text or "")
            and await _check_in_open(session, work)
        ):
            # "OK" is one of the three words the check-in offers him ("Answer OK, tired or
            # pain."). With nothing of his open to say yes to, and no flag to acknowledge,
            # it is his answer to that question, written down as his own word (E19-03).
            return await _check_in_answer(session, work, OK_FEELING, kept=(artifact, row))
        await _say(session, work, "nothing_open")
        return Handled(
            outcome="nothing_open",
            replies=tuple(work.replies),
            profile_id=work.profile.id,
            message_id=row.id,
            artifact_id=artifact.id,
        )
    except ProposalExpired:
        await _say(session, work, "too_old")
        return Handled(
            outcome="too_old",
            replies=tuple(work.replies),
            profile_id=work.profile.id,
            message_id=row.id,
            artifact_id=artifact.id,
        )
    await _say(session, work, "written_down" if yes else "not_written")
    return Handled(
        outcome="confirmed" if yes else "declined",
        replies=tuple(work.replies),
        profile_id=work.profile.id,
        message_id=row.id,
        artifact_id=artifact.id,
        proposal_id=proposal.id,
        fact_id=None if fact is None else fact.id,
    )


async def _coordination(session: AsyncSession, work: _Work) -> Handled:
    """Kept for the family, under the family scope: a MESSAGE artefact and a MESSAGE event,
    and nothing extracted from either."""
    artifact = await _keep_text(session, work=work, scope=Scope.FAMILY)
    await audited_write(
        session,
        Event,
        work.context,
        Scope.FAMILY,
        channel=Channel.WHATSAPP,
        kind=EventKind.MESSAGE,
        occurred_at=work.message.at,
        source_channel=SourceChannel.WHATSAPP,
        label="family message",
        artifact_id=artifact.id,
        recorded_at=utcnow(),
    )
    row = await _keep_row(session, work=work, kind=MessageKind.COORDINATION, artifact=artifact)
    await _say(session, work, "kept_for_family")
    return Handled(
        outcome="coordination",
        replies=tuple(work.replies),
        profile_id=work.profile.id,
        message_id=row.id,
        artifact_id=artifact.id,
    )


async def _other(session: AsyncSession, work: _Work) -> Handled:
    """Not stored, not indexed. In a private thread, one line saying so; in a group, silence."""
    if work.message.group_id is None:
        await _say(session, work, "not_understood")
    return Handled(outcome="other", replies=tuple(work.replies), profile_id=work.profile.id)


# --- voice notes and the family's group (E11-01) -------------------------------------------------


VOICE_DOWNLOAD_BYTES = MAX_VOICE_BYTES
"""The most of a voice note fetched from the provider: a note on an event's own cap, a minute
or two of speech (`app.ingestion.notes`). Past it, nothing is fetched on, heard or kept."""


def _is_voice(message: InboundMessage) -> bool:
    return message.media_id is not None and (message.content_type or "").strip().lower().startswith(
        "audio/"
    )


async def _hear(
    providers: Providers, region: Region, person: Person, message: InboundMessage
) -> tuple[Media | None, Transcript]:
    """A voice note's audio, fetched from the provider within its time limit and heard by the
    region's transcriber — pinned to this deployment's region, so a voice is never heard
    across the causeway. Nothing is kept here: its words are read for a red flag first, like
    any message's, and only then kept as his own note, or not at all."""
    assert message.media_id is not None
    try:
        media = await providers.whatsapp.fetch_media(
            message.media_id, max_bytes=VOICE_DOWNLOAD_BYTES
        )
    except (NoSuchMedia, MediaTooLarge) as unheard:
        log.info("whatsapp: a voice note not fetched: %s", type(unheard).__name__)
        return None, NOTHING_HEARD
    kind = media.content_type.split(";", 1)[0].strip().lower()
    guard_region(held_in=providers.transcriber.region, asked_from=region)
    try:
        heard = await providers.transcriber.transcribe(
            media.data, kind, language_of(person.language), region
        )
    except Exception as failed:  # noqa: BLE001 — a transcriber down is a note not heard, never a lost message
        log.warning("whatsapp: a voice note not heard: %s", type(failed).__name__)
        return media, NOTHING_HEARD
    return media, heard


async def _keep_voice(session: AsyncSession, work: _Work) -> NoteView:
    assert work.voice is not None
    return await keep_voice_message(
        session,
        context=work.context,
        store=work.providers.object_store,
        data=work.voice.data,
        content_type=work.voice.content_type,
        captured_at=work.message.at,
        heard=work.heard,
        source_channel=SourceChannel.WHATSAPP,
        # He was not asked on WhatsApp who may hear it: his and his notes' chief's only.
        private=True,
    )


async def _voice_note(session: AsyncSession, work: _Work) -> Handled:
    """His own voice note on WhatsApp (E11-01): kept as his own note — `Recording.OWN_NOTE`,
    his own words, so on the agreement to hold the record and never the recording consent
    (ADR 0003) — with the words heard in it by reference, private to him and a chief preset
    to his notes, and findable by recall. Anyone else's voice note is not kept: it may carry
    other people's voices, which only a consult keeps, on the consent to record. One of
    theirs that Nura could not hear still reaches a person, all the same (#173)."""
    if not work.context.is_owner:
        if _nothing_heard(work):
            return await _note_unheard_from_someone_else(session, work)
        return await _other(session, work)
    view = await _keep_voice(session, work)
    row = await _keep_row(session, work=work, kind=MessageKind.VOICE_NOTE, artifact=view.artifact)
    if view.transcript is not None:
        await _say(session, work, "voice_note_kept")
    else:
        # Nothing heard in it — a mumble, or the transcriber down: a red word in it could not
        # be read (#158). His chief is told to listen, and he is told what to do if he feels
        # unwell — and who knows now, once the notice has actually gone (#173).
        reached = await _tell_family_unheard(session, work, note_id=view.note.id)
        await _say_unheard(session, work, "voice_note_unheard", reached)
    return Handled(
        outcome="voice_note",
        replies=tuple(work.replies),
        profile_id=work.profile.id,
        message_id=row.id,
        artifact_id=view.artifact.id,
        note_id=view.note.id,
    )


def _nothing_heard(work: _Work) -> bool:
    """Whether this voice note reached Nura with no words in it: the audio never arrived, ran
    past its cap, or the transcriber heard nothing in what did arrive."""
    return work.voice_missing or work.heard is None or not work.heard.heard


async def _say_unheard(
    session: AsyncSession, work: _Work, key: str, reached: Sequence[uuid.UUID]
) -> None:
    """The reply to a note Nura could not hear, with who the notice reached — and nobody named
    who was not told (#173): the plain line where it reached nobody, "Mei knows now." where it
    reached one, "Mei and Kit know now." where it reached more.

    The notice goes first, so this can say who knows; and this runs in a savepoint of its own,
    so a reply that fails is logged by name and never rolls the note or the notice back —
    which would have the family told again on the provider's retry, and him told twice that
    Nura could not hear him. It is the same rule the red flag's reply follows.
    """
    names: list[str] = []
    for person_id in reached:
        person = await session.get(Person, person_id)
        if person is not None and person.display_name and person.display_name not in names:
            names.append(person.display_name)
    told = key if not names else f"{key}_told" if len(names) == 1 else f"{key}_told_many"
    params = {} if not names else {"names": join_names(names, work.language)}
    try:
        async with nested_unit_of_work(session):
            await _say(session, work, told, **params)
    except Exception as failed:  # noqa: BLE001 — the notice stands; the reply is logged by name
        log.warning(
            "whatsapp: the reply to an unheard voice note not sent: %s", type(failed).__name__
        )


async def _voice_not_heard(session: AsyncSession, work: _Work) -> Handled:
    """A voice note that could not be fetched, or ran past its cap: nothing of it is kept, the
    refusal is on the trail by name, and the sender is told plainly. His reply carries what to
    do if he feels unwell, since a red word in it could not be read; anyone else's asks them to
    write what they said instead. Either way a person is told, so someone can call him."""
    if not work.context.is_owner:
        return await _note_unheard_from_someone_else(session, work)
    await _refused_the_note(session, work.context)
    reached = await _tell_family_unheard(session, work, note_id=None)
    await _say_unheard(session, work, "voice_note_not_fetched", reached)
    return Handled(
        outcome="voice_note_not_heard", replies=tuple(work.replies), profile_id=work.profile.id
    )


async def _note_unheard_from_someone_else(session: AsyncSession, work: _Work) -> Handled:
    """A voice note from the helper, or any other key holder, that Nura could not hear (#173).

    Hers is not kept — it may carry other people's voices, which only a consult keeps, on the
    consent to record — and the refusal is on the trail by name. But a red word she spoke could
    not be read either, so it is treated exactly as one of his: the chief is told on her own
    channels, as an alert. The notice names whoever sent it and never says the patient did,
    and what it asks is to call them: there is nothing of theirs to listen to, and they are
    the one who knows what they said. The sender is told plainly and asked to write it; the
    line telling him to call his family is his, and is said to nobody else.
    """
    await _refused_the_note(session, work.context)
    reached = await _tell_family_unheard(session, work, note_id=None)
    await _say_unheard(session, work, "note_unheard_other", reached)
    return Handled(
        outcome="voice_note_not_heard", replies=tuple(work.replies), profile_id=work.profile.id
    )


async def _refused_the_note(session: AsyncSession, context: KeyContext) -> None:
    """A voice note nothing was kept of, on the trail by name and never by its words."""
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.RECORDS,
        target="event_note",
        outcome=Outcome.REFUSED,
        refused_because="VoiceNoteNotHeard",
        channel=Channel.WHATSAPP,
    )


UNHEARD = TriggerType.VOICE_NOTE_UNHEARD


async def _tell_family_unheard(
    session: AsyncSession, work: _Work, *, note_id: uuid.UUID | None
) -> tuple[uuid.UUID, ...]:
    """The same, for a message the thread is handling: `_tell_unheard` for its work."""
    return await _tell_unheard(
        session,
        settings=work.settings,
        providers=work.providers,
        number=work.number,
        profile_id=work.profile.id,
        at=work.message.at,
        provider_message_id=work.message.provider_message_id,
        from_person_id=work.person.id,
        note_id=note_id,
    )


async def _tell_unheard(
    session: AsyncSession,
    *,
    settings: Settings,
    providers: Providers,
    number: BusinessNumber,
    profile_id: uuid.UUID,
    at: datetime,
    provider_message_id: str,
    from_person_id: uuid.UUID,
    note_id: uuid.UUID | None,
) -> tuple[uuid.UUID, ...]:
    """A voice note Nura could not hear, told to a person (#158, #173), so a person listens.

    A red word in it could not be read, so it goes the way a red flag's notice goes: an alert
    under the emergency card (`RULES[VOICE_NOTE_UNHEARD]`), never capped and never held by
    the quiet hours, on the rule's own channels whatever a setting says — WhatsApp, then the
    app's content-free push — and every attempt a `Delivery` row. Whose note it was does not
    change any of that: the helper's unheard note tells a person exactly as his does.

    It climbs a ladder of its own (`unheard_ladder`), so a chief who does not say she has it
    is followed by whoever is on duty and then by everyone else whose key holds the emergency
    card; one person's "I'm on it" stops it for the rest (`acknowledge_flag`). Whoever sent it
    is left off the ladder — they know already. With nobody on any rung, there is nobody to
    tell and the reply says nothing about who knows.

    It carries no word of the note and none of its audio: the note stays private to him and a
    chief preset to his notes. Her key opens them: she is told to listen in the app, or to
    call him; it does not, or there is no note at all: she is told to call him. Somebody
    else's note is never said to be his: the notice names whoever sent it.

    It runs in a savepoint of its own, so a door's no here leaves his note standing. Anything
    else — a lock, the database gone — is a failure and goes on up: the message is not
    handled, the webhook answers 5xx and the provider sends it again, so a note nobody could
    hear never ends in a 200 with nobody told. Nothing has been said to the sender at this
    point — his reply is the last thing, and says who this reached — so a retry never tells
    him twice that Nura could not hear him (#173).

    Whose phone it reached.
    """
    handle = hashlib.sha256(provider_message_id.encode()).hexdigest()[:16]
    try:
        async with nested_unit_of_work(session):
            run = await open_run(
                session,
                via=Via(settings=settings, providers=providers, number=number),
                profile_id=profile_id,
                at=at,
            )
            ladder = await unheard_ladder(
                run,
                dedupe_key=f"{UNHEARD.value}:{note_id or handle}",
                note_id=note_id,
                from_person_id=from_person_id,
            )
            await climb_unheard(run, ladder)
    except Refusal as refusal:
        # A door said no: a decision, not a failure, and on the trail already. His note and
        # his reply stand, and nothing is sent again.
        log.warning("whatsapp: an unheard voice note not told: %s", type(refusal).__name__)
        return ()
    return tuple(
        dict.fromkeys(
            sent.delivery.to_person_id
            for sent in run.report
            if sent.delivery.outcome is DeliveryOutcome.SENT
            and sent.delivery.via in PHONE
            and sent.delivery.to_person_id is not None
        )
    )


async def _unheard_unagreed(
    session: AsyncSession,
    *,
    settings: Settings,
    providers: Providers,
    number: BusinessNumber,
    person: Person,
    context: KeyContext,
    profile: Profile,
    message: InboundMessage,
) -> Handled:
    """A voice note Nura could not hear on a profile whose patient has not agreed to WhatsApp.

    Nothing of it is kept — no artefact, no thread, no message row — the way a red-flag word
    on such a profile is raised on the word alone. A person is still told all the same: the
    notice is an alert, so it goes every way each person can be reached (#163) and the notice
    on their family page is written whatever else carried it. The sender gets one fixed line
    straight from the provider, written down as a share of a notice, content-free.
    """
    await _refused_the_note(session, context)
    await _tell_unheard(
        session,
        settings=settings,
        providers=providers,
        number=number,
        profile_id=profile.id,
        at=message.at,
        provider_message_id=message.provider_message_id,
        from_person_id=person.id,
        note_id=None,
    )
    text = reply(
        "note_unheard_fixed",
        person.language,
        emergency_number=EMERGENCY_NUMBER[settings.region.value],
    )
    await providers.whatsapp.send_text(message.from_e164, text)
    await record(
        session,
        context=context,
        action=Action.SHARE,
        scope=Scope.EMERGENCY,
        target="unheard_note_notice",
        channel=Channel.WHATSAPP,
        rows=1,
        shared_with_person_id=person.id,
        shared_with_label="note_unheard_fixed",
    )
    return Handled(outcome="voice_note_unheard_unagreed", profile_id=profile.id)


async def _check_in_open(session: AsyncSession, work: _Work) -> bool:
    """Whether a feeling check-in went to him in this thread today and no feeling of his has
    been written down since: then his "OK" is its answer, and at no other time."""
    zone = REGION_TZ[work.context.region]
    local_day = as_utc(work.message.at).astimezone(zone).date()
    start = datetime.combine(local_day, time(0), zone).astimezone(UTC)
    asked = await audited_read(
        session,
        WhatsAppMessage,
        work.context,
        Scope.PROFILE,
        where=(
            WhatsAppMessage.thread_id == work.thread.id,
            WhatsAppMessage.direction == Direction.OUTBOUND,
            WhatsAppMessage.template_name == "feeling_check_in",
            WhatsAppMessage.at >= start,
        ),
        channel=Channel.WHATSAPP,
    )
    if not asked:
        return False
    asked_at = max(as_utc(one.at) for one in asked)
    told = await current_facts(
        session, context=work.context, subject="feeling", attribute="reported"
    )
    return not any(as_utc(fact.asserted_at) >= asked_at for fact in told)


async def _group_message(session: AsyncSession, work: _Work) -> Handled:
    """A message in the family's group (E11-01): it lands in the family thread (E12-02) in its
    poster's name, for a member — someone who reads the thread (`is_member`). Anyone else in
    the group is not a member: nothing is kept and nothing is said. Nobody is answered in the
    group, and nothing is read out of what the family says to each other."""
    if not is_member(work.context):
        log.info("whatsapp: a group message from someone who does not read the family thread")
        return Handled(outcome="ignored", profile_id=work.profile.id)
    # Who is in the group is set from the keys again at every post (E11-01).
    await sync_group(session, context=work.context, provider=work.providers.whatsapp)
    entry = await post_message(session, context=work.context, text=work.message.text or "")
    row = await _keep_row(session, work=work, kind=MessageKind.COORDINATION, artifact=None)
    return Handled(
        outcome="family_thread",
        profile_id=work.profile.id,
        message_id=row.id,
        thread_message_id=entry.id,
    )


# --- the walk ------------------------------------------------------------------------------------


async def _dispatch(session: AsyncSession, work: _Work, what: Classification) -> Handled:
    if detect(work.message.text) is not None:
        flagged = await _red_flag(session, work)
        if work.voice is not None and work.context.is_owner:
            # The flag first; then his voice note is his own note, in a savepoint of its own:
            # a refusal keeping the note never takes the flag or its ladder with it.
            try:
                async with nested_unit_of_work(session):
                    kept = await _keep_voice(session, work)
            except Refusal as refused:
                log.info("whatsapp: a flagged voice note not kept: %s", type(refused).__name__)
                return flagged
            return replace(flagged, note_id=kept.note.id)
        return flagged
    if work.message.group_id is not None and (work.voice is not None or work.voice_missing):
        # A voice note in the family's group is the family's, the way a photo there is: not
        # kept, and never an alert. The group is where they talk to each other, and a note
        # Nura could not hear in it would page everyone (#173). A red word in one was read
        # above, before this, and is a flag like any other.
        return Handled(outcome="ignored", profile_id=work.profile.id)
    if work.voice_missing:
        return await _voice_not_heard(session, work)
    if work.voice is not None:
        # Heard, and classified from its transcript exactly as a typed message would be
        # (E11-01): "Taken" or "sudah makan ubat" writes the tap, and his own word to an open
        # check-in or proposal is his yes, the same door the app's own button uses. Anything
        # else a voice note might carry — a document, a health reading, family coordination —
        # is not guessed at from a transcript: it is kept as his own note, unread past the
        # red-flag check already made above, and he is asked to say it again if it mattered.
        #
        # A Taken tap closes the dose window and stops the escalation ladder — nobody asks
        # him again, nobody asks the helper, nobody tells his chief. Missing that ladder costs
        # more than asking him twice, so the transcript is trusted for TAKEN/ANSWER only at
        # the same confidence floor a scanned document field is trusted at before it is shown
        # undotted (`CONFIDENCE_THRESHOLD`, `app/ingestion/models.py`): TAKEN_REPLY, YES and NO
        # are a short closed list, and a recogniser hallucinating one of those exact words on
        # noise is the documented failure mode for short common utterances, not a hypothetical
        # one. Below the floor he keeps his note, unread, and is asked again — nothing closes
        # on a guess.
        confident = work.heard is not None and work.heard.confidence >= CONFIDENCE_THRESHOLD
        if confident and what.kind is Kind.TAKEN:
            return await _taken(session, work)
        if confident and what.kind is Kind.ANSWER:
            assert what.answer is not None
            return await _answer(session, work, what.answer)
        return await _voice_note(session, work)
    if work.message.group_id is not None:
        if work.message.media_id is None and work.message.text:
            return await _group_message(session, work)
        # A photo or a file in the family's group is the family's, never one of his papers.
        return Handled(outcome="ignored", profile_id=work.profile.id)
    if work.message.text and what.kind in (Kind.OTHER, Kind.HEALTH_EVENT):
        # An answer to "which tablet?" (#162): a number, "both", or the tablet's own word.
        question = await _open_question(session, work)
        if question is not None:
            answered = await _answer_which(session, work, question, what)
            if answered is not None:
                return answered
    if what.kind is Kind.DOCUMENT:
        return await _document(session, work)
    if what.kind is Kind.HEALTH_EVENT:
        assert what.event is not None
        return await _health_event(session, work, what.event)
    if what.kind is Kind.ANSWER:
        assert what.answer is not None
        return await _answer(session, work, what.answer)
    if what.kind is Kind.TAKEN:
        return await _taken(session, work)
    if what.kind is Kind.COORDINATION:
        return await _coordination(session, work)
    return await _other(session, work)


async def _refusal_reply(session: AsyncSession, work: _Work, refusal: Refusal) -> Handled:
    """What the thread says when a door refused: the same refusal the app gives, by name on
    the trail already, and a catalogue line to the poster. A missing consent is told as
    such and cannot itself go through the send door, so it goes to the provider directly
    and is written down as a share of a refusal notice, content-free."""
    name = type(refusal).__name__
    if isinstance(refusal, NoConsent):
        text = reply("no_whatsapp_yet", work.language, name=work.profile.display_name)
        await work.providers.whatsapp.send_text(work.message.from_e164, text)
        await record(
            session,
            context=work.context,
            action=Action.SHARE,
            scope=Scope.PROFILE,
            target="refusal_notice",
            channel=Channel.WHATSAPP,
            rows=1,
            shared_with_person_id=work.person.id,
            shared_with_label=name,
        )
        return Handled(outcome="refused", profile_id=work.profile.id, refused=name)
    key = "not_open_to_you" if isinstance(refusal, OutOfScope) else "not_understood"
    try:
        await _say(session, work, key, name=work.profile.display_name)
    except Refusal:
        pass
    return Handled(
        outcome="refused", replies=tuple(work.replies), profile_id=work.profile.id, refused=name
    )


async def handle_inbound(
    session: AsyncSession,
    *,
    settings: Settings,
    providers: Providers,
    number: BusinessNumber,
    classifier: Classifier,
    message: InboundMessage,
) -> Handled:
    """One message, all the way. See the module doc for the order and why."""
    region = settings.region
    # The family's group names its family (E11-01). A group this number does not keep is
    # not read, and nothing is said into any group from here.
    group = (
        None
        if message.group_id is None
        else await profile_for_group(session, region=region, provider_group_id=message.group_id)
    )
    if message.group_id is not None and group is None:
        log.info("whatsapp: a message in a group this number does not keep")
        return Handled(outcome="ignored")
    person = await find_person_by_phone(session, message.from_e164)
    if person is None:
        if group is not None:
            return await _not_kept_in_the_group(providers, message, region=region, language=None)
        return await _stranger(providers, message)
    try:
        guard_region(held_in=person.region, asked_from=region)
    except OutOfRegion:
        # A number pinned elsewhere is, to this deployment, a stranger: same words, nothing
        # about where it is known written anywhere here.
        if group is not None:
            return await _not_kept_in_the_group(
                providers, message, region=region, language=person.language
            )
        return await _stranger(providers, message)
    # A voice note is heard first, in the region, so its words are read like a message's: a
    # red word in it is found before anything else, "ignore" and the consent included.
    voice: Media | None = None
    heard: Transcript | None = None
    if _is_voice(message):
        voice, heard = await _hear(providers, region, person, message)
        message = replace(message, text=heard.text if heard.heard else None)
    # A red-flag word is looked for first: "ignore" never cancels one in the same message.
    flagged = detect(message.text) is not None
    if (
        not flagged
        and message.text
        and classifier.classify(text=message.text, content_type=None).kind is Kind.IGNORE
    ):
        log.info("whatsapp: ignored by request %s", _handle(person.id, message.from_e164))
        return Handled(outcome="ignored")

    if group is not None and await closing_since(session, profile_id=group) is not None:
        # The family's group of a closing account (#143) was emptied; a post that still
        # arrives is not taken in. A red word is answered, to the sender alone, with who to call.
        if flagged:
            return await _stranger(
                providers,
                message,
                key="closing",
                language=person.language,
                emergency_number=EMERGENCY_NUMBER[region.value],
            )
        return Handled(outcome="ignored")
    reachable = (
        [group]
        if group is not None
        else await _profiles_reachable(session, region=region, person=person)
    )
    closing = (
        []
        if group is not None
        else await _profiles_reachable(session, region=region, person=person, closing=True)
    )
    if closing:
        # A family this number belongs to is closing its account (#143). A yes from someone a
        # red flag raised before the closing reached is still that flag's answer.
        answered = await _answer_while_closing(
            session,
            providers=providers,
            classifier=classifier,
            message=message,
            person=person,
            region=region,
            closing=closing,
        )
        if answered is not None:
            return answered
        recent = (
            await _most_recent_thread(session, person=person, profiles=[*reachable, *closing])
            if reachable
            else None
        )
        closing_line = reply(
            "closing", person.language, emergency_number=EMERGENCY_NUMBER[region.value]
        )
        if not reachable or recent in closing:
            # Every family left is closing, or the last one this number talked about is: one
            # fixed line with who to call — nothing kept, nothing raised, never guessed onto
            # another family's papers.
            return await _stranger(
                providers,
                message,
                key="closing",
                language=person.language,
                emergency_number=EMERGENCY_NUMBER[region.value],
            )
        if flagged and recent is None:
            # Nothing says which family: a red word is raised on the families still open, as
            # any red word on more than one list is, and the sender is told who to call too.
            await providers.whatsapp.send_text(message.from_e164, closing_line)
    if not reachable:
        return await _stranger(providers, message)
    profile_id = reachable[0]
    if len(reachable) > 1:
        recent = await _most_recent_thread(session, person=person, profiles=reachable)
        if recent is None:
            # On more than one family's list and nothing to say which: a red flag never waits
            # on "which one?" — it is raised on each — and a name answers the question.
            settled = (
                await _red_flag_everywhere(
                    session,
                    settings=settings,
                    providers=providers,
                    number=number,
                    person=person,
                    profiles=reachable,
                    message=message,
                )
                if flagged
                else await _which_one(
                    session,
                    settings=settings,
                    providers=providers,
                    person=person,
                    profiles=reachable,
                    message=message,
                )
            )
            if settled is not None:
                return settled
            return await _stranger(
                providers, message, key="more_than_one", language=person.language
            )
        profile_id = recent
    try:
        context = await resolve_key_context(
            session, region=region, person_id=person.id, profile_id=profile_id
        )
    except Refusal:
        if group is None:
            raise
        # In the group, but no longer on this family's list: nothing kept; a red word is
        # answered to the sender alone, with who to call (#143).
        return await _not_kept_in_the_group(
            providers, message, region=region, language=person.language
        )
    profile = await audited_profile_read(session, context, channel=Channel.WHATSAPP)
    if flagged and not await _whatsapp_agreed(session, context=context):
        return await _red_flag_unagreed(
            session,
            settings=settings,
            providers=providers,
            number=number,
            person=person,
            context=context,
            profile=profile,
            message=message,
        )
    if (
        not flagged
        and group is None
        and _is_voice(message)
        and not (heard is not None and heard.heard)
        and not await _whatsapp_agreed(session, context=context)
    ):
        # A voice note with no words in it, on a profile whose patient has not agreed to
        # WhatsApp (#173). The consent refusal below would answer the sender and tell nobody;
        # a red word nobody could read must still reach a person, so it goes first. One
        # posted in the family's group is the family's, here as in `_dispatch`.
        return await _unheard_unagreed(
            session,
            settings=settings,
            providers=providers,
            number=number,
            person=person,
            context=context,
            profile=profile,
            message=message,
        )

    async def work_for() -> _Work:
        thread = await thread_for(session, context=context, person=person)
        thread.last_inbound_at = utcnow()
        await session.flush()
        return _Work(
            settings=settings,
            providers=providers,
            number=number,
            classifier=classifier,
            message=message,
            person=person,
            context=context,
            profile=profile,
            thread=thread,
            language=language_of(person.language),
            voice=voice,
            heard=heard,
            voice_missing=_is_voice(message) and voice is None,
        )

    try:
        async with unit_of_work(session):
            await require_consent(
                session,
                context=context,
                purpose=ConsentPurpose.WHATSAPP,
                scope=Scope.PROFILE,
                channel=Channel.WHATSAPP,
            )
            work = await work_for()
            what = classifier.classify(
                text=message.text, content_type=None if voice is not None else message.content_type
            )
            return await _dispatch(session, work, what)
    except NoSuchMedia as refusal:
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.RECORDS,
            target=Artifact.__tablename__,
            outcome=Outcome.REFUSED,
            refused_because=type(refusal).__name__,
            channel=Channel.WHATSAPP,
        )
        return Handled(outcome="refused", profile_id=profile.id, refused=type(refusal).__name__)
    except Refusal as refusal:
        log.info(
            "whatsapp: refused %s for %s",
            type(refusal).__name__,
            _handle(person.id, message.from_e164),
        )
        # The unit rolled back, the thread's opening with it; but the person did write, so
        # the window is opened again here and the refusal reply can go as free text.
        return await _refusal_reply(session, await work_for(), refusal)
