"""The not-feeling-well flow (E13-02): one button, three steps, the family told.

    Voice-captures what is wrong, checks his recent readings and medicines, tells him what
    to do now (rest / call clinic / go now) and tells Ash. Turns fear into a plan. The most
    valuable single button in the product.

What happens, in order, and the order is the point:

1. **Capture.** His words are kept as an artefact — the voice note, or the text he typed —
   before anything is read from them, when the key holds the record. A voice note is handed
   only to a transcriber in the profile's region, and a voice note of him pressed by someone
   else rests on the RECORDING consent.
2. **Hear.** A voice note goes through the `Transcriber` port; typed words are heard as
   typed. Nothing heard is still a press of the button: the family is told and he is asked
   to say it again.
3. **Red flags first.** The words are read against `app.safety.red_flags`. A flag is written
   down (`write_flag_kept`) before the event, the fact and the card — and kept: if anything
   later in the same request is refused, the flag and the notices land anyway. Every key
   holder with the EMERGENCY scope (the roster, when E12 lands) gets a `Notice` to be
   delivered by E11/E19. This whole step runs under `Scope.EMERGENCY`, which every role
   holds, so a helper or a caregiver pressing the button for him escalates exactly as he
   would (docs/00-MASTER-BUILD-SPEC.md §8: red flags escalate immediately).
4. **State.** When the key holds the record, the moment becomes a SYMPTOM event and a
   `symptom.reported` fact resting on the artefact, and a `feeling.control` fact — `act`
   for a red flag, `watch` otherwise, for the next 24 hours — which is how the safety layer
   sets the day's posture: through a fact State folds in, never by writing a snapshot itself.
5. **The card.** One row of a fixed decision table (`DECISION_TABLE`), every line from
   `app.channels.safety_strings` and verified as an action. A key that can compute State
   (the owner, the chief) has the card rendered from the State those facts produced and
   written down as a `WhatToDoCard`; a narrower key gets the same lines to show him and no
   card row, since nothing rendered is stored without the State it came from.

The boundary holds throughout. No line says what is wrong with him; no line tells him to
start, stop or change a medicine — a medicine nobody tapped Taken on gets "Nura has no note
that you took the water pill today. Ask Dr Tan before you take the water pill.", never an
amount; a red flag gets "Mei knows already. Call the ambulance now on 995. After that, call Mei." and
nothing about what it might mean. Nothing tells him to drink. The check-in two hours on is a
question, not a judgement.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read, audited_write
from app.audit.models import Action
from app.channels.safety_strings import (
    SYMPTOM_WORDS,
    YOUR_DOCTOR,
    YOUR_MEDICINE,
    language_of,
    phrase,
    render,
)
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.drafts import FactDraft
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.identity.models import Person, Profile
from app.ingestion.objects import ObjectStore
from app.ingestion.voice import store_voice, store_words
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.models import Key
from app.keys.scopes import KeyRole, Scope
from app.medicines.dose import Anchor
from app.medicines.models import LineStatus, MedicationLine
from app.medicines.service import Slot, today
from app.medicines.strings import PLAIN_NAME
from app.memory.episodic import record_event
from app.memory.models import Artifact, ConfidenceState, Event, EventKind, Fact, SourceChannel
from app.memory.semantic import assert_fact
from app.regions import REGION_TZ, Region, guard_region
from app.safety.emergency_card import EMERGENCY_NUMBER
from app.safety.models import Flag, Notice, NoticeKind, WhatToDoCard, WhatToDoKind
from app.safety.people import key_holder, owner_of
from app.safety.red_flags import (
    FLAG_SCOPE,
    Heard,
    RedFlag,
    is_sugar_medicine,
    keep_row,
    match_red_flags,
    write_flag_kept,
)
from app.safety.symptoms import Parsed, Symptom, parse_symptoms
from app.safety.transcribe import NOTHING_HEARD, Transcriber, Transcript, check_voice_note
from app.state.models import Posture
from app.state.service import RECOMPUTE_SCOPES, StateView, current_state, render_from_state

SYMPTOM = "symptom"
"""The subject his words about how he feels are written under; attribute `reported`."""

REPORTED = "reported"

FEELING = "feeling"
"""The subject the day's posture is set through (`app.state.dimensions` folds it into the
situational dimension); attribute `control`, value a posture word."""

CONTROL = "control"

BUTTON_SCOPE = Scope.EMERGENCY
"""The door on the button: the scope every role holds, so anyone with him can press it."""

NOTICE_SCOPE = Scope.EMERGENCY
"""Notices are written under the same door: telling the family is the emergency act."""

FLAG_TARGET = Flag.__tablename__
NOTICE_TARGET = Notice.__tablename__
CARD_TARGET = WhatToDoCard.__tablename__

POSTURE_WINDOW = timedelta(hours=24)
"""How long a press of the button holds the day's posture. The fact stays on record after."""

