"""The WhatsApp routes: the provider's webhook, the thread as the owner reads it, and the
dev-only doors that drive the channel without a provider.

    GET  /whatsapp/webhook                       the provider's verification handshake
    POST /whatsapp/webhook                       inbound messages, signature checked first
    GET  /profiles/{id}/whatsapp/thread          the thread by reference (owner, chief)
    POST /dev/whatsapp/inbound                   a fake inbound message, same path as the webhook
    POST /dev/whatsapp/morning/{id}              `run_morning`, for the checkpoint
    POST /dev/whatsapp/check-in/{id}             `run_feeling_check_in`
    GET  /dev/whatsapp/outbox                    what the fixture provider has sent

The dev routes exist only on a declared dev run (`NURA_DEV_CODE_SENDER=1`); anywhere else
they are not there at all. The webhook carries no bearer token — the provider is the caller
— so it resolves its own key contexts, one per message, inside `handle_inbound`.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.audit.models import Channel
from app.audit.trail import NotTheirsToRead
from app.channels.api.deps import Context, Db, providers_of, settings_of
from app.channels.api.schemas import PHONE, utc
from app.channels.api.uploads import Cap, read_capped
from app.channels.whatsapp.classifier import RuleClassifier
from app.channels.whatsapp.config import BusinessNumber, business_number_for
from app.channels.whatsapp.group import (
    Member,
    NoFamilyGroup,
    group_of,
    members_of,
    open_group,
)
from app.channels.whatsapp.inbound import Handled, handle_inbound
from app.channels.whatsapp.models import WhatsAppGroup, WhatsAppMessage
from app.channels.whatsapp.outbound.level0 import run_feeling_check_in, run_morning
from app.channels.whatsapp.outbound.send import Delivered, thread_messages
from app.channels.whatsapp.provider import (
    DevInbound,
    FixtureProvider,
    NotAWebhook,
    WebhookTooLarge,
)
from app.db import utcnow
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import WITHHELD_ARTIFACT, withheld_references
from app.settings import Settings

log = logging.getLogger("nura.channels.whatsapp")
router = APIRouter(tags=["whatsapp"])

CLASSIFIER = RuleClassifier()


def _number(settings: Settings) -> BusinessNumber:
    return business_number_for(settings)


class DeliveredOut(BaseModel):
    to_person_id: uuid.UUID
    kind: str
    template_name: str | None
    catalogue_key: str | None
    text: str
    message_id: uuid.UUID

    @classmethod
    def of(cls, sent: Delivered) -> DeliveredOut:
        return cls(
            to_person_id=sent.to_person_id,
            kind=sent.kind,
            template_name=sent.template_name,
            catalogue_key=sent.catalogue_key,
            text=sent.text,
            message_id=sent.message_id,
        )


class HandledOut(BaseModel):
    """What one inbound message became. `stranger_reply` is the one fixed line a number no
    profile knows gets; it is here so the checkpoint can print it, and nowhere else."""

    outcome: str
    replies: list[DeliveredOut]
    profile_id: uuid.UUID | None
    message_id: uuid.UUID | None
    artifact_id: uuid.UUID | None
    proposal_id: uuid.UUID | None
    fact_id: uuid.UUID | None
    flag_id: uuid.UUID | None
    review_card_id: uuid.UUID | None
    stranger_reply: str | None
    refused: str | None
    note_id: uuid.UUID | None = None
    thread_message_id: uuid.UUID | None = None

    @classmethod
    def of(cls, handled: Handled) -> HandledOut:
        return cls(
            outcome=handled.outcome,
            replies=[DeliveredOut.of(sent) for sent in handled.replies],
            profile_id=handled.profile_id,
            message_id=handled.message_id,
            artifact_id=handled.artifact_id,
            proposal_id=handled.proposal_id,
            fact_id=handled.fact_id,
            flag_id=handled.flag_id,
            review_card_id=handled.review_card_id,
            stranger_reply=handled.stranger_reply,
            refused=handled.refused,
            note_id=handled.note_id,
            thread_message_id=handled.thread_message_id,
        )


class ThreadMessageOut(BaseModel):
    """One kept message, by reference: never its words."""

    message_id: uuid.UUID
    thread_id: uuid.UUID
    direction: str
    kind: str
    person_id: uuid.UUID
    at: Any
    artifact_id: uuid.UUID | None
    flag_id: uuid.UUID | None
    template_name: str | None
    catalogue_key: str | None
    state_id: uuid.UUID | None
    withheld: list[str] = []
    """`artifact` when the kept message's artefact is under a scope the reader's key does not
    hold — a health message is the record's, a fall the emergency scope's — its id left out."""

    @classmethod
    def of(cls, row: WhatsAppMessage, withheld: Sequence[str] = ()) -> ThreadMessageOut:
        return cls(
            message_id=row.id,
            thread_id=row.thread_id,
            direction=row.direction.value,
            kind=row.kind.value,
            person_id=row.person_id,
            at=row.at,
            artifact_id=None if WITHHELD_ARTIFACT in withheld else row.artifact_id,
            flag_id=row.flag_id,
            template_name=row.template_name,
            catalogue_key=row.catalogue_key,
            state_id=row.state_id,
            withheld=list(withheld),
        )


# --- the webhook ------------------------------------------------------------------------------


@router.get("/whatsapp/webhook")
async def verify(
    request: Request,
    mode: str | None = Query(default=None, alias="hub.mode"),
    token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Response:
    """The provider's handshake: echo the challenge when the verify token is ours."""
    provider = providers_of(request).whatsapp
    if mode != "subscribe" or not provider.verify_token_matches(token) or challenge is None:
        raise NotAWebhook("the verify token is not ours")
    return Response(content=challenge, media_type="text/plain")


