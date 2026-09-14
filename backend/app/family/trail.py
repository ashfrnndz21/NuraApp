"""The trail as Dad sees it (E12-04): who looked at what, in his words, by day.

`read_audit` gives the owner and his chief the lines as stored — a person id, an action, a
scope, a table name, a refusal's class name. This turns each into sentences from
`app.audit.strings` with the person's name, his words for the part, and the day on his
wall clock, and groups them by day, newest first. The same reach repeated within a day is
one sentence: the trail says who looked at what, not how many times. Nothing on a line is
ever a name from the code: every arm has a default, and a person the profile cannot name
is "someone".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read
from app.audit.models import Action, AuditEntry, Outcome
from app.audit.strings import (
    YOU,
    allowed_lines,
    language_of,
    refusal_family,
    refused_lines,
    what_words,
)
from app.audit.trail import read_audit
from app.consent.service import all_consents
from app.db import as_utc
from app.identity.doors import stewardship_of
from app.identity.models import Person
from app.keys.context import KeyContext
from app.keys.grants import list_keys
from app.keys.privacy import only_me_scopes
from app.medicines.strings import say_date
from app.regions import REGION_TZ

# @patient phrase
SOMEONE = {"en": "someone", "ms": "seseorang", "zh": "有人"}
"""A person the profile cannot name. It should not happen — every actor on the trail is the
owner, a key holder or someone a consent names — and if it does, he still reads a sentence."""


@dataclass(frozen=True, slots=True)
class TrailLine:
    """One thing that happened, as he reads it."""

    at: datetime
    who: str
    sentences: list[str]
    outcome: Outcome


@dataclass(frozen=True, slots=True)
class TrailDay:
    day: date
    day_words: str
    lines: list[TrailLine] = field(default_factory=list)


async def _people_on_the_profile(
    session: AsyncSession, context: KeyContext, owner_person_id: uuid.UUID | None
) -> set[uuid.UUID]:
    """Everyone the profile names: its owner, every key holder, everyone a consent names,
    the steward. Read through the doors the reader already holds — the owner's and the
    chief's — so that naming an actor is never a read the trail's own reader could not make."""
    named: set[uuid.UUID] = set()
    if owner_person_id is not None:
        named.add(owner_person_id)
    named |= {key.holder_person_id for key in await list_keys(session, context=context)}
    for consent in await all_consents(session, context=context):
        named.add(consent.person_id)
        for other in (consent.holder_person_id, consent.witness_person_id):
            if other is not None:
                named.add(other)
    stewardship = await stewardship_of(session, context=context)
    if stewardship is not None:
        named.add(stewardship.steward_person_id)
    return named


async def trail(
    session: AsyncSession,
    *,
    context: KeyContext,
    language: str | None = None,
    since: datetime | None = None,
    limit: int = 500,
) -> list[TrailDay]:
    """The trail in his words, by day, newest first. The owner and his chief, like `read_audit`."""
    entries = await read_audit(session, context=context, since=since, limit=limit)
    profile = await audited_profile_read(session, context)
    words = language_of(language or profile.language)
    zone = REGION_TZ[context.region]
    only_me = await only_me_scopes(session, profile_id=context.profile_id)
    named = await _people_on_the_profile(session, context, profile.owner_person_id)

    names: dict[uuid.UUID, str] = {}

    async def name_of(person_id: uuid.UUID) -> str:
        if person_id == profile.owner_person_id:
            return YOU[words]
        if person_id not in names:
            person = await session.get(Person, person_id) if person_id in named else None
            names[person_id] = person.display_name if person is not None else SOMEONE[words]
        return names[person_id]

    days: dict[date, TrailDay] = {}
    seen: set[tuple[date, uuid.UUID, Action, str, Outcome, str | None]] = set()
    for entry in entries:
        at = as_utc(entry.at)
        local_day = at.astimezone(zone).date()
        what = what_words(entry.target, entry.scope, words)
        key = (
            local_day,
            entry.actor_person_id,
            entry.action,
            what,
            entry.outcome,
            entry.refused_because,
        )
        if key in seen:
            continue
        seen.add(key)
        day_words = say_date(local_day, words)
        who = await name_of(entry.actor_person_id)
        days.setdefault(local_day, TrailDay(day=local_day, day_words=day_words)).lines.append(
            TrailLine(
                at=at,
                who=who,
                sentences=await _sentences(
                    entry,
                    words,
                    who=who,
                    what=what,
                    day=day_words,
                    only_me=only_me,
                    name_of=name_of,
                ),
                outcome=entry.outcome,
            )
        )
    return [days[day] for day in sorted(days, reverse=True)]


async def _sentences(
    entry: AuditEntry,
    words: str,
    *,
    who: str,
    what: str,
    day: str,
    only_me: frozenset,
    name_of,
) -> list[str]:
    if entry.outcome is Outcome.REFUSED:
        family = refusal_family(entry.refused_because, entry.scope, only_me=only_me)
        return refused_lines(family, words, who=who, what=what, day=day)
    other = (
        await name_of(entry.shared_with_person_id)
        if entry.shared_with_person_id is not None
        else (entry.shared_with_label or SOMEONE[words])
    )
    return allowed_lines(entry.action, words, who=who, what=what, day=day, other=other)
