"""The not-feeling-well flow (E13-02): one button, three steps, the family told.

    Voice-captures what is wrong, checks his recent readings and medicines, tells him what
    to do now (rest / call clinic / go now) and tells Ash. Turns fear into a plan. The most
    valuable single button in the product.

What happens, in order, and the order is the point:

1. **Capture.** His words are kept as an artefact — the voice note, or the text he typed —
   before anything is read from them, when the key holds the record. A voice note is handed
   only to a transcriber in the profile's region; a voice note is the sender's own words,
   kept like typed text (ADR 0003: `Recording.OWN_NOTE`).
2. **Hear.** A voice note goes through the `Transcriber` port; typed words are heard as
   typed. Nothing heard is still a press of the button: the family is told and he is asked
   to say it again.
3. **Red flags first.** The words are read against the one table every channel reads
   (`app.safety.red_flags.detect`). A red flag is written before anything else about the
   moment: the SYMPTOM event it was said in (`record_the_moment`), then the flag on it
   (`write_flag_kept`, E21's `red_flag` table) — and kept: if anything later in the same
   request is refused, the event, the flag and the notices land anyway. A flag that depends
   on a fact the record does not hold (read as the system, whoever pressed) is written
   suppressed and escalates nobody. Otherwise the flag goes up the ladder at once
   (`app.delivery.triggers.ladder.escalate_flag`, E11-06), the one record of who is told:
   whoever E12's roster puts on duty first, the chief a few minutes on if nobody answers,
   then everyone else holding his emergency card — never his own rung, never capped, never
   quiet — and the ladder is kept like the flag. This whole step runs under `Scope.EMERGENCY`, which every role holds, so
   a helper or a caregiver pressing the button for him escalates exactly as he would
   (docs/00-MASTER-BUILD-SPEC.md §8: red flags escalate immediately).
4. **State.** When the key holds the record, the moment becomes a SYMPTOM event and a
   `symptom.reported` fact resting on the artefact, and a `feeling.control` fact — `act`
   for a red flag, `watch` otherwise, for the next 24 hours — which is how the safety layer
   sets the day's posture: through a fact State folds in, never by writing a snapshot itself.
5. **The card.** One row of a fixed decision table (`DECISION_TABLE`: go now, call the clinic,
   a tablet with no Taken, rest — top row wins), every line from
   `app.channels.safety_strings` and verified as an action, inside the not-feeling-well
   boundary (`app.safety.boundary`, `Surface.NOT_FEELING_WELL`): the reassurance first —
   "Mei knows now." — then the row, then "Nura wrote down how you feel." and the two closing
   lines — or, on a red flag's urgent card, the one line "Nura does not decide what is wrong.",
   never "Ask your doctor." after an emergency number. Every card, whatever its row, ends on
   "Nura does not decide what is wrong.". The card row carries that boundary, as every inferring surface's row must (E16). A key that can compute State
   (the owner, the chief) has the card rendered from the State those facts produced and
   written down as a `WhatToDoCard`; a narrower key gets the same lines to show him and no
   card row, since nothing rendered is stored without the State it came from.

The boundary holds throughout. No line says what is wrong with him; no line tells him to
start, stop or change a medicine — a medicine nobody tapped Taken on gets "Nura has no note
that you took the water pill today. Ask Dr Tan before you take the water pill.", never an
amount; a red flag gets "Mei knows now. Call the ambulance now on 995. After that, call Mei." and
nothing about what it might mean. Nothing tells him to drink. The check-in two hours on is a
question, not a judgement.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
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
from app.delivery.triggers.deliver import Via
from app.delivery.triggers.ladder import escalate_flag
from app.delivery.triggers.models import Ladder
from app.drafts import FactDraft
from app.drugs.registry import DrugRegistry, UnknownDrug
from app.errors import Refusal
from app.family.roster import who_is_on_duty
from app.identity.models import Person, Profile
from app.ingestion.objects import ObjectStore
from app.ingestion.transcribe import NOTHING_HEARD, Transcriber, Transcript
from app.ingestion.voice import check_voice_note, store_voice, store_words
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.models import Key
from app.keys.scopes import KeyRole, Scope
from app.medicines.models import LineStatus, MedicationLine
from app.medicines.service import Slot, today
from app.medicines.strings import PLAIN_NAME
from app.memory.episodic import record_event
from app.memory.models import (
    Artifact,
    ConfidenceState,
    Event,
    EventKind,
    Fact,
    Provider,
    ProviderKind,
    SourceChannel,
)
from app.memory.semantic import assert_fact
from app.reasoning.feelings.words import NEW_MEDICINE_WINDOW, SYMPTOM_FEELINGS, WATCH_OUT_WORDS
from app.regions import Region, guard_region
from app.safety.boundary import Surface, boundary_line, boundary_lines
from app.safety.emergency_card import EMERGENCY_NUMBER
from app.safety.models import Notice, NoticeKind, WhatToDoCard, WhatToDoKind
from app.safety.people import key_holder, owner_of
from app.safety.red_flags import (
    FLAG_SCOPE,
    Feeling,
    Flag,
    NotAFeeling,
    detect,
    is_red,
    keep_row,
    record_the_moment,
    write_flag_kept,
)
from app.safety.symptoms import Duration, Parsed, Symptom, parse_symptoms
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

QUITE_A_LOT = 2
"""The severity from which a symptom that is not a red flag is a call to the clinic today:
"quite a lot" / "a lot" (2) and "very" (3), in his words (`app.safety.symptoms`)."""

A_DAY_OR_MORE: frozenset[Duration] = frozenset(
    {Duration.SINCE_YESTERDAY, Duration.FEW_DAYS, Duration.ABOUT_A_WEEK, Duration.LONGER}
)
"""How long a symptom has lasted before it is a call to the clinic today: since yesterday or
longer. "Since yesterday" counts, on the side of calling."""

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
class Heard:
    """What the red-flag table heard (`detect`): the flag's word or nothing, and whether the
    flag was held back because the fact it depends on is not on the record."""

    feeling: Feeling | None
    held_back: bool = False

    @property
    def flags(self) -> tuple[Feeling, ...]:
        """The flag raised and escalated, if any."""
        return (self.feeling,) if self.feeling is not None and not self.held_back else ()

    @property
    def suppressed(self) -> tuple[Feeling, ...]:
        """The flag written and held back, visibly, if any."""
        return (self.feeling,) if self.feeling is not None and self.held_back else ()

    @property
    def any(self) -> bool:
        return bool(self.flags)


@dataclass(frozen=True, slots=True)
class Family:
    """Who is told, and who is named on his card.

    `chief` is the one the card names ("Mei knows already."): whoever is on duty now, else the
    chief key holder. `to_tell` is who the ordinary notice goes to: whoever is on duty, else
    everyone on the emergency list. `everyone` is the whole list, whoever is on duty first: a
    red flag goes to all of them.
    """

    chief: Person | None
    to_tell: list[Person]
    everyone: list[Person]


@dataclass(frozen=True, slots=True)
class Escalated:
    """What the red-flag path wrote before anything else: the moment, the flag, and — unless
    the flag was held back — the ladder (E11-06), and who it asked first."""

    event: Event
    flag: Flag
    notices: list[Notice]
    ladder: Ladder | None
    asked: list[uuid.UUID] = field(default_factory=list)

    @property
    def suppressed(self) -> bool:
        return self.flag.suppressed_because is not None

    @property
    def first(self) -> Flag | None:
        """The flag that escalated, or None when it was held back."""
        return None if self.suppressed else self.flag


@dataclass(frozen=True, slots=True)
class Situation:
    """What the decision table reads: a red flag or not, a dose not taken, who there is."""

    red_flag: bool
    heard: bool
    missed: Slot | None
    chief: Person | None
    others_told: bool
    region: Region
    severity: int | None = None
    """How much, in his words: 1 a little, 2 quite a lot, 3 very."""
    lasting: bool = False
    """He said it has lasted a day or more (`A_DAY_OR_MORE`)."""
    new_medicine: bool = False
    """What he said is on the licensed monograph of a medicine started in the last fourteen
    days, by the rule the feeling cloud reads (E17)."""

    @property
    def calls_the_clinic(self) -> bool:
        """Not a red flag, and quite a lot, or a day or more, or a new medicine's watch-out."""
        if self.red_flag:
            return False
        severe = self.severity is not None and self.severity >= QUITE_A_LOT
        return severe or self.lasting or self.new_medicine


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
    red_flags: list[Feeling]
    suppressed: list[Feeling]
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
    """Call the ambulance now, after that call the chief: one order, and nothing that
    contradicts the notice she was sent. The reassurance that she knows is the boundary's
    opening line ("Mei knows now.", `app.safety.boundary`), said before these."""
    number = EMERGENCY_NUMBER[s.region]
    if s.chief is None:
        lines: tuple[str, ...] = (f"nfw.call_{number}",)
        if s.others_told:
            lines += ("nfw.family_knows",)
        return lines
    return (f"nfw.call_{number}", "nfw.then_call_chief")


