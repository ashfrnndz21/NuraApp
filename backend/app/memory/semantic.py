"""Semantic memory: facts with provenance and confidence, immutable with supersession.

Nothing infers without provenance. A fact is asserted from an artefact or an event on this
profile — never from nothing — with a confidence and a state, for a window of time. When it
turns out to be wrong, or a person confirms it, a new fact supersedes it: the old row stays,
marked with when it stopped being current, and the new one names it. The old one is read
under the same key context as the provenance.

A person's word is never replaced by a machine's. CONFIRMED_BY_PERSON and DISPUTED are a
person's yes, offered as a confirm the surface wrote down (`app.keys.confirm`) and used here
once; the fact records who that was. An extraction may replace only an extraction; and a
dispute is kept beside the fact it disputes without closing it, so the person's number stays
current until a person settles it. See `ConfirmedFactStands`. Rules from above this layer —
the label-photo rule for a high-risk drug — register on `before_fact_write`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.drafts import FactDraft
from app.errors import Refusal
from app.keys.confirm import NotAConfirmerHere, consume_confirmation
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.memory.episodic import (
    NoSuchArtifact,
    NoSuchEvent,
    fact_cites_only_what_is_held_here,
    require_artifact,
    require_event,
)
from app.memory.models import ConfidenceState, Fact
from app.memory.working import require_open_episode


class NoProvenance(Refusal):
    """A fact says where it came from. This one named no artefact and no event."""


class NoSuchProvenance(Refusal):
    """The artefact or event a fact names must be on this profile. This one was not."""


class NotAConfidence(Refusal):
    """Confidence is a number from nought to one."""


class EmptyWindow(Refusal):
    """A fact cannot stop holding before it starts."""


class NoSuchFact(Refusal):
    """No fact by that id on this profile."""


class AlreadySuperseded(Refusal):
    """This fact has already been replaced. Supersede the one that replaced it."""


class NotTheSameFact(Refusal):
    """A supersession says the same thing better. This one was about something else."""


class NotTheFactInDispute(Refusal):
    """A dispute is settled on the fact it disputes, not on the dispute."""


class NotAPersonsWord(Refusal):
    """An extracted fact is the machine's. It does not come with a person's yes."""


FactWriteHook = Callable[[AsyncSession, KeyContext, FactDraft], Awaitable[None]]

before_fact_write: list[FactWriteHook] = []
"""Rules from above this layer, run before any fact is written, after every check here.

The medicines module (E04) registers the label-photo rule for a high-risk drug here: a hook
that reads the draft — and, through the session and context, the artefact it cites — and
raises a `Refusal` to stop the write. The door on `assert_fact` writes that refusal down like
any other. Nothing is written until every hook has returned.
"""

FactWrittenHook = Callable[[AsyncSession, KeyContext, Fact], Awaitable[None]]

after_fact_write: list[FactWrittenHook] = []
"""What follows from a fact landing, run once it has, in the same unit of work.

