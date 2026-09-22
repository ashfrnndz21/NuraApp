"""The review card: from a photo's extraction to a person's yes to facts with provenance.

`review_photo` reads the stored bytes back through the store, runs the extractor, and writes
one card with one field per extracted statement. `confirm_review_card` is the other end: the
person's decisions, bound to a confirmation he minted for exactly them, close the card and
write one Fact per confirmed or corrected field — with the photo as provenance, the person
as confirmer, the unit, and a validity window opening on the date on the paper. A rejected
field writes nothing. State recomputes as each fact lands, through the memory store's hook.

One yes, many facts. The person's tap is a confirmation over the whole card
(`app.drafts.ReviewDraft`): every field and his decision on it. A fact needs a yes of its
own to be CONFIRMED_BY_PERSON, so once the card's yes is spent each fact's yes is written
down and used in the same unit of work, from the same person, for exactly the fact being
written — the way the readings route writes the yes for the number a person typed. The
card's yes is the evidence; the per-fact yes is how the store records who gave it.

What else a card may be (E02-02, E02-03, E02-08). A page is offered with a hint — the kind
the person says it is, or the route's, a machine's screen — and the card keeps it
(`asked_as`) beside what the page was read as; a page that is no health paper, or a photo
sent as a machine's screen that is not one, is an open card with no fields and a notice
(`notice_of`) saying so. A field Nura could not read is typed in — by anyone holding the
record, before the yes (`type_field`) — or rejected; it is never confirmed as read
(`UnreadableField`), and the field names who typed it. A card from a machine's screen is
written as one READING event and the facts of the reading (`app.ingestion.readings`); a
hospital letter or a clinic slip is written as the event it records — a discharge, a visit —
on the date on the paper, and its facts name that event beside the page.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.conclusions import ConclusionResponseKind, record_dropped_conclusion
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.delivery.timeline_strings import day_of
from app.drafts import DecidedField, FactDraft, ReviewDraft
from app.drugs.registry import DrugRegistry, LabelFields
from app.errors import Refusal
from app.identity.models import Profile
from app.ingestion.extract import (
    DocumentKind,
    ExtractedField,
    Extraction,
    Extractor,
    Hints,
    check_value,
    fold_legacy_reference_ranges,
)
from app.ingestion.models import (
    CONFIDENCE_THRESHOLD,
    DECISIONS,
    REVIEW_IN_PROGRESS,
    DocumentSource,
    FieldState,
    PendingQuestion,
    ReviewCard,
    ReviewField,
)
from app.ingestion.objects import NoSuchObject, ObjectStore, sha256_of
from app.ingestion.readings import (
    BLOOD_PRESSURE_RANGE,
    DIASTOLIC,
    READING,
    SINGLE_MEASURES,
    SYSTOLIC,
    reading_from,
)
from app.ingestion.whose_paper import IdentityOutcome, check_whose_paper
from app.keys.confirm import confirm, consume_confirmation
from app.keys.context import KeyContext, OutOfScope
from app.keys.repository import scoped_select
from app.keys.scopes import Scope
from app.medicines.models import LineStatus, MedicationLine
from app.memory.attach import attach_from_ingestion
from app.memory.episodic import held_here, record_event, require_artifact
from app.memory.models import Appointment, Artifact, ConfidenceState, EventKind, Fact
from app.memory.semantic import assert_fact
from app.memory.working import require_open_episode
from app.regions import REGION_TZ, guard_region
from app.safety.high_risk import high_risk_class
from app.safety.red_flags import FlagKind, red_flags_in, write_red_flag
from app.state.health_context import active_medicines

CARD = ReviewCard.__tablename__
FIELD = ReviewField.__tablename__
EXTERNAL_MODEL_PROCESSOR = "external_model_processor"
"""The audit target a reach outside the region is written under: a distinct target from
`CARD`/`FIELD`, so a reader of the trail can tell a page read by an external model processor
(e.g. `ClaudeExtractor.external_processor == "anthropic"`) apart from a fixture read, which
writes no such line at all (`review_artifact`)."""

MEDICINE_NAME = ("medicine", "name")
"""The field a label's drug is named in; what the high-risk lookup reads."""
MEDICINE_STRENGTH = ("medicine", "strength")

PILL_MAX_CONFIDENCE = 0.79
"""A pill photo names a drug by how it looks, never by reading it. Even a confident match
against the licensed registry is held here — below `app.ingestion.models.CONFIDENCE_THRESHOLD`
— so `needs_confirm` is always set and a person, then a pharmacist, always decides (docs:
"a proposal ... matched against the licensed registry; confidence forced below the
confirmation threshold so it always needs a person's decision")."""

ITEM_SUBJECT = re.compile(r"^item_\d+$")
"""One line of a pharmacy receipt (`app.ingestion.review._write_receipt`): every field of one
purchased line shares this subject, numbered in the order the receipt prints them."""

MEDICINE_COST_SUBJECT = "medicine_cost"
"""The subject a matched pharmacy receipt line's derived cost fact is written under
(`app.insurance.ledger.medicine_monthly_costs` reads it back), attribute the generic it was
matched to. Distinct from the line's own plain paper fact (`item_N`), which is always written
too — the receipt's own words are never replaced by the match."""


class NoSuchReviewCard(Refusal):
    """No review card by that id on this profile."""


class NoSuchReviewField(Refusal):
    """A decision named a field that is not on this card."""


class AlreadyConfirmed(Refusal):
    """This card has been confirmed. What it wrote is facts now; a wrong one is superseded."""


class NotEveryFieldDecided(Refusal):
    """One tap saves the whole card, so every field needs a decision, and only one."""


class NotADecision(Refusal):
    """A field is confirmed, corrected or rejected. A correction says what to."""


class UnreadableField(Refusal):
    """A field Nura could not read is typed in, or rejected. It is never confirmed as read."""


class QuestionUnanswered(Refusal):
    """D-2/D-4b: this card asked a plain question (`ReviewCard.pending_question`) and it has
    not been answered yet. Nothing is filed from it — not a fact, not a `person.*` field —
    until it is (`POST .../review-cards/{id}/answer`)."""


class CardSetAside(Refusal):
    """This card's question was answered in a way that keeps its paper out of the record —
    "someone else's", or "yes, the same paper" — for good. It can never be confirmed."""


class QuestionAlreadyAnswered(Refusal):
    """This card's question was already answered once. An answer does not change."""


class NoQuestionToAnswer(Refusal):
    """This card never asked a question, so there is nothing to answer."""


class NotAnAnswer(Refusal):
    """The value sent is not one of this question's own choices."""


class Notice(StrEnum):
    """What a card says about the page as a whole, where the page is not what it was offered
    as. The channel turns the code into his words (`app.channels.strings`)."""

    NOT_A_HEALTH_PAPER = "not_a_health_paper"
    NOT_A_MACHINE_SCREEN = "not_a_machine_screen"
    PHOTO_KIND_NOT_READ = "photo_kind_not_read"
    """A file of a kind the route accepted and this extractor never opened at all (E02-02):
    distinct from a page that was looked at and not made out, so the card does not ask for
    another photo of a kind that will fail again the same way."""


def notice_of(card: ReviewCard) -> Notice | None:
    """The notice a card carries, from what the page was read as and what it was offered as."""
    if card.document_kind is DocumentKind.NOT_HEALTH:
        return Notice.NOT_A_HEALTH_PAPER
    if card.document_kind is DocumentKind.UNSUPPORTED_FILE_TYPE:
        return Notice.PHOTO_KIND_NOT_READ
    if (
        card.asked_as is DocumentKind.DEVICE_SCREEN
        and card.document_kind is not DocumentKind.DEVICE_SCREEN
    ):
        return Notice.NOT_A_MACHINE_SCREEN
    return None


def _nothing_to_take(extraction: Extraction, asked_as: DocumentKind | None) -> bool:
    """A page no field may be taken from: not a health paper, or a photo sent as a machine's
    screen that is not one — its fields belong to another kind of card, not this one."""
    if extraction.document_kind is DocumentKind.NOT_HEALTH:
        return True
    return (
        asked_as is DocumentKind.DEVICE_SCREEN
        and extraction.document_kind is not DocumentKind.DEVICE_SCREEN
    )


