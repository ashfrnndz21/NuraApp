"""Red flags: the things we do not wait for — the words, the rule, and the one row they raise.

The list comes from docs/smart-nudges.md §2 and `.claude/rules/safety.md`: chest tightness,
breathlessness at rest, one-sided swelling, worst-ever headache, sudden blurring, a fall,
confusion, shaky-and-sweaty on sugar medicines, a kilo or more in two days after a heart
discharge — plus the discharge-watch words the spec names for a visit (black stool, a fever
beside a medicine). Whichever way one comes in, it comes here first — before planning,
before ranking, before any cap or quiet hour — and raises a `Flag`, one row on the profile:

- **The feeling cloud (E21).** A tap on a red feeling: `raise_flag` writes the `Flag` naming
  the feeling and the SYMPTOM event it was said in, and tells every live key that holds the
  emergency scope, with a share line each.
- **Free text on WhatsApp (E19-05).** `RED_FLAG_WORDS` and `detect` read a message for the same
  nine flags, in the three languages a family here writes in, and give back the `Feeling` a
  tap would have; `record_the_moment` writes the SYMPTOM event under the emergency scope so a
  helper's word can raise it, and `Escalation` is the ladder written beside it — the owner,
  then the chief keys, then every other live key, in calling order — for E11 to walk;
  `roster_for` reads it off the keys table.
- **Words heard at a visit (E05).** `RED_FLAG_TERMS` is the list as words a transcript
  carries, with the discharge-watch words; `find_red_flags` finds them with their spans and
  `red_flags_heard` reads a transcript and everything the summariser heard for them, the
  transcript's own span winning. `write_red_flag` writes the `Flag` before the summary card is
  composed, in a way that outlives a refusal later in the same request. The same row carries
  a medicine change heard at a visit (`FlagKind.MEDICINE_CHANGE_HEARD`) for E04's reconcile —
  never applied here, never an amount.

The two word tables are kept apart on purpose: a family member writing "he fell" means a
fall, and E19 matches the bare word; a doctor's transcript says "fall" of a season or a
number, and E05 matches the phrase. They share one vocabulary (`FEELING_CODE`), so a flag from
any door names the same thing the same way in `code`.

A flag that depends on a missing fact is not raised in silence and not raised loudly either:
it is written with `suppressed_because` so the caregiver sees the suppression (safety.md).
Nothing here diagnoses. The sentences live with the surfaces that say them
(`app.delivery.strings`, `app.channels.whatsapp`, `app.reasoning.visits.strings`) and name a
person and a day, never a condition.

E11's ladder (`app.delivery.triggers.ladder.escalate_flag`) is the one record of who is told
about a red flag, whichever door raised it: no `Escalation` row is written any more (the rows
already written stay, as the record they were), and the share lines a flag writes on `told`
say whose key held the emergency card at that moment, not that a message reached them.

The not-feeling-well button and the symptom log (E13/E14) hear the same words (`detect`) and
raise the same flag, on the SYMPTOM event `record_the_moment` writes under the emergency scope.
Their flag is written through `write_flag_kept`: `raise_flag`, and a keeper on the session
(`app.db.keep_on_refusal`, the mechanism refused audit lines use) that writes the flag, the
event it rests on and their lines on the trail again if something later in the same request
is refused and the unit of work is rolled back. "This one we do not wait for" has to survive
a template that fails, a State that is stale, or a door that refuses further on. A flag heard
at a visit (`write_red_flag`) is kept by the same keeper (`_keep_flag`), and `keep_row` does
the same for the notices and the ladder written beside a flag.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import JSON, Boolean, ForeignKey, String, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited, audited_read, audited_write, record_share
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import Base, ProfileScoped, as_utc, enum_column, frozen, keep_on_refusal, utcnow
from app.errors import Refusal
from app.identity.models import Profile
from app.keys.context import KeyContext
from app.keys.grants import list_keys
from app.keys.models import Key
from app.keys.scopes import KeyRole, Scope
from app.medicines.models import LineStatus, MedicationLine
from app.memory.models import (
    ConfidenceState,
    Event,
    EventKind,
    Fact,
    SourceChannel,
    _row_of_profile,
    _tied_to_profile,
)
from app.state.dimensions import AFTER_DISCHARGE_WINDOW, CONTROL

# --- the feeling cloud -----------------------------------------------------------------------


class Feeling(StrEnum):
    """The words on the feeling cloud. The first nine are the red flags."""

    FALL = "fall"
    CHEST_TIGHTNESS = "chest_tightness"
    BREATHLESS_AT_REST = "breathless_at_rest"
    ONE_SIDED_SWELLING = "one_sided_swelling"
    WORST_HEADACHE = "worst_headache"
    SUDDEN_BLURRING = "sudden_blurring"
    CONFUSION = "confusion"
    SHAKY_SWEATY = "shaky_sweaty"
    WEIGHT_GAIN = "weight_gain"
    DIZZY = "dizzy"
    CRAMPS = "cramps"
    THIRSTY = "thirsty"
    TIRED = "tired"
    ACHES = "aches"
    HEADACHE = "headache"
    FINE = "fine"


RED_FLAGS: frozenset[Feeling] = frozenset(
    {
        Feeling.FALL,
        Feeling.CHEST_TIGHTNESS,
        Feeling.BREATHLESS_AT_REST,
        Feeling.ONE_SIDED_SWELLING,
        Feeling.WORST_HEADACHE,
        Feeling.SUDDEN_BLURRING,
        Feeling.CONFUSION,
        Feeling.SHAKY_SWEATY,
        Feeling.WEIGHT_GAIN,
    }
)

SUGAR_CONDITIONS = frozenset({"diabetes", "type_2_diabetes", "type2_diabetes", "blood_sugar"})
"""Subjects a clinician's control word about sugar is recorded under. Shaky-and-sweaty is a
red flag on one of these, or on an active medicine that can drop his sugar
(`HYPOGLYCAEMIC_CLASSES`); with neither on the record it is written suppressed, visibly, and
`suppressed_because` stays "no_sugar_condition_on_record" for both."""

HYPOGLYCAEMIC_CLASSES = frozenset({"insulin", "sulfonylurea"})
"""The licensed register's classes (`drug_class`, carried on the medication line from the
register) whose medicines can drop his sugar: insulin, and the sulfonylureas — gliclazide,
glibenclamide. On one of them shaky-and-sweaty escalates whether or not a sugar condition is
written down. A class, never a list of names; widening it (meglitinides) is the pharmacist's."""

