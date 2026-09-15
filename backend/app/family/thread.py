"""The family thread and its digests (E12-02).

One thread per profile where the family's short messages and his health cards interleave.
A message is the family talking to each other — the one free-text column here, on purpose
and short — and nothing reads a fact out of it: this module never writes a Fact or an Event,
and the test holds it to that. A card is a reference: the State snapshot it was rendered
from and which kind of card, rendered into words when it is read, never stored as words.

There is no stream. `digest` is the structured summary of the thread and the day's cards
for one caregiver, in whole sentences from `app.family.strings`, each through the
plain-words verifier before it leaves; E11 schedules it, one per day per caregiver.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read, audited_write
from app.audit.models import Action
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.family.common import NotPlainWords
from app.family.models import MESSAGE_LENGTH, CardKind, Task, ThreadMessage
from app.family.roster import who_is_on_duty
from app.family.strings import DIGEST, DIGEST_HEAD, language_of
from app.identity.models import Person
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.strings import say_date
from app.regions import REGION_TZ
from app.safety.plain_words import verify
from app.state.models import StateSnapshot
from app.state.service import StaleState, current_state

THREAD_TARGET = ThreadMessage.__tablename__


class NotAMessage(Refusal):
    """A family message is one to two hundred and eighty characters. This was not."""


class NoSuchTask(Refusal):
    """A task card names a task on this profile."""


@audited(Action.WRITE, Scope.FAMILY, THREAD_TARGET)
async def post_message(session: AsyncSession, *, context: KeyContext, text: str) -> ThreadMessage:
    """One person says something to the family. Kept as said, under the family scope, in
    the author's name. No fact is read out of it, now or ever."""
    line = text.strip()
    if not line or len(line) > MESSAGE_LENGTH:
        raise NotAMessage(f"a message is one to {MESSAGE_LENGTH} characters")
    return await audited_write(
        session,
        ThreadMessage,
        context,
        Scope.FAMILY,
        author_person_id=context.person_id,
        posted_at=utcnow(),
        text=line,
    )


@audited(Action.WRITE, Scope.FAMILY, THREAD_TARGET)
async def post_card(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: CardKind,
    task_id: uuid.UUID | None = None,
) -> ThreadMessage:
    """Put a health card into the thread: a reference to the State it is rendered from.

    The State must be current for the person posting — a card composed from a snapshot the
    record has moved past is refused (`StaleState`), as every rendered thing is.
    """
    state = await current_state(session, context=context)
    if state.stale is not False:
        raise StaleState("state is behind the record, or could not be checked against it")
    if kind is CardKind.TASK:
        if task_id is None:
            raise NoSuchTask("a task card names its task")
        found = await audited_read(
            session, Task, context, Scope.FAMILY, where=(Task.id == task_id,)
        )
        if not found:
            raise NoSuchTask(f"no task {task_id} on this profile")
    elif task_id is not None:
        raise NoSuchTask("only a task card names a task")
    return await audited_write(
        session,
        ThreadMessage,
        context,
        Scope.FAMILY,
        author_person_id=context.person_id,
        posted_at=utcnow(),
        state_id=state.id,
        card_kind=kind,
        task_id=task_id,
    )


async def read_thread(
    session: AsyncSession,
    *,
    context: KeyContext,
    cursor: datetime | None = None,
    limit: int = 50,
) -> tuple[list[ThreadMessage], datetime | None]:
    """A page of the thread, newest first, and the cursor for the page before it.

    `cursor` is the `posted_at` of the oldest entry already seen; the page holds entries
    older than it. The second value is None when there is nothing older than this page.
    """
    where = () if cursor is None else (ThreadMessage.posted_at < as_utc(cursor),)
    found = await audited_read(
        session,
        ThreadMessage,
        context,
        Scope.FAMILY,
        where=where,
        order_by=(ThreadMessage.posted_at.desc(),),
        limit=limit + 1,
    )
    page = list(found[:limit])
    more = len(found) > limit
    return page, (as_utc(page[-1].posted_at) if more and page else None)


# --- the digest ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DigestEntry:
    """One item of the digest: what kind, when, Nura's lines about it, and — for a message —
    the family's own words, which are not Nura's to rewrite."""

    kind: str
    at: datetime
    lines: list[str]
    text: str | None = None
    message_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class Digest:
    """The day for one caregiver: a headline, the entries since `since`, who is on duty."""

    language: str
    since: datetime
    headline: str
    entries: list[DigestEntry]
    on_duty: list[str]
    lines: list[str] = field(default_factory=list)
    """Every line Nura wrote, in order, for the voice and for the verifier."""


