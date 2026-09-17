"""Cutting, listing and closing keys.

Binding does not share the account: it cuts a key per person with a role, a scope, a window
and a recorded basis. Only the owner or a chief may cut one, and nobody may cut a key wider
than the one they hold.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write, record_share
from app.audit.models import Action, Channel, Outcome
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.drafts import KeyChangeDraft
from app.errors import Refusal
from app.identity.models import Person
from app.keys.context import KeyContext, OutOfScope
from app.keys.models import Key
from app.keys.privacy import only_me_scopes
from app.keys.scopes import DEFAULT_WINDOW, ROLE_SCOPES, KeyRole, KeyWindow, Scope, window_ends_at


class NotTheirKeyToCut(Refusal):
    """Only the owner of the graph, or a chief he named, may bind someone to it."""


class NoKeyToClose(Refusal):
    """There is no such key on this profile."""


class WouldWiden(Refusal):
    """A key is narrowed in place, never widened: wider needs a fresh consent and a new key."""


class NothingToNarrow(Refusal):
    """The key already opens exactly this, for exactly this long."""


class NotTheirKeyToLeave(Refusal):
    """A key closes on its own holder's word when it is his to close (#144). Nobody leaves on
    anybody else's key, whatever role they hold."""


class ChiefMustNameSuccessor(Refusal):
    """A chief leaving must name who takes it up next, or rest on Pa's own word that there
    will be none (`waive_successor`), so the family is never left without a chief silently."""


class SuccessorMustAlreadyHoldAKey(Refusal):
    """The next chief is someone already in the family — a key holder promoted, not a
    stranger named in passing on the way out."""


async def may_cut_keys(session: AsyncSession, context: KeyContext) -> None:
    """Only the owner or a chief holding the family scope. A refusal is written down.

    Public so a channel can ask before it does anything on the asker's behalf — resolving
    the holder, say — that it would otherwise have to undo.
    """
    try:
        context.require(Scope.FAMILY)
        if not context.is_owner and context.role is not KeyRole.CHIEF:
            raise NotTheirKeyToCut(f"a {context.role} key cannot cut another key")
    except (OutOfScope, NotTheirKeyToCut) as refusal:
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.FAMILY,
            target=Key.__tablename__,
            outcome=Outcome.REFUSED,
            refused_because=type(refusal).__name__,
        )
        raise


async def grant_key(
    session: AsyncSession,
    *,
    context: KeyContext,
    holder: Person,
    role: KeyRole,
    scopes: Iterable[Scope] | None = None,
    window: KeyWindow | None = None,
) -> Key:
    """Cut a key for one person on the profile in the context.

    `scopes` narrows the role's preset; it can never widen past what the granter holds.
    The basis of the key is the consent it is cut under (E00-02): no key is cut, whatever
    its role, unless a `SHARE_WITH_PERSON` consent naming this holder is in force, given by
    the owner or by someone acting for him on a recorded proxy basis, to the current
    wording, and the key records which consent that was. The words the patient read named
    the parts this person may see, so the key is never wider than those either. New
    wording therefore stops the cutting of keys until the patient agrees again; that is
    what versioned consent means, and shipping new words is paired with asking. The
    emergency role is not exempt: the emergency card is health data too.

    Cutting a key is a share of the graph, so it goes into the audit trail as one (E00-07).
    """
    await may_cut_keys(session, context)
    moment = utcnow()
    consent = await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.SHARE_WITH_PERSON,
        scope=Scope.FAMILY,
        holder_person_id=holder.id,
    )
    asked = frozenset(scopes) if scopes is not None else ROLE_SCOPES[role]
    # Every key opens the face of the graph it is cut on: narrowing never removes PROFILE.
    granted = (asked | {Scope.PROFILE}) & context.scopes
    if consent.scopes is not None:
        # Whose record it is (PROFILE) is not a part of it; the rest is what the words named.
        granted &= consent.scopes | {Scope.PROFILE}
    # A part the owner marked "only me" is cut into no new key (E12-04); the resolver would
    # take it out again anyway, so the row is written as it will be read.
    granted -= await only_me_scopes(session, profile_id=context.profile_id)

    # One person holds one key on one profile: a new key replaces the one before it.
    for existing in await audited_read(session, Key, context, Scope.FAMILY):
        if existing.holder_person_id == holder.id and existing.is_active(moment):
            existing.revoked_at = moment

    key = await audited_write(
        session,
        Key,
        context,
        Scope.FAMILY,
        holder_person_id=holder.id,
        role=role,
        scopes=sorted(scope.value for scope in granted),
        consent_id=consent.consent_id,
        granted_by_person_id=context.person_id,
        granted_at=moment,
        expires_at=window_ends_at(window or DEFAULT_WINDOW[role], moment),
    )
    await record_share(
        session,
        context=context,
        scope=Scope.FAMILY,
        target=Key.__tablename__,
        channel=Channel.APP,
        shared_with_person_id=holder.id,
        target_id=key.id,
    )
    return key


