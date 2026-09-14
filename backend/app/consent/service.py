"""Giving, withdrawing, listing and checking consent.

Consent is reached under `Scope.FAMILY`. There is no `CONSENT` scope on purpose: scopes are
the parts of the graph a key can be cut to, and the record of what the patient agreed to
is not a part of the graph anyone is ever cut a key to. It is the same class of thing as
the keys and the trail — who may reach the graph, and on what footing — and those live
under `FAMILY`, which only the owner and the chief he named are ever preset to.

The one exception is `require_consent`, the gate every consent-dependent act asks before it
goes ahead. It runs under the scope of the act it guards, so a person may ask whether the
consent for an act is in force exactly when they may do the act, and never more widely.

Sharing is agreed to one person at a time: a `SHARE_WITH_FAMILY` consent names the holder,
a key is cut under that consent and records it, and withdrawing it closes that person's
keys and nobody else's. Keeping the record, recording and WhatsApp are agreed to for the
profile as a whole.

Every refusal here is written into the trail with its name, like every other refusal. The
words in the refusals are for the developer reading a log, never for a person: nothing
renders `str(refusal)` (see `app.errors.Refusal`), and channels write their own sentence.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.audit.models import Action, Channel, Outcome
from app.audit.trail import record
from app.consent.models import (
    DOCUMENTED_BASES,
    PER_HOLDER,
    PROXY_BASES,
    Consent,
    ConsentBasis,
    ConsentChannel,
    ConsentPurpose,
)
from app.consent.texts import current_version, wording
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.models import Key
from app.keys.scopes import Scope
from app.memory.models import Artifact
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
    """Only the owner stops sharing with someone: it closes that person's keys."""


class NothingBehindTheBasis(Refusal):
    """A proxy basis is a document or a witnessed word; this named neither."""


class NoSuchWitness(Refusal):
    """The witness to a spoken agreement is the person recording it or someone with a key."""


class NoHolderNamed(Refusal):
    """Sharing is agreed to one person at a time; this named nobody."""


class NotAgreedPerPerson(Refusal):
    """This purpose is agreed to for the whole profile, not for one person."""


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


async def _check_basis(
    session: AsyncSession,
    context: KeyContext,
    basis: ConsentBasis,
    basis_artifact_id: uuid.UUID | None,
    witness_person_id: uuid.UUID | None,
    moment: datetime,
) -> Refusal | None:
    """What has to be behind a proxy basis. Reads go through the doors like any other."""
    if context.is_owner and basis is not ConsentBasis.OWNER:
        return NotTheirConsentToGive(f"the owner agrees on his own basis, not {basis}")
    if not context.is_owner and basis not in PROXY_BASES:
        return NotTheirConsentToGive(f"a {context.role} needs a recorded proxy basis, not {basis}")
    if basis in DOCUMENTED_BASES and basis_artifact_id is None:
        return NothingBehindTheBasis(f"{basis} needs the document as an artefact")
    if basis is ConsentBasis.VERBAL_RECORDED:
        if witness_person_id is None:
            return NoSuchWitness("a spoken agreement names who heard it")
        if witness_person_id != context.person_id:
            heard_by = await audited_read(
                session,
                Key,
                context,
                Scope.FAMILY,
                where=(Key.holder_person_id == witness_person_id,),
                now=moment,
            )
            if not any(key.is_active(moment) for key in heard_by):
                return NoSuchWitness(f"person {witness_person_id} holds no key here")
    if basis_artifact_id is not None:
        # The document or the recording, as an artefact on this profile and no other. Read
        # through the door under the records scope, like any artefact; `app.memory` reaches
        # this module for its own gate, so the read is made here rather than imported.
        behind = await audited_read(
            session,
            Artifact,
            context,
            Scope.RECORDS,
            where=(Artifact.id == basis_artifact_id,),
            now=moment,
        )
        if not behind:
            return NothingBehindTheBasis(f"no artefact {basis_artifact_id} on this profile")
    return None


