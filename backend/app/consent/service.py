"""Giving, withdrawing, listing and checking consent.

Consent is reached under `Scope.FAMILY`. There is no `CONSENT` scope on purpose: scopes are
the parts of the graph a key can be cut to, and the record of what the patient agreed to
is not a part of the graph anyone is ever cut a key to. It is the same class of thing as
the keys and the trail — who may reach the graph, and on what footing — and those live
under `FAMILY`, which only the owner and the chief he named are ever preset to.

The one exception is `require_consent`, the gate every consent-dependent act asks before it
goes ahead. It runs under the scope of the act it guards, so a person may ask whether the
consent for an act is in force exactly when they may do the act, and never more widely.

Every refusal here is written into the trail with its name, like every other refusal. The
words in the refusals are for the developer reading a log, never for a person: nothing
renders `str(refusal)` (see `app.errors.Refusal`), and channels write their own sentence.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.audit.models import Action, Channel, Outcome
from app.audit.trail import record
from app.consent.models import PROXY_BASES, Consent, ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.texts import current_version, wording
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.identity.models import Person
from app.keys.context import KeyContext
from app.keys.models import Key
from app.keys.scopes import Scope
from app.regions import Region

AUDIT_CHANNEL: Mapping[ConsentChannel, Channel] = {
    ConsentChannel.APP: Channel.APP,
    ConsentChannel.WHATSAPP: Channel.WHATSAPP,
    # A paper form or a witnessed spoken agreement is entered by someone in the app; the
    # row says how it was captured, the trail says where the reach came from.
    ConsentChannel.PAPER: Channel.APP,
    ConsentChannel.VERBAL_WITNESSED: Channel.APP,
}


class NoConsent(Refusal):
    """The consent an act rests on is not in force. One subclass per way it can be missing."""

    def __init__(self, *, purpose: ConsentPurpose, context: KeyContext) -> None:
        super().__init__(f"{self.__class__.__doc__} ({purpose})")
        self.purpose = purpose
        self.context = context


class ConsentWithheld(NoConsent):
    """No consent to this was ever given on this profile."""


class ConsentRevoked(NoConsent):
    """Consent to this was given and has since been withdrawn."""


class ConsentOutOfDate(NoConsent):
    """Consent was given to older wording; the current wording needs a fresh agreement."""


class NotTheirConsentToGive(Refusal):
    """The owner agrees for himself on his own basis; anyone else needs a recorded proxy basis."""


class NotTheirConsentToWithdraw(Refusal):
    """Only the owner stops sharing with his family: it closes every key, his chief's too."""


class WordingNotOnFile(Refusal):
    """No such words were ever shown for this purpose, at this version, in this language."""


class NotTheCurrentWording(Refusal):
    """Opening a record is agreed to in today's words, not in words that have moved on."""


class NoConsentToWithdraw(Refusal):
    """Nothing of this purpose is in force on this profile, so there is nothing to withdraw."""


@dataclass(frozen=True, slots=True)
class RecordConsent:
    """What a person agreed to when opening his own record: which words, in which language,
    captured how. Every field is stated by the caller; none is inferred."""

    text_version: str
    language: str
    captured_via: ConsentChannel


@dataclass(frozen=True, slots=True)
class ConsentCheck:
    """What the gate hands back: enough to cite the consent an act rested on, and no more.

    Who gave it and on what basis stay in the record, which only the owner and his chief read.
    """

    consent_id: uuid.UUID
    purpose: ConsentPurpose
    text_version: str
    granted_at: datetime


def check_opening_words(consent: RecordConsent, region: Region) -> None:
    """Refuse, before any row is written, words that are not today's words on file here."""
    purpose = ConsentPurpose.HOLD_HEALTH_RECORD
    if consent.text_version != current_version(purpose):
        raise NotTheCurrentWording(f"{purpose} is agreed to at version {current_version(purpose)}")
    if wording(purpose, consent.text_version, consent.language, region) is None:
        raise WordingNotOnFile(f"{purpose} version {consent.text_version} in {consent.language}")


async def grant_consent(
    session: AsyncSession,
    *,
    context: KeyContext,
    purpose: ConsentPurpose,
    captured_via: ConsentChannel,
    basis: ConsentBasis,
    language: str | None = None,
    text_version: str | None = None,
    now: datetime | None = None,
) -> Consent:
    """Record that the person in the context agreed to `purpose`, in the words at `text_version`.

    The owner agrees for himself and only on `ConsentBasis.OWNER`. Someone acting for him —
    a chief, or later a steward — must hold the family scope and name a proxy basis.
    `text_version` defaults to the current wording; an older one is for capturing an
    agreement made before the words moved on, and it does not stand for the current
    version. Whichever version, the words must be on file in `language` for this region.
    """
    moment = now or utcnow()
    channel = AUDIT_CHANNEL[captured_via]
    version = text_version or current_version(purpose)
    if language is None:
        # An identity row, not profile data: the language the giver registered in. The
        # context is already resolved, so this names nobody the caller could not name.
        giver = await session.get(Person, context.person_id)
        language = giver.language if giver is not None else "en"

    # The door below refuses and records anyone without the family scope; the checks on the
    # basis and the words are only for those it would let through.
    if context.allows(Scope.FAMILY):
        refusal: Refusal | None = None
        if context.is_owner and basis is not ConsentBasis.OWNER:
            refusal = NotTheirConsentToGive(f"the owner agrees on his own basis, not {basis}")
        elif not context.is_owner and basis not in PROXY_BASES:
            refusal = NotTheirConsentToGive(
                f"a {context.role} needs a recorded proxy basis, not {basis}"
            )
        elif wording(purpose, version, language, context.region) is None:
            refusal = WordingNotOnFile(f"{purpose} version {version} was never shown in {language}")
        if refusal is not None:
            await _refused_write(session, context, refusal, channel, moment)
            raise refusal

    return await audited_write(
        session,
        Consent,
        context,
        Scope.FAMILY,
        channel=channel,
        now=moment,
        person_id=context.person_id,
        purpose=purpose,
        text_version=version,
        language=language,
        captured_via=captured_via,
        basis=basis,
        granted_at=moment,
    )


