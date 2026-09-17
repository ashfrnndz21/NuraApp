"""The family's group on WhatsApp (E11-01): the family thread (E12-02), mirrored.

Who is in the group is who reads the family thread: the patient, and every live key that
holds the family's part. It is never stored. It is worked out from the keys each time the
group is used — opened, a key cut or closed, a message mirrored out — and told to the
provider then (`set_group_members`), so a key closed is a person out of the group, and a
message from someone the keys no longer name is not taken in (`is_member`).

Both ways, the thread is the one record. A message written in the app's thread is said in
the group, in its poster's name (`mirror_to_group`); a message posted in the group lands in
the thread in its poster's name (`app.channels.whatsapp.inbound`), and is not said back. A
photo follows the same two roads (#149, `mirror_photo_to_group`): shared in the app it is
sent into the group too, and posted in the group it lands in the thread — always the family's
photo, on the family scope alone (`app.family.photos.share_photo`), never his papers: filing
one of his papers is its own separate door (`app.ingestion.documents`), never reached from a
group photo by this alone. Nothing here reads a fact out of what the family says to each
other.

Who may be in it (#143). The patient, while his agreement to WhatsApp is in force: it is his
agreement to be messaged there, and it is his alone. Everyone else, while their key reads the
family's part and on their own yes to the group, given on that key at the key-accept step, because each
member's number is seen by the others (`app.channels.whatsapp.opt_in`). A withdrawal, a key
closed, a no to the group, a closing account: the group is set again at once, where it
happens (`withdraw`, and every route that changes who reads the thread; held by a test), not
at its next use. A closing account empties it, and nothing is mirrored while it stands.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read, audited_write
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.channels.whatsapp.models import WhatsAppGroup
from app.channels.whatsapp.opt_in import WhatsAppOptIn
from app.channels.whatsapp.provider import WhatsAppProvider
from app.channels.whatsapp.strings import GROUP_NAME, reply
from app.channels.whatsapp.templates import language_of
from app.consent.models import Consent, ConsentChannel, ConsentPurpose
from app.consent.opt_in_words import OPT_IN_VERSION
from app.consent.service import NoConsent, require_consent, revoke_consent
from app.db import as_utc, utcnow
from app.delivery.timeline_strings import SOMEONE
from app.errors import Refusal
from app.family.models import ThreadMessage, ThreadPhoto
from app.family.photos import photo_content
from app.ingestion.objects import ObjectStore
from app.keys.context import KeyContext, closing_since
from app.keys.models import Key
from app.keys.privacy import only_me_scopes
from app.keys.scopes import KeyRole, Scope
from app.safety.people import key_holder

GROUP_TARGET = WhatsAppGroup.__tablename__
log = logging.getLogger(__name__)


class NoFamilyGroup(Refusal):
    """This family has no group on WhatsApp yet."""


class NotTheirsToOpen(Refusal):
    """The family's group is opened by the patient, or by the chief he named."""


@dataclass(frozen=True, slots=True)
class Member:
    """One person in the family's group: who, by name, and whether it is the patient."""

    person_id: uuid.UUID
    name: str
    phone_e164: str
    is_patient: bool


def is_member(context: KeyContext) -> bool:
    """Whether this key's holder is in the family's group: the patient, or a key that reads
    the family thread. The context is resolved from a live key, so a closed one never is."""
    return context.is_owner or Scope.FAMILY in context.scopes


@audited(Action.READ, Scope.FAMILY, GROUP_TARGET)
async def group_of(session: AsyncSession, *, context: KeyContext) -> WhatsAppGroup | None:
    """This family's group, or None before one is opened."""
    found = await audited_read(session, WhatsAppGroup, context, Scope.FAMILY)
    return found[0] if found else None


@audited(Action.READ, Scope.FAMILY, GROUP_TARGET)
async def members_of(session: AsyncSession, *, context: KeyContext) -> list[Member]:
    """Who is in the family's group, worked out from the keys now: the patient while his
    agreement to WhatsApp is in force, then every live key that opens the family's part — its
    scopes less any part he keeps "only me", exactly as the key resolver narrows it
    (`app.keys.context`) — whose holder said yes to the group, in the order the keys were
    cut, each with a number. Nobody else: not a helper, a viewer, a caregiver whose key does
    not read the family, anyone who has not said yes or has since said no, nor anyone at all
    while he keeps the family "only me". Each account is read through the door for a key's
    holder, with a READ line (`app.safety.people`)."""
    profile = await audited_profile_read(session, context)
    keys = await audited_read(session, Key, context, Scope.FAMILY)
    kept_to_himself = await only_me_scopes(session, profile_id=profile.id)
    joined = await said_yes_to_the_group(session, context=context)
    moment = utcnow()
    people: list[tuple[uuid.UUID, Scope]] = []
    if profile.owner_person_id is not None and await _agreed(session, context):
        people.append((profile.owner_person_id, Scope.PROFILE))
    for key in sorted(keys, key=lambda one: as_utc(one.granted_at)):
        if (
            key.is_active(moment)
            and Scope.FAMILY in key.scopes_held - kept_to_himself
            and key.id in joined
        ):
            people.append((key.holder_person_id, Scope.FAMILY))
    members: list[Member] = []
    seen: set[uuid.UUID] = set()
    for person_id, door in people:
        if person_id in seen:
            continue
        seen.add(person_id)
        person = await key_holder(session, context, person_id, scope=door)
        if person is None or not person.phone_e164:
            continue
        members.append(
            Member(
                person_id=person.id,
                name=person.display_name or "",
                phone_e164=person.phone_e164,
                is_patient=person.id == profile.owner_person_id,
            )
        )
    return members


