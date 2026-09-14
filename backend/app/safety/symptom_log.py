"""The symptom log (E14-01): how he feels, in his words, with how much and since when.

    Symptom log by voice, with severity and duration, in his words. Logged in his words;
    appears in the pre-visit brief.

A symptom comes in the way the button's words do (`app.safety.not_feeling_well.capture`):
the voice note or the typed text is kept as an artefact, then heard, then read against the
fixed tables — the red flags first, then `app.safety.symptoms` for the symptom, the severity
("a little / quite a lot / very") and the duration ("since this morning"). It is stored as a
SYMPTOM event and a `symptom.reported` fact with a seven-day window, resting on the artefact,
which is where "in his words" lives. A red flag in a symptom log is the same red flag as
anywhere else: the flag is written first, the family is told, the day's posture is set.

Reading the log is reading the record: `Scope.RECORDS`, the scope the fact itself is held
under (`scope_for_subject("symptom")`). The owner, the chief, a caregiver read it; a viewer
or a helper — whose presets stop at medicines and readings — do not see how he feels,
because a symptom is closer to a note about himself than to a number from a machine. Each
entry is rendered in plain words with the day's name ("Pa felt dizzy on Monday 14 September.
It was quite a lot. It started this morning.") — the same words every time.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read
from app.audit.models import Action
from app.channels.safety_strings import (
    SEVERITY_WORDS,
    SINCE_WORDS,
    SYMPTOM_WORDS,
    language_of,
    phrase,
    render,
)
from app.db import as_utc, utcnow
from app.drugs.registry import DrugRegistry
from app.ingestion.objects import ObjectStore
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import fact_cites_only_what_is_held_here
from app.memory.models import ConfidenceState, Fact
from app.regions import REGION_TZ, Region
from app.safety.models import Notice
from app.safety.not_feeling_well import (
    REPORTED,
    SYMPTOM,
    Line,
    capture,
    escalate,
    family_of,
    sugar_medicine,
    write_the_moment,
)
from app.safety.red_flags import RedFlag, match_red_flags
from app.safety.symptoms import Duration, Symptom, parse_symptoms
from app.safety.transcribe import Transcriber
from app.state.models import Posture

SYMPTOM_LABEL = "symptom"
DEFAULT_LOOKBACK = timedelta(days=7)
"""How far back the log reads when nobody says: the week before a visit."""
SYMPTOM_SCOPE = Scope.RECORDS
"""What reading the log costs: the record's scope, which is the fact's own."""


@dataclass(frozen=True, slots=True)
class Entry:
    """One logged symptom, as the record holds it and as it is said back."""

    fact_id: uuid.UUID
    event_id: uuid.UUID | None
    artifact_id: uuid.UUID | None
    at: datetime
    symptoms: list[Symptom]
    red_flags: list[RedFlag]
    severity: int | None
    duration: Duration | None
    by_voice: bool
    heard: bool
    confidence: float
    language: str
    lines: list[Line]


@dataclass(frozen=True, slots=True)
class Log:
    """The log as read: from when, in which language, and every entry oldest first."""

    since: datetime
    language: str
    entries: list[Entry]


@dataclass(frozen=True, slots=True)
class Logged:
    """The answer to a log: the entry, and what the red-flag path wrote if it ran."""

    entry: Entry
    posture: Posture | None
    flag_id: uuid.UUID | None
    notified_person_ids: list[uuid.UUID]
    notices: list[Notice]
    suppressed: list[RedFlag]


def _lines(
    *,
    name: str,
    language: str,
    at: datetime,
    region_tz: ZoneInfo,
    symptoms: Sequence[Symptom],
    red_flags: Sequence[RedFlag],
    severity: int | None,
    duration: Duration | None,
    by_voice: bool,
) -> list[Line]:
    lang = language_of(language)
    day = as_utc(at).astimezone(region_tz).date()
    lines: list[Line] = []
    codes = [*(flag.value for flag in red_flags), *(one.value for one in symptoms)]
    if codes:
        for code in codes:
            lines.append(
                Line(
                    "sym.felt",
                    render("sym.felt", lang, name=name, symptom=phrase(SYMPTOM_WORDS, lang, code), date=day),
                )
            )
    else:
        lines.append(Line("sym.not_well", render("sym.not_well", lang, name=name, date=day)))
    if severity is not None:
        by_level = SEVERITY_WORDS.get(lang) or SEVERITY_WORDS["en"]
        lines.append(Line("sym.severity", render("sym.severity", lang, severity=by_level[severity])))
    if duration is not None:
        lines.append(
            Line("sym.since", render("sym.since", lang, since=phrase(SINCE_WORDS, lang, duration.value)))
        )
    lines.append(
        Line("sym.by_voice", render("sym.by_voice", lang, name=name))
        if by_voice
        else Line("sym.typed", render("sym.typed", lang, name=name))
    )
    return lines


def _entry(fact: Fact, *, name: str, language: str, region_tz: ZoneInfo) -> Entry:
    value = fact.value if isinstance(fact.value, dict) else {}
    symptoms = [Symptom(code) for code in value.get("symptoms", []) if code in Symptom.__members__.values()]
    flags = [RedFlag(code) for code in value.get("red_flags", []) if code in RedFlag.__members__.values()]
    severity = value.get("severity")
    duration_code = value.get("duration")
    duration = (
        Duration(duration_code)
        if isinstance(duration_code, str) and duration_code in Duration.__members__.values()
        else None
    )
    by_voice = value.get("via") == "voice"
    return Entry(
        fact_id=fact.id,
        event_id=fact.event_id,
        artifact_id=fact.artifact_id,
        at=as_utc(fact.valid_from),
        symptoms=symptoms,
        red_flags=flags,
        severity=severity if isinstance(severity, int) else None,
        duration=duration,
        by_voice=by_voice,
        heard=bool(value.get("heard", True)),
        confidence=fact.confidence,
        language=language_of(language),
        lines=_lines(
            name=name,
            language=language,
            at=as_utc(fact.valid_from),
            region_tz=region_tz,
            symptoms=symptoms,
            red_flags=flags,
            severity=severity if isinstance(severity, int) else None,
            duration=duration,
            by_voice=by_voice,
        ),
    )


@audited(Action.WRITE, SYMPTOM_SCOPE, Fact.__tablename__)
async def log_symptom(
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
) -> Logged:
    """Write one symptom down from a voice note or typed words. A red flag in it escalates
    exactly as the button does — flag first, family told, posture ACT."""
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
    on_sugar, _ = await sugar_medicine(session, context=context)
    heard = match_red_flags(captured.text, on_sugar_medicine=on_sugar)
    parsed = parse_symptoms(captured.text)

    flag_id: uuid.UUID | None = None
    notices: list[Notice] = []
    posture: Posture | None = None
    if heard.any:
        family = await family_of(session, context=context, profile=profile)
        escalated = await escalate(
            session, context=context, captured=captured, heard=heard, parsed=parsed, family=family
        )
        flag_id = escalated.flags[0].id
        notices = escalated.notices
        posture = Posture.ACT

    _event_id, fact_id = await write_the_moment(
        session,
        context=context,
        captured=captured,
        heard=heard,
        parsed=parsed,
        label=SYMPTOM_LABEL,
        posture=posture,
    )
    fact = await session.get(Fact, fact_id)
    assert fact is not None  # written a moment ago in this session
    entry = _entry(
        fact, name=profile.display_name, language=lang, region_tz=REGION_TZ[context.region]
    )
    return Logged(
        entry=entry,
        posture=posture,
        flag_id=flag_id,
        notified_person_ids=[notice.to_person_id for notice in notices],
        notices=notices,
        suppressed=list(heard.suppressed),
    )


@audited(Action.READ, SYMPTOM_SCOPE, Fact.__tablename__)
async def symptoms_since(
    session: AsyncSession,
    *,
    context: KeyContext,
    since: datetime | None = None,
    language: str | None = None,
) -> Log:
    """Every symptom written down since `since` (default: the last seven days), oldest
    first, each in plain words with the day's name. Superseded facts are not shown; a
    disputed one is not a fact that holds."""
    profile = await audited_profile_read(session, context)
    lang = language_of(language or profile.language)
    moment = utcnow()
    start = since if since is not None else moment - DEFAULT_LOOKBACK
    found = await audited_read(
        session,
        Fact,
        context,
        SYMPTOM_SCOPE,
        where=(
            Fact.subject == SYMPTOM,
            Fact.attribute == REPORTED,
            Fact.superseded_at.is_(None),
            Fact.confidence_state != ConfidenceState.DISPUTED,
            Fact.valid_from >= start,
            fact_cites_only_what_is_held_here(context, SYMPTOM_SCOPE),
        ),
    )
    zone = REGION_TZ[context.region]
    return Log(
        since=start,
        language=lang,
        entries=[
            _entry(fact, name=profile.display_name, language=lang, region_tz=zone)
            for fact in sorted(found, key=lambda one: (as_utc(one.valid_from), str(one.id)))
        ],
    )


def nothing_since_line(since: datetime, *, language: str, region: Region) -> str:
    """The one line for an empty log, verified: "Nothing was written down since {date}"."""
    lang = language_of(language)
    day = as_utc(since).astimezone(REGION_TZ[region]).date()
    return render("sym.none", lang, date=day)