async def active_consents(
    session: AsyncSession,
    *,
    context: KeyContext,
    now: datetime | None = None,
) -> list[Consent]:
    """Every consent in force on this profile at this moment, oldest first, whatever its version."""
    moment = now or utcnow()
    rows = await audited_read(session, Consent, context, Scope.FAMILY, now=moment)
    return sorted(
        (row for row in rows if row.is_active(moment)), key=lambda row: as_utc(row.granted_at)
    )


async def all_consents(
    session: AsyncSession,
    *,
    context: KeyContext,
    now: datetime | None = None,
) -> list[Consent]:
    """Every consent ever given on this profile, withdrawn ones included, oldest first."""
    rows = await audited_read(session, Consent, context, Scope.FAMILY, now=now)
    return sorted(rows, key=lambda row: as_utc(row.granted_at))


async def require_consent(
    session: AsyncSession,
    *,
    context: KeyContext,
    purpose: ConsentPurpose,
    scope: Scope,
    channel: Channel = Channel.APP,
    now: datetime | None = None,
) -> ConsentCheck:
    """The gate: the consent for `purpose` that is in force right now, or a refusal.

    `scope` is the scope of the act this consent is being asked for. The check is refused
    exactly when the act would be, so a helper cannot learn from the gate what a chief
    could learn from the record. `channel` is where the act came from, and both the check
    and any refusal are written into the trail on it.
    """
    moment = now or utcnow()
    rows = await audited_read(
        session,
        Consent,
        context,
        scope,
        where=(Consent.purpose == purpose,),
        channel=channel,
        now=moment,
    )
    active = [row for row in rows if row.is_active(moment)]
    wanted = current_version(purpose)
    for row in sorted(active, key=lambda row: as_utc(row.granted_at), reverse=True):
        if row.text_version == wanted:
            return ConsentCheck(
                consent_id=row.id,
                purpose=row.purpose,
                text_version=row.text_version,
                granted_at=as_utc(row.granted_at),
            )

    refusal: type[NoConsent]
    if active:
        refusal = ConsentOutOfDate
    elif rows:
        refusal = ConsentRevoked
    else:
        refusal = ConsentWithheld
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=scope,
        target=Consent.__tablename__,
        outcome=Outcome.REFUSED,
        refused_because=refusal.__name__,
        channel=channel,
        now=moment,
    )
    raise refusal(purpose=purpose, context=context)


async def revoke_consent(
    session: AsyncSession,
    *,
    context: KeyContext,
    purpose: ConsentPurpose,
    captured_via: ConsentChannel,
    now: datetime | None = None,
) -> Sequence[Consent]:
    """Withdraw every consent to `purpose` still in force, whichever wording it was given to.

    The rows stay, marked with when and by whom; `captured_via` is how the withdrawal was
    captured, and the trail is written on the channel it came from.

    Withdrawing `SHARE_WITH_FAMILY` is the owner's alone: it closes every key on the profile
    in the same transaction — the chief's, the helper's, the clinic's and the emergency
    contact's alike — because the keys rest on that consent, and access has to be gone
    within the minute, not at the next review. A chief who wants one person out closes
    that key with `revoke_key`. The way back in is the owner agreeing again, which re-opens
    the cutting of keys; the emergency card is health data too, so no role is exempt.
    """
    moment = now or utcnow()
    channel = AUDIT_CHANNEL[captured_via]
    rows = await audited_read(
        session,
        Consent,
        context,
        Scope.FAMILY,
        where=(Consent.purpose == purpose,),
        channel=channel,
        now=moment,
    )
    refusal: Refusal | None = None
    open_rows = [row for row in rows if row.is_active(moment)]
    if purpose is ConsentPurpose.SHARE_WITH_FAMILY and not context.is_owner:
        refusal = NotTheirConsentToWithdraw(f"a {context.role} does not stop family sharing")
    elif not open_rows:
        refusal = NoConsentToWithdraw(f"nothing to withdraw for {purpose}")
    if refusal is not None:
        await _refused_write(session, context, refusal, channel, moment)
        raise refusal

    for row in open_rows:
        row.revoked_at = moment
        row.revoked_by_person_id = context.person_id
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=Consent.__tablename__,
        rows=len(open_rows),
        channel=channel,
        now=moment,
    )

    if purpose is ConsentPurpose.SHARE_WITH_FAMILY:
        await _close_every_key(session, context, channel, moment)
    return open_rows


async def _close_every_key(
    session: AsyncSession, context: KeyContext, channel: Channel, moment: datetime
) -> None:
    """Every key on the profile rests on the family consent; none outlives it."""
    keys = await audited_read(session, Key, context, Scope.FAMILY, channel=channel, now=moment)
    closed = 0
    for key in keys:
        if key.is_active(moment):
            key.revoked_at = moment
            closed += 1
    if closed:
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.FAMILY,
            target=Key.__tablename__,
            rows=closed,
            channel=channel,
            now=moment,
        )


async def _refused_write(
    session: AsyncSession,
    context: KeyContext,
    refusal: Refusal,
    channel: Channel,
    moment: datetime,
) -> None:
    """One line for a write of consent that did not land: the name of the refusal, no more."""
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=Consent.__tablename__,
        outcome=Outcome.REFUSED,
        refused_because=type(refusal).__name__,
        channel=channel,
        now=moment,
    )