DOCUMENT_EVENTS: Mapping[DocumentKind, tuple[EventKind, str]] = {
    DocumentKind.DISCHARGE_LETTER: (EventKind.DISCHARGE, "hospital letter"),
    DocumentKind.CLINIC_SLIP: (EventKind.VISIT, "clinic slip"),
}
"""The papers that record a moment, and the event each is written as on its date: the
discharge a hospital letter records, the visit a clinic slip was written at (E02-03). A lab
report, an insurance policy or a claim record no moment of their own; their kept fields are
plain facts on the paper's date (`_write_paper`'s fallback), a lab report's known-unit
readings apart (`_LAB_READING_BY_UNIT`)."""


RED_FLAG_SCANNED_KINDS = frozenset(
    {DocumentKind.LAB_REPORT, DocumentKind.PILL_PHOTO, DocumentKind.PHARMACY_RECEIPT}
)
"""Every kind whose proposed fields are scanned for a red-flag word before the card is even
shown (`_red_flag_scan`) — a lab report's own facility remark (documents-lab-reports-and-
insurance), and, the same way, a pill photo's free-text guess or a pharmacy receipt's item
name: "whichever way one comes in, it comes here first" (`app.safety.red_flags`)."""


async def _red_flag_scan(
    session: AsyncSession, *, context: KeyContext, artifact: Artifact, extraction: Extraction
) -> None:
    """Every red-flag word anywhere in a scanned kind's proposed fields, raised before the card
    is even shown — the same rule free text and a visit's transcript already keep
    (`app.safety.red_flags` module docstring): "whichever way one comes in, it comes here
    first". One flag per code, naming the artefact (never an appointment: a lab report or a
    receipt is not tied to a visit) so it still surfaces on `open_flags`
    (`Flag.artifact_id.is_not(None)`). No medicine names are passed in: a fever rule, if any,
    waits for a person's own word the way any paper field does — the page is read here, not
    reasoned about."""
    seen: set[str] = set()
    for field in extraction.fields:
        for hit in red_flags_in(
            field.subject.replace("_", " "), field.attribute.replace("_", " "), field.value
        ):
            if hit.code in seen:
                continue
            seen.add(hit.code)
            await write_red_flag(
                session,
                context=context,
                tell_the_family=True,
                kind=FlagKind.RED_FLAG,
                code=hit.code,
                subject="symptom",
                fact_ids=[],
                payload={
                    "word": hit.word,
                    "span": hit.span(),
                    "found_in": f"{field.subject}.{field.attribute}",
                },
                artifact_id=artifact.id,
                raised_at=utcnow(),
            )


_LAB_READING_CODES: Mapping[tuple[str, str], Any] = dict(SINGLE_MEASURES)
"""A lab report's own row is a reading proposal when its (subject, attribute) is one of the
app's own vitals codes — the exact pair a device's screen already writes
(`app.ingestion.readings.SINGLE_MEASURES`: `("blood_sugar", "glucose")`, `("weight", "kg")`,
`("heart_rate", "pulse")`), and its unit is the one the app already keeps that vital in. A
row named any other way, or in a different unit, is a normal lab row — its own subject and
attribute — and stays a plain paper fact: "a value with a unit the app knows becomes a
reading proposal; an unknown unit stays a paper fact"."""