SYMPTOM_WINDOW = timedelta(days=7)
"""How long a reported symptom is a current fact: the week the pre-visit brief looks back on."""

CHECK_IN_AFTER = timedelta(hours=2)

ANCHOR_HOURS: dict[Anchor, int] = {
    Anchor.BREAKFAST: 9,
    Anchor.LUNCH: 14,
    Anchor.DINNER: 20,
    Anchor.BED: 22,
}
"""The hour of his day after which a dose at that anchor counts as not tapped yet."""

NOT_FEELING_WELL_LABEL = "not feeling well"


class NothingSaid(Refusal):
    """The button was pressed with neither a voice note nor typed words."""


class SaidTwice(Refusal):
    """A voice note and typed words in one press: one of the two, not both."""


@dataclass(frozen=True, slots=True)
class Line:
    id: str
    text: str


@dataclass(frozen=True, slots=True)
class Captured:
    """What was kept and heard: the artefact (None when the key cannot keep one), the
    transcript, how it came in."""

    artifact: Artifact | None
    transcript: Transcript
    by_voice: bool

    @property
    def text(self) -> str:
        return self.transcript.text

    @property
    def heard(self) -> bool:
        return self.transcript.heard


@dataclass(frozen=True, slots=True)
class Family:
    """Who is told: the chief (first, by name on the card) and everyone with EMERGENCY."""

    chief: Person | None
    to_tell: list[Person]


@dataclass(frozen=True, slots=True)
class Escalated:
    """What the red-flag path wrote before anything else."""

    flags: list[Flag]
    notices: list[Notice]

    @property
    def first(self) -> Flag | None:
        return self.flags[0] if self.flags else None


@dataclass(frozen=True, slots=True)
class Situation:
    """What the decision table reads: a red flag or not, a dose not taken, who there is."""

    red_flag: bool
    heard: bool
    missed: Slot | None
    chief: Person | None
    others_told: bool
    region: Region


@dataclass(frozen=True, slots=True)
class Decision:
    kind: WhatToDoKind
    line_ids: tuple[str, ...]
    check_in: bool


@dataclass(frozen=True, slots=True)
class WhatToDoNow:
    """The answer to the button: the card, and everything written on the way to it.

    `card_id` and `state_id` are None when the key could not compute State and so no card
    row was written; `event_id` and `fact_id` are None when the key holds no record to
    write the moment into. The lines are always there, and so is the flag when one was heard.
    """

    kind: WhatToDoKind
    posture: Posture | None
    language: str
    lines: list[Line]
    heard: bool
    by_voice: bool
    transcript_confidence: float
    red_flags: list[RedFlag]
    suppressed: list[RedFlag]
    symptoms: list[Symptom]
    flag_id: uuid.UUID | None
    notified_person_ids: list[uuid.UUID]
    check_in_at: datetime | None
    card_id: uuid.UUID | None = None
    state_id: uuid.UUID | None = None
    artifact_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    fact_id: uuid.UUID | None = None
    missed_medicine: str | None = None
    notices: list[Notice] = field(default_factory=list)


# --- the decision table -------------------------------------------------------------------


def _red_flag_lines(s: Situation) -> tuple[str, ...]:
    """The chief knows already, call the ambulance now, after that call the chief: one order,
    the reassurance first, and nothing that contradicts the notice she was sent."""
    number = EMERGENCY_NUMBER[s.region]
    if s.chief is None:
        lines: tuple[str, ...] = (f"nfw.call_{number}",)
        if s.others_told:
            lines += ("nfw.family_knows",)
        return lines
    return ("nfw.chief_knows", f"nfw.call_{number}", "nfw.then_call_chief")


