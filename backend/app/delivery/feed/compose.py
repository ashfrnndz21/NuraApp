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
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read, audited_read, person_display_name
from app.audit.models import Action, Channel, Outcome
from app.audit.trail import record
from app.db import as_utc, nested_unit_of_work, utcnow
from app.delivery.feed.compress import changes_treatment
from app.delivery.feed.days import Day, plain_day, today_for
from app.delivery.feed.grammar import Direction
from app.delivery.feed.items import NotPlainWords, Why, create_item
from app.delivery.feed.local import HAZARDS, SEASONS, relevant_to
from app.delivery.feed.models import (
    PLAYS,
    CardFormat,
    CardType,
    DeliverTo,
    Engagement,
    EngagementKind,
    FeedItem,
    JobKind,
    SearchJob,
    Supply,
)
from app.delivery.feed.search import Around, Engine, create_job, due, pause_job, run_job
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
from app.delivery.voice import MAX_SECONDS, seconds_to_say, voiced
from app.drugs.registry import DrugRegistry, LabelFields, UnknownDrug
from app.errors import Refusal
from app.family.photos import photos_for_his_feed
from app.family.roster import who_is_on_duty
from app.identity.models import Profile
from app.keys.context import KeyContext
from app.keys.grants import list_keys
from app.keys.models import Key
from app.keys.scopes import KeyRole, Scope, scope_for_subject
from app.language.voice_script import script_for
from app.medicines.service import LineView, active_lines, proud_days
from app.memory.episodic import record_event
from app.memory.models import (
    Appointment,
    Artifact,
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
from app.reasoning.trends import trend
from app.reasoning.visits.brief import brief_for, latest_brief
from app.reasoning.visits.guard import (
    NotTheirsToChangeVisits,
    can_change_visits,
    may_change_visits,
)
from app.reasoning.visits.logistics import logistics_for
from app.reasoning.visits.memos import consolidate_memos, current_memos
from app.reasoning.visits.models import Brief, Memo, MemoSource, SummaryItem, VisitSummary
from app.reasoning.visits.strings import spoken
from app.safety.boundary import Surface, boundary_line, is_boundary_line
from app.safety.red_flags import Flag, open_flags
from app.state.dimensions import BEFORE_VISIT_WINDOW
from app.state.models import Dimension
from app.state.service import RECOMPUTE_SCOPES, StateView, current_state

log = logging.getLogger("nura.delivery.feed")

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
CLIPS_ATTRIBUTE, AS_CARDS = "clips", "card"
"""The fact the clip switch is written as (E11-08): `format.clips` is `card` once two clips
went unplayed, and a video then comes as a voice note instead of a clip."""
MISSES_TO_SWITCH = UNOPENED_TO_SWITCH
"""The configured misses (E11-08): how many unopened text cards, or clips seen and never
played, switch his feed to the other format."""
OPENED_KINDS: frozenset[EngagementKind] = frozenset(
    {
        EngagementKind.HEARD,
        EngagementKind.TAPPED,
        EngagementKind.PLAYED,
        EngagementKind.REPLAYED,
        EngagementKind.ASKED_MORE,
    }
)
"""What says he took up a text card, for the switch to voice: he heard it, played it, tapped
it or asked about it. A card that only rested on his screen does not count — a man who cannot
read it scrolls past it all the same, and it is him the switch is for. Never how long:
nothing here reads seconds."""



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
    every = await audited_read(session, FeedItem, context, Scope.PROFILE)
    existing = [item for item in every if as_utc(item.expires_at) > day.now]
    # Every card ever made here, expired or not: a card is made once per dedupe key, and the
    # table refuses a second (`uq_feed_item_dedupe`), so an expired card is never made again
    # under the same key — a card that comes round (a day's, a week's) has the day in its key.
    keys = {item.dedupe_key for item in every}
    recent = [item for item in every if as_utc(item.created_at) > day.now - UNOPENED_WINDOW]
    await _switch_format_if_ignored(session, context=context, day=day, items=recent)
    state = await current_state(session, context=context)
    format = _format_of(state)
    made: list[FeedItem] = []

    async def make(**values: Any) -> FeedItem | None:
        if values["dedupe_key"] in keys:
            return None
        values.setdefault("format", format)
        if values["type"] is CardType.FLAG:
            # A flag card is made first, on its own: nothing made after it can take it back.
            try:
                item = await create_item(session, context=context, state=state, **values)
            except NotPlainWords:
                return None
        else:
            # Every other card in its own savepoint: a refusal is written down, that card is
            # skipped, and the flag cards made before it stand.
            try:
                async with nested_unit_of_work(session):
                    item = await create_item(session, context=context, state=state, **values)
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
    await _logistics(
        make, session, context=context, engine=engine, state=state, day=day, house=house
    )
    memo_visits = await _visit_memos(session, context=context, house=house)
    on_memo_card = await _memos(make, day=day, house=house, visits=memo_visits)
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
    await _story(
        make,
        session,
        context=context,
        engine=engine,
        day=day,
        house=house,
        readings=readings,
        keys=keys,
        visits=memo_visits,
        on_memo_card=on_memo_card,
    )
    await _recap(
        make,
        day=day,
        house=house,
        story=[
            item
            for item in (*existing, *made)
            if item.type is CardType.STORY
            and item.scope is Scope.READINGS
            and item.dedupe_key.startswith("story:reading:")
            and item.dedupe_key.endswith(day.week)
        ],
        as_cards=_clips_as_cards(state),
    )
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
    await _say_ahead(session, engine, context, made)
    return state, made


VOICE_TARGET = "feed_item_voice"
"""What a pre-render's audit line names: not the card row itself (`feed_item`), its spoken
twin — so a render failure is told apart from a refusal to write the card."""


async def _say_ahead(
    session: AsyncSession, engine: Engine, context: KeyContext, items: Sequence[FeedItem]
) -> None:
    """Each new card's spoken twin, said and kept the moment the card is made (E22-03):
    through the one voice port, into the region's store, under the digest of the card's voice
    script — the same lines, language and boundary the twin route says (`twin.spoken_twin`),
    so the same key, and the first play is a read. A card with no voice in its language yet,
    or too long to say, is not said ahead; the route answers for it exactly as it always has.
    Both `engine.voice` and `engine.store` are optional on the Engine, so a test may build one
    without them and get the old behaviour; the running app never does — `_engine` in
    `app.channels.api.feed` always passes `providers.voice` (the fixture voice by default) and
    `providers.object_store` (required), so this runs on every refresh, including in dev.

    A render that fails — the language is not one there is a voice for, the lines run past
    thirty seconds, the store or the voice itself throws — never costs him the card: each
    item renders in a savepoint of its own, and nothing here is allowed to unmake a card
    `create_item` already wrote. But the failure is not swallowed either: it is written to
    the trail under `VOICE_TARGET`, on the card's own scope, the way any other refused write
    is (`app.audit.trail.record`), so the gap between "the card exists" and "its twin is
    ready" is visible to whoever reads the trail, not just to a log line nobody reads back.
    """
    if engine.voice is None or engine.store is None:
        return
    for item in items:
        try:
            async with nested_unit_of_work(session):
                await voiced(
                    engine.store,
                    engine.voice,
                    profile_id=context.profile_id,
                    region=context.region,
                    lines=list(item.voice or item.body),
                    language=item.language,
                    boundary=item.boundary,
                )
        except Exception as failed:  # noqa: BLE001 — a voice down never costs him a card
            log.warning("voice ahead failed for %s: %s", item.id, type(failed).__name__)
            try:
                async with nested_unit_of_work(session):
                    await record(
                        session,
                        context=context,
                        action=Action.WRITE,
                        scope=item.scope,
                        target=VOICE_TARGET,
                        target_id=item.id,
                        outcome=Outcome.REFUSED,
                        refused_because=type(failed).__name__,
                        channel=Channel.SYSTEM,
                    )
            except Exception as unwritten:  # noqa: BLE001 — see below
                # Writing the trail line is itself a write, and the one thing it must never do
                # is cost him the cards. Without this the failure leaves `_say_ahead`, leaves
                # `refresh`, and reaches the request's own unit of work, which rolls the whole
                # request back — every card `create_item` wrote in this refresh, not just the
                # one whose voice failed, and the trail lines the earlier items in this loop
                # had already earned. A voice that is down would take his day's cards with it.
                # So the trail line degrades to a log line, the same way `_sample` below keeps
                # its own bookkeeping from reaching the caller.
                log.warning(
                    "voice ahead failure not written for %s: %s", item.id, type(unwritten).__name__
                )
            continue


def _format_of(state: StateView) -> CardFormat:
    cognitive = state.dimension(Dimension.COGNITIVE) or {}
    preferred = cognitive.get("facts", {}).get(FORMAT_SUBJECT, {}).get(FORMAT_ATTRIBUTE, {})
    return CardFormat.VOICE_FIRST if preferred.get("value") == VOICE else CardFormat.TEXT


def _clips_as_cards(state: StateView) -> bool:
    """Whether two clips went unplayed and his videos now come as voice notes (E11-08)."""
    cognitive = state.dimension(Dimension.COGNITIVE) or {}
    held = cognitive.get("facts", {}).get(FORMAT_SUBJECT, {}).get(CLIPS_ATTRIBUTE, {})
    return held.get("value") == AS_CARDS


async def _switch_format_if_ignored(
    session: AsyncSession, *, context: KeyContext, day: Day, items: Sequence[FeedItem]
) -> None:
    """The format adapts to what he opens (E11-08, spec §3.9): two text cards from an earlier
    day that he never opened make his feed voice-first; two clips he had on his screen and
    never played make his videos come as voice notes. Each is a Fact resting on the moment it
    was noticed, which State folds, so the next snapshot says why the cards changed shape.
    What is counted is whether a card was opened or played — never for how long."""
    await _text_to_voice(session, context=context, day=day, items=items)
    await _clips_to_cards(session, context=context, day=day, items=items)


async def _engaged(
    session: AsyncSession, context: KeyContext, items: Sequence[FeedItem]
) -> dict[uuid.UUID, set[EngagementKind]]:
    """What he himself did with these cards. His chief reads the same cards on her list, and
    what she opens or plays is hers: it neither counts as his nor holds back his switch."""
    owner = (await audited_profile_read(session, context)).owner_person_id
    found = await audited_read(
        session,
        Engagement,
        context,
        Scope.PROFILE,
        where=(Engagement.item_id.in_([item.id for item in items]),),
    )
    kinds: dict[uuid.UUID, set[EngagementKind]] = {}
    for one in found:
        if one.person_id == owner:
            kinds.setdefault(one.item_id, set()).add(one.kind)
    return kinds


async def _his_word_stands(
    session: AsyncSession, *, context: KeyContext, attribute: str, value: str
) -> tuple[bool, uuid.UUID | None]:
    """Whether the switch is already made, or he chose the format himself — two missed cards
    do not overturn his word (`ConfirmedFactStands`). And the fact a new one supersedes."""
    already = await current_facts(
        session, context=context, subject=FORMAT_SUBJECT, attribute=attribute
    )
    stands = any(
        fact.value == value or fact.confidence_state is not ConfidenceState.EXTRACTED
        for fact in already
    )
    return stands, (already[0].id if already else None)


async def _text_to_voice(
    session: AsyncSession, *, context: KeyContext, day: Day, items: Sequence[FeedItem]
) -> None:
    """Two text cards from an earlier day, delivered to him, that he never opened: the profile
    goes voice-first, as a Fact resting on the moment it was noticed."""
    candidates = [
        item
        for item in items
        if item.deliver_to is DeliverTo.PATIENT
        and item.format is CardFormat.TEXT
        and item.supply in (Supply.TODAY, Supply.NOW)
        and not day.same_day(item.created_at)
    ]
    if len(candidates) < MISSES_TO_SWITCH:
        return
    engaged = await _engaged(session, context, candidates)
    ignored = [item for item in candidates if not engaged.get(item.id, set()) & OPENED_KINDS]
    if len(ignored) < MISSES_TO_SWITCH:
        return
    stands, supersedes = await _his_word_stands(
        session, context=context, attribute=FORMAT_ATTRIBUTE, value=VOICE
    )
    if stands:
        # Voice already, or a format he chose himself on his settings screen (E01-03).
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
        supersedes_id=supersedes,
    )