State (E00-04) registers its recompute here, so "State recomputes on any new fact" happens
at the moment the fact is written and names the fact. A hook runs under the writer's own
key context; one that raises a `Refusal` stops the write, as the door on `assert_fact`
writes that refusal down and the channel rolls the unit back.
"""


class ConfirmedFactStands(Refusal):
    """A person's word is not overwritten by a machine's.

    The rule, in three parts.

    1. An EXTRACTED fact may supersede only an EXTRACTED fact with no open dispute against
       it. Once a person has spoken on a fact — CONFIRMED_BY_PERSON, or DISPUTED — only a
       person replaces it.
    2. A DISPUTED fact is an open dispute, not a replacement. It names the fact it disputes
       in `supersedes_id`, carries the disputed value, and names the person who raised it.
       It closes nothing and is never current: `current_facts` keeps returning the fact it
       disputes. So a dose the person confirmed stays the recorded dose while a photo says
       otherwise, and the disagreement is there to be read (`open_disputes`).
    3. A person settles a dispute with a CONFIRMED_BY_PERSON supersession of the disputed
       fact. That closes the fact and every open dispute against it, and the person's new
       number becomes current. A dispute is not itself a predecessor (`NotTheFactInDispute`).

    For a dose, that is the difference between the person and the machine having the last
    word.
    """


def _check_supersession(
    old: Fact,
    disputes: Sequence[Fact],
    subject: str,
    attribute: str,
    state: ConfidenceState,
) -> None:
    """What a new fact may replace: the same fact, and never a person's word with a machine's."""
    if (old.subject, old.attribute) != (subject, attribute):
        raise NotTheSameFact(f"fact {old.id} is about {old.subject}.{old.attribute}")
    if old.confidence_state is ConfidenceState.DISPUTED:
        raise NotTheFactInDispute(f"fact {old.id} is a dispute; settle the fact it disputes")
    if state is ConfidenceState.EXTRACTED and (
        old.confidence_state is not ConfidenceState.EXTRACTED or disputes
    ):
        raise ConfirmedFactStands(
            f"fact {old.id} is {old.confidence_state}; an extraction does not replace it"
        )


def _check_state_and_confirm(state: ConfidenceState, confirmation_id: uuid.UUID | None) -> None:
    """A state is not a label the caller picks: a person's word comes with a person's yes."""
    if state is ConfidenceState.EXTRACTED and confirmation_id is not None:
        raise NotAPersonsWord("an extracted fact comes with no confirm")
    if state is not ConfidenceState.EXTRACTED and confirmation_id is None:
        raise NotAConfirmerHere(f"a {state} fact is a person's yes, and none was offered")


async def _check_provenance(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID | None,
    event_id: uuid.UUID | None,
) -> None:
    if artifact_id is None and event_id is None:
        raise NoProvenance("a fact names the artefact or the event it came from")
    try:
        if artifact_id is not None:
            await require_artifact(session, context=context, artifact_id=artifact_id)
        if event_id is not None:
            await require_event(session, context=context, event_id=event_id)
    except (NoSuchArtifact, NoSuchEvent) as missing:
        raise NoSuchProvenance(str(missing)) from missing


def _check_confidence(confidence: float) -> float:
    if not 0.0 <= confidence <= 1.0:
        raise NotAConfidence("confidence is a number from nought to one")
    return float(confidence)


def _check_window(valid_from: datetime, valid_to: datetime | None) -> None:
    if valid_to is not None and valid_to <= valid_from:
        raise EmptyWindow("valid_to must come after valid_from")


async def _current_fact(session: AsyncSession, *, context: KeyContext, fact_id: uuid.UUID) -> Fact:
    """The fact by that id on this profile, still current — the only kind that can be replaced.

    The scope is the fact's own subject's, so the row is looked at first to learn it. The
    audited read below is the one that checks the key and writes the line.
    """
    row = await session.get(Fact, fact_id)
    if row is None or row.profile_id != context.profile_id:
        raise NoSuchFact(f"no fact {fact_id} on profile {context.profile_id}")
    found = await audited_read(
        session,
        Fact,
        context,
        scope_for_subject(row.subject),
        where=(
            Fact.id == fact_id,
            fact_cites_only_what_is_held_here(context, scope_for_subject(row.subject)),
        ),
    )
    if not found:
        raise NoSuchFact(f"no fact {fact_id} on profile {context.profile_id}")
    old = found[0]
    if old.superseded_at is not None:
        raise AlreadySuperseded(f"fact {fact_id} was superseded at {old.superseded_at}")
    return old


async def _write_fact(
    session: AsyncSession,
    *,
    context: KeyContext,
    subject: str,
    attribute: str,
    value: Any,
    confidence: float,
    unit: str | None,
    confidence_state: ConfidenceState,
    confirmation_id: uuid.UUID | None,
    artifact_id: uuid.UUID | None,
    event_id: uuid.UUID | None,
    episode_id: uuid.UUID | None,
    valid_from: datetime | None,
    valid_to: datetime | None,
    supersedes: Fact | None,
) -> Fact:
    """The one path a fact is written by: every check, then the hooks, then the confirm is
    used, then the write, then the supersession."""
    moment = utcnow()
    starts = valid_from or moment
    _check_window(starts, valid_to)
    sure = _check_confidence(confidence)
    # Keeping a fact rests on the consent to hold the record (E00-02). The gate runs under
    # the scope of the act it guards, which is the subject's (`app.keys.scopes`).
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=scope_for_subject(subject),
    )
    await _check_provenance(session, context=context, artifact_id=artifact_id, event_id=event_id)
    if episode_id is not None:
        await require_open_episode(session, context=context, episode_id=episode_id)
    _check_state_and_confirm(confidence_state, confirmation_id)
    disputes: Sequence[Fact] = ()
    if supersedes is not None:
        disputes = await open_disputes(session, context=context, fact_id=supersedes.id)
        _check_supersession(supersedes, disputes, subject, attribute, confidence_state)
    draft = FactDraft(
        subject=subject,
        attribute=attribute,
        value=value,
        unit=unit,
        confidence=sure,
        confidence_state=confidence_state,
        artifact_id=artifact_id,
        event_id=event_id,
        episode_id=episode_id,
        supersedes_id=None if supersedes is None else supersedes.id,
    )
    for hook in before_fact_write:
        await hook(session, context, draft)
    # The yes is used last, once everything else has passed, so a refusal never spends it.
    who = None
    if confirmation_id is not None:
        yes = await consume_confirmation(session, context, confirmation_id, draft)
        who = yes.person_id
    new = await audited_write(
        session,
        Fact,
        context,
        scope_for_subject(subject),
        subject=subject,
        attribute=attribute,
        value=value,
        unit=unit,
        confidence=sure,
        confidence_state=confidence_state,
        confirmed_by_person_id=who,
        artifact_id=artifact_id,
        event_id=event_id,
        episode_id=episode_id,
        valid_from=starts,
        valid_to=valid_to,
        asserted_at=moment,
        supersedes_id=None if supersedes is None else supersedes.id,
    )
    # A dispute closes nothing. Anything else closes the fact it names, and settling a fact
    # closes the disputes that were open against it.
    if supersedes is not None and confidence_state is not ConfidenceState.DISPUTED:
        for closed in (supersedes, *disputes):
            closed.superseded_at = moment
        await session.flush()
        for closed in (supersedes, *disputes):
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=Scope.RECORDS,
                target=Fact.__tablename__,
                target_id=closed.id,
                rows=1,
            )
    for followed in after_fact_write:
        await followed(session, context, new)
    return new


@audited(Action.WRITE, lambda call: scope_for_subject(call["subject"]), Fact.__tablename__)
async def assert_fact(
    session: AsyncSession,
    *,
    context: KeyContext,
    subject: str,
    attribute: str,
    value: Any,
    confidence: float,
    unit: str | None = None,
    confidence_state: ConfidenceState = ConfidenceState.EXTRACTED,
    confirmation_id: uuid.UUID | None = None,
    artifact_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    episode_id: uuid.UUID | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    supersedes_id: uuid.UUID | None = None,
) -> Fact:
    """Assert a fact about the profile from an artefact or an event on it.

    `valid_from` defaults to now; `valid_to` of None means it holds until superseded.
    `supersedes_id` names a current fact on this profile, read under the key context like the
    provenance is; naming it is superseding it, under the rule in `ConfirmedFactStands`.
    `confirmation_id` is a yes the surface wrote down (`app.keys.confirm.confirm`) for a
    `FactDraft` of exactly this statement and provenance, naming the fact being superseded
    when there is one. It is required with CONFIRMED_BY_PERSON or DISPUTED, refused with
    EXTRACTED, and used once; the fact records the person who gave it. A medicine fact is
    held under the medicines scope (`scope_for_subject`), a reading under the readings scope.
    """
    old = None
    if supersedes_id is not None:
        old = await _current_fact(session, context=context, fact_id=supersedes_id)
    return await _write_fact(
        session,
        context=context,
        subject=subject,
        attribute=attribute,
        value=value,
        confidence=confidence,
        unit=unit,
        confidence_state=confidence_state,
        confirmation_id=confirmation_id,
        artifact_id=artifact_id,
        event_id=event_id,
        episode_id=episode_id,
        valid_from=valid_from,
        valid_to=valid_to,
        supersedes=old,
    )


@audited(Action.WRITE, Scope.PROFILE, Fact.__tablename__)
async def supersede_fact(
    session: AsyncSession,
    *,
    context: KeyContext,
    fact_id: uuid.UUID,
    value: Any,
    confidence: float,
    unit: str | None = None,
    confidence_state: ConfidenceState = ConfidenceState.EXTRACTED,
    confirmation_id: uuid.UUID | None = None,
    artifact_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> Fact:
    """Replace a fact with a new one that names it. The old row stays.

    Subject and attribute are the old fact's: a supersession says the same thing better, it
    does not say something else. Provenance and unit are carried over unless new ones are
    given, so confirming a reading still links to the photo it was read from. What a person
    confirmed is not replaced by an extraction, and a DISPUTED supersession is an open dispute
    that leaves the old fact current: see `ConfirmedFactStands`.
    """
    old = await _current_fact(session, context=context, fact_id=fact_id)
    carried = artifact_id is None and event_id is None
    return await _write_fact(
        session,
        context=context,
        subject=old.subject,
        attribute=old.attribute,
        value=value,
        confidence=confidence,
        unit=unit if unit is not None else old.unit,
        confidence_state=confidence_state,
        confirmation_id=confirmation_id,
        artifact_id=old.artifact_id if carried else artifact_id,
        event_id=old.event_id if carried else event_id,
        episode_id=old.episode_id,
        valid_from=valid_from,
        valid_to=valid_to,
        supersedes=old,
    )


@audited(Action.READ, lambda call: scope_for_subject(call.get("subject")), Fact.__tablename__)
async def current_facts(
    session: AsyncSession,
    *,
    context: KeyContext,
    subject: str | None = None,
    attribute: str | None = None,
    at: datetime | None = None,
) -> Sequence[Fact]:
    """The facts that hold at `at` (default now): unsuperseded, inside their window.

    Passing `at` is how the timeline asks what was known on a day; the window is on the
    fact's own validity, so a fact asserted later about an earlier time is still found. An
    open dispute is not a fact that holds: the fact it disputes is (`ConfirmedFactStands`).

    The scope is the subject's, decided in `app.keys.scopes`: medicines under MEDICINES,
    readings under READINGS, the whole record — no subject named — under RECORDS.
    """
    moment = at or utcnow()
    where: list[ColumnElement[bool]] = [
        Fact.superseded_at.is_(None),
        Fact.confidence_state != ConfidenceState.DISPUTED,
        Fact.valid_from <= moment,
        or_(Fact.valid_to.is_(None), Fact.valid_to > moment),
        fact_cites_only_what_is_held_here(context, scope_for_subject(subject)),
    ]
    if subject is not None:
        where.append(Fact.subject == subject)
    if attribute is not None:
        where.append(Fact.attribute == attribute)
    found = await audited_read(session, Fact, context, scope_for_subject(subject), where=where)
    return sorted(found, key=lambda fact: (fact.subject, fact.attribute, as_utc(fact.valid_from)))


@audited(Action.READ, Scope.PROFILE, Fact.__tablename__)
async def open_disputes(
    session: AsyncSession,
    *,
    context: KeyContext,
    fact_id: uuid.UUID,
) -> Sequence[Fact]:
    """The disputes still open against a fact, oldest first. Empty once a person settled it."""
    disputed = await session.get(Fact, fact_id)
    if disputed is None or disputed.profile_id != context.profile_id:
        raise NoSuchFact(f"no fact {fact_id} on profile {context.profile_id}")
    found = await audited_read(
        session,
        Fact,
        context,
        scope_for_subject(disputed.subject),
        where=(
            Fact.supersedes_id == fact_id,
            Fact.confidence_state == ConfidenceState.DISPUTED,
            Fact.superseded_at.is_(None),
            fact_cites_only_what_is_held_here(context, scope_for_subject(disputed.subject)),
        ),
    )
    return sorted(found, key=lambda dispute: as_utc(dispute.asserted_at))
