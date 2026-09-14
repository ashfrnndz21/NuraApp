"""Giving, withdrawing, listing and checking consent.

Consent is reached under `Scope.FAMILY`. There is no `CONSENT` scope on purpose: scopes are
the parts of the graph a key can be cut to, and the record of what the patient agreed to
is not a part of the graph anyone is ever cut a key to. It is the same class of thing as
the keys and the trail — who may reach the graph, and on what footing — and those live
under `FAMILY`, which only the owner and the chief he named are ever preset to.

The one exception is `require_consent`, the gate every consent-dependent act asks before it
goes ahead. It runs under the scope of the act it guards, so a person may ask whether the
consent for an act is in force exactly when they may do the act, and never more widely.

Letting someone in is agreed to one person at a time: a `SHARE_WITH_PERSON` consent names
the holder and the parts they may see, in words rendered with that name and those parts; a
key is cut under that consent, records it, and is never wider than it; withdrawing it closes
that person's keys and nobody else's. Keeping the record, recording and WhatsApp are agreed
to for the profile as a whole.

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
from app.consent.texts import current_version, render_sharing, wording
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.identity.models import Person
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
    """The consent an act rests on is not in force. One subclass per way it can be missing.

    Carries the purpose and nothing else: no context, no ids, nothing an error reporter
    could ship out of region. The message is developer copy; no channel renders it.
    """

    def __init__(self, *, purpose: ConsentPurpose) -> None:
        super().__init__(f"{type(self).__name__}: {purpose.value}")
        self.purpose = purpose


class ConsentWithheld(NoConsent):
    """No consent to this was ever given on this profile."""


class ConsentRevoked(NoConsent):
    """Consent to this was given and has since been withdrawn."""


class ConsentOutOfDate(NoConsent):
    """Consent was given to older wording; the current wording needs a fresh agreement."""


class NotTheirConsentToGive(Refusal):
    """The owner agrees for himself on his own basis; anyone else needs a recorded proxy basis."""


class NotTheirConsentToWithdraw(Refusal):
    """Only the owner stops letting someone in: it closes that person's keys."""


class NothingBehindTheBasis(Refusal):
    """A proxy basis is a document or a witnessed word; this named neither."""


class NoSuchWitness(Refusal):
    """The witness to a spoken agreement is the person recording it or someone with a key."""


class NoHolderNamed(Refusal):
    """Letting someone in is agreed to one person at a time; this named nobody."""


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
class Sharing:
    """Who is being let in, to which parts, and — only if the granter says — who they are to
    him ("your daughter", "the clinic"). The words the patient reads are rendered from this."""

    holder: Person
    scopes: frozenset[Scope]
    relationship: str | None = None
    """Who they are to him, in the language of the words, or nothing. The words decide how
    to say it (`app.consent.texts.named_words`); nothing is baked into the name."""

    # @patient
    @property
    def name(self) -> str:
        """The person as the words name them, bare: "Ash"."""
        return self.holder.display_name


