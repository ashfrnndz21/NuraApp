"""The Welcome screen's two shortcuts, demo/dev only (`app.demo_seed`, NURA_DEMO_SEED=1).

    POST /dev/quick-signin   {"as": "pa" | "mei"}

"Try it as Pa" and "Try it as Mei" sign in without the phone number and the code a real
sign-in asks for — the demo/dev code stays server-side, never shipped to the client, and the
number is the one `app.demo_seed` seeded. This mints a session the way `POST
/auth/phone/verify` does (`app.identity.login.open_session`, the same row, the same token
shape), for a person `app.demo_seed` has already put through a real sign-up; it is not a
second way to sign in as anyone else, and it answers 404 — the same door every other dev-only
route is behind (`app.channels.api.dev_clock`) — wherever NURA_DEMO_SEED is not set.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.channels.api.deps import Db, settings_of
from app.channels.api.schemas import SessionOut
from app.demo_numbers import mei_number, pa_number
from app.identity.login import open_session
from app.identity.service import find_person_by_phone

router = APIRouter(tags=["dev"])


class QuickSignInIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    as_: Literal["pa", "mei"] = Field(alias="as")


class NotSeeded(HTTPException):
    def __init__(self, who: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"the demo has not seeded {who} yet"
        )


@router.post("/dev/quick-signin")
async def quick_signin(body: QuickSignInIn, request: Request, session: Db) -> SessionOut:
    settings = settings_of(request)
    if not settings.demo_seed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    phone = pa_number(settings.region) if body.as_ == "pa" else mei_number(settings.region)
    person = await find_person_by_phone(session, phone)
    if person is None:
        raise NotSeeded(body.as_)
    login, token = await open_session(session, region=settings.region, person=person)
    return SessionOut(token=token, person_id=login.person_id, region=login.region)
