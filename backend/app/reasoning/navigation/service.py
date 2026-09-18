"""Care navigation's own service (T3): the needs list, and `draft_message` — the one call
that turns a real need into a drafted message, never sent.

`draft_message(session, context, need, provider)` resolves who is writing (his own voice, or
a chief's own name — `app.family.common`'s `is_chief`/owner distinction, the same the
providers directory already uses), calls the deployment's drafter (the rule-based one unless
a caller names another, `drafter_provider.py`), builds the provider's own contact link
(`sms:`/`https://wa.me/`, built from `Provider.phone_e164` alone — never a number typed for
the occasion) and writes one line to the trail. It never persists the drafted text: the need
it was drafted for is read fresh next time, from the record, the same as any other view.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read, audited_read
from app.audit.models import Action
from app.audit.trail import record
from app.errors import Refusal
from app.identity.models import Person
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import Provider
from app.reasoning.navigation.models import ContactLink, Draft, Drafter, Need
from app.reasoning.navigation.needs import list_needs, need_by_id
from app.reasoning.navigation.rule_drafter import RuleDrafter

NAVIGATION_TARGET = "navigation_draft"

_EVIDENCE_SCOPE: dict[str, Scope] = {
    "fact": Scope.RECORDS,
    "medication_line": Scope.MEDICINES,
    "appointment": Scope.VISITS,
    "provider": Scope.VISITS,
}


class NoSuchNeed(Refusal):
    """No real need on the record answers to this id, under this key — it may have closed
    (the letter's date has passed, the line was superseded) or never existed."""


async def needs_for(session: AsyncSession, *, context: KeyContext) -> list[Need]:
    """Every real need on the record right now — one row per `Need`, no drafted text yet:
    the sheet asks for that only once a person opens "Draft a message"."""
    return list(await list_needs(session, context=context))


async def need_for_id(
    session: AsyncSession, *, context: KeyContext, need_id: str
) -> Need:
    found = await need_by_id(session, context=context, need_id=need_id)
    if found is None:
        raise NoSuchNeed(f"no navigation need {need_id!r} on profile {context.profile_id}")
    return found


async def provider_for_need(
    session: AsyncSession, *, context: KeyContext, need: Need
) -> Provider | None:
    """The provider `need` already names, if any — read fresh, under the scope every
    provider directory read uses, never carried on the `Need` itself."""
    if need.provider_id is None:
        return None
    found = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.id == need.provider_id,)
    )
    return found[0] if found else None


def _links_for(provider: Provider | None) -> tuple[ContactLink, ...]:
    """`sms:`/`https://wa.me/` built from the provider's own phone, and nothing else: no
    email column exists on `Provider` today, so a provider with no phone on file gets no
    link at all — the sheet falls back to "Copy" (the story's own words: "if none, the
    message is copyable")."""
    if provider is None or not provider.phone_e164:
        return ()
    digits = provider.phone_e164.lstrip("+")
    return (
        ContactLink(kind="sms", href=f"sms:{provider.phone_e164}"),
        ContactLink(kind="whatsapp", href=f"https://wa.me/{digits}"),
    )


async def draft_message(
    session: AsyncSession,
    context: KeyContext,
    need: Need,
    provider: Provider | None,
    *,
    drafter: Drafter | None = None,
    language: str | None = None,
) -> Draft:
    """Draft a short plain-words message for `need`. Never sends it; never writes the medicine
    or the diagnosis behind it — only the need, the ask, and the contact he chooses to share
    (see `app.reasoning.navigation` module doc). Every call is one line on the trail, naming
    who drafted it, under the scope the need's own evidence sits under."""
    profile = await audited_profile_read(session, context)
    is_self = context.is_owner
    drafter_name: str | None = None
    if not is_self:
        person = await session.get(Person, context.person_id)
        drafter_name = person.display_name if person is not None else None
    chosen = drafter or RuleDrafter()
    text = await chosen.draft(
        need=need,
        language=language or profile.language,
        patient_name=profile.display_name,
        drafter_name=drafter_name,
        is_self=is_self,
    )
    links = _links_for(provider)
    draft = Draft(
        need_id=need.id,
        kind=need.kind,
        language=language or profile.language,
        text=text,
        drafted_by="self" if is_self else "caregiver",
        links=links,
        copy_only=not links,
        cites=(f"{need.evidence_kind}:{need.evidence_id}",),
    )
    scope = _EVIDENCE_SCOPE.get(need.evidence_kind, Scope.RECORDS)
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=scope,
        target=NAVIGATION_TARGET,
        target_id=need.evidence_id,
        rows=1,
    )
    return draft