@dataclass(frozen=True, slots=True)
class ConsentCheck:
    """What the gate hands back: enough to cite the consent an act rested on, and no more.

    Who gave it and on what basis stay in the record, which only the owner and his chief read.
    `scopes` is what a per-holder consent lets the person see, so a key is cut no wider.
    """

    consent_id: uuid.UUID
    purpose: ConsentPurpose
    text_version: str
    granted_at: datetime
    scopes: frozenset[Scope] | None = None


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
    purpose: ConsentPurpose,
    basis: ConsentBasis,
    basis_artifact_id: uuid.UUID | None,
    witness_person_id: uuid.UUID | None,
    moment: datetime,
) -> Refusal | None:
    """What has to be behind a proxy basis. Reads go through the doors like any other."""
    if context.is_owner and basis is not ConsentBasis.OWNER:
        return NotTheirConsentToGive(f"the owner agrees on his own basis, not {basis}")
    if basis is ConsentBasis.PATIENT_ASKED:
        # The patient asked, and his claim is the proof to come: until then this basis
        # carries the steward's agreement to Nura keeping the record, and nothing else.
        if not context.is_steward or purpose is not ConsentPurpose.HOLD_HEALTH_RECORD:
            return NotTheirConsentToGive(
                f"{basis} carries only a steward's agreement to keeping the record"
            )
        return None
    if not context.is_owner and basis not in PROXY_BASES:
        return NotTheirConsentToGive(f"a {context.role} needs a recorded proxy basis, not {basis}")
    if basis in DOCUMENTED_BASES and basis_artifact_id is None:
        return NothingBehindTheBasis(f"{basis} needs the document as an artefact")
    if basis is ConsentBasis.VERBAL_RECORDED:
        # A spoken agreement needs both halves: a second person who heard it and holds a
        # key here — never the one writing it down — and the recording as an artefact.
        if witness_person_id is None or witness_person_id == context.person_id:
            return NoSuchWitness("a spoken agreement names who else heard it")
        heard_by = await audited_read(
            session,
            Key,
            context,
            Scope.FAMILY,
            where=(Key.holder_person_id == witness_person_id,),
        )
        if not any(key.is_active(moment) for key in heard_by):
            return NoSuchWitness(f"person {witness_person_id} holds no key here")
        if basis_artifact_id is None:
            return NothingBehindTheBasis(f"{basis} needs the recording as an artefact")
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
    sharing: Sharing | None = None,
    basis_artifact_id: uuid.UUID | None = None,
    witness_person_id: uuid.UUID | None = None,
    text_version: str | None = None,
) -> Consent:
    """Record that the person in the context agreed to `purpose`, in the words at `text_version`.

    The owner agrees for himself and only on `ConsentBasis.OWNER`. Someone acting for him —
    a chief, or a steward — must hold the family scope, name a proxy basis, and have
    something behind it: the document as an artefact on the profile for `LPA` and
    `MEDICAL_LETTER`, the witness (and the recording, if there is one) for
    `VERBAL_RECORDED`. `PATIENT_ASKED` is a steward's alone, and only for keeping the
    record until the patient's claim (E01). `SHARE_WITH_PERSON` takes `sharing`: who, to which parts, and the
    words are rendered with that name and those parts before they are kept.

    `language` is the language the words were shown in; it is stated, never inferred.
    `text_version` defaults to the current wording; an older one is for capturing an
    agreement made before the words moved on, and it does not stand for the current
    version. Whichever version, the words are on file and are copied onto the row as read.
    """
    moment = utcnow()
    channel = AUDIT_CHANNEL[captured_via]
    version = text_version or current_version(purpose)

    # The door below refuses and records anyone without the family scope; the checks on the
    # shape, the basis and the words are only for those it would let through.
    words = ""  # never written: the door refuses first
    if context.allows(Scope.FAMILY):
        refusal: Refusal | None = None
        template = wording(purpose, version, language, context.region)
        if purpose in PER_HOLDER and sharing is None:
            refusal = NoHolderNamed(f"{purpose} names who may hold a key, and to what")
        elif purpose not in PER_HOLDER and sharing is not None:
            refusal = NotAgreedPerPerson(f"{purpose} is for the whole profile")
        elif template is None:
            refusal = WordingNotOnFile(f"{purpose} version {version} was never shown in {language}")
        else:
            refusal = await _check_basis(
                session, context, purpose, basis, basis_artifact_id, witness_person_id, moment
            )
        if refusal is not None:
            await _refused_write(session, context, refusal, channel, moment)
            raise refusal
        assert template is not None
        words = (
            render_sharing(
                template,
                name=sharing.name,
                relationship=sharing.relationship,
                scopes=sharing.scopes,
                language=language,
            )
            if sharing is not None
            else template
        )

    return await audited_write(
        session,
        Consent,
        context,
        Scope.FAMILY,
        channel=channel,
        person_id=context.person_id,
        purpose=purpose,
        holder_person_id=sharing.holder.id if sharing is not None else None,
        scopes=sorted(scope.value for scope in sharing.scopes) if sharing is not None else None,
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
    at: datetime | None = None,
) -> list[Consent]:
    """Every consent in force on this profile at this moment, oldest first, whatever its version."""
    moment = at or utcnow()
    rows = await audited_read(session, Consent, context, Scope.FAMILY)
    return sorted(
        (row for row in rows if row.is_active(moment)), key=lambda row: as_utc(row.granted_at)
    )


async def all_consents(
    session: AsyncSession,
    *,
    context: KeyContext,
) -> list[Consent]:
    """Every consent ever given on this profile, withdrawn ones included, oldest first."""
    rows = await audited_read(session, Consent, context, Scope.FAMILY)
    return sorted(rows, key=lambda row: as_utc(row.granted_at))


