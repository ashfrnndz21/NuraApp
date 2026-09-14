"""Making today's cards from State and the record.

`refresh` is what a first page of the feed runs: it reads State, and from the snapshot and
the facts behind it makes the cards that are not there yet — the flag if one was raised, the
one thing for now, today's cards, the gate, this week's story, and the learning cards the
self-search jobs found. Every card is made through `items.create_item`, so every one names
the snapshot, passed the plain-words check, and cites what it was built from in `why`.

Nothing here judges. A reading card says the number; a visit card says the day; a story
card says what the record already says. The only inference is the format switch — two text
cards that went unopened — and that is written as a Fact with its provenance, so State
folds it and the next snapshot says why the cards changed shape.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read, audited_read, person_display_name
from app.db import as_utc, nested_unit_of_work, utcnow
from app.delivery.feed.items import NotPlainWords, Why, create_item
from app.delivery.feed.models import (
    CardFormat,
    CardType,
    DeliverTo,
    Engagement,
    EngagementKind,
    FeedItem,
    JobKind,
    Supply,
)
from app.delivery.feed.search import Engine, create_job, run_job
from app.delivery.strings import (
    CAREGIVER_DUTY_HEADLINE,
    CAREGIVER_DUTY_LINES,
    CAREGIVER_DUTY_LINES_ONE,
    CAREGIVER_DUTY_WHY,
    CAREGIVER_HEARD_HEADLINE,
    CAREGIVER_HEARD_LINE,
    CAREGIVER_NO_ROSTER_LINE,
    CAREGIVER_ON_DUTY_LINE,
    CAREGIVER_ROSTER_WHY,
    CAREGIVER_SUPPRESSED_HEADLINE,
    CAREGIVER_SUPPRESSED_LINE,
    EMERGENCY_NUMBER,
    YOUR_DOCTOR,
    Lines,
    counted,
    feeling_words,
    language_for,
    render,
    test_name,
)
from app.errors import Refusal
from app.family.roster import who_is_on_duty
from app.identity.models import Profile
from app.keys.context import KeyContext
from app.keys.grants import list_keys
from app.keys.models import Key
from app.keys.scopes import KeyRole, Scope
from app.medicines.service import LineView, active_lines
from app.memory.episodic import record_event
from app.memory.models import (
    Appointment,
    ConfidenceState,
    Event,
    EventKind,
    Fact,
    Provider,
    SourceChannel,
)
from app.memory.semantic import assert_fact, current_facts
from app.notes.models import Note
from app.notes.service import list_notes
from app.reasoning.visits.brief import brief_for, latest_brief
from app.reasoning.visits.guard import (
    NotTheirsToChangeVisits,
    can_change_visits,
    may_change_visits,
)
from app.reasoning.visits.memos import consolidate_memos, current_memos
from app.reasoning.visits.models import Brief, Memo, MemoSource, SummaryItem, VisitSummary
from app.reasoning.visits.strings import spoken
from app.regions import REGION_TZ
from app.safety.boundary import Surface, boundary_line, is_boundary_line
from app.safety.red_flags import Flag, open_flags
from app.state.dimensions import BEFORE_VISIT_WINDOW
from app.state.models import Dimension
from app.state.service import RECOMPUTE_SCOPES, StateView, current_state

STORY_LIFETIME = timedelta(days=7)
"""His story regenerates weekly (E21-05): a recall card lives a week, then is made again."""
STORY_READINGS = 6
"""How many past numbers from the book become recall cards in a week."""
UNOPENED_TO_SWITCH = 2
"""Two unopened text cards switch the profile to voice-first delivery (spec §9)."""
UNOPENED_WINDOW = timedelta(days=7)
"""How far back the switch looks for cards that went unopened: yesterday's cards have
expired from the supply, but they are what the switch is about."""

FORMAT_SUBJECT, FORMAT_ATTRIBUTE, VOICE = "format", "preferred", "voice"
"""The fact the format switch is written as. `format` folds into the cognitive dimension."""

WEEKDAYS: Mapping[str, tuple[str, ...]] = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "ms": ("Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"),
    "zh": ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"),
}
MONTHS: Mapping[str, tuple[str, ...]] = {
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "ms": (
        "Januari",
        "Februari",
        "Mac",
        "April",
        "Mei",
        "Jun",
        "Julai",
        "Ogos",
        "September",
        "Oktober",
        "November",
        "Disember",
    ),
}


def plain_day(local: datetime, language: str) -> str:
    """ "Monday 14 September", the way docs/plain-words.md rule 5 says; never "the 14th"."""
    code = language_for(language)
    if code == "zh":
        return f"{local.month}月{local.day}日{WEEKDAYS['zh'][local.weekday()]}"
    return f"{WEEKDAYS[code][local.weekday()]} {local.day} {MONTHS[code][local.month - 1]}"


@dataclass(frozen=True, slots=True)
class Day:
    """Today on the patient's wall clock: the date the caps count, and when it ends."""

    tz: ZoneInfo
    now: datetime
    local: datetime

    @property
    def key(self) -> str:
        return self.local.date().isoformat()

    @property
    def week(self) -> str:
        year, week, _ = self.local.isocalendar()
        return f"{year}-W{week:02d}"

    @property
    def ends_at(self) -> datetime:
        midnight = datetime.combine(self.local.date() + timedelta(days=1), time(0), self.tz)
        return midnight.astimezone(self.now.tzinfo)

    def same_day(self, moment: datetime) -> bool:
        return as_utc(moment).astimezone(self.tz).date() == self.local.date()

    def plain(self, moment: datetime, language: str) -> str:
        return plain_day(as_utc(moment).astimezone(self.tz), language)