def _not_heard(s: Situation) -> tuple[str, ...]:
    """When nothing was heard the card says so first, whichever row it is: he pressed the
    button, and a card that pretends to have understood him would be the wrong card."""
    return () if s.heard else ("nfw.not_heard", "nfw.say_again", "nfw.type_instead")


def _call_clinic_lines(s: Situation) -> tuple[str, ...]:
    """Call the doctor's clinic today — a question for the doctor, never what it might be —
    and, when a tablet has no Taken, the same two lines the tablet row says; then rest, who
    will call, and the check-in."""
    lines: tuple[str, ...] = _not_heard(s) + ("nfw.call_clinic",)
    lines += ("nfw.not_taken", "nfw.ask_before") if s.missed is not None else ()
    # If it gets worse — tonight, before the clinic opens — the ambulance (B1 review).
    lines += ("nfw.rest", f"nfw.if_worse_{EMERGENCY_NUMBER[s.region]}")
    lines += ("nfw.will_call",) if s.chief is not None else ()
    return lines + ("nfw.check_in",)


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
    (WhatToDoKind.CALL_CLINIC, lambda s: s.calls_the_clinic, _call_clinic_lines, True),
    (WhatToDoKind.MISSED_DOSE, lambda s: s.missed is not None, _missed_dose_lines, True),
    (WhatToDoKind.REST, lambda s: True, _rest_lines, True),
)
"""The whole of what the button can say, top row wins. (kind, applies, lines, check-in.)

Red flag: call the ambulance now, after that call the chief.
Call the clinic — a symptom that is not a red flag, said "quite a lot" or "a lot", or that has
lasted a day or more, or that a medicine started in the last fourteen days lists as a
watch-out: call the doctor's clinic today (and, with a tablet not tapped, that Nura has no note
of it and to ask before taking it), rest, the chief will call today, a check-in in two hours.
A dose nobody tapped Taken on: Nura has no note you took it, ask the doctor before you take
it, rest, the chief will call today, a check-in in two hours. Otherwise: rest, the chief will
call today, a check-in in two hours. Nothing else exists, nothing says what is wrong, and
nothing says how much of a medicine to take.
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
    transcriber only if the transcriber is in the profile's region, and is kept, like typed
    words, on the consent to hold the record (ADR 0003).
    """
    if audio is not None and words is not None:
        raise SaidTwice("a voice note or typed words, not both")
    moment = utcnow()
    can_keep = context.allows(Scope.RECORDS)
    if audio is not None:
        kind = check_voice_note(audio, content_type or "")
        guard_region(held_in=context.region, asked_from=transcriber.region)
        # A voice note is the sender's own words, kept like typed text (ADR 0003): no recording
        # consent is asked. It is heard only by a transcriber in the profile's region.
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


