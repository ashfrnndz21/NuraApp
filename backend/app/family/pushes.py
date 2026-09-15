"""The push composer (E12-06): a chief drafts a message to him, previews it as he will read
it, and puts it on the calendar. Nothing here sends; E11 delivers at a State-appropriate
moment between `send_at` and `expires_at`.

The message comes from a template in plain words (`app.family.strings.PUSH_TEMPLATES`), in
his language, with the chief's name and a time in words filled in — or as a memo, lines the
chief wrote herself. Either way the preview is exactly what he will see, and it passes
`app.safety.plain_words.verify` or it is refused with the findings, so the composer can
fix the line. The yes binds to the lines: what was previewed is what is scheduled.

A message to him names no medicine and no dose (#164), whatever the family types into a
memo or a slot: it is refused (`MessageNamesAMedicine`), the way a note about a clinic that
names one is (E03-03). His medicine reminders come only from his confirmed list, at the times
it gives — never from a line the family wrote, which nothing checks against that list.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read
from app.audit.models import Action
from app.db import as_utc, utcnow
from app.delivery.triggers.models import Delivery, DeliveryOutcome, TriggerType
from app.drafts import PushDraft
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.family.common import NotPlainWords, a_chief
from app.family.models import PushChannel, ScheduledPush
from app.family.strings import PUSH_TEMPLATES, TEMPLATE_SLOTS, language_of
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.safety.health_words import names_medicine_or_dose
from app.safety.plain_words import verify
from app.state.service import render_from_state

PUSH_TARGET = ScheduledPush.__tablename__

MAX_MEMO_LINES = 6
"""A memo to him is a few short lines, not a letter."""


class NoSuchTemplate(Refusal):
    """No message template by that id."""


class MissingSlot(Refusal):
    """The template names a person, a time or a doctor the composer did not give."""


class NotAMemo(Refusal):
    """A memo is one to six lines, each with words in it."""


class BadWindow(Refusal):
    """A message is scheduled for a moment ahead, and stops being worth sending after it."""


class MessageNamesAMedicine(Refusal):
    """A message to him named a medicine or a dose (#164). His medicine reminders come only
    from his confirmed list; the refusal carries nothing of what was written."""


@dataclass(frozen=True, slots=True)
class Preview:
    """What he will see: the lines, in his language, and the verifier's notes on them."""

    language: str
    template_id: str | None
    lines: list[str]
    notes: list[str]


def render(
    *,
    language: str,
    template_id: str | None,
    slots: Mapping[str, str],
    memo_lines: Sequence[str] | None,
    registry: DrugRegistry | None = None,
) -> Preview:
    """The lines as he will read them, from a template or a memo, through the verifier.

    Pure: the same inputs give the same lines, which is what lets a yes minted on the
    preview be spent on the schedule. A line naming a medicine or a dose is refused before
    the verifier reads it (`MessageNamesAMedicine`); `registry` is the licensed one, through
    its port, so a medicine it knows by any name is found.
    """
    words = language_of(language)
    if (template_id is None) == (memo_lines is None):
        raise NotAMemo("a message is a template or a memo, one of the two")
    if template_id is not None:
        templates = PUSH_TEMPLATES[words]
        if template_id not in templates:
            raise NoSuchTemplate(f"no template {template_id}")
        missing = TEMPLATE_SLOTS[template_id] - {k for k, v in slots.items() if v.strip()}
        if missing:
            raise MissingSlot(f"template {template_id} needs {sorted(missing)}")
        filled = {k: v.strip() for k, v in slots.items()}
        lines = [line.format(**filled) for line in templates[template_id]]
    else:
        assert memo_lines is not None
        lines = [line.strip() for line in memo_lines if line.strip()]
        if not lines or len(lines) > MAX_MEMO_LINES:
            raise NotAMemo(f"a memo is one to {MAX_MEMO_LINES} lines")
    if any(names_medicine_or_dose(line, registry) for line in lines):
        raise MessageNamesAMedicine("a message to him names no medicine and no dose")
    findings = [finding for line in lines for finding in verify(line, words, "line")]
    failures = [str(f) for f in findings if f.severity == "fail"]
    if failures:
        raise NotPlainWords(failures)
    return Preview(
        language=words,
        template_id=template_id,
        lines=lines,
        notes=[str(f) for f in findings if f.severity == "note"],
    )


@audited(Action.READ, Scope.SEND, PUSH_TARGET)
async def preview_push(
    session: AsyncSession,
    *,
    context: KeyContext,
    template_id: str | None = None,
    slots: Mapping[str, str] | None = None,
    memo_lines: Sequence[str] | None = None,
    language: str | None = None,
    registry: DrugRegistry | None = None,
) -> Preview:
    """Exactly what he will see, in his language unless another is asked for."""
    a_chief(context)
    profile = await audited_profile_read(session, context)
    return render(
        language=language or profile.language,
        template_id=template_id,
        slots=slots or {},
        memo_lines=memo_lines,
        registry=registry,
    )


def push_draft(
    preview: Preview, *, send_at: datetime, channel: PushChannel, expires_at: datetime
) -> PushDraft:
    """What the chief says yes to: these lines, then, there, until."""
    return PushDraft(
        language=preview.language,
        lines=tuple(preview.lines),
        send_at=as_utc(send_at),
        channel=channel.value,
        expires_at=as_utc(expires_at),
    )


@audited(Action.WRITE, Scope.SEND, PUSH_TARGET)
async def schedule_push(
    session: AsyncSession,
    *,
    context: KeyContext,
    send_at: datetime,
    channel: PushChannel,
    expires_at: datetime,
    confirmation_id: uuid.UUID,
    template_id: str | None = None,
    slots: Mapping[str, str] | None = None,
    memo_lines: Sequence[str] | None = None,
    language: str | None = None,
    registry: DrugRegistry | None = None,
) -> ScheduledPush:
    """Put the previewed message on the calendar, on the chief's yes for exactly its lines.

    The preview is rendered again here and the yes checked against it, so nothing can be
    scheduled that was not shown. The row names the State it was composed against, like
    every rendered thing; nothing is sent.
    """
    a_chief(context)
    moment = utcnow()
    if as_utc(expires_at) <= as_utc(send_at) or as_utc(expires_at) <= moment:
        raise BadWindow("a message expires after it is due, and after now")
    profile = await audited_profile_read(session, context)
    preview = render(
        language=language or profile.language,
        template_id=template_id,
        slots=slots or {},
        memo_lines=memo_lines,
        registry=registry,
    )
    draft = push_draft(preview, send_at=send_at, channel=channel, expires_at=expires_at)
    await consume_confirmation(session, context, confirmation_id, draft)
    return await render_from_state(
        session,
        ScheduledPush,
        context,
        Scope.SEND,
        composed_by_person_id=context.person_id,
        composed_at=moment,
        language=preview.language,
        template_id=preview.template_id,
        lines=preview.lines,
        send_at=as_utc(send_at),
        via_channel=channel,
        expires_at=as_utc(expires_at),
    )


async def pushes(session: AsyncSession, *, context: KeyContext) -> list[ScheduledPush]:
    """Every scheduled message, soonest first."""
    found = await audited_read(session, ScheduledPush, context, Scope.SEND)
    return sorted(found, key=lambda push: as_utc(push.send_at))


@dataclass(frozen=True, slots=True)
class PushState:
    """What became of one message to him, as the delivery log says it (E11)."""

    state: Literal["scheduled", "sent", "not_sent"]
    """`sent` once a delivery reached him, `not_sent` when its end passed first, else
    `scheduled`."""
    sent_at: datetime | None = None


async def push_states(
    session: AsyncSession, *, context: KeyContext, rows: Sequence[ScheduledPush]
) -> dict[uuid.UUID, PushState]:
    """Each message's state, read from the delivery log under the same scope as the messages
    themselves (`Scope.SEND`): only the family-message deliveries that reached him, and of
    those only when — never who else was reached, by what, or why something was held."""
    if not rows:
        return {}
    sent = await audited_read(
        session,
        Delivery,
        context,
        Scope.SEND,
        where=(
            Delivery.trigger_type == TriggerType.FAMILY_MESSAGE,
            Delivery.outcome == DeliveryOutcome.SENT,
        ),
    )
    first: dict[str, datetime] = {}
    for delivery in sent:
        push_id = str(delivery.why.get("scheduled_push_id", ""))
        at = as_utc(delivery.recorded_at)
        if push_id and (push_id not in first or at < first[push_id]):
            first[push_id] = at
    moment = utcnow()
    states: dict[uuid.UUID, PushState] = {}
    for push in rows:
        if str(push.id) in first:
            states[push.id] = PushState("sent", first[str(push.id)])
        elif as_utc(push.expires_at) <= moment:
            states[push.id] = PushState("not_sent")
        else:
            states[push.id] = PushState("scheduled")
    return states