def today_for(context: KeyContext) -> Day:
    tz = REGION_TZ[context.region]
    now = utcnow()
    return Day(tz=tz, now=now, local=now.astimezone(tz))


@dataclass(frozen=True, slots=True)
class Household:
    """Who is around him, for the lines that say who does the next thing."""

    profile: Profile
    language: str
    who: str | None
    """Who does the next thing: the person on duty by the roster (E12-03), else the first
    live chief or caregiver, or None when he is on his own here."""
    doctor: str | None
    holding_now: int
    on_duty: tuple[str, ...] = ()
    """Everyone the roster puts on duty right now, in roster order; empty with no roster."""


async def _household(session: AsyncSession, *, context: KeyContext) -> Household:
    profile = await audited_profile_read(session, context)
    keys = await list_keys(session, context=context) if context.allows(Scope.FAMILY) else ()
    moment = utcnow()
    who: str | None = None
    holding = 0
    for key in sorted(keys, key=lambda one: as_utc(one.granted_at)):
        if not key.is_active(moment):
            continue
        holding += 1
        if who is None and key.role in (KeyRole.CHIEF, KeyRole.CAREGIVER):
            name = await person_display_name(session, context, key.holder_person_id)
            who = name or None
    # The roster, when the family keeps one, says who does the next thing better than the
    # order the keys were cut in; with no roster (or no slot right now) the keys stand.
    on_duty: list[str] = []
    if context.allows(Scope.FAMILY):
        for duty in await who_is_on_duty(session, context=context, at=moment):
            name = await person_display_name(session, context, duty.person_id)
            if name and name not in on_duty:
                on_duty.append(name)
    return Household(
        profile=profile,
        language=language_for(profile.language),
        who=on_duty[0] if on_duty else who,
        doctor=None,
        holding_now=holding,
        on_duty=tuple(on_duty),
    )


async def can_compose(context: KeyContext) -> bool:
    """Composing renders from State, so it needs what a recompute needs."""
    return RECOMPUTE_SCOPES <= context.scopes


