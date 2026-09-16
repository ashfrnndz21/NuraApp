"""Each inbound message handled once, and none dropped (#158).

A provider sends a webhook delivery again until it is answered with a 2xx: that is the only
retry there is. So the webhook must never answer 200 for a message it failed to handle — a
red word that met a passing failure would be lost for good, and never on the trail — and it
must never handle a message twice when the delivery comes again.

`receive` is one message's walk through the webhook. The receipt row is claimed before the
handler runs (#173): the provider's id is inserted first, under the unique constraint, so two
copies of one delivery arriving at the same instant cannot both run the handler — the second
one's insert loses the race and is answered as the duplicate it is, not with a 500. A message
whose row says it was handled already is acknowledged and skipped the same way, and a row left
by an earlier failure is claimed for this try alone (`SELECT ... FOR UPDATE`), so a redelivery
racing another redelivery waits and then finds it handled. Then it is handled in a savepoint
of its own (`nested_unit_of_work`), and its receipt is marked in the same savepoint, so the
message's rows and the note that it was handled stand or fall together.
A refusal is an answer, not a failure: its lines are on the trail (the savepoint's keepers
replay them) and it is not tried again. Anything else rolls the savepoint back — nothing of
that message is left half-written — and is counted on the receipt, by the class name of what
went wrong and never the message's words; the webhook then answers 5xx, the provider sends the
delivery again, and only the message that failed is tried again. A red word is still read
first on every try, before "ignore" and before the consent (`handle_inbound`).

A message that keeps failing is the operator's to look at: from its `FAILING_AFTER`th failure,
every failure is logged at error level by the receipt's id — never the number, never the words
— and the receipts with failures and no `handled_at` are the list.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp.models import WhatsAppReceipt
from app.channels.whatsapp.provider import InboundMessage
from app.db import nested_unit_of_work, utcnow
from app.errors import Refusal

log = logging.getLogger("nura.channels.whatsapp")

FAILING_AFTER = 3
"""From this many failures of one message, each further failure is logged for the operator."""
KEY_LENGTH = 128
"""The longest provider id kept as it is; a longer one is kept as its digest."""


class Received(StrEnum):
    HANDLED = "handled"
    ALREADY = "already"
    """Handled on an earlier delivery, or being handled by one running right now: acknowledged,
    and nothing is done twice."""
    FAILED = "failed"
    """Not handled, and nothing of it kept: the provider is asked to send it again."""


def receipt_key(provider_message_id: str) -> str:
    """The provider's id as the receipt keeps it: as it is, or its digest when it is longer
    than the column."""
    if len(provider_message_id) <= KEY_LENGTH:
        return provider_message_id
    return "sha256:" + hashlib.sha256(provider_message_id.encode()).hexdigest()


async def _receipt(session: AsyncSession, key: str) -> WhatsAppReceipt | None:
    found: WhatsAppReceipt | None = await session.scalar(
        select(WhatsAppReceipt).where(WhatsAppReceipt.provider_message_id == key)
    )
    return found


async def _handled(session: AsyncSession, key: str) -> None:
    moment = utcnow()
    receipt = await _receipt(session, key)
    if receipt is None:
        session.add(
            WhatsAppReceipt(provider_message_id=key, first_seen_at=moment, handled_at=moment)
        )
    else:
        receipt.handled_at = moment
    await session.flush()


async def _claim(session: AsyncSession, key: str) -> Received | None:
    """This message's receipt row, claimed for this try before the handler runs, or the
    answer when another try holds it: `ALREADY` when it is handled, or being handled now.

    The row is inserted first, in a savepoint of its own: the unique constraint on the
    provider's id is what decides the race, so of two copies of one delivery arriving at the
    same instant exactly one runs the handler and the other is answered as a duplicate. A row
    an earlier try left behind is claimed with `SELECT ... FOR UPDATE`, which waits for a try
    running right now and then reads what it wrote — handled, and there is nothing to do.
    """
    earlier = await _receipt(session, key)
    if earlier is None:
        try:
            async with nested_unit_of_work(session):
                session.add(
                    WhatsAppReceipt(provider_message_id=key, first_seen_at=utcnow(), failures=0)
                )
                await session.flush()
        except IntegrityError:
            # Another copy of this delivery claimed it first: a duplicate, not a failure.
            log.info("whatsapp: one inbound message is being handled already")
            return Received.ALREADY
        return None
    held: WhatsAppReceipt | None = await session.scalar(
        select(WhatsAppReceipt)
        .where(WhatsAppReceipt.provider_message_id == key)
        .with_for_update()
    )
    if held is not None and held.handled_at is not None:
        return Received.ALREADY
    return None


async def _failed(session: AsyncSession, key: str, what: str) -> WhatsAppReceipt:
    moment = utcnow()
    receipt = await _receipt(session, key)
    if receipt is None:
        receipt = WhatsAppReceipt(provider_message_id=key, first_seen_at=moment, failures=0)
        session.add(receipt)
    receipt.failures = (receipt.failures or 0) + 1
    receipt.last_failed_at = moment
    receipt.last_failure = what[:64]
    await session.flush()
    return receipt


async def receive(
    session: AsyncSession,
    message: InboundMessage,
    handle: Callable[[], Awaitable[object]],
) -> Received:
    """One message of a webhook delivery, once: its receipt row claimed before anything is
    done, skipped when another try holds it or handled it already; handled in a savepoint of
    its own otherwise; and counted, with nothing of it kept, when that failed."""
    key = receipt_key(message.provider_message_id)
    claimed = await _claim(session, key)
    if claimed is not None:
        return claimed
    try:
        async with nested_unit_of_work(session):
            await handle()
            await _handled(session, key)
    except Refusal as refused:
        # A door said no: the answer is the refusal, on the trail already. Not tried again.
        log.info("whatsapp: one inbound message refused: %s", type(refused).__name__)
        await _handled(session, key)
        return Received.HANDLED
    except Exception as failed:  # noqa: BLE001 — counted by name; the provider sends it again
        what = type(failed).__name__
        receipt = await _failed(session, key, what)
        if receipt.failures >= FAILING_AFTER:
            log.error(
                "whatsapp: inbound message %s has failed %d times (%s); for the operator",
                receipt.id,
                receipt.failures,
                what,
            )
        else:
            log.warning("whatsapp: one inbound message not handled, to be sent again: %s", what)
        return Received.FAILED
    return Received.HANDLED


__all__ = ["FAILING_AFTER", "Received", "receipt_key", "receive"]
