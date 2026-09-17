"""Delivery over HTTP (E00-05, E11-05, E11-06, E11-10).

    GET  /profiles/{id}/delivery-settings             the profile's default (any key)
    PUT  /profiles/{id}/delivery-settings             change it (owner, chief)
    GET  /profiles/{id}/delivery-settings/mine        the caller's own, over the default (any key)
    PUT  /profiles/{id}/delivery-settings/mine        change the caller's own (any key, #144)
    GET  /profiles/{id}/deliveries?day=               every attempt and its rule (owner, chief)
    GET  /profiles/{id}/ladders?language=             the open flag ladders that reached the caller
    GET  /profiles/{id}/reach?language=               who Nura cannot message on WhatsApp (owner, chief)
    POST /profiles/{id}/ladders/{ladder}/acknowledge  "I have it": a flag's ladder stops
    POST /profiles/{id}/push-subscriptions            this phone gets reminders (Web Push)
    DELETE /profiles/{id}/push-subscriptions          this phone stops getting them
    POST /dev/run-triggers                            `run_due` for one profile at one moment

`/dev/run-triggers` exists only on a declared dev run (NURA_DEV_CODE_SENDER=1), like the other
dev doors: it runs the engine now, and on a dev run with a frozen clock (NURA_FROZEN_CLOCK,
`POST /dev/clock`) "now" is whatever hour the checkpoint stepped it to. A deployment's
scheduler calls `run_due` itself, every five minutes (`app.delivery.triggers.engine`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.audit.access import audited_profile_read, person_display_name
from app.channels.api.deps import (
    ClosingContext,
    Context,
    Db,
    SignedIn,
    current_login,
    providers_of,
    settings_of,
)
from app.db import as_utc
from app.delivery.ladder_words import answered_lines, asked_lines
from app.delivery.ladder_words import language_of as ladder_language
from app.delivery.reach import who_nura_reaches
from app.delivery.reach_words import not_reached_line
from app.delivery.subscriptions import subscribe, unsubscribe
from app.delivery.triggers.deliver import Sent, Via
from app.delivery.triggers.engine import run_due
from app.delivery.triggers.ladder import acknowledge_flag, not_reached, open_flags_for
from app.delivery.triggers.models import Delivery, DeliverySettings, Ladder, TriggerType
from app.delivery.triggers.preferences import change, current, log
from app.delivery.triggers.rules import Config
from app.delivery.when_words import say_clock
from app.identity.closing import answerable_while_closing
from app.keys.scopes import KeyRole
from app.medicines.strings import say_date
from app.regions import REGION_TZ
from app.settings import Settings

router = APIRouter(tags=["delivery"])


def via_of(request: Request) -> Via:
    """The channels this process sends through, for a route that starts a delivery."""
    return Via.of(settings_of(request), providers_of(request))


class SettingsIn(BaseModel):
    skip_quiet_days: bool = False
    quiet_from: time | None = None
    quiet_until: time | None = None
    channels: dict[str, list[str]] = Field(default_factory=dict)
    """Per trigger type, the channels in the order to try: app_push, whatsapp, caregiver."""
    caps: dict[str, int] = Field(default_factory=dict)
    """Per trigger type, how many a person may have in a day. Never for an alert."""


class SettingsOut(BaseModel):
    breakfast_at: time
    """The one breakfast time (his settings, else his routine, else 07:30): the morning card,
    the first week's prompt and the breakfast tablet all come at it."""
    anchors: dict[str, time]
    """The routine's anchors the tablets hang on, breakfast the one above."""
    skip_quiet_days: bool
    quiet_from: time
    quiet_until: time
    channels: dict[str, list[str]]
    caps: dict[str, int | None]
    set_by_person_id: uuid.UUID | None
    set_at: datetime | None
    is_own: bool
    """False on the profile's default; true only when the row read (or changed) is this
    caller's own, never someone else's (#144) — the profile's default is `is_own=False`
    with `for_person_id=None`, since it belongs to nobody in particular."""

    @classmethod
    def of(cls, config: Config, row: DeliverySettings | None) -> SettingsOut:
        return cls(
            breakfast_at=config.day.anchors["breakfast"],
            anchors=dict(config.day.anchors),
            skip_quiet_days=config.skip_quiet_days,
            quiet_from=config.quiet_from,
            quiet_until=config.quiet_until,
            channels={
                kind.value: [one.value for one in config.channels_for(kind)] for kind in TriggerType
            },
            caps={kind.value: config.cap_for(kind) for kind in TriggerType},
            set_by_person_id=None if row is None else row.set_by_person_id,
            set_at=None if row is None else row.set_at,
            is_own=row is not None and row.for_person_id is not None,
        )