FLAG_TARGET = "red_flag"

# --- the words written on WhatsApp (E19-05) --------------------------------------------------

RED_FLAG_WORDS: Mapping[Feeling, tuple[str, ...]] = {
    Feeling.CHEST_TIGHTNESS: (
        r"chest (?:is )?(?:tight|pain|hurt|hurts|pressure)",
        r"tight(?:ness)? in (?:his|her|my|the) chest",
        r"sakit dada",
        r"dada (?:saya |dia )?(?:sakit|sesak|ketat|berat)",
        r"胸[口]?(?:痛|闷|紧)",
        r"pain in (?:his|her|my|the) chest",
        r"heart pain",
        r"心口(?:痛|闷)",
    ),
    Feeling.BREATHLESS_AT_REST: (
        r"breathless",
        r"cannot breathe",
        r"can'?t breathe",
        r"short of breath",
        r"hard to breathe",
        r"sesak nafas",
        r"susah bernafas",
        r"(?:喘不过气|呼吸困难|气喘)",
        r"tak boleh bernafas",
        r"\bsemput\b",
        r"透不过气",
    ),
    Feeling.ONE_SIDED_SWELLING: (
        r"one (?:leg|arm|foot|side) (?:is )?swollen",
        r"swollen on one side",
        r"(?:left|right) (?:leg|foot|arm) (?:is )?(?:swollen|swelling)",
        r"(?:kaki|tangan) (?:sebelah|kiri|kanan) bengkak",
        r"(?:一边|一只)(?:腿|脚|手)肿",
        r"sebelah (?:kaki|tangan) bengkak",
        r"bengkak sebelah",
    ),
    Feeling.WORST_HEADACHE: (
        r"worst headache",
        r"headache (?:ever|like never)",
        r"sakit kepala (?:teruk|paling)",
        r"(?:头痛得?|头很痛)(?:厉害|从来没有|最)",
    ),
    Feeling.SUDDEN_BLURRING: (
        r"suddenly (?:blur|blurry|cannot see|can'?t see)",
        r"(?:blur|blurry|blurred) (?:vision|eyes?|eyesight)",
        r"cannot see (?:properly|well|suddenly)",
        r"mata (?:kabur|tiba-tiba kabur)",
        r"tiba-tiba (?:kabur|tak nampak)",
        r"(?:突然|忽然)?(?:看不清|眼睛模糊|视线模糊)",
        r"kabur tiba-tiba",
    ),
    Feeling.FALL: (
        r"\bfell\b",
        r"\bfall(?:en|s)?\b",
        r"\bfalling\b",
        r"\bjatuh\b",
        r"terjatuh",
        r"(?:跌倒|摔倒|摔了|跌了|摔跤)",
        r"\btergolek\b",
    ),
    Feeling.CONFUSION: (
        r"\bconfused\b",
        r"not making sense",
        r"does ?n[o']t (?:recognise|recognize|know) (?:me|us|anyone)",
        r"\bkeliru\b",
        r"tak (?:kenal|ingat) (?:kami|saya|orang)",
        r"(?:糊涂|认不出|说话不清|神志不清)",
        r"\bconfusion\b",
        r"(?:don'?t|do not) know where (?:i|he|she) (?:am|is)",
        r"\bkebingungan\b",
    ),
    Feeling.SHAKY_SWEATY: (
        r"shak(?:y|ing) and sweat(?:y|ing)",
        r"sweat(?:y|ing) and shak(?:y|ing)",
        r"trembling and sweating",
        r"menggigil dan berpeluh",
        r"berpeluh dan menggigil",
        r"(?:发抖|手抖).{0,4}(?:出汗|冒汗)|(?:出汗|冒汗).{0,4}(?:发抖|手抖)",
    ),
}
"""The rule's words, matched anywhere in a message, case-insensitively. Whole words for the
short English ones, so that "fell" is a fall and "fellow" is not."""

