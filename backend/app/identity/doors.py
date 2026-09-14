"""The three doors after registration, and the claim that ends a stewardship (E01-01).

*For me* is `app.identity.service.create_own_profile`: the person opens his own graph.

*For someone I care for* is `set_up_for_someone`: a graph set up against the patient's
phone number, held by the person who set it up — the steward — on a declared basis until
the patient claims it. There is one graph per number, ever. A second person setting up for
the same number is refused in the same words whoever holds the first, and the answer names
nobody: not the steward, not the owner, not the graph.

*I was invited* needs nothing built here: a key cut for a phone number lands on the account
that number becomes when the person proves it (`app.identity.login`), and `doors` lists it.

The steward holds a chief key over everything but the patient's private notes
(`STEWARD_SCOPES`) and the agreement to Nura keeping the record, given on the patient's
behalf on the basis he declared. Until the claim there is no owner, so the steward reads
the trail and the consents the way a chief does. The claim is the patient's alone: he
registers with the number, sees what was set up for him and by whom, and says yes to a
draft that names the steward, the parts the steward keeps seeing and the words he read.
On that yes the graph becomes his, he agrees to Nura keeping it in his own words, the
steward's proxy agreement is withdrawn, he lets the steward in as a chief on a per-person
consent, the steward's key is cut again resting on it, and the stewardship closes. Every
step is on the trail.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard, audited_profile_read, audited_read, audited_write
from app.audit.models import Action, Outcome
from app.audit.trail import record
from app.consent.models import (
    DOCUMENTED_BASES,
    STEWARDSHIP_BASES,
    ConsentBasis,
    ConsentChannel,
    ConsentPurpose,
)
from app.consent.service import (
    NoSuchWitness,
    NothingBehindTheBasis,
    NotTheirConsentToGive,
    RecordConsent,
    Sharing,
    WordingNotOnFile,
    check_opening_words,
    grant_consent,
    revoke_consent,
)
from app.consent.texts import current_version, render_sharing, wording
from app.db import utcnow
from app.drafts import ClaimDraft
from app.errors import Refusal
from app.identity.models import Person, Profile, Stewardship
from app.keys.confirm import consume_confirmation
from app.keys.context import (
    KeyContext,
    Standing,
    owned_profile,
    profile_for_number,
    resolve_key_context,
    unknown_reach,
)
from app.keys.grants import grant_key
from app.keys.models import Key
from app.keys.scopes import STEWARD_SCOPES, KeyRole, KeyWindow, Scope
from app.memory.models import Artifact, ArtifactKind, SourceChannel
from app.regions import Region, guard_region


class AlreadySetUp(Refusal):
    """A graph is already set up for that number.

    The same words whether the patient opened it himself, someone else set it up for him,
    or the asker did so earlier: nothing in the answer says which, or who. The way in is
    a key from whoever holds it, never a second graph.
    """


class NotForYourself(Refusal):
    """Setting up for someone is for someone else; your own graph is the "for me" door."""


class NotTheClaimant(Refusal):
    """Only the person a graph was set up for — registered with that number — claims it."""


class NoStewardshipHere(Refusal):
    """This graph was never set up for someone: nobody stewards it, or ever did."""


@dataclass(frozen=True, slots=True)
class Evidence:
    """The document behind a documented basis, already stored in the region."""

    kind: ArtifactKind
    storage_key: str
    content_type: str
    sha256: str
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class Claimable:
    """A graph waiting for its patient: what he is shown before he says it is his."""

    profile: Profile
    stewardship: Stewardship
    steward: Person
    context: KeyContext
    draft: ClaimDraft
    hold_words: str
    sharing_words: str


@dataclass(frozen=True, slots=True)
class Held:
    """A graph a person reaches through a key, as he holds it."""

    profile: Profile
    context: KeyContext


@dataclass(frozen=True, slots=True)
class Doors:
    """Which doors apply to a person: his own graph, graphs waiting for his claim, graphs he
    was let in to, graphs he holds for someone."""

    own: Held | None
    claimable: list[Claimable]
    invited: list[Held]
    stewarding: list[Held]


# --- for someone I care for ---------------------------------------------------------------


async def set_up_for_someone(
    session: AsyncSession,
    *,
    region: Region,
    steward: Person,
    patient_phone_e164: str,
    display_name: str,
    language: str,
    consent: RecordConsent,
    basis: ConsentBasis,
    relationship: str | None = None,
    evidence: Evidence | None = None,
) -> tuple[Profile, Stewardship]:
    """Set up a graph for the person at `patient_phone_e164`, held by `steward` until claimed.

    `consent` is the agreement to Nura keeping the record as the steward read it, in the
    steward's language; it is recorded on `basis`, which is what entitles him to give it
    for the patient: the patient asked (and will claim), or a lasting power of attorney
    or a doctor's letter, whose document is `evidence` and is kept as the first artefact
    on the graph. A spoken agreement is not a basis a graph can be set up on: its witness
    must hold a key on the graph, and there are no keys yet.

    Everything is checked before a row is written, so a refusal leaves no graph behind.
    The one refusal with a graph to write under is `AlreadySetUp`; a person that graph
    knows is written into its trail, and a stranger is counted, not written, like any
    stranger reaching for a graph (`app.keys.context.on_unknown_reach`).
    """
    guard_region(held_in=steward.region, asked_from=region)
    if steward.phone_e164 is not None and steward.phone_e164 == patient_phone_e164:
        raise NotForYourself("your own graph opens through the for-me door")
    check_opening_words(consent, region)
    if basis not in STEWARDSHIP_BASES:
        if basis is ConsentBasis.VERBAL_RECORDED:
            raise NoSuchWitness(
                "a graph being set up has no keys yet, so nobody can have witnessed"
            )
        raise NotTheirConsentToGive(f"a graph is not set up for someone on basis {basis}")
    if basis in DOCUMENTED_BASES and evidence is None:
        raise NothingBehindTheBasis(f"{basis} needs the document as an artefact")

    existing = await profile_for_number(session, region=region, phone_e164=patient_phone_e164)
    if existing is not None:
        refusal = AlreadySetUp("a graph is already set up for that number")
        await _refuse_a_second_graph(session, existing=existing, asker=steward, refusal=refusal)
        raise refusal

    moment = utcnow()
    profile = Profile(
        region=region,
        display_name=display_name,
        language=language,
        owner_person_id=None,
        patient_phone_e164=patient_phone_e164,
        created_at=moment,
    )
    session.add(profile)
    await session.flush()
    # The steward's key is cut before any context can exist, like the profile itself: it is
    # what the context is resolved from. It rests on no consent yet; the stewardship says
    # what it rests on instead, and the claim replaces it with a key that does.
    key = Key(
        profile_id=profile.id,
        holder_person_id=steward.id,
        role=KeyRole.CHIEF,
        scopes=sorted(scope.value for scope in STEWARD_SCOPES),
        consent_id=None,
        granted_by_person_id=steward.id,
        granted_at=moment,
        expires_at=None,
    )
    session.add(key)
    await session.flush()

    context = await resolve_key_context(
        session, region=region, person_id=steward.id, profile_id=profile.id
    )
    assert context.is_steward  # a key on a graph with no owner
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.PROFILE,
        target=Profile.__tablename__,
        target_id=profile.id,
        rows=1,
    )
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=Key.__tablename__,
        target_id=key.id,
        rows=1,
    )

    artifact_id: uuid.UUID | None = None
    if evidence is not None:
        # Not `store_artifact`: that rests on the agreement to keep the record, and this
        # document is what that agreement rests on. It is the one artefact kept before it.
        artifact = await audited_write(
            session,
            Artifact,
            context,
            Scope.RECORDS,
            kind=evidence.kind,
            storage_key=evidence.storage_key,
            content_type=evidence.content_type,
            sha256=evidence.sha256,
            captured_at=evidence.captured_at,
            source_channel=SourceChannel.APP,
            region=region,
            stored_at=moment,
        )
        artifact_id = artifact.id

    hold = await grant_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        captured_via=consent.captured_via,
        basis=basis,
        language=consent.language,
        text_version=consent.text_version,
        basis_artifact_id=artifact_id,
    )
    stewardship = await audited_write(
        session,
        Stewardship,
        context,
        Scope.FAMILY,
        steward_person_id=steward.id,
        key_id=key.id,
        consent_id=hold.id,
        basis=basis,
        relationship=relationship,
        opened_at=moment,
    )
    return profile, stewardship


async def _refuse_a_second_graph(
    session: AsyncSession, *, existing: Profile, asker: Person, refusal: Refusal
) -> None:
    """The refusal is the same for everyone; where it is written depends on who asked."""
    known = existing.owner_person_id == asker.id or bool(
        (
            await session.scalars(
                select(Key.id).where(
                    Key.profile_id == existing.id, Key.holder_person_id == asker.id
                )
            )
        ).first()
    )
    if not known:
        unknown_reach(asker.id, existing.id)
        return
    await record(
        session,
        context=KeyContext(
            profile_id=existing.id,
            region=existing.region,
            person_id=asker.id,
            scopes=frozenset(),
            standing=Standing.NONE,
        ),
        action=Action.WRITE,
        scope=Scope.PROFILE,
        target=Profile.__tablename__,
        outcome=Outcome.REFUSED,
        refused_because=type(refusal).__name__,
    )


# --- the stewardship, as anyone holding the graph reads it --------------------------------


async def stewardship_of(session: AsyncSession, *, context: KeyContext) -> Stewardship | None:
    """The stewardship on this graph, open or closed, or None if it was never set up for
    someone. Read under `Scope.PROFILE`: who holds a graph for whom is part of whose graph
    it is, and every key — the claimant's least of all — opens that much."""
    found = await audited_read(session, Stewardship, context, Scope.PROFILE)
    return found[0] if found else None


