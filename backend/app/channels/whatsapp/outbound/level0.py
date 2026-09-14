"""The patient's Level 0: a whole day on WhatsApp, with no app (E19-03).

Four things go to him, each one of the six approved templates, each composed from the
current State and the record it folds, each a function a scheduler (E11) will call at its
hour — nothing here is scheduled yet, and the dev-only route calls `run_morning` by hand:

- the morning card: the now and today cards his feed leads with (`rank.morning_supply`) —
  the tablets card said as today's doses the way the medicines module renders them — and one
  thing to measure;
- the feeling check-in: three words, one tap; his answer is his own and is written down
  without a second yes (`inbound._check_in_answer` says why);
- the visit card: the next visit on the spine, with who takes him;
- the family notice: to each chief, how many things were written down this week.

Every one goes through `send`: the profile's WHATSAPP consent, a template outside the
window, plain words, a SHARE line. All of it runs in the owner's own key context — the
patient's day is sent to the patient about the patient.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.audit.models import Channel
from app.channels.api.deps import Providers
from app.channels.whatsapp.config import BusinessNumber
from app.channels.whatsapp.outbound.send import Delivered, send
from app.channels.whatsapp.strings import YOUR_DOCTOR
from app.channels.whatsapp.templates import language_of
from app.db import as_utc, utcnow
from app.delivery.feed.models import CardType
from app.delivery.feed.rank import morning_supply
from app.delivery.feed.search import Engine
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.keys.context import KeyContext, profile_by_id, resolve_key_context
from app.keys.models import Key
from app.keys.scopes import KeyRole, Scope
from app.medicines.service import today
from app.medicines.strings import say_date
from app.memory.models import Provider
from app.memory.semantic import current_facts
from app.memory.spine import upcoming_appointments
from app.regions import REGION_TZ
from app.settings import Settings
from app.state.service import StateView, current_state

# @patient
NO_DOSES_TODAY = {
    "en": "You have no tablets written down for today.",
    "ms": "Tiada ubat ditulis untuk hari ini.",
    "zh": "今天没有记下要吃的药。",
}
"""The doses slot of the morning card when the list is empty."""

# @patient
TABLETS_ON_YOUR_LIST = {
    "en": ("Your tablets for today are on your list.", "Take them the way the label says."),
    "ms": (
        "Ubat anda untuk hari ini ada dalam senarai anda.",
        "Ambil ikut apa yang tertulis pada label.",
    ),
    "zh": ("您今天的药在您的清单上。", "请按照药盒上写的吃。"),
}
"""The feed's tablets card on WhatsApp when there are medicines on his papers but no dose
line written down yet: its words without the app's Taken button, which the thread has not."""


class NoPatientYet(Refusal):
    """The profile has no owner yet: it is stewarded, and there is no patient's thread."""


async def _owner(
    session: AsyncSession, *, settings: Settings, profile_id: uuid.UUID
) -> tuple[Profile, Person, KeyContext]:
    profile = await profile_by_id(session, region=settings.region, profile_id=profile_id)
    if profile is None or profile.owner_person_id is None:
        raise NoPatientYet(f"profile {profile_id} has no patient to send to here")
    owner = await session.get(Person, profile.owner_person_id)
    assert owner is not None  # the profile names this row
    context = await resolve_key_context(
        session, region=settings.region, person_id=owner.id, profile_id=profile.id
    )
    return profile, owner, context


def _today(context: KeyContext, language: str) -> str:
    return say_date(utcnow().astimezone(REGION_TZ[context.region]).date(), language)


async def run_morning(
    session: AsyncSession,
    *,
    settings: Settings,
    providers: Providers,
    number: BusinessNumber,
    profile_id: uuid.UUID,
) -> Delivered:
    """The morning card to the patient: what his feed leads with today, and one thing to
    measure. The doses slot carries the lines; the State is the one the cards came from."""
    profile, owner, context = await _owner(session, settings=settings, profile_id=profile_id)
    language = language_of(profile.language)
    state, lines = await _morning_lines(
        session, context=context, providers=providers, language=language
    )
    doses = "\n".join(lines)
    return await send(
        session,
        context=context,
        to_person=owner,
        kind="morning_card",
        params={"name": profile.display_name, "day": _today(context, language), "doses": doses},
        provider=providers.whatsapp,
        number=number,
        language=language,
        state=state,
    )


