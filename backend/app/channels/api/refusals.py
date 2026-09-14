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
from app.channels.api.consent_words import NoWordsInThatLanguage
from app.channels.api.profiles import NoSuchHolder
from app.channels.safety_strings import NotPlainWords as CatalogueNotPlainWords
from app.channels.whatsapp.outbound.level0 import NoPatientYet
from app.channels.whatsapp.outbound.send import OutsideTheWindow
from app.channels.whatsapp.provider import NotAWebhook
from app.consent.service import (
    NoConsent,
    NoConsentToWithdraw,
    NotTheirConsentToGive,
    NotTheirConsentToWithdraw,
)
from app.delivery.feed.engagement import NoSuchItem
from app.delivery.feed.rank import NoCachedPage
from app.delivery.feed.search import NoSuchSearchJob
from app.delivery.feed.sources import NotTheirsToManage
from app.delivery.feed.twin import NotInThatLanguage
from app.delivery.nudges.engine import NoSuchNudge, NotAPlanDay, NothingToHandOver
from app.delivery.nudges.metrics import NotOwnerOrChief
from app.delivery.triggers.deliver import NoOneToActFor
from app.delivery.triggers.engine import NothingToSay
from app.delivery.triggers.ladder import NotOnTheLadder
from app.delivery.voice import NoVoiceFor, TooLongToSay
from app.errors import Refusal
from app.family.common import NotAChief, NotPlainWords
from app.family.documents import NotADocument
from app.family.photos import NoSuchPhoto, NotAPhoto, NotTheirsToTakeBack
from app.family.privacy import AlreadyMarked, NotAPartToMark, NotMarked, NotTheOwner
from app.family.pushes import BadWindow, MissingSlot, NoSuchTemplate, NotAMemo
from app.family.roster import (
    AlreadyDone,
    NoSuchSlot,
    NoSuchTask,
    NotADuty,
    NotOnThisProfile,
    NotTheDoer,
)
from app.family.thread import NoSuchTask as NoSuchTaskForCard
from app.identity.doors import AlreadySetUp, NoStewardshipHere, NotTheClaimant
from app.identity.login import NoSession
from app.identity.service import AlreadyRegistered, ProfileAlreadyOwned, WaitingToBeClaimed
from app.ingestion.connectors.service import (
    AlreadyDecided,
    NoSuchConnector,
    NoSuchProposal,
    NotTheirsToConnect,
    NotTheirsToDecide,
)
from app.ingestion.consult import (
    ConsultTooLong,
    NoSuchRecording,
    NotAClip,
    NotAConsultRecording,
)
from app.ingestion.documents import PdfTooLarge
from app.ingestion.notes import NoSuchEventNote, NoteTooLarge
from app.ingestion.photos import PhotoTooLarge
from app.ingestion.review import AlreadyConfirmed, NoSuchReviewCard
from app.ingestion.voice import VoiceNoteTooLong
from app.keys.context import NoKey, OutOfScope
from app.keys.grants import NoKeyToClose, NothingToNarrow, NotTheirKeyToCut, WouldWiden
from app.language.review import (
    AlreadyReviewed,
    NoSuchReviewItem,
    NotStaff,
    SourceAlreadyListed,
)
from app.medicines.service import AlreadyRecorded, NoSuchLine, NotTheirsToChange
from app.memory.attach import AlreadyHangsThere
from app.memory.episodic import OnlyTheFamilyHears
from app.memory.providers import NotAPlaceNote, NoteNamesHealth
from app.memory.spine import NoSuchAppointment, NoSuchProvider, NotThatStatusChange
from app.memory.timeline import NotACursor
from app.memory.working import EpisodeAlreadyClosed, EpisodeAlreadyOpen, NoSuchEpisode
from app.onboarding.biography import (
    AlreadyReadBack,
    BiographyAlreadyOpen,
    BiographyClosed,
    CardsStillOpen,
    NoBiography,
    NoSuchReadBackLine,
    NotAtThisStep,
    PaperAlreadyAdded,
)
from app.onboarding.biography import NoSuchQuestion as NoSuchBiographyQuestion
from app.onboarding.plan import NoPlan, NoSuchPrompt, PromptAlreadySettled
from app.onboarding.settings import NotTheirsToSetUp
from app.reasoning.feelings.service import AlreadyAnswered, NoSuchTap, NotAnAnswer
from app.reasoning.trends import NoSuchAnalyte
from app.reasoning.visits.gaps import NoSuchAppointment as NoSuchVisit
from app.reasoning.visits.guard import NotTheirsToChangeVisits
from app.reasoning.visits.logistics import NotOnThisVisit
from app.reasoning.visits.questions import NoSuchQuestion
from app.reasoning.visits.summary import AlreadyConfirmed as SummaryAlreadyConfirmed
from app.reasoning.visits.summary import DrugNamedInAFact, NoSuchSummary, TranscriptTooLarge
from app.regions import OutOfRegion
from app.routines.service import NotTheirsToSet
from app.safety.high_risk import HighRiskNeedsLabelPhoto
from app.search.ask import NotAQuestion
from app.search.transcripts import NotASearch
from app.state.service import NoState, StaleState