class DeliveryOut(BaseModel):
    delivery_id: uuid.UUID
    trigger_kind: str
    trigger_type: str
    category: str
    rule: str
    dedupe_key: str
    why: dict[str, Any]
    to_person_id: uuid.UUID | None
    for_person_id: uuid.UUID | None
    standing: str | None
    rung: int | None
    ladder_id: uuid.UUID | None
    channel: str | None
    template_name: str | None
    outcome: str
    reason: str | None
    passed_over: list[str]
    message_id: uuid.UUID | None
    day: str
    due_at: datetime
    recorded_at: datetime

    @classmethod
    def fields_of(cls, row: Delivery) -> dict[str, Any]:
        return {
            "delivery_id": row.id,
            "trigger_kind": row.trigger_kind.value,
            "trigger_type": row.trigger_type.value,
            "category": row.category.value,
            "rule": row.rule,
            "dedupe_key": row.dedupe_key,
            "why": dict(row.why),
            "to_person_id": row.to_person_id,
            "for_person_id": row.for_person_id,
            "standing": row.standing,
            "rung": row.rung,
            "ladder_id": row.ladder_id,
            "channel": None if row.via is None else row.via.value,
            "template_name": row.template_name,
            "outcome": row.outcome.value,
            "reason": row.reason,
            "passed_over": list(row.passed_over),
            "message_id": row.message_id,
            "day": row.day,
            "due_at": row.due_at,
            "recorded_at": row.recorded_at,
        }

    @classmethod
    def of(cls, row: Delivery) -> DeliveryOut:
        return cls(**cls.fields_of(row))


class RunLineOut(DeliveryOut):
    """A row the run wrote, with who it went to and the words, for the checkpoint to print."""

    to_name: str | None
    text: str | None

    @classmethod
    def of_sent(cls, sent: Sent) -> RunLineOut:
        return cls(**cls.fields_of(sent.delivery), to_name=sent.to_name, text=sent.text)


class RunIn(BaseModel):
    profile_id: uuid.UUID


class RunOut(BaseModel):
    at: datetime
    day: str
    deliveries: list[RunLineOut]


class LadderOut(BaseModel):
    ladder_id: uuid.UUID
    subject: str
    closed_because: str | None
    acknowledged_by_person_id: uuid.UUID | None
    acknowledged_at: datetime | None
    lines: list[str] = Field(default_factory=list)
    """What the web says after "I'm on it", in the reader's language (E11-06)."""

    @classmethod
    def of(cls, ladder: Ladder, lines: list[str] | None = None) -> LadderOut:
        return cls(
            ladder_id=ladder.id,
            subject=ladder.subject.value,
            closed_because=ladder.closed_because,
            acknowledged_by_person_id=ladder.acknowledged_by_person_id,
            acknowledged_at=ladder.acknowledged_at,
            lines=lines or [],
        )


class OpenLadderOut(BaseModel):
    """A red flag's ladder still open that reached the caller, and what the web says beside
    its one button."""

    ladder_id: uuid.UUID
    subject: str
    started_at: datetime
    lines: list[str]
    not_reached: list[str] = Field(default_factory=list)
    """For the owner and his chief: who this flag's ladder asked whose phone nothing reached —
    they have only the notice on their family page (#162). Empty for anyone else."""


