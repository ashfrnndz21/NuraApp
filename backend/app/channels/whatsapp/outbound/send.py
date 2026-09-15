"""The one door a message leaves through.

`send` takes who it is for, what it is (a template name, or a reply key from the catalogue)
and the slots, and does the rest in order: whether Nura may message this person about the
profile (`_may_message`: his WHATSAPP consent for him; for anyone else a key, their own answer,
and his agreement for anything but a red flag),
the recipient's thread and where its 24-hour window stands, the rendered words through the
plain-words verifier, the provider, the message row naming the template or the key and the
State it came from, and the SHARE line. A template outside the window is sent as a
template; inside it, as text; a reply outside the window cannot be sent at all.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard, audited_read, audited_write, record_share
from app.audit.models import Action, Channel
from app.channels.whatsapp.config import BusinessNumber
from app.channels.whatsapp.models import (
    Direction,
    MessageKind,
    WhatsAppMessage,
    WhatsAppThread,
)
from app.channels.whatsapp.opt_in import said_no
from app.channels.whatsapp.provider import WhatsAppProvider
from app.channels.whatsapp.strings import REPLIES, reply
from app.channels.whatsapp.templates import TEMPLATES, language_of, render
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.delivery.voice import Voice, voiced
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.ingestion.objects import ObjectStore
from app.keys.context import KeyContext, holds_the_profile
from app.keys.scopes import Scope
from app.safety.plain_words import verify
from app.state.service import StateView

CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)
"""How long after a person's last message the number may answer in free text."""

MESSAGE = WhatsAppMessage.__tablename__
THREAD = WhatsAppThread.__tablename__


class NoNumber(Refusal):
    """The person has no phone number, so there is no WhatsApp to send to."""


class OutsideTheWindow(Refusal):
    """More than 24 hours since the person's last message: only a template may go out."""


class TemplateNotApproved(Refusal):
    """A template Meta has not approved for this number is not sent: the refusal is on the
    trail, and a delivery tries its next channel."""


class NotPlainWords(Refusal):
    """The rendered text did not pass docs/plain-words.md. Nothing that fails ships."""


class NotFromState(Refusal):
    """A proactive template is composed from State; none was given, or it is behind."""


class NotAMessage(Refusal):
    """Neither an approved template nor a reply in the catalogue."""


@dataclass(frozen=True, slots=True)
class Delivered:
    """What went out: to whom, as what, the words, and the rows that record it."""

    to_person_id: uuid.UUID
    to_e164: str
    kind: str
    """`text` or `template`."""
    template_name: str | None
    catalogue_key: str | None
    text: str
    message_id: uuid.UUID
    provider_message_id: str


def inside_window(thread: WhatsAppThread | None, now: datetime) -> bool:
    if thread is None or thread.last_inbound_at is None:
        return False
    return now - as_utc(thread.last_inbound_at) < CUSTOMER_SERVICE_WINDOW


async def thread_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    person: Person,
    channel: Channel = Channel.WHATSAPP,
) -> WhatsAppThread:
    """The thread between this person and this profile, opened now if it was not before.

    Thread rows are under the profile scope every key holds: they say who talks to the
    profile on WhatsApp, which is part of whose graph it is, and hold nothing it says.
    """
    found = await audited_read(
        session,
        WhatsAppThread,
        context,
        Scope.PROFILE,
        where=(WhatsAppThread.person_id == person.id,),
        channel=channel,
    )
    if found:
        return found[0]
    profile = await session.get(Profile, context.profile_id)
    assert profile is not None  # the context was resolved from this row
    return await audited_write(
        session,
        WhatsAppThread,
        context,
        Scope.PROFILE,
        channel=channel,
        person_id=person.id,
        is_patient=profile.owner_person_id == person.id,
        opened_at=utcnow(),
    )


NAME_SLOTS: frozenset[str] = frozenset(
    {"name", "names", "who", "doctor", "hospital", "patient", "chief", "insurer", "clinic", "both", "either"}
)
"""Slots that hold a name: a person's, a doctor's, a hospital's, an insurer's. The standard
leaves names alone — a name is said as it is written — so the words are verified with each name
slot standing in as a plain name (`NAME_STAND_IN`) and sent with the real one: "SGH" is a
hospital's name, not an abbreviation in his sentence, and a red flag's reply is never refused
for it (B1 review)."""

NAME_STAND_IN = "Ash"


class NotLetInHere(Refusal):
    """This person holds no key to the profile, so Nura says nothing to them about it."""


class SaidNoToWhatsApp(Refusal):
    """This person answered no to WhatsApp messages from Nura at the key-accept step (#163):
    Nura starts none with them, a red-flag notice included — that reaches them by app push and
    on their family page. A reply to a message they wrote themselves still goes."""