_PATTERNS: tuple[tuple[Feeling, re.Pattern[str]], ...] = tuple(
    (rule, re.compile(pattern, re.IGNORECASE))
    for rule, patterns in RED_FLAG_WORDS.items()
    for pattern in patterns
)


def detect(text: str | None) -> Feeling | None:
    """The first red flag the words of a message match, or None: the same `Feeling` a tap on
    the cloud raises, heard in free text on WhatsApp (E19-05). The weight rule is a fact, not a
    word, so it is not in the table."""
    if not text:
        return None
    for rule, pattern in _PATTERNS:
        if pattern.search(text):
            return rule
    return None


# --- the words heard at a visit (E05) --------------------------------------------------------

RED_FLAG_TERMS: Mapping[str, tuple[str, ...]] = {
    "chest_pain": (
        "chest pain",
        "chest tightness",
        "tight chest",
        "sakit dada",
        "dada ketat",
        "胸痛",
        "胸闷",
    ),
    "breathless": (
        "breathless",
        "breathlessness",
        "short of breath",
        "cannot breathe",
        "sesak nafas",
        "susah bernafas",
        "气促",
        "呼吸困难",
    ),
    "black_stool": ("black stool", "black stools", "najis hitam", "berak hitam", "黑便"),
    "fall": ("a fall", "fell down", "fell over", "had a fall", "jatuh", "terjatuh", "跌倒"),
    "confusion": ("confusion", "confused", "keliru", "celaru", "神志不清", "糊涂"),
    "one_sided_swelling": (
        "one-sided swelling",
        "one leg swollen",
        "sebelah kaki bengkak",
        "单侧肿胀",
    ),
    "worst_headache": (
        "worst headache",
        "worst-ever headache",
        "sakit kepala paling teruk",
        "最严重的头痛",
    ),
    "sudden_blurring": ("sudden blurring", "suddenly blurry", "kabur tiba-tiba", "突然模糊"),
    "shaky_and_sweaty": ("shaky and sweaty", "menggigil dan berpeluh", "发抖出汗"),
    "fever_on_medicine": ("fever", "demam", "发烧", "发热"),
}
"""The codes and the words a transcript or a fact might carry them in, in the three
languages. `fever_on_medicine` is the discharge-watch entry: a fever is a red-flag word only
beside a medicine name (`FEVER_NEEDS_A_MEDICINE`)."""

FEELING_CODE: Mapping[Feeling, str] = {
    Feeling.FALL: "fall",
    Feeling.CHEST_TIGHTNESS: "chest_pain",
    Feeling.BREATHLESS_AT_REST: "breathless",
    Feeling.ONE_SIDED_SWELLING: "one_sided_swelling",
    Feeling.WORST_HEADACHE: "worst_headache",
    Feeling.SUDDEN_BLURRING: "sudden_blurring",
    Feeling.CONFUSION: "confusion",
    Feeling.SHAKY_SWEATY: "shaky_and_sweaty",
    Feeling.WEIGHT_GAIN: "weight_gain",
}
"""Every red feeling as its code in `RED_FLAG_TERMS`, so a flag from the cloud or WhatsApp and
one heard at a visit name the same thing the same way. `weight_gain` has no words to hear: it
is a number rule (a kilo in two days after a discharge), raised from the cloud or a reading."""

FEVER_NEEDS_A_MEDICINE = frozenset({"fever_on_medicine"})

MEDICINE_WORDS = re.compile(
    r"\b(?:tablet|tablets|pill|pills|medicine|medicines|ubat|pil|药|药片)\b", re.IGNORECASE
)
"""How a medicine is named beside a fever: a word for a medicine, or a drug name the
caller passes in (`medicine_names`)."""


@dataclass(frozen=True, slots=True)
class RedFlagHit:
    """One red-flag word found: the code, the word as it appeared, and where."""

    code: str
    word: str
    start: int
    end: int

    def span(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end}