async def _clips_to_cards(
    session: AsyncSession, *, context: KeyContext, day: Day, items: Sequence[FeedItem]
) -> None:
    """Two clips from an earlier day that were on his screen and that he never played: his
    videos come as voice notes from now on (the backlog's "clip to card")."""
    clips = [
        item
        for item in items
        if item.deliver_to is DeliverTo.PATIENT
        and item.format is CardFormat.CLIP
        and not day.same_day(item.created_at)
    ]
    if len(clips) < MISSES_TO_SWITCH:
        return
    engaged = await _engaged(session, context, clips)
    played = PLAYS | {EngagementKind.HEARD}
    missed = [
        item
        for item in clips
        if EngagementKind.OPENED in engaged.get(item.id, set())
        and not engaged.get(item.id, set()) & played
    ]
    if len(missed) < MISSES_TO_SWITCH:
        return
    stands, supersedes = await _his_word_stands(
        session, context=context, attribute=CLIPS_ATTRIBUTE, value=AS_CARDS
    )
    if stands:
        return
    noticed = await record_event(
        session,
        context=context,
        kind=EventKind.ENGAGEMENT,
        occurred_at=day.now,
        label="two clips went unplayed",
        source_channel=SourceChannel.APP,
    )
    await assert_fact(
        session,
        context=context,
        subject=FORMAT_SUBJECT,
        attribute=CLIPS_ATTRIBUTE,
        value=AS_CARDS,
        confidence=0.8,
        event_id=noticed.id,
        supersedes_id=supersedes,
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
                    plain=CAREGIVER_SUPPRESSED_LINE.format(
                        name=house.profile.display_name,
                        feeling=flag.feeling.value,
                        reason=flag.suppressed_because,
                    ),
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


def _direction(numbers: tuple[int, int], before: tuple[int, int] | None) -> Direction | None:
    """Up, down or the same as the number before, by the top number; nothing to say when
    there is no number before. A direction, never a judgement of it."""
    if before is None:
        return None
    if numbers[0] > before[0]:
        return Direction.UP
    if numbers[0] < before[0]:
        return Direction.DOWN
    return Direction.SAME


async def _readings(make: Any, *, day: Day, house: Household, readings: Sequence[Fact]) -> None:
    """One card per number taken today. The caps decide how many he sees (`rank`). The card
    shows the one reading and its direction from the one before (E11-03)."""
    in_order = sorted(
        (fact for fact in readings if _numbers(fact) is not None),
        key=lambda fact: as_utc(fact.valid_from),
    )
    for index, fact in enumerate(in_order):
        numbers = _numbers(fact)
        if numbers is None or not day.same_day(fact.valid_from):
            continue
        before = _numbers(in_order[index - 1]) if index > 0 else None
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
            number=f"{numbers[0]}/{numbers[1]}",
            direction=_direction(numbers, before),
        )