RED_FLAG_NOTICES: frozenset[str] = frozenset(
    {"red_flag_notice", "red_flag_notice_self", "red_flag_notice_ambiguous"}
)
"""The one kind of message about him his family is sent on WhatsApp after he stops it (#163)."""


async def _may_message(
    session: AsyncSession, *, context: KeyContext, person: Person, kind: str | None
) -> None:
    """Whether Nura may message this person about the profile (#143, #163). `kind` is the
    template or the reply key; None for a voice note.

    The patient's WhatsApp agreement is for messages to him. Anyone else must hold a key his
    agreement to let them in rests on. A message Nura starts with them — a template or a voice
    note — needs two things more: that they did not answer no to WhatsApp (`SaidNoToWhatsApp`),
    and, unless it is a red-flag notice, that his WhatsApp agreement stands. So after he stops
    WhatsApp his family hears about him there only when he is unwell, which is what his stop
    lines say (`app.consent.withdrawal.STILL_TOLD`). A reply answers something they wrote, and
    the inbound door has asked his agreement before it (or it is a red flag's fixed line)."""
    profile = await session.get(Profile, context.profile_id)
    assert profile is not None  # the context was resolved from this row
    patient = profile.owner_person_id == person.id or (
        profile.owner_person_id is None
        and profile.patient_phone_e164 is not None
        and profile.patient_phone_e164 == person.phone_e164
    )
    if patient:
        await require_consent(
            session,
            context=context,
            purpose=ConsentPurpose.WHATSAPP,
            scope=Scope.SEND,
            channel=Channel.WHATSAPP,
        )
        return
    starts = kind is None or kind in TEMPLATES
    async with audited_guard(
        session, context, Action.SHARE, Scope.SEND, "whatsapp_message", channel=Channel.WHATSAPP
    ):
        if not await holds_the_profile(session, profile_id=context.profile_id, person_id=person.id):
            raise NotLetInHere(f"person {person.id} holds no key here")
        if starts and await said_no(
            session, context=context, person_id=person.id, channel=Channel.WHATSAPP
        ):
            raise SaidNoToWhatsApp(f"person {person.id} said no to WhatsApp")
    if starts and kind not in RED_FLAG_NOTICES:
        await require_consent(
            session,
            context=context,
            purpose=ConsentPurpose.WHATSAPP,
            scope=Scope.SEND,
            channel=Channel.WHATSAPP,
        )


def _render(
    kind: str, language: str, params: Mapping[str, str]
) -> tuple[str, str | None, str | None, str]:
    """The words, which of a template or a catalogue key they came from, and the words as the
    verifier reads them — every name slot standing in as a plain name."""
    stand_in = {key: NAME_STAND_IN if key in NAME_SLOTS else value for key, value in params.items()}
    if kind in TEMPLATES:
        return render(kind, language, params), kind, None, render(kind, language, stand_in)
    if kind in REPLIES:
        return reply(kind, language, **params), None, kind, reply(kind, language, **stand_in)
    raise NotAMessage(f"{kind!r} is neither an approved template nor a catalogue reply")


async def send(
    session: AsyncSession,
    *,
    context: KeyContext,
    to_person: Person,
    kind: str,
    params: Mapping[str, str],
    provider: WhatsAppProvider,
    number: BusinessNumber,
    language: str | None = None,
    state: StateView | None = None,
) -> Delivered:
    """Send one message to one person about the profile in the context.

    `kind` is a template name (proactive: needs the `state` it was composed from, and may go
    outside the window) or a reply key (free text: inside the window only). The consent
    checked is the profile's WHATSAPP consent, under the send scope, on the WhatsApp
    channel; the refusal, like every other here, is on the trail before it is passed on.
    """
    if not to_person.phone_e164:
        raise NoNumber(f"person {to_person.id} has no phone number")
    await _may_message(session, context=context, person=to_person, kind=kind)
    moment = utcnow()
    lang = language_of(language or to_person.language)
    thread = await thread_for(session, context=context, person=to_person)
    text, template_name, catalogue_key, checked = _render(kind, lang, params)
    failures = [finding for finding in verify(checked, lang) if finding.severity == "fail"]
    if failures:
        raise NotPlainWords(f"{kind} in {lang}: {failures[0].problem}")

    state_id: uuid.UUID | None = None
    if template_name is not None:
        if not number.approves(template_name):
            async with audited_guard(
                session, context, Action.SHARE, Scope.SEND, MESSAGE, channel=Channel.WHATSAPP
            ):
                raise TemplateNotApproved(f"{template_name} is not approved on {number.phone_e164}")
        if state is None or state.stale is not False or state.profile_id != context.profile_id:
            raise NotFromState(f"{template_name} is composed from a current State of this profile")
        state_id = state.id
    elif not inside_window(thread, moment):
        raise OutsideTheWindow("a reply is free text, and free text needs the 24-hour window")

    if template_name is not None and not inside_window(thread, moment):
        provider_id = await provider.send_template(
            to_person.phone_e164, template_name, lang, {**params, "_rendered": text}
        )
        how = "template"
    else:
        provider_id = await provider.send_text(to_person.phone_e164, text)
        how = "text"

    row = await audited_write(
        session,
        WhatsAppMessage,
        context,
        Scope.PROFILE,
        channel=Channel.WHATSAPP,
        thread_id=thread.id,
        direction=Direction.OUTBOUND,
        kind=MessageKind.TEMPLATE if template_name else MessageKind.REPLY,
        person_id=to_person.id,
        at=moment,
        provider_message_id=provider_id,
        template_name=template_name,
        catalogue_key=catalogue_key,
        state_id=state_id,
    )
    await record_share(
        session,
        context=context,
        scope=Scope.SEND,
        target=MESSAGE,
        channel=Channel.WHATSAPP,
        shared_with_person_id=to_person.id,
        target_id=row.id,
    )
    thread.last_outbound_at = moment
    await session.flush()
    return Delivered(
        to_person_id=to_person.id,
        to_e164=to_person.phone_e164,
        kind=how,
        template_name=template_name,
        catalogue_key=catalogue_key,
        text=text,
        message_id=row.id,
        provider_message_id=provider_id,
    )