def _term_pattern(word: str) -> re.Pattern[str]:
    # Words in Latin script match whole words; Chinese has no word boundaries.
    if re.search(r"[A-Za-z]", word):
        return re.compile(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", re.IGNORECASE)
    return re.compile(re.escape(word))


_TERM_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = tuple(
    (code, word, _term_pattern(word))
    for code, words in RED_FLAG_TERMS.items()
    for word in sorted(words, key=len, reverse=True)
)


def _strings_in(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for inner in value.values():
            yield from _strings_in(inner)
    elif isinstance(value, list | tuple):
        for inner in value:
            yield from _strings_in(inner)


def find_red_flags(text: str, *, medicine_names: tuple[str, ...] = ()) -> list[RedFlagHit]:
    """Every red-flag word in `text`, in the order found. A fever counts only beside a
    medicine word or one of `medicine_names` on the same text."""
    names_medicine = bool(MEDICINE_WORDS.search(text)) or any(
        name and name.lower() in text.lower() for name in medicine_names
    )
    hits: list[RedFlagHit] = []
    for code, word, pattern in _TERM_PATTERNS:
        if code in FEVER_NEEDS_A_MEDICINE and not names_medicine:
            continue
        for match in pattern.finditer(text):
            if any(h.start <= match.start() < h.end for h in hits):
                continue
            hits.append(RedFlagHit(code, match.group(), match.start(), match.end()))
    return sorted(hits, key=lambda h: h.start)


def red_flags_in(*values: Any, medicine_names: tuple[str, ...] = ()) -> list[RedFlagHit]:
    """Red-flag words anywhere in these values — strings, or the strings inside JSON."""
    found: list[RedFlagHit] = []
    for value in values:
        for text in _strings_in(value):
            found.extend(find_red_flags(text, medicine_names=medicine_names))
    return found


class HeardSpan(Protocol):
    """Where in a transcript something was heard, as the summariser gives it."""

    def as_json(self) -> dict[str, int]: ...


class HeardFact(Protocol):
    """A fact the summariser heard: its code, its value, where."""

    @property
    def subject(self) -> str: ...
    @property
    def attribute(self) -> str: ...
    @property
    def value(self) -> Any: ...
    @property
    def span(self) -> HeardSpan: ...


class HeardAction(Protocol):
    """An action the summariser heard: its slots, where."""

    @property
    def slots(self) -> Mapping[str, Any]: ...
    @property
    def span(self) -> HeardSpan: ...


class HeardDraft(Protocol):
    """What the summariser heard (`app.reasoning.visits.summary.SummaryDraft`), as far as the
    red-flag rule reads it."""

    @property
    def facts_heard(self) -> Sequence[HeardFact]: ...
    @property
    def actions(self) -> Sequence[HeardAction]: ...


@dataclass(frozen=True, slots=True)
class Heard:
    """One red-flag word heard at a visit: the word, its span in the transcript, and where it
    was found — the transcript itself, a fact the summariser heard, or an action's slots."""

    word: str
    span: dict[str, int]
    found_in: str


def red_flags_heard(
    text: str, draft: HeardDraft, *, medicine_names: tuple[str, ...]
) -> dict[str, Heard]:
    """Every red-flag word, wherever it was heard: the raw transcript first (with the word's
    own span in it), then every fact's subject, attribute and value, then every action's
    slots. One entry per code, the transcript's span winning — so a word the summariser left
    out is still found (E05 review, B2)."""
    found: dict[str, Heard] = {}
    for hit in find_red_flags(text, medicine_names=medicine_names):
        found.setdefault(hit.code, Heard(hit.word, hit.span(), "transcript"))
    for fact in draft.facts_heard:
        # A subject or attribute is an underscore-joined code ("black_stool"); read as words.
        for hit in red_flags_in(
            fact.subject.replace("_", " "),
            fact.attribute.replace("_", " "),
            fact.value,
            medicine_names=medicine_names,
        ):
            found.setdefault(hit.code, Heard(hit.word, fact.span.as_json(), "fact"))
    for action in draft.actions:
        for hit in red_flags_in(action.slots, medicine_names=medicine_names):
            found.setdefault(hit.code, Heard(hit.word, action.span.as_json(), "action"))
    return found


# --- the rows --------------------------------------------------------------------------------


class NotAFeeling(Refusal):
    """The feeling cloud has a fixed set of words. This was not one of them."""


class FlagKind(StrEnum):
    """What a flag is. None of these is a diagnosis; each is a thing that bypasses planning
    (a red flag) or becomes a question for the doctor (a change heard)."""

    RED_FLAG = "red_flag"
    MEDICINE_CHANGE_HEARD = "medicine_change_heard"
    """A change to a medicine the doctor said at a visit (E05-05). Never applied here: the
    row is what E04's reconcile picks up, with the person's OK on a plan. Its `subject` is
    the generic, `code` the kind of change, and `payload` carries `generic`, `change`,
    `line_id` (the active line of that generic, when there is one), `span` in the transcript
    and `ask_the_doctor: true` — and never an amount. Interactions are E04's own
    `InteractionFlag` rows, not a kind here."""


class Flag(ProfileScoped, Base):
    """One flag on one profile: what it is, where it came from, who raised it, who was told.

    `code` is the entry in `RED_FLAG_TERMS` (`FEELING_CODE` for one from the cloud or
    WhatsApp) or, for a change heard, the kind of change. A flag from the cloud or WhatsApp
    names the `feeling` and the SYMPTOM `event_id` it was said in; one heard at a visit names
    the transcript `artifact_id` and the `appointment_id`, with the word, its span and where
    it was found in `payload`. `payload` is structured — a generic name, a span — never a
    sentence and never an amount.

    `suppressed_because` is set when a flag depends on a fact that is not on the record
    (`SUGAR_CONDITIONS`, a discharge inside the window): the flag is written so the
    caregiver sees it was considered, and it does not reach the patient's feed as a flag.
    Escalation is the `told` list and the share lines beside it, and on WhatsApp the
    `Escalation` ladder. A flag takes one change, `resolved_at`: set by a person when the
    doctor has been asked.
    """

    __tablename__ = FLAG_TARGET
    __table_args__ = (
        _row_of_profile(FLAG_TARGET),
        _tied_to_profile(FLAG_TARGET, "event_id", "event"),
        _tied_to_profile(FLAG_TARGET, "artifact_id", "artifact"),
        _tied_to_profile(FLAG_TARGET, "appointment_id", "appointment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[FlagKind] = mapped_column(
        enum_column(FlagKind, "flag_kind"), default=FlagKind.RED_FLAG
    )
    code: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(64), default="symptom")
    feeling: Mapped[Feeling | None] = mapped_column(enum_column(Feeling, "feeling"), default=None)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("event.id"), default=None)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artifact.id"), default=None)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointment.id"), default=None
    )
    fact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raised_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    raised_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    told: Mapped[list[str]] = mapped_column(JSON, default=list)
    suppressed_because: Mapped[str | None] = mapped_column(String(64), default=None)
    ambiguous_profile: Mapped[bool] = mapped_column(Boolean, default=False)
    """Raised by someone on more than one profile before they said which: raised on each (E11)."""
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)


