"""The safety routes (E13-01, E13-02, E14-01). Every one takes the key context.

    GET  /profiles/{id}/emergency-card        the card as JSON: data and verified lines
    GET  /profiles/{id}/emergency-card.html   the same card as one printable page
    POST /profiles/{id}/not-feeling-well      the button: voice or words in, the card out
    POST /profiles/{id}/symptoms              a symptom in his words, with how much and since when
    GET  /profiles/{id}/symptoms?since=       the log, in plain words with the day's name

The emergency card is opened by `Scope.EMERGENCY`, which every role preset holds; the button
and the log write and read the record (`Scope.RECORDS`). There is no public link to the
card: a stranger holding his phone sees the cached page the client kept, and a stranger
holding a URL sees nothing without a key.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import AwareDatetime

from app.channels.api.delivery import via_of
from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.safety_schemas import (
    EmergencyCardOut,
    SaidIn,
    SymptomEntryOut,
    SymptomLoggedOut,
    SymptomLogOut,
    WhatToDoOut,
)
from app.channels.printable import emergency_card_html
from app.channels.safety_strings import severity_said
from app.safety.emergency_card import emergency_card
from app.safety.models import CardFormat
from app.safety.not_feeling_well import not_feeling_well
from app.safety.symptom_log import (
    Entry,
    log_symptom,
    nothing_since_line,
    symptoms_since,
)

router = APIRouter(prefix="/profiles", tags=["safety"])

Language = Query(default=None, min_length=2, max_length=16)
Since = Query(default=None)


@router.get("/{profile_id}/emergency-card")
async def card(
    request: Request, context: Context, session: Db, language: str | None = Language
) -> EmergencyCardOut:
    """The emergency card, rendered now from State, in `language` or the profile's own.
    Refused when the last State is behind the record (`StaleState`, 409) rather than shown."""
    shown = await emergency_card(
        session,
        context=context,
        registry=providers_of(request).drug_registry,
        language=language,
        format=CardFormat.JSON,
    )
    return EmergencyCardOut.of(shown)


@router.get("/{profile_id}/emergency-card.html", response_class=HTMLResponse)
async def printable(
    request: Request, context: Context, session: Db, language: str | None = Language
) -> HTMLResponse:
    """The same card as a single self-contained page: paper surface, 20px body, the tokens
    inline, nothing fetched. The client caches it for offline; a print goes in his wallet."""
    shown = await emergency_card(
        session,
        context=context,
        registry=providers_of(request).drug_registry,
        language=language,
        format=CardFormat.HTML,
    )
    return HTMLResponse(
        emergency_card_html(shown),
        headers={"Cache-Control": "private, max-age=0, must-revalidate"},
    )


@router.post("/{profile_id}/not-feeling-well", status_code=status.HTTP_201_CREATED)
async def button(body: SaidIn, request: Request, context: Context, session: Db) -> WhatToDoOut:
    """ "I'm not feeling well." His words are kept, heard, read for red flags first, and the
    family is told; the lines say what to do now. Anyone with a key may press it for him —
    a helper, a caregiver — and a red flag escalates whoever pressed; a voice note is the sender's
    own words, kept like typed text (ADR 0003). Nothing here starts, stops or changes a
    medicine."""
    providers = providers_of(request)
    done = await not_feeling_well(
        session,
        context=context,
        store=providers.object_store,
        transcriber=providers.transcriber,
        registry=providers.drug_registry,
        via=via_of(request),
        words=body.words,
        audio=body.audio_bytes(),
        content_type=body.content_type,
        language=body.language,
    )
    return WhatToDoOut.of(done)


def _severity_words(entry: Entry) -> str | None:
    return None if entry.severity is None else severity_said(entry.severity, entry.language)


@router.post("/{profile_id}/symptoms", status_code=status.HTTP_201_CREATED)
async def add_symptom(
    body: SaidIn, request: Request, context: Context, session: Db
) -> SymptomLoggedOut:
    """A symptom in his words — by voice or typed — read for the symptom, how much and
    since when, and written down with its window. A red-flag word escalates as the button
    does."""
    providers = providers_of(request)
    logged = await log_symptom(
        session,
        context=context,
        store=providers.object_store,
        transcriber=providers.transcriber,
        registry=providers.drug_registry,
        via=via_of(request),
        words=body.words,
        audio=body.audio_bytes(),
        content_type=body.content_type,
        language=body.language,
    )
    return SymptomLoggedOut.of(logged, _severity_words(logged.entry))


@router.get("/{profile_id}/symptoms")
async def symptoms(
    context: Context,
    session: Db,
    since: AwareDatetime | None = Since,
    language: str | None = Language,
) -> SymptomLogOut:
    """The symptoms written down since `since` (default the last seven days), oldest first,
    each in plain words with the day's name. Read under the record's scope: the owner, the
    chief and a caregiver; a viewer's or a helper's key is refused (`OutOfScope`, 403)."""
    log = await symptoms_since(session, context=context, since=since, language=language)
    shown = [SymptomEntryOut.of(entry, _severity_words(entry)) for entry in log.entries]
    empty = None
    if not shown:
        empty = nothing_since_line(log.since, language=log.language, region=context.region)
    return SymptomLogOut.of(log.since, shown, empty)