def _in_range(value: Any, low: float, high: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return low <= value <= high


def _lab_reading_split(
    kept: Sequence[DecidedField],
) -> tuple[list[DecidedField], list[DecidedField]]:
    """Every kept field of a lab report, split into a reading proposal's fields and the rest,
    which stay plain paper facts. A field never taken from twice: the blood-pressure pair, if
    whole, in the app's own unit and in range, is taken first; every other field named and
    unitted the way the app's own vitals are, with a value in range, next; everything else is
    a paper fact — every ordinary lab row, a half blood pressure, and a vital in a unit or out
    of a range the app does not recognise (kept as read, never refused, the same as any other
    paper fact)."""
    by_code = {(field.subject, field.attribute): field for field in kept}
    systolic, diastolic = by_code.get(SYSTOLIC), by_code.get(DIASTOLIC)
    whole_bp = (
        systolic is not None
        and diastolic is not None
        and systolic.unit == "mmHg"
        and diastolic.unit == "mmHg"
        and _in_range(systolic.value, *BLOOD_PRESSURE_RANGE[SYSTOLIC])
        and _in_range(diastolic.value, *BLOOD_PRESSURE_RANGE[DIASTOLIC])
    )
    taken: set[uuid.UUID] = set()
    readings: list[DecidedField] = []
    if whole_bp:
        assert systolic is not None and diastolic is not None
        readings.extend((systolic, diastolic))
        taken.update((systolic.field_id, diastolic.field_id))
    rest: list[DecidedField] = []
    for field in kept:
        if field.field_id in taken:
            continue
        measure = _LAB_READING_CODES.get((field.subject, field.attribute))
        if (
            measure is not None
            and field.unit == measure.unit
            and _in_range(field.value, measure.low, measure.high)
        ):
            readings.append(field)
        else:
            rest.append(field)
    return readings, rest


@dataclass(frozen=True, slots=True)
class Decision:
    """What the person said about one field."""

    field_id: uuid.UUID
    decision: FieldState
    corrected_value: Any = None


def _cards_held_here(context: KeyContext) -> Any:
    """The cards whose photo is held in this region: part of every query returning cards, the
    way `fact_cites_only_what_is_held_here` is for facts."""
    return ReviewCard.artifact_id.in_(
        scoped_select(Artifact, context, Scope.RECORDS)
        .with_only_columns(Artifact.id)
        .where(held_here(context))
    )


class ImportStepKey(StrEnum):
    """One real stage of turning a stored photo or PDF into a review card, in the order
    `review_artifact_stream` yields them. Never every stage runs for every artefact: a
    document kind outside `RED_FLAG_SCANNED_KINDS` never raises `RED_FLAG_CHECKED` (only a
    lab report, a pill photo, or a pharmacy receipt is scanned, `_red_flag_scan`), and
    `LINKED` is yielded only when a real match was found — no invented step, no step for a
    check that did not run."""

    STORED = "stored"
    READING = "reading"
    FOUND = "found"
    RED_FLAG_CHECKED = "red_flag_checked"
    LINKED = "linked"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class ImportStep:
    """One `ImportStepKey`, with the short, already-checked strings a step may carry so the
    trace can say what it found — never a row, the way `app.search.ask.AskStep` carries only
    a count. `document_kind`/`document_date`/`facility` are the paper's own real fields
    (`FOUND`); `linked_kind` is `"medicine"` or `"visit"` and `linked_label` is the matched
    line's or visit's own name (`LINKED`)."""

    key: ImportStepKey
    document_kind: str | None = None
    facility: str | None = None
    document_date: str | None = None
    linked_kind: str | None = None
    linked_label: str | None = None


async def _linked_match(
    session: AsyncSession, *, context: KeyContext, extraction: Extraction
) -> ImportStep | None:
    """Whether this page's own fields name a medicine already on the record, or land on the
    same day as a visit already on the spine — read-only, from the profile's own rows alone
    (the signal-locality rule), never written anywhere. `None` when neither matches: the
    trace shows a link only when one is real (module docstring)."""
    named = next(
        (
            field.value
            for field in extraction.fields
            if (field.subject, field.attribute) == MEDICINE_NAME
        ),
        None,
    )
    if isinstance(named, str) and named.strip() and context.allows(Scope.MEDICINES):
        word = named.strip().lower()
        # The Health Graph's one reader (`app.state.health_context.active_medicines`, ADR
        # 0019 point 3; independent review of #331, follow-up 1): `status == ACTIVE`, not
        # `superseded_at IS NULL` alone — a paper must not link itself to a medicine he has
        # stopped or paused.
        lines = await active_medicines(session, context=context)
        for line in lines:
            if word in line.generic.lower() or (
                line.brand is not None and word in line.brand.lower()
            ):
                return ImportStep(
                    key=ImportStepKey.LINKED, linked_kind="medicine", linked_label=line.generic
                )
    if extraction.document_date is not None and context.allows(Scope.VISITS):
        tz = REGION_TZ[context.region]
        visits = await audited_read(session, Appointment, context, Scope.VISITS)
        for visit in visits:
            if as_utc(visit.scheduled_at).astimezone(tz).date() == extraction.document_date:
                return ImportStep(
                    key=ImportStepKey.LINKED,
                    linked_kind="visit",
                    linked_label=as_utc(visit.scheduled_at).astimezone(tz).date().isoformat(),
                )
    return None


async def review_artifact_stream(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    store: ObjectStore,
    extractor: Extractor,
    language: str,
    asked_as: DocumentKind | None = None,
    source: DocumentSource | None = None,
    registry: DrugRegistry | None = None,
) -> AsyncIterator[ImportStep | ReviewCard]:
    """`review_artifact`, streamed: an `ImportStep` the instant each real stage of turning a
    stored photo or PDF into a review card finishes, then the `ReviewCard` itself, last.
    `review_artifact` is this, drained — the relationship `recall`/`recall_stream` already
    have (`app.search.ask`) — so the plain route and the streamed one can never answer the
    pipeline two different ways.

    The order is the pipeline's own, unchanged from `review_artifact`: stored, then read,
    then what it found, then the red-flag check where one really runs, then a real link if
    one exists, then the card. Nothing here waits to look slower and nothing is skipped to
    look faster — a caller that never reads the generator (`review_artifact`) still does
    every step, in the same order, in the same unit of work. `registry` is what a pill
    photo's guess is matched against (`_capped_pill_fields`); omitted, a pill photo's fields
    still reach the card, unmatched and still capped."""
    context.require(Scope.RECORDS)
    artifact = await require_artifact(session, context=context, artifact_id=artifact_id)
    yield ImportStep(key=ImportStepKey.STORED)
    data = await store.get(artifact.storage_key)
    if extractor.external_processor is not None:
        # Written before the call, in the same unit of work as the card: a reach that sends
        # the artefact's bytes outside the region is recorded whether or not the call that
        # follows succeeds, distinct from the CARD/FIELD writes below so a reader of the
        # trail can tell an external model processor's read apart from a fixture's.
        await record(
            session,
            context=context,
            action=Action.SHARE,
            scope=Scope.RECORDS,
            target=EXTERNAL_MODEL_PROCESSOR,
            target_id=artifact.id,
            rows=1,
            shared_with_label=extractor.external_processor,
        )
    yield ImportStep(key=ImportStepKey.READING)
    extraction = await extractor.extract(
        data,
        artifact.content_type,
        Hints(language=language, region=context.region, expected=asked_as),
    )
    facility = next(
        (
            field.value
            for field in extraction.fields
            if field.attribute == "facility" and isinstance(field.value, str)
        ),
        None,
    )
    yield ImportStep(
        key=ImportStepKey.FOUND,
        document_kind=extraction.document_kind.value,
        facility=facility,
        document_date=None
        if extraction.document_date is None
        else extraction.document_date.isoformat(),
    )
    if extraction.document_kind in RED_FLAG_SCANNED_KINDS:
        # The red-flag path first, exactly like typed free text (`app.safety.red_flags`
        # module docstring): before the card is even written, not held for the person's
        # review. A lab report rarely carries a red word, but a facility's own remark
        # ("breathless at rest", "chest pain") is read the same way a transcript is — and so
        # is a pill photo's free-text guess or a pharmacy receipt's item name.
        await _red_flag_scan(session, context=context, artifact=artifact, extraction=extraction)
        yield ImportStep(key=ImportStepKey.RED_FLAG_CHECKED)
    linked = await _linked_match(session, context=context, extraction=extraction)
    if linked is not None:
        yield linked
    card = await card_from(
        session,
        context=context,
        artifact=artifact,
        extraction=extraction,
        asked_as=asked_as,
        source=source,
        registry=registry,
    )
    yield ImportStep(key=ImportStepKey.READY)
    yield card


@audited(Action.WRITE, Scope.RECORDS, CARD)
async def review_artifact(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    store: ObjectStore,
    extractor: Extractor,
    language: str,
    asked_as: DocumentKind | None = None,
    source: DocumentSource | None = None,
    registry: DrugRegistry | None = None,
) -> ReviewCard:
    """`review_artifact_stream`, drained: the card alone, for a caller that does not stream
    (the existing `POST /profiles/{id}/photos` and `/imports` routes, unchanged). Read a
    stored photo or PDF into a review card: one field per extracted statement, the
    extractor's confidence on each, the kind and date of the paper, and — from the drug the
    card names — whether the label rule guards it. `asked_as` goes to the extractor as the
    hint and onto the card; `source` is where an imported PDF came from. `registry` is what a
    pill photo's guess is matched against (`_capped_pill_fields`); omitted, a pill photo's
    fields still reach the card, unmatched and still capped."""
    card: ReviewCard | None = None
    async for event in review_artifact_stream(
        session,
        context=context,
        artifact_id=artifact_id,
        store=store,
        extractor=extractor,
        language=language,
        asked_as=asked_as,
        source=source,
        registry=registry,
    ):
        if isinstance(event, ReviewCard):
            card = event
    assert card is not None
    return card


async def review_photo(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    store: ObjectStore,
    extractor: Extractor,
    language: str,
    asked_as: DocumentKind | None = None,
    registry: DrugRegistry | None = None,
) -> ReviewCard:
    """Read a stored photo into a review card (`review_artifact`)."""
    return await review_artifact(
        session,
        context=context,
        artifact_id=artifact_id,
        store=store,
        extractor=extractor,
        language=language,
        asked_as=asked_as,
        registry=registry,
    )


def _capped_pill_fields(
    fields: Sequence[ExtractedField], registry: DrugRegistry | None
) -> list[ExtractedField]:
    """A pill's identity is never read off it, only guessed from what is visible — the
    imprint, the colour, the shape point at a product, but nothing about a loose pill proves
    it. The guess (`medicine`/`name`, `medicine`/`strength`) is matched against the licensed
    registry, when one is given: a match narrows the guess to the register's own generic and
    strength — a canonical answer, not the model's free text — and an unmatched guess is kept
    exactly as guessed. Either way, every `medicine` field is held at most at
    `PILL_MAX_CONFIDENCE`: a pill photo never earns the confidence a printed label can. The
    raw `pill` fields (imprint, colour, shape, score line) pass through unchanged — they are
    what was actually seen, not a guess."""
    name_field = next((f for f in fields if (f.subject, f.attribute) == MEDICINE_NAME), None)
    if registry is not None and name_field is not None and isinstance(name_field.value, str):
        strength_field = next(
            (f for f in fields if (f.subject, f.attribute) == MEDICINE_STRENGTH), None
        )
        strength = (
            strength_field.value
            if strength_field and isinstance(strength_field.value, str)
            else None
        )
        matches = registry.identify(LabelFields(generic=name_field.value, strength=strength))
        if not matches:
            matches = registry.identify(LabelFields(brand=name_field.value, strength=strength))
        # Only a match the register itself is confident of narrows the guess — the same
        # floor `app.medicines.service._one_product` holds a label to (#206): a wrong
        # strength or a bare high-risk name scores below it, and the guess is kept as
        # guessed rather than swapped for a product it likely is not.
        if matches and matches[0].confidence >= CONFIDENCE_THRESHOLD:
            best = matches[0]

            def _matched(field: ExtractedField) -> ExtractedField:
                if (field.subject, field.attribute) == MEDICINE_NAME:
                    return replace(field, value=best.generic)
                if (field.subject, field.attribute) == MEDICINE_STRENGTH:
                    return replace(field, value=best.strength, unit=None)
                return field

            fields = [_matched(field) for field in fields]
    return [
        replace(field, confidence=min(field.confidence, PILL_MAX_CONFIDENCE)).checked()
        if field.subject == "medicine"
        else field
        for field in fields
    ]


_INSURANCE_ESSENTIAL_ATTRIBUTE = re.compile(r"^(covers|excludes|benefit|claim_step)_\d+$")

_ADVICE_LANGUAGE_TOKENS: tuple[str, ...] = (
    # English
    "you are covered",
    "you're covered",
    "you will get",
    "you'll get",
    "you can claim",
    "entitled to",
    "should",
    "we recommend",
    "likely",
    "probably",
    # Malay
    "anda dilindungi",
    "anda akan mendapat",
    "anda boleh menuntut",
    "berhak",
    "sepatutnya",
    "kami mengesyorkan",
    "berkemungkinan",
    "mungkin",
    # Chinese
    "您已受保",
    "你已受保",
    "您将获得",
    "您可以索赔",
    "有权获得",
    "我们建议",
    "可能",
)
"""A policy essentials line that reads like Nura's own advice about his cover ("you are
covered up to S$150,000", "you should claim within 30 days") rather than the paper's own
printed words (independent review, package 12a fix round, item 5). A heuristic word list
across English, Malay and Chinese, since the paper itself may print in any of the three —
never a refusal, only a flag: a false positive only asks him to check the line again."""


_UNSEEN = re.compile(
    "[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f-\\x9f\\u00ad\\u061c\\u200b-\\u200f\\u202a-\\u202e\\u2066-\\u2069\\ufeff]"
)
"""What a reader never sees and every later step strips (`app.insurance.policy._clean`, the
web's own display path): matched on the raw value, "You a<ZWSP>re covered up to …" walked
past the tokens below and was then read by him intact (independent review, round 2, R-2)."""


def _carries_advice_language(text: str) -> bool:
    text = _UNSEEN.sub("", text)
    lowered = text.lower()
    return any(token in lowered or token in text for token in _ADVICE_LANGUAGE_TOKENS)


def _flagged_insurance_essentials(
    fields: Sequence[ExtractedField], document_kind: DocumentKind
) -> list[ExtractedField]:
    """Every `covers_N`/`excludes_N`/`benefit_N`/`claim_step_N` line that carries advice
    language is held below `CONFIDENCE_THRESHOLD` so the card's own `needs_confirm` catches it
    (`app.ingestion.models.ReviewField.needs_confirm`) — "Check this one", the same as any
    other field Nura is unsure of, never a silent pass-through and never a refusal: a false
    positive is still his own paper's words once he confirms it anyway. Only on an
    `insurance_policy` (`DocumentKind.INSURANCE_POLICY`); every other kind is returned
    unchanged."""
    if document_kind is not DocumentKind.INSURANCE_POLICY:
        return list(fields)
    return [
        replace(field, confidence=min(field.confidence, CONFIDENCE_THRESHOLD - 0.01))
        if _INSURANCE_ESSENTIAL_ATTRIBUTE.match(field.attribute)
        and isinstance(field.value, str)
        and _carries_advice_language(field.value)
        else field
        for field in fields
    ]


_HEADER_FIELD_KEYS = frozenset(
    {
        ("lab_report", "patient_name"),
        ("lab_report", "patient_id"),
        ("lab_report", "ordering_doctor"),
        ("lab_report", "facility"),
        ("lab_report", "lab"),
    }
)
"""Every field D-4b's semantic key leaves out: who the paper says it is about, not what it
says (`app.ingestion.whose_paper` already covers the identity fields on their own terms).
`person`-subject fields (birth year, sex) are excluded the same way, by subject alone."""


def _content_keys(fields: Sequence[ExtractedField]) -> frozenset[tuple[str, str]]:
    """The set of (subject, attribute) pairs a paper's own results are named under — D-4b's
    "the set of analytes/attributes" — everything except the identity header."""
    return frozenset(
        (field.subject, field.attribute)
        for field in fields
        if field.subject != "person" and (field.subject, field.attribute) not in _HEADER_FIELD_KEYS
    )


def _facility_of(fields: Sequence[ExtractedField] | Sequence[ReviewField]) -> str | None:
    found = next(
        (
            field.value
            for field in fields
            if field.subject == "lab_report" and field.attribute == "facility"
        ),
        None,
    )
    return found.strip().lower() if isinstance(found, str) else None


async def _semantic_duplicate_of(
    session: AsyncSession,
    *,
    context: KeyContext,
    extraction: Extraction,
    fields: Sequence[ExtractedField],
    exclude_artifact_id: uuid.UUID,
) -> ReviewCard | None:
    """D-4b: a card already on file, confirmed and not set aside, with the same document
    kind, the same printed date, the same facility (when both name one) and exactly the same
    set of results — the case a re-photographed paper makes, under a digest that will never
    match the first photo's own. `None` when nothing on file matches, including when this
    paper's own content set is empty (nothing to key on)."""
    if extraction.document_date is None:
        return None
    my_keys = _content_keys(fields)
    if not my_keys:
        return None
    my_facility = _facility_of(fields)
    candidates = await audited_read(
        session,
        ReviewCard,
        context,
        Scope.RECORDS,
        where=(
            ReviewCard.document_kind == extraction.document_kind,
            ReviewCard.document_date == extraction.document_date,
            ReviewCard.artifact_id != exclude_artifact_id,
            ReviewCard.confirmed_at.is_not(None),
            ReviewCard.discarded_at.is_(None),
            _cards_held_here(context),
        ),
    )
    for candidate in candidates:
        candidate_fields = await card_fields(session, context=context, card_id=candidate.id)
        candidate_facility = _facility_of(candidate_fields)
        if my_facility is not None and candidate_facility is not None and my_facility != candidate_facility:
            continue
        candidate_keys = frozenset(
            (field.subject, field.attribute)
            for field in candidate_fields
            if field.subject != "person" and (field.subject, field.attribute) not in _HEADER_FIELD_KEYS
        )
        if candidate_keys and candidate_keys == my_keys:
            return candidate
    return None


async def card_from(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact: Artifact,
    extraction: Extraction,
    asked_as: DocumentKind | None = None,
    source: DocumentSource | None = None,
    registry: DrugRegistry | None = None,
) -> ReviewCard:
    """Write the card and its fields for an extraction of this artefact. Every field is
    checked (`ExtractedField.checked`) before it is written: codes are codes, values short.
    A page no field may be taken from (`_nothing_to_take`) is a card with no fields.

    D-2 and D-4b, in order: the identity check runs first (`check_whose_paper`) — a mismatch
    is always the more urgent question, since it is the one a wrong answer could put another
    person's birth year and sex onto this profile. Only when identity matches (or there is
    nothing on either side to compare) does the semantic-duplicate check run at all. Either
    way, at most one question is ever pending — the card asks one plain thing, never two."""
    fields = [field.checked() for field in extraction.fields]
    if _nothing_to_take(extraction, asked_as):
        fields = []
    else:
        # The server-side normaliser (defect #3): a legacy `<analyte>_reference_range`
        # sibling — the shape every extractor wrote before a result carried its own `range` —
        # folded onto the result it describes and dropped, so an older extractor answer, and
        # a fixture already written that way, show a range that belongs to its result rather
        # than an unlabelled line of its own. A result already given its own `range` directly
        # is left exactly as it is.
        fields = list(fold_legacy_reference_ranges(fields))
    if extraction.document_kind is DocumentKind.PILL_PHOTO:
        fields = _capped_pill_fields(fields, registry)
    fields = _flagged_insurance_essentials(fields, extraction.document_kind)
    named = next(
        (field.value for field in fields if (field.subject, field.attribute) == MEDICINE_NAME),
        None,
    )

    pending_question: PendingQuestion | None = None
    question_payload: dict[str, Any] | None = None
    if fields:
        profile = await session.get(Profile, context.profile_id)
        identity = await check_whose_paper(
            session,
            context=context,
            fields=fields,
            document_date=extraction.document_date,
            profile_display_name=profile.display_name if profile is not None else "",
        )
        if identity.outcome is IdentityOutcome.MISMATCH:
            pending_question = PendingQuestion.WHOSE_PAPER
            # FIX BEFORE MERGE, the independent safety review: the paper's own printed name
            # (and, in the same spirit, its year of birth and sex) never leaves this
            # function's own return value from here on. `ReviewClarifyOut` names only which
            # *fields* disagreed (`mismatched`, the closed `IdentitySignal.kind` enum) — the
            # sentence built from it is Nura's own words, never a quote of what an
            # unconfirmed page happened to print (extracted text is hostile until confirmed;
            # a page printing an instruction in the name field must never become a headline).
            # The paper's own printed values stay visible only behind "See the paper itself",
            # the photo — never composed into text here.
            question_payload = {
                "mismatches": [{"kind": m.kind} for m in identity.mismatches],
            }
        else:
            duplicate = await _semantic_duplicate_of(
                session,
                context=context,
                extraction=extraction,
                fields=fields,
                exclude_artifact_id=artifact.id,
            )
            if duplicate is not None:
                pending_question = PendingQuestion.DUPLICATE_PAPER
                question_payload = {
                    "existing_card_id": str(duplicate.id),
                    # The day on his own clock, not UTC's (the independent safety review's
                    # FIX BEFORE MERGE): `ReviewClarifyOut.of` only ever keeps the first ten
                    # characters of this string as a date, and a naive UTC `.isoformat()`
                    # names the wrong day near midnight in Singapore or Malaysia.
                    "existing_added_on": day_of(duplicate.created_at, context.region).isoformat(),
                }

    card = await audited_write(
        session,
        ReviewCard,
        context,
        Scope.RECORDS,
        artifact_id=artifact.id,
        document_kind=extraction.document_kind,
        document_date=extraction.document_date,
        high_risk_class=high_risk_class(named if isinstance(named, str) else None),
        asked_as=asked_as,
        source=source,
        created_at=utcnow(),
        pending_question=pending_question,
        question_payload=question_payload,
    )
    for position, field in enumerate(fields):
        await audited_write(
            session,
            ReviewField,
            context,
            Scope.RECORDS,
            card_id=card.id,
            position=position,
            subject=field.subject,
            attribute=field.attribute,
            value=field.value,
            unit=field.unit,
            confidence=field.confidence,
            span=None if field.span is None else field.span.as_json(),
            range=None if field.range is None else field.range.as_json(),
            label_on_paper=field.label_on_paper,
            state=FieldState.PROPOSED,
        )
    return card


@audited(Action.READ, Scope.RECORDS, CARD)
async def list_review_cards(
    session: AsyncSession, *, context: KeyContext, open_only: bool = False
) -> Sequence[ReviewCard]:
    """The profile's cards, newest first; with `open_only`, the ones still waiting — a card
    set aside on its own question is resolved, not waiting, so it is excluded from
    `open_only` the same way a confirmed one already is (B2)."""
    where: list[Any] = [_cards_held_here(context)]
    if open_only:
        where.append(ReviewCard.confirmed_at.is_(None))
        where.append(ReviewCard.discarded_at.is_(None))
    found = await audited_read(session, ReviewCard, context, Scope.RECORDS, where=where)
    return sorted(found, key=lambda card: (as_utc(card.created_at), str(card.id)), reverse=True)


@audited(Action.READ, Scope.RECORDS, CARD)
async def require_review_card(
    session: AsyncSession, *, context: KeyContext, card_id: uuid.UUID
) -> ReviewCard:
    found = await audited_read(
        session,
        ReviewCard,
        context,
        Scope.RECORDS,
        where=(ReviewCard.id == card_id, _cards_held_here(context)),
    )
    if not found:
        raise NoSuchReviewCard(f"no review card {card_id} on profile {context.profile_id}")
    return found[0]


@audited(Action.READ, Scope.RECORDS, CARD)
async def card_for_artifact(
    session: AsyncSession, *, context: KeyContext, artifact_id: uuid.UUID
) -> ReviewCard | None:
    """The one card an artefact was read into, if it was (D-4a): every artefact gets at most
    one card (`card_from` runs once per upload), so this is the card a duplicate-bytes upload
    is shown instead of reading anything again (`app.channels.api.capture`).

    FOLLOW-UP, the independent safety review: the "at most one card" invariant this
    docstring states is not actually kept everywhere — `POST /readings/photo` and the
    WhatsApp photo branch can each mint a second card for the same artefact (documented, not
    fixed here, in the PR body). Without an explicit order this `limit=1` picked whichever
    row the database happened to return first — silently a different card on a re-run, on a
    different engine, or after an unrelated change to how SQLite orders ties. Ordered by
    `created_at` so a duplicate-bytes upload is shown consistently the *earliest* card on
    file, the same "earliest survives" rule migration `0055`'s own collapse already keeps."""
    found = await audited_read(
        session,
        ReviewCard,
        context,
        Scope.RECORDS,
        where=(ReviewCard.artifact_id == artifact_id, _cards_held_here(context)),
        order_by=(ReviewCard.created_at.asc(),),
        limit=1,
    )
    return found[0] if found else None


@audited(Action.READ, Scope.RECORDS, CARD)
async def card_artifact(
    session: AsyncSession, *, context: KeyContext, store: ObjectStore, card_id: uuid.UUID
) -> tuple[bytes, str]:
    """The bytes of the paper behind one review card, and its content type — "See the paper
    itself" on a paper he has already checked, reopened read-only (E02-07 library part B #3).
    Read through the record's own door twice over: the card must be his
    (`require_review_card`), and so must the artefact it names (`require_artifact`, the same
    door `app.family.photos.photo_content` reads a shared photo through). Nothing new is
    stored or scoped here — a card's artefact was always his to read under the record's
    scope; this is the one small additive route the library needed, to read it back."""
    guard_region(held_in=store.region, asked_from=context.region)
    card = await require_review_card(session, context=context, card_id=card_id)
    artifact = await require_artifact(session, context=context, artifact_id=card.artifact_id)
    data = await store.get(artifact.storage_key)
    if sha256_of(data) != artifact.sha256:
        raise NoSuchObject("the bytes under that key are not the paper")
    return data, artifact.content_type


@audited(Action.READ, Scope.RECORDS, FIELD)
async def card_fields(
    session: AsyncSession, *, context: KeyContext, card_id: uuid.UUID
) -> Sequence[ReviewField]:
    """The fields of one card, in the order they were read off the page."""
    found = await audited_read(
        session, ReviewField, context, Scope.RECORDS, where=(ReviewField.card_id == card_id,)
    )
    return sorted(found, key=lambda field: field.position)


@audited(Action.WRITE, Scope.RECORDS, FIELD)
async def type_field(
    session: AsyncSession,
    *,
    context: KeyContext,
    card_id: uuid.UUID,
    field_id: uuid.UUID,
    value: Any,
) -> ReviewField:
    """Type in the value of one field on an open card: a field Nura could not read, or one
    it read wrong. Anyone holding the record may, before the card is confirmed — a daughter
    typing what her father's slip says — and the field names who did. The value read stays
    beside it; nothing is a fact until the card's yes, which binds to the typed value and to
    who typed it. Typing again replaces the typed value, and names the new typist."""
    card = await require_review_card(session, context=context, card_id=card_id)
    if card.discarded_at is not None:
        raise CardSetAside(f"review card {card_id} was set aside at {card.discarded_at}")
    if not card.is_open:
        raise AlreadyConfirmed(f"review card {card_id} was confirmed at {card.confirmed_at}")
    fields = await card_fields(session, context=context, card_id=card_id)
    field = next((one for one in fields if one.id == field_id), None)
    if field is None:
        raise NoSuchReviewField(f"field {field_id} is not on this card")
    typed = check_value(value)
    session.info[REVIEW_IN_PROGRESS] = card.id
    try:
        field.corrected_value = typed
        field.corrected_by_person_id = context.person_id
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.RECORDS,
            target=FIELD,
            target_id=field.id,
            rows=1,
        )
    finally:
        session.info.pop(REVIEW_IN_PROGRESS, None)
    return field