WEBHOOK_BYTES = 1024 * 1024
"""The most one webhook delivery may carry: a megabyte. A delivery is text and handles — a
photo, a PDF or a voice note comes as the provider's id and is fetched by it, against its
own cap — so a megabyte holds a long batch; a body past it is not a delivery (#136)."""


@router.post("/whatsapp/webhook")
async def webhook(request: Request, session: Db) -> dict[str, int]:
    """Inbound messages. The body is read against its cap as it arrives (`read_capped`):
    one declared longer is refused before a byte is read, and one that runs longer is refused
    at the first chunk past the cap, both with a 413, before anything is parsed (#136). The
    signature is then checked over exactly the bytes read, and only a signed body is read as
    JSON; each message walks `handle_inbound`, where a red flag is looked for before the ignore
    and the consent checks. The provider gets a 200 and a count; what each message became is
    on the profile's trail, not on the wire."""
    body = await read_capped(
        request.stream(),
        Cap(WEBHOOK_BYTES, WebhookTooLarge),
        declared=request.headers.get("content-length"),
    )
    providers = providers_of(request)
    if not providers.whatsapp.verify_webhook(request.headers.get("X-Hub-Signature-256"), body):
        raise NotAWebhook("the webhook body was not signed by the provider")
    try:
        payload = json.loads(body)
    except ValueError as not_json:
        raise NotAWebhook("the webhook body is not JSON") from not_json
    if not isinstance(payload, dict):
        raise NotAWebhook("the webhook body is not a delivery")
    settings = settings_of(request)
    handled = 0
    for message in providers.whatsapp.parse_inbound(payload):
        # Each message on its own: one that fails never holds back the rest of the delivery,
        # a red flag among them least of all.
        try:
            await handle_inbound(
                session,
                settings=settings,
                providers=providers,
                number=_number(settings),
                classifier=CLASSIFIER,
                message=message,
            )
        except Exception as failed:  # noqa: BLE001 — logged by name; the rest of the batch goes on
            log.warning("whatsapp: one inbound message not handled: %s", type(failed).__name__)
            await session.rollback()
            continue
        handled += 1
    return {"handled": handled}


# --- the thread -------------------------------------------------------------------------------


def _may_read_the_thread(context: KeyContext) -> None:
    """The patient, and the chief he named — the same people who read the trail."""
    if context.is_owner or context.is_steward:
        return
    if context.role is not KeyRole.CHIEF:
        raise NotTheirsToRead(f"a {context.role} key does not open the thread")
    context.require(Scope.FAMILY)


@router.get("/profiles/{profile_id}/whatsapp/thread")
async def thread(context: Context, session: Db) -> list[ThreadMessageOut]:
    """Every kept message on this profile's WhatsApp threads, oldest first, by reference:
    who, when, what kind, and the artefact, template or key it names. Never the words."""
    _may_read_the_thread(context)
    rows = await thread_messages(session, context=context)
    withheld = await withheld_references(
        session,
        context=context,
        cited=[(row.id, Scope.FAMILY, row.artifact_id, None) for row in rows],
    )
    return [ThreadMessageOut.of(row, withheld.get(row.id, ())) for row in rows]