async def _morning_lines(
    session: AsyncSession, *, context: KeyContext, providers: Providers, language: str
) -> tuple[StateView, list[str]]:
    """The lines between the day and the thing to measure: the now and today cards of his
    feed, in its order and under its caps. The now card about his tablets is said as today's
    doses from the medicines module (the app's card points at the list; a thread has no
    list); a quiet now card as "no tablets written down"; every other card as its own body,
    lines that already passed plain words when the card was made. When the feed gives no line
    at all — every card held by his "not for me" — the doses alone, as before the feed."""
    engine = Engine(
        searcher=providers.searcher,
        compressor=providers.compressor,
        registry=providers.drug_registry,
    )
    state, items = await morning_supply(session, context=context, engine=engine)
    slots = await today(
        session, context=context, registry=providers.drug_registry, language=language
    )
    doses = [slot.card for slot in slots]
    lines: list[str] = []
    for item in items:
        if item.type is CardType.NOW and item.scope is not Scope.VISITS:
            if doses:
                lines.extend(doses)
            elif item.scope is Scope.MEDICINES:
                lines.extend(TABLETS_ON_YOUR_LIST[language])
            else:
                lines.append(NO_DOSES_TODAY[language])
        else:
            lines.extend(item.body)
    return state, lines or doses or [NO_DOSES_TODAY[language]]


async def run_feeling_check_in(
    session: AsyncSession,
    *,
    settings: Settings,
    providers: Providers,
    number: BusinessNumber,
    profile_id: uuid.UUID,
) -> Delivered:
    """Three words to the patient. His answer is written down by the inbound path."""
    profile, owner, context = await _owner(session, settings=settings, profile_id=profile_id)
    language = language_of(profile.language)
    state = await current_state(session, context=context)
    return await send(
        session,
        context=context,
        to_person=owner,
        kind="feeling_check_in",
        params={"name": profile.display_name},
        provider=providers.whatsapp,
        number=number,
        language=language,
        state=state,
    )


async def run_visit_card(
    session: AsyncSession,
    *,
    settings: Settings,
    providers: Providers,
    number: BusinessNumber,
    profile_id: uuid.UUID,
) -> Delivered | None:
    """The next visit on the spine, or nothing when there is none to remind him of."""
    profile, owner, context = await _owner(session, settings=settings, profile_id=profile_id)
    language = language_of(profile.language)
    coming = await upcoming_appointments(session, context=context, limit=1)
    if not coming:
        return None
    visit = coming[0]
    providers_here = await audited_read(
        session,
        Provider,
        context,
        Scope.VISITS,
        where=(Provider.id == visit.provider_id,),
        channel=Channel.WHATSAPP,
    )
    doctor = providers_here[0].name if providers_here else YOUR_DOCTOR[language]
    when = as_utc(visit.scheduled_at).astimezone(REGION_TZ[context.region])
    chief = await _first_chief(session, context=context)
    state = await current_state(session, context=context)
    return await send(
        session,
        context=context,
        to_person=owner,
        kind="visit_reminder",
        params={
            "name": profile.display_name,
            "doctor": doctor,
            "day": say_date(when.date(), language),
            "time": when.strftime("%-I %p").lower() if language == "en" else when.strftime("%-H"),
            "who": chief or YOUR_DOCTOR[language],
        },
        provider=providers.whatsapp,
        number=number,
        language=language,
        state=state,
    )


async def _first_chief(session: AsyncSession, *, context: KeyContext) -> str | None:
    keys = await audited_read(session, Key, context, Scope.FAMILY, channel=Channel.WHATSAPP)
    moment = utcnow()
    for key in sorted(keys, key=lambda k: as_utc(k.granted_at)):
        if key.is_active(moment) and key.role is KeyRole.CHIEF:
            person = await session.get(Person, key.holder_person_id)
            if person is not None and person.display_name:
                return person.display_name
    return None


async def run_family_notice(
    session: AsyncSession,
    *,
    settings: Settings,
    providers: Providers,
    number: BusinessNumber,
    profile_id: uuid.UUID,
) -> Sequence[Delivered]:
    """To each chief: how many things were written down about him this week. A count, never
    what they said; the app is where the digest is read."""
    profile, _, context = await _owner(session, settings=settings, profile_id=profile_id)
    moment = utcnow()
    facts = await current_facts(session, context=context)
    this_week = [f for f in facts if as_utc(f.asserted_at) > moment - timedelta(days=7)]
    state = await current_state(session, context=context)
    keys = await audited_read(session, Key, context, Scope.FAMILY, channel=Channel.WHATSAPP)
    sent: list[Delivered] = []
    for key in sorted(keys, key=lambda k: as_utc(k.granted_at)):
        if not key.is_active(moment) or key.role is not KeyRole.CHIEF:
            continue
        chief = await session.get(Person, key.holder_person_id)
        if chief is None or not chief.phone_e164:
            continue
        sent.append(
            await send(
                session,
                context=context,
                to_person=chief,
                kind="family_digest",
                params={"name": profile.display_name, "count": str(len(this_week))},
                provider=providers.whatsapp,
                number=number,
                language=chief.language,
                state=state,
            )
        )
    return sent


__all__ = [
    "NoPatientYet",
    "run_family_notice",
    "run_feeling_check_in",
    "run_morning",
    "run_visit_card",
]