async def list_keys(session: AsyncSession, *, context: KeyContext) -> Sequence[Key]:
    """Every key ever cut on this profile, so the owner can read who holds what."""
    return await audited_read(session, Key, context, Scope.FAMILY)


async def revoke_key(
    session: AsyncSession,
    *,
    context: KeyContext,
    key_id: uuid.UUID,
) -> Key:
    """Close a key. The row stays, so the owner can still read that it was held."""
    await may_cut_keys(session, context)
    moment = utcnow()
    found = await audited_read(session, Key, context, Scope.FAMILY, where=(Key.id == key_id,))
    if not found:
        raise NoKeyToClose(f"no key {key_id} on profile {context.profile_id}")
    key = found[0]
    if key.revoked_at is None:
        key.revoked_at = moment
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=Key.__tablename__,
        target_id=key.id,
        rows=1,
    )
    return key


@audited(Action.WRITE, Scope.FAMILY, Key.__tablename__)
async def key_change_draft_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    key_id: uuid.UUID,
    scopes: Iterable[Scope] | None = None,
    window: KeyWindow | None = None,
) -> tuple[Key, frozenset[Scope], datetime | None, KeyChangeDraft]:
    """What narrowing this key to these parts and this window would leave: the key, the
    parts it would open, when it would end, and the draft a yes is minted for.

    Refused before any yes is looked for: a wider ask (`WouldWiden`) — one part more, or a
    longer window — and an ask that changes nothing (`NothingToNarrow`). Only the owner or
    a chief asks, like every key operation.
    """
    await may_cut_keys(session, context)
    moment = utcnow()
    found = await audited_read(session, Key, context, Scope.FAMILY, where=(Key.id == key_id,))
    if not found or not found[0].is_active(moment):
        raise NoKeyToClose(f"no live key {key_id} on profile {context.profile_id}")
    key = found[0]
    held = key.scopes_held
    asked = (frozenset(scopes) | {Scope.PROFILE}) if scopes is not None else held
    if not asked <= held:
        raise WouldWiden("a key is narrowed in place; wider needs a fresh consent and a new key")
    ends_at = None if key.expires_at is None else as_utc(key.expires_at)
    if window is not None:
        shorter = window_ends_at(window, moment)
        if shorter is None or (ends_at is not None and shorter >= ends_at):
            raise WouldWiden("a key's window is shortened in place, never lengthened")
        ends_at = shorter
    if asked == held and window is None:
        raise NothingToNarrow("the key already opens exactly this, for exactly this long")
    draft = KeyChangeDraft(
        key_id=key.id,
        scopes=tuple(sorted(scope.value for scope in asked)),
        window=None if window is None else window.value,
    )
    return key, asked, ends_at, draft


@audited(Action.WRITE, Scope.FAMILY, Key.__tablename__)
async def narrow_key(
    session: AsyncSession,
    *,
    context: KeyContext,
    key_id: uuid.UUID,
    scopes: Iterable[Scope] | None = None,
    window: KeyWindow | None = None,
    confirmation_id: uuid.UUID,
) -> Key:
    """Narrow a live key in place: fewer parts, or a shorter window, or both (E12-01).

    Only the owner or a chief, on their own yes for exactly this change
    (`app.drafts.KeyChangeDraft`). A key is never widened here — not by one part, not by
    a day — because the parts a person may see are what the patient agreed to in words
    naming that person, and more needs him to agree again and a new key cut under that
    agreement (`grant_key`). So a wider ask is refused before the yes is looked for, and
    the refusal is on the trail like any other. The key keeps its role and its basis; the
    row changes in place, since what it says now is what it opens now, and the trail says
    who narrowed it and when.
    """
    # Local import: `app.keys.confirm` imports this package's context for the confirmer
    # check, and this module is imported by the doors; the yes is the last thing looked at.
    from app.keys.confirm import consume_confirmation

    key, asked, ends_at, draft = await key_change_draft_for(
        session, context=context, key_id=key_id, scopes=scopes, window=window
    )
    await consume_confirmation(session, context, confirmation_id, draft)
    key.scopes = sorted(scope.value for scope in asked)
    key.expires_at = ends_at
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=Key.__tablename__,
        target_id=key.id,
        rows=1,
    )
    return key