STATUS: tuple[tuple[type[Refusal], int], ...] = (
    (NoSession, 401),
    # The pharmacist's review queue (E22-04): staff only, no profile in it.
    (NotStaff, 403),
    (NoSuchReviewItem, 404),
    (AlreadyReviewed, 409),
    (SourceAlreadyListed, 409),
    (NoKey, 403),
    (OutOfScope, 403),
    (OutOfRegion, 403),
    (NotTheirsToRead, 403),
    (NotTheirKeyToCut, 403),
    (NoSuchHolder, 403),
    # A key that reads the visits does not write them; same footing as the medicines.
    (NotTheirsToChangeVisits, 403),
    # A webhook body not signed by the provider, or a verify token that is not ours.
    (NotAWebhook, 403),
    # No consent in force for the act: withheld, withdrawn or out of date, by name.
    (NoConsent, 403),
    (NotTheirConsentToGive, 403),
    (NotTheirConsentToWithdraw, 403),
    # The engine's sources and jobs are the owner's and his chief's to see (E21).
    (NotTheirsToManage, 403),
    (NotTheClaimant, 403),
    # A key to read the medicines is not a key to change them.
    (NotTheirsToChange, 403),
    # The day, and a calendar's proposals (E10-01, E18-02): reading them is not setting them.
    (NotTheirsToSet, 403),
    (NotTheirsToConnect, 403),
    (NotTheirsToDecide, 403),
    # The family's arrangements (E12): the owner's and his chief's; a key is never widened
    # in place; a task is done by the person it names; only me is the owner's alone.
    (NotAChief, 403),
    (NotTheOwner, 403),
    (NotTheDoer, 403),
    (WouldWiden, 403),
    (NotOnThisProfile, 403),
    (NoSuchSlot, 404),
    (NoSuchTask, 404),
    (NoSuchTaskForCard, 404),
    (NoSuchTemplate, 404),
    (NotMarked, 404),
    (NothingToNarrow, 409),
    (AlreadyMarked, 409),
    (AlreadyDone, 409),
    # Setting a profile up — settings, biography, first week — is the owner's and his
    # chief's (E01); a sitting walks its steps in order, one sitting at a time.
    (NotTheirsToSetUp, 403),
    (NoBiography, 404),
    (NoPlan, 404),
    (NoSuchPrompt, 404),
    (NoSuchBiographyQuestion, 404),
    (NoSuchReadBackLine, 404),
    (PaperAlreadyAdded, 409),
    (BiographyAlreadyOpen, 409),
    (BiographyClosed, 409),
    (NotAtThisStep, 409),
    (AlreadyReadBack, 409),
    (CardsStillOpen, 409),
    (PromptAlreadySettled, 409),
    (NoConsentToWithdraw, 404),
    (NoKeyToClose, 404),
    (NoStewardshipHere, 404),
    (NoState, 404),
    (NoWordsInThatLanguage, 404),
    # A stewarded profile has no patient to send the morning card to yet.
    (NoPatientYet, 404),
    (NoSuchReviewCard, 404),
    (NoSuchAppointment, 404),
    (NoSuchVisit, 404),
    (NoSuchProvider, 404),
    (NoSuchQuestion, 404),
    (NoSuchSummary, 404),
    # A fact heard at a visit that names a drug is never written; the answer names the rule.
    (DrugNamedInAFact, 400),
    (NoSuchItem, 404),
    (NoOneToActFor, 404),
    (NothingToSay, 404),
    # Only someone a flag's ladder reached, whose key covers it, answers it (E11-06).
    (NotOnTheLadder, 403),
    # No audio for this card (E11-04): not its language, no voice in it yet, too long to say.
    # The web client then says it with the phone's own voice.
    (NotInThatLanguage, 404),
    (NoVoiceFor, 404),
    (TooLongToSay, 404),
    (NoSuchSearchJob, 404),
    (NoCachedPage, 404),
    (NoSuchLine, 404),
    (NoSuchAnalyte, 404),
    (NoSuchConnector, 404),
    (NoSuchProposal, 404),
    # The timeline (E03): a visit, an episode or a provider not on this profile; a paper
    # hangs somewhere once; one episode of a kind open at a time; a status goes one way.
    (NoSuchEpisode, 404),
    (AlreadyHangsThere, 409),
    (EpisodeAlreadyOpen, 409),
    (EpisodeAlreadyClosed, 409),
    (NotThatStatusChange, 409),
    (PhotoTooLarge, 413),
    # A visit's recording (E02-05): too big or too long to be one visit; no recording of that
    # artefact on this profile.
    (ConsultTooLong, 413),
    # A visit's recording is heard by him and the family he let in, and nobody else.
    (OnlyTheFamilyHears, 403),
    (NoSuchPhoto, 404),
    (NotTheirsToTakeBack, 403),
    (NoSuchRecording, 404),
    (TranscriptTooLarge, 413),
    (VoiceNoteTooLong, 413),
    # The record moved past the State a card was composed from: read it again, compose again.
    (StaleState, 409),
    # A safety template failed the plain-words standard at run time: the fault is the
    # catalogue's, not the caller's. (E12's `NotPlainWords` — words the caller offered — is a
    # 400 with its findings, below.)
    (CatalogueNotPlainWords, 500),
    # Free text needs the 24-hour window; outside it only a template goes.
    (OutsideTheWindow, 409),
    # A PDF or a note on an event is not this big (E02-03, E02-06).
    (PdfTooLarge, 413),
    (NoteTooLarge, 413),
    (NoSuchEventNote, 404),
    (ProfileAlreadyOwned, 409),
    # A card is confirmed once; its facts are facts now, superseded and never re-confirmed.
    (AlreadyConfirmed, 409),
    (SummaryAlreadyConfirmed, 409),
    # The same label twice, or one that adds nothing, changes nothing.
    (AlreadyRecorded, 409),
    # A proposal has one yes or one no; a trend is not rendered from a State the record has
    # moved past, or one the key cannot check (compose again).
    (AlreadyDecided, 409),
    (StaleState, 409),
    (AlreadyRegistered, 409),
    # One graph per number: the second setup, and the for-me door on a number already set
    # up for, are answered by name and nothing else.
    (AlreadySetUp, 409),
    (WaitingToBeClaimed, 409),
    # The feeling cloud and the nudges (E17): the metrics are the owner's and his chief's; a
    # tap asks one thing once; a day with nothing to hand over says so by name.
    (NotOwnerOrChief, 403),
    (NoSuchTap, 404),
    (NoSuchNudge, 404),
    (AlreadyAnswered, 409),
    (NothingToHandOver, 409),
)
"""Every other refusal is a 400: the request was well formed and the answer is no. The
high-risk rule is one of those — `HighRiskNeedsLabelPhoto`, 400, naming the class — and so
are the family's shape refusals (`NotADuty`, `NotAPartToMark`, `NotAMemo`, `MissingSlot`,
`BadWindow`, `NotADocument`) and `NotPlainWords`, which carries its findings so the composer
can fix the line."""

_SHAPE: tuple[type[Refusal], ...] = (
    NotADuty,
    NotAPartToMark,
    NotAMemo,
    MissingSlot,
    BadWindow,
    NotADocument,
    NotAnAnswer,
    NotAPlanDay,
    # The timeline's (E03): a place note that is not one line, or that names a medicine or a
    # condition; a cursor that is not the last page's; a question that is not one line.
    NotAPlaceNote,
    NoteNamesHealth,
    NotACursor,
    NotAQuestion,
    NotASearch,
    # A photo shared with the family that is not an image (E12-02, E21-05).
    NotAPhoto,
    # The visit day's (E05-03, E02-05): bytes that are not a recorder's audio, a clip outside
    # its recording, a driver who holds nothing here or a visit that has been.
    NotAConsultRecording,
    NotAClip,
    NotOnThisVisit,
)
"""Named so that a reader of this file sees every family and timeline refusal; each is a
400."""


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
    if isinstance(refusal, NotPlainWords):
        # The verifier's findings — rule, problem, rewrite — so the composer can fix the
        # line. They are about the words offered, never about the record.
        return JSONResponse(
            status_code=status_of(refusal), content={**body, "findings": refusal.findings}
        )
    return JSONResponse(status_code=status_of(refusal), content=body)
