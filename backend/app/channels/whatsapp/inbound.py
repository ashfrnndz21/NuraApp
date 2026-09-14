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
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard, audited_profile_read, audited_read, audited_write
from app.audit.models import Action, Channel, Outcome
from app.audit.trail import record
from app.channels.api.deps import Providers
from app.channels.whatsapp.classifier import Classification, Classifier, HealthEvent, Kind
from app.channels.whatsapp.config import BusinessNumber
from app.channels.whatsapp.models import (
    Direction,
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
from app.channels.whatsapp.group import group_for, is_member
from app.channels.whatsapp.provider import InboundMessage, Media, NoSuchMedia
from app.channels.whatsapp.strings import FEELING_WORDS, YOU, YOUR_DOCTOR, join_names, reply
from app.channels.whatsapp.templates import language_of
from app.consent.models import ConsentPurpose
from app.consent.service import NoConsent, require_consent
from app.db import as_utc, unit_of_work, utcnow
from app.delivery.strings import EMERGENCY_NUMBER, theirs
from app.delivery.triggers.deliver import Via
from app.delivery.triggers.ladder import (
    acknowledge_dose,
    acknowledge_flag,
    close,
    dose_for_reply,
    escalate_flag,
    medicine_words,
)
from app.delivery.triggers.models import Ladder
from app.drafts import FactDraft
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.identity.service import find_person_by_phone
from app.family.thread import post_message
from app.ingestion.notes import NoteView, keep_voice_message
from app.ingestion.objects import check_key, sha256_of
from app.ingestion.photos import store_photo
from app.ingestion.review import review_photo
from app.ingestion.transcribe import NOTHING_HEARD, Transcript
from app.keys.confirm import confirm
from app.keys.context import KeyContext, OutOfScope, owned_profile, resolve_key_context
from app.keys.models import Key
from app.keys.scopes import Scope, scope_for_subject
from app.medicines.service import record_dose_taken
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
from app.memory.semantic import assert_fact
from app.regions import REGION_TZ, OutOfRegion, Region, guard_region
from app.safety.red_flags import FLAG_WINDOW, Flag, detect, raise_flag, record_the_moment
from app.settings import Settings

log = logging.getLogger("nura.channels.whatsapp")

MESSAGE = WhatsAppMessage.__tablename__
TEXT_CONTENT_TYPE = "text/plain; charset=utf-8"
IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/heic", "image/webp"})
PDF_CONTENT_TYPE = "application/pdf"
FEELING_VOCABULARY = frozenset({"ok", "tired", "pain"})


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


def _handle(person_id: uuid.UUID | None, phone: str) -> str:
    """A short handle for the log: never the number, never the id."""
    return hashlib.sha256(f"{person_id}:{phone}".encode()).hexdigest()[:8]


# --- resolving the sender ------------------------------------------------------------------


async def _profiles_reachable(
    session: AsyncSession, *, region: Region, person: Person
) -> list[uuid.UUID]:
    """The profiles this person may act on here: their own, then every live key's."""
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
    return found


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
) -> Handled:
    """One fixed reply, no health content, nothing stored. Logged by a handle."""
    text = reply(key, language)
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
    feeling = detect(work.message.text)
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
    doctor = await _doctor(session, work)
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
    if names:
        key = "red_flag_one" if len(names) == 1 else "red_flag"
        await _say(session, work, key, doctor=doctor, names=join_names(names, work.language))
    else:
        await _say(session, work, "red_flag_alone", doctor=doctor)
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
    feeling = detect(message.text)
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
    feeling = detect(message.text)
    assert feeling is not None
    raised: list[tuple[Profile, KeyContext, Flag]] = []
    for profile_id in profiles:
        context = await resolve_key_context(
            session, region=settings.region, person_id=person.id, profile_id=profile_id
        )
        if not context.allows(Scope.EMERGENCY):
            continue
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