async def refresh(
    session: AsyncSession, *, context: KeyContext, engine: Engine
) -> tuple[StateView, Sequence[FeedItem]]:
    """Make whatever card is missing for today, and return the State the cards came from.

    The format switch is decided first, because it may write a Fact and move State; the
    cards are then rendered from the State that includes it.
    """
    day = today_for(context)
    house = await _household(session, context=context)
    existing = await audited_read(
        session, FeedItem, context, Scope.PROFILE, where=(FeedItem.expires_at > day.now,)
    )
    keys = {item.dedupe_key for item in existing}
    recent = await audited_read(
        session,
        FeedItem,
        context,
        Scope.PROFILE,
        where=(FeedItem.created_at > day.now - UNOPENED_WINDOW,),
    )
    await _switch_format_if_ignored(session, context=context, day=day, items=recent)
    state = await current_state(session, context=context)
    format = _format_of(state)
    made: list[FeedItem] = []

    async def make(**values: Any) -> FeedItem | None:
        if values["dedupe_key"] in keys:
            return None
        if values["type"] is CardType.FLAG:
            # A flag card is made first, on its own: nothing made after it can take it back.
            try:
                item = await create_item(
                    session, context=context, state=state, format=format, **values
                )
            except NotPlainWords:
                return None
        else:
            # Every other card in its own savepoint: a refusal is written down, that card is
            # skipped, and the flag cards made before it stand.
            try:
                async with nested_unit_of_work(session):
                    item = await create_item(
                        session, context=context, state=state, format=format, **values
                    )
            except Refusal:
                return None
        keys.add(item.dedupe_key)
        made.append(item)
        return item

    medicines: list[LineView] = (
        await active_lines(
            session, context=context, registry=engine.registry, language=house.language
        )
        if context.allows(Scope.MEDICINES)
        else []
    )
    await _flags(make, session, context=context, day=day, house=house)
    await _now(
        make, session, context=context, state=state, day=day, house=house, medicines=medicines
    )
    readings = await current_facts(
        session, context=context, subject="blood_pressure", attribute="reading"
    )
    await _reorder(make, day=day, house=house, medicines=medicines)
    await _readings(make, day=day, house=house, readings=readings)
    await _visit(make, session, context=context, engine=engine, state=state, day=day, house=house)
    await _memos(make, session, context=context, day=day, house=house)
    await make(
        type=CardType.GATE,
        lines=render("gate", house.language, body=("gate",)),
        why=Why(kind="gate", plain=render("gate", house.language, body=()).why),
        scope=Scope.PROFILE,
        deliver_to=DeliverTo.PATIENT,
        day=day.key,
        dedupe_key=f"gate:{day.key}",
        expires_at=day.ends_at,
    )
    await make(
        type=CardType.DUTY,
        lines=Lines(
            language=house.language,
            headline=CAREGIVER_DUTY_HEADLINE,
            body=tuple(
                [
                    CAREGIVER_ON_DUTY_LINE.format(
                        who=" and ".join(house.on_duty), name=house.profile.display_name
                    )
                ]
                if house.on_duty
                else []
            )
            + tuple(
                line.format(count=house.holding_now, name=house.profile.display_name)
                for line in (
                    CAREGIVER_DUTY_LINES_ONE if house.holding_now == 1 else CAREGIVER_DUTY_LINES
                )
            )
            + (() if house.on_duty else (CAREGIVER_NO_ROSTER_LINE,)),
            voice=(),
            why=CAREGIVER_ROSTER_WHY if house.on_duty else CAREGIVER_DUTY_WHY,
        ),
        why=Why(kind="duty", plain=CAREGIVER_ROSTER_WHY if house.on_duty else CAREGIVER_DUTY_WHY),
        scope=Scope.FAMILY,
        deliver_to=DeliverTo.CAREGIVER,
        day=day.key,
        dedupe_key=f"duty:{day.key}",
        expires_at=day.ends_at,
    )
    await _story(make, session, context=context, day=day, house=house, readings=readings)
    made.extend(
        await _learning(
            session,
            context=context,
            engine=engine,
            state=state,
            day=day,
            house=house,
            keys=keys,
            medicines=medicines,
        )
    )
    return state, made


def _format_of(state: StateView) -> CardFormat:
    cognitive = state.dimension(Dimension.COGNITIVE) or {}
    preferred = cognitive.get("facts", {}).get(FORMAT_SUBJECT, {}).get(FORMAT_ATTRIBUTE, {})
    return CardFormat.VOICE_FIRST if preferred.get("value") == VOICE else CardFormat.TEXT


async def _switch_format_if_ignored(
    session: AsyncSession, *, context: KeyContext, day: Day, items: Sequence[FeedItem]
) -> None:
    """Two text cards from an earlier day, delivered to him, that nobody heard or tapped:
    the profile goes voice-first, as a Fact resting on the moment it was noticed."""
    candidates = [
        item
        for item in items
        if item.deliver_to is DeliverTo.PATIENT
        and item.format is CardFormat.TEXT
        and item.supply in (Supply.TODAY, Supply.NOW)
        and not day.same_day(item.created_at)
    ]
    if len(candidates) < UNOPENED_TO_SWITCH:
        return
    opened = await audited_read(
        session,
        Engagement,
        context,
        Scope.PROFILE,
        where=(
            Engagement.item_id.in_([item.id for item in candidates]),
            Engagement.kind.in_([EngagementKind.HEARD, EngagementKind.TAPPED]),
        ),
    )
    heard = {one.item_id for one in opened}
    ignored = [item for item in candidates if item.id not in heard]
    if len(ignored) < UNOPENED_TO_SWITCH:
        return
    already = await current_facts(
        session, context=context, subject=FORMAT_SUBJECT, attribute=FORMAT_ATTRIBUTE
    )
    if any(
        fact.value == VOICE or fact.confidence_state is not ConfidenceState.EXTRACTED
        for fact in already
    ):
        # Voice already, or a format he chose himself on his settings screen (E01-03): two
        # unopened cards do not overturn his word, and `ConfirmedFactStands` would refuse it.
        return
    noticed = await record_event(
        session,
        context=context,
        kind=EventKind.ENGAGEMENT,
        occurred_at=day.now,
        label="two cards went unopened",
        source_channel=SourceChannel.APP,
    )
    await assert_fact(
        session,
        context=context,
        subject=FORMAT_SUBJECT,
        attribute=FORMAT_ATTRIBUTE,
        value=VOICE,
        confidence=0.8,
        event_id=noticed.id,
        supersedes_id=already[0].id if already else None,
    )