class ReachOut(BaseModel):
    person_id: uuid.UUID
    whatsapp: bool
    push: bool
    lines: list[str]


@router.get("/profiles/{profile_id}/delivery-settings")
async def settings_now(context: Context, session: Db) -> SettingsOut:
    """The settings in force, over the defaults: per type the channel list and the cap."""
    config, row = await current(session, context=context)
    return SettingsOut.of(config, row)


@router.put("/profiles/{profile_id}/delivery-settings")
async def settings_change(body: SettingsIn, context: Context, session: Db) -> SettingsOut:
    """Change them: a new row, the newest in force. An alert's cap is refused
    (`AlertsAreNeverHeld`, 400), and so is an alert's channel list (`AlertsGoEveryWay`, 400):
    a red flag goes every way each person can be reached, whatever is set (#162)."""
    changed = await change(
        session,
        context=context,
        skip_quiet_days=body.skip_quiet_days,
        quiet_from=body.quiet_from,
        quiet_until=body.quiet_until,
        channels=body.channels,
        caps=body.caps,
    )
    config, row = await current(session, context=context)
    assert row is not None and row.id == changed.id
    return SettingsOut.of(config, row)


@router.get("/profiles/{profile_id}/delivery-settings/mine")
async def settings_mine(context: Context, session: Db) -> SettingsOut:
    """The caller's own settings (#144): quiet hours and channels differ per person — Mei's
    weekdays, Kit's weekends — read over the profile's default, which is what stands until
    they set one of their own. Any key holder, the same as the plain settings route."""
    config, row = await current(session, context=context, mine=True)
    return SettingsOut.of(config, row)


@router.put("/profiles/{profile_id}/delivery-settings/mine")
async def settings_change_mine(body: SettingsIn, context: Context, session: Db) -> SettingsOut:
    """Change the caller's own settings (#144): self-service, the same footing as leaving a
    key — no family scope is asked, because nobody else's word is needed for a person's own
    quiet hours. An alert's cap and channel list are refused here exactly as they are on the
    profile's own settings (#162)."""
    changed = await change(
        session,
        context=context,
        skip_quiet_days=body.skip_quiet_days,
        quiet_from=body.quiet_from,
        quiet_until=body.quiet_until,
        channels=body.channels,
        caps=body.caps,
        mine=True,
    )
    config, row = await current(session, context=context, mine=True)
    assert row is not None and row.id == changed.id
    return SettingsOut.of(config, row)