async def _taken(session: AsyncSession, work: _Work) -> Handled:
    """ "Taken" from him, "given" from the helper: the Taken tap, said as a reply (E11-01).

    It is about the tablet the ladder last asked this person about today, else the one whose
    window is open now with no Taken yet; with neither, nothing is written and the reply says
    so. The tap is written the way the app's button writes it — the tap is the yes, under
    the medicines scope the helper's key holds — on the WhatsApp channel, and the ladder for
    that tablet stops at once.
    """
    registry = work.providers.drug_registry
    asked = await dose_for_reply(
        session, context=work.context, registry=registry, at=work.message.at
    )
    if asked is None:
        await _say(session, work, "taken_nothing_due")
        return Handled(
            outcome="nothing_due", replies=tuple(work.replies), profile_id=work.profile.id
        )
    artifact = await _keep_text(session, work=work, scope=Scope.MEDICINES)
    row = await _keep_row(session, work=work, kind=MessageKind.TAKEN, artifact=artifact)
    await record_dose_taken(
        session,
        context=work.context,
        line_id=asked.line_id,
        anchor=asked.anchor,
        source_channel=SourceChannel.WHATSAPP,
        channel=Channel.WHATSAPP,
    )
    day = as_utc(work.message.at).astimezone(REGION_TZ[work.context.region]).date().isoformat()
    await acknowledge_dose(
        session,
        context=work.context,
        line_id=asked.line_id,
        anchor=asked.anchor,
        day=day,
        channel=Channel.WHATSAPP,
    )
    if work.thread.is_patient:
        who = await _who_checks(session, work)
        if who != YOU[work.language]:
            await _say(session, work, "taken_patient", who=who)
        else:
            await _say(session, work, "taken_alone")
    else:
        medicine = theirs(
            medicine_words(registry, asked.generic, work.language),
            work.profile.display_name,
            work.language,
        )
        await _say(session, work, "given", name=work.profile.display_name, medicine=medicine)
    return Handled(
        outcome="taken",
        replies=tuple(work.replies),
        profile_id=work.profile.id,
        message_id=row.id,
        artifact_id=artifact.id,
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


async def _check_in_answer(session: AsyncSession, work: _Work, event: HealthEvent) -> Handled:
    """The patient's own feeling word, in his own thread: the reply is the yes.

    No proposal: there is nothing to read back. Mei's "he's tired" is a third party's
    account of him, read out of free text, so she is asked whether Nura heard it right; his
    "tired" is one of the three words Nura offered him, about himself, with nothing
    extracted from it. So — like the Taken tap — the word is written down as his own, the
    confirmation minted and spent in the same unit of work, the way the app's save button
    does for a number he typed.
    """
    assert event.word is not None
    artifact = await _keep_text(session, work=work)
    row = await _keep_row(session, work=work, kind=MessageKind.CHECK_IN_ANSWER, artifact=artifact)
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
        media = await providers.whatsapp.fetch_media(message.media_id)
    except NoSuchMedia:
        return None, NOTHING_HEARD
    kind = media.content_type.split(";", 1)[0].strip().lower()
    guard_region(held_in=providers.transcriber.region, asked_from=region)
    heard = await providers.transcriber.transcribe(
        media.data, kind, language_of(person.language), region
    )
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
    other people's voices, which only a consult keeps, on the consent to record."""
    if not work.context.is_owner:
        return await _other(session, work)
    view = await _keep_voice(session, work)
    row = await _keep_row(session, work=work, kind=MessageKind.VOICE_NOTE, artifact=view.artifact)
    await _say(
        session, work, "voice_note_kept" if view.transcript is not None else "voice_note_unheard"
    )
    return Handled(
        outcome="voice_note",
        replies=tuple(work.replies),
        profile_id=work.profile.id,
        message_id=row.id,
        artifact_id=view.artifact.id,
        note_id=view.note.id,
    )


async def _group_message(session: AsyncSession, work: _Work) -> Handled:
    """A message in the family's group (E11-01): it lands in the family thread (E12-02) in its
    poster's name, for a member — someone who reads the thread (`is_member`). Anyone else in
    the group is not a member: nothing is kept and nothing is said. Nobody is answered in the
    group, and nothing is read out of what the family says to each other."""
    if not is_member(work.context):
        log.info("whatsapp: a group message from someone who does not read the family thread")
        return Handled(outcome="ignored", profile_id=work.profile.id)
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
            # The flag first; then his voice note is his own note, like any other.
            kept = await _keep_voice(session, work)
            return replace(flagged, note_id=kept.note.id)
        return flagged
    if work.voice is not None:
        return await _voice_note(session, work)
    if work.message.group_id is not None and work.message.media_id is None and work.message.text:
        return await _group_message(session, work)
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
    group = None if message.group_id is None else await group_for(session, message.group_id)
    if message.group_id is not None and group is None:
        log.info("whatsapp: a message in a group this number does not keep")
        return Handled(outcome="ignored")
    person = await find_person_by_phone(session, message.from_e164)
    if person is None:
        if group is not None:
            return Handled(outcome="ignored")
        return await _stranger(providers, message)
    try:
        guard_region(held_in=person.region, asked_from=region)
    except OutOfRegion:
        # A number pinned elsewhere is, to this deployment, a stranger: same words, nothing
        # about where it is known written anywhere here.
        if group is not None:
            return Handled(outcome="ignored")
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

    reachable = (
        [group.profile_id]
        if group is not None
        else await _profiles_reachable(session, region=region, person=person)
    )
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
                    session, settings=settings, providers=providers, person=person,
                    profiles=reachable, message=message,
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
        # In the group, but no longer on this family's list: nothing kept, nothing said.
        return Handled(outcome="ignored")
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