def _not_heard(s: Situation) -> tuple[str, ...]:
    """When nothing was heard the card says so first, whichever row it is: he pressed the
    button, and a card that pretends to have understood him would be the wrong card."""
    return () if s.heard else ("nfw.not_heard", "nfw.say_again", "nfw.type_instead")


def _missed_dose_lines(s: Situation) -> tuple[str, ...]:
    lines: tuple[str, ...] = _not_heard(s) + ("nfw.not_taken", "nfw.ask_before", "nfw.rest")
    lines += ("nfw.will_call",) if s.chief is not None else ()
    return lines + ("nfw.check_in",)


def _rest_lines(s: Situation) -> tuple[str, ...]:
    lines: tuple[str, ...] = _not_heard(s) + ("nfw.rest",)
    lines += ("nfw.will_call",) if s.chief is not None else ()
    return lines + ("nfw.check_in",)


Row = tuple[WhatToDoKind, Callable[[Situation], bool], Callable[[Situation], tuple[str, ...]], bool]

DECISION_TABLE: tuple[Row, ...] = (
    (WhatToDoKind.RED_FLAG, lambda s: s.red_flag, _red_flag_lines, False),
    (WhatToDoKind.MISSED_DOSE, lambda s: s.missed is not None, _missed_dose_lines, True),
    (WhatToDoKind.REST, lambda s: True, _rest_lines, True),
)
"""The whole of what the button can say, top row wins. (kind, applies, lines, check-in.)

Red flag: the chief knows already, call the ambulance now, after that call the chief.
A dose nobody tapped Taken on: Nura has no note you took it, ask the doctor before you take
it, rest, the chief will call today, a check-in in two hours. Otherwise: rest, the chief will
call today, a check-in in two hours. Nothing else exists, and nothing says what is wrong.
"""


def decide(situation: Situation) -> Decision:
    for kind, applies, lines, check_in in DECISION_TABLE:
        if applies(situation):
            return Decision(kind=kind, line_ids=lines(situation), check_in=check_in)
    raise AssertionError("the last row of the decision table applies to everything")


# --- the steps ----------------------------------------------------------------------------


async def capture(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    transcriber: Transcriber,
    language: str,
    words: str | None,
    audio: bytes | None,
    content_type: str | None,
    source_channel: SourceChannel = SourceChannel.APP,
) -> Captured:
    """Step 1 and 2: keep what he said, then hear it. Exactly one of voice or words.

    The artefact is written when the key holds the record; a key that does not (a helper's)
    still has the words heard, in memory, so the flag can be raised — the words themselves
    are then not kept, and the flag names no artefact. A voice note is handed to the
    transcriber only if the transcriber is in the profile's region, and only on the RECORDING
    consent when the person pressing is not the person recorded.
    """
    if audio is not None and words is not None:
        raise SaidTwice("a voice note or typed words, not both")
    moment = utcnow()
    can_keep = context.allows(Scope.RECORDS)
    if audio is not None:
        kind = check_voice_note(audio, content_type or "")
        guard_region(held_in=context.region, asked_from=transcriber.region)
        if not context.is_owner:
            # His voice, recorded by someone else: the recording consent, not the record's.
            await require_consent(
                session,
                context=context,
                purpose=ConsentPurpose.RECORDING,
                scope=BUTTON_SCOPE,
            )
        artifact = (
            await store_voice(
                session,
                context=context,
                store=store,
                data=audio,
                content_type=kind,
                captured_at=moment,
                source_channel=source_channel,
            )
            if can_keep
            else None
        )
        transcript = await transcriber.transcribe(audio, kind, language, context.region)
        return Captured(artifact=artifact, transcript=transcript or NOTHING_HEARD, by_voice=True)
    if words is not None:
        if not words.strip():
            raise NothingSaid("say it or type it")
        artifact = (
            await store_words(
                session,
                context=context,
                store=store,
                text=words,
                captured_at=moment,
                source_channel=source_channel,
            )
            if can_keep
            else None
        )
        return Captured(
            artifact=artifact,
            transcript=Transcript(text=words.strip(), confidence=1.0, language=language),
            by_voice=False,
        )
    raise NothingSaid("say it or type it")