async def require_stewardship(session: AsyncSession, *, context: KeyContext) -> Stewardship:
    found = await stewardship_of(session, context=context)
    if found is None:
        raise NoStewardshipHere(f"profile {context.profile_id} was never set up for someone")
    return found


async def _what_the_steward_sees(
    session: AsyncSession, *, context: KeyContext, stewardship: Stewardship
) -> frozenset[Scope]:
    """The parts the steward's key opens, minus the face of the graph that every key opens.

    The key is the one the stewardship row just read under the context names; reading
    the row it names is reading what the context already let through, the way
    `app.audit.access.person_display_name` reads the person a row names.
    """
    key = await session.get(Key, stewardship.key_id)
    assert key is not None and key.profile_id == context.profile_id  # the row names it
    return key.scopes_held - {Scope.PROFILE}


def claim_draft(stewardship: Stewardship, *, scopes: frozenset[Scope], language: str) -> ClaimDraft:
    """What the patient says yes to: this stewardship, this steward, these parts, these
    words. The service recomputes it at the claim, so a yes to anything else is refused."""
    return ClaimDraft(
        stewardship_id=stewardship.id,
        steward_person_id=stewardship.steward_person_id,
        scopes=tuple(sorted(scope.value for scope in scopes)),
        language=language,
        hold_wording_version=current_version(ConsentPurpose.HOLD_HEALTH_RECORD),
        sharing_wording_version=current_version(ConsentPurpose.SHARE_WITH_PERSON),
    )