ON_THE_LOGISTICS_CARD = frozenset(
    {"visit_with", "logistics_place", "logistics_no_place", "bring_bp_book", "bring_medicines"}
)
"""The logistics lines the feed's card may carry: the visits' part only (E05-03, ADR 0004).
The memos filed to bring are the visits' too (`section == "memo"`)."""

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


async def _logistics(
    make: Any,
    session: AsyncSession,
    *,
    context: KeyContext,
    engine: Engine,
    state: StateView,
    day: Day,
    house: Household,
) -> None:
    """The logistics card, the day before the next visit and on the day (E05-03), carrying
    only what its scope opens: a card is read by whoever holds its scope, and this one is the
    visits'. So it says when, where, and what to bring from the visit's own part — his blood
    pressure book, his medicines in their boxes (as the visit card's brief does), the memos
    filed to bring — each line the logistics card's own, through the verifier there and
    again here. Who drives him and the chief's note are the family list's, and his hospital
    letter is the record's: they are on the Visit screen, each read under its own scope, and
    never on a card a key without that part could read. A card that shows the booking back
    infers nothing, so it carries no boundary line."""
    if not context.allows(Scope.VISITS):
        return
    visit, _ = await _next_visit(session, context=context, state=state)
    if visit is None:
        return
    at = datetime.fromisoformat(visit["at"])
    on = as_utc(at).astimezone(day.tz).date()
    if on == day.local.date():
        headline = "logistics_today"
    elif on == day.local.date() + timedelta(days=1):
        headline = "logistics_tomorrow"
    else:
        return
    try:
        async with nested_unit_of_work(session):
            card = await logistics_for(
                session,
                context=context,
                appointment_id=uuid.UUID(visit["id"]),
                registry=engine.registry,
            )
    except Refusal:
        return
    shown = [
        line for line in card.lines if line.key in ON_THE_LOGISTICS_CARD or line.section == "memo"
    ]
    lines = render(
        "visit_logistics",
        house.language,
        headline=headline,
        extra=tuple(line.text for line in shown),
        doctor=card.doctor,
        day=day.plain(at, house.language),
    )
    lines = replace(lines, voice=tuple(line.spoken for line in shown))
    await make(
        type=CardType.VISIT_LOGISTICS,
        lines=lines,
        why=Why(kind="visit_logistics", plain=lines.why, visit_id=visit["id"]),
        scope=Scope.VISITS,
        deliver_to=DeliverTo.PATIENT,
        day=day.key,
        dedupe_key=f"logistics:{visit['id']}:{day.key}",
        expires_at=day.ends_at,
    )


STORY_VISITS = 2
"""How many visits before the one on the memo card tell again what the doctor said, a week."""
STORY_PHOTOS = 3
"""How many of the photos the family shared with a yes to his story become cards, newest."""


@dataclass(frozen=True, slots=True)
class VisitMemos:
    """What was agreed at one visit: the visit, the doctor, its current memos in his language,
    and until when the memo card carries them."""

    visit: Appointment
    doctor: str | None
    memos: tuple[Memo, ...]
    until: datetime
    clips: tuple[dict[str, Any], ...] = ()
    """Where each memo was said in the consult recording, when there is one (E21-03): the
    phone plays that stretch on a tap under the memo's own line, and nothing else."""

    def clips_for(self, memos: Sequence[Memo]) -> list[dict[str, Any]]:
        """The clips of these memos only, by their lines."""
        said = {memo.text for memo in memos}
        return [clip for clip in self.clips if clip["line"] in said]


