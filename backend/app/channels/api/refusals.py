"""How a refusal leaves the building: a status, and the refusal's name. Nothing else.

A `Refusal` carries a message written for a log, and that message can name ids of other
people and profiles. None of it crosses the wire. The body is `{"refusal": "<ClassName>"}`,
plus the scope for an `OutOfScope`, so the app can say the right sentence — and the
sentence is the app's to write, not this layer's.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.audit.trail import NotTheirsToRead
from app.channels.api.profiles import NoSuchHolder
from app.consent.service import (
    NoConsent,
    NoConsentToWithdraw,
    NotTheirConsentToGive,
    NotTheirConsentToWithdraw,
)
from app.errors import Refusal
from app.identity.doors import AlreadySetUp, NoStewardshipHere, NotTheClaimant
from app.identity.login import NoSession
from app.identity.service import AlreadyRegistered, ProfileAlreadyOwned, WaitingToBeClaimed
from app.ingestion.photos import PhotoTooLarge
from app.ingestion.review import AlreadyConfirmed, NoSuchReviewCard
from app.keys.context import NoKey, OutOfScope
from app.keys.grants import NoKeyToClose, NotTheirKeyToCut
from app.medicines.service import AlreadyRecorded, NoSuchLine, NotTheirsToChange
from app.memory.spine import NoSuchAppointment as NoSuchVisit
from app.memory.spine import NoSuchProvider
from app.reasoning.visits.gaps import NoSuchAppointment
from app.reasoning.visits.questions import NoSuchQuestion
from app.reasoning.visits.summary import AlreadyConfirmed as SummaryAlreadyConfirmed
from app.reasoning.visits.summary import NoSuchSummary, TranscriptTooLarge
from app.regions import OutOfRegion
from app.safety.high_risk import HighRiskNeedsLabelPhoto
from app.state.service import NoState

STATUS: tuple[tuple[type[Refusal], int], ...] = (
    (NoSession, 401),
    (NoKey, 403),
    (OutOfScope, 403),
    (OutOfRegion, 403),
    (NotTheirsToRead, 403),
    (NotTheirKeyToCut, 403),
    (NoSuchHolder, 403),
    # No consent in force for the act: withheld, withdrawn or out of date, by name.
    (NoConsent, 403),
    (NotTheirConsentToGive, 403),
    (NotTheirConsentToWithdraw, 403),
    (NotTheClaimant, 403),
    # A key to read the medicines is not a key to change them.
    (NotTheirsToChange, 403),
    (NoConsentToWithdraw, 404),
    (NoKeyToClose, 404),
    (NoStewardshipHere, 404),
    (NoState, 404),
    (NoSuchReviewCard, 404),
    (NoSuchAppointment, 404),
    (NoSuchVisit, 404),
    (NoSuchProvider, 404),
    (NoSuchQuestion, 404),
    (NoSuchSummary, 404),
    (NoSuchLine, 404),
    (PhotoTooLarge, 413),
    (TranscriptTooLarge, 413),
    (ProfileAlreadyOwned, 409),
    # A card is confirmed once; its facts are facts now, superseded and never re-confirmed.
    (AlreadyConfirmed, 409),
    (SummaryAlreadyConfirmed, 409),
    # The same label twice, or one that adds nothing, changes nothing.
    (AlreadyRecorded, 409),
    (AlreadyRegistered, 409),
    # One graph per number: the second setup, and the for-me door on a number already set
    # up for, are answered by name and nothing else.
    (AlreadySetUp, 409),
    (WaitingToBeClaimed, 409),
)
"""Every other refusal is a 400: the request was well formed and the answer is no. The
high-risk rule is one of those — `HighRiskNeedsLabelPhoto`, 400, naming the class."""


def status_of(refusal: Refusal) -> int:
    for kind, status in STATUS:
        if isinstance(refusal, kind):
            return status
    return 400


async def refused(request: Request, refusal: Exception) -> JSONResponse:
    assert isinstance(refusal, Refusal)
    body: dict[str, str] = {"refusal": type(refusal).__name__}
    if isinstance(refusal, OutOfScope):
        body["scope"] = refusal.scope.value
    if isinstance(refusal, HighRiskNeedsLabelPhoto):
        body["drug_class"] = refusal.drug_class
    return JSONResponse(status_code=status_of(refusal), content=body)