async def claim_draft_for(
    session: AsyncSession, *, context: KeyContext, language: str
) -> ClaimDraft:
    """The claim draft as it stands on this graph now, for a yes to be minted or spent."""
    stewardship = await require_stewardship(session, context=context)
    scopes = await _what_the_steward_sees(session, context=context, stewardship=stewardship)
    return claim_draft(stewardship, scopes=scopes, language=language)


# --- the claim -----------------------------------------------------------------------------


async def claimable_for(
    session: AsyncSession, *, region: Region, person: Person, language: str | None = None
) -> list[Claimable]:
    """The graphs set up for this person's number that nobody owns yet, with what he is
    shown before claiming: who set it up, what they keep seeing, and the words in
    `language` (his own, unless the app says which he is reading)."""
    if person.phone_e164 is None:
        return []
    profile = await profile_for_number(session, region=region, phone_e164=person.phone_e164)
    if profile is None or not profile.is_stewarded:
        return []
    context = await resolve_key_context(
        session, region=region, person_id=person.id, profile_id=profile.id
    )
    if not context.is_claimant:
        return []
    return [await _claimable(session, context=context, language=language or person.language)]


async def _claimable(session: AsyncSession, *, context: KeyContext, language: str) -> Claimable:
    profile = await audited_profile_read(session, context)
    stewardship = await require_stewardship(session, context=context)
    steward = await session.get(Person, stewardship.steward_person_id)
    assert steward is not None  # the stewardship names this row
    scopes = await _what_the_steward_sees(session, context=context, stewardship=stewardship)
    draft = claim_draft(stewardship, scopes=scopes, language=language)
    hold = wording(
        ConsentPurpose.HOLD_HEALTH_RECORD, draft.hold_wording_version, language, context.region
    )
    template = wording(
        ConsentPurpose.SHARE_WITH_PERSON, draft.sharing_wording_version, language, context.region
    )
    if hold is None or template is None:
        raise WordingNotOnFile(f"no words in {language} for the claim")
    return Claimable(
        profile=profile,
        stewardship=stewardship,
        steward=steward,
        context=context,
        draft=draft,
        hold_words=hold,
        sharing_words=render_sharing(
            template,
            name=steward.display_name,
            relationship=stewardship.relationship,
            scopes=scopes,
            language=language,
        ),
    )