async def _visit_memos(
    session: AsyncSession, *, context: KeyContext, house: Household
) -> list[VisitMemos]:
    """The memos heard at each visit that has any (E05-06) — the current ones, after
    consolidation, so two that say the same thing are one — newest visit first. A memo from a
    visit is written only on his yes to its card (`confirm_summary`), so every one here is from
    a card he confirmed. The memo card shows the newest; the story tells the ones before."""
    if not context.allows(Scope.VISITS):
        return []
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
        return []
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
        return []
    doctors = {
        provider.id: provider.name
        for provider in await audited_read(
            session,
            Provider,
            context,
            Scope.VISITS,
            where=(Provider.id.in_(sorted({booked[one].provider_id for one in by_visit})),),
        )
    }
    recording_of = {summary.id: summary.recording_artifact_id for summary in summaries}
    item_of = {item.id: item for item in items}
    found: list[VisitMemos] = []
    for visit_id, kept in by_visit.items():
        visit = booked[visit_id]
        doctor = doctors.get(visit.provider_id)
        clips: list[dict[str, Any]] = []
        for memo in kept:
            item = item_of.get(memo.source_id) if memo.source_id is not None else None
            heard_in = None if item is None else recording_of.get(item.summary_id)
            if (
                item is None
                or heard_in is None
                or item.clip_start_s is None
                or item.clip_end_s is None
            ):
                continue
            clips.append(
                {
                    "line": memo.text,
                    "artifact_id": str(heard_in),
                    "start_s": item.clip_start_s,
                    "end_s": item.clip_end_s,
                    "doctor": doctor or YOUR_DOCTOR[house.language],
                }
            )
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
        found.append(VisitMemos(visit, doctor, tuple(kept), until, tuple(clips)))
    return sorted(found, key=lambda one: as_utc(one.visit.scheduled_at), reverse=True)


async def _memos(
    make: Any, *, day: Day, house: Household, visits: Sequence[VisitMemos]
) -> uuid.UUID | None:
    """What was agreed at the last visit, in his words (E05-06).

    The memos of the most recent visit that has any, on one card, until the appointment they
    are filed against has passed (two weeks, when nothing was booked after it). The card ends
    on the summary's boundary line: these are the doctor's words as Nura wrote them down
    (E16-01). Returns the visit the card is about while it is on his feed, so the story does
    not tell the same visit twice.
    """
    if not visits:
        return None
    latest = visits[0]
    if day.now > latest.until:
        return None
    lines = render(
        "memo",
        house.language,
        body=("memo",),
        doctor=latest.doctor or YOUR_DOCTOR[house.language],
        day=day.plain(latest.visit.scheduled_at, house.language),
    )
    lines = _ending_on(
        lines,
        [*lines.body, *(memo.text for memo in latest.memos)],
        boundary_line(Surface.SUMMARY, house.language, doctor=latest.doctor),
    )
    ids = tuple(str(memo.id) for memo in latest.memos)
    digest = hashlib.sha256(" ".join(sorted(ids)).encode()).hexdigest()[:12]
    await make(
        type=CardType.MEMO,
        lines=lines,
        surface=Surface.SUMMARY,
        why=Why(
            kind="memo",
            plain=lines.why,
            visit_id=str(latest.visit.id),
            memo_id=ids[0],
            memo_ids=ids,
        ),
        scope=Scope.VISITS,
        deliver_to=DeliverTo.PATIENT,
        day=day.key,
        dedupe_key=f"memo:{latest.visit.id}:{digest}:{day.key}",
        expires_at=day.ends_at,
        cite={"clips": list(latest.clips)} if latest.clips else None,
    )
    return latest.visit.id


async def _story(
    make: Any,
    session: AsyncSession,
    *,
    context: KeyContext,
    engine: Engine,
    day: Day,
    house: Household,
    readings: Sequence[Fact],
    keys: set[str],
    visits: Sequence[VisitMemos],
    on_memo_card: uuid.UUID | None,
) -> None:
    """Story cards from his own record, a week at a time (E21-05): past numbers from his
    book and how the last one moved, a lab result that moved against its range, what the
    doctor said at a visit whose card he confirmed, his papers, his own notes, the photos
    the family shared with a yes to his story, and the number that only goes up. Each is
    made again the next week from what memory holds then (`STORY_LIFETIME`, the ISO week in
    every dedupe key); the number that only goes up is made each day, so it is that day's."""
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
            number=f"{numbers[0]}/{numbers[1]}",
        )
    await _story_change(make, day=day, house=house, past=past, until=until)
    await _story_trends(
        make, session, context=context, engine=engine, day=day, house=house, keys=keys, until=until
    )
    await _story_doctor(
        make,
        context=context,
        day=day,
        house=house,
        visits=visits,
        on_memo_card=on_memo_card,
        until=until,
    )
    if context.allows(Scope.RECORDS):
        # A story about a paper is the record's card (`scope=RECORDS`), so it names only what
        # a key to the record reads: a paper kept under the record's scope — the family's
        # message is not a paper — and the record's facts on it. A medicine fact on a label
        # photo is the medicines'; the photo is still one of his papers, and the card cites
        # the photo and not the fact.
        papers: dict[uuid.UUID, list[Fact]] = {}
        for fact in await current_facts(session, context=context):
            if fact.artifact_id is not None and fact.subject != "blood_pressure":
                papers.setdefault(fact.artifact_id, []).append(fact)
        if papers:
            kept = await audited_read(
                session,
                Artifact,
                context,
                Scope.RECORDS,
                where=(
                    Artifact.id.in_(sorted(papers, key=str)),
                    Artifact.written_scope == Scope.RECORDS,
                ),
            )
            on_the_record = {artifact.id for artifact in kept}
            papers = {ident: facts for ident, facts in papers.items() if ident in on_the_record}
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
                    fact_ids=tuple(
                        sorted(
                            str(fact.id)
                            for fact in facts
                            if scope_for_subject(fact.subject) is Scope.RECORDS
                        )
                    ),
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
    await _story_photos(make, session, context=context, day=day, house=house, until=until)
    await _story_proud(make, session, context=context, day=day, house=house)


async def _story_change(
    make: Any, *, day: Day, house: Household, past: Sequence[Fact], until: datetime
) -> None:
    """How his blood pressure moved (E21-05): the last number from his book, the one before
    it, and which way the top number went — arithmetic, a direction and never a judgement.
    Nothing is said about a range: his book prints none, and a number is placed against a
    range only beside the lab's own (`app.delivery.trend_strings`)."""
    if len(past) < 2:
        return
    latest, before = past[0], past[1]
    now, was = _numbers(latest), _numbers(before)
    assert now is not None and was is not None
    direction = _direction(now, was)
    assert direction is not None
    moved = {Direction.UP: "story_up", Direction.DOWN: "story_down", Direction.SAME: "story_same"}
    earlier = render(
        "story_reading",
        house.language,
        body=("story_change_before", moved[direction]),
        day=day.plain(before.valid_from, house.language),
        top_number=was[0],
        bottom_number=was[1],
    ).body
    lines = render(
        "story_change",
        house.language,
        body=("story_change",),
        why="story_reading",
        extra=earlier,
        day=day.plain(latest.valid_from, house.language),
        top_number=now[0],
        bottom_number=now[1],
    )
    await make(
        type=CardType.STORY,
        lines=lines,
        why=Why(kind="story", plain=lines.why, fact_ids=(str(latest.id), str(before.id))),
        scope=Scope.READINGS,
        deliver_to=DeliverTo.PATIENT,
        day=day.key,
        dedupe_key=f"story:change:{latest.id}:{day.week}",
        expires_at=until,
        number=f"{now[0]}/{now[1]}",
        direction=direction,
    )