def _decided(
    fields: Sequence[ReviewField], decisions: Sequence[Decision], confirmer: uuid.UUID
) -> list[DecidedField]:
    """Every field with exactly one decision on it, or a refusal saying which rule broke.

    The value kept is the confirmer's correction where he made one; otherwise a value typed
    in before the yes, naming who typed it; otherwise what was read. A field Nura could not
    read and nobody typed is never confirmed as read (`UnreadableField`)."""
    by_id = {field.id: field for field in fields}
    said: dict[uuid.UUID, Decision] = {}
    for decision in decisions:
        if decision.field_id not in by_id:
            raise NoSuchReviewField(f"field {decision.field_id} is not on this card")
        if decision.field_id in said:
            raise NotEveryFieldDecided(f"field {decision.field_id} was decided twice")
        if decision.decision not in DECISIONS:
            raise NotADecision("a field is confirmed, corrected or rejected")
        if (decision.decision is FieldState.CORRECTED) != (decision.corrected_value is not None):
            raise NotADecision("a correction says what to, and nothing else does")
        said[decision.field_id] = decision
    missing = set(by_id) - set(said)
    if missing:
        raise NotEveryFieldDecided(f"{len(missing)} field(s) have no decision")
    decided = []
    for field in fields:
        decision = said[field.id]
        typed = field.corrected_value is not None
        corrected_by: uuid.UUID | None = None
        if decision.decision is FieldState.CORRECTED:
            value, corrected_by = decision.corrected_value, confirmer
        elif decision.decision is FieldState.CONFIRMED and typed:
            value, corrected_by = field.corrected_value, field.corrected_by_person_id
        elif decision.decision is FieldState.CONFIRMED and field.unreadable:
            raise UnreadableField(f"field {field.id} could not be read and was not typed in")
        else:
            value = field.value
        decided.append(
            DecidedField(
                field_id=field.id,
                subject=field.subject,
                attribute=field.attribute,
                value=value,
                unit=field.unit,
                decision=decision.decision.value,
                corrected_by=corrected_by,
            )
        )
    return decided