def _about(
    purpose: ConsentPurpose, holder_person_id: uuid.UUID | None
) -> list[ColumnElement[bool]]:
    """Rows about this purpose, and for a per-holder purpose about this one person."""
    where: list[ColumnElement[bool]] = [Consent.purpose == purpose]
    if purpose in PER_HOLDER:
        where.append(Consent.holder_person_id == holder_person_id)
    return where


def read_scope(purpose: ConsentPurpose, scope: Scope) -> Scope:
    """The scope a consent of this purpose is read under: the act's own for a profile-wide
    purpose, `FAMILY` for a per-holder one, whatever the caller asked."""
    return Scope.FAMILY if purpose in PER_HOLDER else scope


def _shape(purpose: ConsentPurpose, holder_person_id: uuid.UUID | None) -> Refusal | None:
    if purpose in PER_HOLDER and holder_person_id is None:
        return NoHolderNamed(f"{purpose} is asked about one person at a time")
    return None


async def require_consent(
    session: AsyncSession,
    *,
    context: KeyContext,
    purpose: ConsentPurpose,
    scope: Scope,
    holder_person_id: uuid.UUID | None = None,
    channel: Channel = Channel.APP,
) -> ConsentCheck:
    """The gate: the consent for `purpose` that is in force right now, or a refusal.

    `scope` is the scope of the act this consent is being asked for. The check is refused
    exactly when the act would be, so a helper cannot learn from the gate what a chief
    could learn from the record. For a per-holder purpose, `holder_person_id` says whom the
    act is for, and the read runs under `FAMILY` whatever the act's scope: who else was let
    in, and to what, is the family list, and the family list is the owner's and his chief's
    (`app.audit.access.person_display_name` says the same). `channel` is where the act came
    from, and both the check and any refusal are written into the trail on it.
    """
    moment = utcnow()
    scope = read_scope(purpose, scope)
    misshapen = _shape(purpose, holder_person_id)
    if misshapen is not None:
        await _refused_read(session, context, misshapen, scope, channel, moment)
        raise misshapen
    rows = await audited_read(
        session,
        Consent,
        context,
        scope,
        where=_about(purpose, holder_person_id),
        channel=channel,
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
                scopes=(
                    frozenset(Scope(name) for name in row.scopes)
                    if row.scopes is not None
                    else None
                ),
            )

    refusal: NoConsent
    if active:
        refusal = ConsentOutOfDate(purpose=purpose)
    elif rows:
        refusal = ConsentRevoked(purpose=purpose)
    else:
        refusal = ConsentWithheld(purpose=purpose)
    await _refused_read(session, context, refusal, scope, channel, moment)
    raise refusal


async def revoke_consent(
    session: AsyncSession,
    *,
    context: KeyContext,
    purpose: ConsentPurpose,
    captured_via: ConsentChannel,
    holder_person_id: uuid.UUID | None = None,
) -> Sequence[Consent]:
    """Withdraw every consent to `purpose` still in force, whichever wording it was given to.

    The rows stay, marked with when and by whom; `captured_via` is how the withdrawal was
    captured, and the trail is written on the channel it came from.

    Withdrawing `SHARE_WITH_PERSON` names the person it is withdrawn from and is the
    owner's alone: it closes every key that person holds, in the same transaction — a chief
    or an emergency contact alike, because the key rests on that consent and access has to
    be gone within the minute, not at the next review. A chief who wants someone out closes
    the key with `revoke_key`. The way back in is the owner agreeing again for that person,
    which lets a key be cut again.

    Withdrawing `HOLD_HEALTH_RECORD` stops anything more being kept; what is already kept
    is the deletion story's to remove, not this one's.
    """
    moment = utcnow()
    channel = AUDIT_CHANNEL[captured_via]
    misshapen = _shape(purpose, holder_person_id)
    if misshapen is not None:
        await _refused_write(session, context, misshapen, channel, moment)
        raise misshapen
    rows = await audited_read(
        session,
        Consent,
        context,
        Scope.FAMILY,
        where=_about(purpose, holder_person_id),
        channel=channel,
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
    )

    if purpose in PER_HOLDER:
        assert holder_person_id is not None  # `_shape` refused otherwise
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
        )


async def _refused_read(
    session: AsyncSession,
    context: KeyContext,
    refusal: Refusal,
    scope: Scope,
    channel: Channel,
    moment: datetime,
) -> None:
    """One line for a check of consent that did not land: the name of the refusal, no more."""
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=scope,
        target=Consent.__tablename__,
        outcome=Outcome.REFUSED,
        refused_because=type(refusal).__name__,
        channel=channel,
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
    )