async def _story_trends(
    make: Any,
    session: AsyncSession,
    *,
    context: KeyContext,
    engine: Engine,
    day: Day,
    house: Household,
    keys: set[str],
    until: datetime,
) -> None:
    """A lab result that moved, against its range (E09-01, E21-05): for each result he has
    confirmed twice or more, the trend's own lines — the latest number and its day, the range,
    where it sits only against the lab's own range, how it moved — ending on the trend's
    boundary line. Made once a week per result: a trend is rendered (and kept) only when this
    week's card for it is not there yet."""
    ranges = engine.ranges
    if ranges is None or not await can_compose(context):
        return
    confirmed = [
        fact
        for fact in await current_facts(session, context=context)
        if fact.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
    ]
    for analyte in ranges.analytes():
        key = f"story:trend:{analyte.id}:{day.week}"
        if key in keys:
            continue
        results = [
            fact
            for fact in confirmed
            if (fact.subject, fact.attribute) == (analyte.subject, analyte.attribute)
        ]
        if len(results) < 2:
            continue
        try:
            async with nested_unit_of_work(session):
                told = await trend(
                    session,
                    context=context,
                    ranges=ranges,
                    analyte=analyte.id,
                    language=house.language,
                )
        except Exception as failed:  # noqa: BLE001 — a voice down never costs him a card
            log.warning("voice ahead skipped: %s", type(failed).__name__)
            continue
        if told.direction_since is None:
            continue
        head = render("story_trend", house.language)
        lines = Lines(
            language=told.language,
            headline=head.headline,
            body=tuple(told.lines),
            voice=tuple(told.lines),
            why=head.why,
            boundary=told.boundary,
        )
        await make(
            type=CardType.STORY,
            lines=lines,
            surface=Surface.TREND,
            why=Why(
                kind="story",
                plain=lines.why,
                fact_ids=tuple(str(point.fact_id) for point in told.points),
            ),
            scope=scope_for_subject(analyte.subject),
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key=key,
            expires_at=until,
        )


async def _story_doctor(
    make: Any,
    *,
    context: KeyContext,
    day: Day,
    house: Household,
    visits: Sequence[VisitMemos],
    on_memo_card: uuid.UUID | None,
    until: datetime,
) -> None:
    """What the doctor said (E21-05): the memos of a visit whose card he confirmed, told
    again as his story — each visit but the one the memo card is showing, so no visit is told
    twice at once. The words are the memos', ending on the summary's boundary line, as on the
    memo card: they are the doctor's words as Nura wrote them down (E16-01)."""
    if not context.allows(Scope.VISITS):
        return
    for one in [each for each in visits if each.visit.id != on_memo_card][:STORY_VISITS]:
        # A memo about a medicine may have been changed at a later visit; only the memo card,
        # which is the latest visit's, carries those. The story tells the rest.
        told = tuple(memo for memo in one.memos if "medicine" not in (memo.slots or {}))
        if not told:
            continue
        lines = render(
            "memo",
            house.language,
            body=("story_doctor",),
            doctor=one.doctor or YOUR_DOCTOR[house.language],
            day=day.plain(one.visit.scheduled_at, house.language),
        )
        lines = _ending_on(
            lines,
            [*lines.body, *(memo.text for memo in told)],
            boundary_line(Surface.SUMMARY, house.language, doctor=one.doctor),
        )
        ids = tuple(str(memo.id) for memo in told)
        await make(
            type=CardType.STORY,
            lines=lines,
            surface=Surface.SUMMARY,
            why=Why(
                kind="story",
                plain=lines.why,
                visit_id=str(one.visit.id),
                memo_id=ids[0],
                memo_ids=ids,
            ),
            scope=Scope.VISITS,
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key=f"story:doctor:{one.visit.id}:{day.week}",
            expires_at=until,
            # The same clips the memo card carries (E21-03), for the memos this card tells.
            cite={"clips": one.clips_for(told)} if one.clips_for(told) else None,
        )


async def _story_photos(
    make: Any,
    session: AsyncSession,
    *,
    context: KeyContext,
    day: Day,
    house: Household,
    until: datetime,
) -> None:
    """The photos the family shared with a yes to his story (E21-05), the newest few. The
    photo is the family's, so the card is the family scope's and a key without it never sees
    one; the card names the photo, which is read through the thread; a photo its sharer takes
    back is not shown again (`rank`), and none is made of it."""
    if not context.allows(Scope.FAMILY):
        return
    shared = await photos_for_his_feed(session, context=context)
    for photo in reversed(shared[-STORY_PHOTOS:]):
        who = await person_display_name(session, context, photo.author_person_id)
        if not who:
            continue
        lines = render(
            "story_photo",
            house.language,
            body=("story_photo",),
            who=who,
            day=day.plain(photo.posted_at, house.language),
        )
        await make(
            type=CardType.STORY,
            lines=lines,
            why=Why(
                kind="story",
                plain=lines.why,
                photo_id=str(photo.id),
                artifact_id=str(photo.artifact_id),
            ),
            scope=Scope.FAMILY,
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key=f"story:photo:{photo.id}:{day.week}",
            expires_at=until,
        )


async def _story_proud(
    make: Any, session: AsyncSession, *, context: KeyContext, day: Day, house: Household
) -> None:
    """The number that only goes up (E21-05): the days he has taken his tablets — the same
    count the Me page shows (`GET /profiles/{id}/me-summary`, `proud_days`), never a count
    of things written down. Made each day, so the card says that day's number."""
    if not context.allows(Scope.MEDICINES):
        return
    days = (await proud_days(session, context=context)).days
    if not days:
        return
    lines = render("story_count", house.language, body=(counted("story_count", days),), count=days)
    await make(
        type=CardType.STORY,
        lines=lines,
        why=Why(kind="story", plain=lines.why),
        scope=Scope.MEDICINES,
        deliver_to=DeliverTo.PATIENT,
        day=day.key,
        dedupe_key=f"story:proud:{day.key}",
        expires_at=day.ends_at,
        number=str(days),
        direction=Direction.UP,
    )


RECAP_LINES = 3
"""How many of the week's numbers the recap says: as many as fit in thirty seconds, at most three."""