class Escalation(ProfileScoped, Base):
    """Who is told about a flag, in what order, and who has been told so far.

    `roster` is a list of `{"person_id", "standing"}` in calling order: the owner, then the
    chief keys, then every other live key, the poster left out (they know). `told` is the
    person ids that have had the in-thread word. Person ids only; no names, no words.
    """

    __tablename__ = "safety_escalation"
    __table_args__ = (
        _row_of_profile("safety_escalation"),
        _tied_to_profile("safety_escalation", "flag_id", FLAG_TARGET),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    flag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("red_flag.id"), index=True)
    roster: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    told: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


frozen(Flag, except_for=frozenset({"resolved_at"}))
frozen(Escalation)

FLAG_WINDOW = timedelta(hours=24)
"""How long a raised flag leads the feed: the same day, whatever the hour."""


def is_red(feeling: Feeling) -> bool:
    return feeling in RED_FLAGS


async def _system_read(
    session: AsyncSession,
    *,
    context: KeyContext,
    model: Any,
    scope: Scope,
    where: Sequence[Any],
) -> Sequence[Any]:
    """A safety rule's own read of the record: the system's view, not the key of whoever raised
    the flag. A helper who saw him shaking must start the ladder when the record says he is on
    a sugar medicine, though her key opens neither his conditions nor his medicines. The rows
    are for the rule alone — nothing read reaches the caller, only whether the flag was held
    back — and the read is written down as the system's (`Channel.SYSTEM`), in the raiser's
    name, under the scope the rows sit in."""
    rows = list(
        await session.scalars(select(model).where(model.profile_id == context.profile_id, *where))
    )
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=scope,
        target=model.__tablename__,
        rows=len(rows),
        channel=Channel.SYSTEM,
    )
    return rows