# --- the family's group (E11-01) ---------------------------------------------------------------


class GroupMemberOut(BaseModel):
    """One person in the family's group, by name. Never a number: who is in it is worked out
    from the keys, and the numbers stay with the provider."""

    person_id: uuid.UUID
    name: str
    is_patient: bool


class GroupOut(BaseModel):
    group_id: uuid.UUID
    opened_at: datetime
    members: list[GroupMemberOut]

    @classmethod
    def of(cls, group: WhatsAppGroup, members: list[Member]) -> GroupOut:
        return cls(
            group_id=group.id,
            opened_at=utc(group.opened_at),
            members=[
                GroupMemberOut(person_id=m.person_id, name=m.name, is_patient=m.is_patient)
                for m in members
            ],
        )


@router.post("/profiles/{profile_id}/whatsapp/group", status_code=status.HTTP_201_CREATED)
async def open_family_group(request: Request, context: Context, session: Db) -> GroupOut:
    """Open the family's group on WhatsApp, once — the family thread, mirrored — with the
    people who read the thread in it: the patient and every key holding the family's part.
    The patient's or his chief's to open, on his agreement to WhatsApp."""
    group, members = await open_group(
        session, context=context, provider=providers_of(request).whatsapp
    )
    return GroupOut.of(group, members)


@router.get("/profiles/{profile_id}/whatsapp/group")
async def family_group(context: Context, session: Db) -> GroupOut:
    """The family's group and who is in it now, as the keys say. Under the family scope."""
    group = await group_of(session, context=context)
    if group is None:
        raise NoFamilyGroup("this family has no group on WhatsApp yet")
    return GroupOut.of(group, await members_of(session, context=context))


# --- dev only ---------------------------------------------------------------------------------


def _dev_only(request: Request) -> Settings:
    settings = settings_of(request)
    if not settings.dev_code_sender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return settings


class DevInboundIn(BaseModel):
    from_e164: str = Field(pattern=PHONE)
    text: str | None = Field(default=None, max_length=4000)
    media_id: str | None = Field(default=None, max_length=80)
    content_type: str | None = Field(default=None, max_length=128)
    group_id: str | None = Field(default=None, max_length=80)


@router.post("/dev/whatsapp/inbound")
async def dev_inbound(body: DevInboundIn, request: Request, session: Db) -> HandledOut:
    """A message as if it had come through the webhook, without a provider. Dev runs only."""
    settings = _dev_only(request)
    providers = providers_of(request)
    message = DevInbound(
        from_e164=body.from_e164,
        text=body.text,
        media_id=body.media_id,
        content_type=body.content_type,
        group_id=body.group_id,
    ).as_message(utcnow())
    handled = await handle_inbound(
        session,
        settings=settings,
        providers=providers,
        number=_number(settings),
        classifier=CLASSIFIER,
        message=message,
    )
    return HandledOut.of(handled)


@router.post("/dev/whatsapp/morning/{profile_id}")
async def dev_morning(profile_id: uuid.UUID, request: Request, session: Db) -> DeliveredOut:
    """`run_morning` for one profile, the way the scheduler (E11) will call it."""
    settings = _dev_only(request)
    sent = await run_morning(
        session,
        settings=settings,
        providers=providers_of(request),
        number=_number(settings),
        profile_id=profile_id,
    )
    return DeliveredOut.of(sent)


@router.post("/dev/whatsapp/check-in/{profile_id}")
async def dev_check_in(profile_id: uuid.UUID, request: Request, session: Db) -> DeliveredOut:
    settings = _dev_only(request)
    sent = await run_feeling_check_in(
        session,
        settings=settings,
        providers=providers_of(request),
        number=_number(settings),
        profile_id=profile_id,
    )
    return DeliveredOut.of(sent)


@router.get("/dev/whatsapp/outbox")
async def dev_outbox(request: Request) -> list[dict[str, Any]]:
    """What the fixture provider has sent since the process started. Dev runs only."""
    _dev_only(request)
    provider = providers_of(request).whatsapp
    if not isinstance(provider, FixtureProvider):
        return []
    return [
        {
            "to_e164": sent.to_e164,
            "kind": sent.kind,
            "template_name": sent.template_name,
            "language": sent.language,
            "text": sent.text,
        }
        for sent in provider.sent
    ]


__all__ = ["Channel", "router"]