@audited(Action.READ, Scope.RECORDS, CARD)
async def review_draft_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    card_id: uuid.UUID,
    decisions: Sequence[Decision],
    episode_id: uuid.UUID | None = None,
) -> ReviewDraft:
    """What the person is saying yes to: this card, its photo, every field with his
    decision — and, when he named one, the open episode the card goes into (E03-02). The
    surface mints the confirmation over this; the confirm recomputes it."""
    card = await require_review_card(session, context=context, card_id=card_id)
    if card.discarded_at is not None:
        raise CardSetAside(f"review card {card_id} was set aside at {card.discarded_at}")
    if not card.is_open:
        raise AlreadyConfirmed(f"review card {card_id} was confirmed at {card.confirmed_at}")
    fields = await card_fields(session, context=context, card_id=card_id)
    return ReviewDraft(
        card_id=card.id,
        artifact_id=card.artifact_id,
        fields=tuple(_decided(fields, decisions, context.person_id)),
        episode_id=episode_id,
    )


def _opens_at(card: ReviewCard, artifact: Artifact, context: KeyContext) -> datetime:
    """When the facts start holding: the day on the paper, on the patient's clock, or the
    moment the photo was taken when the paper has no date."""
    if card.document_date is None:
        return as_utc(artifact.captured_at)
    midnight = datetime.combine(card.document_date, time.min, tzinfo=REGION_TZ[context.region])
    return midnight.astimezone(UTC)