async def said_yes_to_the_group(session: AsyncSession, *, context: KeyContext) -> set[uuid.UUID]:
    """Every key whose holder's newest answer on that key, to today's words, is yes to the
    family's group. A yes given on an earlier key — one closed, then cut again — or to words
    since replaced does not count: they are asked again. Two answers at the same instant:
    the no stands, so nobody's number is shown on a tie."""
    answers = await audited_read(
        session,
        WhatsAppOptIn,
        context,
        Scope.FAMILY,
        where=(
            WhatsAppOptIn.wording_version == OPT_IN_VERSION,
            WhatsAppOptIn.key_id.is_not(None),
        ),
    )
    newest: dict[uuid.UUID, tuple[datetime, bool]] = {}
    for row in answers:
        assert row.key_id is not None
        at = as_utc(row.said_at)
        held = newest.get(row.key_id)
        if held is None or at > held[0] or (at == held[0] and not row.joins_group):
            newest[row.key_id] = (at, row.joins_group)
    return {key_id for key_id, (_, yes) in newest.items() if yes}


async def _agreed(session: AsyncSession, context: KeyContext) -> bool:
    """Whether the patient's agreement to WhatsApp is in force; a refusal is written down."""
    try:
        await require_consent(
            session,
            context=context,
            purpose=ConsentPurpose.WHATSAPP,
            scope=Scope.PROFILE,
            channel=Channel.WHATSAPP,
        )
    except NoConsent:
        return False
    return True


async def sync_group(
    session: AsyncSession, *, context: KeyContext, provider: WhatsAppProvider
) -> list[Member]:
    """Set the group's members from the keys, now. Nothing when the family has no group, or
    this key does not read the family's part (it cannot know who is in it). The patient is
    out of it while his agreement to WhatsApp is not in force, and a member who has not said
    yes to it is never in it (`members_of`). A closing account (#143) empties it."""
    if not context.allows(Scope.FAMILY):
        return []
    group = await group_of(session, context=context)
    if group is None:
        return []
    closing = await closing_since(session, profile_id=context.profile_id) is not None
    members = [] if closing else await members_of(session, context=context)
    numbers = sorted({m.phone_e164 for m in members})
    digest = hashlib.sha256("\n".join(numbers).encode()).hexdigest()
    if digest == group.members_digest:
        return members  # the provider already has exactly these: nothing to tell, or to write
    try:
        await provider.set_group_members(group.provider_group_id, numbers)
    except Exception:
        # A provider that fails never undoes what asked for the change — a withdrawal, a key
        # closed, a closing all stand. The digest is left as it was, so the next run of the
        # engine tells the provider again (`app.delivery.triggers.engine._family_group`).
        log.exception("whatsapp: the family group could not be set; the next run tries again")
        return members
    group.members_digest = digest
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.SHARE,
        scope=Scope.FAMILY,
        target=GROUP_TARGET,
        channel=Channel.WHATSAPP,
        target_id=group.id,
        rows=len(members),
        shared_with_label="whatsapp_group_members",
    )
    return members


@audited(Action.WRITE, Scope.FAMILY, GROUP_TARGET)
async def open_group(
    session: AsyncSession, *, context: KeyContext, provider: WhatsAppProvider
) -> tuple[WhatsAppGroup, list[Member]]:
    """Open the family's group on the business number, once, and put the people who read
    the family thread in it. The patient's or his chief's to open, on the patient's
    agreement to WhatsApp; opened twice, it is the same group, its members set again."""
    if not (context.is_owner or context.is_steward or context.role is KeyRole.CHIEF):
        raise NotTheirsToOpen(f"a {context.role} key does not open the family's group")
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.WHATSAPP,
        scope=Scope.PROFILE,
        channel=Channel.WHATSAPP,
    )
    group = await group_of(session, context=context)
    if group is None:
        profile = await audited_profile_read(session, context)
        name = GROUP_NAME[language_of(profile.language)].format(name=profile.display_name)
        group = await audited_write(
            session,
            WhatsAppGroup,
            context,
            Scope.FAMILY,
            channel=Channel.WHATSAPP,
            provider_group_id=await provider.open_group(name),
            opened_by_person_id=context.person_id,
            opened_at=utcnow(),
        )
    return group, await sync_group(session, context=context, provider=provider)


