"""The family's group on WhatsApp (E11-01): the family thread (E12-02), mirrored.

Who is in the group is who reads the family thread: the patient, and every live key that
holds the family's part. It is never stored. It is worked out from the keys each time the
group is used — opened, a key cut or closed, a message mirrored out — and told to the
provider then (`set_group_members`), so a key closed is a person out of the group, and a
message from someone the keys no longer name is not taken in (`is_member`).

Both ways, the thread is the one record. A message written in the app's thread is said in
the group, in its poster's name (`mirror_to_group`); a message posted in the group lands in
the thread in its poster's name (`app.channels.whatsapp.inbound`), and is not said back. The
group rests on the patient's agreement to WhatsApp, like everything on the business number.
Nothing here reads a fact out of what the family says to each other.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read, audited_write
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.channels.whatsapp.models import WhatsAppGroup
from app.channels.whatsapp.provider import WhatsAppProvider
from app.channels.whatsapp.strings import GROUP_NAME, reply
from app.channels.whatsapp.templates import language_of
from app.consent.models import ConsentPurpose
from app.consent.service import NoConsent, require_consent
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.family.models import ThreadMessage
from app.keys.context import KeyContext
from app.keys.models import Key
from app.keys.privacy import only_me_scopes
from app.keys.scopes import KeyRole, Scope
from app.safety.people import key_holder

GROUP_TARGET = WhatsAppGroup.__tablename__


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


async def group_for(session: AsyncSession, provider_group_id: str) -> WhatsAppGroup | None:
    """The family group a provider's handle names, read before anyone's key is resolved —
    as the sender's number is (`find_person_by_phone`): the handle and its profile only."""
    found: WhatsAppGroup | None = await session.scalar(
        select(WhatsAppGroup).where(WhatsAppGroup.provider_group_id == provider_group_id)
    )
    return found


@audited(Action.READ, Scope.FAMILY, GROUP_TARGET)
async def group_of(session: AsyncSession, *, context: KeyContext) -> WhatsAppGroup | None:
    """This family's group, or None before one is opened."""
    found = await audited_read(session, WhatsAppGroup, context, Scope.FAMILY)
    return found[0] if found else None


@audited(Action.READ, Scope.FAMILY, GROUP_TARGET)
async def members_of(session: AsyncSession, *, context: KeyContext) -> list[Member]:
    """Who is in the family's group, worked out from the keys now: the patient, then every
    live key that opens the family's part — its scopes less any part he keeps "only me",
    exactly as the key resolver narrows it (`app.keys.context`) — in the order the keys were
    cut, each with a number. Nobody else: not a helper, a viewer, a caregiver whose key does
    not read the family, nor anyone at all while he keeps the family "only me". Each account
    is read through the door for a key's holder, with a READ line (`app.safety.people`)."""
    profile = await audited_profile_read(session, context)
    keys = await audited_read(session, Key, context, Scope.FAMILY)
    kept_to_himself = await only_me_scopes(session, profile_id=profile.id)
    moment = utcnow()
    people: list[tuple[uuid.UUID, Scope]] = []
    if profile.owner_person_id is not None:
        people.append((profile.owner_person_id, Scope.PROFILE))
    for key in sorted(keys, key=lambda one: as_utc(one.granted_at)):
        if key.is_active(moment) and Scope.FAMILY in key.scopes_held - kept_to_himself:
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
    this key does not read the family's part (it cannot know who is in it). While the
    patient's agreement to WhatsApp is not in force the group is emptied: no number is
    handed to the provider on his account, and nobody in it hears the family there."""
    if not context.allows(Scope.FAMILY):
        return []
    group = await group_of(session, context=context)
    if group is None:
        return []
    members = await members_of(session, context=context) if await _agreed(session, context) else []
    await provider.set_group_members(group.provider_group_id, [m.phone_e164 for m in members])
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
    words), nor when there is no group or the patient has withdrawn his agreement. The
    trail says it was shared with the group, and with how many; never the words."""
    if message.text is None or not context.allows(Scope.FAMILY):
        return None
    group = await group_of(session, context=context)
    if group is None or not await _agreed(session, context):
        return None
    members = await sync_group(session, context=context, provider=provider)
    poster = next((m for m in members if m.person_id == message.author_person_id), None)
    if poster is None:
        return None
    profile = await audited_profile_read(session, context)
    said = reply("family_said", profile.language, who=poster.name) + "\n" + message.text
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


__all__ = [
    "Member",
    "NoFamilyGroup",
    "NotTheirsToOpen",
    "group_for",
    "group_of",
    "is_member",
    "members_of",
    "mirror_to_group",
    "open_group",
    "sync_group",
]