async def _write_fact_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    card: ReviewCard,
    subject: str,
    attribute: str,
    value: Any,
    unit: str | None,
    event_id: uuid.UUID | None,
    valid_from: datetime,
    episode_id: uuid.UUID | None = None,
) -> Fact:
    draft = FactDraft(
        subject=subject,
        attribute=attribute,
        value=value,
        unit=unit,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=card.artifact_id,
        event_id=event_id,
        episode_id=episode_id,
        supersedes_id=None,
    )
    yes = await confirm(session, context, draft)
    return await assert_fact(
        session,
        context=context,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        unit=draft.unit,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        artifact_id=draft.artifact_id,
        event_id=draft.event_id,
        episode_id=draft.episode_id,
        valid_from=valid_from,
    )


@audited(Action.WRITE, Scope.RECORDS, CARD)
async def confirm_review_card(
    session: AsyncSession,
    *,
    context: KeyContext,
    card_id: uuid.UUID,
    decisions: Sequence[Decision],
    confirmation_id: uuid.UUID,
    episode_id: uuid.UUID | None = None,
    registry: DrugRegistry | None = None,
) -> tuple[ReviewCard, Sequence[ReviewField], Sequence[Fact]]:
    """Close the card on the person's yes and write the facts it decided.

    `registry` is what a pharmacy receipt's item lines are matched against — the same
    register a pill photo's guess is matched against at read time — so a line naming a
    medicine or supplement already on his list also writes a cost entry
    (`_write_receipt`); omitted, every line still writes as a plain paper fact.

    The yes must be for exactly these decisions on exactly this card (`ReviewDraft`); a
    decision changed since is `NotWhatWasConfirmed`. Then, field by field: a confirmed or
    corrected field becomes a Fact — the photo as provenance, CONFIRMED_BY_PERSON naming
    the confirmer, the unit, valid from the date on the paper — and the field names it; a
    rejected field is marked and writes nothing. A rule under the store (the label rule for
    a high-risk dose) that refuses one fact refuses the whole card: the channel rolls the
    unit back, yes included. The card closes last, naming who confirmed it and when.

    A machine's screen is written as one READING event at the time on the screen and the
    facts of the reading resting on it (`_write_reading`); a hospital letter or a clinic slip
    as the event it records, on the date on the paper, which its facts name beside the page.
    A value typed in before the yes, or corrected in it, leaves the field CORRECTED and
    naming who typed it.

    With `episode_id` the yes was for the card going into that open episode: the event and
    each fact name the episode, and the photo hangs off it (`attach_from_ingestion`, E03-02)
    under the same yes — the automatic way a paper joins the concern it belongs to.
    """
    draft = await review_draft_for(
        session, context=context, card_id=card_id, decisions=decisions, episode_id=episode_id
    )
    if episode_id is not None:
        await require_open_episode(session, context=context, episode_id=episode_id)
    card = await require_review_card(session, context=context, card_id=card_id)
    # D-2/D-4b: nothing is written from a card that asked a question and has not been
    # answered — not a fact, not a `person.*` field, ever (`ReviewCard.awaiting_answer`).
    # Checked before the yes is even consumed, so a stale confirmation minted before the
    # question was asked is refused the same way a fresh one would be.
    if card.awaiting_answer:
        raise QuestionUnanswered(f"review card {card_id} is waiting on {card.pending_question}")
    if card.discarded_at is not None:
        raise CardSetAside(f"review card {card_id} was set aside and cannot be confirmed")
    artifact = await require_artifact(session, context=context, artifact_id=card.artifact_id)
    fields = await card_fields(session, context=context, card_id=card_id)
    yes = await consume_confirmation(session, context, confirmation_id, draft)

    moment = utcnow()
    by_id = {decided.field_id: decided for decided in draft.fields}
    session.info[REVIEW_IN_PROGRESS] = card.id
    try:
        if card.document_kind is DocumentKind.DEVICE_SCREEN:
            fact_of = await _write_reading(
                session,
                context=context,
                card=card,
                artifact=artifact,
                draft=draft,
                now=moment,
                episode_id=episode_id,
            )
        else:
            fact_of = await _write_paper(
                session,
                context=context,
                card=card,
                artifact=artifact,
                draft=draft,
                episode_id=episode_id,
                registry=registry,
            )
        written = list(dict.fromkeys(fact_of.values()))
        for field in fields:
            decided = by_id[field.id]
            said = FieldState(decided.decision)
            kept = said is not FieldState.REJECTED
            fact = fact_of.get(field.id)
            if fact is not None:
                field.fact_id = fact.id
            if kept and decided.corrected_by is not None:
                field.corrected_value = decided.value
                field.corrected_by_person_id = decided.corrected_by
            field.state = FieldState.CORRECTED if kept and decided.corrected_by else said
            field.decided_at = moment
            await session.flush()
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=Scope.RECORDS,
                target=FIELD,
                target_id=field.id,
                rows=1,
            )
            # D3 (ADR 0019 point 7): a "No" (`REJECTED`) or a "Fix" (kept, but corrected) on a
            # field the extractor proposed is a rejected or corrected AI conclusion, recorded
            # the same way a dropped Ask line is — never the extracted or corrected value
            # itself, only the closed response kind and which field.
            if field.state is FieldState.REJECTED:
                await record_dropped_conclusion(
                    session,
                    context=context,
                    response_kind=ConclusionResponseKind.USER_NO,
                    target=FIELD,
                    target_id=field.id,
                    scope=Scope.RECORDS,
                )
            elif field.state is FieldState.CORRECTED:
                await record_dropped_conclusion(
                    session,
                    context=context,
                    response_kind=ConclusionResponseKind.USER_FIX,
                    target=FIELD,
                    target_id=field.id,
                    scope=Scope.RECORDS,
                )
        card.confirmed_at = moment
        card.confirmed_by_person_id = yes.person_id
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.RECORDS,
            target=CARD,
            target_id=card.id,
            rows=1,
        )
    finally:
        session.info.pop(REVIEW_IN_PROGRESS, None)
    if episode_id is not None:
        await attach_from_ingestion(
            session,
            context=context,
            artifact_id=card.artifact_id,
            episode_id=episode_id,
            by_person_id=yes.person_id,
        )
    return card, fields, written


WHOSE_PAPER_ANSWERS = frozenset({"mine", "someone_elses"})
"""D-2's two answers that reach the backend at all. "I'm not sure" is the third chip the
reading screen offers, and it never calls this door — it leaves the card exactly as it is,
pending, which is what "keeps the card open" means (the owner requirement's own words)."""

DUPLICATE_PAPER_ANSWERS = frozenset({"same", "different"})