async def _missing_fact(
    session: AsyncSession, *, context: KeyContext, feeling: Feeling
) -> str | None:
    """For the two flags that depend on the record: what is missing, or None.

    The record is read as the system (`_system_read`), whoever raised the flag: a safety rule
    is evaluated on what the record holds, not on what the raiser's key opens. Shaky-and-sweaty
    stands on a sugar condition or an active medicine the register classes as lowering sugar;
    a kilo in two days on a recent discharge."""
    moment = utcnow()
    if feeling is Feeling.SHAKY_SWEATY:
        conditions = await _system_read(
            session,
            context=context,
            model=Fact,
            scope=Scope.RECORDS,
            where=(
                Fact.attribute == CONTROL,
                Fact.subject.in_(SUGAR_CONDITIONS),
                Fact.superseded_at.is_(None),
                Fact.confidence_state != ConfidenceState.DISPUTED,
                Fact.valid_from <= moment,
                or_(Fact.valid_to.is_(None), Fact.valid_to > moment),
            ),
        )
        if conditions:
            return None
        medicines = await _system_read(
            session,
            context=context,
            model=MedicationLine,
            scope=Scope.MEDICINES,
            where=(
                MedicationLine.superseded_at.is_(None),
                MedicationLine.status == LineStatus.ACTIVE,
                MedicationLine.drug_class.in_(HYPOGLYCAEMIC_CLASSES),
            ),
        )
        if medicines:
            return None
        return "no_sugar_condition_on_record"
    if feeling is Feeling.WEIGHT_GAIN:
        discharges = await _system_read(
            session,
            context=context,
            model=Event,
            scope=Scope.RECORDS,
            where=(
                Event.kind == EventKind.DISCHARGE,
                Event.occurred_at > moment - AFTER_DISCHARGE_WINDOW,
            ),
        )
        if not discharges:
            return "no_recent_discharge_on_record"
    return None


async def _live_keys(session: AsyncSession, *, context: KeyContext) -> Sequence[Key]:
    """Every key on the profile: through the family door when the raiser holds it (the owner,
    a chief), and read off the table otherwise — the way `roster_for` and
    `app.keys.context.holds_the_profile` do — so that a helper who saw him fall can raise the
    flag that tells the family. Person ids only; the off-table read is written down."""
    if context.allows(Scope.FAMILY):
        return await list_keys(session, context=context)
    keys = list(await session.scalars(select(Key).where(Key.profile_id == context.profile_id)))
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=Scope.EMERGENCY,
        target=Key.__tablename__,
        rows=len(keys),
        channel=Channel.SYSTEM,
    )
    return keys


async def _emergency_holders(session: AsyncSession, *, context: KeyContext) -> list[str]:
    """Everyone holding a live key with the emergency scope right now: who a red flag tells."""
    moment = utcnow()
    return [
        str(key.holder_person_id)
        for key in await _live_keys(session, context=context)
        if key.is_active(moment) and Scope.EMERGENCY in key.scopes_held
    ]


@audited(Action.WRITE, Scope.EMERGENCY, FLAG_TARGET)
async def record_the_moment(
    session: AsyncSession,
    *,
    context: KeyContext,
    feeling: Feeling,
    occurred_at: datetime,
    source_channel: SourceChannel,
    channel: Channel = Channel.APP,
) -> Event:
    """The SYMPTOM event a flag heard in free text rests on, written under the emergency scope.

    `raise_flag` needs an event, and `record_event` writes one under the record's scope. A
    helper's key holds the emergency scope and not the record (`ROLE_SCOPES`), and a helper
    who saw him fall is the one whose word must start the ladder — so the moment is written
    here, behind the same door as the flag: a key without the emergency scope is refused at
    it, by name, before anything is written. The event is a moment and the flag's word, no
    content; what was said is the message artefact, kept under the same scope.
    """
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.EMERGENCY,
        channel=channel,
    )
    return await audited_write(
        session,
        Event,
        context,
        Scope.EMERGENCY,
        channel=channel,
        kind=EventKind.SYMPTOM,
        occurred_at=occurred_at,
        source_channel=source_channel,
        label=feeling.value,
        recorded_at=utcnow(),
    )


@audited(Action.WRITE, Scope.EMERGENCY, FLAG_TARGET)
async def raise_flag(
    session: AsyncSession,
    *,
    context: KeyContext,
    feeling: Feeling,
    event_id: uuid.UUID,
    channel: Channel = Channel.APP,
    ambiguous_profile: bool = False,
) -> Flag:
    """Raise a red flag on the event in which the feeling was said, and tell the family.

    Runs before any ranking or cap: the caller records the SYMPTOM event, calls this, and
    only then does the feed learn of it. Everyone holding a live key with the emergency
    scope is on `told`, with a share line each. `NotAFeeling` for a word that is not red.
    """
    if not is_red(feeling):
        raise NotAFeeling(f"{feeling} is not a red flag")
    suppressed = await _missing_fact(session, context=context, feeling=feeling)
    moment = utcnow()
    told = [] if suppressed is not None else await _emergency_holders(session, context=context)
    flag = await audited_write(
        session,
        Flag,
        context,
        Scope.EMERGENCY,
        channel=channel,
        kind=FlagKind.RED_FLAG,
        code=FEELING_CODE[feeling],
        subject="symptom",
        feeling=feeling,
        event_id=event_id,
        raised_by_person_id=context.person_id,
        raised_at=moment,
        told=told,
        suppressed_because=suppressed,
        ambiguous_profile=ambiguous_profile,
    )
    for person in told:
        await record_share(
            session,
            context=context,
            scope=Scope.EMERGENCY,
            target=FLAG_TARGET,
            channel=channel,
            shared_with_person_id=uuid.UUID(person),
            target_id=flag.id,
        )
    return flag