@router.get("/profiles/{profile_id}/deliveries")
async def deliveries(
    context: Context,
    session: Db,
    day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> list[DeliveryOut]:
    """Every attempt to reach someone about him, newest first, with the rule that fired."""
    return [DeliveryOut.of(row) for row in await log(session, context=context, day=day)]


@router.get("/profiles/{profile_id}/ladders")
async def open_ladders(
    context: Context,
    session: Db,
    language: str | None = Query(default=None, min_length=2, max_length=16),
) -> list[OpenLadderOut]:
    """The red flags still climbing that reached the caller, newest first, each with the
    lines the web shows beside "I'm on it". Under the emergency scope; nothing of the flag's
    own words — those went in the notice."""
    found = await open_flags_for(session, context=context)
    if not found:
        return []
    profile = await audited_profile_read(session, context)
    words = ladder_language(language or profile.language)
    zone = REGION_TZ[context.region]
    runs_it = context.is_owner or context.is_steward or context.role is KeyRole.CHIEF
    shown: list[OpenLadderOut] = []
    for ladder in found:
        local = as_utc(ladder.started_at).astimezone(zone)
        missed = (
            [
                not_reached_line(await person_display_name(session, context, person), words)
                for person in await not_reached(session, context=context, ladder=ladder)
                if person != context.person_id
            ]
            if runs_it
            else []
        )
        shown.append(
            OpenLadderOut(
                ladder_id=ladder.id,
                subject=ladder.subject.value,
                started_at=as_utc(ladder.started_at),
                lines=asked_lines(
                    name=profile.display_name,
                    day=say_date(local.date(), words),
                    time=say_clock(local.time(), words),
                    language=words,
                ),
                not_reached=missed,
            )
        )
    return shown


@router.get("/profiles/{profile_id}/reach")
async def reach(
    request: Request,
    context: Context,
    session: Db,
    language: str | None = Query(default=None, min_length=2, max_length=16),
) -> list[ReachOut]:
    """Each person holding a live key, and whether Nura can message them on WhatsApp and push
    to them, with a line for each it cannot message on WhatsApp (#163). Owner and chief."""
    profile = await audited_profile_read(session, context)
    found = await who_nura_reaches(
        session,
        context=context,
        push=providers_of(request).push,
        language=language or profile.language,
    )
    return [
        ReachOut(person_id=one.person_id, whatsapp=one.whatsapp, push=one.push, lines=one.lines)
        for one in found
    ]


@router.post("/profiles/{profile_id}/ladders/{ladder_id}/acknowledge")
async def acknowledge(
    ladder_id: uuid.UUID,
    context: ClosingContext,
    session: Db,
    language: str | None = Query(default=None, min_length=2, max_length=16),
) -> LadderOut:
    """Someone the flag's ladder reached says they have it; the ladder asks nobody else. While
    the owner's closing stands, still so for a flag raised before it (#143)."""
    await answerable_while_closing(session, context=context, ladder_id=ladder_id)
    ladder = await acknowledge_flag(session, context=context, ladder_id=ladder_id)
    assert ladder is not None  # a named ladder that is not theirs is refused, not None
    return LadderOut.of(ladder, answered_lines(language))


class PushKeysIn(BaseModel):
    p256dh: str = Field(min_length=1, max_length=128)
    """The browser's P-256 key, base64url."""
    auth: str = Field(min_length=1, max_length=64)
    """The browser's auth secret, base64url."""


class PushSubscriptionIn(BaseModel):
    """What the browser's `PushSubscription.toJSON()` says: the push service's endpoint and
    the browser's two keys."""

    endpoint: str = Field(min_length=1, max_length=1024)
    keys: PushKeysIn


class PushEndpointIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1024)


class PushSubscribedOut(BaseModel):
    subscription_id: uuid.UUID


@router.post("/profiles/{profile_id}/push-subscriptions", status_code=status.HTTP_201_CREATED)
async def push_subscribe(
    body: PushSubscriptionIn,
    context: Context,
    signed_in: Annotated[SignedIn, Depends(current_login)],
    session: Db,
) -> PushSubscribedOut:
    """This phone gets reminders about this profile: the browser's subscription, kept for
    this login session, under the face of the graph every key opens. The same browser again
    replaces the one before. Not an https endpoint and the two keys: `NotAPushSubscription`."""
    row = await subscribe(
        session,
        context=context,
        login_id=signed_in.login.id,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
    )
    return PushSubscribedOut(subscription_id=row.id)


@router.delete("/profiles/{profile_id}/push-subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def push_forget(body: PushEndpointIn, context: Context, session: Db) -> Response:
    """This phone stops getting reminders about this profile: its subscription is revoked."""
    await unsubscribe(session, context=context, endpoint=body.endpoint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _dev_only(request: Request) -> Settings:
    settings = settings_of(request)
    if not settings.dev_code_sender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return settings


@router.post("/dev/run-triggers")
async def dev_run_triggers(body: RunIn, request: Request, session: Db) -> RunOut:
    """`run_due` for one profile, now, the way the scheduler calls it. Dev only: on a dev run
    started with NURA_FROZEN_CLOCK, `POST /dev/clock` moves "now" to the hour a step needs."""
    _dev_only(request)
    report = await run_due(session, via=via_of(request), profile_id=body.profile_id)
    return RunOut(
        at=report.at,
        day=report.day,
        deliveries=[RunLineOut.of_sent(sent) for sent in report.sent],
    )


__all__ = ["router", "via_of"]
