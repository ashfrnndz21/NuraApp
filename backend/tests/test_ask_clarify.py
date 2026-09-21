"""Natural clarifying questions (W2): the rule-based asker's two deterministic cases
(`app.search.ask._clarify_for`), the agent asker's own model-proposed clarification, validated
before a word of it reaches the wire (`app.llm.ask_agent._parse_clarify`), and a tap's own
token resolved on the next turn (`app.search.conversation.resolve_clarify_value`).

Every test here mocks the `anthropic` client, the same rule `test_ask_agent.py` holds
`ClaudeAsker` to: deterministic inputs, no network.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Outcome
from app.channels.about_him import reader_of
from app.ingestion.objects import LocalObjectStore
from app.llm.ask_agent import ClaudeAsker, _waiting_clarify_label
from app.memory.models import Artifact, ArtifactKind, SourceChannel
from app.regions import Region
from app.search.ask import Answer, Mode, _clarify_for, _Corpus, _keep_question, recall
from app.search.asker import AnswerDelta
from app.search.conversation import (
    ConversationMemory,
    TurnMemory,
    current_conversation,
    record_turn,
    resolve_clarify_value,
)
from app.search.retrieve import KeywordRetriever
from tests.medicines_support import REGISTRY
from tests.test_ask_agent import FakeClient, FakeMessage, FakeSearcher, _drive, _tool_call
from tests.timeline_support import record, trail

# --- the rule-based asker's two deterministic cases (`_clarify_for`) -------------------------


def _paper(when: datetime) -> Artifact:
    return Artifact(
        id=uuid.uuid4(),
        kind=ArtifactKind.PDF,
        storage_key=f"papers/{uuid.uuid4()}",
        content_type="application/pdf",
        sha256="0" * 64,
        captured_at=when,
        source_channel=SourceChannel.APP,
        region=Region.SG,
        stored_at=when,
    )


def _corpus_with_papers(count: int, kind: str = "lab_report") -> _Corpus:
    corpus = _Corpus()
    for n in range(count):
        artifact = _paper(datetime(2026, 1, n + 1, tzinfo=UTC))
        corpus.papers[artifact.id] = artifact
        corpus.paper_kinds[artifact.id] = kind
    return corpus


async def test_which_paper_clarify_fires_with_two_or_more_confirmed_papers_of_one_kind(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    reader = await reader_of(sg, rec.owner, "en")
    corpus = _corpus_with_papers(2)
    found = _clarify_for("what did my blood test show", corpus, rec.owner, "en", reader)
    assert found is not None
    assert found.options != ()
    assert len(found.options) == 2
    assert found.allow_other is False
    # Newest first.
    assert "Your blood test of" in found.options[0].label
    assert found.options[0].label != found.options[1].label
    # Opaque values, never the row's own id.
    assert all(uuid.UUID(hex=str(rec.paper.id)) is not None for _ in [0])  # sanity: uuid works
    assert all(o.value != str(o.cite.id) for o in found.options if o.cite is not None)


async def test_exactly_one_matching_paper_never_clarifies(sg: AsyncSession) -> None:
    rec = await record(sg)
    reader = await reader_of(sg, rec.owner, "en")
    corpus = _corpus_with_papers(1)
    assert _clarify_for("what did my blood test show", corpus, rec.owner, "en", reader) is None


async def test_five_same_kind_papers_capped_at_four_newest(sg: AsyncSession) -> None:
    rec = await record(sg)
    reader = await reader_of(sg, rec.owner, "en")
    corpus = _corpus_with_papers(5)
    found = _clarify_for("what did my blood test show", corpus, rec.owner, "en", reader)
    assert found is not None
    assert len(found.options) == 4
    # Newest (Jan 5) first, oldest of the four kept (Jan 2) last — Jan 1 dropped.
    dates = [corpus.papers[o.cite.id].captured_at.day for o in found.options if o.cite]
    assert dates == sorted(dates, reverse=True)
    assert min(dates) == 2


async def test_a_question_that_already_names_a_date_never_triggers_the_paper_clarify(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    reader = await reader_of(sg, rec.owner, "en")
    corpus = _corpus_with_papers(2)
    assert (
        _clarify_for("what did my blood test from September show", corpus, rec.owner, "en", reader)
        is None
    )


async def test_a_cost_question_with_no_procedure_asks_what_it_is_for_free_text(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    reader = await reader_of(sg, rec.owner, "en")
    corpus = _Corpus()
    found = _clarify_for("how much will this cost", corpus, rec.owner, "en", reader)
    assert found is not None
    assert found.options == ()
    assert found.allow_other is True


async def test_caregiver_voice_names_him_never_your(sg: AsyncSession) -> None:
    rec = await record(sg)
    reader = await reader_of(sg, rec.mei, "en")
    assert reader.his is False
    corpus = _corpus_with_papers(2)
    found = _clarify_for("what did his blood test show", corpus, rec.owner, "en", reader)
    assert found is not None
    assert all("Your" not in o.label for o in found.options)
    assert all(reader.name in o.label for o in found.options)


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
async def test_rule_based_clarify_exists_in_every_language_owner_and_caregiver(
    sg: AsyncSession, language: str
) -> None:
    from app.delivery.timeline_strings import paper_word

    rec = await record(sg)
    word = paper_word("lab_report", language)
    question = {"en": f"what did my {word} show", "ms": f"apa hasil {word} saya", "zh": f"我的{word}结果如何"}[language]
    cost_question = {"ms": "berapa kos ini", "zh": "这个多少钱", "en": "how much does this cost"}[language]
    for context in (rec.owner, rec.mei):
        reader = await reader_of(sg, context, language)
        corpus = _corpus_with_papers(2)
        found = _clarify_for(question, corpus, context, language, reader)
        assert found is not None
        assert found.question
        assert len(found.options) == 2
        cost = _clarify_for(cost_question, _Corpus(), context, language, reader)
        assert cost is not None
        assert cost.allow_other is True


# --- the agent asker's own model-proposed clarification (`_parse_clarify`, `ClaudeAsker`) ----


def _clarify_payload(candidate_ids: list[str], question: str = "Which test does this mean?") -> FakeMessage:
    payload = {
        "lines": [],
        "boundary": "ignored",
        "clarify": {
            "referent_class": "which_test",
            "candidate_ids": candidate_ids,
            "question": question,
        },
    }
    return FakeMessage(stop_reason="end_turn", content=[{"type": "text", "text": json.dumps(payload)}])


async def test_a_valid_clarify_proposal_reaches_the_wire_with_backend_built_labels(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """BEHAVIOURAL PROOF 1: on the pre-change code, `Answer` has no `clarify` field at all and
    `ClaudeAsker` never looks at `payload["clarify"]` — this fails with an `AttributeError`
    (`answer.clarify`) on unmodified code, not an import error, because `_drive`/`ClaudeAsker`
    themselves already exist."""
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_records"),
            _clarify_payload(["f1", "f2"]),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    deltas: list[AnswerDelta] = []
    answer = None
    async for event in asker.ask_stream(
        sg,
        context=rec.owner,
        question="what about my test",
        mode=Mode.TEXT,
        retriever=KeywordRetriever(),
        store=LocalObjectStore(tmp_path, Region.SG),
        registry=REGISTRY,
        language="en",
    ):
        if isinstance(event, AnswerDelta):
            deltas.append(event)
        elif event.__class__.__name__ == "Answer":
            answer = event
    assert answer is not None
    assert answer.clarify is not None
    assert answer.lines == ()
    assert len(answer.clarify.options) == 2
    # The wire's own `answer_sentence` for the question, before the final answer.
    assert deltas and deltas[0].text == answer.clarify.question
    # Labels are backend-built (contain "Your" + a said-date), never the model's own words —
    # the model was never given a label to write in the first place.
    for option in answer.clarify.options:
        assert "Your" in option.label
        assert option.value not in ("f1", "f2")


async def test_a_clarify_candidate_not_in_tool_results_drops_the_whole_proposal(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """BEHAVIOURAL PROOF 2: on the pre-change code this fails the same way (`AttributeError`
    on `answer.clarify`); after the change, it must show that a forged id makes the WHOLE
    proposal vanish — never a partial clarify with a made-up option."""
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_records"),
            _clarify_payload(["f1", "not-a-real-id"]),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    _steps, _deltas, answer = await _drive(asker, sg, rec.owner, "what about my test", tmp_path)
    assert answer.clarify is None
    # A dropped proposal with no lines at all falls back to the rule-based answer — never
    # nothing.
    assert answer.answered or answer.honest


async def test_a_clarify_proposal_with_only_one_candidate_is_dropped(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_records"),
            _clarify_payload(["f1"]),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    _steps, _deltas, answer = await _drive(asker, sg, rec.owner, "what about my test", tmp_path)
    assert answer.clarify is None


async def test_a_clarify_question_failing_plain_words_is_dropped(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    too_long = (
        "Please specify precisely and in great detail which of your several different blood "
        "test results, taken on various different occasions throughout the year, you are "
        "actually referring to in your question just now"
    )
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_records"),
            _clarify_payload(["f1", "f2"], question=too_long),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    _steps, _deltas, answer = await _drive(asker, sg, rec.owner, "what about my test", tmp_path)
    assert answer.clarify is None


async def test_second_consecutive_clarify_is_refused_the_model_must_answer(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """BEHAVIOURAL PROOF 3: on the pre-change code `ConversationMemory`/`TurnMemory` carry no
    `was_clarify` field at all — this raises `TypeError` on unmodified code (an unexpected
    keyword argument), not an import error, since `TurnMemory`/`ConversationMemory` already
    exist. After the change: even though the model proposes ANOTHER clarify, the second
    consecutive one is never looked at — the answer must come from `lines` instead."""
    rec = await record(sg)
    history = ConversationMemory(
        conversation_id=uuid.uuid4(),
        recent=(TurnMemory(question="what about my test", answer_lines=(), honest=(), was_clarify=True),),
        summary=None,
    )
    payload = {
        "lines": [{"text": "Your blood test of Saturday 12 September is on your papers.", "cites": ["f1"]}],
        "boundary": "ignored",
        "clarify": {"referent_class": "which_test", "candidate_ids": ["f1", "f2"], "question": "Which one?"},
    }
    client = FakeClient(
        [
            _tool_call("toolu_1", "read_records"),
            FakeMessage(stop_reason="end_turn", content=[{"type": "text", "text": json.dumps(payload)}]),
        ]
    )
    asker = ClaudeAsker(client, searcher=FakeSearcher())
    answer = None
    async for event in asker.ask_stream(
        sg,
        context=rec.owner,
        question="what about my test",
        mode=Mode.TEXT,
        retriever=KeywordRetriever(),
        store=LocalObjectStore(tmp_path, Region.SG),
        registry=REGISTRY,
        language="en",
        history=history,
    ):
        if event.__class__.__name__ == "Answer":
            answer = event
    assert answer is not None
    assert answer.clarify is None
    assert answer.answered


async def test_red_flag_message_never_reaches_the_asker_so_never_clarifies(sg: AsyncSession, tmp_path: Path) -> None:
    """The red-flag path is untouched (`app.channels.api.timeline.ask`/`_stream_turn`): a red
    word is answered before `recall`/`ask_stream` is ever called at all, so neither asker's
    clarify logic can ever run for one. Proven here at the boundary this module owns: a red
    question given straight to the rule-based composer still never carries a `clarify`,
    because `_clarify_for` is never even reached once a red-flag reroute or honest line has
    already been decided — the ordering the route enforces is exercised in
    `tests/test_ask_http_stream.py`."""
    rec = await record(sg)
    answer = await recall(
        sg,
        context=rec.owner,
        question="I feel very dizzy and shaky",
        mode=Mode.TEXT,
        retriever=KeywordRetriever(),
        store=LocalObjectStore(tmp_path, Region.SG),
        registry=REGISTRY,
    )
    assert answer.clarify is None


# --- a tap's own token, resolved on the next turn (`resolve_clarify_value`) -------------------


async def test_resolve_clarify_value_happy_path(sg: AsyncSession, tmp_path: Path) -> None:
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, Region.SG)
    conversation = await current_conversation(sg, context=rec.owner)
    corpus = _corpus_with_papers(2)
    reader = await reader_of(sg, rec.owner, "en")
    clarify = _clarify_for("what did my blood test show", corpus, rec.owner, "en", reader)
    assert clarify is not None
    answer = Answer(
        question_artifact_id=uuid.uuid4(),
        mode=Mode.TEXT,
        language="en",
        lines=(),
        honest=(),
        boundary=(),
        withheld=(),
        dropped=0,
        clarify=clarify,
    )
    kept = await _keep_question(sg, rec.owner, store, "what about my test")
    await record_turn(
        sg,
        context=rec.owner,
        store=store,
        conversation=conversation,
        question_artifact_id=kept.id,
        answer=answer,
    )
    picked = clarify.options[0]
    resolved = await resolve_clarify_value(
        sg, context=rec.owner, store=store, conversation=conversation, value=picked.value
    )
    assert resolved is not None
    cite, label = resolved
    assert cite.kind == "paper_artifact"
    assert cite.id == picked.cite.id
    assert label == picked.label
    entries = await trail(sg, rec.owner)
    matches = [e for e in entries if e.target == "clarify_token" and e.outcome == Outcome.ALLOWED]
    assert matches and matches[-1].rows == 1


async def test_resolve_clarify_value_wrong_value_refused_and_audited_with_zero_rows(
    sg: AsyncSession, tmp_path: Path
) -> None:
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, Region.SG)
    conversation = await current_conversation(sg, context=rec.owner)
    corpus = _corpus_with_papers(2)
    reader = await reader_of(sg, rec.owner, "en")
    clarify = _clarify_for("what did my blood test show", corpus, rec.owner, "en", reader)
    assert clarify is not None
    answer = Answer(
        question_artifact_id=uuid.uuid4(),
        mode=Mode.TEXT,
        language="en",
        lines=(),
        honest=(),
        boundary=(),
        withheld=(),
        dropped=0,
        clarify=clarify,
    )
    kept = await _keep_question(sg, rec.owner, store, "what about my test")
    await record_turn(
        sg, context=rec.owner, store=store, conversation=conversation,
        question_artifact_id=kept.id, answer=answer,
    )
    resolved = await resolve_clarify_value(
        sg, context=rec.owner, store=store, conversation=conversation, value="not-a-real-token"
    )
    assert resolved is None
    entries = await trail(sg, rec.owner)
    matches = [e for e in entries if e.target == "clarify_token"]
    assert matches and matches[-1].rows == 0


async def test_resolve_clarify_value_replayed_on_a_different_profile_is_refused(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """A token minted under Pa's conversation, replayed against a caregiver's own conversation
    (a different row, a different person): `conversation` here is always already scoped to the
    caller's own key by `current_conversation`/`conversation_by_id`, so the token can never
    even be looked up under someone else's thread — nothing leaked, refused the same as any
    other stale token."""
    rec = await record(sg)
    pa_store = LocalObjectStore(tmp_path, Region.SG)
    pa_conversation = await current_conversation(sg, context=rec.owner)
    corpus = _corpus_with_papers(2)
    reader = await reader_of(sg, rec.owner, "en")
    clarify = _clarify_for("what did my blood test show", corpus, rec.owner, "en", reader)
    assert clarify is not None
    answer = Answer(
        question_artifact_id=uuid.uuid4(), mode=Mode.TEXT, language="en", lines=(), honest=(),
        boundary=(), withheld=(), dropped=0, clarify=clarify,
    )
    kept = await _keep_question(sg, rec.owner, pa_store, "what about my test")
    await record_turn(
        sg, context=rec.owner, store=pa_store, conversation=pa_conversation,
        question_artifact_id=kept.id, answer=answer,
    )
    mei_conversation = await current_conversation(sg, context=rec.mei)
    resolved = await resolve_clarify_value(
        sg, context=rec.mei, store=pa_store, conversation=mei_conversation, value=clarify.options[0].value
    )
    assert resolved is None


# --- the waiting-paper option shape (kind + backend date + "not yet checked") ----------------


def test_waiting_paper_clarify_option_label_shape() -> None:
    dated = _waiting_clarify_label("blood test", "Saturday 12 September", "en")
    assert dated == "blood test of Saturday 12 September, not yet checked"
    # No digits beyond the ones inside the given date string itself, and never a bare number.
    undated = _waiting_clarify_label("blood test", None, "en")
    assert undated == "blood test, not yet checked"
