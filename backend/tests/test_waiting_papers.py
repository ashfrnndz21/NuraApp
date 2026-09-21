"""A paper waiting to be checked (W2, `app.llm.ask_agent`'s fix 2): a review card not yet
confirmed is his own information — that it exists, its kind, the date printed on it, where it
is from, and when he added it — never the values on it, which stay behind his own yes.
`app.search.ask.waiting_papers` is the one read both askers share: `RuleBasedAsker`
(`recall_stream`) says one deterministic line for the obvious case, and `ClaudeAsker`'s
`read_waiting_papers` tool hands the model the same four fields and nothing else.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.photos import store_photo
from app.ingestion.review import review_photo
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.memory.models import SourceChannel
from app.regions import Region
from app.search.ask import Cite, Mode, recall_stream
from app.search.ask import waiting_papers as waiting_papers_read
from app.search.retrieve import KeywordRetriever
from tests.medicines_support import let_in
from tests.paper import LAB_REPORT_VITALS, PAPER, placeholder_png
from tests.timeline_support import record, trail

SG = Region.SG
CAPTURED_AT = datetime(2026, 9, 18, 8, 0, tzinfo=UTC)


async def _waiting_card(
    session: AsyncSession, context: KeyContext, store: LocalObjectStore, label: str = LAB_REPORT_VITALS
):
    photo = await store_photo(
        session,
        context=context,
        store=store,
        data=placeholder_png(label),
        content_type="image/png",
        captured_at=CAPTURED_AT,
        source_channel=SourceChannel.APP,
    )
    return await review_photo(
        session,
        context=context,
        artifact_id=photo.id,
        store=store,
        extractor=FixtureExtractor(PAPER),
        language="en",
    )


async def test_a_waiting_card_carries_only_the_four_safe_fields(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, SG)
    card = await _waiting_card(sg, rec.owner, store)

    found = await waiting_papers_read(sg, rec.owner, language="en")
    assert [w.card_id for w in found] == [card.id]
    waiting = found[0]
    assert waiting.kind == "blood test"
    assert waiting.document_date is not None and waiting.document_date.isoformat() == "2026-09-10"
    assert waiting.facility == "Bukit Lab"
    # Never a value, a unit or a range: the dataclass itself has no field for one, and the
    # LAB_REPORT_VITALS fixture's own extracted numbers (5.6, 140, the "<130" range, "glucose",
    # "ldl") never appear anywhere on the object at all.
    rendered = repr(waiting)
    for leaked in ("5.6", "140", "<130", "glucose", "ldl"):
        assert leaked not in rendered


async def test_a_key_without_the_records_scope_gets_no_waiting_list(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, SG)
    await _waiting_card(sg, rec.owner, store)
    narrow = await let_in(
        sg,
        rec.owner,
        phone="+6588880099",
        name="Aminah",
        role=KeyRole.HELPER,
        scopes={Scope.PROFILE, Scope.ASK, Scope.VISITS, Scope.EMERGENCY},
    )
    # The same rule `_corpus_stream` holds for the papers already confirmed: a part this key
    # cannot open is never read, so a waiting card under it can never even be named.
    assert await waiting_papers_read(sg, narrow, language="en") == []


async def test_the_waiting_papers_read_is_audited(sg: AsyncSession, tmp_path: Path) -> None:
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, SG)
    await _waiting_card(sg, rec.owner, store)

    entries = await trail(sg, rec.owner)
    before = len(entries)
    await waiting_papers_read(sg, rec.owner, language="en")
    after = await trail(sg, rec.owner)
    new_targets = {e.target for e in after[before:] if e.action is Action.READ}
    assert new_targets & {"review_card", "review_field"}
    assert all(e.outcome is Outcome.ALLOWED for e in after[before:])


async def test_the_rule_based_asker_says_one_line_for_the_obvious_waiting_case(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """`RuleBasedAsker` (`recall_stream`), never a model: a question naming a paper kind that
    has a waiting card, and nothing confirmed answers it, gets one deterministic line saying
    it is waiting — cited to the review card alone."""
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, SG)
    card = await _waiting_card(sg, rec.owner, store)

    answer = None
    async for event in recall_stream(
        sg,
        context=rec.owner,
        question="When was my last blood results done?",
        mode=Mode.TEXT,
        retriever=KeywordRetriever(),
        store=store,
        language="en",
    ):
        if hasattr(event, "lines"):
            answer = event
    assert answer is not None
    assert len(answer.lines) == 1
    line = answer.lines[0]
    assert "waiting" in line.text.lower()
    assert line.cites == (Cite(kind="review_card", id=card.id),)
    # Never a value from the card: the fixture's own numbers never appear in the line said.
    for leaked in ("5.6", "140", "<130"):
        assert leaked not in line.text
