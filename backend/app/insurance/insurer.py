"""His insurer on the emergency card (E13-01): the name and the policy reference, typed on a yes.

    Conditions, medicines, allergies, blood type, contacts, insurer in two languages.

The insurer is what the ambulance crew or the hospital desk asks for first, so it sits on the
card beside the chief's number. It is typed — by him, or by the chief he named — and saved
only on the typer's own yes for exactly those words (`InsurerDraft`, the confirm pattern every
arranging write uses). A change is a new row and the newest row is in force; a row with no
name takes the insurer off the card. The policy reference is an identifier: it is carried on
the card as data beside the sentence, never inside one, and `scripts/data_map.py` classifies
every column here as one. An identity-card number is not a policy reference and is refused
(`NotAPolicyReference`): this module does not keep one until a guarantee letter needs it.

The rows are written and read under `Scope.EMERGENCY`, the part of the graph every role holds,
because the card is what that scope opens (ADR 0002): an emergency-only key reads the insurer
on the card and nothing else, and cannot set it (`NotTheirsToSetInsurer`).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.db import Base, ProfileScoped, as_utc, frozen, utcnow
from app.drafts import InsurerDraft
from app.errors import Refusal
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.memory.models import _row_of_profile

INSURER_SCOPE = Scope.EMERGENCY
TARGET = "insurer"

NAME_LENGTH = 120
REFERENCE_LENGTH = 40

_NRIC = re.compile(r"[STFGM]\d{7}[A-Z]")
"""A Singapore NRIC or FIN, anywhere in the words once spaces and marks are taken out."""
_TWELVE = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(\d{2})\d{4}(?!\d)")
"""Twelve digits whose first six are a date and whose next two a place of birth: a MyKad,
with its dashes or without."""


def looks_like_an_identity_card(text: str) -> bool:
    """Whether the words hold a Singapore NRIC or FIN, or a Malaysian MyKad — however they are
    written: with or without dashes, spaces or dots, after "NRIC" or "IC"."""
    compact = re.sub(r"[\s\-./:#]", "", text).upper()
    if _NRIC.search(compact):
        return True
    for match in _TWELVE.finditer(compact):
        _year, month, day, place = (int(part) for part in match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31 and place >= 1:
            return True
    return False


class Insurer(ProfileScoped, Base):
    """Who insures him, as typed on a yes. A change is a new row; the newest is in force."""

    __tablename__ = TARGET
    __table_args__ = (_row_of_profile(TARGET),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(String(NAME_LENGTH), default=None)
    policy_reference: Mapped[str | None] = mapped_column(String(REFERENCE_LENGTH), default=None)
    set_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    confirmation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("confirmation.id"))
    set_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


frozen(Insurer)


class NotTheirsToSetInsurer(Refusal):
    """The insurer is typed by him, the steward holding his graph, or the chief he named."""


class NotAnInsurer(Refusal):
    """An insurer is a name of 1 to 120 characters, with a policy reference of up to 40, or
    nothing at all to take it off the card."""


class NotAPolicyReference(Refusal):
    """An identity-card number is not a policy reference, and is not kept here."""


def may_set_insurer(context: KeyContext) -> None:
    if context.is_owner or context.is_steward or context.role is KeyRole.CHIEF:
        return
    raise NotTheirsToSetInsurer(f"a {context.role} key reads the insurer; it does not set it")


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    one_line = " ".join(text.split())
    return one_line or None


def insurer_draft(name: str | None, policy_reference: str | None) -> InsurerDraft:
    """The insurer as it will be kept, or a refusal naming what is wrong with it."""
    said = _clean(name)
    reference = _clean(policy_reference)
    if said is None and reference is not None:
        raise NotAnInsurer("a policy reference needs the insurer's name")
    if said is not None and len(said) > NAME_LENGTH:
        raise NotAnInsurer(f"an insurer's name is at most {NAME_LENGTH} characters")
    if reference is not None and len(reference) > REFERENCE_LENGTH:
        raise NotAnInsurer(f"a policy reference is at most {REFERENCE_LENGTH} characters")
    if any(one is not None and looks_like_an_identity_card(one) for one in (said, reference)):
        raise NotAPolicyReference("that holds an identity-card number")
    return InsurerDraft(name=said, policy_reference=reference)


@audited(Action.READ, INSURER_SCOPE, TARGET)
async def current_insurer(session: AsyncSession, *, context: KeyContext) -> Insurer | None:
    """The insurer in force, or None: never typed, or taken off the card."""
    rows = await audited_read(session, Insurer, context, INSURER_SCOPE)
    newest = max(rows, key=lambda row: (as_utc(row.set_at), str(row.id)), default=None)
    return None if newest is None or newest.name is None else newest


@audited(Action.WRITE, INSURER_SCOPE, TARGET)
async def set_insurer(
    session: AsyncSession,
    *,
    context: KeyContext,
    name: str | None,
    policy_reference: str | None,
    confirmation_id: uuid.UUID,
) -> Insurer:
    """Put the insurer on the card — or take it off, with no name — on the typer's own yes
    for exactly these words."""
    may_set_insurer(context)
    draft = insurer_draft(name, policy_reference)
    yes = await consume_confirmation(session, context, confirmation_id, draft)
    return await audited_write(
        session,
        Insurer,
        context,
        INSURER_SCOPE,
        name=draft.name,
        policy_reference=draft.policy_reference,
        set_by_person_id=context.person_id,
        confirmation_id=yes.id,
        set_at=utcnow(),
    )


__all__ = [
    "INSURER_SCOPE",
    "Insurer",
    "NotAPolicyReference",
    "NotAnInsurer",
    "NotTheirsToSetInsurer",
    "current_insurer",
    "insurer_draft",
    "looks_like_an_identity_card",
    "may_set_insurer",
    "set_insurer",
]