async def _recap(
    make: Any, *, day: Day, house: Household, story: Sequence[FeedItem], as_cards: bool
) -> None:
    """His week in 30 seconds (E11-09): the first line of this week's story cards from his
    blood pressure book — his own numbers, in his words — narrated over a still with captions,
    once a week. It repeats the record and infers nothing, so it carries no boundary line. Two
    of them or none: one number is not a week. When his clips have gone unplayed it is a voice
    note instead (E11-08)."""
    if len(story) < 2:
        return
    chosen = list(reversed(story[:RECAP_LINES]))
    head = render("recap", house.language, body=("recap_intro",), why="story_reading")
    while True:
        lines = (*head.body, *(item.body[0] for item in chosen))
        spoken = script_for(lines, head.language).spoken()
        if seconds_to_say(spoken, head.language) <= MAX_SECONDS or len(chosen) <= 2:
            break
        chosen = chosen[1:]
    if seconds_to_say(script_for(lines, head.language).spoken(), head.language) > MAX_SECONDS:
        return
    # His week is his own story cards read back, so nothing here should ever read as a change
    # to his treatment — but it is screened like every other card that reaches him rather than
    # trusted because of where it came from. A line that would change treatment stops the
    # recap: it belongs in a question for his doctor, never in a card he plays to himself.
    if changes_treatment(list(lines)):
        return
    await make(
        type=CardType.RECAP,
        lines=Lines(
            language=head.language, headline=head.headline, body=lines, voice=lines, why=head.why
        ),
        why=Why(
            kind="recap",
            plain=head.why,
            fact_ids=tuple(sorted({one for item in chosen for one in item.why.get("fact_ids", [])})),
        ),
        scope=Scope.READINGS,
        deliver_to=DeliverTo.PATIENT,
        day=day.key,
        dedupe_key=f"recap:{day.week}",
        expires_at=day.week_ends_at,
        format=CardFormat.VOICE_FIRST if as_cards else CardFormat.CLIP,
        cite={"recap": True, "story_item_ids": [str(item.id) for item in chosen]},
    )


CONDITION_TERMS: Mapping[str, str] = {"high_blood_pressure": "blood pressure"}
"""What a self-search asks the allowlisted sources about for a condition he told (E01): the
condition's code in words ("diabetes", "kidneys"), except where the record already searches
for the same thing under another name — high blood pressure is the blood pressure search."""

DECLINED_TOPIC = "declined_topic"
"""The subject of the topic-level "not for me" fact (RE-07): the attribute is the catalogue
topic code (`app.delivery.recommend.models.Candidate.topic`), the value idle, and the window
thirty days — a Fact with a validity window and a confidence state (CLAUDE.md), not a new
column. `app.delivery.feed.engagement` writes it; `_declined_topics` below reads it back.
Distinct from `rank.DECLINED`, which is per card *type* and holds only for the rest of his
day — this is per *topic* and holds for thirty days, so a rule that would otherwise keep
proposing the same topic every week stays quiet about it that long."""

DECLINED_TOPIC_WINDOW = timedelta(days=30)


async def _declined_topics(
    session: AsyncSession, *, context: KeyContext, at: datetime
) -> frozenset[str]:
    """The topic codes he said "not for me" to, still inside their thirty days at `at`
    (`current_facts` already answers only what is inside its window)."""
    facts = await current_facts(session, context=context, subject=DECLINED_TOPIC, at=at)
    return frozenset(fact.attribute for fact in facts)


def _topic_term(topic: str, *, medicines_by_plain_id: Mapping[str, str]) -> tuple[str, str] | None:
    """The plain search term and scope word a broker topic (RE-04 code) asks the allowlist
    about — the same words `_gaps` already asks for a medicine or a condition, so a broker-
    found gap and a State-found gap share one card rather than drifting into two searches for
    the same thing. `None` for a topic this function cannot place a search for (a sensitive
    topic, or a medicine this key's own lines do not name — never guessed)."""
    family, _, code = topic.partition(".")
    if family == "medicine":
        term = medicines_by_plain_id.get(code)
        return (term, "medicines") if term else None
    if family == "condition":
        return (CONDITION_TERMS.get(code, code.replace("_", " ")), "records")
    return None


def _plain_name_ids(registry: DrugRegistry, medicines: Sequence[str]) -> dict[str, str]:
    """Which of his own medicine generics answer which licensed `plain_name_id` (module doc
    of `app.delivery.recommend.rules`): the one lookup `_topic_term` needs to turn a
    `medicine.<plain_name_id>` topic back into the generic his record actually holds."""
    by_id: dict[str, str] = {}
    for generic in medicines:
        try:
            monograph = registry.monograph(generic)
        except UnknownDrug:
            continue
        if monograph.plain_name_id:
            by_id.setdefault(monograph.plain_name_id, generic)
    return by_id


async def _broker_wanted(
    session: AsyncSession,
    *,
    context: KeyContext,
    engine: Engine,
    state: StateView,
    around: Around,
    moment: datetime,
) -> list[tuple[JobKind, tuple[str, ...], str, list[str], dict[str, Any]]]:
    """The slate's READ and CLIP candidates, turned into `_learning`'s `wanted` shape (RE-07,
    docs/recommendation-engine.md §2.6: "`wanted` gains the slate's READ topics"). Ranked
    first, so they lead: the broker's own `RuleRanker` has already ordered `result.candidates`
    best first, deterministically (its own tie-break), and this function only ever narrows
    that order — drops what he has said "not for me" to in the last thirty days, and collapses
    a rule's READ and its CLIP for the same topic into one watch, keeping the higher-ranked
    entry's rule id and boosts. It never widens what the broker already dropped: every
    candidate here already passed `Candidate.readable_by(context)` inside `slate()` itself, so
    nothing a withheld scope rests on ever reaches this list, let alone a card.

    Imported here, not at module level: `app.delivery.recommend` reaches `app.onboarding`
    (for the topic catalogue), and `app.onboarding.settings` reaches back to this module for
    `FORMAT_SUBJECT`/`FORMAT_ATTRIBUTE` — a real cycle a top-level import would hit the moment
    either module loaded first. Deferring it here, at call time, is enough: by then every
    module involved has finished initialising."""
    from app.delivery.recommend.broker import slate as recommend_slate
    from app.delivery.recommend.models import OutputKind as RecommendOutputKind

    result = await recommend_slate(
        session, context=context, state=state, registry=engine.registry, now=moment
    )
    declined = await _declined_topics(session, context=context, at=moment)
    by_plain_id = _plain_name_ids(engine.registry, around.medicines)
    wanted: list[tuple[JobKind, tuple[str, ...], str, list[str], dict[str, Any]]] = []
    queued: set[str] = set()
    for candidate in result.candidates:
        if candidate.output not in (RecommendOutputKind.READ, RecommendOutputKind.CLIP):
            continue
        if candidate.topic in declined or candidate.topic in queued:
            continue
        mapped = _topic_term(candidate.topic, medicines_by_plain_id=by_plain_id)
        if mapped is None:
            continue
        term, scope_word = mapped
        queued.add(candidate.topic)
        fact_ids = sorted({f"{item.kind}:{item.id}" for item in candidate.because})
        wanted.append(
            (
                JobKind.WORTH_KNOWING,
                (term,),
                scope_word,
                fact_ids,
                {
                    "rule": candidate.rule_id,
                    "boosts": list(candidate.boosts),
                    "topic": candidate.topic,
                    # The gap the independent safety review found (item 2): a candidate
                    # resting on his own private curiosity (§3.5) named it on `Candidate.
                    # private_to`, but nothing carried it past this dict — `run_job` below
                    # never read it back onto `create_item`, so the card it becomes would
                    # have shown to every key that holds its scope, private or not. `job.
                    # reason` is JSON (`SearchJob.reason`), so the id is a string here and
                    # `run_job` parses it back to a `uuid.UUID`, the same shape `rule`/
                    # `topic` already travel in.
                    "private_to": str(candidate.private_to)
                    if candidate.private_to is not None
                    else None,
                },
            )
        )
    return wanted


