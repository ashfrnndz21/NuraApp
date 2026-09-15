"""The profile's settings (E01-03): his conditions, his language, how much goes on a screen,
what helps him read and hear, what helps him remember, the name he goes by, his doctor's
name and his breakfast time.

**Who may write.** The owner, and a chief — the steward who set the profile up for him is
one until he claims it (`app.identity.doors`). Anyone else is refused `NotTheirsToSetUp`
(403), on the trail. A save is the person's own word and is written down as his yes: every
fact it writes is CONFIRMED_BY_PERSON, on a Confirmation minted and spent in the same request
for exactly that fact (`app.keys.confirm`), the way a reading he typed is.

**What a key may read** (`GET /profiles/{id}/settings`).

- Every key opens the face of the graph (`Scope.PROFILE`), and reads how to talk to him and
  when: the language, the density, large text, high contrast, voice, big targets, one thing
  per screen, read-back, repeated prompts, the name he goes by and his breakfast time. A
  helper needs these to help him; none of them is his health.
- A key to the record (`Scope.RECORDS`: the owner, a chief, a caregiver, a clinic) reads the
  conditions and the doctor's name as well. They are his health record: a helper's or a
  viewer's key does not open them, and the answer names them as `withheld` rather than
  leaving them empty. When the owner marks the record "only me", the key resolver takes
  RECORDS out of every key (`app.keys.privacy`), and a caregiver's read withholds them too.
- A caregiver reads; a caregiver never writes.

**Settings as facts.** Each setting is also a fact resting on the event of the save, under a
subject State already classifies, so the cognitive, functional and preference dimensions fold
them with no change to State (`app.state.dimensions.SUBJECT_DIMENSION`): the language under
`language` (`reading` and `spoken`, which State names as the reading and the spoken
language); density and one-thing-per-screen under `format`, and voice as `format.preferred`,
the fact the feed reads to go voice-first; read-back and repeated prompts under
`memory_support`; large text and high contrast under `vision`; big targets under `dexterity`;
breakfast and the name he goes by under `nudges`. A `setting.*` subject would have folded
into the clinical dimension, which is State's default for a subject it does not know. The
conditions are `condition.<code>` facts "as told", the doctor is `doctor.name` and the decade
he was born in is `setting.birth_decade` (lab trends read his age band from it), all in
the clinical dimension and neither a `control` word, so neither moves a posture. Only what
changed writes a fact, superseding the one before; a condition untapped is superseded with
`false`. The language also becomes the profile's own, so the feed speaks it from the next
card.

Voice is the one setting with a machine beside it: two unopened text cards switch the feed to
voice-first on their own (E21, spec §9). Voice on is written as his word; voice off is
written only to take back a voice-on he gave, so an untouched switch leaves the feed's own
rule free to act.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.delivery.feed.compose import FORMAT_ATTRIBUTE, FORMAT_SUBJECT, VOICE
from app.delivery.feed.models import CardFormat
from app.drafts import FactDraft
from app.errors import Refusal
from app.identity.models import Profile
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, Event, EventKind, Fact, SourceChannel, short_label
from app.memory.semantic import assert_fact, current_facts
from app.onboarding.conditions import check_conditions
from app.onboarding.models import Density, ProfileSettings
from app.onboarding.strings import LANGUAGES, language_for

SETTINGS_SCOPE = Scope.PROFILE
"""Reading and writing the settings row: the face of the graph, which every key opens. Who
may write is decided by `a_setter`; which parts a key reads, by `RECORD_PARTS`."""

TARGET = ProfileSettings.__tablename__

RECORD_PARTS: tuple[str, ...] = ("conditions", "doctor_name", "birth_decade")
"""The parts of the settings that are his health record — and the decade he was born in, which
the record reads his lab ranges by — read only under `Scope.RECORDS`."""

CONDITION = "condition"
DOCTOR = ("doctor", "name")
BREAKFAST = ("nudges", "breakfast_time")
PREFERRED_NAME = ("nudges", "preferred_name")
CHECKIN_TIME = ("setting", "checkin_time")
"""When he is asked how he is, "HH:MM" on his region's clock: a `setting.*` fact the
check-in (E17) reads; State has no need to fold it."""
BIRTH_DECADE = ("setting", "birth_decade")
"""The one `setting.*` fact: the decade he was born in, by its first year, which lab trends
(E07) read his age band from. Clinical by State's default, as a reference range is."""
FIRST_DECADE = 1900
VOICE_FACT = (FORMAT_SUBJECT, FORMAT_ATTRIBUTE)
TEXT = CardFormat.TEXT.value