async def waive_successor(session: AsyncSession, *, context: KeyContext, key_id: uuid.UUID) -> Key:
    """Pa's own word, before his chief leaves with nobody named after her (#144): there will
    be no chief on this profile until he names one again.

    Only the owner says this — a chief cannot waive it for herself, which is the whole
    point — and only about a live chief key. It stands until a successor is named or this is
    said again about a later chief; leaving with a named successor never needs it.
    """
    if not context.is_owner:
        raise NotTheirKeyToCut("only Pa says there will be no next chief")
    moment = utcnow()
    key = await session.get(Key, key_id)
    if key is None or key.profile_id != context.profile_id:
        raise NoKeyToClose(f"no key {key_id} on profile {context.profile_id}")
    if key.role is not KeyRole.CHIEF or not key.is_active(moment):
        raise NoKeyToClose("only a live chief key needs this word")
    key.successor_waived_at = moment
    key.successor_waived_by_person_id = context.person_id
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=Key.__tablename__,
        target_id=key.id,
        rows=1,
    )
    return key


async def leave_key(
    session: AsyncSession,
    *,
    context: KeyContext,
    key_id: uuid.UUID,
    successor_person_id: uuid.UUID | None = None,
) -> Key:
    """A holder closes their own key (#144): Pa let them in; they let themselves out.

    Self-authorised, unlike `revoke_key`: the only thing asked of the caller is that this is
    their own key, named in their own context, so a viewer or a caregiver with no family
    scope at all may still leave without anybody else's say-so. The row stays, the way any
    closed key's does, so Pa can still read that it was held; his trail carries the leaving
    like any other write to his keys, in the leaver's own name.

    A chief's key is the one exception. Closing it can leave the family's escalation ladder
    with nobody at the top, so it takes one more thing first: another holder named as the
    next chief — promoted here, on the leaving chief's own still-live authority, before her
    own key closes — or Pa's own word that there will be none (`waive_successor`). Neither
    one: the leave is refused, on the trail, and nothing closes.
    """
    moment = utcnow()
    key = await session.get(Key, key_id)
    if key is None or key.profile_id != context.profile_id:
        raise NoKeyToClose(f"no key {key_id} on profile {context.profile_id}")
    if context.key_id != key.id or key.holder_person_id != context.person_id:
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.FAMILY,
            target=Key.__tablename__,
            target_id=key.id,
            outcome=Outcome.REFUSED,
            refused_because=NotTheirKeyToLeave.__name__,
        )
        raise NotTheirKeyToLeave("a key closes on its own holder's word")
    if not key.is_active(moment):
        raise NoKeyToClose("this key is already closed")
    if key.role is KeyRole.CHIEF:
        if successor_person_id is not None:
            if successor_person_id == context.person_id:
                raise ChiefMustNameSuccessor("the next chief is someone other than her")
            candidates = await audited_read(
                session, Key, context, Scope.FAMILY, where=(Key.holder_person_id == successor_person_id,)
            )
            if not any(candidate.is_active(moment) for candidate in candidates):
                raise SuccessorMustAlreadyHoldAKey(
                    f"person {successor_person_id} holds no live key on profile {context.profile_id}"
                )
            successor = await session.get(Person, successor_person_id)
            assert successor is not None, "a live key names a real person"
            # Promoted while she is still the chief: `grant_key` asks the same authority
            # this key is about to give up, and it is hers to spend until it closes below.
            await grant_key(session, context=context, holder=successor, role=KeyRole.CHIEF)
        elif key.successor_waived_at is None:
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=Scope.FAMILY,
                target=Key.__tablename__,
                target_id=key.id,
                outcome=Outcome.REFUSED,
                refused_because=ChiefMustNameSuccessor.__name__,
            )
            raise ChiefMustNameSuccessor(
                "name the next chief, or ask Pa to say there will be none"
            )
    key.revoked_at = moment
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=Key.__tablename__,
        target_id=key.id,
        rows=1,
    )
    return key
