"""Signing in: a code to the phone or a link to the email, and the session it earns.

No passwords, ever. A person proves he holds the number or the address by sending back the
secret that was sent to it. The secret is six digits by phone, a random token by email; it
lives ten minutes, works once, and is spent after five wrong tries. What the proof earns is a
session: a random token, handed over once, good for thirty days on that device.

Registration and sign-in are the same door. The account is made on the verify that succeeds,
never on the ask, so nobody can put a name on a number he has not proved he holds.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from sqlalchemy import Delete, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import as_utc, keep_on_refusal, utcnow
from app.errors import Refusal
from app.identity.models import LoginChallenge, LoginChannel, LoginSession, Person
from app.identity.providers import CodeSender
from app.identity.service import find_person_by_phone, register_person
from app.regions import OutOfRegion, Region, guard_region

CODE_LIFETIME = timedelta(minutes=10)
MAX_ATTEMPTS = 5
SESSION_LIFETIME = timedelta(days=30)


class NoOpenChallenge(Refusal):
    """Nothing to verify: no code was asked for, or the one asked for was already used.

    A number that never asked and a number whose code was spent are refused in the same
    words, so that nothing about who has asked can be learned by guessing.
    """


class WrongCode(Refusal):
    """That is not the code that was sent."""


class ChallengeExpired(Refusal):
    """The code is older than ten minutes. Ask for a new one."""


class ChallengeLocked(Refusal):
    """Five wrong tries spend the code. Ask for a new one."""


class NoSession(Refusal):
    """No token, a token nobody issued, or one that has expired or been logged out."""


def _hash_secret(challenge_id: uuid.UUID, secret: str) -> str:
    """The hash of a secret, keyed by the challenge it belongs to. Never the secret."""
    return hashlib.sha256(f"{challenge_id}:{secret}".encode()).hexdigest()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _six_digits() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def _open_challenges(
    session: AsyncSession, *, channel: LoginChannel, address: str
) -> list[LoginChallenge]:
    column = LoginChallenge.phone_e164 if channel is LoginChannel.PHONE else LoginChallenge.email
    found = await session.scalars(
        select(LoginChallenge)
        .where(
            LoginChallenge.channel == channel,
            column == address,
            LoginChallenge.consumed_at.is_(None),
        )
        .order_by(LoginChallenge.issued_at.desc())
    )
    return list(found)


async def _start(
    session: AsyncSession,
    *,
    region: Region,
    channel: LoginChannel,
    address: str,
    secret: str,
    display_name: str | None,
    language: str | None,
) -> LoginChallenge:
    moment = utcnow()
    # One live challenge per address: asking again closes the one before.
    for earlier in await _open_challenges(session, channel=channel, address=address):
        earlier.consumed_at = moment
    challenge_id = uuid.uuid4()
    challenge = LoginChallenge(
        id=challenge_id,
        region=region,
        channel=channel,
        phone_e164=address if channel is LoginChannel.PHONE else None,
        email=address if channel is LoginChannel.EMAIL else None,
        code_hash=_hash_secret(challenge_id, secret),
        display_name=display_name,
        language=language,
        issued_at=moment,
        expires_at=moment + CODE_LIFETIME,
    )
    session.add(challenge)
    await session.flush()
    return challenge


async def start_phone_login(
    session: AsyncSession,
    *,
    region: Region,
    sender: CodeSender,
    phone_e164: str,
    display_name: str | None = None,
    language: str | None = None,
) -> LoginChallenge:
    """Send a six-digit code to the phone. The code is given to the sender and to nobody else."""
    code = _six_digits()
    challenge = await _start(
        session,
        region=region,
        channel=LoginChannel.PHONE,
        address=phone_e164,
        secret=code,
        display_name=display_name,
        language=language,
    )
    await sender.send_phone_code(phone_e164, code)
    return challenge


async def start_email_login(
    session: AsyncSession,
    *,
    region: Region,
    sender: CodeSender,
    email: str,
    display_name: str | None = None,
    language: str | None = None,
) -> LoginChallenge:
    """Send a link with a one-time token to the email address."""
    token = secrets.token_urlsafe(32)
    challenge = await _start(
        session,
        region=region,
        channel=LoginChannel.EMAIL,
        address=email,
        secret=token,
        display_name=display_name,
        language=language,
    )
    await sender.send_email_link(email, token)
    return challenge


async def _person_for(
    session: AsyncSession, *, region: Region, challenge: LoginChallenge
) -> Person:
    """The account this address is, made now if it was not one yet.

    An existing account is returned as it is: a name given at registration fills an empty
    one and never overwrites a chosen one. A person pinned to another region is refused by
    this one, whichever database his row is sitting in.
    """
    if challenge.channel is LoginChannel.PHONE:
        existing = await find_person_by_phone(session, str(challenge.phone_e164))
    else:
        existing = await session.scalar(select(Person).where(Person.email == challenge.email))
    if existing is not None:
        guard_region(held_in=existing.region, asked_from=region)
        if not existing.display_name and challenge.display_name:
            existing.display_name = challenge.display_name
        return existing
    return await register_person(
        session,
        region=region,
        display_name=challenge.display_name or "",
        phone_e164=challenge.phone_e164,
        email=challenge.email,
        language=challenge.language or "en",
    )


async def _verify(
    session: AsyncSession,
    *,
    region: Region,
    channel: LoginChannel,
    address: str,
    secret: str,
) -> tuple[LoginSession, str]:
    moment = utcnow()
    open_challenges = await _open_challenges(session, channel=channel, address=address)
    if not open_challenges:
        raise NoOpenChallenge(f"no open challenge for this {channel}")
    challenge = open_challenges[0]
    guard_region(held_in=challenge.region, asked_from=region)
    if as_utc(challenge.expires_at) <= moment:
        raise ChallengeExpired("the code is older than ten minutes")
    if challenge.attempts >= MAX_ATTEMPTS:
        raise ChallengeLocked("five wrong tries spend the code")

    if not hmac.compare_digest(challenge.code_hash, _hash_secret(challenge.id, secret)):
        # The wrong try is counted before the refusal goes out, and it must be kept: the
        # channel unwinds a refused request, so the count is registered to be replayed.
        challenge.attempts += 1
        await session.flush()
        keep_on_refusal(session, _count_wrong_try(challenge.id))
        raise WrongCode("that is not the code that was sent")

    challenge.consumed_at = moment
    try:
        person = await _person_for(session, region=region, challenge=challenge)
    except OutOfRegion:
        # This deployment should never have been asked. Refusing at start would tell the
        # asker the number is known elsewhere, so the ask was taken and is thrown away now:
        # nothing about the address stays in this region's database.
        await session.execute(_purge(channel, address))
        keep_on_refusal(session, _purge_again(channel, address))
        raise
    challenge.person_id = person.id
    return await open_session(session, region=region, person=person)


def _count_wrong_try(challenge_id: uuid.UUID) -> Callable[[AsyncSession], Awaitable[None]]:
    async def again(session: AsyncSession) -> None:
        row = await session.get(LoginChallenge, challenge_id)
        if row is not None:
            row.attempts += 1
            await session.flush()

    return again


def _purge(channel: LoginChannel, address: str) -> Delete:
    column = LoginChallenge.phone_e164 if channel is LoginChannel.PHONE else LoginChallenge.email
    return delete(LoginChallenge).where(LoginChallenge.channel == channel, column == address)


def _purge_again(channel: LoginChannel, address: str) -> Callable[[AsyncSession], Awaitable[None]]:
    async def again(session: AsyncSession) -> None:
        await session.execute(_purge(channel, address))

    return again


async def verify_phone_code(
    session: AsyncSession,
    *,
    region: Region,
    phone_e164: str,
    code: str,
) -> tuple[LoginSession, str]:
    """Prove the phone with the code sent to it. The session, and the token, once."""
    return await _verify(
        session, region=region, channel=LoginChannel.PHONE, address=phone_e164, secret=code
    )


async def verify_email_link(
    session: AsyncSession,
    *,
    region: Region,
    email: str,
    token: str,
) -> tuple[LoginSession, str]:
    """Prove the email address with the token in the link sent to it."""
    return await _verify(
        session, region=region, channel=LoginChannel.EMAIL, address=email, secret=token
    )


async def open_session(
    session: AsyncSession,
    *,
    region: Region,
    person: Person,
) -> tuple[LoginSession, str]:
    """Issue a session for a person who has just proved who he is. Returns the token once."""
    moment = utcnow()
    token = secrets.token_urlsafe(32)
    login = LoginSession(
        region=region,
        person_id=person.id,
        token_hash=_hash_token(token),
        created_at=moment,
        expires_at=moment + SESSION_LIFETIME,
    )
    session.add(login)
    await session.flush()
    return login, token


async def resolve_session(
    session: AsyncSession,
    *,
    region: Region,
    token: str | None,
) -> tuple[Person, LoginSession]:
    """Who this token is. `NoSession` for anything but an open token issued in this region."""
    moment = utcnow()
    if not token:
        raise NoSession("no token")
    login = await session.scalar(
        select(LoginSession).where(LoginSession.token_hash == _hash_token(token))
    )
    if login is None or not login.is_open(moment):
        raise NoSession("no such open session")
    guard_region(held_in=login.region, asked_from=region)
    person = await session.get(Person, login.person_id)
    if person is None:
        raise NoSession("no such person")
    guard_region(held_in=person.region, asked_from=region)
    return person, login


async def logout(
    session: AsyncSession, *, login: LoginSession, now: datetime | None = None
) -> None:
    """Close the session. The row stays, closed; the token is no longer anyone."""
    if login.revoked_at is None:
        login.revoked_at = utcnow()
        await session.flush()