async def write_red_flag(
    session: AsyncSession, *, context: KeyContext, tell_the_family: bool = False, **values: Any
) -> Flag:
    """A flag heard at a visit that outlives the request it was written in.

    With `tell_the_family` (a red-flag word heard, not a change heard) the flag tells what a
    tapped one tells: everyone holding a live key with the emergency scope is on `told`, with
    a share line each, and the caregiver's feed shows it (`open_flags`); the patient's own
    summary card leads with calling the doctor today.

    The request is one savepoint (`app.db.unit_of_work`): a refusal later in the same
    request — a line the verifier will not pass, a slot value that is not one — rolls the
    savepoint back. A red flag must not go with it, so the write also registers a keeper
    (`app.db.keep_on_refusal`), the mechanism the refused audit lines use: after the
    rollback the channel replays it and the same row, with the same id, lands and is
    written down again. On success the keeper is dropped, the row already there. Written
    under the record's scope, where the transcript it was heard in is kept.
    """
    values.setdefault("raised_by_person_id", context.person_id)
    if tell_the_family:
        values["told"] = await _emergency_holders(session, context=context)
    flag = await audited_write(session, Flag, context, Scope.RECORDS, **values)
    for person in flag.told:
        await record_share(
            session,
            context=context,
            scope=Scope.EMERGENCY,
            target=FLAG_TARGET,
            channel=Channel.APP,
            shared_with_person_id=uuid.UUID(person),
            target_id=flag.id,
        )
    # Kept the way every flag is kept, the button's included (`write_flag_kept`).
    _keep_flag(session, context, flag, scope=Scope.RECORDS)
    return flag


@audited(Action.READ, Scope.EMERGENCY, FLAG_TARGET)
async def open_flags(session: AsyncSession, *, context: KeyContext) -> Sequence[Flag]:
    """The red flags inside the window, newest first, suppressed ones included: raised on a
    feeling — tapped on the cloud or heard on WhatsApp — or a word heard in a visit
    transcript. The caller decides who sees which (`compose`): a word heard at a visit is the
    caregiver's card only, since his own summary card already leads with calling the doctor
    today and a word in a transcript can be one said in passing ("no chest pain"), while the
    patient's flag card says to call the emergency number. A medicine change heard is a
    question for the doctor, never a card here.
    """
    moment = utcnow()
    found = await audited_read(
        session,
        Flag,
        context,
        Scope.EMERGENCY,
        where=(
            Flag.raised_at > moment - FLAG_WINDOW,
            Flag.kind == FlagKind.RED_FLAG,
            or_(Flag.feeling.is_not(None), Flag.artifact_id.is_not(None)),
        ),
        order_by=(Flag.raised_at.desc(),),
    )
    return [flag for flag in found if as_utc(flag.raised_at) <= moment]


async def roster_for(
    session: AsyncSession, *, context: KeyContext, channel: Channel = Channel.WHATSAPP
) -> list[dict[str, str]]:
    """The calling order for this profile: owner, chief keys, other live keys; the poster out.

    The keys table is read here directly, the way `app.keys.context.holds_the_profile`
    reads it: this is a yes-or-no about who is *named* on the profile, never a read of what
    the graph holds, and the escalation must not depend on the poster's key covering the
    family list — a helper who sees him fall is the one whose word starts the ladder. The
    read is still written down, as a system read of the key table on this profile.
    """
    moment = utcnow()
    profile = await session.get(Profile, context.profile_id)
    assert profile is not None  # the context was resolved from this row
    keys = list(
        await session.scalars(
            select(Key).where(Key.profile_id == context.profile_id).order_by(Key.granted_at)
        )
    )
    live = [key for key in keys if key.is_active(moment)]
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=Scope.EMERGENCY,
        target=Key.__tablename__,
        rows=len(live),
        channel=Channel.SYSTEM,
    )
    order: list[dict[str, str]] = []
    seen: set[uuid.UUID] = {context.person_id}
    if profile.owner_person_id is not None and profile.owner_person_id not in seen:
        order.append({"person_id": str(profile.owner_person_id), "standing": "owner"})
        seen.add(profile.owner_person_id)
    for role in (KeyRole.CHIEF, None):
        for key in live:
            if key.holder_person_id in seen:
                continue
            if role is not None and key.role is not role:
                continue
            if role is None and key.role is KeyRole.CHIEF:
                continue
            order.append(
                {
                    "person_id": str(key.holder_person_id),
                    "standing": "chief" if key.role is KeyRole.CHIEF else key.role.value,
                }
            )
            seen.add(key.holder_person_id)
    return order


