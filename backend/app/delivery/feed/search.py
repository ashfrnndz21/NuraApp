"""Self-search: a job the engine runs for him, against the allowlist, through the two ports.

A job is made from a gap State shows — a medicine with no explainer, a condition with none —
or by the owner or his chief by hand. It names the sources it may read, every one of them
usable at the time, and `run_job` reads no others. What comes back goes through the
compressor; what the compressor returns is checked — cited, in his language, not a change
of treatment — and only then becomes a learning card through `items.create_item`, which
checks the source and the words again. A finding that would change treatment is not lost:
it becomes a `QUESTION` item for the memo, never for his feed.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.db import utcnow
from app.delivery.feed.compress import Compressor, Found, Searcher, changes_treatment
from app.delivery.feed.items import NotPlainWords, Why, create_item
from app.delivery.feed.models import (
    CardFormat,
    CardType,
    DeliverTo,
    FeedItem,
    JobKind,
    JobStatus,
    SearchJob,
)
from app.delivery.feed.sources import (
    SourceNotAllowlisted,
    require_manager,
    require_usable_source,
    usable_sources,
)
from app.delivery.strings import YOUR_DOCTOR, Lines, language_for, learning_lines
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.state.models import Dimension
from app.state.service import StateView

JOB_TARGET = SearchJob.__tablename__
LEARNING_LIFETIME = timedelta(days=90)
"""Evergreen: a learning card stays in the supply for a season, then is made again if the
gap is still there."""


class NoSuchSearchJob(Refusal):
    """No search job by that id on this profile."""


class NoTerms(Refusal):
    """A search job searches for something."""


@dataclass(frozen=True, slots=True)
class Engine:
    """The ports the feed composes from, as one deployment has them: the searcher and the
    compressor (fixtures here; real adapters later), and the licensed drug registry
    (`app.drugs`) the medicines module reads a line's plain name and count through."""

    searcher: Searcher
    compressor: Compressor
    registry: DrugRegistry


@audited(Action.WRITE, Scope.RECORDS, JOB_TARGET)
async def create_job(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: JobKind,
    terms: Sequence[str],
    reason: Mapping[str, Any],
    source_ids: Sequence[uuid.UUID] | None = None,
    cadence: str = "on_change",
) -> SearchJob:
    """Queue a self-search for this profile, scoped to usable sources only.

    The owner's and his chief's to make (`NotTheirsToManage`). Named sources are each
    checked against the allowlist (`SourceNotAllowlisted`); none named means every usable
    source in the profile's region.
    """
    await require_manager(session, context=context, target=JOB_TARGET)
    cleaned = [term.strip().lower() for term in terms if term.strip()]
    if not cleaned:
        raise NoTerms("a search job needs at least one term")
    sources = await usable_sources(session, region=context.region, source_ids=source_ids)
    return await audited_write(
        session,
        SearchJob,
        context,
        Scope.RECORDS,
        kind=kind,
        terms=cleaned,
        source_ids=[str(source.id) for source in sources],
        cadence=cadence,
        reason=dict(reason),
        status=JobStatus.QUEUED,
        results={},
        enabled=True,
        created_by_person_id=context.person_id,
        created_at=utcnow(),
    )


@audited(Action.READ, Scope.RECORDS, JOB_TARGET)
async def list_jobs(session: AsyncSession, *, context: KeyContext) -> Sequence[SearchJob]:
    await require_manager(session, context=context, target=JOB_TARGET)
    return await audited_read(
        session, SearchJob, context, Scope.RECORDS, order_by=(SearchJob.created_at.desc(),)
    )


@audited(Action.READ, Scope.RECORDS, JOB_TARGET)
async def get_job(session: AsyncSession, *, context: KeyContext, job_id: uuid.UUID) -> SearchJob:
    await require_manager(session, context=context, target=JOB_TARGET)
    found = await audited_read(
        session, SearchJob, context, Scope.RECORDS, where=(SearchJob.id == job_id,)
    )
    if not found:
        raise NoSuchSearchJob(f"no search job {job_id} on profile {context.profile_id}")
    return found[0]


def _dedupe_key(found: Found, language: str) -> str:
    return f"learning:{hashlib.sha256(found.url.encode()).hexdigest()[:24]}:{language}"


def _facts_for(state: StateView) -> Mapping[str, Any]:
    """What the compressor may ground on: the clinical facts the snapshot holds, by id."""
    clinical = state.dimension(Dimension.CLINICAL)
    return {} if clinical is None else dict(clinical.get("facts", {}))