async def sugar_medicine(
    session: AsyncSession, *, context: KeyContext
) -> tuple[bool | None, Sequence[MedicationLine]]:
    """Whether he is on a sugar medicine: True, False, or None when the medicines are not
    known — because none is on record, or because this key does not open them."""
    if not context.allows(Scope.MEDICINES):
        return None, ()
    lines = await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(
            MedicationLine.superseded_at.is_(None),
            MedicationLine.status == LineStatus.ACTIVE,
        ),
    )
    if not lines:
        return None, lines
    return any(is_sugar_medicine(line.drug_class) for line in lines), lines


async def family_of(
    session: AsyncSession, *, context: KeyContext, profile: Profile
) -> Family:
    """Who is told: every active key holder with EMERGENCY, the chief named first.

    Read under EMERGENCY, not FAMILY: who the patient let in to his emergency card is part
    of the emergency card (ADR 0002), and a caregiver or a helper pressing the button holds
    no FAMILY key. The roster (E12) will decide who is on duty; until it lands, everyone the
    patient let in to his emergency card is the roster. The person pressing is not told.
    """
    moment = utcnow()
    keys = await audited_read(session, Key, context, BUTTON_SCOPE)
    chief: Person | None = None
    to_tell: list[Person] = []
    for key in sorted(keys, key=lambda one: (as_utc(one.granted_at), str(one.id))):
        if not key.is_active(moment) or Scope.EMERGENCY not in key.scopes_held:
            continue
        if key.holder_person_id == context.person_id:
            continue
        if any(one.id == key.holder_person_id for one in to_tell):
            continue
        person = await key_holder(session, context, key.holder_person_id, scope=BUTTON_SCOPE)
        if person is None:
            continue
        to_tell.append(person)
        if chief is None and key.role is KeyRole.CHIEF:
            chief = person
    return Family(chief=chief, to_tell=to_tell)


def _words_code(heard: Heard, parsed: Parsed) -> str | None:
    """The code the notice quotes: the first red flag, else the first symptom, else nothing."""
    if heard.flags:
        return heard.flags[0].value
    if parsed.symptoms:
        return parsed.symptoms[0].value
    return None


async def escalate(
    session: AsyncSession,
    *,
    context: KeyContext,
    captured: Captured,
    heard: Heard,
    parsed: Parsed,
    family: Family,
) -> Escalated:
    """Step 3, when a red flag was heard: the flags, then a notice to each person.

    Written before the event, the fact and the card, and kept (`write_flag_kept`, `keep_row`)
    so a refusal further on cannot take them back. The notice is a template id and codes:
    "{patient} is not feeling well. Nura heard this: chest pain. Call {patient} now. This one
    we do not wait for." — the words quoted are the table's words for the code, in the
    reader's language, never the transcript.
    """
    moment = utcnow()
    flags: list[Flag] = []
    for code in heard.flags:
        flags.append(
            await write_flag_kept(
                session,
                context,
                code=code.value,
                posture=Posture.ACT,
                artifact=captured.artifact,
                suppressed=[one.value for one in heard.suppressed],
            )
        )
    first = flags[0] if flags else None
    notices: list[Notice] = []
    for person in family.to_tell:
        notice = await _notice(
            session,
            context=context,
            to=person,
            kind=NoticeKind.FAMILY_ALERT,
            template="family_alert.red_flag",
            slots={"words": _words_code(heard, parsed), "heard": captured.heard},
            flag_id=None if first is None else first.id,
            deliver_after=moment,
        )
        keep_row(session, context, notice, scope=NOTICE_SCOPE)
        notices.append(notice)
    return Escalated(flags=flags, notices=notices)


