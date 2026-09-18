"""The Add flow's thinking trace (docs/design-direction.md, "Conversation, waiting and
'thinking'"): `review_artifact_stream` yields one `ImportStep` for each real stage of turning
a stored photo or PDF into a review card — stored, reading, what it found, the red-flag
check where one really runs, a real link where one exists — then the `ReviewCard` itself,
never an invented step, never an artificial delay. `review_artifact` (E02-01/E02-07's
existing surface) is `review_artifact_stream`, drained, so the two can never drift apart:
this file only exercises the stream's own promises, the way `test_ask_stream.py` does for
`recall`/`recall_stream`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.extract import DocumentKind, FixtureExtractor
from app.ingestion.models import ReviewCard
from app.ingestion.objects import LocalObjectStore
from app.ingestion.photos import store_photo
from app.ingestion.review import (
    ImportStep,
    ImportStepKey,
    review_artifact,
    review_artifact_stream,
)
from app.keys.context import KeyContext
from app.memory.models import SourceChannel
from app.safety.red_flags import Flag, open_flags
from tests.medicines_support import SEPT_3, add, label, pa
from tests.paper import (
    LAB_REPORT_RED_FLAG,
    LAB_REPORT_VITALS,
    PAPER,
    WARFARIN_LABEL,
    placeholder_png,
)


async def _photo(
    session: AsyncSession, context: KeyContext, store: LocalObjectStore, digest_label: str
):
    return await store_photo(
        session,
        context=context,
        store=store,
        data=placeholder_png(digest_label),
        content_type="image/png",
        captured_at=SEPT_3,
        source_channel=SourceChannel.APP,
    )


async def _stream(
    session: AsyncSession,
    context: KeyContext,
    store: LocalObjectStore,
    extractor: FixtureExtractor,
    digest_label: str,
) -> tuple[list[ImportStep], ReviewCard]:
    photo = await _photo(session, context, store, digest_label)
    steps: list[ImportStep] = []
    card: ReviewCard | None = None
    async for event in review_artifact_stream(
        session,
        context=context,
        artifact_id=photo.id,
        store=store,
        extractor=extractor,
        language="en",
    ):
        if isinstance(event, ImportStep):
            steps.append(event)
        else:
            card = event
    assert card is not None
    return steps, card


async def test_a_lab_report_streams_stored_reading_found_and_ready_in_order(
    sg: AsyncSession, tmp_path: Path
) -> None:
    context = await pa(sg)
    store = LocalObjectStore(tmp_path, context.region)
    extractor = FixtureExtractor(PAPER)
    steps, card = await _stream(sg, context, store, extractor, LAB_REPORT_VITALS)
    # No red-flag word on this paper and nothing on the record to link to: RED_FLAG_CHECKED
    # is real (every lab report is scanned) but LINKED is not (module docstring: a step is
    # shown only when a real check found something, never invented).
    assert [step.key for step in steps] == [
        ImportStepKey.STORED,
        ImportStepKey.READING,
        ImportStepKey.FOUND,
        ImportStepKey.RED_FLAG_CHECKED,
        ImportStepKey.READY,
    ]
    found = steps[2]
    assert found.document_kind == "lab_report"
    assert found.facility == "Bukit Lab"
    assert found.document_date == "2026-09-10"
    assert card.document_kind is DocumentKind.LAB_REPORT
    assert card.document_date == date(2026, 9, 10)


async def test_the_stream_matches_review_artifact_for_the_same_photo(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """`review_artifact` is `review_artifact_stream`, drained: the plain route and the
    streamed one can never answer the pipeline two different ways."""
    context = await pa(sg)
    store = LocalObjectStore(tmp_path, context.region)
    extractor = FixtureExtractor(PAPER)
    photo_a = await _photo(sg, context, store, LAB_REPORT_VITALS)
    drained = await review_artifact(
        sg, context=context, artifact_id=photo_a.id, store=store, extractor=extractor, language="en"
    )
    photo_b = await _photo(sg, context, store, LAB_REPORT_VITALS)
    steps: list[ImportStep] = []
    card: ReviewCard | None = None
    async for event in review_artifact_stream(
        sg, context=context, artifact_id=photo_b.id, store=store, extractor=extractor, language="en"
    ):
        if isinstance(event, ImportStep):
            steps.append(event)
        else:
            card = event
    assert card is not None
    assert card.document_kind == drained.document_kind
    assert card.document_date == drained.document_date
    assert card.high_risk_class == drained.high_risk_class


async def test_a_red_flag_word_on_a_lab_report_is_raised_before_the_ready_step(
    sg: AsyncSession, tmp_path: Path
) -> None:
    context = await pa(sg)
    store = LocalObjectStore(tmp_path, context.region)
    extractor = FixtureExtractor(PAPER)
    steps, _card = await _stream(sg, context, store, extractor, LAB_REPORT_RED_FLAG)
    keys = [step.key for step in steps]
    assert ImportStepKey.RED_FLAG_CHECKED in keys
    assert keys.index(ImportStepKey.RED_FLAG_CHECKED) < keys.index(ImportStepKey.READY)
    flags = await open_flags(sg, context=context)
    assert any(isinstance(flag, Flag) for flag in flags)


async def test_a_medicine_already_on_the_list_streams_a_real_link(
    sg: AsyncSession, tmp_path: Path
) -> None:
    context = await pa(sg)
    store = LocalObjectStore(tmp_path, context.region)
    extractor = FixtureExtractor(PAPER)
    # Warfarin is already on his list before this label is read.
    await add(sg, context, label("Warfarin", "3mg"))
    steps, _card = await _stream(sg, context, store, extractor, WARFARIN_LABEL)
    linked = next((step for step in steps if step.key is ImportStepKey.LINKED), None)
    assert linked is not None
    assert linked.linked_kind == "medicine"
    assert linked.linked_label is not None and "warfarin" in linked.linked_label.lower()


async def test_no_link_step_when_nothing_on_the_record_matches(
    sg: AsyncSession, tmp_path: Path
) -> None:
    context = await pa(sg)
    store = LocalObjectStore(tmp_path, context.region)
    extractor = FixtureExtractor(PAPER)
    steps, _card = await _stream(sg, context, store, extractor, WARFARIN_LABEL)
    assert all(step.key is not ImportStepKey.LINKED for step in steps)