async def send_voice_note(
    session: AsyncSession,
    *,
    context: KeyContext,
    to_person: Person,
    lines: Sequence[str],
    provider: WhatsAppProvider,
    voice: Voice,
    store: ObjectStore,
    language: str | None = None,
    state: StateView | None = None,
) -> Delivered:
    """A card's spoken twin as a WhatsApp voice note (E11-04), through the same checks as
    every send: his WHATSAPP consent, plain words, a message row by reference, a SHARE line.

    A voice note is not a template, so it goes only inside the 24-hour window
    (`OutsideTheWindow` otherwise): outside it the card goes as its template and the twin
    waits in his feed, where a tap plays it. The audio comes from the one `Voice` port and
    the region's cache (`app.delivery.voice.voiced`), under thirty seconds or not at all.
    """
    if not to_person.phone_e164:
        raise NoNumber(f"person {to_person.id} has no phone number")
    await _may_message(session, context=context, person=to_person, kind=None)
    moment = utcnow()
    lang = language_of(language or to_person.language)
    thread = await thread_for(session, context=context, person=to_person)
    if not inside_window(thread, moment):
        raise OutsideTheWindow("a voice note is not a template: it needs the 24-hour window")
    text = "\n".join(lines)
    failures = [finding for finding in verify(text, lang) if finding.severity == "fail"]
    if failures:
        raise NotPlainWords(f"voice note in {lang}: {failures[0].problem}")
    said = await voiced(
        store,
        voice,
        profile_id=context.profile_id,
        region=context.region,
        lines=lines,
        language=lang,
    )
    provider_id = await provider.send_audio(
        to_person.phone_e164, said.spoken.audio, said.spoken.content_type
    )
    row = await audited_write(
        session,
        WhatsAppMessage,
        context,
        Scope.PROFILE,
        channel=Channel.WHATSAPP,
        thread_id=thread.id,
        direction=Direction.OUTBOUND,
        kind=MessageKind.VOICE_NOTE,
        person_id=to_person.id,
        at=moment,
        provider_message_id=provider_id,
        state_id=None if state is None else state.id,
    )
    await record_share(
        session,
        context=context,
        scope=Scope.SEND,
        target=MESSAGE,
        channel=Channel.WHATSAPP,
        shared_with_person_id=to_person.id,
        target_id=row.id,
    )
    thread.last_outbound_at = moment
    await session.flush()
    return Delivered(
        to_person_id=to_person.id,
        to_e164=to_person.phone_e164,
        kind="audio",
        template_name=None,
        catalogue_key=None,
        text=text,
        message_id=row.id,
        provider_message_id=provider_id,
    )


async def thread_messages(
    session: AsyncSession, *, context: KeyContext, thread_id: uuid.UUID | None = None
) -> Sequence[WhatsAppMessage]:
    """Every kept message on this profile's threads, oldest first, by reference."""
    where = () if thread_id is None else (WhatsAppMessage.thread_id == thread_id,)
    found = await audited_read(
        session, WhatsAppMessage, context, Scope.PROFILE, where=where, channel=Channel.WHATSAPP
    )
    return sorted(found, key=lambda row: (as_utc(row.at), str(row.id)))