async def tell_family(
    session: AsyncSession,
    *,
    context: KeyContext,
    captured: Captured,
    heard: Heard,
    parsed: Parsed,
    family: Family,
    missed: str | None,
) -> list[Notice]:
    """The ordinary path's notice: he is not feeling well, this is what Nura heard, call today."""
    moment = utcnow()
    return [
        await _notice(
            session,
            context=context,
            to=person,
            kind=NoticeKind.FAMILY_ALERT,
            template="family_alert.not_well",
            slots={"words": _words_code(heard, parsed), "heard": captured.heard, "missed": missed},
            flag_id=None,
            deliver_after=moment,
        )
        for person in family.to_tell
    ]


async def _notice(
    session: AsyncSession,
    *,
    context: KeyContext,
    to: Person,
    kind: NoticeKind,
    template: str,
    slots: dict[str, object],
    flag_id: uuid.UUID | None,
    deliver_after: datetime,
    event_id: uuid.UUID | None = None,
) -> Notice:
    return await audited_write(
        session,
        Notice,
        context,
        NOTICE_SCOPE,
        kind=kind,
        to_person_id=to.id,
        template=template,
        slots={key: value for key, value in slots.items() if value is not None},
        language=language_of(to.language),
        flag_id=flag_id,
        event_id=event_id,
        created_at=utcnow(),
        deliver_after=deliver_after,
    )


def notice_lines(notice: Notice, *, patient: str, language: str | None = None) -> list[str]:
    """A notice as sentences, in the reader's language — for the channel that delivers it,
    and for the tests. Every line verified."""
    lang = language_of(language or notice.language)
    slots = notice.slots
    if notice.kind is NoticeKind.CHECK_IN:
        return [render("notice.check_in", lang)]
    lines = [render("notice.not_well", lang, patient=patient)]
    code = slots.get("words")
    if isinstance(code, str):
        lines.append(render("notice.heard", lang, words=phrase(SYMPTOM_WORDS, lang, code)))
    elif slots.get("heard") is False:
        lines.append(render("notice.not_heard", lang, patient=patient))
    if notice.template == "family_alert.red_flag":
        lines.append(render("notice.call_now", lang, patient=patient))
        lines.append(render("notice.do_not_wait", lang))
    else:
        missed = slots.get("missed")
        if isinstance(missed, str):
            lines.append(render("notice.not_taken", lang, patient=patient, medicine=missed))
        lines.append(render("notice.call_today", lang, patient=patient))
    return lines


async def write_the_moment(
    session: AsyncSession,
    *,
    context: KeyContext,
    captured: Captured,
    heard: Heard,
    parsed: Parsed,
    label: str,
    posture: Posture | None,
) -> tuple[Event, Fact]:
    """Step 4: the SYMPTOM event, the `symptom.reported` fact on the artefact and the event,
    and — when the button was pressed — the `feeling.control` fact that sets the posture.
    State recomputes as each fact lands. Needs the record: the caller checks."""
    moment = utcnow()
    artifact_id = None if captured.artifact is None else captured.artifact.id
    event = await record_event(
        session,
        context=context,
        kind=EventKind.SYMPTOM,
        occurred_at=moment,
        label=label,
        artifact_id=artifact_id,
        source_channel=None if artifact_id is not None else SourceChannel.APP,
    )
    # "Not well" is what is written when the button was pressed and nothing the tables know
    # was said — neither a symptom nor a red flag. A red flag is already the word for it.
    said_nothing_known = not parsed.symptoms and not heard.flags
    value = {
        "symptoms": [one.value for one in parsed.symptoms]
        or ([Symptom.NOT_WELL.value] if said_nothing_known and label == NOT_FEELING_WELL_LABEL else []),
        "red_flags": [one.value for one in heard.flags],
        "suppressed": [one.value for one in heard.suppressed],
        "severity": parsed.severity,
        "duration": None if parsed.duration is None else parsed.duration.value,
        "heard": captured.heard,
        "via": "voice" if captured.by_voice else "typed",
    }
    if captured.by_voice:
        fact = await assert_fact(
            session,
            context=context,
            subject=SYMPTOM,
            attribute=REPORTED,
            value=value,
            confidence=captured.transcript.confidence,
            confidence_state=ConfidenceState.EXTRACTED,
            artifact_id=artifact_id,
            event_id=event.id,
            valid_from=moment,
            valid_to=moment + SYMPTOM_WINDOW,
        )
    else:
        # Typed words are his own word: the yes is written and used in the same press, the
        # way the app's save button does, so a later extraction cannot overwrite them.
        draft = FactDraft(
            subject=SYMPTOM,
            attribute=REPORTED,
            value=value,
            unit=None,
            confidence=1.0,
            confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
            artifact_id=artifact_id,
            event_id=event.id,
            episode_id=None,
            supersedes_id=None,
        )
        yes = await confirm(session, context, draft)
        fact = await assert_fact(
            session,
            context=context,
            subject=SYMPTOM,
            attribute=REPORTED,
            value=value,
            confidence=1.0,
            confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
            confirmation_id=yes.id,
            artifact_id=artifact_id,
            event_id=event.id,
            valid_from=moment,
            valid_to=moment + SYMPTOM_WINDOW,
        )
    if posture is not None:
        await assert_fact(
            session,
            context=context,
            subject=FEELING,
            attribute=CONTROL,
            value=posture.value,
            confidence=1.0,
            confidence_state=ConfidenceState.EXTRACTED,
            event_id=event.id,
            valid_from=moment,
            valid_to=moment + POSTURE_WINDOW,
        )
    return event, fact


