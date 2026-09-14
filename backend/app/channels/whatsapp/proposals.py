"""Proposals: a health event heard in a thread, written only on the poster's yes (E19-02).

The classifier hears "BP 150/90 this morning" and proposes a fact. Nothing is written yet
but the proposal itself — what was heard, who said it, until when it may be answered — and
the message it was heard in, as an artefact. The poster is asked "Did I get this right?"
and answers in the same thread. A yes from the same number, inside the window, mints a
confirmation for the draft recomputed from the proposal and spends it in the same unit of
work, the way the app's save button does for a number the person typed: the event is
written, the fact names it and the message, State recomputes. A no closes the proposal. A
yes from anyone else finds nothing open: only the poster confirms the poster's word.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard, audited_read, audited_write
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.channels.whatsapp.classifier import HealthEvent
from app.channels.whatsapp.models import (
    ANSWER_IN_PROGRESS,
    Proposal,
    ProposalStatus,
    WhatsAppMessage,
    WhatsAppThread,
)
from app.db import as_utc, utcnow
from app.drafts import FactDraft
from app.errors import Refusal
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, Event, Fact
from app.memory.semantic import assert_fact

PROPOSAL_WINDOW = timedelta(hours=24)
"""How long a proposal waits for its yes: the same day, on a phone someone reads later."""

PROPOSAL = Proposal.__tablename__


class NoOpenProposal(Refusal):
    """Nothing of this poster's is waiting for an answer on this profile."""


class ProposalExpired(Refusal):
    """The question is older than a day. The message is sent again, and heard again."""


class NotThePoster(Refusal):
    """Only the person whose words were heard confirms what was heard."""


async def propose(
    session: AsyncSession,
    *,
    context: KeyContext,
    thread: WhatsAppThread,
    message: WhatsAppMessage,
    event: HealthEvent,
) -> Proposal:
    """Write down what was heard, for the poster to confirm. Under the scope of the fact it
    would become: a key that could not write the fact cannot propose it either, and that
    refusal is the same one the app gives, on the trail — on the WhatsApp channel, which is
    why the door here is explicit rather than the `audited` decorator's."""
    scope = scope_for_subject(event.subject)
    async with audited_guard(
        session, context, Action.WRITE, scope, PROPOSAL, channel=Channel.WHATSAPP
    ):
        context.require(scope)
        return await _propose(session, context=context, thread=thread, message=message, event=event)


async def _propose(
    session: AsyncSession,
    *,
    context: KeyContext,
    thread: WhatsAppThread,
    message: WhatsAppMessage,
    event: HealthEvent,
) -> Proposal:
    moment = utcnow()
    return await audited_write(
        session,
        Proposal,
        context,
        scope_for_subject(event.subject),
        channel=Channel.WHATSAPP,
        thread_id=thread.id,
        message_id=message.id,
        poster_person_id=context.person_id,
        subject=event.subject,
        attribute=event.attribute,
        value=event.value,
        unit=event.unit,
        event_kind=event.event_kind,
        occurred_at=as_utc(message.at),
        said=event.said,
        created_at=moment,
        expires_at=moment + PROPOSAL_WINDOW,
        status=ProposalStatus.OPEN,
    )


async def open_proposals_of(session: AsyncSession, *, context: KeyContext) -> Sequence[Proposal]:
    """The poster's own open proposals on this profile, oldest first.

    Read under the profile scope: a person reading back the question Nura asked them about
    their own words, and nobody else's — the filter is the poster, who is the person asking.
    """
    found = await audited_read(
        session,
        Proposal,
        context,
        Scope.PROFILE,
        where=(
            Proposal.poster_person_id == context.person_id,
            Proposal.status == ProposalStatus.OPEN,
        ),
        channel=Channel.WHATSAPP,
    )
    return sorted(found, key=lambda row: (as_utc(row.created_at), str(row.id)))