async def _flags(
    make: Any, session: AsyncSession, *, context: KeyContext, day: Day, house: Household
) -> None:
    if not context.allows(Scope.EMERGENCY):
        return
    number = EMERGENCY_NUMBER[context.region.value]
    for flag in await open_flags(session, context=context):
        if flag.feeling is None:
            # A word heard at a visit (E05): his summary card already leads with calling the
            # doctor today; the family is told here, in the caregiver's fuller words.
            word = str(flag.payload.get("word") or flag.code)
            heard = CAREGIVER_HEARD_LINE.format(word=word, name=house.profile.display_name)
            await make(
                type=CardType.FLAG,
                lines=Lines(
                    language=house.language,
                    headline=CAREGIVER_HEARD_HEADLINE.format(word=word),
                    body=(heard,),
                    voice=(),
                    why=heard,
                ),
                why=Why(
                    kind="flag",
                    plain="",
                    flag_id=str(flag.id),
                    artifact_id=None if flag.artifact_id is None else str(flag.artifact_id),
                ),
                scope=Scope.EMERGENCY,
                deliver_to=DeliverTo.CAREGIVER,
                day=day.key,
                dedupe_key=f"flag:{flag.id}",
                expires_at=as_utc(flag.raised_at) + timedelta(hours=24),
            )
            continue
        feeling = feeling_words(flag.feeling.value, house.language)
        if flag.suppressed_because is not None:
            await make(
                type=CardType.FLAG,
                lines=Lines(
                    language=house.language,
                    headline=CAREGIVER_SUPPRESSED_HEADLINE.format(feeling=flag.feeling.value),
                    body=(
                        CAREGIVER_SUPPRESSED_LINE.format(
                            name=house.profile.display_name,
                            feeling=flag.feeling.value,
                            reason=flag.suppressed_because,
                        ),
                    ),
                    voice=(),
                    why=CAREGIVER_SUPPRESSED_LINE.format(
                        name=house.profile.display_name,
                        feeling=flag.feeling.value,
                        reason=flag.suppressed_because,
                    ),
                ),
                why=Why(
                    kind="flag",
                    plain="",
                    flag_id=str(flag.id),
                    event_id=str(flag.event_id),
                    suppressed=flag.suppressed_because,
                ),
                scope=Scope.EMERGENCY,
                deliver_to=DeliverTo.CAREGIVER,
                day=day.key,
                dedupe_key=f"flag:{flag.id}",
                expires_at=as_utc(flag.raised_at) + timedelta(hours=24),
            )
            continue
        lines = render(
            "flag",
            house.language,
            body=("flag_family",) if house.who else ("flag_alone",),
            feeling=feeling,
            who=house.who or "",
            emergency_number=number,
        )
        await make(
            type=CardType.FLAG,
            lines=lines,
            why=Why(
                kind="flag", plain=lines.why, flag_id=str(flag.id), event_id=str(flag.event_id)
            ),
            scope=Scope.EMERGENCY,
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key=f"flag:{flag.id}",
            expires_at=as_utc(flag.raised_at) + timedelta(hours=24),
        )


def _has_medicines(state: StateView) -> tuple[bool, list[str]]:
    clinical = state.dimension(Dimension.CLINICAL) or {}
    facts = clinical.get("facts", {})
    ids: list[str] = []
    for subject in ("medicine", "medication"):
        for entry in facts.get(subject, {}).values():
            ids.append(entry["fact_id"])
    return bool(ids), sorted(ids)


async def _next_visit(
    session: AsyncSession, *, context: KeyContext, state: StateView
) -> tuple[dict[str, Any] | None, str | None]:
    """The next visit State names, and the provider's name, or nothing."""
    situational = state.dimension(Dimension.SITUATIONAL) or {}
    visit = situational.get("next_visit")
    if visit is None:
        return None, None
    providers = await audited_read(
        session,
        Provider,
        context,
        Scope.VISITS,
        where=(Provider.id == uuid.UUID(visit["provider_id"]),),
    )
    return visit, (providers[0].name if providers else None)


