"""Care navigation with drafted messages (T3) acceptance.

Each need on the record — a letter's own check-up date (#257's `follow_up`/`date` field), a
new line the pharmacy wrote, an upcoming visit at a lab, a care-service category on the
provider directory (PR #264) — drafts a short plain-words message, in his language, citing
the row it rests on. Nothing is ever sent: `draft_message` only ever returns text and a link
built from the provider's own phone; a provider with none gets a copyable draft. No draft, in
any kind, ever carries a dose or a diagnosis — there is no template slot for either. A
caregiver drafts in her own name, never his.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action
from app.clock import now
from app.memory.models import HomeCareCategory, ProviderKind
from app.memory.semantic import assert_fact
from app.memory.spine import add_provider
from app.reasoning.navigation.models import NeedKind
from app.reasoning.navigation.rule_drafter import names_dose_or_diagnosis
from app.reasoning.navigation.service import (
    draft_message,
    needs_for,
    provider_for_need,
)
from app.regions import Region
from tests.timeline_support import book, record, trail


def _need(needs, kind: NeedKind):
    found = [need for need in needs if need.kind is kind]
    assert found, f"no {kind} need among {[n.kind for n in needs]}"
    return found[0]


async def test_a_letters_follow_up_date_drafts_with_cites(sg: AsyncSession) -> None:
    rec = await record(sg)
    fact = await assert_fact(
        sg,
        context=rec.owner,
        subject="follow_up",
        attribute="date",
        value="2026-09-25",
        confidence=0.9,
        artifact_id=rec.paper.id,
        episode_id=rec.episode.id,
        valid_from=now(),
    )
    needs = await needs_for(sg, context=rec.owner)
    need = _need(needs, NeedKind.FOLLOW_UP)
    assert need.doctor == "Dr Tan"  # the episode's own next visit names the provider
    provider = await provider_for_need(sg, context=rec.owner, need=need)
    draft = await draft_message(sg, rec.owner, need, provider)
    assert draft.cites == (f"fact:{fact.id}",)
    assert "Pa" in draft.text and "Dr Tan" in draft.text
    assert draft.drafted_by == "self"


async def test_a_new_pharmacy_line_drafts_with_cites(sg: AsyncSession) -> None:
    rec = await record(sg)  # record() already writes a first amlodipine line
    needs = await needs_for(sg, context=rec.owner)
    need = _need(needs, NeedKind.NEW_MEDICINE)
    assert need.evidence_id == rec.medicine.line.id
    assert need.doctor == "Dr Tan"
    draft = await draft_message(sg, rec.owner, need, None)
    assert draft.cites == (f"medication_line:{need.evidence_id}",)
    assert "new medicine" in draft.text
    assert "amlodipine" not in draft.text.lower()  # never the drug's own name either


async def test_an_upcoming_lab_visit_drafts_with_cites(sg: AsyncSession) -> None:
    rec = await record(sg)
    lab = await add_provider(
        sg, context=rec.owner, name="PanaBio Labs", kind=ProviderKind.LAB, region=Region.SG, phone_e164="+6598765432"
    )
    visit = await book(sg, rec.owner, lab, now() + timedelta(days=3), "blood test")
    needs = await needs_for(sg, context=rec.owner)
    need = _need(needs, NeedKind.TEST_DUE)
    assert need.evidence_id == visit.id
    provider = await provider_for_need(sg, context=rec.owner, need=need)
    draft = await draft_message(sg, rec.owner, need, provider)
    assert draft.cites == (f"appointment:{visit.id}",)
    assert not draft.copy_only
    assert draft.links and draft.links[0].kind == "sms"
    assert draft.links[0].href == "sms:+6598765432"
    assert any(link.href == "https://wa.me/6598765432" for link in draft.links)


async def test_a_home_care_category_drafts_with_cites_and_copies_without_a_phone(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    await add_provider(
        sg, context=rec.owner, name="Golden Years Physio", kind=ProviderKind.OTHER,
        region=Region.SG, category=HomeCareCategory.PHYSIO,
    )
    needs = await needs_for(sg, context=rec.owner)
    need = _need(needs, NeedKind.HOME_CARE)
    assert need.category == "physio"
    provider = await provider_for_need(sg, context=rec.owner, need=need)
    draft = await draft_message(sg, rec.owner, need, provider)
    assert draft.copy_only and not draft.links
    assert "physio" in draft.text.lower()


async def test_nothing_is_ever_sent_and_the_draft_is_on_the_trail(sg: AsyncSession) -> None:
    rec = await record(sg)
    needs = await needs_for(sg, context=rec.owner)
    need = _need(needs, NeedKind.NEW_MEDICINE)
    before = [line for line in await trail(sg, rec.owner) if line.target == "navigation_draft"]
    draft = await draft_message(sg, rec.owner, need, None)
    after = [line for line in await trail(sg, rec.owner) if line.target == "navigation_draft"]
    assert len(after) == len(before) + 1
    assert after[-1].action is Action.WRITE
    # The draft carries only text and links, nothing that could itself be a send.
    assert not hasattr(draft, "sent") and not hasattr(draft, "sent_at")


async def test_a_caregiver_drafts_in_her_own_name(sg: AsyncSession) -> None:
    rec = await record(sg)
    needs = await needs_for(sg, context=rec.mei)
    need = _need(needs, NeedKind.NEW_MEDICINE)
    draft = await draft_message(sg, rec.mei, need, None)
    assert draft.drafted_by == "caregiver"
    assert draft.text.startswith("This is Mei")
    assert "Pa" in draft.text


async def test_no_draft_ever_names_a_dose_or_a_diagnosis(sg: AsyncSession) -> None:
    rec = await record(sg)
    await assert_fact(
        sg,
        context=rec.owner,
        subject="follow_up",
        attribute="date",
        value="2026-09-25",
        confidence=0.9,
        artifact_id=rec.paper.id,
        valid_from=now(),
    )
    lab = await add_provider(sg, context=rec.owner, name="PanaBio Labs", kind=ProviderKind.LAB, region=Region.SG)
    await book(sg, rec.owner, lab, now() + timedelta(days=3), "blood test")
    await add_provider(
        sg, context=rec.owner, name="Home Nursing Co", kind=ProviderKind.OTHER,
        region=Region.SG, category=HomeCareCategory.NURSING,
    )
    needs = await needs_for(sg, context=rec.owner)
    assert {need.kind for need in needs} == {
        NeedKind.FOLLOW_UP,
        NeedKind.NEW_MEDICINE,
        NeedKind.TEST_DUE,
        NeedKind.HOME_CARE,
    }
    for need in needs:
        provider = await provider_for_need(sg, context=rec.owner, need=need)
        draft = await draft_message(sg, rec.owner, need, provider)
        assert names_dose_or_diagnosis(draft.text) is None, draft.text


def test_the_blocklist_itself_catches_a_dose_and_a_diagnosis() -> None:
    assert names_dose_or_diagnosis("Take 5 mg once a day") == "dose"
    assert names_dose_or_diagnosis("He has diabetes") == "condition"
    assert names_dose_or_diagnosis("This is Pa. Could we book a time, please?") is None