def draft_for(proposal: Proposal, *, event_id: uuid.UUID, artifact_id: uuid.UUID) -> FactDraft:
    """What the yes is for: the fact as the proposal holds it, resting on the event just
    written and the message it was heard in."""
    return FactDraft(
        subject=proposal.subject,
        attribute=proposal.attribute,
        value=proposal.value,
        unit=proposal.unit,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=artifact_id,
        event_id=event_id,
        episode_id=None,
        supersedes_id=None,
    )


async def _close(
    session: AsyncSession,
    *,
    context: KeyContext,
    proposal: Proposal,
    status: ProposalStatus,
    fact: Fact | None = None,
    event: Event | None = None,
) -> None:
    moment = utcnow()
    session.info[ANSWER_IN_PROGRESS] = proposal.id
    try:
        proposal.status = status
        proposal.answered_at = moment
        if fact is not None:
            proposal.fact_id = fact.id
        if event is not None:
            proposal.event_id = event.id
        await session.flush()
    finally:
        session.info.pop(ANSWER_IN_PROGRESS, None)
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=scope_for_subject(proposal.subject),
        target=PROPOSAL,
        target_id=proposal.id,
        rows=1,
        channel=Channel.WHATSAPP,
    )


async def answer(
    session: AsyncSession,
    *,
    context: KeyContext,
    yes: bool,
) -> tuple[Proposal, Fact | None]:
    """The poster's answer to their oldest open proposal, on this profile, now. One door for
    the whole answer, on the WhatsApp channel; see `_answer` for what it does."""
    async with audited_guard(
        session, context, Action.WRITE, Scope.PROFILE, PROPOSAL, channel=Channel.WHATSAPP
    ):
        context.require(Scope.PROFILE)
        return await _answer(session, context=context, yes=yes)


async def _answer(
    session: AsyncSession,
    *,
    context: KeyContext,
    yes: bool,
) -> tuple[Proposal, Fact | None]:
    """The poster's answer to their oldest open proposal, on this profile, now.

    A yes writes the event (resting on the message the words were heard in), mints the
    confirmation for exactly the draft recomputed here, spends it, and writes the fact
    naming both; State recomputes as it lands. The answer itself is kept in the thread by
    the caller, so the record shows the words heard and the word that confirmed them. A no
    closes the proposal and writes nothing. An expired proposal is closed as expired, and
    the poster is told to say it again. Nothing here is done for anyone but the person in
    the context: the open proposals read are the poster's own.
    """
    waiting = list(await open_proposals_of(session, context=context))
    if not waiting:
        raise NoOpenProposal("nothing of this poster's is waiting for an answer here")
    proposal = waiting[0]
    if proposal.poster_person_id != context.person_id:
        raise NotThePoster("only the poster confirms what was heard")  # pragma: no cover
    moment = utcnow()
    if moment >= as_utc(proposal.expires_at):
        await _close(session, context=context, proposal=proposal, status=ProposalStatus.EXPIRED)
        raise ProposalExpired("the question is older than a day")
    if not yes:
        await _close(session, context=context, proposal=proposal, status=ProposalStatus.DECLINED)
        return proposal, None

    heard = await audited_read(
        session,
        WhatsAppMessage,
        context,
        Scope.PROFILE,
        where=(WhatsAppMessage.id == proposal.message_id,),
        channel=Channel.WHATSAPP,
    )
    assert heard and heard[0].artifact_id is not None  # a proposal is heard in a kept message
    event = await record_event(
        session,
        context=context,
        kind=proposal.event_kind,
        occurred_at=as_utc(proposal.occurred_at),
        artifact_id=heard[0].artifact_id,
    )
    draft = draft_for(proposal, event_id=event.id, artifact_id=heard[0].artifact_id)
    minted = await confirm(session, context, draft, channel=Channel.WHATSAPP)
    fact = await assert_fact(
        session,
        context=context,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        unit=draft.unit,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=minted.id,
        artifact_id=draft.artifact_id,
        event_id=event.id,
        valid_from=as_utc(proposal.occurred_at),
    )
    await _close(
        session,
        context=context,
        proposal=proposal,
        status=ProposalStatus.CONFIRMED,
        fact=fact,
        event=event,
    )
    return proposal, fact