async def _now(
    make: Any,
    session: AsyncSession,
    *,
    context: KeyContext,
    state: StateView,
    day: Day,
    house: Household,
    medicines: Sequence[LineView],
) -> None:
    has_medicines, medicine_ids = _has_medicines(state)
    if medicines:
        has_medicines = True
        medicine_ids = sorted({*medicine_ids, *(str(view.line.fact_id) for view in medicines)})
    boosts = tuple(
        window for window in (state.dimension(Dimension.SITUATIONAL) or {}).get("windows", [])
    )
    if has_medicines:
        lines = render(
            "now_tablets", house.language, body=("now_tablets",), voice=("now_tablets_voice",)
        )
        await make(
            type=CardType.NOW,
            lines=lines,
            why=Why(kind="now", plain=lines.why, fact_ids=tuple(medicine_ids), boosts=boosts),
            scope=Scope.MEDICINES,
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key=f"now:{day.key}",
            expires_at=day.ends_at,
        )
        return
    visit, doctor = await _next_visit(session, context=context, state=state)
    if visit is not None and day.same_day(datetime.fromisoformat(visit["at"])):
        lines = render(
            "now_visit",
            house.language,
            body=("now_visit",),
            doctor=doctor or YOUR_DOCTOR[house.language],
        )
        await make(
            type=CardType.NOW,
            lines=lines,
            why=Why(kind="now", plain=lines.why, visit_id=visit["id"], boosts=boosts),
            scope=Scope.VISITS,
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key=f"now:{day.key}",
            expires_at=day.ends_at,
        )
        return
    lines = render("now_quiet", house.language, body=("now_quiet",))
    await make(
        type=CardType.NOW,
        lines=lines,
        why=Why(kind="now", plain=lines.why, boosts=boosts),
        scope=Scope.PROFILE,
        deliver_to=DeliverTo.PATIENT,
        day=day.key,
        dedupe_key=f"now:{day.key}",
        expires_at=day.ends_at,
    )


async def _reorder(make: Any, *, day: Day, house: Household, medicines: Sequence[LineView]) -> None:
    """A medicine running low: E04 worked the count and the date out and wrote the lines;
    the card repeats them and says how many days are left (docs/medications-module.md)."""
    for view in medicines:
        count = view.count
        if not count.reorder_due or not count.reorder or count.days_left is None:
            continue
        lines = render(
            "reorder",
            house.language,
            body=(),
            extra=tuple(count.reorder),
            why=counted("reorder", count.days_left),
            medicine=view.name,
            days=count.days_left,
        )
        await make(
            type=CardType.REORDER,
            lines=lines,
            why=Why(
                kind="reorder",
                plain=lines.why,
                fact_ids=(str(view.line.fact_id),),
                gap=f"{count.remaining:g} {count.unit} left, {count.days_left} days",
            ),
            scope=Scope.MEDICINES,
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key=f"reorder:{view.line.id}:{day.key}",
            expires_at=day.ends_at,
        )


def _numbers(fact: Fact) -> tuple[int, int] | None:
    value = fact.value
    if isinstance(value, dict) and "systolic" in value and "diastolic" in value:
        return int(value["systolic"]), int(value["diastolic"])
    return None


async def _readings(make: Any, *, day: Day, house: Household, readings: Sequence[Fact]) -> None:
    """One card per number taken today. The caps decide how many he sees (`rank`)."""
    for fact in readings:
        numbers = _numbers(fact)
        if numbers is None or not day.same_day(fact.valid_from):
            continue
        lines = render(
            "reading",
            house.language,
            body=("reading", "reading_family" if house.who else "reading_alone"),
            top_number=numbers[0],
            bottom_number=numbers[1],
            who=house.who or "",
        )
        await make(
            type=CardType.READING,
            lines=lines,
            why=Why(
                kind="reading",
                plain=lines.why,
                fact_ids=(str(fact.id),),
                event_id=None if fact.event_id is None else str(fact.event_id),
            ),
            scope=Scope.READINGS,
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key=f"reading:{fact.id}",
            expires_at=day.ends_at,
        )


BRIEF_ON_THE_CARD = ("purpose", "bring")
"""What the visit card carries of the pre-visit brief (E05-01): who and when and what the visit
is about, and what to bring. The questions are their own card (E05-02); what changed is the
brief's own."""

MEMO_CARD_DAYS = timedelta(days=14)
"""How long the memos from a visit with nothing booked after it stay on his feed. With a
follow-up booked they stay until it: they are filed against it (E05-06)."""