def _gaps(state: StateView, medicines: Sequence[LineView] = ()) -> list[tuple[str, str, list[str]]]:
    """What the record holds that deserves an explainer: (term, scope word, fact ids). A
    medicine is one E04 reconciled into a line, or one a label card wrote as a fact; a
    condition is one he told when his profile was set up or on his settings screen (E01,
    a `condition.<code>` fact that holds), so a learning card can be made for each condition
    as well as each medicine (E21-06)."""
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
    for code, entry in sorted(facts.get("condition", {}).items()):
        if entry.get("value") is not True:
            continue
        term = CONDITION_TERMS.get(code, code.replace("_", " "))
        if term not in seen:
            seen.add(term)
            gaps.append((term, "records", [entry["fact_id"]]))
    if "blood_pressure" in facts and "blood pressure" not in seen:
        ids = [entry["fact_id"] for entry in facts["blood_pressure"].values()]
        gaps.append(("blood pressure", "readings", ids))
    return gaps


FOOD_TERMS: Mapping[str, str] = {
    "diabetes": "diabetes",
    "high_blood_pressure": "blood pressure",
    "cholesterol": "cholesterol",
}
"""The conditions a weekly food card is for, and the term its search asks about."""


def _conditions_of(state: StateView) -> dict[str, str]:
    """The conditions he told (E01) that hold, by code, with the fact each rests on."""
    clinical = state.dimension(Dimension.CLINICAL) or {}
    return {
        code: entry["fact_id"]
        for code, entry in sorted(clinical.get("facts", {}).get("condition", {}).items())
        if entry.get("value") is True
    }


def _generic_of(registry: DrugRegistry, written: str) -> str | None:
    """The generic the licensed register gives a medicine's name as his record wrote it, or
    nothing where the register knows no such medicine.

    Which written name is which medicine — its salts, its strengths, the other names for it —
    is the licensed data's to say and no one else's (CLAUDE.md), so this asks the register
    rather than tidying the string itself. A name it does not know matches no hazard rule,
    which is the same answer a table of our own would have to give.
    """
    matches = registry.identify(LabelFields(generic=written.strip()))
    return matches[0].generic.strip().lower() if matches else None


async def around_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    engine: Engine,
    state: StateView,
    day: Day,
    profile: Profile | None = None,
    medicines: Sequence[LineView] | None = None,
) -> Around:
    """What a search job run needs to know about him besides the State: the day, his area,
    his conditions and medicines (by fact), and the formats his feed has settled on."""
    profile = profile if profile is not None else await audited_profile_read(session, context)
    if medicines is None:
        medicines = (
            await active_lines(
                session,
                context=context,
                registry=engine.registry,
                language=language_for(profile.language),
            )
            if context.allows(Scope.MEDICINES)
            else []
        )
    conditions = _conditions_of(state)
    taken: dict[str, str] = {
        view.line.generic.strip().lower(): str(view.line.fact_id) for view in medicines
    }
    clinical = (state.dimension(Dimension.CLINICAL) or {}).get("facts", {})
    for subject in ("medicine", "medication"):
        name = clinical.get(subject, {}).get("name")
        if name and isinstance(name.get("value"), str):
            generic = _generic_of(engine.registry, name["value"])
            if generic is not None:
                taken.setdefault(generic, name["fact_id"])
    return Around(
        day=day,
        area=profile.area,
        conditions=tuple(conditions),
        medicines=tuple(sorted(taken)),
        format=_format_of(state),
        clips_as_cards=_clips_as_cards(state),
        fact_ids={
            **{code: (fact,) for code, fact in conditions.items()},
            **{name: (fact,) for name, fact in taken.items()},
        },
    )


LEARNING_CARD_TYPES = frozenset(
    {CardType.LEARNING, CardType.CLIP, CardType.LOCAL, CardType.SEASONAL, CardType.FOOD}
)
"""What a `run_job` call above can turn a job into (`_shape`, `app/delivery/feed/search.py`) —
every card type that counts as "a learning card today" for the catch-up check below. `NOTICE`
and `RECALL_ACTION` are a safety job's own cards, never this supply's, so they are not here."""

MAX_CATCH_UP_JOBS = 3
"""When nothing has run for him today at all — not a new gap, not a job whose own cadence
made it due — force at most this many of the oldest enabled jobs to run anyway, so the first
open of a new day is never met with only what already expired (live-run defect: "no learning
cards appear", `GET /feed` showing none of READ, CLIP or "Did you know"). Bounded, the same
way every other inline compose step already is, so one open of the feed can never fan out into
an unbounded run of searches."""