async def grant_consent(
    session: AsyncSession,
    *,
    context: KeyContext,
    purpose: ConsentPurpose,
    captured_via: ConsentChannel,
    basis: ConsentBasis,
    language: str,
    holder_person_id: uuid.UUID | None = None,
    basis_artifact_id: uuid.UUID | None = None,
    witness_person_id: uuid.UUID | None = None,
    text_version: str | None = None,
    now: datetime | None = None,
) -> Consent:
    """Record that the person in the context agreed to `purpose`, in the words at `text_version`.

    The owner agrees for himself and only on `ConsentBasis.OWNER`. Someone acting for him —
    a chief, or later a steward — must hold the family scope, name a proxy basis, and have
    something behind it: the document as an artefact on the profile for `LPA` and
    `MEDICAL_LETTER`, the witness (and the recording, if there is one) for
    `VERBAL_RECORDED`. `SHARE_WITH_FAMILY` names the `holder_person_id` it is about.

    `language` is the language the words were shown in; it is stated, never inferred.
    `text_version` defaults to the current wording; an older one is for capturing an
    agreement made before the words moved on, and it does not stand for the current
    version. Whichever version, the words are on file and are copied onto the row.
    """
    moment = now or utcnow()
    channel = AUDIT_CHANNEL[captured_via]
    version = text_version or current_version(purpose)

    # The door below refuses and records anyone without the family scope; the checks on the
    # shape, the basis and the words are only for those it would let through.
    if context.allows(Scope.FAMILY):
        refusal: Refusal | None = None
        words = wording(purpose, version, language, context.region)
        if purpose in PER_HOLDER and holder_person_id is None:
            refusal = NoHolderNamed(f"{purpose} names who may hold a key")
        elif purpose not in PER_HOLDER and holder_person_id is not None:
            refusal = NotAgreedPerPerson(f"{purpose} is for the whole profile")
        elif words is None:
            refusal = WordingNotOnFile(f"{purpose} version {version} was never shown in {language}")
        else:
            refusal = await _check_basis(
                session, context, basis, basis_artifact_id, witness_person_id, moment
            )
        if refusal is not None:
            await _refused_write(session, context, refusal, channel, moment)
            raise refusal
        assert words is not None
    else:
        words = ""  # never written: the door refuses first

    return await audited_write(
        session,
        Consent,
        context,
        Scope.FAMILY,
        channel=channel,
        now=moment,
        person_id=context.person_id,
        purpose=purpose,
        holder_person_id=holder_person_id,
        text_version=version,
        language=language,
        wording_text=words,
        captured_via=captured_via,
        basis=basis,
        basis_artifact_id=basis_artifact_id,
        witness_person_id=witness_person_id,
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


def _about(purpose: ConsentPurpose, holder_person_id: uuid.UUID | None) -> list[ColumnElement[bool]]:
    where: list[ColumnElement[bool]] = [Consent.purpose == purpose]
    if purpose in PER_HOLDER:
        if holder_person_id is None:
            raise NoHolderNamed(f"{purpose} is asked about one person at a time")
        where.append(Consent.holder_person_id == holder_person_id)
    return where


async def require_consent(
    session: AsyncSession,
    *,
    context: KeyContext,
    purpose: ConsentPurpose,
    scope: Scope,
    holder_person_id: uuid.UUID | None = None,
    channel: Channel = Channel.APP,
    now: datetime | None = None,
) -> ConsentCheck:
    """The gate: the consent for `purpose` that is in force right now, or a refusal.

    `scope` is the scope of the act this consent is being asked for. The check is refused
    exactly when the act would be, so a helper cannot learn from the gate what a chief
    could learn from the record. For a per-holder purpose, `holder_person_id` says whom the
    act is for. `channel` is where the act came from, and both the check and any refusal
    are written into the trail on it.
    """
    moment = now or utcnow()
    rows = await audited_read(
        session,
        Consent,
        context,
        scope,
        where=_about(purpose, holder_person_id),
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
    holder_person_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> Sequence[Consent]:
    """Withdraw every consent to `purpose` still in force, whichever wording it was given to.

    The rows stay, marked with when and by whom; `captured_via` is how the withdrawal was
    captured, and the trail is written on the channel it came from.

    Withdrawing `SHARE_WITH_FAMILY` names the person it is withdrawn from and is the
    owner's alone: it closes every key that person holds, in the same transaction — a chief
    or an emergency contact alike, because the key rests on that consent and access has to
    be gone within the minute, not at the next review. A chief who wants someone out closes
    the key with `revoke_key`. The way back in is the owner agreeing again for that person,
    which lets a key be cut again.

    Withdrawing `HOLD_HEALTH_RECORD` stops anything more being kept; what is already kept
    is the deletion story's to remove, not this one's.
    """
    moment = now or utcnow()
    channel = AUDIT_CHANNEL[captured_via]
    rows = await audited_read(
        session,
        Consent,
        context,
        Scope.FAMILY,
        where=_about(purpose, holder_person_id),
        channel=channel,
        now=moment,
    )
    refusal: Refusal | None = None
    open_rows = [row for row in rows if row.is_active(moment)]
    if purpose in PER_HOLDER and not context.is_owner:
        refusal = NotTheirConsentToWithdraw(f"a {context.role} does not stop sharing")
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
        assert holder_person_id is not None  # `_about` refused otherwise
        await _close_keys_held_by(session, context, holder_person_id, channel, moment)
    return open_rows


async def _close_keys_held_by(
    session: AsyncSession,
    context: KeyContext,
    holder_person_id: uuid.UUID,
    channel: Channel,
    moment: datetime,
) -> None:
    """This person's keys rest on the consent just withdrawn; none of them outlives it."""
    keys = await audited_read(
        session,
        Key,
        context,
        Scope.FAMILY,
        where=(Key.holder_person_id == holder_person_id,),
        channel=channel,
        now=moment,
    )
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