class NotTheirsToSetUp(Refusal):
    """Setting a profile up — its settings, its biography, its first week — is the owner's
    and his chief's to do. A caregiver reads it; she does not change it."""


class NotADecade(Refusal):
    """The decade he was born in is its first year — 1940, 1950 — from 1900 to this one."""


class NotALanguage(Refusal):
    """The profile's language is one Nura's words are written in: en, ms or zh."""


def a_setter(context: KeyContext) -> None:
    """Refuse anyone but the owner or a chief (a steward holds a chief key). The door around
    the caller writes the refusal down."""
    if not context.is_owner and context.role is not KeyRole.CHIEF:
        raise NotTheirsToSetUp(f"a {context.role} key does not set the profile up")


def clock_time(value: time | None) -> str | None:
    """A time of day as it is stored and sent: "07:30", on his wall clock."""
    return None if value is None else f"{value.hour:02d}:{value.minute:02d}"


def parse_clock_time(text: str | None) -> time | None:
    if text is None:
        return None
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))


def _name(text: str | None) -> str | None:
    return None if text is None or not text.strip() else short_label(text)


@dataclass(frozen=True, slots=True)
class SettingsValues:
    """What the settings screen says. Every part has a default but the language."""

    language: str
    conditions: tuple[str, ...] = ()
    density: Density = Density.DETAILED
    large_text: bool = False
    high_contrast: bool = False
    voice_on: bool = False
    big_targets: bool = False
    one_thing_per_screen: bool = False
    read_back: bool = False
    repeat_prompts: bool = False
    preferred_name: str | None = None
    doctor_name: str | None = None
    breakfast_time: time | None = None
    checkin_time: time | None = None
    birth_decade: int | None = None

    def checked(self) -> SettingsValues:
        """The same values, or a refusal: a language Nura speaks, conditions from the
        graph, names that are names, a time to the minute."""
        if self.language not in LANGUAGES:
            raise NotALanguage(f"{self.language!r} is not one of {LANGUAGES}")
        if self.birth_decade is not None and (
            self.birth_decade % 10
            or not FIRST_DECADE <= self.birth_decade <= utcnow().year // 10 * 10
        ):
            raise NotADecade(f"{self.birth_decade} is not the first year of a decade")
        return replace(
            self,
            conditions=check_conditions(self.conditions),
            preferred_name=_name(self.preferred_name),
            doctor_name=_name(self.doctor_name),
            breakfast_time=None
            if self.breakfast_time is None
            else time(self.breakfast_time.hour, self.breakfast_time.minute),
            checkin_time=None
            if self.checkin_time is None
            else time(self.checkin_time.hour, self.checkin_time.minute),
        )


def values_of(row: ProfileSettings) -> SettingsValues:
    return SettingsValues(
        language=row.language,
        conditions=tuple(row.conditions),
        density=row.density,
        large_text=row.large_text,
        high_contrast=row.high_contrast,
        voice_on=row.voice_on,
        big_targets=row.big_targets,
        one_thing_per_screen=row.one_thing_per_screen,
        read_back=row.read_back,
        repeat_prompts=row.repeat_prompts,
        preferred_name=row.preferred_name,
        doctor_name=row.doctor_name,
        breakfast_time=parse_clock_time(row.breakfast_time),
        checkin_time=parse_clock_time(row.checkin_time),
        birth_decade=row.birth_decade,
    )


def facts_of(values: SettingsValues) -> dict[tuple[str, str], Any]:
    """Every setting as the fact it is written as: (subject, attribute) -> value."""
    wanted: dict[tuple[str, str], Any] = {
        ("language", "reading"): values.language,
        ("language", "spoken"): values.language,
        ("format", "density"): values.density.value,
        ("format", "one_thing_per_screen"): values.one_thing_per_screen,
        VOICE_FACT: VOICE if values.voice_on else TEXT,
        ("memory_support", "read_back"): values.read_back,
        ("memory_support", "repeat_prompts"): values.repeat_prompts,
        ("vision", "large_text"): values.large_text,
        ("vision", "high_contrast"): values.high_contrast,
        ("dexterity", "big_targets"): values.big_targets,
        BREAKFAST: clock_time(values.breakfast_time),
        PREFERRED_NAME: values.preferred_name,
        DOCTOR: values.doctor_name,
        CHECKIN_TIME: clock_time(values.checkin_time),
        BIRTH_DECADE: values.birth_decade,
    }
    for code in values.conditions:
        wanted[(CONDITION, code)] = True
    return wanted