def _ending_on(lines: Lines, carried: Sequence[str], boundary: str) -> Lines:
    """A card that repeats words from an inferring surface: those words, then that surface's
    boundary line, in print and in voice (the chemical name in brackets is not read aloud),
    and the line kept whole on the row (E16-01)."""
    closing = tuple(boundary.splitlines())
    return replace(
        lines,
        body=(*carried, *closing),
        voice=(*(spoken(line) for line in carried), *closing),
        boundary=boundary,
    )


async def _brief(
    session: AsyncSession, *, context: KeyContext, engine: Engine, appointment_id: uuid.UUID
) -> Brief | None:
    """The pre-visit brief for the visit card.

    Inside the week before a visit the feed is what asks for it — the T-minus trigger the
    brief waits for (E05-01) — so a key that may change the visits has it built, or gets the
    one State has not moved past; a key that only reads them gets the newest there is. A
    brief that cannot be built is refused inside its own savepoint, so nothing of it is kept
    but the refusal on the trail, and the card falls back to its template.
    """
    if not context.allows(Scope.VISITS):
        return None
    try:
        may_change_visits(context)
    except NotTheirsToChangeVisits:
        return await latest_brief(session, context=context, appointment_id=appointment_id)
    try:
        async with nested_unit_of_work(session):
            built = await brief_for(
                session, context=context, appointment_id=appointment_id, registry=engine.registry
            )
    except Refusal:
        return await latest_brief(session, context=context, appointment_id=appointment_id)
    return built


async def _visit(
    make: Any,
    session: AsyncSession,
    *,
    context: KeyContext,
    engine: Engine,
    state: StateView,
    day: Day,
    house: Household,
) -> None:
    """A visit inside the week. Its words are the pre-visit brief's (E05-01) — who and when,
    what it is about, what to bring — ending on the brief's boundary line; with no brief (a
    key that does not reach the visits, or one that could not be built) it is the template,
    which shows the booking back and infers nothing."""
    visit, doctor = await _next_visit(session, context=context, state=state)
    if visit is None:
        return
    at = datetime.fromisoformat(visit["at"])
    if day.same_day(at) or at > day.now + BEFORE_VISIT_WINDOW:
        return
    who = doctor or YOUR_DOCTOR[house.language]
    when = day.plain(at, house.language)
    lines = render("visit", house.language, body=("visit",), doctor=who, day=when)
    why = Why(kind="visit", plain=lines.why, visit_id=visit["id"])
    surface: Surface | None = None
    brief = await _brief(
        session, context=context, engine=engine, appointment_id=uuid.UUID(visit["id"])
    )
    # A stored brief is used only if it carries the brief's own boundary line: one written
    # before the line existed, or with other words, leaves the card to its template.
    if (
        brief is not None
        and brief.language == house.language
        and is_boundary_line(Surface.BRIEF, brief.boundary)
        and brief.boundary is not None
    ):
        carried = [
            str(line["text"]) for line in brief.lines if line["section"] in BRIEF_ON_THE_CARD
        ]
        if carried:
            surface = Surface.BRIEF
            lines = _ending_on(
                render("visit", house.language, doctor=who, day=when), carried, brief.boundary
            )
            why = Why(
                kind="visit",
                plain=lines.why,
                visit_id=visit["id"],
                brief_id=str(brief.id),
                fact_ids=tuple(brief.sources.get("gap_fact_ids", ())),
            )
    await make(
        type=CardType.VISIT,
        lines=lines,
        surface=surface,
        why=why,
        scope=Scope.VISITS,
        deliver_to=DeliverTo.PATIENT,
        day=day.key,
        dedupe_key=f"visit:{visit['id']}:{day.key}",
        expires_at=day.ends_at,
    )