async def run_job(
    session: AsyncSession,
    *,
    context: KeyContext,
    job: SearchJob,
    engine: Engine,
    state: StateView,
    language: str,
    day: str,
    doctor: str | None,
    existing: set[str],
    format: CardFormat = CardFormat.TEXT,
) -> list[FeedItem]:
    """Run one job now: search, compress, check, and write the cards.

    `existing` is the dedupe keys already on the profile; a page already turned into a card
    is not made twice. The job's `results` record every page by outcome.
    """
    sources = await usable_sources(
        session, region=context.region, source_ids=[uuid.UUID(one) for one in job.source_ids]
    )
    domains = [source.domain for source in sources]
    made: list[FeedItem] = []
    questions: list[FeedItem] = []
    rejected: list[dict[str, str]] = []
    moment = utcnow()
    code = language_for(language)
    for found in engine.searcher.search(job.kind.value, job.terms, domains):
        try:
            source = await require_usable_source(
                session, region=context.region, domain=found.domain
            )
        except SourceNotAllowlisted:
            rejected.append({"url": found.url, "because": "not_allowlisted"})
            continue
        compressed = engine.compressor.compress(found.text, code, _facts_for(state))
        if compressed is None:
            rejected.append({"url": found.url, "because": "nothing_for_him_in_" + code})
            continue
        if not compressed.passage.strip():
            rejected.append({"url": found.url, "because": "uncited"})
            continue
        key = _dedupe_key(found, code)
        if key in existing:
            continue
        cite = {
            "url": found.url,
            "title": found.title,
            "published_at": found.published_at,
            "passage": compressed.passage,
            "start_sec": compressed.start_sec,
            "end_sec": compressed.end_sec,
        }
        if job.kind is JobKind.SAFETY:
            # A notice is checked against the batch on his pack. One that does not match is
            # held for the caregiver and never sent to him (spec §9); one that does is a
            # card for today, capped like any other.
            matches = found.batch is not None and found.batch.strip().lower() in _batches_on_record(
                state
            )
            notice_lines = learning_lines(
                code,
                headline=compressed.headline,
                body=compressed.body,
                topic=compressed.why_topic,
                source_name=source.name,
                doctor=doctor or YOUR_DOCTOR[code],
            )
            try:
                notice = await create_item(
                    session,
                    context=context,
                    state=state,
                    type=CardType.NOTICE,
                    lines=notice_lines,
                    why=Why(
                        kind="notice",
                        plain=notice_lines.why,
                        source_id=str(source.id),
                        gap=job.terms[0],
                        fact_ids=tuple(_fact_ids_about(state, job.terms)),
                        suppressed=None if matches else "batch_does_not_match_the_pack",
                    ),
                    scope=Scope.MEDICINES,
                    deliver_to=DeliverTo.PATIENT if matches else DeliverTo.CAREGIVER,
                    day=day,
                    dedupe_key=key,
                    expires_at=moment + LEARNING_LIFETIME,
                    format=format,
                    source=source,
                    cite={**cite, "batch": found.batch},
                    search_job_id=job.id,
                )
            except NotPlainWords as failed:
                rejected.append(
                    {"url": found.url, "because": "not_plain_words", "detail": str(failed)}
                )
                continue
            existing.add(key)
            made.append(notice)
            continue
        if changes_treatment([compressed.headline, *compressed.body]):
            # Not a card: a question for the doctor, held for the memo (E05 reads HELD).
            question = await create_item(
                session,
                context=context,
                state=state,
                type=CardType.QUESTION,
                lines=Lines(
                    language=code,
                    headline=f"Ask about: {found.title}",
                    body=tuple(compressed.body),
                    voice=(),
                    why=f"Found on {found.domain}; it could change treatment, so it is a question.",
                ),
                why=Why(kind="question", plain="", source_id=str(source.id), gap=job.terms[0]),
                scope=Scope.RECORDS,
                deliver_to=DeliverTo.MEMO,
                day=day,
                dedupe_key=key,
                expires_at=moment + LEARNING_LIFETIME,
                source=source,
                cite=cite,
                search_job_id=job.id,
            )
            existing.add(key)
            questions.append(question)
            rejected.append(
                {
                    "url": found.url,
                    "because": "treatment_change_rerouted_as_question",
                    "item_id": str(question.id),
                }
            )
            continue
        card = learning_lines(
            code,
            headline=compressed.headline,
            body=compressed.body,
            topic=compressed.why_topic,
            source_name=source.name,
            doctor=doctor or YOUR_DOCTOR[code],
        )
        try:
            item = await create_item(
                session,
                context=context,
                state=state,
                type=CardType.LEARNING,
                lines=card,
                why=Why(
                    kind="learning",
                    plain=card.why,
                    source_id=str(source.id),
                    gap=job.terms[0],
                    fact_ids=tuple(_fact_ids_about(state, job.terms)),
                ),
                scope=Scope.MEDICINES if job.reason.get("scope") == "medicines" else Scope.RECORDS,
                deliver_to=DeliverTo.PATIENT,
                day=day,
                dedupe_key=key,
                expires_at=moment + LEARNING_LIFETIME,
                format=format,
                source=source,
                cite=cite,
                search_job_id=job.id,
            )
        except NotPlainWords as failed:
            rejected.append({"url": found.url, "because": "not_plain_words", "detail": str(failed)})
            continue
        existing.add(key)
        made.append(item)
    job.status = JobStatus.DONE
    job.last_run_at = moment
    job.results = {
        "items": [str(item.id) for item in made],
        "questions": [str(item.id) for item in questions],
        "rejected": rejected,
        "searched": domains,
    }
    await session.flush()
    return [*made, *questions]


def _batches_on_record(state: StateView) -> set[str]:
    """The batch numbers read off his packs (a `medicine.batch` fact from a label photo)."""
    clinical = state.dimension(Dimension.CLINICAL) or {}
    facts = clinical.get("facts", {})
    found: set[str] = set()
    for subject in ("medicine", "medication"):
        batch = facts.get(subject, {}).get("batch", {}).get("value")
        if isinstance(batch, str):
            found.add(batch.strip().lower())
    return found


def _fact_ids_about(state: StateView, terms: Sequence[str]) -> list[str]:
    """The clinical fact ids whose subject or value names one of the terms."""
    clinical = state.dimension(Dimension.CLINICAL)
    if clinical is None:
        return []
    ids: list[str] = []
    for subject, attributes in clinical.get("facts", {}).items():
        for entry in attributes.values():
            haystack = f"{subject} {entry.get('value')}".lower()
            if any(term in haystack for term in terms):
                ids.append(entry["fact_id"])
    return sorted(ids)