def _newest(facts: Sequence[Fact]) -> dict[tuple[str, str], Fact]:
    """The current fact for each subject and attribute: the newest asserted, as State folds."""
    found: dict[tuple[str, str], Fact] = {}
    for fact in sorted(facts, key=lambda one: as_utc(one.asserted_at)):
        found[(fact.subject, fact.attribute)] = fact
    return found


def changes(
    values: SettingsValues, held: Sequence[Fact]
) -> list[tuple[str, str, Any, Fact | None]]:
    """What a save writes: each setting whose value differs from the fact that holds, with the
    fact it supersedes. A condition no longer tapped is superseded with `false`; a name or a
    time taken away, with null. Voice off is written only over a voice-on he gave."""
    current = _newest(held)
    wanted = facts_of(values)
    for (subject, attribute), fact in current.items():
        if subject == CONDITION and fact.value is True and (subject, attribute) not in wanted:
            wanted[(subject, attribute)] = False
    out: list[tuple[str, str, Any, Fact | None]] = []
    for (subject, attribute), value in wanted.items():
        was = current.get((subject, attribute))
        if (subject, attribute) == VOICE_FACT and value == TEXT:
            said_voice = (
                was is not None
                and was.value == VOICE
                and was.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
            )
            if not said_voice:
                continue
        if was is None and value is None:
            continue
        if was is not None and was.value == value:
            continue
        out.append((subject, attribute, value, was))
    return out


async def _current_row(
    session: AsyncSession, *, context: KeyContext, scope: Scope
) -> ProfileSettings | None:
    found = await audited_read(
        session,
        ProfileSettings,
        context,
        scope,
        where=(ProfileSettings.superseded_at.is_(None),),
    )
    return max(found, key=lambda row: as_utc(row.set_at)) if found else None


@dataclass(frozen=True, slots=True)
class Reach:
    """How to reach him, as the settings screen serves it: his language and the two times of
    his day. None where he has not said."""

    language: str | None
    breakfast: time | None
    checkin: time | None


async def reach_of(session: AsyncSession, *, context: KeyContext) -> Reach:
    """His language, breakfast and check-in exactly as `GET …/settings` serves them (the web's
    About you): the one settings read for how to reach him. The breakfast resolver
    (`app.routines.breakfast`), the nudges' check-in (`app.delivery.nudges.engine`) and every
    message said in his language (`his_language`) ask it, so nothing reads the row another
    way. The face of the graph, as `read_settings` reads it: how to reach him, not his
    health, so every key may ask."""
    row = await _current_row(session, context=context, scope=SETTINGS_SCOPE)
    if row is None:
        return Reach(language=None, breakfast=None, checkin=None)
    values = values_of(row)
    return Reach(
        language=values.language, breakfast=values.breakfast_time, checkin=values.checkin_time
    )


async def his_language(session: AsyncSession, *, context: KeyContext) -> str:
    """The language Nura says things to him in: his settings' (`reach_of`), else the
    profile's own, which the settings keep in step. The capture lines (#132), the delivery
    engine's messages to him and the morning card (E11) all ask here."""
    said = (await reach_of(session, context=context)).language
    return said if said else (await audited_profile_read(session, context)).language


@audited(Action.READ, Scope.RECORDS, TARGET)
async def current_settings(session: AsyncSession, *, context: KeyContext) -> ProfileSettings | None:
    """The settings row that stands now, whole — conditions and doctor included — for the
    services that act on the record (the biography, the plan). Read under the record's scope,
    so a key without it never gets the whole row; the settings screen reads through
    `read_settings`, which narrows it."""
    return await _current_row(session, context=context, scope=Scope.RECORDS)


async def _write_setting(
    session: AsyncSession,
    *,
    context: KeyContext,
    subject: str,
    attribute: str,
    value: Any,
    was: Fact | None,
    event: Event,
    moment: datetime,
) -> Fact:
    draft = FactDraft(
        subject=subject,
        attribute=attribute,
        value=value,
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None if was is None else was.id,
    )
    yes = await confirm(session, context, draft)
    return await assert_fact(
        session,
        context=context,
        subject=subject,
        attribute=attribute,
        value=value,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        event_id=event.id,
        valid_from=moment,
        supersedes_id=draft.supersedes_id,
    )