async def _memos(
    make: Any, session: AsyncSession, *, context: KeyContext, day: Day, house: Household
) -> None:
    """What was agreed at the last visit, in his words (E05-06).

    The memos heard at the most recent visit that has any — the current ones, after
    consolidation, so two that say the same thing are one — on one card, until the
    appointment they are filed against has passed (two weeks, when nothing was booked after
    it). The card ends on the summary's boundary line: these are the doctor's words as Nura
    wrote them down (E16-01).
    """
    if not context.allows(Scope.VISITS):
        return
    memos = [
        memo
        for memo in (
            await consolidate_memos(session, context=context)
            if can_change_visits(context)
            else await current_memos(session, context=context)
        )
        if memo.source is MemoSource.VISIT
        and memo.source_id is not None
        and memo.language == house.language
    ]
    if not memos:
        return
    items = await audited_read(
        session,
        SummaryItem,
        context,
        Scope.VISITS,
        where=(SummaryItem.id.in_([memo.source_id for memo in memos]),),
    )
    summaries = await audited_read(
        session,
        VisitSummary,
        context,
        Scope.VISITS,
        where=(VisitSummary.id.in_(sorted({item.summary_id for item in items})),),
    )
    visit_of = {summary.id: summary.appointment_id for summary in summaries}
    heard_at = {item.id: visit_of.get(item.summary_id) for item in items}
    wanted = {one for one in heard_at.values() if one is not None} | {
        memo.appointment_id for memo in memos if memo.appointment_id is not None
    }
    booked = {
        appointment.id: appointment
        for appointment in await audited_read(
            session,
            Appointment,
            context,
            Scope.VISITS,
            where=(Appointment.id.in_(sorted(wanted)),),
        )
    }
    by_visit: dict[uuid.UUID, list[Memo]] = {}
    for memo in memos:
        visit_id = heard_at.get(memo.source_id) if memo.source_id is not None else None
        if visit_id is not None and visit_id in booked:
            by_visit.setdefault(visit_id, []).append(memo)
    if not by_visit:
        return
    visit = max((booked[one] for one in by_visit), key=lambda one: as_utc(one.scheduled_at))
    kept = by_visit[visit.id]
    until = max(
        [
            as_utc(visit.scheduled_at) + MEMO_CARD_DAYS,
            *(
                as_utc(booked[memo.appointment_id].scheduled_at)
                for memo in kept
                if memo.appointment_id is not None and memo.appointment_id in booked
            ),
        ]
    )
    if day.now > until:
        return
    providers = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.id == visit.provider_id,)
    )
    doctor = providers[0].name if providers else None
    lines = render(
        "memo",
        house.language,
        body=("memo",),
        doctor=doctor or YOUR_DOCTOR[house.language],
        day=day.plain(visit.scheduled_at, house.language),
    )
    lines = _ending_on(
        lines,
        [*lines.body, *(memo.text for memo in kept)],
        boundary_line(Surface.SUMMARY, house.language, doctor=doctor),
    )
    ids = tuple(str(memo.id) for memo in kept)
    digest = hashlib.sha256(" ".join(sorted(ids)).encode()).hexdigest()[:12]
    await make(
        type=CardType.MEMO,
        lines=lines,
        surface=Surface.SUMMARY,
        why=Why(
            kind="memo",
            plain=lines.why,
            visit_id=str(visit.id),
            memo_id=ids[0],
            memo_ids=ids,
        ),
        scope=Scope.VISITS,
        deliver_to=DeliverTo.PATIENT,
        day=day.key,
        dedupe_key=f"memo:{visit.id}:{digest}:{day.key}",
        expires_at=day.ends_at,
    )


async def _story(
    make: Any,
    session: AsyncSession,
    *,
    context: KeyContext,
    day: Day,
    house: Household,
    readings: Sequence[Fact],
) -> None:
    """Recall cards from his own record, a week at a time."""
    until = day.now + STORY_LIFETIME
    past = sorted(
        (fact for fact in readings if _numbers(fact) and not day.same_day(fact.valid_from)),
        key=lambda fact: as_utc(fact.valid_from),
        reverse=True,
    )
    for fact in past[:STORY_READINGS]:
        numbers = _numbers(fact)
        assert numbers is not None
        lines = render(
            "story_reading",
            house.language,
            body=("story_reading",),
            day=day.plain(fact.valid_from, house.language),
            top_number=numbers[0],
            bottom_number=numbers[1],
        )
        await make(
            type=CardType.STORY,
            lines=lines,
            why=Why(kind="story", plain=lines.why, fact_ids=(str(fact.id),)),
            scope=Scope.READINGS,
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key=f"story:reading:{fact.id}:{day.week}",
            expires_at=until,
        )
    if readings:
        lines = render(
            "story_count",
            house.language,
            body=(counted("story_count", len(readings)),),
            count=len(readings),
        )
        await make(
            type=CardType.STORY,
            lines=lines,
            why=Why(
                kind="story", plain=lines.why, fact_ids=tuple(sorted(str(f.id) for f in readings))
            ),
            scope=Scope.READINGS,
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key=f"story:count:{day.week}",
            expires_at=until,
        )
    if context.allows(Scope.RECORDS):
        papers: dict[uuid.UUID, list[Fact]] = {}
        for fact in await current_facts(session, context=context):
            if fact.artifact_id is not None and fact.subject != "blood_pressure":
                papers.setdefault(fact.artifact_id, []).append(fact)
        for artifact_id, facts in papers.items():
            first = min(facts, key=lambda fact: as_utc(fact.valid_from))
            lines = render(
                "story_paper",
                house.language,
                body=("story_paper",),
                test_name=test_name(first.subject, house.language),
                day=day.plain(first.valid_from, house.language),
                doctor=house.doctor or YOUR_DOCTOR[house.language],
            )
            await make(
                type=CardType.STORY,
                lines=lines,
                why=Why(
                    kind="story",
                    plain=lines.why,
                    artifact_id=str(artifact_id),
                    fact_ids=tuple(sorted(str(fact.id) for fact in facts)),
                ),
                scope=Scope.RECORDS,
                deliver_to=DeliverTo.PATIENT,
                day=day.key,
                dedupe_key=f"story:paper:{artifact_id}:{day.week}",
                expires_at=until,
            )
    if context.allows(Scope.NOTES):
        notes: Sequence[Note] = await list_notes(session, context=context)
        for note in notes[-3:]:
            lines = render(
                "story_note",
                house.language,
                body=("story_note",),
                extra=(note.text,),
                day=day.plain(note.written_at, house.language),
            )
            await make(
                type=CardType.STORY,
                lines=lines,
                why=Why(kind="story", plain=lines.why, note_id=str(note.id)),
                scope=Scope.NOTES,
                deliver_to=DeliverTo.PATIENT,
                day=day.key,
                dedupe_key=f"story:note:{note.id}:{day.week}",
                expires_at=until,
            )