async def escalate(
    session: AsyncSession,
    *,
    context: KeyContext,
    flag: Flag,
    roster: Sequence[Mapping[str, str]],
    told: Sequence[uuid.UUID],
    channel: Channel = Channel.WHATSAPP,
) -> Escalation:
    """Write down the ladder for this flag and who has had the word so far."""
    return await audited_write(
        session,
        Escalation,
        context,
        Scope.EMERGENCY,
        channel=channel,
        flag_id=flag.id,
        roster=[dict(step) for step in roster],
        told=[str(person_id) for person_id in told],
        created_at=utcnow(),
    )


# --- a flag that stays written (E13/E14) ------------------------------------------------------

FLAG_SCOPE = Scope.EMERGENCY
"""The door a flag is written through: the one every role holds, because the person who hears
the words — a helper, a neighbour — must be able to raise the flag whoever he is."""


def _columns(row: Any) -> dict[str, Any]:
    """The column values of a row, for writing the same row again after a rollback."""
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


async def write_flag_kept(
    session: AsyncSession,
    context: KeyContext,
    *,
    feeling: Feeling,
    event: Event,
    channel: Channel = Channel.APP,
) -> Flag:
    """Raise the flag on the SYMPTOM event it was said in (`raise_flag`), and keep it.

    A keeper is registered on the session (`app.db.keep_on_refusal`): if the unit of work this
    flag was written in is rolled back on a later refusal, the channel replays the keeper,
    which writes the event the flag rests on and the flag again — the same ids, the same
    moment — with their WRITE lines and a share line for each person on `told`. On success
    the keeper is dropped: the rows are already there.
    """
    flag = await raise_flag(
        session, context=context, feeling=feeling, event_id=event.id, channel=channel
    )
    _keep_flag(session, context, flag, event=event, scope=FLAG_SCOPE, channel=channel)
    return flag


def _keep_flag(
    session: AsyncSession,
    context: KeyContext,
    flag: Flag,
    *,
    scope: Scope,
    event: Event | None = None,
    channel: Channel = Channel.APP,
) -> None:
    """The one way a flag is kept, whichever door raised it: a keeper on the session
    (`app.db.keep_on_refusal`) that, if the unit of work the flag was written in is rolled back
    on a later refusal, writes the event it rests on (when there is one) and the flag again —
    the same ids, the same moment — with their WRITE lines under `scope` and a share line for
    each person on `told`. On success the keeper is dropped: the rows are already there."""
    event_values = None if event is None else _columns(event)
    flag_values = _columns(flag)

    async def keep(again: AsyncSession) -> None:
        if event_values is not None and await again.get(Event, event_values["id"]) is None:
            again.add(Event(**event_values))
            await again.flush()
            await record(
                again,
                context=context,
                action=Action.WRITE,
                scope=scope,
                target=Event.__tablename__,
                target_id=event_values["id"],
                rows=1,
                channel=channel,
            )
        if await again.get(Flag, flag_values["id"]) is None:
            again.add(Flag(**flag_values))
            await again.flush()
            await record(
                again,
                context=context,
                action=Action.WRITE,
                scope=scope,
                target=FLAG_TARGET,
                target_id=flag_values["id"],
                rows=1,
                channel=channel,
            )
            for person in flag_values["told"]:
                await record_share(
                    again,
                    context=context,
                    scope=Scope.EMERGENCY,
                    target=FLAG_TARGET,
                    channel=channel,
                    shared_with_person_id=uuid.UUID(person),
                    target_id=flag_values["id"],
                )

    keep_on_refusal(session, keep)


def keep_row(session: AsyncSession, context: KeyContext, row: Any, *, scope: Scope) -> None:
    """Keep one already-written row the way `write_flag_kept` keeps the flag: written again,
    with its WRITE line, if the unit it was written in is rolled back. For the notices and
    the ladder that go with a flag."""
    values = _columns(row)
    model = type(row)

    async def keep(again: AsyncSession) -> None:
        if await again.get(model, values["id"]) is None:
            again.add(model(**values))
            await again.flush()
            await record(
                again,
                context=context,
                action=Action.WRITE,
                scope=scope,
                target=model.__tablename__,
                target_id=values["id"],
                rows=1,
            )

    keep_on_refusal(session, keep)


__all__ = [
    "FEELING_CODE",
    "FLAG_SCOPE",
    "FLAG_TARGET",
    "FLAG_WINDOW",
    "RED_FLAGS",
    "RED_FLAG_TERMS",
    "RED_FLAG_WORDS",
    "Escalation",
    "Feeling",
    "Flag",
    "FlagKind",
    "Heard",
    "NotAFeeling",
    "RedFlagHit",
    "SourceChannel",
    "detect",
    "escalate",
    "find_red_flags",
    "is_red",
    "keep_row",
    "open_flags",
    "raise_flag",
    "record_the_moment",
    "red_flags_heard",
    "red_flags_in",
    "roster_for",
    "write_flag_kept",
    "write_red_flag",
]
