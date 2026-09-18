"""W2: Ask becomes a conversation.

`app.search.conversation` (thread persistence, scope isolation between two people's threads,
the deterministic summary) and the new ground the agent asker (`app.llm.ask_agent`) stands on:
a follow-up resolving "that" against conversation memory, an insurance answer citing only
policy lines, a cost answer that says plainly when nothing is on the ledger, a proposal that
never writes anything by itself, and a withheld tool for a scope the key does not hold.

Every model call is mocked (`FakeClient`, from `tests.test_ask_agent`) — no network, the same
rule every test of `ClaudeAsker` holds to.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.objects import LocalObjectStore
from app.insurance.policy import PolicyStatus, PolicyType, policy_draft, set_a_policy
from app.keys.confirm import confirm
from app.keys.scopes import KeyRole, Scope
from app.llm.ask_agent import ClaudeAsker, _tools_for
from app.memory.models import Appointment
from app.regions import Region
from app.search.ask import Answer, AnswerLine, AskStep, Cite, Mode, _keep_question
from app.search.asker import AnswerDelta
from app.search.conversation import (
    KEPT_VERBATIM,
    NoSuchConversation,
    conversation_by_id,
    current_conversation,
    memory_for,
    record_turn,
    start_new_conversation,
    turns_of,
)
from app.search.retrieve import KeywordRetriever
from tests.medicines_support import REGISTRY, let_in
from tests.test_ask_agent import FakeClient, FakeSearcher, _drive, _final, _tool_call
from tests.timeline_support import record


async def _write_policy(session: AsyncSession, context, *, covers: str = "Hospital stays, up to $500 a day.") -> None:
    draft = policy_draft(
        insurer_name="Great Eastern",
        policy_reference="GE-1",
        policy_type=PolicyType.HOSPITAL,
        covered="Pa",
        covers=covers,
        start_date=date(2026, 1, 1),
        renewal_date=date(2027, 1, 1),
        premium_due_date=None,
        status=PolicyStatus.ACTIVE,
        guarantee_letter=False,
        supersedes_id=None,
    )
    yes = await confirm(session, context, draft)
    await set_a_policy(
        session,
        context=context,
        insurer_name=draft.insurer_name,
        policy_reference=draft.policy_reference,
        policy_type=draft.policy_type,
        covered=draft.covered,
        covers=draft.covers,
        start_date=draft.start_date,
        renewal_date=draft.renewal_date,
        premium_due_date=draft.premium_due_date,
        status=draft.status,
        guarantee_letter=draft.guarantee_letter,
        supersedes_id=draft.supersedes_id,
        confirmation_id=yes.id,
    )


def _answer(lines: tuple[AnswerLine, ...] = (), honest: tuple[str, ...] = ()) -> Answer:
    return Answer(
        question_artifact_id=uuid.uuid4(),
        mode=Mode.TEXT,
        language="en",
        lines=lines,
        honest=honest,
        boundary=("Ask Dr Tan.",),
        withheld=(),
        dropped=0,
    )


# --- thread persistence and scope ------------------------------------------------------------


async def test_current_conversation_is_reused_then_a_new_one_starts_on_request(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    first = await current_conversation(sg, context=rec.owner)
    again = await current_conversation(sg, context=rec.owner)
    assert again.id == first.id

    fresh = await start_new_conversation(sg, context=rec.owner)
    assert fresh.id != first.id
    still_fresh = await current_conversation(sg, context=rec.owner)
    assert still_fresh.id == fresh.id


async def test_a_caregivers_thread_is_never_the_patients(sg: AsyncSession) -> None:
    rec = await record(sg)
    caregiver = await let_in(
        sg,
        rec.owner,
        phone="+6588880011",
        name="Mei",
        role=KeyRole.CAREGIVER,
        scopes={Scope.PROFILE, Scope.ASK, Scope.VISITS},
    )
    his = await current_conversation(sg, context=rec.owner)
    hers = await current_conversation(sg, context=caregiver)
    assert his.id != hers.id

    with pytest.raises(NoSuchConversation):
        await conversation_by_id(sg, context=caregiver, conversation_id=his.id)


async def test_a_turn_is_kept_on_the_thread_and_read_back_by_get(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, Region.SG)
    conversation = await current_conversation(sg, context=rec.owner)
    answer = _answer(
        lines=(AnswerLine(text="Your medicine is on your list.", cites=(Cite(kind="fact", id=uuid.uuid4()),)),)
    )
    q = await _keep_question(sg, rec.owner, store, "what is my medicine")
    turn = await record_turn(
        sg,
        context=rec.owner,
        store=store,
        conversation=conversation,
        question_artifact_id=q.id,
        answer=answer,
    )
    turns = await turns_of(sg, context=rec.owner, conversation=conversation)
    assert [t.id for t in turns] == [turn.id]
    assert turns[0].answered is True
    assert turns[0].line_count == 1


# --- summary after 7 turns ---------------------------------------------------------------------


async def test_the_eighth_turn_folds_the_first_into_the_summary(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, Region.SG)
    conversation = await current_conversation(sg, context=rec.owner)
    assert KEPT_VERBATIM == 6

    for n in range(7):
        answer = _answer(
            lines=(AnswerLine(text=f"line {n}", cites=(Cite(kind="fact", id=uuid.uuid4()),)),)
        )
        q = await _keep_question(sg, rec.owner, store, f"question {n}")
        await record_turn(
            sg,
            context=rec.owner,
            store=store,
            conversation=conversation,
            question_artifact_id=q.id,
            answer=answer,
        )
    # Six turns in, nothing is folded yet — only the seventh pushes the first out of the
    # verbatim window.
    assert conversation.turn_count == 7
    assert conversation.summarized_through == 1
    assert conversation.summary is not None
    assert "Nura found 1 line" in conversation.summary

    memory = await memory_for(sg, context=rec.owner, store=store, conversation=conversation)
    assert len(memory.recent) == KEPT_VERBATIM
    assert memory.summary == conversation.summary


# --- a follow-up resolving "that" (mocked model) ------------------------------------------------


async def test_a_follow_up_sees_the_earlier_turn_in_its_system_prompt(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, Region.SG)
    conversation = await current_conversation(sg, context=rec.owner)
    q = await _keep_question(
        sg, rec.owner, store, "what is my blood pressure tablet"
    )
    await record_turn(
        sg,
        context=rec.owner,
        store=store,
        conversation=conversation,
        question_artifact_id=q.id,
        answer=_answer(
            lines=(
                AnswerLine(
                    text="Your blood pressure tablet is on your list of medicines.",
                    cites=(Cite(kind="medication_line", id=uuid.uuid4()),),
                ),
            )
        ),
    )
    history = await memory_for(sg, context=rec.owner, store=store, conversation=conversation)
    assert len(history.recent) == 1

    client = FakeClient(
        [_final([{"text": "It is on your list of medicines.", "cites": ["m1"]}])]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    answer = None
    async for event in asker.ask_stream(
        sg,
        context=rec.owner,
        question="and what about that",
        mode=Mode.TEXT,
        retriever=KeywordRetriever(),
        store=store,
        registry=REGISTRY,
        language="en",
        history=history,
    ):
        if not isinstance(event, (AskStep, AnswerDelta)):
            answer = event
    assert answer is not None
    sent_system = client.messages.calls[0]["system"]
    assert "Your blood pressure tablet is on your list of medicines" in sent_system
    assert "continuing conversation" in sent_system


# --- insurance answer only cites policy lines ---------------------------------------------------


async def test_an_insurance_answer_cites_only_the_policy_line(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    await _write_policy(sg, rec.owner)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_insurance"),
            _final(
                [
                    {
                        "text": "Your policy covers hospital stays, up to $500 a day.",
                        "cites": ["p1"],
                    }
                ]
            ),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    steps, _deltas, answer = await _drive(asker, sg, rec.owner, "what does my policy cover", tmp_path)
    assert steps == ["insurance"]
    assert len(answer.lines) == 1
    assert {cite.kind for cite in answer.lines[0].cites} == {"policy"}


async def test_insurance_and_costs_are_withheld_without_money_scope(sg: AsyncSession) -> None:
    rec = await record(sg)
    narrow = await let_in(
        sg,
        rec.owner,
        phone="+6588880022",
        name="Aminah",
        role=KeyRole.HELPER,
        scopes={Scope.PROFILE, Scope.ASK},
    )
    tools = _tools_for(narrow)
    assert "read_insurance" not in tools
    assert "read_costs" not in tools
    assert "read_plan" not in tools
    # An action offer is never itself a scope-gated read: the tool exists so the reader can
    # still be offered a next step (e.g. "message the provider") even on a narrow key.
    assert "propose_action" in tools


# --- cost answer says "no benchmark" honestly ----------------------------------------------------


async def test_a_cost_question_with_nothing_on_the_ledger_is_answered_honestly(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    # No claims ever filed: `read_costs` returns nothing, so no id exists to cite, and the
    # model's own line (whatever it wrote) cannot survive `_answer_from_payload` — the same
    # "never invent a cite" rule every other tool's line already rests on.
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_costs"),
            _final(
                [{"text": "Nothing is written down about what this cost.", "cites": ["c1"]}]
            ),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    _steps, _deltas, answer = await _drive(
        asker, sg, rec.owner, "what did the stent procedure cost", tmp_path
    )
    # No claim was ever registered, so "c1" cites nothing this ask actually read: the line is
    # dropped, and the rule-based fallback says plainly that nothing is written down.
    assert answer.lines == ()
    assert answer.honest


# --- a proposal never writes without a yes -------------------------------------------------------


async def test_a_proposal_is_offered_but_writes_nothing_by_itself(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    before = (await sg.execute(select(Appointment).where(Appointment.profile_id == rec.owner.profile_id))).scalars().all()

    client = FakeClient(
        [
            _tool_call(
                "toolu_1",
                "propose_action",
                {"kind": "add_to_visit", "label": "Add to Thursday's questions"},
            ),
            _final(
                [
                    {
                        "text": "Your next visit with Dr Tan is written down.",
                        # The one id this ask actually has: the note `propose_action` itself
                        # registered (`x1`) — no `read_visits` call happened this ask, so a
                        # cite naming a visit would match nothing and the line would be
                        # dropped, same as any other tool's line.
                        "cites": ["x1"],
                    }
                ]
            ),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    steps, _deltas, answer = await _drive(asker, sg, rec.owner, "add this to my next visit", tmp_path)
    assert steps == ["plan"]
    assert len(answer.proposals) == 1
    assert answer.proposals[0].kind == "add_to_visit"
    assert answer.proposals[0].label == "Add to Thursday's questions"

    after = (await sg.execute(select(Appointment).where(Appointment.profile_id == rec.owner.profile_id))).scalars().all()
    assert len(after) == len(before)