def _last_run(job: SearchJob, day: Day) -> datetime | None:
    """`job.last_run_at`, tz-aware — `due()`'s own normalisation, reused here so "did this run
    today" is answered the same way `due()` answers "is this due"."""
    if job.last_run_at is None:
        return None
    return job.last_run_at if job.last_run_at.tzinfo else job.last_run_at.replace(tzinfo=day.now.tzinfo)


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
    """The self-searches his record calls for, run against the allowlist, their findings made
    into cards (or questions for the memo, or notices for his chief):

    - an explainer for each gap State shows, and a daily safety job for each medicine;
    - a daily local watch for each hazard a condition or medicine of his makes relevant
      (E09-07) — the bulletins matched to his area here, never searched by it;
    - a weekly watch for each season his conditions make relevant, where the planner may add
      it (the fasting month is added by a person, never guessed);
    - one weekly food watch across his conditions (a new one pauses the one it replaces).

    A new job runs now; a daily or weekly one that has not run today or this week runs again;
    a paused one does not run."""
    # #236: ordered, and with `SearchJob.id` as a tie-break — two jobs created in the same
    # transaction can share a `created_at` to the microsecond, and a job's own dedupe key is
    # now scoped to it (`search._key_for`), but the order jobs run in still decides the order
    # `rejected`/`made` come back in below, which a deployment may log or show; that order is
    # never left to storage to decide.
    jobs = list(
        await audited_read(
            session,
            SearchJob,
            context,
            Scope.RECORDS,
            order_by=(SearchJob.created_at.asc(), SearchJob.id.asc()),
        )
    )
    have = {(job.kind, tuple(job.terms)) for job in jobs}
    around = await around_for(
        session,
        context=context,
        engine=engine,
        state=state,
        day=day,
        profile=house.profile,
        medicines=medicines,
    )
    wanted: list[tuple[JobKind, tuple[str, ...], str, list[str], dict[str, Any]]] = []
    # RE-07: the broker's slate leads — its READ and CLIP candidates are already ranked best
    # first (`RuleRanker`), so queuing them ahead of the plain gaps below is what makes a new
    # medicine's explainer and clip lead this week's learning supply, not an accident of dict
    # or set order (the "hard-won rule" on tie-breaks, CLAUDE.md).
    wanted.extend(
        await _broker_wanted(
            session,
            context=context,
            engine=engine,
            state=state,
            around=around,
            moment=day.now,
        )
    )
    for term, scope_word, fact_ids in _gaps(state, medicines):
        wanted.append((JobKind.EXPLAINER, (term,), scope_word, fact_ids, {}))
        if scope_word == "medicines":
            # Any medicine on the list starts a daily safety-notice job (spec §9).
            wanted.append((JobKind.SAFETY, (term,), scope_word, fact_ids, {}))
    for hazard in HAZARDS:
        reasons = relevant_to(hazard, around.conditions, around.medicines)
        if reasons:
            ids = sorted({one for reason in reasons for one in around.fact_ids.get(reason, ())})
            wanted.append((JobKind.LOCAL, (hazard,), "records", ids, {}))
    for season in SEASONS:
        if season.planned and season.conditions & set(around.conditions):
            ids = sorted(
                {one for code in season.conditions for one in around.fact_ids.get(code, ())}
            )
            wanted.append((JobKind.SEASONAL, (season.term,), "records", ids, {}))
    food = tuple(sorted({FOOD_TERMS[code] for code in around.conditions if code in FOOD_TERMS}))
    if food:
        ids = sorted({one for code in FOOD_TERMS for one in around.fact_ids.get(code, ())})
        wanted.append((JobKind.FOOD, food, "records", ids, {}))
    found: list[FeedItem] = []
    ran: set[uuid.UUID] = set()
    for kind, terms, scope_word, fact_ids, extra in wanted:
        if (kind, terms) in have:
            continue
        if kind is JobKind.FOOD:
            # His conditions changed: the food watch for the old ones stops, this one starts.
            for old in jobs:
                if old.kind is JobKind.FOOD and old.enabled and old.reason.get("planned"):
                    await pause_job(session, context=context, job_id=old.id, enabled=False)
        job = await create_job(
            session,
            context=context,
            kind=kind,
            terms=list(terms),
            reason={
                "gap": f"no {kind.value} about {' and '.join(terms)}",
                "fact_ids": fact_ids,
                "scope": scope_word,
                "planned": True,
                **extra,
            },
        )
        have.add((kind, terms))
        ran.add(job.id)
        found.extend(
            await run_job(
                session,
                context=context,
                job=job,
                engine=engine,
                state=state,
                language=house.language,
                around=around,
                doctor=house.doctor,
                existing=keys,
            )
        )
    for job in jobs:
        if job.id in ran or not due(job, day):
            continue
        found.extend(
            await run_job(
                session,
                context=context,
                job=job,
                engine=engine,
                state=state,
                language=house.language,
                around=around,
                doctor=house.doctor,
                existing=keys,
            )
        )
        ran.add(job.id)
    if not found:
        # Defect: "Pa's feed never creates learning jobs" — the old guard here was `not ran`,
        # which only says no job was *attempted* today; a job that ran and simply found
        # nothing (the search came back empty, everything it found was already shown) still
        # landed in `ran`, so a day where every attempt came up empty looked, wrongly, like a
        # day that needed no catching up. What actually matters is whether he has a learning
        # card *today* at all — so this reads the day's own cards back, not the jobs' own
        # bookkeeping.
        today_cards = await audited_read(
            session,
            FeedItem,
            context,
            Scope.PROFILE,
            where=(FeedItem.day == day.key, FeedItem.type.in_(LEARNING_CARD_TYPES)),
        )
        if not today_cards:
            # Nothing at all became a learning card for him today: no new gap opened a job,
            # no existing job's own cadence said it was due (an "on_change" explainer that
            # already ran once, a weekly watch not due till later this week, ...), and no
            # attempt today turned into a card either. Rather than the first open of the day
            # showing only yesterday's cards — or nothing, once they expire — force the most
            # overdue enabled jobs that have not already been tried this call to run anyway,
            # oldest first, capped at `MAX_CATCH_UP_JOBS` so this can never fan out into an
            # unbounded run of searches.
            overdue = sorted(
                (job for job in jobs if job.enabled and job.id not in ran),
                key=lambda job: _last_run(job, day) or datetime.min.replace(tzinfo=UTC),
            )
            for job in overdue[:MAX_CATCH_UP_JOBS]:
                found.extend(
                    await run_job(
                        session,
                        context=context,
                        job=job,
                        engine=engine,
                        state=state,
                        language=house.language,
                        around=around,
                        doctor=house.doctor,
                        existing=keys,
                    )
                )
                ran.add(job.id)
    log.info("feed: ran %d learning jobs for the day", len(ran))
    return found


__all__ = ["Day", "Event", "Flag", "Key", "can_compose", "plain_day", "refresh", "today_for"]
