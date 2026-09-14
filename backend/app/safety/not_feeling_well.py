"""The not-feeling-well flow (E13-02): one button, three steps, the family told.

    Voice-captures what is wrong, checks his recent readings and medicines, tells him what
    to do now (rest / call clinic / go to A&E) and tells Ash. Turns fear into a plan. The
    most valuable single button in the product.

What happens, in order, and the order is the point:

1. **Capture.** His words are kept as an artefact — the voice note, or the text he typed —
   before anything is read from them. The words live there and nowhere else.
2. **Hear.** A voice note goes through the `Transcriber` port; typed words are heard as
   typed. Nothing heard is still a press of the button: the family is told and he is asked
   to say it again.
3. **Red flags first.** The words are read against `app.safety.red_flags`. A flag is written
   down (`Flag`) before the event, the fact, the notices and the card — "this one we do not
   wait for" is a property of the write order, not of the ranking. Every key holder with the
   EMERGENCY scope (the roster, when E12 lands) gets a `Notice` to be delivered by E11/E19.
4. **State.** The moment becomes a SYMPTOM event and a `symptom.reported` fact resting on
   the artefact, and a `feeling.control` fact — `act` for a red flag, `watch` otherwise, for
   the next 24 hours — which is how the safety layer sets the day's posture: through a fact
   State folds in, never by writing a snapshot itself.
5. **The card.** One row of a fixed decision table (`DECISION_TABLE`), rendered from the
   State those facts produced, every line from `app.channels.safety_strings` and verified.

The boundary holds throughout. No line says what is wrong with him; no line tells him to
start, stop or change a medicine — a medicine he has not taken today gets "Ask Mei before
you take it", never an amount; a red flag gets "Call Mei now. Call 995 now." and nothing
about what it might mean. The check-in two hours on is a question, not a judgement.
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
from app.memory.models import Artifact, ConfidenceState, EventKind, SourceChannel
from app.memory.semantic import assert_fact
from app.regions import REGION_TZ, Region
from app.safety.emergency_card import EMERGENCY_NUMBER
from app.safety.models import Flag, FlagKind, Notice, NoticeKind, WhatToDoCard, WhatToDoKind
from app.safety.red_flags import Heard, RedFlag, is_sugar_medicine, match_red_flags
from app.safety.symptoms import Parsed, Symptom, parse_symptoms
from app.safety.transcribe import Transcriber, Transcript
from app.state.models import Posture
from app.state.service import current_state, render_from_state

SYMPTOM = "symptom"
"""The subject his words about how he feels are written under; attribute `reported`."""

REPORTED = "reported"

FEELING = "feeling"
"""The subject the day's posture is set through (`app.state.dimensions` folds it into the
situational dimension); attribute `control`, value a posture word."""

CONTROL = "control"

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
"""The hour of his day after which a dose at that anchor counts as not taken yet."""

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
    """What was kept and heard: the artefact, the transcript, how it came in."""

    artifact: Artifact
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
    """The answer to the button: the card, and everything written on the way to it."""

    card_id: uuid.UUID
    state_id: uuid.UUID
    kind: WhatToDoKind
    posture: Posture
    language: str
    lines: list[Line]
    artifact_id: uuid.UUID
    event_id: uuid.UUID
    fact_id: uuid.UUID
    heard: bool
    by_voice: bool
    transcript_confidence: float
    red_flags: list[RedFlag]
    suppressed: list[RedFlag]
    symptoms: list[Symptom]
    flag_id: uuid.UUID | None
    notified_person_ids: list[uuid.UUID]
    check_in_at: datetime | None
    missed_medicine: str | None = None
    notices: list[Notice] = field(default_factory=list)


# --- the decision table -------------------------------------------------------------------


def _red_flag_lines(s: Situation) -> tuple[str, ...]:
    number = EMERGENCY_NUMBER[s.region]
    if s.chief is None:
        lines: tuple[str, ...] = (f"nfw.call_{number}",)
        if s.others_told:
            lines += ("nfw.family_knows",)
        return lines
    return ("nfw.call_chief", f"nfw.call_{number}", "nfw.chief_knows")


def _not_heard(s: Situation) -> tuple[str, ...]:
    """When nothing was heard the card says so first, whichever row it is: he pressed the
    button, and a card that pretends to have understood him would be the wrong card."""
    return () if s.heard else ("nfw.not_heard", "nfw.say_again")


def _missed_dose_lines(s: Situation) -> tuple[str, ...]:
    lines: tuple[str, ...] = _not_heard(s) + ("nfw.not_taken", "nfw.ask_before", "nfw.rest")
    lines += ("nfw.will_call",) if s.chief is not None else ()
    return lines + ("nfw.check_in",)


def _rest_lines(s: Situation) -> tuple[str, ...]:
    lines: tuple[str, ...] = _not_heard(s) + ("nfw.rest", "nfw.water")
    lines += ("nfw.will_call",) if s.chief is not None else ()
    return lines + ("nfw.check_in",)


DECISION_TABLE: tuple[tuple[WhatToDoKind, Callable[[Situation], bool], Callable[[Situation], tuple[str, ...]], bool], ...] = (
    (WhatToDoKind.RED_FLAG, lambda s: s.red_flag, _red_flag_lines, False),
    (WhatToDoKind.MISSED_DOSE, lambda s: s.missed is not None, _missed_dose_lines, True),
    (WhatToDoKind.REST, lambda s: True, _rest_lines, True),
)
"""The whole of what the button can say, top row wins. (kind, applies, lines, check-in.)

