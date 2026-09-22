"""D3 — a rejected or corrected AI conclusion is recorded (ADR 0019 point 7;
`docs/design/NURA-BUILD-MASTER-SPEC.md` §39) on the review-card side: a person's "No"
(`FieldState.REJECTED`) or "Fix" (`FieldState.CORRECTED`) on a confirmed card writes a
`ConclusionReview` row beside an `AuditEntry` (`Action.REVIEW`) — the same discipline
`tests/test_ask_agent.py::test_a_dropped_plain_words_line_writes_a_content_free_d3_row` proves
for a gate's own drop. Neither row carries the rejected value, the corrected value, or any
fragment of either.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.conclusions import ConclusionResponseKind, ConclusionReview
from app.audit.models import AuditEntry
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.review import confirm_review_card
from app.regions import Region
from tests.paper import PAPER
from tests.test_ingestion import _card, _decide, _pa, _yes


async def test_a_rejected_field_writes_a_user_no_row_with_no_extracted_value(
    sg: AsyncSession, tmp_path: Path
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(
        sg, owner, LocalObjectStore(tmp_path, Region.SG), FixtureExtractor(PAPER)
    )
    rejected_field = next(f for f in fields if f.attribute == "tc_hdl_ratio")
    decisions = _decide(fields, reject={"tc_hdl_ratio"})
    yes = await _yes(sg, owner, card, decisions)

    await confirm_review_card(
        sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=yes
    )

    rows = (
        (
            await sg.execute(
                select(ConclusionReview).where(ConclusionReview.profile_id == owner.profile_id)
            )
        )
        .scalars()
        .all()
    )
    no_rows = [r for r in rows if r.response_kind is ConclusionResponseKind.USER_NO]
    assert len(no_rows) == 1
    row = no_rows[0]
    assert row.reason_code is None
    assert row.rule_id is None
    entry = await sg.get(AuditEntry, row.audit_entry_id)
    assert entry is not None
    assert entry.action.value == "review"
    assert entry.refused_because == "user_no"
    # Content-free: the extracted value this field would have carried (a number, a unit)
    # appears nowhere the row's own columns can be inspected — there simply is no column
    # for it, on either table.
    assert not hasattr(row, "value")
    assert rejected_field.attribute not in (entry.refused_because or "")


async def test_a_corrected_field_writes_a_user_fix_row_with_no_corrected_value(
    sg: AsyncSession, tmp_path: Path
) -> None:
    owner = await _pa(sg)
    card, fields = await _card(
        sg, owner, LocalObjectStore(tmp_path, Region.SG), FixtureExtractor(PAPER)
    )
    decisions = _decide(fields, correct={"triglycerides": 54})
    yes = await _yes(sg, owner, card, decisions)

    await confirm_review_card(
        sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=yes
    )

    rows = (
        (
            await sg.execute(
                select(ConclusionReview).where(ConclusionReview.profile_id == owner.profile_id)
            )
        )
        .scalars()
        .all()
    )
    fix_rows = [r for r in rows if r.response_kind is ConclusionResponseKind.USER_FIX]
    assert len(fix_rows) == 1
    row = fix_rows[0]
    entry = await sg.get(AuditEntry, row.audit_entry_id)
    assert entry is not None
    assert entry.refused_because == "user_fix"
    assert "54" not in (entry.refused_because or "")