async def claim_profile(
    session: AsyncSession,
    *,
    context: KeyContext,
    confirmation_id: uuid.UUID,
    language: str,
    captured_via: ConsentChannel = ConsentChannel.APP,
) -> Profile:
    """The patient says the graph set up for him is his, and it becomes his.

    `context` is his, resolved as the claimant. `confirmation_id` is a yes he minted for
    the `ClaimDraft` recomputed here — same stewardship, same steward, same parts, same
    words in `language` — and it is spent once. Then, in one transaction and each on the
    trail: the graph's ownership passes to him; the steward's proxy agreement to keeping
    the record is withdrawn and his own recorded in his words; he agrees to let the
    steward in to the parts the steward held; the steward's key is cut again as a chief key
    resting on that agreement; and the stewardship closes, naming him.
    """
    if not context.is_claimant:
        refusal = NotTheClaimant("only the person the graph was set up for claims it")
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.PROFILE,
            target=Profile.__tablename__,
            outcome=Outcome.REFUSED,
            refused_because=type(refusal).__name__,
        )
        raise refusal
    # One door for the whole claim: whatever it refuses — a yes for other words, a spent
    # yes, an old one — is written into the graph's trail before it is passed on.
    async with audited_guard(session, context, Action.WRITE, Scope.PROFILE, Profile.__tablename__):
        stewardship = await require_stewardship(session, context=context)
        scopes = await _what_the_steward_sees(session, context=context, stewardship=stewardship)
        draft = claim_draft(stewardship, scopes=scopes, language=language)
        await consume_confirmation(session, context, confirmation_id, draft)

        moment = utcnow()
        profile = await session.get(Profile, context.profile_id)
        assert profile is not None  # the context was resolved from this row
        profile.owner_person_id = context.person_id
        await session.flush()
        owner = await resolve_key_context(
            session, region=context.region, person_id=context.person_id, profile_id=profile.id
        )
        assert owner.is_owner
        await record(
            session,
            context=owner,
            action=Action.WRITE,
            scope=Scope.PROFILE,
            target=Profile.__tablename__,
            target_id=profile.id,
            rows=1,
        )
        await _hand_over(
            session,
            owner=owner,
            stewardship=stewardship,
            scopes=scopes,
            draft=draft,
            captured_via=captured_via,
            moment=moment,
        )
    return profile


