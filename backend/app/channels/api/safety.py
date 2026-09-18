"""The safety routes (E13-01, E13-02, E14-01). Every one takes the key context.

    GET  /profiles/{id}/emergency-card        the card as JSON: data and verified lines
    GET  /profiles/{id}/emergency-card.html   the same card as one printable page
    PUT  /profiles/{id}/emergency-card/insurer the insurer on the card, on the typer's yes
    POST /profiles/{id}/not-feeling-well      the button: voice or words in, the card out
    POST /profiles/{id}/not-feeling-well/stream    the same, streamed: the button runs, then a step per real check, then the card
    GET  /profiles/{id}/not-feeling-well/offline   the two cards the phone keeps for no network
    POST /profiles/{id}/symptoms              a symptom in his words, with how much and since when
    GET  /profiles/{id}/symptoms?since=       the log, in plain words with the day's name

The emergency card is opened by `Scope.EMERGENCY`, which every role preset holds; the button
and the log write and read the record (`Scope.RECORDS`). There is no public link to the
card: a stranger holding his phone sees the cached page the client kept, and a stranger
holding a URL sees nothing without a key.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import AwareDatetime

from app.channels.about_him import reader_of
from app.channels.api.delivery import via_of
from app.channels.api.deps import Context, Db, providers_of, session_scope, settings_of
from app.channels.api.refusals import refused
from app.channels.api.safety_schemas import (
    EmergencyCardOut,
    InsurerIn,
    InsurerSetOut,
    OfflineCardsOut,
    SaidIn,
    SymptomEntryOut,
    SymptomLoggedOut,
    SymptomLogOut,
    WhatToDoOut,
)
from app.channels.printable import emergency_card_html
from app.channels.safety_strings import severity_said
from app.delivery.timeline_strings import NFW_STEPS
from app.errors import Refusal
from app.insurance.insurer import set_insurer
from app.safety.emergency_card import emergency_card
from app.safety.models import CardFormat
from app.safety.not_feeling_well import (
    NfwStep,
    not_feeling_well,
    not_feeling_well_stream,
    offline_cards,
)
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
        emergency_card_html(shown, demo=settings_of(request).demo_mode),
        headers={"Cache-Control": "private, max-age=0, must-revalidate"},
    )


@router.put("/{profile_id}/emergency-card/insurer")
async def insurer(body: InsurerIn, context: Context, session: Db) -> InsurerSetOut:
    """His insurer on the card (E13-01): typed by him or his chief, saved on the typer's own
    yes for exactly these words; no name takes it off. An emergency-only key reads the card
    and cannot set it (`NotTheirsToSetInsurer`, 403); an identity-card number is not a policy
    reference (`NotAPolicyReference`, 400)."""
    row = await set_insurer(
        session,
        context=context,
        name=body.name,
        policy_reference=body.policy_reference,
        confirmation_id=body.confirmation_id,
    )
    return InsurerSetOut(
        insurer_id=row.id,
        name=row.name,
        policy_reference=row.policy_reference,
        set_by_person_id=row.set_by_person_id,
        set_at=row.set_at,
    )


@router.get("/{profile_id}/not-feeling-well/offline")
async def offline(
    context: Context, session: Db, language: str | None = Language
) -> OfflineCardsOut:
    """The two cards the phone keeps for when it cannot reach Nura (the web client, W7): one
    for a red word tapped with no network, one for the button pressed with no network. The
    catalogue's lines, verified, naming the chief and the region's ambulance number. A read:
    nothing is written, nobody is told, and nothing here escalates."""
    return OfflineCardsOut.of(await offline_cards(session, context=context, language=language))


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


def _sse(payload: dict[str, object]) -> bytes:
    """One Server-Sent Event: a `data:` line of JSON, blank line after
    (`app.channels.api.timeline._sse`, the same shape every streaming route here uses)."""
    return f"data: {json.dumps(payload)}\n\n".encode()


async def _refusal_event(request: Request, refusal: Refusal) -> bytes:
    """A refusal mid-stream, in the same shape the plain route answers it in
    (`app.channels.api.timeline._refusal_event`)."""
    response = await refused(request, refusal)
    body = json.loads(bytes(response.body))
    return _sse({"type": "refusal", "status": response.status_code, **body})


@router.post("/{profile_id}/not-feeling-well/stream", status_code=status.HTTP_200_OK)
async def button_stream(body: SaidIn, request: Request, context: Context) -> StreamingResponse:
    """`POST /{id}/not-feeling-well`, streamed (docs/design-direction.md 'Conversation,
    waiting and thinking'): the whole button runs first, entirely unchanged, red-flag path
    and all (`not_feeling_well_stream`'s own docstring — this never interleaves a step into
    that flow, only narrates it once it is done), then a `step` event for each real check it
    made, then a `card` event, the same `WhatToDoOut` the plain route gives. An older web
    client that has never asked for this route keeps using the plain one unchanged.

    Opens its own session (`session_scope`), never `Depends(db)`, for the reason
    `app.channels.api.timeline.ask_stream` gives."""
    providers = providers_of(request)

    async def events() -> AsyncIterator[bytes]:
        try:
            async with session_scope(request) as session:
                reader = await reader_of(session, context, body.language)
                done = None
                steps: list[bytes] = []
                async for event in not_feeling_well_stream(
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
                ):
                    if isinstance(event, NfwStep):
                        steps.append(event.key.value.encode())
                    else:
                        done = event
                assert done is not None
                # `done.language` is the language `not_feeling_well` actually rendered the
                # card in — never `reader.language`, which is only a caregiver-key default
                # unrelated to whose profile this is (`app.channels.about_him.Reader`).
                lang = done.language if done.language in NFW_STEPS else "en"
                for raw in steps:
                    key = raw.decode()
                    label = reader.says(NFW_STEPS[lang][key])
                    yield _sse({"type": "step", "key": key, "label": label})
                yield _sse({"type": "card", "card": WhatToDoOut.of(done).model_dump(mode="json")})
        except Refusal as refusal:
            yield await _refusal_event(request, refusal)

    return StreamingResponse(events(), media_type="text/event-stream")


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