Red flag: call the chief, call the ambulance, the chief knows. A dose not taken: you have
not taken it, ask before you take it, rest, the chief will call, a check-in in two hours.
Otherwise: rest, water, the chief will call, a check-in in two hours. Nothing else exists.
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
    """Step 1 and 2: keep what he said, then hear it. Exactly one of voice or words."""
    if audio is not None and words is not None:
        raise SaidTwice("a voice note or typed words, not both")
    moment = utcnow()
    if audio is not None:
        artifact = await store_voice(
            session,
            context=context,
            store=store,
            data=audio,
            content_type=content_type or "",
            captured_at=moment,
            source_channel=source_channel,
        )
        transcript = await transcriber.transcribe(audio, artifact.content_type, language)
        return Captured(artifact=artifact, transcript=transcript, by_voice=True)
    if words is not None:
        artifact = await store_words(
            session,
            context=context,
            store=store,
            text=words,
            captured_at=moment,
            source_channel=source_channel,
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
    """Whether he is on a sugar medicine: True, False, or None when no medicine is known."""
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

    The roster (E12) will decide who is on duty; until it lands, everyone the patient let
    in to his emergency card is the roster. The person pressing the button is not told.
    """
    moment = utcnow()
    keys = await audited_read(session, Key, context, Scope.FAMILY)
    chief: Person | None = None
    to_tell: list[Person] = []
    for key in sorted(keys, key=lambda one: (as_utc(one.granted_at), str(one.id))):
        if not key.is_active(moment) or Scope.EMERGENCY not in key.scopes_held:
            continue
        if key.holder_person_id == context.person_id:
            continue
        person = await session.get(Person, key.holder_person_id)
        if person is None or any(one.id == person.id for one in to_tell):
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

    Written before the event, the fact and the card. The notice is a template id and codes:
    "{patient} is not feeling well. {patient} said: 'chest pain'. Call {patient} now. This
    one we do not wait for." — the words quoted are the table's words for the code, in the
    reader's language, never the transcript.
    """
    moment = utcnow()
    flags: list[Flag] = []
    for code in heard.flags:
        flags.append(
            await audited_write(
                session,
                Flag,
                context,
                Scope.RECORDS,
                kind=FlagKind.RED_FLAG,
                code=code.value,
                posture=Posture.ACT,
                artifact_id=captured.artifact.id,
                raised_at=moment,
                raised_by_person_id=context.person_id,
                suppressed=[one.value for one in heard.suppressed],
            )
        )
    first = flags[0]
    notices = [
        await _notice(
            session,
            context=context,
            to=person,
            kind=NoticeKind.FAMILY_ALERT,
            template="family_alert.red_flag",
            slots={"words": _words_code(heard, parsed), "heard": captured.heard},
            flag_id=first.id,
            deliver_after=moment,
        )
        for person in family.to_tell
    ]
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
    """The ordinary path's notice: he is not feeling well, this is what he said, call today."""
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
        Scope.RECORDS,
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
    lines = [render("notice.not_well", lang, patient=patient)]
    code = slots.get("words")
    if isinstance(code, str):
        lines.append(render("notice.said", lang, patient=patient, words=phrase(SYMPTOM_WORDS, lang, code)))
    elif slots.get("heard") is False:
        lines.append(render("notice.not_heard", lang))
    if notice.template == "family_alert.red_flag":
        lines.append(render("notice.call_now", lang, patient=patient))
        lines.append(render("notice.do_not_wait", lang))
    elif notice.kind is NoticeKind.CHECK_IN:
        return [render("notice.check_in", lang)]
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
) -> tuple[uuid.UUID, uuid.UUID]:
    """Step 4: the SYMPTOM event, the `symptom.reported` fact on the artefact and the event,
    and — when the button was pressed — the `feeling.control` fact that sets the posture.
    State recomputes as each fact lands. Returns (event id, symptom fact id)."""
    moment = utcnow()
    event = await record_event(
        session,
        context=context,
        kind=EventKind.SYMPTOM,
        occurred_at=moment,
        label=label,
        artifact_id=captured.artifact.id,
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
            artifact_id=captured.artifact.id,
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
            artifact_id=captured.artifact.id,
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
            artifact_id=captured.artifact.id,
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
    return event.id, fact.id


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
    """The card's lines, filled and verified, in the table's order."""
    lang = language_of(language)
    who = chief.display_name if chief is not None else (doctor or YOUR_DOCTOR[lang])
    slots = {
        "chief": chief.display_name if chief is not None else "",
        "medicine": missed_medicine or YOUR_MEDICINE[lang],
        "who": who,
    }
    return [Line(line_id, render(line_id, lang, **slots)) for line_id in decision.line_ids]


@audited(Action.WRITE, Scope.RECORDS, CARD_TARGET)
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
        # Before the event, before the fact, before the card. The flag is on the record
        # whatever happens next, and so is the notice to each person.
        escalated = await escalate(
            session, context=context, captured=captured, heard=heard, parsed=parsed, family=family
        )

    missed = None if heard.any else await _missed_dose(
        session, context=context, registry=registry, language=lang
    )
    missed_name = (
        None if missed is None else _plain_name(registry, missed.line.generic, lang)
    )
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

    event_id, fact_id = await write_the_moment(
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
    if decision.check_in and profile.owner_person_id is not None:
        check_in_at = utcnow() + CHECK_IN_AFTER
        owner = await session.get(Person, profile.owner_person_id)
        if owner is not None:
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
                    event_id=event_id,
                )
            )

    # Step 5: the card, from the State the facts above produced. `current_state` sees the
    # recompute the hooks made and answers stale=False; a snapshot the record has moved
    # past would be refused here rather than shown.
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
        flag_id=None if escalated is None else escalated.flags[0].id,
        event_id=event_id,
        check_in_at=check_in_at,
        rendered_at=utcnow(),
        rendered_for_person_id=context.person_id,
    )
    return WhatToDoNow(
        card_id=card.id,
        state_id=card.state_id,
        kind=decision.kind,
        posture=state.posture,
        language=lang,
        lines=lines,
        artifact_id=captured.artifact.id,
        event_id=event_id,
        fact_id=fact_id,
        heard=captured.heard,
        by_voice=captured.by_voice,
        transcript_confidence=captured.transcript.confidence,
        red_flags=list(heard.flags),
        suppressed=list(heard.suppressed),
        symptoms=list(parsed.symptoms),
        flag_id=None if escalated is None else escalated.flags[0].id,
        notified_person_ids=[
            n.to_person_id for n in notices if n.kind is NoticeKind.FAMILY_ALERT
        ],
        check_in_at=check_in_at,
        missed_medicine=missed_name,
        notices=notices,
    )


__all__ = [
    "ANCHOR_HOURS",
    "DECISION_TABLE",
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