@audited(Action.WRITE, Scope.RECORDS, CARD)
async def answer_review_card_question(
    session: AsyncSession, *, context: KeyContext, card_id: uuid.UUID, value: str
) -> ReviewCard:
    """Answer a card's one pending question (D-2, D-4b).

    `WHOSE_PAPER`: `"mine"` records the answer and lets `confirm_review_card` proceed —
    including the `person.birth_year`/`person.sex` facts the audit found being written
    unchecked; `"someone_elses"` sets the card aside (`discarded_at`) — its paper never
    reaches the record, calmly, and for good (`CardSetAside` on any later confirm attempt).
    There is no backend call for "I'm not sure" (see `WHOSE_PAPER_ANSWERS`).

    `DUPLICATE_PAPER`: `"same"` sets the card aside the same way — it is not a new paper;
    `"different"` records the answer and lets confirmation proceed as an ordinary new one.
    """
    card = await require_review_card(session, context=context, card_id=card_id)
    if card.pending_question is None:
        raise NoQuestionToAnswer(f"review card {card_id} has no pending question")
    if card.question_answer is not None:
        raise QuestionAlreadyAnswered(f"review card {card_id}'s question was already answered")
    valid = (
        WHOSE_PAPER_ANSWERS
        if card.pending_question is PendingQuestion.WHOSE_PAPER
        else DUPLICATE_PAPER_ANSWERS
    )
    if value not in valid:
        raise NotAnAnswer(f"{value!r} is not a choice on this question")
    moment = utcnow()
    session.info[REVIEW_IN_PROGRESS] = card.id
    try:
        card.question_answer = value
        card.question_answered_at = moment
        card.question_answered_by_person_id = context.person_id
        if value in {"someone_elses", "same"}:
            card.discarded_at = moment
        await session.flush()
        # FIX BEFORE MERGE, the independent safety review: `@audited` above only writes a
        # line on a refusal, so the decision this whole package exists to make safe used to
        # leave no trail on success at all. `value` is already checked against the closed
        # set above (`NotAnAnswer` otherwise) — never the paper's own printed name, which
        # this table never held in the first place.
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.RECORDS,
            target=CARD,
            target_id=card.id,
            rows=1,
            answered_with=value,
        )
    finally:
        session.info.pop(REVIEW_IN_PROGRESS, None)
    return card


async def close_card_for_artifact(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    person_id: uuid.UUID,
    moment: datetime,
) -> None:
    """Close whatever open review card this artefact still has — for a caller that writes a
    fact from an artefact's own yes without going through `confirm_review_card` itself. The
    add-a-medicine screen is exactly this (redesign package 11): it runs its own reconcile
    pipeline end to end, past its own confirmation card, and never calls
    `confirm_review_card` — so, without this, a label read by photo through that screen kept
    its card open forever, and `app.search.ask.waiting_papers` (and the ordinary papers
    screen behind it) kept asking him to check something he had already said yes to
    (review defect #9).

    Only a card whose every field is the medicine's own: a paper that says anything else (a
    pharmacy's name, a receipt's priced lines) stays open, so nothing on it is lost.

    A no-op when the artefact never had a card at all (a typed entry keeps its own artefact
    but is never read by an extractor, so `card_from` was never called for it) or its card is
    already closed. Silent, not a refusal, when this key lacks `Scope.RECORDS` to see cards —
    a `Scope.MEDICINES`-only key can still write the line; it simply cannot be the one to
    close a card that belongs to the record scope its key was never granted, the same shape
    `app.medicines.service._artifact_kinds_for` already holds for reading a card's kind."""
    try:
        found = await audited_read(
            session,
            ReviewCard,
            context,
            Scope.RECORDS,
            where=(ReviewCard.artifact_id == artifact_id, _cards_held_here(context)),
        )
    except OutOfScope:
        return
    for card in found:
        if card.confirmed_at is not None or card.discarded_at is not None:
            continue
        if card.awaiting_answer:
            # This artefact's card is asking its own question (D-2/D-4b) — the same rule
            # `confirm_review_card` holds applies to this side door too: nothing on the card
            # is treated as settled, medicine fact included, until it is answered. The card
            # stays open; the add-a-medicine screen's own write already went through
            # (independent of this card), so nothing is lost either way.
            continue
        # Only a card this add accounted for in full. A closed card leaves the papers screen
        # for good and none of its other fields is ever written: a pharmacy's name and phone
        # on a label, every priced line of a receipt whose file he chose on the add screen
        # (independent review, round 2, blocker 2). Such a card stays open — he is asked to
        # check that paper the ordinary way, and nothing on it is lost.
        fields = await audited_read(
            session, ReviewField, context, Scope.RECORDS, where=(ReviewField.card_id == card.id,)
        )
        if any(field.subject != MEDICINE_NAME[0] for field in fields):
            continue
        # `ReviewCard` is a frozen row outside its own service (`app.ingestion.models.frozen`,
        # `_review_is_in_progress`): the same marker `confirm_review_card` sets before it
        # closes a card is required here too, or the flush below raises `ImmutableRow`.
        session.info[REVIEW_IN_PROGRESS] = card.id
        try:
            card.confirmed_at = moment
            card.confirmed_by_person_id = person_id
            await session.flush()
        finally:
            session.info.pop(REVIEW_IN_PROGRESS, None)
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.RECORDS,
            target=CARD,
            target_id=card.id,
            rows=1,
        )


