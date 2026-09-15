"""Each inbound message handled once, and none dropped (#158).

A provider sends a webhook delivery again until it is answered with a 2xx: that is the only
retry there is. So the webhook must never answer 200 for a message it failed to handle — a
red word that met a passing failure would be lost for good, and never on the trail — and it
must never handle a message twice when the delivery comes again.

`receive` is one message's walk through the webhook. The provider's id for it is looked up
first (`WhatsAppReceipt`): a message handled already is acknowledged and skipped. Otherwise it
is handled in a savepoint of its own (`nested_unit_of_work`), and its receipt is written in the
same savepoint, so the message's rows and the note that it was handled stand or fall together.
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
    """Handled on an earlier delivery: acknowledged, and nothing is done twice."""
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
    """One message of a webhook delivery, once: skipped when handled already; handled in a
    savepoint of its own otherwise; and counted, with nothing of it kept, when that failed."""
    key = receipt_key(message.provider_message_id)
    earlier = await _receipt(session, key)
    if earlier is not None and earlier.handled_at is not None:
        return Received.ALREADY
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