async def _missed_dose(
    session: AsyncSession, *, context: KeyContext, registry: DrugRegistry, language: str
) -> Slot | None:
    """The first dose of today whose hour has passed and that nobody tapped Taken on."""
    if not context.allows(Scope.MEDICINES):
        return None
    slots = await today(session, context=context, registry=registry, language=language)
    hour = utcnow().astimezone(REGION_TZ[context.region]).hour
    due = [
        slot for slot in slots if not slot.taken and hour >= ANCHOR_HOURS[Anchor(slot.anchor)]
    ]
    return due[0] if due else None


def _plain_name(registry: DrugRegistry, generic: str, language: str) -> str:
    try:
        return PLAIN_NAME[language][registry.monograph(generic).plain_name_id]
    except Exception:  # noqa: BLE001 — a generic the register has no story for keeps its name
        return YOUR_MEDICINE[language]


def compose(
    decision: Decision,
    *,
    language: str,
    chief: Person | None,
    missed_medicine: str | None,
    doctor: str | None,
) -> list[Line]:
    """The card's lines, filled and verified, in the table's order.

    The one who is asked before a dose is the doctor on the label first, then the chief,
    then "your doctor": a question about a medicine is rerouted to the doctor, not the family.
    """
    lang = language_of(language)
    who = doctor or (chief.display_name if chief is not None else YOUR_DOCTOR[lang])
    slots = {
        "chief": chief.display_name if chief is not None else "",
        "medicine": missed_medicine or YOUR_MEDICINE[lang],
        "who": who,
    }
    return [Line(line_id, render(line_id, lang, **slots)) for line_id in decision.line_ids]