async def family_of(session: AsyncSession, *, context: KeyContext, profile: Profile) -> Family:
    """Who is told, and who is named on his card.

    The emergency list is every active key holder with EMERGENCY but the person pressing,
    read under EMERGENCY, not FAMILY: who the patient let in to his emergency card is part of
    the emergency card (ADR 0002), and a caregiver or a helper pressing the button holds no
    FAMILY key. The roster (E12, `who_is_on_duty`) is read when the key can read it — the
    owner, a chief — and says who does the next thing: whoever on the list is on duty now is
    named on the card and is the one the ordinary notice goes to. A red flag still goes to
    everyone on the list, whoever is on duty first. With no roster, nobody on duty, or a key
    that cannot read the roster, the whole list is told and the chief is named.
    """
    moment = utcnow()
    keys = await audited_read(session, Key, context, BUTTON_SCOPE)
    chief: Person | None = None
    listed: list[Person] = []
    for key in sorted(keys, key=lambda one: (as_utc(one.granted_at), str(one.id))):
        if not key.is_active(moment) or Scope.EMERGENCY not in key.scopes_held:
            continue
        if key.holder_person_id == context.person_id:
            continue
        if any(one.id == key.holder_person_id for one in listed):
            continue
        person = await key_holder(session, context, key.holder_person_id, scope=BUTTON_SCOPE)
        if person is None:
            continue
        listed.append(person)
        if chief is None and key.role is KeyRole.CHIEF:
            chief = person
    on_duty: list[Person] = []
    if context.allows(Scope.FAMILY):
        by_id = {person.id: person for person in listed}
        for duty in await who_is_on_duty(session, context=context, at=moment):
            found = by_id.get(duty.person_id)
            if found is not None and found not in on_duty:
                on_duty.append(found)
    if not on_duty:
        return Family(chief=chief, to_tell=listed, everyone=listed)
    rest = [person for person in listed if person not in on_duty]
    return Family(chief=on_duty[0], to_tell=on_duty, everyone=on_duty + rest)


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
    feeling: Feeling,
    family: Family,
    via: Via,
) -> Escalated:
    """Step 3, when the table heard a red flag: the moment, the flag, then who is told.

    Written before the fact and the card, and kept (`write_flag_kept`, `keep_row`) so a
    refusal further on cannot take them back. A flag held back because the fact it depends
    on is not on the record (`suppressed_because`) is written and tells nobody; the ordinary
    path runs instead. Otherwise each person on the emergency list gets a notice — a template
    id and codes: "{patient} is not feeling well. Nura heard this: chest pain. Call {patient}
    now. This one we do not wait for." — the table's words for the code in the reader's
    language, never the transcript; and the ladder (`roster_for`, `Escalation`) is written
    beside the flag for E11 to walk.
    """
    moment = utcnow()
    event = await record_the_moment(
        session,
        context=context,
        feeling=feeling,
        occurred_at=moment,
        source_channel=SourceChannel.APP,
    )
    flag = await write_flag_kept(session, context, feeling=feeling, event=event)
    if flag.suppressed_because is not None:
        return Escalated(event=event, flag=flag, notices=[], ladder=None)
    escalated = await escalate_flag(
        session, context, flag, told_already=(context.person_id,), via=via, at=moment
    )
    if escalated.ladder is not None:
        keep_row(session, context, escalated.ladder, scope=FLAG_SCOPE)
    return Escalated(
        event=event,
        flag=flag,
        notices=[],
        ladder=escalated.ladder,
        asked=list(escalated.asked),
    )


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
    event: Event | None = None,
) -> tuple[Event, Fact]:
    """Step 4: the SYMPTOM event, the `symptom.reported` fact on the artefact and the event,
    and — when the button was pressed — the `feeling.control` fact that sets the posture.
    State recomputes as each fact lands. Needs the record: the caller checks."""
    moment = utcnow()
    artifact_id = None if captured.artifact is None else captured.artifact.id
    if event is None:
        # The red-flag path has written the moment already (`record_the_moment`); otherwise
        # it is written here, on the artefact that holds his words.
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
        or (
            [Symptom.NOT_WELL.value]
            if said_nothing_known and label == NOT_FEELING_WELL_LABEL
            else []
        ),
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
    """The first dose of today whose window has closed with nobody tapping Taken on it: the
    window his routine sets (E04-02, `app.medicines.windows`), the same one the Taken card
    and the ladder read."""
    if not context.allows(Scope.MEDICINES):
        return None
    slots = await today(session, context=context, registry=registry, language=language)
    due = [slot for slot in slots if not slot.taken and slot.missed]
    return due[0] if due else None


