"""The emergency card (E13-01): what a stranger needs to know, in two languages, offline.

    Conditions, medicines, allergies, blood type, contacts, insurer in two languages. Works
    offline. Daily-carry trust. The reason he keeps the app installed.

The card is a fixed projection of the record: his name, age band and language; the
conditions a clinician's control word is recorded against; the active medicines with their
strength and how much he takes; the allergies; the high-risk medicines by class; his blood
type if a fact says it; the chief's name and number; the doctor or clinic; the date of the
last reading; his insurer, as he or his chief typed it on a yes (`app.insurance.insurer`).
Nothing else, ever — no reading values, no notes, no visits, no history. That
projection is what `Scope.EMERGENCY` opens, and every role preset holds it, so an
emergency-only key (a neighbour, a helper) reads exactly this and nothing more. Every read
here is under EMERGENCY and on the trail as such.

The card is rendered from State. A key that can recompute goes through `render_from_state`;
an emergency-only key cannot, so it goes through `render_from_last_snapshot`, which refuses
the card unless the last snapshot already folds in every fact the card shows. Either way a
stale card is refused rather than shown, and an `EmergencyCard` row records every render —
the audit of who was handed the card, and the offline story: the app caches the last render.

Every sentence comes from `app.channels.safety_strings` and is verified. Three things do not
go through a sentence, because the standard forbids them there and the stranger needs them:
the chief's phone number, the medicine's strength and the insurer's policy reference, carried
beside the lines as data.

Two languages on one card: the lines in his language, and — when that is not English — the
same lines again in English (`english_lines`), line for line, so the ambulance crew and the
hospital desk can read what he reads. The printable page prints each English line under its
twin.
Public share: none. There is no link to this card without a key.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_projection_read, audited_read
from app.audit.models import Action
from app.channels.safety_strings import (
    BLOOD_GROUP_WORDS,
    CONDITION_WORDS,
    LANGUAGE_NAMES,
    WHEN_WORDS,
    NotPlainWords,
    language_of,
    phrase,
    render,
)
from app.db import as_utc, utcnow
from app.delivery.strings import theirs
from app.drugs.registry import DrugRegistry
from app.identity.models import Person
from app.insurance.insurer import Insurer
from app.keys.context import KeyContext
from app.keys.models import Key
from app.keys.scopes import KeyRole, Scope
from app.medicines.dose import Dose
from app.medicines.models import LineStatus, MedicationLine
from app.medicines.strings import PLAIN_NAME, say_amount
from app.memory.episodic import fact_cites_only_what_is_held_here
from app.memory.models import ConfidenceState, Event, EventKind, Fact, Provider, ProviderKind
from app.regions import REGION_TZ, Region
from app.safety.high_risk import high_risk_class, is_high_risk
from app.safety.models import CardFormat, EmergencyCard
from app.safety.people import key_holder
from app.state.dimensions import ALLERGY, CONTROL, dimension_of
from app.state.models import Dimension
from app.state.service import (
    RECOMPUTE_SCOPES,
    current_state,
    render_from_last_snapshot,
    render_from_state,
)

EMERGENCY_SCOPE = Scope.EMERGENCY
CARD_TARGET = EmergencyCard.__tablename__

EMERGENCY_NUMBER: dict[Region, str] = {Region.SG: "995", Region.MY: "999"}
"""The ambulance, by region: 995 in Singapore, 999 in Malaysia."""

BLOOD_TYPE = "blood_type"
"""The subject a blood-type fact is written under; attribute `group`, value "O+"."""

PERSON = "person"
"""The subject his birth year is written under; attribute `birth_year`, value 1952."""

PROVIDER_ORDER = (ProviderKind.DOCTOR, ProviderKind.CLINIC, ProviderKind.HOSPITAL)

BLOOD_PRESSURE_LABEL = "blood pressure"
"""The label a blood-pressure READING event carries (`app.channels.api.profiles`). The card's
last-reading line is about his blood pressure and nothing else."""

READING_HORIZON = timedelta(days=365)
"""A reading older than this is not "last written down" on a card that says no year."""

log = logging.getLogger("nura.safety")


@dataclass(frozen=True, slots=True)
class Line:
    """One verified sentence on the card and the template it came from."""

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class Condition:
    code: str
    words: str
    fact_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class Allergy:
    code: str
    words: str
    fact_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class Medicine:
    """One active line as the card shows it. `strength` and `generic` are the register's
    words, data for the stranger; `plain_name`, `amount` and `when` are his."""

    line_id: uuid.UUID
    fact_id: uuid.UUID
    generic: str
    brand: str | None
    strength: str
    form: str
    plain_name: str
    amount: str
    when: str
    high_risk: bool
    high_risk_class: str | None


@dataclass(frozen=True, slots=True)
class Contact:
    """The chief: name and number, as data. The sentence beside it says to call first."""

    person_id: uuid.UUID
    name: str
    phone_e164: str | None
    role: str


@dataclass(frozen=True, slots=True)
class Clinic:
    provider_id: uuid.UUID
    name: str
    kind: str
    phone_e164: str | None


@dataclass(frozen=True, slots=True)
class InsurerOnCard:
    """Who insures him: the name, said in a sentence, and the policy reference, as data."""

    name: str
    policy_reference: str | None


@dataclass(frozen=True, slots=True)
class Card:
    """The emergency card as one value: the data and the verified lines, and the row."""

    card_id: uuid.UUID
    profile_id: uuid.UUID
    state_id: uuid.UUID
    rendered_at: datetime
    name: str
    language: str
    spoken_language: str
    age_band: str | None
    conditions: list[Condition]
    medicines: list[Medicine]
    allergies: list[Allergy]
    blood_type: str | None
    high_risk: list[str]
    contacts: list[Contact]
    clinic: Clinic | None
    last_reading_at: datetime | None
    emergency_number: str
    lines: list[Line]
    fact_ids: list[uuid.UUID] = field(default_factory=list)
    insurer: InsurerOnCard | None = None
    english_lines: list[Line] = field(default_factory=list)
    """The same lines in English when his language is not English, for the ambulance crew;
    empty when it is."""

    @property
    def line_ids(self) -> list[str]:
        return [line.id for line in self.lines]


@dataclass(frozen=True, slots=True)
class Projection:
    """What EMERGENCY opens, read once under that scope."""

    control_facts: Sequence[Fact]
    allergy_facts: Sequence[Fact]
    blood_type: Fact | None
    birth_year: Fact | None
    lines: Sequence[MedicationLine]
    chiefs: Sequence[tuple[Key, Person]]
    clinic: Provider | None
    last_reading: Event | None
    insurer: Insurer | None = None

    def fact_ids(self) -> list[uuid.UUID]:
        ids = [fact.id for fact in (*self.control_facts, *self.allergy_facts)]
        ids.extend(fact.id for fact in (self.blood_type, self.birth_year) if fact is not None)
        ids.extend(line.fact_id for line in self.lines)
        return sorted(set(ids), key=str)


def _asserted(fact: Fact) -> datetime:
    return as_utc(fact.asserted_at)


async def _projection(session: AsyncSession, *, context: KeyContext) -> Projection:
    moment = utcnow()
    facts = await audited_read(
        session,
        Fact,
        context,
        EMERGENCY_SCOPE,
        where=(
            Fact.superseded_at.is_(None),
            Fact.confidence_state != ConfidenceState.DISPUTED,
            Fact.valid_from <= moment,
            or_(Fact.valid_to.is_(None), Fact.valid_to > moment),
            or_(
                Fact.attribute.in_((CONTROL, ALLERGY)),
                Fact.subject.in_((BLOOD_TYPE, PERSON)),
            ),
            fact_cites_only_what_is_held_here(context, EMERGENCY_SCOPE),
        ),
    )
    control = sorted(
        (
            fact
            for fact in facts
            if fact.attribute == CONTROL and dimension_of(fact.subject) is Dimension.CLINICAL
        ),
        key=lambda fact: (fact.subject, as_utc(fact.asserted_at)),
    )
    allergies = sorted(
        (fact for fact in facts if fact.attribute == ALLERGY),
        key=lambda fact: (fact.subject, as_utc(fact.asserted_at)),
    )
    blood = [f for f in facts if f.subject == BLOOD_TYPE and f.attribute == "group"]
    born = [f for f in facts if f.subject == PERSON and f.attribute == "birth_year"]
    lines = await audited_read(
        session,
        MedicationLine,
        context,
        EMERGENCY_SCOPE,
        where=(
            MedicationLine.superseded_at.is_(None),
            MedicationLine.status == LineStatus.ACTIVE,
        ),
    )
    keys = await audited_read(
        session, Key, context, EMERGENCY_SCOPE, where=(Key.role == KeyRole.CHIEF,)
    )
    chiefs: list[tuple[Key, Person]] = []
    for key in sorted(keys, key=lambda one: as_utc(one.granted_at)):
        if not key.is_active(moment):
            continue
        # The chief's name and number are what the card is for (ADR 0002). The Key row was
        # read under EMERGENCY above; the account it names is read under the same scope,
        # with its own READ line, for a name and a number and nothing else.
        person = await key_holder(session, context, key.holder_person_id, scope=EMERGENCY_SCOPE)
        if person is not None:
            chiefs.append((key, person))
    providers = await audited_read(session, Provider, context, EMERGENCY_SCOPE)
    clinic = None
    for kind in PROVIDER_ORDER:
        of_kind = [one for one in providers if one.kind is kind]
        if of_kind:
            clinic = max(of_kind, key=lambda one: as_utc(one.added_at))
            break
    # The moment a reading was taken is written under the readings' part (row scope); the
    # card's projection names its date, so it is read through the projection's own door.
    readings = await audited_projection_read(
        session,
        Event,
        context,
        EMERGENCY_SCOPE,
        where=(
            Event.kind == EventKind.READING,
            Event.label == BLOOD_PRESSURE_LABEL,
            Event.occurred_at > moment - READING_HORIZON,
        ),
        # `.seq` breaks a tie in `occurred_at` (#192/#218): which reading is "the" latest
        # one on the card is a decision, not a display order.
        order_by=(Event.occurred_at.desc(), Event.seq.desc()),
        limit=1,
    )
    # His insurer, as typed on a yes: the newest row in force, under the same scope.
    typed = await audited_read(session, Insurer, context, EMERGENCY_SCOPE)
    insurer = max(typed, key=lambda row: (as_utc(row.set_at), str(row.id)), default=None)
    return Projection(
        insurer=None if insurer is None or insurer.name is None else insurer,
        control_facts=control,
        allergy_facts=allergies,
        blood_type=max(blood, key=_asserted, default=None),
        birth_year=max(born, key=_asserted, default=None),
        lines=sorted(lines, key=lambda line: (as_utc(line.started_at), line.generic)),
        chiefs=chiefs,
        clinic=clinic,
        last_reading=readings[0] if readings else None,
    )


def masked(reference: str | None) -> str | None:
    """A policy reference as a key that is not his or his chief's reads it: the last four
    letters or digits, the rest hidden ("••••0932")."""
    if reference is None:
        return None
    kept = "".join(ch for ch in reference if ch.isalnum())[-4:]
    return f"••••{kept}"


def age_band(birth_year: int, today_year: int) -> str | None:
    """ "70 to 79": the decade, never the year. A band is enough for a stranger."""
    age = today_year - birth_year
    if age < 0 or age > 120:
        return None
    low = (age // 10) * 10
    return f"{low} to {low + 9}"


def _plain_medicine(registry: DrugRegistry, line: MedicationLine, language: str) -> str:
    """His name for the medicine — "the water pill" — with the register's name small beside
    it in English ("the water pill (frusemide)"), as the standard allows. In Malay and
    Chinese the sentence carries his name only: the generic is in the table beside it."""
    try:
        plain = PLAIN_NAME[language][registry.monograph(line.generic).plain_name_id]
    except Exception:  # noqa: BLE001 — a generic the register has no story for keeps its name
        return line.generic.title()
    return f"{plain} ({line.generic})" if language == "en" else plain


def _medicines(
    registry: DrugRegistry, lines: Sequence[MedicationLine], language: str
) -> list[Medicine]:
    shown: list[Medicine] = []
    for line in lines:
        dose = Dose.from_json(line.dose)
        danger = high_risk_class(line.generic) or (
            line.drug_class.lower() if is_high_risk(line.drug_class) else None
        )
        shown.append(
            Medicine(
                line_id=line.id,
                fact_id=line.fact_id,
                generic=line.generic,
                brand=line.brand,
                strength=line.strength,
                form=line.form,
                plain_name=_plain_medicine(registry, line, language),
                amount=say_amount(dose.amount, dose.unit, language),
                when=phrase(WHEN_WORDS, language, dose.frequency.value),
                high_risk=bool(line.high_risk or danger),
                high_risk_class=danger or ("high_risk" if line.high_risk else None),
            )
        )
    return shown


def compose_lines(
    *,
    name: str,
    language: str,
    spoken_language: str,
    age: str | None,
    conditions: Sequence[Condition],
    medicines: Sequence[Medicine],
    allergies: Sequence[Allergy],
    blood_type: str | None,
    contacts: Sequence[Contact],
    clinic: Clinic | None,
    last_reading_at: datetime | None,
    region: Region,
    insurer: str | None = None,
) -> list[Line]:
    """The card as sentences, in order, every one through `render` and so verified."""
    lang = language_of(language)
    zone = REGION_TZ[region]
    lines: list[Line] = []

    def say(template_id: str, **slots: Any) -> None:
        """One line, or none: a line that fails the standard is withheld and logged, so the
        card a stranger is holding is never taken away whole for one bad template."""
        try:
            lines.append(Line(template_id, render(template_id, lang, **slots)))
        except NotPlainWords as failed:
            log.warning("emergency card line withheld: %s", failed)

    say("ec.title", name=name)
    say("ec.show")
    say("ec.language", name=name, speaks=phrase(LANGUAGE_NAMES, lang, spoken_language))
    if age is not None:
        say("ec.age", name=name, band=age)
    if conditions:
        for condition in conditions:
            say("ec.condition", name=name, condition=condition.words)
    else:
        say("ec.no_condition", name=name)
    if medicines:
        for medicine in medicines:
            # His words for a medicine carry his possessive; on his card it is said about him.
            say("ec.medicine", name=name, medicine=theirs(medicine.plain_name, name, lang))
            say("ec.medicine_when", name=name, amount=medicine.amount, when=medicine.when)
            if medicine.high_risk:
                # The same name as the line above it, so the two are one tablet to him.
                say("ec.high_risk", name=name, medicine=theirs(medicine.plain_name, name, lang))
    else:
        say("ec.no_medicine", name=name)
    if allergies:
        for allergy in allergies:
            say("ec.allergy", name=name, thing=allergy.words)
    else:
        say("ec.no_allergy", name=name)
    if blood_type is not None:
        say("ec.blood_type", name=name, group=phrase(BLOOD_GROUP_WORDS, lang, blood_type))
    if contacts:
        # A stranger holding the card does not know who Mei is: say it, then say to call her.
        say("ec.chief_who", chief=contacts[0].name, name=name)
        say("ec.chief", chief=contacts[0].name)
    else:
        say("ec.no_chief")
    if clinic is not None:
        if clinic.kind == ProviderKind.DOCTOR.value:
            say("ec.doctor", name=name, doctor=clinic.name)
        else:
            say("ec.clinic", name=name, clinic=clinic.name)
    if insurer is not None:
        say("ec.insurer", name=name, insurer=insurer)
    say("ec.ambulance", number=EMERGENCY_NUMBER[region])
    if last_reading_at is not None:
        say("ec.last_reading", name=name, date=as_utc(last_reading_at).astimezone(zone).date())
    say("ec.boundary")
    return lines


@audited(Action.READ, EMERGENCY_SCOPE, CARD_TARGET)
async def emergency_card(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    language: str | None = None,
    format: CardFormat = CardFormat.JSON,
) -> Card:
    """The card, rendered now from State for whoever holds EMERGENCY, and written down.

    In `language`, or the profile's own. A key that can recompute State has the record
    checked against the snapshot first; an emergency-only key has the snapshot checked
    against the facts the card shows. Both refuse a stale card.
    """
    profile = await audited_profile_read(session, context)
    lang = language_of(language or profile.language)
    held = await _projection(session, context=context)
    zone = REGION_TZ[context.region]
    today = utcnow().astimezone(zone).date()

    def conditions_in(code: str) -> list[Condition]:
        return [
            Condition(
                code=fact.subject,
                words=phrase(CONDITION_WORDS, code, fact.subject),
                fact_id=fact.id,
            )
            for fact in held.control_facts
        ]

    conditions = conditions_in(lang)
    allergies = [
        # An allergen is a name — "Penicillin" — and is said as one: the standard leaves
        # names alone, and a stranger needs the exact word.
        Allergy(code=fact.subject, words=fact.subject.replace("_", " ").title(), fact_id=fact.id)
        for fact in held.allergy_facts
    ]
    blood_type = (
        str(held.blood_type.value)
        if held.blood_type is not None and isinstance(held.blood_type.value, str)
        else None
    )
    age = None
    if held.birth_year is not None and isinstance(held.birth_year.value, int):
        age = age_band(held.birth_year.value, today.year)
    medicines = _medicines(registry, held.lines, lang)
    contacts = [
        Contact(
            person_id=person.id,
            name=person.display_name,
            phone_e164=person.phone_e164,
            role=key.role.value,
        )
        for key, person in held.chiefs
    ]
    clinic = (
        None
        if held.clinic is None
        else Clinic(
            provider_id=held.clinic.id,
            name=held.clinic.name,
            kind=held.clinic.kind.value,
            phone_e164=held.clinic.phone_e164,
        )
    )
    last_reading_at = None if held.last_reading is None else as_utc(held.last_reading.occurred_at)
    # The policy reference in full for him, the steward and his chief — the card he prints and
    # carries; the last four for everyone else holding the emergency card (B1 review).
    reveal = context.is_owner or context.is_steward or context.role is KeyRole.CHIEF
    insurer = (
        None
        if held.insurer is None or held.insurer.name is None
        else InsurerOnCard(
            name=held.insurer.name,
            policy_reference=(
                held.insurer.policy_reference
                if reveal
                else masked(held.insurer.policy_reference)
            ),
        )
    )

    def lines_in(code: str) -> list[Line]:
        """The card's sentences in one language, from the same data."""
        return compose_lines(
            name=profile.display_name,
            language=code,
            spoken_language=profile.language,
            age=age,
            conditions=conditions if code == lang else conditions_in(code),
            medicines=medicines if code == lang else _medicines(registry, held.lines, code),
            allergies=allergies,
            blood_type=blood_type,
            contacts=contacts,
            clinic=clinic,
            last_reading_at=last_reading_at,
            region=context.region,
            insurer=None if insurer is None else insurer.name,
        )

    lines = lines_in(lang)
    # His language and English, on one card (E13-01): the crew reads the English twin.
    english_lines = [] if lang == "en" else lines_in("en")
    fact_ids = held.fact_ids()
    values: dict[str, Any] = {
        "format": format,
        "language": lang,
        "fact_ids": [str(one) for one in fact_ids],
        "line_ids": [line.id for line in lines],
        "rendered_at": utcnow(),
        "rendered_for_person_id": context.person_id,
    }
    if RECOMPUTE_SCOPES <= context.scopes:
        state = await current_state(session, context=context)
        row = await render_from_state(
            session, EmergencyCard, context, EMERGENCY_SCOPE, state=state, **values
        )
    else:
        row = await render_from_last_snapshot(
            session, EmergencyCard, context, EMERGENCY_SCOPE, covering=fact_ids, **values
        )
    return Card(
        card_id=row.id,
        profile_id=context.profile_id,
        state_id=row.state_id,
        rendered_at=as_utc(row.rendered_at),
        name=profile.display_name,
        language=lang,
        spoken_language=profile.language,
        age_band=age,
        conditions=conditions,
        medicines=medicines,
        allergies=allergies,
        blood_type=blood_type,
        high_risk=sorted({m.high_risk_class for m in medicines if m.high_risk_class}),
        contacts=contacts,
        clinic=clinic,
        last_reading_at=last_reading_at,
        emergency_number=EMERGENCY_NUMBER[context.region],
        lines=lines,
        fact_ids=fact_ids,
        insurer=insurer,
        english_lines=english_lines,
    )