async def pill_photo_artifacts_of(
    session: AsyncSession, *, context: KeyContext, artifact_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of these artefacts' own review cards say `DocumentKind.PILL_PHOTO` — never any
    other column, only that one enum (BLOCKER 1, independent safety review #1's no-migration
    fix: `app.medicines.service.source_line`, for a line a medicines-only key can already see
    citing its own `source_artifact_id`; review defect #2c, a loose tablet's own guess is
    never said as "the label he kept").

    A raw, profile-scoped, id-restricted read, the same shape as
    `app.safety.high_risk.is_pill_photo` beside it in spirit (a narrow kind check that needs
    no key) and `app.memory.episodic.artifact_kinds_of` in reason: `ReviewCard` is defined in
    this module, which is where a read like this belongs, and the caller writes its own
    audit line under whichever door it actually read this through, since only the caller
    knows which one that was."""
    if not artifact_ids:
        return set()
    found = (
        await session.execute(
            select(ReviewCard.artifact_id).where(
                ReviewCard.artifact_id.in_(list(artifact_ids)),
                ReviewCard.profile_id == context.profile_id,
                ReviewCard.document_kind == DocumentKind.PILL_PHOTO,
            )
        )
    ).scalars().all()
    return set(found)


async def _write_lab_readings(
    session: AsyncSession,
    *,
    context: KeyContext,
    card: ReviewCard,
    artifact: Artifact,
    reading_fields: Sequence[DecidedField],
    opens: datetime,
    episode_id: uuid.UUID | None,
) -> dict[uuid.UUID, Fact]:
    """A lab report's known-unit fields (`_lab_reading_split`), written as reading facts on
    one READING event at the date on the paper — the same fact shape a device's screen
    writes (`app.ingestion.readings`), so a lab's own blood pressure or blood sugar line
    joins the same trend a typed or a device reading does."""
    fact_of: dict[uuid.UUID, Fact] = {}
    event = await record_event(
        session,
        context=context,
        kind=EventKind.READING,
        occurred_at=opens,
        label="reading",
        artifact_id=artifact.id,
        episode_id=episode_id,
    )
    # Keyed by (subject, attribute), exactly as `_lab_reading_split` found the pair. Keyed by
    # subject alone, both numbers of a blood pressure collapsed onto "blood_pressure", the pair
    # was never found, and the loop below raised `KeyError: ('blood_pressure', 'systolic')` —
    # confirming any lab report that prints a blood pressure was a 500 (#303 final check, NEW-4;
    # no lab fixture carried one, so nothing caught it).
    by_code = {(field.subject, field.attribute): field for field in reading_fields}
    systolic, diastolic = by_code.get(SYSTOLIC), by_code.get(DIASTOLIC)
    if systolic is not None and diastolic is not None:
        fact = await _write_fact_for(
            session,
            context=context,
            card=card,
            subject="blood_pressure",
            attribute=READING,
            value={"systolic": systolic.value, "diastolic": diastolic.value},
            unit="mmHg",
            event_id=event.id,
            valid_from=opens,
            episode_id=episode_id,
        )
        fact_of[systolic.field_id] = fact
        fact_of[diastolic.field_id] = fact
    for field in reading_fields:
        if field.field_id in fact_of:
            continue
        measure = _LAB_READING_CODES[(field.subject, field.attribute)]
        fact = await _write_fact_for(
            session,
            context=context,
            card=card,
            subject=measure.subject,
            attribute=READING,
            value={measure.key: field.value},
            unit=measure.unit,
            event_id=event.id,
            valid_from=opens,
            episode_id=episode_id,
        )
        fact_of[field.field_id] = fact
    return fact_of


async def _his_generics(session: AsyncSession, *, context: KeyContext) -> frozenset[str]:
    """The generics on his active list now — what a pharmacy receipt line's match is checked
    against (`_write_receipt`): a receipt names a real product, but it becomes a cost entry
    only for something he is actually recorded as taking, never a new medicine of its own
    (a receipt is never how a medicine is added; the medicines module's own flow is)."""
    found = await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(
            MedicationLine.superseded_at.is_(None),
            MedicationLine.status == LineStatus.ACTIVE,
        ),
    )
    return frozenset(line.generic for line in found)


def _receipt_currency(kept: Sequence[DecidedField]) -> str | None:
    for decided in kept:
        if (
            decided.subject == "receipt"
            and decided.attribute == "currency"
            and isinstance(decided.value, str)
        ):
            return decided.value
    return None


def _cents(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return round(value * 100)


async def _write_receipt(
    session: AsyncSession,
    *,
    context: KeyContext,
    card: ReviewCard,
    kept: Sequence[DecidedField],
    opens: datetime,
    episode_id: uuid.UUID | None,
    registry: DrugRegistry | None,
) -> dict[uuid.UUID, Fact]:
    """A pharmacy receipt's kept fields: every one a plain paper fact, exactly as printed
    (the receipt's own words are never replaced) — and, for an item line whose name matches a
    medicine or supplement already on his list, one more fact besides:
    `medicine_cost`/<generic>, the line's price, for the ledger to sum
    (`app.insurance.ledger.medicine_monthly_costs`). A line that matches nothing on his list,
    or a receipt with no registry to match against, stays a plain fact only — never held back
    for that (#pill-receipt, "unmatched items stay as paper facts")."""
    fact_of: dict[uuid.UUID, Fact] = {}
    for decided in kept:
        fact_of[decided.field_id] = await _write_fact_for(
            session,
            context=context,
            card=card,
            subject=decided.subject,
            attribute=decided.attribute,
            value=decided.value,
            unit=decided.unit,
            event_id=None,
            valid_from=opens,
            episode_id=episode_id,
        )
    if registry is None:
        return fact_of
    currency = _receipt_currency(kept)
    his_generics = await _his_generics(session, context=context)
    by_item: dict[str, dict[str, DecidedField]] = {}
    for decided in kept:
        if ITEM_SUBJECT.match(decided.subject):
            by_item.setdefault(decided.subject, {})[decided.attribute] = decided
    for item in by_item.values():
        name = item.get("name")
        if name is None or not isinstance(name.value, str):
            continue
        matches = registry.identify(LabelFields(generic=name.value)) or registry.identify(
            LabelFields(brand=name.value)
        )
        matched = next(
            (
                m
                for m in matches
                if m.generic in his_generics and m.confidence >= CONFIDENCE_THRESHOLD
            ),
            None,
        )
        if matched is None:
            continue
        quantity_field = item.get("quantity")
        quantity = (
            quantity_field.value
            if quantity_field is not None and isinstance(quantity_field.value, int | float)
            else None
        )
        total_field = item.get("total")
        total_cents = _cents(total_field.value) if total_field is not None else None
        if total_cents is None:
            unit_price = item.get("unit_price")
            unit_price_cents = _cents(unit_price.value) if unit_price is not None else None
            if unit_price_cents is None:
                continue
            count = quantity if quantity is not None else 1
            total_cents = round(unit_price_cents * count)
        cost_fact = await _write_fact_for(
            session,
            context=context,
            card=card,
            subject=MEDICINE_COST_SUBJECT,
            attribute=matched.generic,
            value={"total_cents": total_cents, "item": name.value, "quantity": quantity},
            unit=currency,
            event_id=None,
            valid_from=opens,
            episode_id=episode_id,
        )
        # Kept apart from the field->fact_id map on purpose: the cost fact is derived from a
        # whole line, not one field, so no single field's `fact_id` is overwritten to point
        # at it — every field still names the plain fact it actually became. The cost fact
        # itself still reaches `written` below (and the trail), under a key of its own.
        fact_of[uuid.uuid4()] = cost_fact
    return fact_of


async def _write_paper(
    session: AsyncSession,
    *,
    context: KeyContext,
    card: ReviewCard,
    artifact: Artifact,
    draft: ReviewDraft,
    episode_id: uuid.UUID | None = None,
    registry: DrugRegistry | None = None,
) -> dict[uuid.UUID, Fact]:
    """One fact per kept field, valid from the date on the paper; for a paper that records a
    moment (`DOCUMENT_EVENTS`), the event first, on that date, and every fact names it. A lab
    report is its own case: its known-unit rows become reading facts on one READING event
    (`_write_lab_readings`), everything else on it a plain fact exactly like any other kind
    (a header field, a reference range, an insurance line) — the same fallback below. A
    pharmacy receipt is its own case too (`_write_receipt`)."""
    opens = _opens_at(card, artifact, context)
    kept = [decided for decided in draft.fields if decided.decision != FieldState.REJECTED]
    if card.document_kind is DocumentKind.PHARMACY_RECEIPT:
        return await _write_receipt(
            session,
            context=context,
            card=card,
            kept=kept,
            opens=opens,
            episode_id=episode_id,
            registry=registry,
        )
    if card.document_kind is DocumentKind.LAB_REPORT:
        reading_fields, plain_fields = _lab_reading_split(kept)
        lab_fact_of: dict[uuid.UUID, Fact] = {}
        if reading_fields:
            lab_fact_of.update(
                await _write_lab_readings(
                    session,
                    context=context,
                    card=card,
                    artifact=artifact,
                    reading_fields=reading_fields,
                    opens=opens,
                    episode_id=episode_id,
                )
            )
        for decided in plain_fields:
            lab_fact_of[decided.field_id] = await _write_fact_for(
                session,
                context=context,
                card=card,
                subject=decided.subject,
                attribute=decided.attribute,
                value=decided.value,
                unit=decided.unit,
                event_id=None,
                valid_from=opens,
                episode_id=episode_id,
            )
        return lab_fact_of
    event_id: uuid.UUID | None = None
    shape = DOCUMENT_EVENTS.get(card.document_kind)
    if shape is not None and kept:
        kind, label = shape
        event = await record_event(
            session,
            context=context,
            kind=kind,
            occurred_at=opens,
            label=label,
            artifact_id=artifact.id,
            episode_id=episode_id,
        )
        event_id = event.id
    fact_of: dict[uuid.UUID, Fact] = {}
    for decided in kept:
        fact_of[decided.field_id] = await _write_fact_for(
            session,
            context=context,
            card=card,
            subject=decided.subject,
            attribute=decided.attribute,
            value=decided.value,
            unit=decided.unit,
            event_id=event_id,
            valid_from=opens,
            episode_id=episode_id,
        )
    return fact_of


async def _write_reading(
    session: AsyncSession,
    *,
    context: KeyContext,
    card: ReviewCard,
    artifact: Artifact,
    draft: ReviewDraft,
    now: datetime,
    episode_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, Fact]:
    """A machine's screen: one READING event at the time on the screen — or when the photo
    was taken, if that was rejected — and the facts of the reading, each naming the event
    and the photo, in the shape a typed reading takes. Every number rejected writes nothing."""
    reading = reading_from(draft.fields, tz=REGION_TZ[context.region], now=now)
    if not reading.facts:
        return {}
    taken_at = reading.taken_at or as_utc(artifact.captured_at)
    event = await record_event(
        session,
        context=context,
        kind=EventKind.READING,
        occurred_at=taken_at,
        label=reading.label,
        artifact_id=artifact.id,
        episode_id=episode_id,
    )
    fact_of: dict[uuid.UUID, Fact] = {}
    for measured in reading.facts:
        fact = await _write_fact_for(
            session,
            context=context,
            card=card,
            subject=measured.subject,
            attribute=measured.attribute,
            value=measured.value,
            unit=measured.unit,
            event_id=event.id,
            valid_from=taken_at,
            episode_id=episode_id,
        )
        for field_id in measured.field_ids:
            fact_of[field_id] = fact
    return fact_of