async def _names(
    session: AsyncSession, context: KeyContext, person_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Display names for the people the thread names. Every author holds, or held, a key
    to the profile, or owns it — the thread is written under the family scope — so this
    is the same read `app.audit.access.person_display_name` makes, for several at once."""
    names: dict[uuid.UUID, str] = {}
    for person_id in person_ids:
        person = await session.get(Person, person_id)
        names[person_id] = person.display_name if person is not None else ""
    return names


def _blood_pressure(snapshot: StateSnapshot) -> tuple[int, int] | None:
    reading: dict[str, Any] | None = (
        snapshot.clinical.get("facts", {}).get("blood_pressure", {}).get("reading")
    )
    if reading is None:
        return None
    value = reading.get("value") or {}
    top, bottom = value.get("systolic"), value.get("diastolic")
    if top is None or bottom is None:
        return None
    return int(top), int(bottom)


async def digest(
    session: AsyncSession,
    *,
    context: KeyContext,
    since: datetime,
    language: str | None = None,
) -> Digest:
    """The structured summary of the thread and the day's cards for the person asking.

    Rendered as the caregiver's key reads it: a reading card carries its numbers only when
    the key opens the readings and the record; a card the key cannot render still says that
    a card was posted. Every line Nura wrote goes through the verifier; a line that does
    not pass is a refusal, not a sentence he hears.
    """
    words = language_of(language)
    zone = REGION_TZ[context.region]
    profile = await audited_profile_read(session, context)
    moment = utcnow()
    today = say_date(moment.astimezone(zone).date(), words)
    found = await audited_read(
        session,
        ThreadMessage,
        context,
        Scope.FAMILY,
        where=(ThreadMessage.posted_at >= as_utc(since),),
        order_by=(ThreadMessage.posted_at.asc(),),
    )
    names = await _names(session, context, {entry.author_person_id for entry in found})
    can_render_numbers = context.allows(Scope.RECORDS) and context.allows(Scope.READINGS)
    templates = DIGEST[words]
    # A line carrying a value that is not Nura's words, and the template it is checked as.
    checked: dict[str, str] = {}

    entries: list[DigestEntry] = []
    for entry in found:
        at = as_utc(entry.posted_at)
        day = say_date(at.astimezone(zone).date(), words)
        who = names.get(entry.author_person_id, "")
        if not entry.is_card:
            entries.append(
                DigestEntry(
                    kind="message",
                    at=at,
                    lines=[templates["message"].format(who=who, day=day)],
                    text=entry.text,
                    message_id=entry.id,
                )
            )
            continue
        lines: list[str]
        if entry.card_kind is CardKind.READING:
            lines = [templates["reading"].format(who=who, name=profile.display_name, day=day)]
            if can_render_numbers and entry.state_id is not None:
                snapshots = await audited_read(
                    session,
                    StateSnapshot,
                    context,
                    Scope.RECORDS,
                    where=(StateSnapshot.id == entry.state_id,),
                )
                pressure = _blood_pressure(snapshots[0]) if snapshots else None
                if pressure is not None:
                    lines.append(
                        templates["reading_value"].format(
                            top_number=pressure[0], bottom_number=pressure[1]
                        )
                    )
        elif entry.card_kind is CardKind.TAKEN:
            lines = [templates["taken"].format(who=who, name=profile.display_name, day=day)]
        elif entry.card_kind is CardKind.VISIT:
            lines = [templates["visit"].format(name=profile.display_name, day=day)]
        else:
            lines = await _task_lines(
                session, context, entry, names, templates, words, zone, checked
            )
        assert entry.card_kind is not None  # `is_card` said so
        entries.append(
            DigestEntry(kind=entry.card_kind.value, at=at, lines=lines, message_id=entry.id)
        )

    on_duty_names: list[str] = []
    for duty in await who_is_on_duty(session, context=context, at=moment):
        person = await session.get(Person, duty.person_id)
        if person is not None and person.display_name not in on_duty_names:
            on_duty_names.append(person.display_name)
    closing = (
        [templates["on_duty"].format(who=name) for name in on_duty_names]
        if on_duty_names
        else [templates["nobody_on_duty"]]
    )
    if not entries:
        closing.insert(
            0, templates["quiet"].format(day=say_date(since.astimezone(zone).date(), words))
        )

    headline = DIGEST_HEAD[words].format(name=profile.display_name, day=today)
    nura_lines = [headline] + [line for entry in entries for line in entry.lines] + closing
    failures = [
        str(finding)
        for index, line in enumerate(nura_lines)
        for finding in verify(checked.get(line, line), words, "headline" if index == 0 else "line")
        if finding.severity == "fail"
    ]
    if failures:
        raise NotPlainWords(failures)
    return Digest(
        language=words,
        since=as_utc(since),
        headline=headline,
        entries=entries,
        on_duty=on_duty_names,
        lines=nura_lines,
    )


async def _task_lines(
    session: AsyncSession,
    context: KeyContext,
    entry: ThreadMessage,
    names: dict[uuid.UUID, str],
    templates: Mapping[str, str],
    words: str,
    zone: Any,
    checked: dict[str, str],
) -> list[str]:
    """The task card's line, with the task's own words in it. An order task (E04-05) names
    the medicine as its box does ("order more amlodipine 5 mg for Pa"), a value and not
    Nura's words: its label was checked as a template when it was kept (`add_task`), so the
    digest checks this line with `{what}` in its place, recorded in `checked`."""
    if entry.task_id is None:
        return []
    found = await audited_read(
        session, Task, context, Scope.FAMILY, where=(Task.id == entry.task_id,)
    )
    if not found:
        return []
    task = found[0]
    doer = names.get(task.assigned_person_id)
    if doer is None:
        doer = (await _names(session, context, {task.assigned_person_id}))[task.assigned_person_id]
    slots = {"who": doer}
    template = templates["task_open"]
    if task.done_at is not None:
        slots["day"] = say_date(as_utc(task.done_at).astimezone(zone).date(), words)
        template = templates["task_done"]
    line = template.format(what=task.what, **slots)
    if task.medication_line_id is not None:
        checked[line] = template.format(what="{what}", **slots)
    return [line]