async def _new_medicine(
    session: AsyncSession, *, context: KeyContext, registry: DrugRegistry, parsed: Parsed
) -> MedicationLine | None:
    """A medicine started in the last fourteen days whose licensed monograph lists what he said
    as a watch-out — the rule the feeling cloud reads a tap by (E17: `WATCH_OUT_WORDS` from the
    registry's rule ids, `NEW_MEDICINE_WINDOW`), with his words read to the cloud's word
    (`SYMPTOM_FEELINGS`). The pharmacology is the register's; nothing here is a finding."""
    said = {SYMPTOM_FEELINGS[one] for one in parsed.symptoms if one in SYMPTOM_FEELINGS}
    if not said or not context.allows(Scope.MEDICINES):
        return None
    moment = utcnow()
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
    for line in sorted(lines, key=lambda one: (as_utc(one.started_at), one.generic), reverse=True):
        if moment - as_utc(line.started_at) > NEW_MEDICINE_WINDOW:
            continue
        try:
            watch = registry.monograph(line.generic).watch_out_ids
        except UnknownDrug:
            continue
        if any(WATCH_OUT_WORDS.get(rule) in said for rule in watch):
            return line
    return None


async def _directory_doctor(
    session: AsyncSession, *, context: KeyContext
) -> tuple[str, ProviderKind] | None:
    """The doctor, else the clinic, his directory names, and which it is — read under the
    emergency scope, the part every role holds and the one his emergency card names the
    doctor from (ADR 0002). A clinic is called by its own name, never as "Dr …'s clinic"."""
    providers = await audited_read(session, Provider, context, BUTTON_SCOPE)
    for kind in (ProviderKind.DOCTOR, ProviderKind.CLINIC):
        for provider in sorted(providers, key=lambda one: (as_utc(one.added_at), one.name)):
            if provider.kind is kind:
                return provider.name, kind
    return None


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
    clinic: str | None = None,
) -> list[Line]:
    """The card's lines, filled and verified, in the table's order.

    The one who is asked before a dose is the doctor on the label first, then the chief,
    then "your doctor": a question about a medicine is rerouted to the doctor, not the family.
    The clinic called today is a doctor's ("Call Dr Tan's clinic today."), or — when the
    directory names only a clinic — the clinic by its own name ("Call Bedok Clinic today.").
    """
    lang = language_of(language)
    who = doctor or (chief.display_name if chief is not None else YOUR_DOCTOR[lang])
    slots = {
        "chief": chief.display_name if chief is not None else "",
        "medicine": missed_medicine or YOUR_MEDICINE[lang],
        "who": who,
        # The clinic is always a doctor's: never the chief's name in "Call …'s clinic today."
        "doctor": doctor or YOUR_DOCTOR[lang],
        "clinic": clinic or "",
    }
    ids = [
        "nfw.call_named" if one == "nfw.call_clinic" and clinic and not doctor else one
        for one in decision.line_ids
    ]
    return [Line(line_id, render(line_id, lang, **slots)) for line_id in ids]