async def _speak(session: AsyncSession, *, context: KeyContext, language: str) -> Profile:
    """The profile's own language becomes the one he chose, so everything that reads it — the
    feed, the extractor's hints, the words of a claim — speaks it from now."""
    profile = await audited_profile_read(session, context)
    if profile.language != language:
        profile.language = language
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.PROFILE,
            target=Profile.__tablename__,
            target_id=profile.id,
            rows=1,
        )
    return profile


@audited(Action.WRITE, SETTINGS_SCOPE, TARGET)
async def save_settings(
    session: AsyncSession, *, context: KeyContext, values: SettingsValues
) -> tuple[ProfileSettings, list[Fact]]:
    """Save the settings screen: a new settings row superseding the last, the facts for what
    changed, and the profile's language. Everything in one unit of work; a refusal anywhere
    leaves nothing behind but the line that says so."""
    a_setter(context)
    chosen = values.checked()
    previous = await _current_row(session, context=context, scope=SETTINGS_SCOPE)
    moment = utcnow()
    held = await current_facts(session, context=context)
    event = await record_event(
        session,
        context=context,
        kind=EventKind.ONBOARDING,
        occurred_at=moment,
        label="profile settings",
        source_channel=SourceChannel.APP,
    )
    written = [
        await _write_setting(
            session,
            context=context,
            subject=subject,
            attribute=attribute,
            value=value,
            was=was,
            event=event,
            moment=moment,
        )
        for subject, attribute, value, was in changes(chosen, held)
    ]
    row = await audited_write(
        session,
        ProfileSettings,
        context,
        SETTINGS_SCOPE,
        conditions=list(chosen.conditions),
        language=chosen.language,
        density=chosen.density,
        large_text=chosen.large_text,
        high_contrast=chosen.high_contrast,
        voice_on=chosen.voice_on,
        big_targets=chosen.big_targets,
        one_thing_per_screen=chosen.one_thing_per_screen,
        read_back=chosen.read_back,
        repeat_prompts=chosen.repeat_prompts,
        preferred_name=chosen.preferred_name,
        doctor_name=chosen.doctor_name,
        breakfast_time=clock_time(chosen.breakfast_time),
        checkin_time=clock_time(chosen.checkin_time),
        birth_decade=chosen.birth_decade,
        event_id=event.id,
        set_by_person_id=context.person_id,
        set_at=moment,
        supersedes_id=None if previous is None else previous.id,
    )
    if previous is not None:
        previous.superseded_at = moment
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=SETTINGS_SCOPE,
            target=TARGET,
            target_id=previous.id,
            rows=1,
        )
    await _speak(session, context=context, language=chosen.language)
    return row, written


@dataclass(frozen=True, slots=True)
class SettingsView:
    """The settings as this key reads them: the row (None before the first save), the values
    — the defaults, in the profile's language, before it — and which parts were withheld."""

    row: ProfileSettings | None
    values: SettingsValues
    withheld: tuple[str, ...]


def _narrowed(
    values: SettingsValues, context: KeyContext
) -> tuple[SettingsValues, tuple[str, ...]]:
    if context.allows(Scope.RECORDS):
        return values, ()
    return replace(values, conditions=(), doctor_name=None, birth_decade=None), RECORD_PARTS


@audited(Action.READ, SETTINGS_SCOPE, TARGET)
async def read_settings(session: AsyncSession, *, context: KeyContext) -> SettingsView:
    """The settings as the caller's key reads them (see the module's note on who reads what)."""
    row = await _current_row(session, context=context, scope=SETTINGS_SCOPE)
    if row is None:
        profile = await audited_profile_read(session, context)
        values = SettingsValues(language=language_for(profile.language))
    else:
        values = values_of(row)
    shown, withheld = _narrowed(values, context)
    if row is not None and not withheld:
        # The conditions and the doctor are his record: serving them is a read of the record,
        # and the trail says so, not only that the face of the graph was read.
        await record(
            session,
            context=context,
            action=Action.READ,
            scope=Scope.RECORDS,
            target=TARGET,
            target_id=row.id,
            rows=1,
        )
    return SettingsView(row=row, values=shown, withheld=withheld)


def settings_language(row: ProfileSettings | None, profile_language: str) -> str:
    """The language his words are served in: the one on his settings, or the profile's."""
    return language_for(row.language if row is not None else profile_language)