@audited(Action.WRITE, BUTTON_SCOPE, CARD_TARGET)
async def not_feeling_well(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    transcriber: Transcriber,
    registry: DrugRegistry,
    words: str | None = None,
    audio: bytes | None = None,
    content_type: str | None = None,
    language: str | None = None,
) -> WhatToDoNow:
    """The button. See the module doc for the five steps and their order."""
    profile = await audited_profile_read(session, context)
    lang = language_of(language or profile.language)
    can_record = context.allows(Scope.RECORDS)

    captured = await capture(
        session,
        context=context,
        store=store,
        transcriber=transcriber,
        language=profile.language,
        words=words,
        audio=audio,
        content_type=content_type,
    )
    on_sugar, _lines = await sugar_medicine(session, context=context)
    heard = match_red_flags(captured.text, on_sugar_medicine=on_sugar)
    parsed = parse_symptoms(captured.text)
    family = await family_of(session, context=context, profile=profile)

    escalated: Escalated | None = None
    if heard.any:
        # Before the event, before the fact, before the card — and kept whatever follows.
        escalated = await escalate(
            session, context=context, captured=captured, heard=heard, parsed=parsed, family=family
        )

    missed = None if heard.any else await _missed_dose(
        session, context=context, registry=registry, language=lang
    )
    missed_name = None if missed is None else _plain_name(registry, missed.line.generic, lang)
    notices: list[Notice] = list(escalated.notices) if escalated is not None else []
    if escalated is None:
        notices = await tell_family(
            session,
            context=context,
            captured=captured,
            heard=heard,
            parsed=parsed,
            family=family,
            missed=missed_name,
        )

    event: Event | None = None
    fact: Fact | None = None
    if can_record:
        event, fact = await write_the_moment(
            session,
            context=context,
            captured=captured,
            heard=heard,
            parsed=parsed,
            label=NOT_FEELING_WELL_LABEL,
            posture=Posture.ACT if heard.any else Posture.WATCH,
        )

    situation = Situation(
        red_flag=heard.any,
        heard=captured.heard,
        missed=missed,
        chief=family.chief,
        others_told=bool(family.to_tell),
        region=context.region,
    )
    decision = decide(situation)
    lines = compose(
        decision,
        language=lang,
        chief=family.chief,
        missed_medicine=missed_name,
        doctor=None if missed is None else missed.line.prescriber,
    )

    check_in_at: datetime | None = None
    if decision.check_in:
        owner = await owner_of(session, context, profile)
        if owner is not None:
            check_in_at = utcnow() + CHECK_IN_AFTER
            notices.append(
                await _notice(
                    session,
                    context=context,
                    to=owner,
                    kind=NoticeKind.CHECK_IN,
                    template="check_in",
                    slots={},
                    flag_id=None,
                    deliver_after=check_in_at,
                    event_id=None if event is None else event.id,
                )
            )

    # Step 5: the card, from the State the facts above produced, for a key that can compute
    # it. `current_state` sees the recompute the hooks made and answers stale=False; a
    # snapshot the record has moved past would be refused here rather than shown. A key
    # that cannot compute State shows him the same lines and writes no card row.
    card: WhatToDoCard | None = None
    state: StateView | None = None
    if can_record and RECOMPUTE_SCOPES <= context.scopes and event is not None:
        state = await current_state(session, context=context)
        card = await render_from_state(
            session,
            WhatToDoCard,
            context,
            Scope.RECORDS,
            state=state,
            kind=decision.kind,
            language=lang,
            line_ids=[line.id for line in lines],
            flag_id=None if escalated is None or escalated.first is None else escalated.first.id,
            event_id=event.id,
            check_in_at=check_in_at,
            rendered_at=utcnow(),
            rendered_for_person_id=context.person_id,
        )
    posture: Posture | None
    if state is not None:
        posture = state.posture
    else:
        posture = Posture.ACT if heard.any else None
    return WhatToDoNow(
        card_id=None if card is None else card.id,
        state_id=None if card is None else card.state_id,
        kind=decision.kind,
        posture=posture,
        language=lang,
        lines=lines,
        artifact_id=None if captured.artifact is None else captured.artifact.id,
        event_id=None if event is None else event.id,
        fact_id=None if fact is None else fact.id,
        heard=captured.heard,
        by_voice=captured.by_voice,
        transcript_confidence=captured.transcript.confidence,
        red_flags=list(heard.flags),
        suppressed=list(heard.suppressed),
        symptoms=list(parsed.symptoms),
        flag_id=None if escalated is None or escalated.first is None else escalated.first.id,
        notified_person_ids=[
            n.to_person_id for n in notices if n.kind is NoticeKind.FAMILY_ALERT
        ],
        check_in_at=check_in_at,
        missed_medicine=missed_name,
        notices=notices,
    )


__all__ = [
    "ANCHOR_HOURS",
    "BUTTON_SCOPE",
    "DECISION_TABLE",
    "FLAG_SCOPE",
    "Captured",
    "Decision",
    "Escalated",
    "Family",
    "Line",
    "NothingSaid",
    "SaidTwice",
    "Situation",
    "WhatToDoNow",
    "capture",
    "decide",
    "escalate",
    "family_of",
    "not_feeling_well",
    "notice_lines",
    "sugar_medicine",
    "write_the_moment",
]