async def mirror_to_group(
    session: AsyncSession,
    *,
    context: KeyContext,
    provider: WhatsAppProvider,
    message: ThreadMessage,
) -> str | None:
    """A message written in the app's family thread, said in the family's group too, in its
    poster's name — after the members are set from the keys, so nobody who no longer reads
    the thread is sent it. Nothing for a card (it is rendered from State, never sent as
    words), nor when there is no group or his account is closing (#143). Whose agreement a
    message needs is the members' own: `sync_group` sets them first. The trail says it was
    shared with the group, and with how many; never the words."""
    if message.text is None or not context.allows(Scope.FAMILY):
        return None
    group = await group_of(session, context=context)
    if group is None or await closing_since(session, profile_id=context.profile_id) is not None:
        return None
    members = await sync_group(session, context=context, provider=provider)
    poster = next((m for m in members if m.person_id == message.author_person_id), None)
    if poster is None:
        return None
    profile = await audited_profile_read(session, context)
    # A poster who has not given a name yet is Someone, as the family's timeline says (#158).
    who = poster.name or SOMEONE[language_of(profile.language)]
    said = reply("family_said", profile.language, who=who) + "\n" + message.text
    sent = await provider.send_group_text(group.provider_group_id, said)
    await record(
        session,
        context=context,
        action=Action.SHARE,
        scope=Scope.FAMILY,
        target=ThreadMessage.__tablename__,
        channel=Channel.WHATSAPP,
        target_id=message.id,
        rows=len(members),
        shared_with_label="whatsapp_group",
    )
    return sent


async def mirror_photo_to_group(
    session: AsyncSession,
    *,
    context: KeyContext,
    provider: WhatsAppProvider,
    store: ObjectStore,
    message: ThreadMessage,
    photo: ThreadPhoto,
) -> str | None:
    """A photo shared in the app's family thread, said in the family's group too (#149), the
    same way `mirror_to_group` says a text message: after the members are set from the keys,
    in the sharer's name, with the caption it came with. Nothing when there is no group, his
    account is closing, or the sharer no longer reads the thread — the same rules
    `mirror_to_group` holds to. The photo is read through the family door
    (`app.family.photos.photo_content`), which is what keeps it the family's, never one of
    his papers, whatever the group later does with it."""
    if not context.allows(Scope.FAMILY):
        return None
    group = await group_of(session, context=context)
    if group is None or await closing_since(session, profile_id=context.profile_id) is not None:
        return None
    members = await sync_group(session, context=context, provider=provider)
    poster = next((m for m in members if m.person_id == message.author_person_id), None)
    if poster is None:
        return None
    profile = await audited_profile_read(session, context)
    who = poster.name or SOMEONE[language_of(profile.language)]
    caption = reply("family_said", profile.language, who=who)
    if message.text:
        caption += "\n" + message.text
    data, content_type = await photo_content(
        session, context=context, store=store, photo_id=photo.id
    )
    sent = await provider.send_group_image(
        group.provider_group_id, data, content_type, caption=caption
    )
    await record(
        session,
        context=context,
        action=Action.SHARE,
        scope=Scope.FAMILY,
        target=ThreadPhoto.__tablename__,
        channel=Channel.WHATSAPP,
        target_id=photo.id,
        rows=len(members),
        shared_with_label="whatsapp_group",
    )
    return sent


async def withdraw(
    session: AsyncSession,
    *,
    context: KeyContext,
    provider: WhatsAppProvider,
    purpose: ConsentPurpose,
    captured_via: ConsentChannel,
    holder_person_id: uuid.UUID | None = None,
) -> Sequence[Consent]:
    """Withdraw an agreement and set the family's group again, in the same step (#143): the
    person it was about is out of the group now, not at its next use — his WhatsApp
    agreement takes him out; a sharing agreement closes the keys it rested on, and so the
    holder. Every route that withdraws an agreement goes through here (held by a test)."""
    withdrawn = await revoke_consent(
        session,
        context=context,
        purpose=purpose,
        captured_via=captured_via,
        holder_person_id=holder_person_id,
    )
    await sync_group(session, context=context, provider=provider)
    return withdrawn


__all__ = [
    "Member",
    "NoFamilyGroup",
    "NotTheirsToOpen",
    "group_of",
    "is_member",
    "members_of",
    "mirror_photo_to_group",
    "mirror_to_group",
    "open_group",
    "said_yes_to_the_group",
    "sync_group",
    "withdraw",
]