BOUNDARY_PREFIX = "boundary."
BOUNDARY_IDS = (
    "boundary.opening",
    "boundary.did",
    "boundary.not_advice",
    "boundary.ask",
    "boundary.not_deciding",
)
"""The not-feeling-well boundary's five lines as he sees them (no letter is carried yet): the
reassurance, what Nura did, the two closing lines, and "Nura does not decide what is wrong."."""
URGENT_BOUNDARY_IDS = ("boundary.opening", "boundary.urgent")
"""The urgent card's two: the reassurance first, "Nura does not decide what is wrong." last."""


def within_the_boundary(
    lines: list[Line],
    *,
    language: str,
    doctor: str | None,
    told: str | None,
    urgent: bool = False,
) -> list[Line]:
    """The row's lines inside the not-feeling-well boundary (E16-01): the reassurance first
    ("Mei knows now." — or "You did right to say so." when nobody was named), then the row,
    then — on an ordinary card — what Nura did and the two closing lines, or — on the urgent
    card of a red flag — the one closing line "Nura does not decide what is wrong.", so that
    nothing after "Call the ambulance now on 995." sends him anywhere else. The words are
    `app.safety.boundary`'s; the card row keeps the same text in its `boundary` column and the
    row's ids in `line_ids`."""
    said = boundary_lines(
        Surface.NOT_FEELING_WELL, language, doctor=doctor, told=told, urgent=urgent
    )
    ids = URGENT_BOUNDARY_IDS if urgent else BOUNDARY_IDS
    opening, *closing = (Line(line_id, text) for line_id, text in zip(ids, said, strict=True))
    return [opening, *lines, *closing]


