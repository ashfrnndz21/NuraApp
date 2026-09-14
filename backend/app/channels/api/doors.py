"""Which doors apply to the caller: the first question after registration, answered."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.channels.api.deps import CurrentPerson, Db, settings_of
from app.channels.api.schemas import DoorsOut
from app.identity.doors import doors_for

router = APIRouter(tags=["doors"])


@router.get("/doors")
async def doors(
    request: Request,
    person: CurrentPerson,
    session: Db,
    language: str | None = Query(default=None, min_length=2, max_length=16),
) -> DoorsOut:
    """Who is this for, and what is already there for the caller.

    `own` is his graph if he has opened one. `claimable` is a graph set up for his number
    that waits for his OK, with the words in `language` (or his own). `invited` is every
    graph a key lets him in to — the third door: a key cut for his number before he
    registered is already his. `stewarding` is every graph he holds for someone who has
    not claimed it yet. Every graph is read through its context and written down.
    """
    return DoorsOut.of(
        await doors_for(
            session, region=settings_of(request).region, person=person, language=language
        )
    )