async def _hand_over(
    session: AsyncSession,
    *,
    owner: KeyContext,
    stewardship: Stewardship,
    scopes: frozenset[Scope],
    draft: ClaimDraft,
    captured_via: ConsentChannel,
    moment: datetime,
) -> None:
    """The rest of the claim, in the owner's name: the consents, the key, the closing."""
    language = draft.language

    # The steward's footing ends with the claim: the agreement he gave for the patient is
    # withdrawn, and the patient's own is recorded in the words he read, in his language.
    await revoke_consent(
        session,
        context=owner,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        captured_via=captured_via,
    )
    await grant_consent(
        session,
        context=owner,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        captured_via=captured_via,
        basis=ConsentBasis.OWNER,
        language=language,
        text_version=draft.hold_wording_version,
    )
    steward = await session.get(Person, stewardship.steward_person_id)
    assert steward is not None  # the stewardship names this row
    await grant_consent(
        session,
        context=owner,
        purpose=ConsentPurpose.SHARE_WITH_PERSON,
        captured_via=captured_via,
        basis=ConsentBasis.OWNER,
        language=language,
        sharing=Sharing(holder=steward, scopes=scopes, relationship=stewardship.relationship),
        text_version=draft.sharing_wording_version,
    )
    # `grant_key` closes the steward's key and cuts the chief key that rests on the consent.
    await grant_key(
        session,
        context=owner,
        holder=steward,
        role=KeyRole.CHIEF,
        scopes=scopes,
        window=KeyWindow.ALWAYS,
    )
    stewardship.closed_at = moment
    stewardship.claimed_by_person_id = owner.person_id
    await session.flush()
    await record(
        session,
        context=owner,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=Stewardship.__tablename__,
        target_id=stewardship.id,
        rows=1,
    )


# --- which doors apply -----------------------------------------------------------------------


async def doors_for(
    session: AsyncSession, *, region: Region, person: Person, language: str | None = None
) -> Doors:
    """Which doors apply to this person, each graph read the way every graph is read: through
    a context, written down."""
    own: Held | None = None
    found = await owned_profile(session, region=region, owner_person_id=person.id)
    if found is not None:
        context = await resolve_key_context(
            session, region=region, person_id=person.id, profile_id=found.id
        )
        own = Held(profile=await audited_profile_read(session, context), context=context)

    moment = utcnow()
    invited: list[Held] = []
    stewarding: list[Held] = []
    keys = await session.scalars(
        select(Key).where(Key.holder_person_id == person.id).order_by(Key.granted_at)
    )
    for key in keys:
        if not key.is_active(moment):
            continue
        context = await resolve_key_context(
            session, region=region, person_id=person.id, profile_id=key.profile_id
        )
        held = Held(profile=await audited_profile_read(session, context), context=context)
        (stewarding if context.is_steward else invited).append(held)

    return Doors(
        own=own,
        claimable=await claimable_for(session, region=region, person=person, language=language),
        invited=invited,
        stewarding=stewarding,
    )


__all__ = [
    "AlreadySetUp",
    "Claimable",
    "Doors",
    "Evidence",
    "Held",
    "NoStewardshipHere",
    "NotForYourself",
    "NotTheClaimant",
    "claim_draft",
    "claim_draft_for",
    "claim_profile",
    "claimable_for",
    "doors_for",
    "require_stewardship",
    "set_up_for_someone",
    "stewardship_of",
]