@audited(Action.WRITE, BUTTON_SCOPE, CARD_TARGET)
async def not_feeling_well(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    transcriber: Transcriber,
    registry: DrugRegistry,
    via: Via,
    words: str | None = None,
    audio: bytes | None = None,
    content_type: str | None = None,
    language: str | None = None,
    feeling: Feeling | None = None,
) -> WhatToDoNow:
    """The button. See the module doc for the five steps and their order. `via` is the
    channels this process sends through: a red flag's ladder sends its first rung at once.

    `feeling` is for a caller that already knows the red word — a tap on the feeling cloud
    (E17), where he chose the word itself: the flag is that word, and the table is not asked
    to hear it back from the words (weight gain has no words in the table at all). Only a red
    word may be named (`NotAFeeling`); the words are still kept and read for symptoms.
    """
    if feeling is not None and not is_red(feeling):
        raise NotAFeeling(f"{feeling} is not a red flag")
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
    feeling = feeling if feeling is not None else detect(captured.text)
    parsed = parse_symptoms(captured.text)
    family = await family_of(session, context=context, profile=profile)

    escalated: Escalated | None = None
    if feeling is not None:
        # Before the fact, before the card — and kept whatever follows.
        escalated = await escalate(
            session, context=context, captured=captured, feeling=feeling, family=family, via=via
        )
        if escalated.asked:
            # The card names who the ladder called first: that is who knows now.
            first = await key_holder(session, context, escalated.asked[0], scope=BUTTON_SCOPE)
            if first is not None:
                family = Family(chief=first, to_tell=family.to_tell, everyone=family.everyone)
    heard = Heard(feeling, held_back=escalated is not None and escalated.suppressed)

    missed = (
        None
        if heard.any
        else await _missed_dose(session, context=context, registry=registry, language=lang)
    )
    missed_name = None if missed is None else _plain_name(registry, missed.line.generic, lang)
    new_line = (
        None
        if heard.any
        else await _new_medicine(session, context=context, registry=registry, parsed=parsed)
    )
    notices: list[Notice] = list(escalated.notices) if escalated is not None else []
    if not heard.any:
        notices = await tell_family(
            session,
            context=context,
            captured=captured,
            heard=heard,
            parsed=parsed,
            family=family,
            missed=missed_name,
        )

    event: Event | None = None if escalated is None else escalated.event
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
            event=event,
        )

    situation = Situation(
        red_flag=heard.any,
        heard=captured.heard,
        missed=missed,
        chief=family.chief,
        others_told=bool(family.everyone),
        region=context.region,
        severity=parsed.severity,
        lasting=parsed.duration in A_DAY_OR_MORE,
        new_medicine=new_line is not None,
    )
    decision = decide(situation)
    urgent = decision.kind is WhatToDoKind.RED_FLAG
    doctor = None if missed is None else missed.line.prescriber
    clinic: str | None = None
    if decision.kind is WhatToDoKind.CALL_CLINIC:
        # The clinic of the doctor on the new medicine's label, else the tablet's, else his
        # directory's doctor — or its clinic, by the clinic's own name; "your doctor" when
        # none is named.
        doctor = (new_line.prescriber if new_line is not None else None) or doctor
        if doctor is None:
            named = await _directory_doctor(session, context=context)
            if named is not None and named[1] is ProviderKind.DOCTOR:
                doctor = named[0]
            elif named is not None:
                clinic = named[0]
    told = None if family.chief is None else family.chief.display_name
    lines = within_the_boundary(
        compose(
            decision,
            language=lang,
            chief=family.chief,
            missed_medicine=missed_name,
            doctor=doctor,
            clinic=clinic,
        ),
        language=lang,
        doctor=doctor,
        told=told,
        urgent=urgent,
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
            surface=Surface.NOT_FEELING_WELL,
            boundary=boundary_line(
                Surface.NOT_FEELING_WELL, lang, doctor=doctor, told=told, urgent=urgent
            ),
            kind=decision.kind,
            language=lang,
            line_ids=[line.id for line in lines if not line.id.startswith(BOUNDARY_PREFIX)],
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
        # A key that does not open the record is not told what the rule found in it.
        suppressed=list(heard.suppressed) if can_record else [],
        symptoms=list(parsed.symptoms),
        flag_id=None if escalated is None or escalated.first is None else escalated.first.id,
        notified_person_ids=(
            list(escalated.asked)
            if escalated is not None and escalated.first is not None
            else [n.to_person_id for n in notices if n.kind is NoticeKind.FAMILY_ALERT]
        ),
        check_in_at=check_in_at,
        missed_medicine=missed_name,
        notices=notices,
    )


__all__ = [
    "A_DAY_OR_MORE",
    "BUTTON_SCOPE",
    "DECISION_TABLE",
    "FLAG_SCOPE",
    "QUITE_A_LOT",
    "Captured",
    "Decision",
    "Escalated",
    "Family",
    "Heard",
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
    "write_the_moment",
]
