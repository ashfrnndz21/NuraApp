"""Signing in and out, and who am I."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.audit.access import audited_profile_read
from app.channels.api.deps import Db, SignedIn, current_login, providers_of, settings_of
from app.channels.api.schemas import (
    EmailStart,
    EmailVerify,
    MeOut,
    PhoneStart,
    PhoneVerify,
    SessionOut,
    Started,
)
from app.identity.login import (
    CODE_LIFETIME,
    logout,
    start_email_login,
    start_phone_login,
    verify_email_link,
    verify_phone_code,
)
from app.identity.service import find_own_profile
from app.keys.context import resolve_key_context

router = APIRouter(tags=["auth"])

STARTED = Started(expires_in_seconds=int(CODE_LIFETIME.total_seconds()))


@router.post("/auth/phone/start", status_code=status.HTTP_202_ACCEPTED)
async def phone_start(body: PhoneStart, request: Request, session: Db) -> Started:
    await start_phone_login(
        session,
        region=settings_of(request).region,
        sender=providers_of(request).code_sender,
        phone_e164=body.phone_e164,
        display_name=body.display_name,
        language=body.language,
    )
    return STARTED


@router.post("/auth/phone/verify")
async def phone_verify(body: PhoneVerify, request: Request, session: Db) -> SessionOut:
    login, token = await verify_phone_code(
        session, region=settings_of(request).region, phone_e164=body.phone_e164, code=body.code
    )
    return SessionOut(token=token, person_id=login.person_id, region=login.region)


@router.post("/auth/email/start", status_code=status.HTTP_202_ACCEPTED)
async def email_start(body: EmailStart, request: Request, session: Db) -> Started:
    await start_email_login(
        session,
        region=settings_of(request).region,
        sender=providers_of(request).code_sender,
        email=body.email,
        display_name=body.display_name,
        language=body.language,
    )
    return STARTED


@router.post("/auth/email/verify")
async def email_verify(body: EmailVerify, request: Request, session: Db) -> SessionOut:
    login, token = await verify_email_link(
        session, region=settings_of(request).region, email=body.email, token=body.token
    )
    return SessionOut(token=token, person_id=login.person_id, region=login.region)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(signed_in: Annotated[SignedIn, Depends(current_login)], session: Db) -> Response:
    await logout(session, login=signed_in.login)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
async def me(
    signed_in: Annotated[SignedIn, Depends(current_login)], request: Request, session: Db
) -> MeOut:
    """The caller's own account, and the id of his own profile once he has opened one.

    The profile is read the way every profile is read: through a context, written down.
    """
    found = await find_own_profile(session, signed_in.person)
    if found is None:
        return MeOut.of(signed_in.person, None)
    context = await resolve_key_context(
        session,
        region=settings_of(request).region,
        person_id=signed_in.person.id,
        profile_id=found.id,
    )
    return MeOut.of(signed_in.person, await audited_profile_read(session, context))