def _gaps(state: StateView, medicines: Sequence[LineView] = ()) -> list[tuple[str, str, list[str]]]:
    """What the record holds that deserves an explainer: (term, scope word, fact ids). A
    medicine is one E04 reconciled into a line, or one a label card wrote as a fact."""
    clinical = state.dimension(Dimension.CLINICAL) or {}
    facts = clinical.get("facts", {})
    gaps: list[tuple[str, str, list[str]]] = []
    seen: set[str] = set()
    for view in medicines:
        term = view.line.generic.strip().lower()
        if term not in seen:
            seen.add(term)
            gaps.append((term, "medicines", [str(view.line.fact_id)]))
    for subject in ("medicine", "medication"):
        name = facts.get(subject, {}).get("name")
        if name and isinstance(name.get("value"), str):
            term = name["value"].strip().lower()
            if term not in seen:
                seen.add(term)
                gaps.append((term, "medicines", [name["fact_id"]]))
    if "blood_pressure" in facts:
        ids = [entry["fact_id"] for entry in facts["blood_pressure"].values()]
        gaps.append(("blood pressure", "readings", ids))
    return gaps


async def _learning(
    session: AsyncSession,
    *,
    context: KeyContext,
    engine: Engine,
    state: StateView,
    day: Day,
    house: Household,
    keys: set[str],
    medicines: Sequence[LineView] = (),
) -> list[FeedItem]:
    """A self-search for each gap State shows, run now against the fixture ports, its
    findings made into learning cards (or questions for the memo, or notices)."""
    from app.delivery.feed.models import SearchJob

    jobs = await audited_read(session, SearchJob, context, Scope.RECORDS)
    have = {(job.kind, tuple(job.terms)) for job in jobs}
    wanted: list[tuple[JobKind, str, str, list[str], str]] = []
    for term, scope_word, fact_ids in _gaps(state, medicines):
        wanted.append((JobKind.EXPLAINER, term, scope_word, fact_ids, "on_change"))
        if scope_word == "medicines":
            # Any medicine on the list starts a daily safety-notice job (spec §9).
            wanted.append((JobKind.SAFETY, term, scope_word, fact_ids, "daily"))
    found: list[FeedItem] = []
    for kind, term, scope_word, fact_ids, cadence in wanted:
        if (kind, (term,)) in have:
            continue
        job = await create_job(
            session,
            context=context,
            kind=kind,
            terms=[term],
            cadence=cadence,
            reason={
                "gap": f"no {kind.value} about {term}",
                "fact_ids": fact_ids,
                "scope": scope_word,
            },
        )
        found.extend(
            await run_job(
                session,
                context=context,
                job=job,
                engine=engine,
                state=state,
                language=house.language,
                day=day.key,
                doctor=house.doctor,
                existing=keys,
                format=_format_of(state),
            )
        )
    return found


__all__ = ["Day", "Event", "Flag", "Key", "can_compose", "plain_day", "refresh", "today_for"]
